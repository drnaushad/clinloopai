"""
chart_review.py — Stage 1 retrospective validation toolkit
(docs/LIFE_SAVING_ROADMAP.md §7, reporting per TRIPOD+AI)

Workflow:
  1. sample   Run the engine over a FHIR export, build one row per loop, and
              draw a stratified random sample (strata = rule × prediction),
              so rare rules and both predicted classes are represented.
  2. review   Two clinicians, blinded to ClinLoop's prediction, answer for
              each sampled loop: "Was the required follow-up completed within
              the guideline window?"  (yes / no / unclear). Disagreements go
              to a third adjudicator.
  3. analyze  Merge the reviews with the (separately kept) prediction key and
              estimate sensitivity, specificity, PPV and NPV. Estimates are
              weighted by the inverse sampling fraction of each stratum, with
              stratified-bootstrap 95% CIs, plus Cohen's kappa between the two
              reviewers.

Positive class = loop NOT closed in time (the patient is exposed).

Usage:
  python -m src.validation.chart_review sample --fhir export.json --out review/ \
         --per-stratum 20 [--evaluation-time 2026-09-01T00:00:00]
  python -m src.validation.chart_review analyze --packet review/review_packet.csv \
         --key review/prediction_key.csv
"""

import argparse
import csv
import json
import os
import random
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.clinloop_engine.clinical_ontology import format_window  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.safety_clock import normalize_timestamp  # noqa: E402

SEED = 42
PREDICTED_POSITIVE = {"open", "delayed", "needs_human_review"}
ANSWERS = {"yes", "no", "unclear"}

PACKET_FIELDS = ["review_id", "patient_id", "source_record", "obligation", "trigger_time",
                 "required_followup", "window", "deadline",
                 "reviewer_1", "reviewer_2", "adjudicator", "notes"]
KEY_FIELDS = ["review_id", "rule_id", "predicted_status", "predicted_positive", "stratum", "weight"]


# ── 1. Sampling ──────────────────────────────────────────────────────────────

def build_frame(fhir_bundle: Dict, evaluation_time: Optional[str] = None) -> List[Dict]:
    """One row per loop the engine identified in the export."""
    when = normalize_timestamp(evaluation_time) if evaluation_time else None
    events_by_patient, _ = bundle_to_events(fhir_bundle)
    detector = ClinLoopDetector(evaluation_time=when)
    frame = []
    for pid, events in sorted(events_by_patient.items()):
        for d in detector.process_patient("chart-review", pid, events):
            frame.append({
                "patient_id": pid, "rule_id": d.rule_id, "rule_name": d.rule_name,
                "trigger_event_id": d.trigger_event_id, "trigger_time": d.trigger_time,
                "deadline": d.deadline, "missing_step": d.missing_step,
                "predicted_status": d.loop_status,
                "predicted_positive": d.loop_status in PREDICTED_POSITIVE,
            })
    return frame


def stratified_sample(frame: Sequence[Dict], per_stratum: int, seed: int = SEED) -> List[Dict]:
    """
    Sample up to `per_stratum` loops from each (rule, predicted class)
    stratum. Each sampled row carries weight = stratum size / sample size,
    so population estimates stay unbiased despite oversampling rare strata.
    """
    rng = random.Random(seed)
    strata: Dict[str, List[Dict]] = defaultdict(list)
    for row in frame:
        strata[f"{row['rule_id']}|{'pos' if row['predicted_positive'] else 'neg'}"].append(row)
    sample = []
    for name in sorted(strata):
        rows = strata[name]
        chosen = rng.sample(rows, min(per_stratum, len(rows)))
        for row in chosen:
            sample.append({**row, "stratum": name, "weight": len(rows) / len(chosen)})
    rng.shuffle(sample)  # reviewers must not infer the stratum from the order
    for i, row in enumerate(sample, 1):
        row["review_id"] = f"CR-{i:04d}"
    return sample


def export_review_files(sample: Sequence[Dict], out_dir: str, rules: Dict[str, Dict]) -> Tuple[str, str]:
    """
    Write the blinded packet (for reviewers) and the prediction key (kept
    by the study coordinator). The packet contains no ClinLoop output.
    """
    os.makedirs(out_dir, exist_ok=True)
    packet_path = os.path.join(out_dir, "review_packet.csv")
    key_path = os.path.join(out_dir, "prediction_key.csv")
    with open(packet_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PACKET_FIELDS)
        w.writeheader()
        for r in sorted(sample, key=lambda x: x["review_id"]):
            rule = rules.get(r["rule_id"], {})
            w.writerow({
                "review_id": r["review_id"], "patient_id": r["patient_id"],
                "source_record": r["trigger_event_id"], "obligation": r["rule_name"],
                "trigger_time": r["trigger_time"],
                "required_followup": rule.get("required", ""), "window": rule.get("window", ""),
                "deadline": r["deadline"], "reviewer_1": "", "reviewer_2": "", "adjudicator": "", "notes": "",
            })
    with open(key_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEY_FIELDS)
        w.writeheader()
        for r in sorted(sample, key=lambda x: x["review_id"]):
            w.writerow({k: r[k] for k in KEY_FIELDS})
    return packet_path, key_path


# ── 3. Analysis ──────────────────────────────────────────────────────────────

