"""
test_patterns.py — Diagnostic patterns across events (R052–R055). Synthetic patients only.
"""

import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.motifs import cha2ds2_vasc  # noqa: E402
from src.clinloop_engine.patient_graph import build_patient_graph  # noqa: E402


def patient(sex="male", born="1958-03-01"):
    return {"resourceType": "Patient", "id": "Q", "gender": sex, "birthDate": born}


def lab(rid, loinc, name, when, value, unit, flag=None):
    r = {"resourceType": "Observation", "id": rid, "status": "final", "subject": {"reference": "Patient/Q"},
         "category": [{"coding": [{"code": "laboratory"}]}],
         "code": {"coding": [{"system": "http://loinc.org", "code": loinc}], "text": name},
         "effectiveDateTime": when, "valueQuantity": {"value": value, "unit": unit}}
    if flag:
        r["interpretation"] = [{"coding": [{"code": flag}]}]
    return r


def hb(rid, when, v=9.8):
    return lab(rid, "718-7", "Hemoglobin [Mass/volume] in Blood", when, v, "g/dL", "L")


def ferritin(rid, when, v=8):
    return lab(rid, "2276-4", "Ferritin [Mass/volume] in Serum", when, v, "ng/mL", "L")


def creat(rid, when, v):
    return lab(rid, "2160-0", "Creatinine [Mass/volume] in Serum", when, v, "mg/dL")


def urbc(rid, when, v=12):
    return lab(rid, "13945-1", "RBC [#/area] in Urine sediment by Microscopy high power field", when, v, "/[HPF]", "H")


def condition(rid, text, code=None, when="2025-01-10"):
    c = {"resourceType": "Condition", "id": rid, "subject": {"reference": "Patient/Q"},
         "clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"text": text}, "recordedDate": when}
    if code:
        c["code"]["coding"] = [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code}]
    return c


def referral(rid, text, when):
    return {"resourceType": "ServiceRequest", "id": rid, "status": "active", "intent": "order",
            "subject": {"reference": "Patient/Q"}, "authoredOn": when, "code": {"text": text}}


def med(rid, name, when):
    return {"resourceType": "MedicationRequest", "id": rid, "status": "active", "intent": "order",
            "subject": {"reference": "Patient/Q"}, "authoredOn": when, "medicationCodeableConcept": {"text": name}}


def loops(resources, when=datetime(2026, 10, 8)):
    events, warnings = bundle_to_events(resources)
    assert warnings == [], warnings
    out = {}
    for d in ClinLoopDetector(evaluation_time=when).process_patient("t", "Q", events.get("Q", [])):
        out.setdefault(d.rule_id, []).append(d.loop_status)
    return {k: v[0] if len(v) == 1 else sorted(v) for k, v in out.items()}, events.get("Q", [])


class TestIronDeficiency(unittest.TestCase):

    def test_ida_in_older_man_opens_urgent_gi_work_up(self):
        statuses, events = loops([patient(), hb("h1", "2026-05-02T08:00:00Z"), ferritin("f1", "2026-05-03T08:00:00Z")])
        self.assertEqual(statuses["R052"], "open")
        p = next(e for e in events if e["event_type"] == "diagnostic_pattern")
        self.assertEqual(p["details"]["rule_deadline_days"]["R052"], 14.0)       # age 68: suspected-cancer pathway
        self.assertEqual(len(p["details"]["evidence_events"]), 2)

    def test_closed_by_colonoscopy_or_gi_referral_not_by_other_referral(self):
        base = [patient(), hb("h1", "2026-05-02T08:00:00Z"), ferritin("f1", "2026-05-03T08:00:00Z")]
        self.assertEqual(loops(base + [referral("s1", "Referral to gastroenterology", "2026-05-10")])[0]["R052"], "closed")
        self.assertEqual(loops(base + [referral("s2", "Referral to dermatology", "2026-05-10")])[0]["R052"], "open")
        colo = {"resourceType": "Procedure", "id": "p1", "status": "completed", "subject": {"reference": "Patient/Q"},
                "performedDateTime": "2026-05-12", "code": {"text": "Colonoscopy"}}
        self.assertEqual(loops(base + [colo])[0]["R052"], "closed")

    def test_not_for_premenopausal_women_or_values_far_apart_or_prior_work_up(self):
        self.assertNotIn("R052", loops([patient("female", "1990-01-01"), hb("h1", "2026-05-02T08:00:00Z", 10.5),
                                        ferritin("f1", "2026-05-03T08:00:00Z")])[0])
        self.assertNotIn("R052", loops([patient(), hb("h1", "2026-01-02T08:00:00Z"),
                                        ferritin("f1", "2026-06-03T08:00:00Z")])[0])
        prior = {"resourceType": "Procedure", "id": "p0", "status": "completed", "subject": {"reference": "Patient/Q"},
                 "performedDateTime": "2026-02-01", "code": {"text": "Colonoscopy"}}
        self.assertNotIn("R052", loops([patient(), prior, hb("h1", "2026-05-02T08:00:00Z"),
                                        ferritin("f1", "2026-05-03T08:00:00Z")])[0])

    def test_normal_ferritin_is_not_iron_deficiency(self):
        self.assertNotIn("R052", loops([patient(), hb("h1", "2026-05-02T08:00:00Z"),
                                        lab("f1", "2276-4", "Ferritin", "2026-05-03T08:00:00Z", 180, "ng/mL")])[0])


