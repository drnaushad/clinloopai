"""
benchmark.py — ClinLoop AI Benchmarking Suite

Compares the deterministic engine with fitted ML/neural baselines on a synthetic group holdout.
Calculates metrics: Sensitivity, Specificity, F1, Alert Fatigue.
Stratifies performance by risk severity.
"""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, roc_curve, auc, precision_recall_curve, brier_score_loss, log_loss

from .loop_detector import ClinLoopDetector
from ..validation.learned_baselines import event_features, grouped_split, train_and_predict
from .safety_clock import normalize_timestamp

# Fixed evaluation clock, after the last synthetic event (Nov 2026). Using the
# wall clock would make AUROC/PR-AUC change depending on the day it is run.
BENCHMARK_EVALUATION_TIME = datetime(2027, 1, 1)


class BenchmarkSuite:
    def __init__(self, scenarios: List[Dict], evaluation_time: Optional[datetime] = None):
        self.scenarios = [s.to_dict() if hasattr(s, "to_dict") else s for s in scenarios]
        self.evaluation_time = normalize_timestamp(evaluation_time or BENCHMARK_EVALUATION_TIME)
        self.clinloop = ClinLoopDetector(evaluation_time=self.evaluation_time)
        self.results = {}
        
    def _calculate_metrics(self, y_true: List[bool], y_pred: List[bool], y_scores: List[float], name: str) -> Dict:
        """Calculate standard classification metrics."""
        cm = confusion_matrix(y_true, y_pred, labels=[False, True])
        
        # Handle edge cases where one class might be missing
        if cm.shape == (1, 1):
            if y_true[0]:
                cm = np.array([[0, 0], [0, cm[0,0]]])
            else:
                cm = np.array([[cm[0,0], 0], [0, 0]])
                
        tn, fp, fn, tp = cm.ravel()
        
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        f1 = 2 * (precision * sensitivity) / (precision + sensitivity) if (precision + sensitivity) > 0 else 0.0
        
        # Alert fatigue = False Positives per 100 total cases
        alert_fatigue = (fp / len(y_true)) * 100 if len(y_true) > 0 else 0.0
        
        # ROC and PR curves
        fpr, tpr, _ = roc_curve(y_true, y_scores)
        roc_auc = auc(fpr, tpr)
        
        pr_prec, pr_rec, _ = precision_recall_curve(y_true, y_scores)
        pr_auc = auc(pr_rec, pr_prec)
        
        return {
            "name": name,
            "tp": int(tp), "tn": int(tn), "fp": int(fp), "fn": int(fn),
            "sensitivity": float(sensitivity),
            "specificity": float(specificity),
            "precision": float(precision),
            "f1_score": float(f1),
            "alert_fatigue": float(alert_fatigue),
            "roc_auc": float(roc_auc),
            "pr_auc": float(pr_auc),
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "pr_prec": pr_prec.tolist(),
            "pr_rec": pr_rec.tolist()
        }

    def run(self) -> Dict:
        """A fixed patient/duplicate-group holdout; every comparator sees the same cases.

        The label is an open OR delayed synthetic obligation, including a late
        completion. It does not mean the patient currently needs an intervention.
        No reference-label simulator is treated as a measured comparator.
        """
        import platform
        import sklearn
        from .governance import ruleset_version

        keys = [s.get("scenario_id") for s in self.scenarios]
        if any(not isinstance(key, str) or not key.strip() for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Research cohort requires unique nonempty scenario keys")
        if any(s.get("ground_truth_status") not in {"open", "closed", "delayed"} for s in self.scenarios):
            raise ValueError("Research cohort requires explicit binary-evaluable reference statuses")
        features = [event_features(s, self.evaluation_time) for s in self.scenarios]
        train, test, split = grouped_split(self.scenarios, features)
        labels = [s["ground_truth_status"] in ("open", "delayed") for s in self.scenarios]
        y_train, y_true = [labels[i] for i in train], [labels[i] for i in test]
        if set(y_train) != {False, True} or set(y_true) != {False, True}:
            raise ValueError("Fixed research split lacks a class; collect more independent groups")
        print(f"Synthetic group holdout: {len(train)} training / {len(test)} test trajectories")
        learned = train_and_predict([features[i] for i in train], y_train, [features[i] for i in test])
        # Inference receives observed events and grouping keys only. Labels,
        # severity annotations, scenario names and missing-followup hints stay out.
        views = [{"scenario_id": self.scenarios[i]["scenario_id"],
                  "patient_id": self.scenarios[i]["patient_id"],
                  "events": [e for e in self.scenarios[i]["events"]
                             if normalize_timestamp(e["timestamp"]) <= self.evaluation_time]}
                 for i in test]
        batch = self.clinloop.process_batch(views)
        predictions = []
        for view in views:
            detections = batch.get(view["scenario_id"], [])
            top = detections[0] if detections else None
            predictions.append({"predicted_status": top.loop_status if top else "closed",
                                "predicted_risk": top.risk_score if top else 0.0,
                                "predicted_abstain": top.should_abstain if top else False})
        cl_labels = [p["predicted_status"] in ("open", "delayed", "needs_human_review") for p in predictions]
        scores = {"ClinLoop AI": [p["predicted_risk"] for p in predictions]}
        predicted = {"ClinLoop AI": cl_labels}
        metrics = {"ClinLoop AI": self._calculate_metrics(y_true, cl_labels, scores["ClinLoop AI"], "ClinLoop AI")}
        positives = sum(y_true)
        metrics["ClinLoop AI"]["sensitivity_including_abstention_as_miss"] = (
            sum(y and predicted and not row["predicted_abstain"]
                for y, predicted, row in zip(y_true, cl_labels, predictions)) / positives if positives else None)
        metrics["ClinLoop AI"]["coverage_without_abstention"] = sum(not p["predicted_abstain"] for p in predictions) / len(predictions)
        metrics["ClinLoop AI"]["sensitivity_scope"] = "Triage recall includes referral to human review; autonomous recall excludes abstentions"
        for name, result in learned.items():
            scores[name] = result["scores"]
            predicted[name] = [score >= 0.5 for score in result["scores"]]
            metrics[name] = self._calculate_metrics(y_true, predicted[name], scores[name], name)
            metrics[name]["training"] = {k: v for k, v in result.items() if k != "scores"}
            metrics[name]["threshold"] = 0.5
            metrics[name]["brier_score"] = float(brier_score_loss(y_true, scores[name]))
            metrics[name]["log_loss"] = float(log_loss(y_true, scores[name], labels=[False, True]))
        stratified = {}
        for severity in ("critical", "high", "moderate", "low"):
            positions = [j for j, i in enumerate(test)
                         if self.scenarios[i].get("ground_truth_severity", "").lower() == severity]
            if not positions:
                continue
            positives = sum(y_true[j] for j in positions)
            stratified[severity] = {"count": len(positions), "positive_references": positives,
                                    "sensitivity": {name: (sum(y_true[j] and rows[j] for j in positions) / positives
                                                           if positives else None)
                                                    for name, rows in predicted.items()}}
        self.results = {
            "schema_version": 2, "overall": metrics, "stratified": stratified,
            "cohort_samples": len(self.scenarios), "n_samples": len(test), "split": split,
            "evaluation_time": self.evaluation_time.isoformat(),
            "abstention_rate": sum(p["predicted_abstain"] for p in predictions) / len(predictions),
            "scope": "Synthetic event-trajectory software experiment; not report-text, LLM or clinical accuracy",
            "target": "Open or delayed obligation, including a completed-late task; not current treatment need",
            "feature_contract": "Observed typed events and temporal edges only; no IDs, reference labels, scenario hints, rule outputs or future events",
            "preprocessing_fit": "training partition only", "model_artifacts_saved": False,
            "clinical_state_modified": False, "clinical_accuracy_established": False,
            "probability_calibration": "Not established; all scores are research ranking outputs",
            "provenance": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                           "numpy": np.__version__, "ruleset_version": ruleset_version(), "seed": 42,
                           "research_source_sha256": hashlib.sha256(
                               Path(__file__).read_bytes() +
                               (Path(__file__).parents[1] / "validation" / "learned_baselines.py").read_bytes()).hexdigest()},
            "excluded_comparators": {"EMRInboxBaseline": "Reference-label simulation, not a measured hospital system",
                                      "LLMBaseline": "Reference-label simulation, not an LLM inference or fitted model"},
            "limits": ["Synthetic generator labels share assumptions with the rule engine",
                       "Patient separation is within this synthetic cohort only",
                       "No template-family, site, temporal or external clinical validation",
                       "No learned comparator can open, close or suppress a clinical task",
                       "Learned baselines use structured event features, not raw reports or images"],
        }
        return self.results

    def save_results(self, output_dir: str):
        """Save benchmark results to JSON."""
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "benchmark_results.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, allow_nan=False)
        print(f"  ✓ Saved benchmark results to {path}")