def _answer(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in ANSWERS else ""


def merge_reviews(packet_rows: Sequence[Dict], key_rows: Sequence[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Reference standard per loop: the two reviewers' shared answer, else the
    adjudicator's. "Was the follow-up completed in time?" → no = positive
    (loop open). Unclear or unresolved loops are excluded and counted.
    """
    key = {k["review_id"]: k for k in key_rows}
    merged, excluded = [], {"unreviewed": 0, "unclear": 0, "disagreement_unresolved": 0}
    for p in packet_rows:
        r1, r2, adj = _answer(p.get("reviewer_1")), _answer(p.get("reviewer_2")), _answer(p.get("adjudicator"))
        if not r1 or not r2:
            excluded["unreviewed"] += 1
            continue
        final = r1 if r1 == r2 else adj
        if not final:
            excluded["disagreement_unresolved"] += 1
            continue
        if final == "unclear":
            excluded["unclear"] += 1
            continue
        k = key[p["review_id"]]
        merged.append({
            "review_id": p["review_id"], "rule_id": k["rule_id"], "stratum": k["stratum"],
            "weight": float(k["weight"]),
            "predicted_positive": str(k["predicted_positive"]).lower() == "true",
            "truth_positive": final == "no",
            "reviewer_1": r1, "reviewer_2": r2,
        })
    return merged, excluded


def _weighted_metrics(rows: Sequence[Dict]) -> Dict[str, Optional[float]]:
    tp = sum(r["weight"] for r in rows if r["predicted_positive"] and r["truth_positive"])
    fp = sum(r["weight"] for r in rows if r["predicted_positive"] and not r["truth_positive"])
    fn = sum(r["weight"] for r in rows if not r["predicted_positive"] and r["truth_positive"])
    tn = sum(r["weight"] for r in rows if not r["predicted_positive"] and not r["truth_positive"])
    div = lambda a, b: a / b if b > 0 else None
    return {"sensitivity": div(tp, tp + fn), "specificity": div(tn, tn + fp),
            "ppv": div(tp, tp + fp), "npv": div(tn, tn + fn)}


def bootstrap_ci(rows: Sequence[Dict], reps: int = 2000, seed: int = SEED) -> Dict[str, Tuple[float, float]]:
    """Stratified bootstrap (resample within each stratum) 95% percentile CIs."""
    rng = random.Random(seed)
    by_stratum: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        by_stratum[r["stratum"]].append(r)
    draws: Dict[str, List[float]] = defaultdict(list)
    for _ in range(reps):
        boot = [rng.choice(s) for s in by_stratum.values() for _ in s]
        for metric, value in _weighted_metrics(boot).items():
            if value is not None:
                draws[metric].append(value)
    ci = {}
    for metric, vals in draws.items():
        vals.sort()
        ci[metric] = (vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))])
    return ci


def cohens_kappa(rows: Sequence[Dict]) -> Optional[float]:
    """Agreement between reviewer 1 and 2 beyond chance (yes/no/unclear)."""
    n = len(rows)
    if n == 0:
        return None
    observed = sum(r["reviewer_1"] == r["reviewer_2"] for r in rows) / n
    expected = sum((sum(r["reviewer_1"] == c for r in rows) / n) * (sum(r["reviewer_2"] == c for r in rows) / n)
                   for c in ANSWERS)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def analyze(packet_rows: Sequence[Dict], key_rows: Sequence[Dict], reps: int = 2000) -> Dict:
    merged, excluded = merge_reviews(packet_rows, key_rows)
    # Kappa uses every loop both reviewers answered, before adjudication
    both = [{"reviewer_1": _answer(p.get("reviewer_1")), "reviewer_2": _answer(p.get("reviewer_2"))}
            for p in packet_rows if _answer(p.get("reviewer_1")) and _answer(p.get("reviewer_2"))]
    estimates = _weighted_metrics(merged)
    return {
        "n_reviewed": len(merged),
        "excluded": excluded,
        "estimates": estimates,
        "ci95": bootstrap_ci(merged, reps=reps) if merged else {},
        "cohens_kappa": cohens_kappa(both),
        "by_rule": {rule: {"n": len(rs), **_weighted_metrics(rs)}
                    for rule, rs in sorted(_group(merged, "rule_id").items())},
        "note": ("Estimates are weighted by inverse sampling fraction per (rule × predicted class) stratum. "
                 "Report with TRIPOD+AI."),
    }


def _group(rows: Sequence[Dict], field: str) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        out[r[field]].append(r)
    return out


def _read_csv(path: str) -> List[Dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _rule_lookup() -> Dict[str, Dict]:
    from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES
    return {r.rule_id: {
        "required": (" or " if r.followup_logic == "any" else " and ").join(
            f.value.replace("_", " ") for f in r.required_followups),
        "window": format_window(r.deadline_days),
    } for r in OBLIGATION_RULES}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ClinLoop Stage 1 chart-review validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="draw a stratified, blinded review sample")
    s.add_argument("--fhir", required=True, help="FHIR R4 Bundle export (JSON)")
    s.add_argument("--out", required=True, help="output directory")
    s.add_argument("--per-stratum", type=int, default=20)
    s.add_argument("--evaluation-time", default=None)
    s.add_argument("--seed", type=int, default=SEED)
    a = sub.add_parser("analyze", help="estimate accuracy from completed reviews")
    a.add_argument("--packet", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args(argv)

    if args.cmd == "sample":
        with open(args.fhir, encoding="utf-8") as f:
            frame = build_frame(json.load(f), args.evaluation_time)
        sample = stratified_sample(frame, args.per_stratum, args.seed)
        packet, key = export_review_files(sample, args.out, _rule_lookup())
        print(f"{len(frame)} loops in frame; {len(sample)} sampled.\n"
              f"Give reviewers:  {packet}\nKeep separately: {key}")
    else:
        print(json.dumps(analyze(_read_csv(args.packet), _read_csv(args.key), args.reps), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