class TestCreatinineRise(unittest.TestCase):

    def test_rise_against_recent_baseline(self):
        statuses, events = loops([patient(), creat("c1", "2026-04-01T08:00:00Z", 0.9),
                                  creat("c2", "2026-04-04T08:00:00Z", 1.6)])
        self.assertEqual(statuses["R053"], "open")
        p = next(e for e in events if e["event_type"] == "diagnostic_pattern")
        self.assertEqual(p["details"]["aki_stage"], 1)

    def test_repeat_creatinine_closes_it(self):
        self.assertEqual(loops([patient(), creat("c1", "2026-04-01T08:00:00Z", 0.9), creat("c2", "2026-04-04T08:00:00Z", 1.6),
                                creat("c3", "2026-04-05T08:00:00Z", 1.4)])[0]["R053"], "closed")

    def test_small_rise_or_no_baseline_is_ignored(self):
        self.assertNotIn("R053", loops([patient(), creat("c1", "2026-04-01T08:00:00Z", 0.5),
                                        creat("c2", "2026-04-03T08:00:00Z", 0.75)])[0])       # +0.25 mg/dL only
        self.assertNotIn("R053", loops([patient(), creat("c2", "2026-04-04T08:00:00Z", 3.0)])[0])

    def test_median_baseline_from_older_results(self):
        rs = [patient(), creat("a", "2025-12-01T08:00:00Z", 1.0), creat("b", "2026-01-15T08:00:00Z", 1.1),
              creat("c", "2026-02-20T08:00:00Z", 1.0), creat("d", "2026-04-04T08:00:00Z", 2.3)]
        _, events = loops(rs)
        p = next(e for e in events if e["event_type"] == "diagnostic_pattern")
        self.assertIn("median of the previous 8–365 days", p["details"]["evidence_span"])
        self.assertEqual(p["details"]["aki_stage"], 2)


class TestAtrialFibrillation(unittest.TestCase):

    def test_score_from_problem_list_age_and_sex(self):
        _, events = loops([patient("female", "1950-01-01"), condition("d1", "Essential hypertension", "I10"),
                           condition("d2", "Type 2 diabetes mellitus", "E11.9")])
        s = cha2ds2_vasc(events, {"birth_date": datetime(1950, 1, 1), "sex": "female"}, datetime(2026, 5, 1))
        self.assertEqual(s["score"], 5)              # HTN 1 + DM 1 + age ≥ 75 2 + female 1

    def test_af_with_high_score_and_no_anticoagulant(self):
        base = [patient("male", "1955-01-01"), condition("d1", "Hypertension", "I10"),
                condition("af", "Atrial fibrillation", "I48.91", "2026-05-01")]
        self.assertEqual(loops(base)[0]["R054"], "open")                              # age 71 + HTN = 2
        self.assertEqual(loops(base + [med("m1", "apixaban 5 mg", "2026-05-08")])[0]["R054"], "closed")
        self.assertNotIn("R054", loops(base[:1] + base[2:])[0])                        # score 1: no rule
        self.assertNotIn("R054", loops([med("m0", "warfarin 5 mg", "2026-04-01")] + base)[0])   # already on OAC


class TestHaematuria(unittest.TestCase):

    def test_two_positive_tests_open_urology_work_up(self):
        base = [patient(), urbc("u1", "2026-02-01T08:00:00Z"), urbc("u2", "2026-03-15T08:00:00Z")]
        self.assertEqual(loops(base)[0]["R055"], "open")
        self.assertEqual(loops(base + [referral("s1", "Urology referral", "2026-03-20")])[0]["R055"], "closed")
        self.assertNotIn("R055", loops(base[:2])[0])                                    # one test is not enough
        self.assertNotIn("R055", loops([patient(born="2000-01-01")] + base[1:])[0])     # age < 35

    def test_ct_must_cover_the_urinary_tract(self):
        base = [patient(), urbc("u1", "2026-02-01T08:00:00Z"), urbc("u2", "2026-03-15T08:00:00Z")]
        head = {"resourceType": "ImagingStudy", "id": "i1", "status": "available", "subject": {"reference": "Patient/Q"},
                "started": "2026-04-01T09:00:00Z", "modality": [{"code": "CT"}],
                "series": [{"modality": {"code": "CT"}, "bodySite": {"display": "HEAD"}}]}
        abd = {**head, "id": "i2", "series": [{"modality": {"code": "CT"}, "bodySite": {"display": "ABDOMEN"}}]}
        self.assertEqual(loops(base + [head])[0]["R055"], "open")
        self.assertEqual(loops(base + [abd])[0]["R055"], "closed")


class TestPatternGraph(unittest.TestCase):

    def test_pattern_node_links_to_its_evidence(self):
        events, _ = bundle_to_events([patient(), hb("h1", "2026-05-02T08:00:00Z"), ferritin("f1", "2026-05-03T08:00:00Z")])
        g = build_patient_graph("Q", events["Q"], datetime(2026, 10, 8))
        pat = next(n for n in g["nodes"] if n["lane"] == "patterns")
        self.assertIn("iron-deficiency", pat["label"])
        sources = {e["source"] for e in g["edges"] if e["target"] == pat["id"] and e["kind"] == "derived_from"}
        self.assertEqual(sources, {"Observation/h1:lab_result", "Observation/f1:lab_result"})


if __name__ == "__main__":
    unittest.main()
