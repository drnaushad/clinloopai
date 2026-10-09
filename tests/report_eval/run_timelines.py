"""
Blind timeline evaluation: does follow-up that happens (or does not) close the right obligations?

Each case is a patient timeline: a first report, then later events (imaging of some modality and body part,
referrals, specialist visits, biopsies, later reports). Every event becomes the FHIR resource a hospital feed
would send; the real pipeline (bundle_to_events → ClinLoopDetector) runs at the evaluation date; each
obligation created by the FIRST report is compared with the clinician's expected status:
  done       the right follow-up happened within the deadline
  done_late  it happened after the deadline
  pending    not done, deadline not yet passed
  missed     not done, deadline passed
Usage: python tests/report_eval/run_timelines.py tests/report_eval/timelines.json [--show]
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402

REPORT_RULES = {"R003", "R009", "R018", "R019", "R020", "R030", "R031", "R032", "R033", "R034", "R035", "R036",
                "R037", "R038", "R039", "R040", "R041", "R042", "R043", "R044", "R045", "R046"}
SMOKING = {"current": ("77176002", "Current smoker"), "former": ("8517006", "Former smoker"),
           "never": ("266919005", "Never smoked")}
DONE = {"done", "done_late"}
# One alert per finding (as in run_eval.py): the guideline rule and the radiologist's own recommendation for
# the same study are one obligation. "Equivalent" compares each finding's status, whichever of the two is raised.
GROUPS = [{"R003", "R019", "R034", "R030", "R031", "R032", "R033", "R037", "R040", "R041", "R043", "R044"},
          {"R036", "R039", "R018", "R020", "R046", "R038", "R042", "R045"}, {"R009"}, {"R035"}]


def by_group(statuses):
    out = {}
    for r, st in statuses.items():
        g = next((i for i, grp in enumerate(GROUPS) if r in grp), r)
        out.setdefault(g, set()).add(st)
    return out


def resources(case):
    pid = "P-" + case["id"]
    ref = {"reference": f"Patient/{pid}"}
    first = case["events"][0]["date"]
    p = case.get("patient") or {}
    born = datetime.fromisoformat(first) - timedelta(days=int(p.get("age") or 60) * 365.25 + 100)
    out = [{"resourceType": "Patient", "id": pid, "gender": p.get("sex") or "unknown", "birthDate": born.date().isoformat()}]
    sm = SMOKING.get(p.get("smoking"))
    if sm:
        out.append({"resourceType": "Observation", "id": f"{pid}-smk", "status": "final", "subject": ref,
                    "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2"}]},
                    "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": sm[0]}], "text": sm[1]},
                    "effectiveDateTime": (datetime.fromisoformat(first) - timedelta(days=30)).date().isoformat()})
    if p.get("known_malignancy"):
        out.append({"resourceType": "Condition", "id": f"{pid}-ca", "subject": ref,
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "C50.9"}], "text": "Malignant neoplasm"},
                    "recordedDate": (datetime.fromisoformat(first) - timedelta(days=400)).date().isoformat()})
    last_referral = None
    first_report = None
    for i, e in enumerate(case["events"]):
        eid, when = f"{pid}-e{i}", e["date"][:10] + "T10:00:00Z"
        t = e["type"]
        if t == "report":
            first_report = first_report or eid
            out.append({"resourceType": "DiagnosticReport", "id": eid, "status": "final",
                        "category": [{"coding": [{"code": e.get("category") or "RAD"}]}], "code": {"text": e.get("title") or ""},
                        "subject": ref, "effectiveDateTime": when, "conclusion": e.get("text") or ""})
        elif t == "imaging_done":
            out.append({"resourceType": "ImagingStudy", "id": eid, "status": "available", "subject": ref, "started": when,
                        "modality": [{"system": "http://dicom.nema.org/resources/ontology/DCM", "code": e.get("modality")}],
                        "description": e.get("description") or "",
                        "series": [{"uid": f"1.2.{i}", "modality": {"code": e.get("modality")},
                                    "bodySite": {"display": e.get("body_part") or ""}}]})
        elif t == "referral":
            last_referral = eid
            out.append({"resourceType": "ServiceRequest", "id": eid, "status": "active", "intent": "order", "subject": ref,
                        "category": [{"text": "Referral"}], "code": {"text": e.get("description") or "Referral"},
                        "authoredOn": when})
        elif t == "specialist_visit":
            appt = {"resourceType": "Appointment", "id": eid, "status": "fulfilled", "start": when,
                    "participant": [{"actor": ref, "status": "accepted"}],
                    "serviceType": [{"text": e.get("description") or ""}], "description": e.get("description") or ""}
            if last_referral:
                appt["basedOn"] = [{"reference": f"ServiceRequest/{last_referral}"}]
            out.append(appt)
        elif t == "biopsy_done":
            out.append({"resourceType": "Procedure", "id": eid, "status": "completed", "subject": ref,
                        "code": {"text": e.get("description") or "Biopsy"}, "performedDateTime": when})
    return pid, first_report, out


def run_case(case):
    pid, first_report, res = resources(case)
    events, _ = bundle_to_events(res)
    when = datetime.fromisoformat(case["evaluation_date"][:10]) + timedelta(hours=23, minutes=59)
    dets = ClinLoopDetector(evaluation_time=when).process_patient("eval", pid, events.get(pid, []))
    got = {}
    for d in dets:
        if d.rule_id not in REPORT_RULES or (f"/{first_report}:" not in str(d.trigger_event_id)):
            continue
        if d.loop_status == "closed":
            status = "done"
        elif d.loop_status == "delayed":
            status = "done_late"
        else:
            status = "pending" if datetime.fromisoformat(d.deadline) > when else "missed"
        got[d.rule_id] = status
    return got


def main():
    path = sys.argv[1]
    show = "--show" in sys.argv
    cases = json.load(open(path, encoding="utf-8"))
    pairs = Counter()
    agree = total = 0
    false_closure, false_alarm, wrong_rules, exact = [], [], [], 0
    eq_agree = eq_total = 0
    for c in cases:
        exp = {k: v for k, v in (c.get("expected") or {}).items() if k in REPORT_RULES}
        try:
            got = run_case(c)
        except Exception as e:                       # a crash is a failure
            got = {"CRASH": type(e).__name__}
        exact += int(exp == got)
        ge, gg = by_group(exp), by_group(got)
        for g in set(ge) | set(gg):
            eq_total += 1
            eq_agree += int(ge.get(g) == gg.get(g))
        for r in set(exp) | set(got):
            e, g = exp.get(r, "absent"), got.get(r, "absent")
            pairs[(e, g)] += 1
            total += 1
            agree += int(e == g)
            if e in ("missed", "pending") and g in DONE:
                false_closure.append((c["id"], r, e, g))
            if e in DONE and g in ("missed", "pending"):
                false_alarm.append((c["id"], r, e, g))
            if "absent" in (e, g):
                wrong_rules.append((c["id"], r, e, g))
        if show and exp != got:
            print(f"\n{c['id']} expected {exp} got {got}\n   {c.get('rationale', '')[:220]}")
    print(f"\ntimelines={len(cases)}  exact={exact}/{len(cases)} = {exact / max(1, len(cases)):.1%}")
    print(f"obligation status agreement (strict rule ids): {agree}/{total} = {agree / max(1, total):.1%}")
    print(f"finding status agreement (one alert per finding): {eq_agree}/{eq_total} = {eq_agree / max(1, eq_total):.1%}")
    print(f"FALSE CLOSURES (not done, app says done): {len(false_closure)} {false_closure}")
    print(f"false alarms (done, app says not done): {len(false_alarm)} {false_alarm}")
    print(f"rule present/absent disagreements: {len(wrong_rules)}")
    print("expected → got:", dict(sorted(pairs.items())))


if __name__ == "__main__":
    main()
