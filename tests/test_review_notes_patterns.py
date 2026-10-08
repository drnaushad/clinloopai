"""
test_review_notes_patterns.py — The 12 defects an independent review confirmed in the note reader and the
diagnostic patterns (2026-10-08), each kept as a regression test. Synthetic data only.
"""

import base64
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from test_notes import P as NOTE_PATIENT, doc, lab, loops as note_loops, study  # noqa: E402
from test_patterns import condition, creat, med, patient, urbc, hb, ferritin, loops as pattern_loops  # noqa: E402

from src.clinloop_engine.document_reader import scrub_identifiers  # noqa: E402
from src.clinloop_engine.note_reader import analyte_of, find_plans, interval_days  # noqa: E402


def plans(text):
    return [(p["kind"], p["target"], p["interval_days"], p["tracked"]) for p in find_plans(text)["plans"]]


class TestIntervals(unittest.TestCase):
    """1. Letters inside words ('today', 'and', 'head') were read as intervals."""

    def test_words_are_not_intervals(self):
        self.assertEqual(plans("Plan: CT head in 3 months."), [("imaging", "ct", 91.3, True)])
        self.assertEqual(plans("Plan: Repeat potassium today and in 1 week."), [("lab", "potassium", 7.0, True)])
        self.assertEqual(interval_days("Repeat CT chest on Monday")[0], None)
        self.assertEqual(interval_days("BMP in AM")[0], 1.0)
        self.assertEqual(interval_days("Recheck K in 4 hrs")[0], 0.17)
        self.assertEqual(interval_days("labs q3mo")[0], 91.3)
        self.assertIsNone(interval_days("last CT 3 months ago")[0])
        self.assertEqual({p[2] for p in plans("Plan: Check A1c, lipid panel and TSH in 3 months.")}, {91.3})


class TestSections(unittest.TestCase):
    """2. A 'Follow-up:' line swallowed the note; history sections hid the plan after them."""

    def test_assessment_items_and_follow_up_line(self):
        got = plans("Assessment:\n1. Hypokalemia - repeat K in 3 days\n2. Nodule - CT chest in 3 months\nFollow-up: RTC 4 weeks")
        self.assertEqual(sorted(got), sorted([("lab", "potassium", 3.0, True), ("imaging", "ct", 91.3, True),
                                              ("visit", None, 28.0, True)]))

    def test_history_then_plan_line(self):
        self.assertEqual(plans("Subjective: K was 5.9 last week.\nRepeat potassium in 1 week."),
                         [("lab", "potassium", 7.0, True)])
        self.assertEqual(plans("Follow-up: last CT chest 3 months ago stable\nRepeat CT chest in 12 months"),
                         [("imaging", "ct", 365.3, True)])


class TestClauseCues(unittest.TestCase):
    """3. A cue anywhere in the sentence cancelled every plan in it. 4. 'Scheduled' is not 'done'."""

    def test_valid_plans_stay_tracked(self):
        for text in ("Plan: Recheck K in 3 days, sooner if symptomatic.", "Plan: RTC 2 weeks or sooner if needed.",
                     "Plan: Refer to GI for possible colonoscopy.",
                     "Plan: No further imaging needed for the kidney stone, repeat CBC in 2 weeks.",
                     "계획: 와파린 보류, 3일 후 INR 재검", "계획: 메트포르민 중단, 1주 후 신기능 재검",
                     "Plan: Repeat CBC in 2 weeks (Hb 9.1 last week).", "계획: 환자에게 설명했음, 2주 후 혈액검사 재검 예정",
                     "Plan: CT already scheduled for next week.", "Plan: CT chest ordered today."):
            got = find_plans(text)["plans"]
            self.assertTrue(got and all(p["tracked"] for p in got), (text, got))

    def test_real_negations_and_conditions_still_win(self):
        for text, reason in (("Plan: If fever recurs, repeat CBC.", "conditional"),
                             ("Plan: No need to repeat echo.", "negated"),
                             ("Plan: CT 취소.", "negated"),
                             ("Plan: HbA1c was rechecked last month.", "already done")):
            p = find_plans(text)["plans"][0]
            self.assertFalse(p["tracked"], text)
            self.assertIn(reason, p["reason"])


