"""
benchmark.py — ClinLoop AI Benchmarking Suite

Evaluates the performance of ClinLoop AI against baselines (EMR Inbox, LLM).
Calculates metrics: Sensitivity, Specificity, F1, Alert Fatigue.
Stratifies performance by risk severity.
"""

import json
import os
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, f1_score, roc_curve, auc, precision_recall_curve

from .loop_detector import ClinLoopDetector
from .baselines import EMRInboxBaseline, LLMBaseline

class BenchmarkSuite:
    def __init__(self, scenarios: List[Dict]):
        self.scenarios = [s.to_dict() if hasattr(s, "to_dict") else s for s in scenarios]
        self.clinloop = ClinLoopDetector()
        self.emr_baseline = EMRInboxBaseline()
        self.llm_baseline = LLMBaseline(hallucination_rate=0.14)
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
        """Run all detectors and compute benchmark metrics."""
        print(f"Running benchmark on {len(self.scenarios)} scenarios...")
        
        # 1. Get predictions
        print("  Evaluating ClinLoop AI (Neuro-Symbolic)...")
        clinloop_preds = self.clinloop.get_predictions(self.scenarios)
        
        print("  Evaluating EMR Inbox Baseline...")
        emr_preds = self.emr_baseline.predict(self.scenarios)
        
        print("  Evaluating LLM Zero-shot Baseline...")
        llm_preds = self.llm_baseline.predict(self.scenarios)
        
        # 2. Extract ground truth (Positive class = OPEN or DELAYED loop)
        y_true = [s["ground_truth_status"] in ("open", "delayed") for s in self.scenarios]
        
        # 3. Extract predicted labels and scores
        # ClinLoop
        cl_pred_labels = [p["predicted_status"] in ("open", "delayed", "needs_human_review") for p in clinloop_preds]
        cl_pred_scores = [p["predicted_risk"] for p in clinloop_preds]
        
        # EMR
        emr_pred_labels = [p["predicted_status"] in ("open", "delayed") for p in emr_preds]
        emr_pred_scores = [p["predicted_risk"] for p in emr_preds]
        
        # LLM
        llm_pred_labels = [p["predicted_status"] in ("open", "delayed") for p in llm_preds]
        llm_pred_scores = [p["predicted_risk"] for p in llm_preds]
        
        # 4. Calculate overall metrics
        metrics = {
            "ClinLoop AI": self._calculate_metrics(y_true, cl_pred_labels, cl_pred_scores, "ClinLoop AI"),
            "EMR Baseline": self._calculate_metrics(y_true, emr_pred_labels, emr_pred_scores, "EMR Baseline"),
            "LLM Baseline": self._calculate_metrics(y_true, llm_pred_labels, llm_pred_scores, "LLM Baseline")
        }
        
        # 5. Stratify by severity
        severities = ["critical", "high", "moderate", "low"]
        stratified = {}
        
        for sev in severities:
            # Indices for this severity
            idx = [i for i, s in enumerate(self.scenarios) if s.get("ground_truth_severity", "").lower() == sev]
            
            if not idx:
                continue
                
            y_true_sev = [y_true[i] for i in idx]
            cl_pred_sev = [cl_pred_labels[i] for i in idx]
            emr_pred_sev = [emr_pred_labels[i] for i in idx]
            llm_pred_sev = [llm_pred_labels[i] for i in idx]
            
            stratified[sev] = {
                "count": len(idx),
                "ClinLoop_Sens": recall_score(y_true_sev, cl_pred_sev, zero_division=0) if any(y_true_sev) else 1.0,
                "EMR_Sens": recall_score(y_true_sev, emr_pred_sev, zero_division=0) if any(y_true_sev) else 1.0,
                "LLM_Sens": recall_score(y_true_sev, llm_pred_sev, zero_division=0) if any(y_true_sev) else 1.0,
            }
            
        self.results = {
            "overall": metrics,
            "stratified": stratified,
            "n_samples": len(self.scenarios),
            "abstention_rate": sum(p["predicted_abstain"] for p in clinloop_preds) / len(clinloop_preds)
        }
        
        return self.results

    def save_results(self, output_dir: str):
        """Save benchmark results to JSON."""
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "benchmark_results.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2)
        print(f"  ✓ Saved benchmark results to {path}")
