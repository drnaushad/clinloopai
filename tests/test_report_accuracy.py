"""
test_report_accuracy.py — Report-reading defects found by a blind accuracy evaluation, each kept fixed.

Every case here is a defect a blind case writer's report exposed (missed critical finding, Korean wording,
category in the next sentence, a differential read as a diagnosis …). The texts are re-worded, synthetic
examples of the same defect, not the evaluation cases themselves. Synthetic.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.radiology import _critical_findings  # noqa: E402

REPORT_RULES = {"R003", "R009", "R018", "R019", "R020", "R030", "R031", "R032", "R033", "R034", "R035", "R036",
                "R037", "R038", "R039", "R040", "R041", "R042", "R043", "R044", "R045", "R046"}


def rules(text, title="CT abdomen and pelvis with contrast", category="RAD", sex="male", smoking=None):
    """Rule ids one report opens, through the real pipeline."""
    when = datetime(2026, 9, 1)
    res = [{"resourceType": "Patient", "id": "A", "gender": sex, "birthDate": "1960-03-01"},
           {"resourceType": "DiagnosticReport", "id": "r", "status": "final", "category": [{"coding": [{"code": category}]}],
            "code": {"text": title}, "subject": {"reference": "Patient/A"},
            "effectiveDateTime": when.date().isoformat() + "T09:00:00Z", "conclusion": text}]
    if smoking:
        res.append({"resourceType": "Observation", "id": "s", "status": "final", "subject": {"reference": "Patient/A"},
                    "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2"}]},
                    "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": smoking}]},
                    "effectiveDateTime": "2026-08-01"})
    events, _ = bundle_to_events(res)
    dets = ClinLoopDetector(evaluation_time=when + timedelta(days=1)).process_patient("t", "A", events.get("A", []))
    return {d.rule_id for d in dets} & REPORT_RULES


def critical(text):
    return [c["id"] for c in _critical_findings(text)]


class TestCriticalFindings(unittest.TestCase):

    def test_ruptured_aaa_abbreviation_is_critical_and_still_gets_vascular_rule(self):
        self.assertEqual(rules("Ruptured 6.8 cm infrarenal AAA with retroperitoneal blood. Called to ED."),
                         {"R035", "R045"})

    def test_aaa_without_rupture_is_not_critical(self):
        self.assertEqual(critical("4.2 cm infrarenal AAA without rupture."), [])
        self.assertEqual(critical("AAA 5.8 cm, no evidence of leak."), [])

    def test_large_vessel_occlusion_wordings(self):
        for t in ("Acute occlusion of the right M1 segment.", "Acute left MCA occlusion.",
                  "Right M2 branch occlusion with perfusion mismatch.", "우측 중대뇌동맥 M2 분절 급성 폐색."):
            self.assertEqual(critical(t), ["acute_stroke"], t)

    def test_korean_haemorrhage_wordings_and_old_findings(self):
        self.assertEqual(critical("우측 시상 부위 급성 뇌내출혈, 뇌실내 출혈 동반."), ["intracranial_haemorrhage"])
        self.assertEqual(critical("이전 뇌실내 출혈은 흡수됨."), [])
        self.assertEqual(critical("기존 좌측 기흉 호전."), [])
        self.assertEqual(critical("새로 발생한 우측 기흉."), ["pneumothorax"])

    def test_non_vascular_or_chronic_occlusion_is_not_a_stroke(self):
        for t in ("Acute cholecystitis with cystic duct occlusion.", "Chronic right ICA occlusion, unchanged.",
                  "No acute large vessel occlusion."):
            self.assertEqual(critical(t), [], t)


class TestKidney(unittest.TestCase):

    def test_korean_kidney_words(self):
        self.assertEqual(rules("좌신 상극에 5.0 cm 크기의 조영증강되는 고형 종괴, 신세포암 의심."), {"R039"})
        self.assertEqual(rules("우측 신호강도 증가된 3 cm 병변.", title="MRI brain"), set())

    def test_rcc_to_be_excluded_is_indeterminate_not_suspicious(self):
        got = rules("우신 하극에 1.3 cm 고에코 결절. 혈관근지방종 가능성 높으나 신세포암 배제 위해 조영증강 CT 권고.")
        self.assertNotIn("R039", got)
        self.assertTrue(got & {"R030", "R040"})

    def test_bosniak_class_in_the_next_sentence(self):
        self.assertEqual(rules("3.1 cm right renal cystic mass with thick enhancing septa. Bosniak III. Urology referral."),
                         {"R039"})
        self.assertEqual(rules("좌신 2.0 cm 낭종, 얇은 격막 다수. Bosniak IIF. 추적 검사 권고."), {"R040"})

    def test_a_differential_is_not_a_diagnosis(self):
        self.assertEqual(rules("1.4 cm left renal lesion of 50 HU on a single venous phase, indeterminate "
                               "(hyperdense cyst versus solid mass)."), {"R040"})


class TestAdrenalPancreasThyroid(unittest.TestCase):

    def test_adrenal_washout_is_an_adenoma(self):
        self.assertEqual(rules("1.9 cm right adrenal nodule, 22 HU unenhanced, absolute washout 68%."), set())
        self.assertEqual(rules("1.9 cm right adrenal nodule, 22 HU unenhanced, relative washout 45%."), set())
        self.assertEqual(rules("1.9 cm right adrenal nodule, 22 HU unenhanced, absolute washout 41%."), {"R037"})

    def test_korean_pancreatic_cyst_with_a_negated_clause(self):
        # "벽결절 없음" negates the mural nodule, not the cyst
        got = rules("췌장 체부에 2.8 cm 낭성 병변, 벽결절 없음. 6개월 후 MRCP 추적 권고.")
        self.assertTrue(got & {"R031", "R041"})
        self.assertNotIn("R042", got)

    def test_korean_enhancing_solid_component_is_worrisome(self):
        self.assertEqual(rules("췌장 두부에 2.0 cm 낭종, 조영증강되는 고형 성분 동반."), {"R042"})

    def test_long_stable_small_pancreatic_cyst_stops_surveillance(self):
        self.assertEqual(rules("Stable 0.9 cm pancreatic body cyst, unchanged for 6 years."), set())

    def test_thyroid_without_suspicious_features(self):
        self.assertEqual(rules("Incidental 1.1 cm left thyroid nodule without suspicious features.",
                               title="CT chest with contrast"), set())

    def test_benign_cytology_ends_tirads_followup(self):
        self.assertEqual(rules("2.0 cm right thyroid nodule, TR3, benign on prior FNA (Bethesda II). Stable.",
                               title="US thyroid"), set())


class TestLungAndRecommendations(unittest.TestCase):

    def test_persistent_part_solid_korean(self):
        self.assertEqual(rules("우하엽 부분고형 결절 15 mm, 고형 성분 7 mm, 이전 CT와 비교하여 지속됨.",
                               title="CT chest", smoking="77176002"), {"R046"})

    def test_new_solid_component_is_growth(self):
        self.assertEqual(rules("RLL nodule, formerly pure ground-glass (8 mm), now part-solid with a new 6 mm solid component.",
                               title="CT chest", smoking="8517006"), {"R046"})

    def test_shorthand_report(self):
        self.assertTrue(rules("LUL nod 8mm, solid. f/u CT 3 mo.", title="CT chest", smoking="8517006") & {"R003", "R030"})

    def test_two_years_of_stability_is_benign(self):
        self.assertEqual(rules("The 6 mm LLL solid nodule is unchanged since CT of 02/2024 (more than 2 years of "
                               "stability), consistent with a benign etiology.", title="CT chest", smoking="8517006"), set())

    def test_prior_lung_rads_is_not_the_current_category(self):
        self.assertEqual(rules("Prior Lung-RADS 3 nodule in the RUL, 6 mm, unchanged. Lung-RADS 2. Annual screening.",
                               title="LDCT lung cancer screening", smoking="77176002"), set())

    def test_mr_angiography_and_korean_region_words(self):
        self.assertEqual(rules("3 mm unruptured aneurysm of the right ICA. Recommend follow-up MR angiography in 12 months.",
                               title="MRA brain"), {"R031"})
        self.assertEqual(rules("우측 소량 흉수. 추적 흉부 X선 권고.", title="Chest X-ray"), {"R033"})
        self.assertEqual(rules("간 S7 1.0 cm 결절. 3개월 후 dynamic liver MRI 권고.", title="US abdomen"), {"R031"})

    def test_a_recommendation_for_one_organ_does_not_cover_another(self):
        # The MRI is for the pancreatic cyst; the aneurysm still needs its own surveillance
        got = rules("1. 2.6 cm side-branch IPMN in the pancreatic tail, no worrisome features.\n"
                    "2. Incidental infrarenal AAA 3.6 cm.\nRecommend MRI/MRCP in 6 months (or EUS-FNA) for the cyst.",
                    title="MRI abdomen with MRCP")
        self.assertIn("R031", got)
        self.assertIn("R044", got)
        self.assertNotIn("R036", got)      # EUS-FNA is offered as an alternative to the MRI

    def test_korean_request_wording(self):
        self.assertEqual(rules("우하엽 폐렴. 치료 후 8주 뒤 흉부 X선 f/u으로 호전 확인 바람.", title="Chest X-ray"), {"R033"})

    def test_targeted_biopsy_is_not_an_mri(self):
        self.assertNotIn("R031", rules("1.5 cm PI-RADS 5 lesion, right peripheral zone. Recommend MRI-targeted biopsy.",
                                       title="MRI prostate"))


class TestPathology(unittest.TestCase):

    def test_high_grade_cytology_and_high_risk_breast_lesions(self):
        for t in ("Cervical cytology: high-grade squamous intraepithelial lesion (HSIL).",
                  "Breast, left, core biopsy: atypical ductal hyperplasia. Excision recommended.",
                  "Cervix, biopsy: CIN 3."):
            self.assertEqual(rules(t, title="Pathology", category="PAT", sex="female"), {"R009"}, t)
        self.assertEqual(rules("Breast, core biopsy: fibroadenoma. Benign.", title="Pathology", category="PAT",
                               sex="female"), set())


class TestBlindCaseSets(unittest.TestCase):
    """The 270 blind-written cases (docs/ACCURACY_EVALUATION.md) stay above a floor: a change that loses
    findings or adds false alerts fails CI."""

    def test_accuracy_floor(self):
        import json
        sys.path.insert(0, os.path.join(ROOT, "tests", "report_eval"))
        from run_eval import REPORT_RULES as EVAL_RULES, equivalent, run_case
        with open(os.path.join(ROOT, "tests", "report_eval", "cases.json"), encoding="utf-8") as f:
            cases = json.load(f)
        equiv = negatives = clean = 0
        for c in cases:
            exp = set(c["expected_rules"]) & EVAL_RULES
            got, _ = run_case(c)
            equiv += equivalent(exp, got)
            if not exp:
                negatives += 1
                clean += not got
        self.assertGreaterEqual(equiv / len(cases), 0.97)
        self.assertGreaterEqual(clean / negatives, 0.97)


if __name__ == "__main__":
    unittest.main()