class TestScrubbing(unittest.TestCase):
    """5. Names were removed inside words; 'ID clinic' was removed; addresses and relatives were kept."""

    def test_clinical_words_survive_and_identifiers_go(self):
        t = ("Patient Li Wei. Address: 12 Main St, Seoul\nDaughter Mary Smith called. 보호자 홍길순 동반. DOB 3/2/56. "
             "Tel +82 10 1234 5678\nPlan: Repeat lipid panel in 3 months. Liver ultrasound. Follow-up in clinic. "
             "Refer to ID clinic. 홍 길동님 설명함.")
        out = scrub_identifiers(t, ["Li", "Wei", "Li Wei", "홍길동", "홍 길동"])
        for kept in ("lipid panel", "Liver ultrasound", "in clinic", "Refer to ID clinic"):
            self.assertIn(kept, out)
        for gone in ("Wei", "Main St", "Mary Smith", "홍길순", "3/2/56", "1234 5678", "홍 길동"):
            self.assertNotIn(gone, out)


class TestSpecimenAndMatching(unittest.TestCase):
    """6. Urine tests closed blood-test plans. 7. Wrong imaging closed plans. 11. Any visit closed a visit plan."""

    def test_specimens_are_kept_apart(self):
        self.assertEqual(analyte_of("Potassium [Moles/volume] in Urine"), "urine:potassium")
        self.assertEqual(analyte_of("Creatinine [Mass/volume] in Urine"), "urine:creatinine")
        self.assertIsNone(analyte_of("HIV 1 RNA viral load"))
        self.assertEqual(analyte_of("HCV RNA quantitative"), "hcv_rna")
        urine_k = lab("u1", "2829-0", "Potassium [Moles/volume] in Urine", "2026-06-05T08:00:00Z")
        self.assertEqual(note_loops([NOTE_PATIENT, doc("Plan: repeat potassium in 1 week."), urine_k])["R048"], "open")

    def test_imaging_matches(self):
        note = doc("Plan: CT A/P in 6 months.")
        head = study("c1", "CT", "HEAD", "2026-11-20T09:00:00Z", "CT head")
        self.assertIn(note_loops([NOTE_PATIENT, note, head])["R049"], ("open", "needs_human_review"))
        echo = doc("Plan: echo next month.")
        abd_us = study("u1", "US", "ABDOMEN", "2026-06-20T09:00:00Z", "US abdomen")
        tte = study("u2", "US", "CHEST", "2026-06-20T09:00:00Z", "Transthoracic echocardiogram")
        self.assertIn(note_loops([NOTE_PATIENT, echo, abd_us])["R049"], ("open", "needs_human_review"))
        self.assertEqual(note_loops([NOTE_PATIENT, echo, tte])["R049"], "closed")
        mammo_plan = doc("Plan: mammogram in 1 year.")
        mg = study("m1", "MG", "", "2027-05-20T09:00:00Z", "Screening mammography")
        self.assertEqual(note_loops([NOTE_PATIENT, mammo_plan, mg], datetime(2027, 6, 30))["R049"], "closed")

    def test_visit_long_before_the_interval_does_not_close(self):
        note = doc("Plan: RTC 6 months.")
        derm = {"resourceType": "Appointment", "id": "a1", "status": "fulfilled", "start": "2026-06-02T09:00:00Z",
                "participant": [{"actor": {"reference": "Patient/N"}}], "specialty": [{"text": "Dermatology"}]}
        later = {**derm, "id": "a2", "start": "2026-11-25T09:00:00Z", "specialty": []}
        self.assertIn(note_loops([NOTE_PATIENT, note, derm], datetime(2026, 7, 1))["R051"], ("open", "needs_human_review"))
        self.assertEqual(note_loops([NOTE_PATIENT, note, later], datetime(2026, 12, 30))["R051"], "closed")


