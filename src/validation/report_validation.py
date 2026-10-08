"""
report_validation.py — Report-level validation of ClinLoop's radiology reading

Answers one question per report, before any follow-up is considered:
"Which follow-up obligations should this report create?"  A radiologist
labels each report blind to ClinLoop; the tool then measures, per rule,
how often ClinLoop agrees (sensitivity, PPV, with Wilson 95% intervals)
and lists every disagreement for adjudication.

Workflow:
  1. template  One row per radiology report in a FHIR export, with the text
               de-identified, patient context columns (age, sex, smoking,
               cancer) and an empty `expected_rules` column. No prediction is
               included, so labelling is blind.
  2. label     A radiologist fills `expected_rules` with rule IDs separated by
               ';' (empty = the report creates no obligation).
  3. score     ClinLoop reads every report and the labels are compared.

Usage:
  python -m src.validation.report_validation template --fhir export.json --out sheet.csv
  python -m src.validation.report_validation score --sheet sheet.csv [--out result.json]

Each report is scored on its own (no earlier reports), so stepped Fleischner
follow-up is not exercised here; the chart review (chart_review.py) covers
whole patient histories. Synthetic sheets (data/radiology_validation_synthetic.csv)
test the tool; they are not clinical validation.
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402

SHEET_FIELDS = ["report_id", "study", "report_date", "conclusion", "age", "sex", "smoking", "cancer",
                "expected_rules", "notes"]
SMOKING_SNOMED = {"current": "449868002", "former": "8517006", "never": "266919005"}
RULE_IDS = {r.rule_id for r in OBLIGATION_RULES}


# ── 1. Template ──────────────────────────────────────────────────────────────

def _is_radiology(r: Dict) -> bool:
    text = json.dumps(r.get("category", [])).lower()
    return r.get("resourceType") == "DiagnosticReport" and any(k in text for k in ('"rad"', "imaging", "radiology"))


def template_rows(bundle: Dict, deidentify: bool = True) -> List[Dict]:
    from src.clinloop_engine.phi_deidentifier import PHIDeidentifier
    scrub = PHIDeidentifier()._scrub_text
    resources = [e.get("resource", e) for e in bundle.get("entry", [])] if bundle.get("resourceType") == "Bundle" else bundle
    patients = {r["id"]: r for r in resources if r.get("resourceType") == "Patient" and r.get("id")}
    rows = []
    for i, r in enumerate(x for x in resources if _is_radiology(x)):
        pid = str((r.get("subject") or {}).get("reference", "")).split("/")[-1]
        p = patients.get(pid, {})
        when = r.get("effectiveDateTime") or r.get("issued") or ""
        age = ""
        if p.get("birthDate") and when:
            age = str(int(when[:4]) - int(p["birthDate"][:4]))
        text = r.get("conclusion", "")
        if deidentify:
            text, _ = scrub(text)
        rows.append({"report_id": f"RPT-{i + 1:04d}", "study": (r.get("code") or {}).get("text", ""),
                     "report_date": when[:10], "conclusion": text, "age": age, "sex": p.get("gender", ""),
                     "smoking": "", "cancer": "", "expected_rules": "", "notes": ""})
    return rows


# ── 3. Scoring ───────────────────────────────────────────────────────────────

def _parse_rules(value: str) -> Set[str]:
    rules = {x.strip().upper() for x in (value or "").replace(",", ";").split(";") if x.strip()}
    unknown = rules - RULE_IDS
    if unknown:
        raise ValueError(f"Unknown rule id(s): {', '.join(sorted(unknown))}")
    return rules


def predict(row: Dict) -> Tuple[Set[str], List[str]]:
    """Rules ClinLoop creates for one report (whatever their follow-up status), and its reading notes."""
    when = (row.get("report_date") or "2026-01-01")[:10] + "T09:00:00Z"
    resources = [{"resourceType": "DiagnosticReport", "id": "r", "status": "final",
                  "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": row.get("study", "")},
                  "subject": {"reference": "Patient/P"}, "effectiveDateTime": when,
                  "conclusion": row.get("conclusion", "")}]
    patient: Dict = {"resourceType": "Patient", "id": "P"}
    if str(row.get("age", "")).strip().isdigit():
        patient["birthDate"] = f"{int(when[:4]) - int(row['age'])}-01-01"   # age on the report date
    if row.get("sex"):
        patient["gender"] = row["sex"].strip().lower()
    resources.append(patient)
    smoking = (row.get("smoking") or "").strip().lower()
    if smoking in SMOKING_SNOMED:
        resources.append({"resourceType": "Observation", "id": "smk", "status": "final",
                          "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2"}]},
                          "subject": {"reference": "Patient/P"}, "effectiveDateTime": when,
                          "valueCodeableConcept": {"coding": [{"code": SMOKING_SNOMED[smoking]}]}})
    if (row.get("cancer") or "").strip().lower() in ("yes", "y", "1", "true"):
        resources.append({"resourceType": "Condition", "id": "ca", "subject": {"reference": "Patient/P"},
                          "clinicalStatus": {"coding": [{"code": "active"}]},
                          "code": {"coding": [{"code": "C80.1"}], "text": "Malignant neoplasm"},
                          "recordedDate": "2000-01-01"})
    events, _ = bundle_to_events(resources)
    if "P" not in events:
        return set(), []
    evaluation = datetime.fromisoformat(when.replace("Z", "")).replace(hour=12)
    dets = ClinLoopDetector(evaluation_time=evaluation).process_patient("validation", "P", events["P"])
    report = next((e for e in events["P"] if e["event_type"] == "radiology_report"), None)
    notes = report["details"].get("mapping", [])[1:] if report else []
    return {d.rule_id for d in dets}, notes


def wilson(successes: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if n == 0:
        return None, None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(p, 3), round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def score(rows: Sequence[Dict]) -> Dict:
    per_rule: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    discordant = []
    exact = 0
    labelled = [r for r in rows if r.get("expected_rules") is not None]
    for row in labelled:
        expected = _parse_rules(row.get("expected_rules", ""))
        predicted, notes = predict(row)
        for rule in expected | predicted:
            key = "tp" if rule in expected and rule in predicted else "fn" if rule in expected else "fp"
            per_rule[rule][key] += 1
        if expected == predicted:
            exact += 1
        else:
            discordant.append({"report_id": row.get("report_id"), "study": row.get("study"),
                               "conclusion": row.get("conclusion"), "expected": sorted(expected),
                               "clinloop": sorted(predicted), "missed": sorted(expected - predicted),
                               "extra": sorted(predicted - expected), "clinloop_reading": notes})
    rules_out = {}
    for rule, c in sorted(per_rule.items()):
        sens = wilson(c["tp"], c["tp"] + c["fn"])
        ppv = wilson(c["tp"], c["tp"] + c["fp"])
        rules_out[rule] = {**c, "sensitivity": sens[0], "sensitivity_95ci": sens[1:],
                           "ppv": ppv[0], "ppv_95ci": ppv[1:]}
    tp = sum(c["tp"] for c in per_rule.values())
    fp = sum(c["fp"] for c in per_rule.values())
    fn = sum(c["fn"] for c in per_rule.values())
    sens, ppv = wilson(tp, tp + fn), wilson(tp, tp + fp)
    return {"reports": len(labelled), "exact_agreement": exact,
            "overall": {"tp": tp, "fp": fp, "fn": fn, "sensitivity": sens[0], "sensitivity_95ci": sens[1:],
                        "ppv": ppv[0], "ppv_95ci": ppv[1:]},
            "per_rule": rules_out, "discordant": discordant}


def _print_summary(result: Dict) -> None:
    o = result["overall"]
    print(f"Reports: {result['reports']}  exact agreement: {result['exact_agreement']}")
    print(f"Overall sensitivity {o['sensitivity']} (95% CI {o['sensitivity_95ci']}), PPV {o['ppv']} (95% CI {o['ppv_95ci']})")
    print(f"{'rule':6} {'TP':>4} {'FP':>4} {'FN':>4}  sensitivity   PPV")
    for rule, c in result["per_rule"].items():
        print(f"{rule:6} {c['tp']:>4} {c['fp']:>4} {c['fn']:>4}  {str(c['sensitivity']):>11}  {str(c['ppv']):>5}")
    for d in result["discordant"]:
        print(f"\n✗ {d['report_id']} [{d['study']}] expected {d['expected']} ClinLoop {d['clinloop']}\n  {d['conclusion']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template", help="Build a blind labelling sheet from a FHIR export")
    t.add_argument("--fhir", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--keep-text", action="store_true", help="Do not de-identify the report text")
    s = sub.add_parser("score", help="Compare ClinLoop with a labelled sheet")
    s.add_argument("--sheet", required=True)
    s.add_argument("--out")
    args = ap.parse_args(argv)

    if args.cmd == "template":
        with open(args.fhir, encoding="utf-8") as f:
            rows = template_rows(json.load(f), deidentify=not args.keep_text)
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SHEET_FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {len(rows)} reports to {args.out}. Fill expected_rules (e.g. R003;R035), blind to ClinLoop.")
        return 0

    with open(args.sheet, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = score(rows)
    _print_summary(result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
