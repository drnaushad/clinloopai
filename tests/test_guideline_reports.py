"""
test_guideline_reports.py — R060–R065: HIV, hepatitis B and TB tests, colonoscopy surveillance, echocardiograms

Each rule follows a published guideline (see clinical_ontology.py). The blind sets in tests/blind_reports_2
and tests/blind_reports_3 were written by independent authors from the guideline definitions alone; the
first is enforced here after its defects were fixed, so they cannot return.
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "blind_reports_2"))

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.guideline_reports import (colonoscopy_interval, echo_findings,  # noqa: E402
                                                   classify_lab)
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402

P = {"resourceType": "Patient", "id": "P", "gender": "female", "birthDate": "1960-01-01"}
SUBJ = {"reference": "Patient/P"}


def obs(rid, text, value=None, when="2026-03-01", loinc=None, qty=None):
    r = {"resourceType": "Observation", "id": rid, "status": "final", "subject": SUBJ, "effectiveDateTime": when,
         "category": [{"coding": [{"code": "laboratory"}]}],
         "code": {"text": text, **({"coding": [{"system": "http://loinc.org", "code": loinc}]} if loinc else {})}}
    if value is not None:
        r["valueString"] = value
    if qty is not None:
        r["valueQuantity"] = {"value": qty, "unit": "mm"}
    return r


def report(rid, code, text, when="2026-03-01", category=None):
    r = {"resourceType": "DiagnosticReport", "id": rid, "status": "final", "subject": SUBJ, "effectiveDateTime": when,
         "code": {"text": code}, "conclusion": text}
    if category:
        r["category"] = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": category}]}]
    return r


def procedure(rid, text, when):
    return {"resourceType": "Procedure", "id": rid, "status": "completed", "subject": SUBJ,
            "code": {"text": text}, "performedDateTime": when}


def referral(rid, text, when):
    return {"resourceType": "ServiceRequest", "id": rid, "status": "active", "intent": "order", "subject": SUBJ,
            "code": {"text": text}, "authoredOn": when}


def condition(rid, text, when="2020-01-01"):
    return {"resourceType": "Condition", "id": rid, "subject": SUBJ, "code": {"text": text},
            "clinicalStatus": {"coding": [{"code": "active"}]}, "onsetDateTime": when}


OPEN = ("open", "needs_human_review")   # a one-result record is sparse: still on the worklist, for review


def loops(resources, when="2026-03-08T00:00:00"):
    events, _ = bundle_to_events([P] + resources)
    found = ClinLoopDetector(evaluation_time=when).process_patient("t", "P", events.get("P", []))
    return {d.rule_id: d for d in found if d.rule_id in ("R060", "R061", "R062", "R063", "R064", "R065")}


class TestLabs(unittest.TestCase):

    def test_hiv_screen(self):
        self.assertIn(loops([obs("h", "HIV Ag/Ab Combo", "Reactive", loinc="75622-1")])["R060"].loop_status, OPEN)
        self.assertNotIn("R060", loops([obs("h", "HIV Ag/Ab Combo", "Non-reactive")]))
        self.assertNotIn("R060", loops([obs("h", "HIV Ag/Ab Combo", "Indeterminate")]))
        # Supplemental test closes it; a dermatology referral does not
        closed = loops([obs("h", "HIV Ag/Ab Combo", "Reactive"),
                        obs("r", "HIV-1 RNA quantitative", "48,000 copies/mL", when="2026-03-04")])
        self.assertEqual(closed["R060"].loop_status, "closed")
        self.assertIn(loops([obs("h", "HIV Ag/Ab Combo", "Reactive"),
                             referral("d", "Referral to dermatology", "2026-03-03")])["R060"].loop_status, OPEN)
        self.assertIn(loops([obs("h", "HIV Ag/Ab Combo", "Reactive"),
                                referral("i", "Referral to infectious disease clinic", "2026-03-03")])["R060"].loop_status,
                         "closed")

    def test_known_hiv_but_not_exposure(self):
        self.assertNotIn("R060", loops([condition("c", "HIV infection"), obs("h", "HIV Ag/Ab Combo", "Reactive")]))
        self.assertIn("R060", loops([condition("c", "Exposure to HIV (needlestick)"),
                                     obs("h", "HIV Ag/Ab Combo", "Reactive")]))

    def test_hbsag_not_antibody(self):
        self.assertIn("R061", loops([obs("b", "HBsAg", "Positive", loinc="5196-1")]))
        self.assertIn("R061", loops([obs("b", "B형간염 표면항원", "양성")]))
        self.assertNotIn("R061", loops([obs("b", "Anti-HBs (hepatitis B surface antibody)", "Positive")]))
        self.assertNotIn("R061", loops([condition("c", "Chronic hepatitis B"), obs("b", "HBsAg", "Positive")]))

    def test_tb_tests_and_chest_imaging(self):
        self.assertIn("R062", loops([obs("q", "QuantiFERON-TB Gold Plus", "Positive")]))
        self.assertNotIn("R062", loops([obs("q", "QuantiFERON-TB Gold Plus", "Indeterminate")]))
        self.assertIn("R062", loops([obs("t", "Tuberculin skin test induration", qty=12)]))
        self.assertNotIn("R062", loops([obs("t", "Tuberculin skin test induration", qty=8)]))
        self.assertIsNone(classify_lab([], "quantiferon tb1 antigen minus nil", "", None, 0.62, "IU/mL", [])["condition"])
        pos = obs("q", "QuantiFERON-TB Gold Plus", "Positive")
        self.assertEqual(loops([pos, procedure("x", "Chest X-ray PA and lateral", "2026-03-05")])["R062"].loop_status,
                         "closed")
        self.assertIn(loops([pos, procedure("x", "Abdominal X-ray", "2026-03-05")])["R062"].loop_status, OPEN)


class TestColonoscopy(unittest.TestCase):

    def test_intervals(self):
        self.assertEqual(colonoscopy_interval("BBPS 5 (1/2/2). Two 4 mm polyps removed.")["days"], 365)
        self.assertEqual(colonoscopy_interval("A 25 mm LST removed by piecemeal EMR.")["days"], 183)
        self.assertEqual(colonoscopy_interval("Tubular adenoma, 12 mm.")["days"], 1096)
        self.assertEqual(colonoscopy_interval("Tubulovillous adenoma, 8 mm.")["days"], 1096)
        self.assertIsNone(colonoscopy_interval("Three tubular adenomas, 3-6 mm. No high-grade dysplasia.")["days"])
        self.assertIsNone(colonoscopy_interval("Four tubular adenomas, all < 10 mm, low-grade.")["days"])
        self.assertTrue(colonoscopy_interval("Invasive adenocarcinoma arising in a tubular adenoma.")["cancer"])
        # Distances and instruments are not polyp sizes
        self.assertIsNone(colonoscopy_interval("A 5 mm polyp at 30 cm from the anal verge, removed with a 10 mm snare.")["days"])

    def test_counts_and_serrated(self):
        for text in ("A-E. Colon polyps (x5, 3-6 mm): Tubular adenomas (5 of 5).",
                     "Polyps x7: Tubular adenomas (x5) and hyperplastic polyps (x2).",
                     "대장 용종 6개: 모두 관상선종, 저등급 이형성."):
            self.assertEqual(colonoscopy_interval(text)["days"], 1096, text)
        self.assertEqual(colonoscopy_interval("Sessile serrated lesion WITH low-grade dysplasia, 7 mm.")["days"], 1096)
        self.assertIsNone(colonoscopy_interval("Sessile serrated lesion without dysplasia, 6 mm.")["days"])

    def test_one_obligation_per_colonoscopy_and_cancer_wins(self):
        scope = report("c", "Colonoscopy report", "BBPS 8. A 15 mm sessile polyp removed.", when="2026-03-01")
        path = report("p", "Surgical pathology report", "FINAL DIAGNOSIS: Tubular adenoma with high-grade dysplasia.",
                      when="2026-03-04", category="PAT")
        found = loops([scope, procedure("i", "Colonoscopy", "2026-03-01"), path], when="2026-03-20T00:00:00")
        self.assertIn(found["R063"].loop_status, OPEN)
        cancer = report("p", "Surgical pathology report", "FINAL DIAGNOSIS: Invasive adenocarcinoma.", when="2026-03-04",
                        category="PAT")
        self.assertNotIn("R063", loops([scope, procedure("i", "Colonoscopy", "2026-03-01"), cancer]))
        # The index colonoscopy does not close its own surveillance; a later one does
        later = procedure("s", "Colonoscopy", "2028-12-01")
        self.assertIn(loops([scope, procedure("i", "Colonoscopy", "2026-03-01"), path, later],
                               when="2029-01-01T00:00:00")["R063"].loop_status, "closed")


class TestEcho(unittest.TestCase):

    def test_severe_aortic_stenosis(self):
        self.assertTrue(echo_findings("Severe calcific aortic stenosis.")["severe_as"])
        self.assertTrue(echo_findings("AV Vmax: 4.3 m/s | Mean PG: 46 mmHg | AVA (VTI): 0.78 cm2")["severe_as"])
        self.assertFalse(echo_findings("Moderate aortic stenosis. AVA 1.0 cm2. AV mean gradient 28 mmHg.")["severe_as"])
        self.assertFalse(echo_findings("No aortic stenosis. MV mean gradient 9 mmHg.")["severe_as"])
        self.assertFalse(echo_findings("s/p TAVR, well-seated valve, mean gradient 9 mmHg.")["severe_as"])
        self.assertTrue(echo_findings("중증 대동맥판 협착증")["severe_as"])

    def test_ejection_fraction(self):
        self.assertTrue(echo_findings("LVEF 35-40% by biplane Simpson.")["reduced_ef"])
        self.assertFalse(echo_findings("LVEF 40-45%.")["reduced_ef"])
        self.assertTrue(echo_findings("Severely reduced LV systolic function.")["reduced_ef"])
        self.assertFalse(echo_findings("Previous EF 30%; now LVEF 55%.")["reduced_ef"])
        self.assertTrue(echo_findings("좌심실 구혈률 35%")["reduced_ef"])

    def test_echo_loops(self):
        echo = report("e", "Transthoracic echocardiogram", "Severe aortic stenosis. LVEF 30%.", category="CUS")
        found = loops([echo])
        self.assertTrue({found["R064"].loop_status, found["R065"].loop_status} <= set(OPEN))
        done = loops([echo, referral("r", "Referral to cardiology", "2026-03-03")])
        self.assertEqual((done["R064"].loop_status, done["R065"].loop_status), ("closed", "closed"))
        self.assertIn(loops([echo, referral("u", "Referral to urology", "2026-03-03")])["R064"].loop_status, OPEN)
        self.assertNotIn("R065", loops([condition("hf", "Heart failure with reduced ejection fraction"), echo]))


class TestBlindSet(unittest.TestCase):

    def test_first_blind_set_stays_correct(self):
        from score import score
        with open(os.path.join(ROOT, "tests", "blind_reports_2", "cases.json"), encoding="utf-8") as f:
            result = score(json.load(f), show_misses=True)
        self.assertEqual(result["misses"], [])


if __name__ == "__main__":
    unittest.main()
