"""
test_followup_matching.py — Follow-up must be the RIGHT follow-up: right specialty, right organ.

Defects found by a blind timeline evaluation (docs/ACCURACY_EVALUATION.md): a cardiology referral closed a
lung-nodule work-up, a nephrology referral closed a renal-mass referral, a liver biopsy closed a pancreatic
work-up. Also: Korean "BI-RADS 범주 4", "discussed by telephone with", "grown from 6 mm to 10 mm".
Reworded synthetic cases, not the evaluation cases.
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "report_eval"))

from run_timelines import run_case  # noqa: E402


def timeline(events, evaluation_date, smoking="former"):
    return {"id": "X", "patient": {"age": 64, "sex": "male", "smoking": smoking, "known_malignancy": False},
            "events": events, "evaluation_date": evaluation_date}


def report(date, title, text, category="RAD"):
    return {"type": "report", "date": date, "category": category, "title": title, "text": text}


class TestRightServiceAndOrgan(unittest.TestCase):

    def test_wrong_specialty_referral_does_not_close_a_lung_workup(self):
        base = [report("2026-02-02", "LDCT lung cancer screening",
                       "IMPRESSION: 18 mm solid nodule, right lower lobe. Lung-RADS 4B. PET/CT or tissue sampling advised.")]
        wrong = run_case(timeline(base + [{"type": "referral", "date": "2026-02-05",
                                           "description": "Referral to cardiology for coronary calcification"}], "2026-03-20"))
        self.assertEqual(wrong.get("R020"), "missed")
        right = run_case(timeline(base + [{"type": "referral", "date": "2026-02-05",
                                           "description": "Referral to thoracic surgery"}], "2026-03-20"))
        self.assertEqual(right.get("R020"), "done")
        generic = run_case(timeline(base + [{"type": "referral", "date": "2026-02-05", "description": "Referral"}],
                                    "2026-03-20"))
        self.assertEqual(generic.get("R020"), "done")      # a referral naming no service still counts

    def test_wrong_specialty_does_not_close_a_renal_mass_referral(self):
        base = [report("2026-02-02", "CT abdomen",
                       "IMPRESSION: 2.8 cm enhancing solid right renal mass, suspicious for renal cell carcinoma.")]
        self.assertEqual(run_case(timeline(base + [{"type": "referral", "date": "2026-02-06",
                                                    "description": "Nephrology referral for CKD"}], "2026-04-01"))
                         .get("R039"), "missed")
        self.assertEqual(run_case(timeline(base + [{"type": "referral", "date": "2026-02-06",
                                                    "description": "비뇨의학과 의뢰"}], "2026-04-01"))
                         .get("R039"), "done")

    def test_biopsy_of_another_organ_does_not_close_a_pancreatic_workup(self):
        base = [report("2026-02-02", "MRI pancreas",
                       "IMPRESSION: 2.9 cm pancreatic head cyst with an enhancing mural nodule. EUS recommended.")]
        liver = run_case(timeline(base + [{"type": "biopsy_done", "date": "2026-02-10",
                                           "description": "Percutaneous liver biopsy"}], "2026-04-01"))
        self.assertEqual(liver.get("R042"), "missed")

    def test_lung_biopsy_closes_a_growing_nodule_workup(self):
        base = [report("2026-02-02", "CT chest",
                       "IMPRESSION: Left lower lobe nodule has grown from 7 mm to 11 mm. Tissue sampling recommended.")]
        lung = run_case(timeline(base + [{"type": "biopsy_done", "date": "2026-02-20",
                                          "description": "CT-guided transthoracic biopsy, left lower lobe"}], "2026-04-01"))
        self.assertEqual(lung.get("R046"), "done")
        kidney = run_case(timeline(base + [{"type": "biopsy_done", "date": "2026-02-20",
                                            "description": "Renal biopsy"}], "2026-04-01"))
        self.assertEqual(kidney.get("R046"), "missed")


    def test_biopsy_of_another_organ_does_not_close_a_prostate_biopsy(self):
        base = [report("2026-02-02", "MRI prostate",
                       "IMPRESSION: 1.6 cm PI-RADS 5 lesion, left peripheral zone. Targeted prostate biopsy recommended.")]
        colon = run_case(timeline(base + [{"type": "biopsy_done", "date": "2026-02-10",
                                           "description": "Colonoscopic biopsy, sigmoid colon"}], "2026-04-15"))
        self.assertEqual(colon.get("R036"), "missed")


class TestReportWording(unittest.TestCase):

    def test_korean_birads_category(self):
        got = run_case(timeline([report("2026-02-02", "유방촬영술",
                                        "결론: 우측 유방 1.0 cm 불규칙 종괴, BI-RADS 범주 4. 조직검사 권고.")], "2026-02-10"))
        self.assertIn("R018", got)

    def test_communication_by_telephone_closes_the_critical_result(self):
        got = run_case(timeline([report("2026-02-02", "CT pulmonary angiography",
                                        "IMPRESSION: Acute right lower lobe pulmonary embolism. Discussed by telephone "
                                        "with Dr. Lee (emergency department) at 03:10.")], "2026-02-03"))
        self.assertEqual(got.get("R035"), "done")


class TestBlindTimelines(unittest.TestCase):
    """The blind timelines (docs/ACCURACY_EVALUATION.md) never show a follow-up as done when it was not."""

    def test_no_false_closures(self):
        path = os.path.join(ROOT, "tests", "report_eval", "timelines.json")
        with open(path, encoding="utf-8") as f:
            cases = json.load(f)
        closures = []
        for c in cases:
            got = run_case(c)
            for rule, expected in (c.get("expected") or {}).items():
                if expected in ("missed", "pending") and got.get(rule) in ("done", "done_late"):
                    closures.append((c["id"], rule))
        self.assertEqual(closures, [])


if __name__ == "__main__":
    unittest.main()
