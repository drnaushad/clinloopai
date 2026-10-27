"""Offline research comparators, never imported by the clinical decision path.

Train logistic-regression, gradient-boosted-tree and two-hidden-layer neural baselines on
observed, typed temporal-event features. Labels, IDs, scenario descriptions,
rule outputs and future events are excluded from predictors. This is not an
LLM, an image interpreter or a calibrated clinical risk model.
"""
import hashlib
import json
import math
import warnings
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from ..clinloop_engine.clinical_ontology import EventType, OBLIGATION_RULES
from ..clinloop_engine.safety_clock import normalize_timestamp

SEED = 42
EVENT_TYPES = frozenset(e.value for e in EventType)
CONDITIONS = frozenset(r.trigger_condition for r in OBLIGATION_RULES)
FLAGS = frozenset({"ABNORMAL", "CRITICAL", "HIGH", "LOW", "NORMAL", "POSITIVE", "NEGATIVE"})
OBSERVED_STATUSES = frozenset({"completed", "pending", "scheduled", "cancelled", "no_show", "unknown"})


def event_features(scenario: Dict[str, Any], evaluation_time: datetime) -> Dict[str, float]:
    """Bounded, identifier-free features from one patient's observed event graph.

    Only adjacent, time-ordered typed edges are used. Arbitrary detail strings,
    outcome annotations and identifiers never become feature names or values.
    """
    pid = scenario.get("patient_id")
    if not isinstance(pid, str) or not pid.strip() or not isinstance(scenario.get("events"), list):
        raise ValueError("Research scenario requires a patient group and event list")
    when = normalize_timestamp(evaluation_time)
    observed = []
    for event in scenario["events"]:
        if not isinstance(event, dict) or event.get("patient_id") != pid:
            raise ValueError("Research trajectory contains an invalid or mixed patient event")
        try:
            timestamp = normalize_timestamp(event["timestamp"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("Research trajectory contains an invalid event time") from None
        if timestamp > when:
            continue
        kind = event.get("event_type")
        kind = kind if isinstance(kind, str) and kind in EVENT_TYPES else "unmapped"
        observed.append((timestamp, kind, event))
    observed.sort(key=lambda row: (row[0], row[1]))
    features = Counter({"events.total": float(len(observed))})
    gaps = defaultdict(list)
    for timestamp, kind, event in observed:
        features[f"event.{kind}.count"] += 1.0
        age = (when - timestamp).total_seconds() / 86400
        age_key = f"event.{kind}.latest_age_days"
        features[age_key] = min(features[age_key], age) if age_key in features else age
        status = str(event.get("status") or "unknown").strip().lower()
        features[f"status.{status if status in OBSERVED_STATUSES else 'unknown'}.count"] += 1.0
        details = event.get("details") or {}
        if not isinstance(details, dict):
            raise ValueError("Research trajectory contains invalid event details")
        condition = details.get("condition")
        if isinstance(condition, str) and condition in CONDITIONS:
            features[f"condition.{condition}.count"] += 1.0
        flag = str(details.get("flag") or "").upper()
        if flag in FLAGS:
            features[f"flag.{flag}.count"] += 1.0
    for left, right in zip(observed, observed[1:]):
        edge = f"transition.{left[1]}>{right[1]}"
        features[edge + ".count"] += 1.0
        gaps[edge].append((right[0] - left[0]).total_seconds() / 86400)
    for edge, values in gaps.items():
        features[edge + ".mean_gap_days"] = float(np.mean(values))
    if observed:
        features["timeline.span_days"] = (observed[-1][0] - observed[0][0]).total_seconds() / 86400
    return dict(sorted(features.items()))


def _predictor_signature(values: Dict) -> str:
    """Canonical numeric vector: absent features and explicit zero both encode zero."""
    if not isinstance(values, dict) or any(not isinstance(k, str) or type(v) not in (int, float)
                                          or not math.isfinite(v) for k, v in values.items()):
        raise ValueError("Research predictors must be finite named numeric values")
    return json.dumps({k: float(v) for k, v in values.items() if v != 0}, sort_keys=True, allow_nan=False)


def grouped_split(scenarios: List[Dict], features: List[Dict], test_size: float = 0.3) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Keep patients and exact predictor duplicates in the same connected group.

    Transitive grouping matters: two visits of one patient may each duplicate
    a different patient's representation. No seed search or label-driven split.
    """
    if len(scenarios) != len(features) or len(scenarios) < 4 or not 0 < test_size < 1:
        raise ValueError("Invalid research cohort or test fraction")
    parents = list(range(len(scenarios)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen_patients, seen_features = {}, {}
    for i, (row, values) in enumerate(zip(scenarios, features)):
        pid = row.get("patient_id")
        if not isinstance(pid, str) or not pid.strip():
            raise ValueError("Research cohort requires explicit patient groups")
        fingerprint = hashlib.sha256(_predictor_signature(values).encode()).hexdigest()
        for seen, key in ((seen_patients, pid), (seen_features, fingerprint)):
            if key in seen:
                parents[find(i)] = find(seen[key])
            else:
                seen[key] = i
    groups = [find(i) for i in range(len(scenarios))]
    if len(set(groups)) < 2:
        raise ValueError("Research cohort has too few independent predictor groups")
    train, test = next(GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=SEED).split(features, groups=groups))
    train_patients = {scenarios[i]["patient_id"] for i in train}
    test_patients = {scenarios[i]["patient_id"] for i in test}
    signature = lambda i: _predictor_signature(features[i])
    duplicate_overlap = len({signature(i) for i in train} & {signature(i) for i in test})
    if train_patients & test_patients or duplicate_overlap:
        raise ValueError("Research partition leakage detected")
    metadata = {"seed": SEED, "requested_test_group_fraction": test_size,
                "train_examples": len(train), "test_examples": len(test),
                "train_patients": len(train_patients), "test_patients": len(test_patients),
                "train_connected_groups": len({groups[i] for i in train}),
                "test_connected_groups": len({groups[i] for i in test}),
                "patient_overlap": len(train_patients & test_patients),
                "exact_predictor_overlap": duplicate_overlap,
                "limits": "Exact predictor grouping does not establish template, site, language or external-cohort independence"}
    return train, test, metadata


def train_and_predict(train_features: List[Dict], train_labels: List[bool],
                      test_features: List[Dict]) -> Dict[str, Dict]:
    """No test labels accepted. Fit preprocessing on training data only.

    Scores are uncalibrated synthetic-classifier outputs, never patient risk.
    Models live in memory; no pickle files, network calls or clinical registry writes.
    """
    if len(train_features) != len(train_labels) or not train_features or not test_features \
            or any(type(y) is not bool for y in train_labels) or set(train_labels) != {False, True}:
        raise ValueError("Research training requires matching features and both binary classes")
    classifiers = {
        "Logistic regression": LogisticRegression(class_weight="balanced", max_iter=500, random_state=SEED),
        "Gradient-boosted trees": HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=7,
                                                                min_samples_leaf=5, early_stopping=False,
                                                                random_state=SEED),
        "Neural network (32,16)": MLPClassifier(hidden_layer_sizes=(32, 16), solver="lbfgs", max_iter=500,
                                               max_fun=15000, random_state=SEED),
    }
    results = {}
    with threadpool_limits(limits=1):
        for name, classifier in classifiers.items():
            model = make_pipeline(DictVectorizer(sparse=False), StandardScaler(), classifier)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ConvergenceWarning)
                model.fit(train_features, train_labels)
            results[name] = {"scores": model.predict_proba(test_features)[:, 1].tolist(),
                             "converged": not any(issubclass(w.category, ConvergenceWarning) for w in caught),
                             "iterations": int(classifier.n_iter_[0] if isinstance(classifier.n_iter_, np.ndarray)
                                               else classifier.n_iter_),
                             "training_only_feature_count": len(model[0].feature_names_),
                             "score_meaning": "Uncalibrated research score; not a clinical risk probability",
                             "can_modify_clinical_state": False}
    return results
