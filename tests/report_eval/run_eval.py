"""
Blind evaluation harness: each case (one report + patient context) → FHIR resources → the real ClinLoop
pipeline (bundle_to_events → ClinLoopDetector) → the set of rule ids it opens. Compared with the
clinician-written expected set. Usage: python tests/report_eval/run_eval.py tests/report_eval/cases.json [dev|heldout|confirm|all] [--show]
"""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402

REPORT_RULES = {"R003", "R009", "R018", "R019", "R020", "R030", "R031", "R032", "R033", "R034", "R035", "R036",
                "R037", "R038", "R039", "R040", "R041", "R042", "R043", "R044", "R045", "R046"}
# The app raises one alert per finding: a guideline rule and the radiologist's own recommendation for the
# same study are de-duplicated (one follow-up closes both). "Equivalent" counts an expected rule as covered
# when an alert from the same clinical group (imaging follow-up vs work-up/referral) was raised.
GROUPS = [{"R003", "R019", "R034", "R030", "R031", "R032", "R033", "R037", "R040", "R041", "R043", "R044"},
          {"R036", "R039", "R018", "R020", "R046", "R038", "R042", "R045", "R009"}, {"R035"}]


def group(r):
    return next((g for g in GROUPS if r in g), {r})


def equivalent(exp, got):
    return all(r in got or group(r) & got for r in exp) and all(r in exp or group(r) & exp for r in got)


SMOKING = {"current": ("77176002", "Current smoker"), "former": ("8517006", "Former smoker"),
           "never": ("266919005", "Never smoked")}


def resources(case):
    pid = "P-" + case["id"]
    date = datetime.fromisoformat(case["date"][:10])
    p = case.get("patient") or {}
    born = date - timedelta(days=int(p.get("age") or 60) * 365.25 + 100)
    out = [{"resourceType": "Patient", "id": pid, "gender": p.get("sex") or "unknown",
            "birthDate": born.date().isoformat()}]
    sm = SMOKING.get(p.get("smoking"))
    if sm:
        out.append({"resourceType": "Observation", "id": f"{pid}-smk", "status": "final",
                    "subject": {"reference": f"Patient/{pid}"},
                    "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2"}], "text": "Tobacco smoking status"},
                    "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": sm[0]}], "text": sm[1]},
                    "effectiveDateTime": (date - timedelta(days=30)).date().isoformat()})
    if p.get("known_malignancy"):
        out.append({"resourceType": "Condition", "id": f"{pid}-ca", "subject": {"reference": f"Patient/{pid}"},
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "C50.9"}],
                             "text": "Malignant neoplasm"},
                    "recordedDate": (date - timedelta(days=400)).date().isoformat()})
    if p.get("immunocompromised"):
        out.append({"resourceType": "Condition", "id": f"{pid}-ic", "subject": {"reference": f"Patient/{pid}"},
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "D84.9"}],
                             "text": "Immunodeficiency"},
                    "recordedDate": (date - timedelta(days=400)).date().isoformat()})
    cat = "RAD" if case.get("report_type", "radiology") == "radiology" else "PAT"
    out.append({"resourceType": "DiagnosticReport", "id": f"{pid}-rep", "status": "final",
                "category": [{"coding": [{"code": cat}]}], "code": {"text": case.get("title") or ""},
                "subject": {"reference": f"Patient/{pid}"}, "effectiveDateTime": case["date"][:10] + "T09:00:00Z",
                "conclusion": case["text"]})
    return pid, date, out


def run_case(case):
    pid, date, res = resources(case)
    events, warnings = bundle_to_events(res)
    dets = ClinLoopDetector(evaluation_time=date + timedelta(days=1)).process_patient("eval", pid, events.get(pid, []))
    got = {d.rule_id for d in dets if d.rule_id in REPORT_RULES}
    days = {d.rule_id: round((datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds() / 86400, 1)
            for d in dets if d.rule_id in REPORT_RULES}
    return got, days


def main():
    path, which = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "all")
    show = "--show" in sys.argv
    cases = [c for c in json.load(open(path)) if which == "all" or c["set"] == which]
    tp, fp, fn = Counter(), Counter(), Counter()
    exact = equiv = 0
    none_cases = none_ok = pos_cases = pos_any = 0
    window_ok = window_n = 0
    failures = []
    for c in cases:
        exp = set(c.get("expected_rules") or []) & REPORT_RULES
        try:
            got, days = run_case(c)
        except Exception as e:  # a crash is a failure
            got, days = {"CRASH:" + type(e).__name__}, {}
        for r in exp & got:
            tp[r] += 1
        for r in got - exp:
            fp[r] += 1
        for r in exp - got:
            fn[r] += 1
        exact += int(exp == got)
        equiv += int(equivalent(exp, got))
        if not exp:
            none_cases += 1
            none_ok += int(not got)
        else:
            pos_cases += 1
            pos_any += int(bool(exp & got))
        w = c.get("expected_window_days")
        if w and exp & got:
            main_rule = sorted(exp & got)[0]
            window_n += 1
            window_ok += int(w[0] * 0.8 <= days.get(main_rule, -1) <= w[1] * 1.25 + 7)
        if not equivalent(exp, got):
            failures.append((c["id"], c["language"], sorted(exp), sorted(got), c["text"][:160], c.get("patient")))
    n = len(cases)
    TP, FP, FN = sum(tp.values()), sum(fp.values()), sum(fn.values())
    print(f"set={which} cases={n}")
    print(f"exact match (report level): {exact}/{n} = {exact / n:.1%}")
    print(f"clinically equivalent (same finding, same kind of follow-up): {equiv}/{n} = {equiv / n:.1%}")
    print(f"obligation sensitivity (rule level): {TP}/{TP + FN} = {TP / max(1, TP + FN):.1%}")
    print(f"obligation PPV (rule level): {TP}/{TP + FP} = {TP / max(1, TP + FP):.1%}")
    print(f"reports needing follow-up with ≥1 correct obligation: {pos_any}/{pos_cases} = {pos_any / max(1, pos_cases):.1%}")
    print(f"reports needing nothing with no alert (specificity): {none_ok}/{none_cases} = {none_ok / max(1, none_cases):.1%}")
    if window_n:
        print(f"deadline within the expected window: {window_ok}/{window_n} = {window_ok / window_n:.1%}")
    print("per rule (tp/fn/fp):", {r: (tp[r], fn[r], fp[r]) for r in sorted(set(tp) | set(fn) | set(fp))})
    if show:
        for f in failures:
            print("\n", f[0], f[1], "expected", f[2], "got", f[3], "|", f[5], "\n   ", f[4])


if __name__ == "__main__":
    main()