class TestPatternFixes(unittest.TestCase):
    """8. AF judged only at diagnosis; cancelled/stopped orders. 9. Units. 10. Haematuria formats."""

    def test_af_risk_reached_later_and_order_status(self):
        base = [patient("male", "1955-01-01"), condition("af", "Atrial fibrillation", "I48.91", "2020-03-01")]
        self.assertNotIn("R054", pattern_loops(base, datetime(2026, 10, 8))[0])        # age 71 alone: score 1
        htn = condition("d1", "Hypertension", "I10", "2026-02-01")
        self.assertEqual(pattern_loops(base + [htn], datetime(2026, 10, 8))[0]["R054"], "open")
        cancelled = {**med("m0", "warfarin 5 mg", "2019-01-01"), "status": "cancelled"}
        self.assertEqual(pattern_loops(base + [htn, cancelled], datetime(2026, 10, 8))[0]["R054"], "open")
        stopped = {**med("m1", "apixaban 5 mg", "2026-02-10"), "status": "stopped"}
        self.assertEqual(pattern_loops(base + [htn, stopped], datetime(2026, 10, 8))[0]["R054"], "open")
        ruled_out = condition("af2", "Rule out atrial fibrillation", None, "2026-01-01")
        self.assertNotIn("R054", pattern_loops([patient("male", "1940-01-01"), ruled_out], datetime(2026, 10, 8))[0])
        pulm = condition("p1", "Pulmonary hypertension", None, "2026-01-01")
        self.assertNotIn("R054", pattern_loops(base + [pulm], datetime(2026, 10, 8))[0])

    def test_creatinine_units_are_normalised(self):
        umol = [patient(), {**creat("c1", "2026-04-01T08:00:00Z", 80), "valueQuantity": {"value": 80, "unit": "umol/L"}},
                {**creat("c2", "2026-04-03T08:00:00Z", 150), "valueQuantity": {"value": 150, "unit": "µmol/L"}}]
        self.assertEqual(pattern_loops(umol)[0]["R053"], "open")
        mixed = [patient(), creat("c1", "2026-04-01T08:00:00Z", 0.9),
                 {**creat("c2", "2026-04-03T08:00:00Z", 150), "valueQuantity": {"value": 150, "unit": "µmol/L"}}]
        self.assertEqual(pattern_loops(mixed)[0]["R053"], "open")

    def test_haematuria_text_ranges_and_per_ul_counts(self):
        def ranged(rid, when, text):
            r = urbc(rid, when)
            r.pop("valueQuantity"); r.pop("interpretation")
            r["valueString"] = text
            return r
        self.assertEqual(pattern_loops([patient(), ranged("u1", "2026-02-01T08:00:00Z", "10-20"),
                                        ranged("u2", "2026-03-15T08:00:00Z", "5-9")])[0]["R055"], "open")
        per_ul = [patient()] + [{**urbc(r, w, 10), "valueQuantity": {"value": 10, "unit": "/uL"}, "interpretation": []}
                                for r, w in (("u1", "2026-02-01T08:00:00Z"), ("u2", "2026-03-15T08:00:00Z"))]
        self.assertNotIn("R055", pattern_loops(per_ul)[0])

    def test_haemoglobin_mmol(self):
        r = {**hb("h1", "2026-05-02T08:00:00Z"), "valueQuantity": {"value": 8.5, "unit": "mmol/L"}, "interpretation": []}
        self.assertNotIn("R052", pattern_loops([patient(), r, ferritin("f1", "2026-05-03T08:00:00Z")])[0])


class TestSupersededNote(unittest.TestCase):

    def test_superseded_version_is_ignored(self):
        old = {**doc("Plan: repeat potassium in 1 week.", rid="v1"), "status": "superseded"}
        self.assertEqual(note_loops([NOTE_PATIENT, old]), {})


if __name__ == "__main__":
    unittest.main()
