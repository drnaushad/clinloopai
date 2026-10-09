"""
test_radiology.py — Body-region matching, Fleischner 2017, ACR incidental findings,
and the hospital critical-finding list.

Each case is a synthetic report written the way radiologists write them.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events
from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.radiology import expand_regions, load_critical_findings, regions_in

T0 = "2026-01-10T09:00:00Z"


def rad(rid, when, title, text):
    return {"resourceType": "DiagnosticReport", "id": rid, "status": "final",
            "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": title},
            "subject": {"reference": "Patient/P"}, "effectiveDateTime": when, "conclusion": text}


def patient(birth="1960-01-01", sex="male"):
    return {"resourceType": "Patient", "id": "P", "birthDate": birth, "gender": sex}


def smoking(snomed):
    return {"resourceType": "Observation", "id": "smk", "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2"}]},
            "subject": {"reference": "Patient/P"}, "effectiveDateTime": "2025-01-01T00:00:00Z",
            "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": snomed}]}}


def condition(icd, text):
    return {"resourceType": "Condition", "id": f"c-{icd}", "subject": {"reference": "Patient/P"},
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": icd}], "text": text},
            "recordedDate": "2020-01-01"}


def referral(when, text="Urology referral"):
    return {"resourceType": "ServiceRequest", "id": "ref", "status": "completed", "authoredOn": when,
            "code": {"text": text}, "subject": {"reference": "Patient/P"}}


def run(resources, when=datetime(2026, 2, 1)):
    events, warnings = bundle_to_events(resources)
    assert warnings == [], warnings
    dets = ClinLoopDetector(evaluation_time=when).process_patient("fhir", "P", events["P"])
    statuses = {}
    for d in dets:
        statuses.setdefault(d.rule_id, []).append(d.loop_status.replace("needs_human_review", "open"))
    flat = {k: v[0] if len(v) == 1 else v for k, v in statuses.items()}
    reports = [e for e in events["P"] if e["event_type"] == "radiology_report"]
    return flat, dets, reports


def deadline_days(dets, rule_id):
    d = next(x for x in dets if x.rule_id == rule_id)
    return (datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds() / 86400


class TestBodyRegions(unittest.TestCase):

    def test_region_vocabulary(self):
        self.assertIn("adrenal", expand_regions(regions_in("CT abdomen and pelvis")))
        self.assertNotIn("chest", regions_in("CT thoracic spine"))
        self.assertIn("abdominal_aorta", regions_in("US abdominal aorta"))
        self.assertNotIn("abdominal_aorta", regions_in("CTA thoracic aorta"))
        self.assertTrue({"chest", "abdomen", "pelvis"} <= regions_in("PET/CT skull base to mid-thigh"))
        self.assertNotIn("kidney", regions_in("adrenal protocol CT"))

    def test_head_ct_does_not_close_adrenal_followup(self):
        statuses, dets, _ = run([patient(),
            rad("a", T0, "CT abdomen", "Indeterminate 18 mm left adrenal nodule. Recommend adrenal protocol CT in 3 months."),
            rad("b", "2026-03-01T09:00:00Z", "CT head without contrast", "No acute intracranial abnormality.")],
            when=datetime(2026, 5, 1))
        self.assertEqual(statuses, {"R030": "open"})
        chain = " ".join(dets[0].evidence_chain)
        self.assertIn("different or unknown body region", chain)

    def test_abdominal_ct_closes_adrenal_followup(self):
        statuses, _, _ = run([patient(),
            rad("a", T0, "CT abdomen", "Indeterminate 18 mm left adrenal nodule. Recommend adrenal protocol CT in 3 months."),
            rad("b", "2026-03-01T09:00:00Z", "CT abdomen and pelvis", "Stable left adrenal nodule.")],
            when=datetime(2026, 5, 1))
        self.assertEqual(statuses, {"R030": "closed"})

    def test_knee_radiograph_does_not_close_chest_radiograph(self):
        statuses, _, _ = run([patient(),
            rad("a", T0, "Chest radiograph", "Right lower lobe pneumonia. Recommend follow-up chest radiograph in 6 weeks."),
            rad("b", "2026-02-10T09:00:00Z", "Knee radiograph", "No fracture.")], when=datetime(2026, 4, 1))
        self.assertEqual(statuses, {"R033": "open"})

    def test_region_from_previous_sentence(self):
        statuses, _, reports = run([patient(),
            rad("a", T0, "CT abdomen", "8 mm indeterminate hepatic lesion. Follow-up MRI in 3-6 months is recommended."),
            rad("b", "2026-05-01T09:00:00Z", "MRI lumbar spine", "Degenerative change.")], when=datetime(2026, 9, 1))
        self.assertEqual(reports[0]["details"]["followup_regions"]["R031"], ["liver"])
        self.assertEqual(statuses, {"R031": "open"})


class TestFleischner2017(unittest.TestCase):

    def test_solid_under_6mm_not_tracked(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT chest", "4 mm solid nodule in the right middle lobe.")])
        self.assertEqual(statuses, {})

    def test_solid_6_to_8mm_twelve_month_window(self):
        statuses, dets, _ = run([patient(), smoking("266919005"),
                                 rad("a", T0, "CT chest", "7 mm solid nodule in the right middle lobe.")])
        self.assertEqual(statuses, {"R003": "open"})
        self.assertAlmostEqual(deadline_days(dets, "R003"), 365.25 + 30, delta=1)

    def test_solid_over_8mm_three_months(self):
        _, dets, _ = run([patient(), rad("a", T0, "CT chest", "1.1 cm solid nodule in the right lower lobe.")])
        self.assertAlmostEqual(deadline_days(dets, "R003"), 90 + 22.5, delta=1)

    def test_multiple_solid_three_to_six_months(self):
        _, dets, reports = run([patient(), rad("a", T0, "CT chest",
                                               "Multiple bilateral solid nodules, the largest 7 mm in the right lower lobe.")])
        self.assertTrue(reports[0]["details"]["radiology"]["lung_nodule"]["multiple"])
        self.assertAlmostEqual(deadline_days(dets, "R003"), 182.6 + 30, delta=1)

    def test_ground_glass(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT chest", "5 mm pure ground-glass nodule in the left lower lobe.")])
        self.assertEqual(statuses, {})
        _, dets, _ = run([patient(), rad("a", T0, "CT chest", "8 mm pure ground-glass nodule in the left lower lobe.")])
        self.assertAlmostEqual(deadline_days(dets, "R003"), 365.25 + 30, delta=1)

    def test_part_solid_with_large_solid_component(self):
        _, dets, reports = run([patient(), rad("a", T0, "CT chest",
                                               "9 mm part-solid nodule with a 7 mm solid component in the right upper lobe.")])
        nodule = reports[0]["details"]["radiology"]["lung_nodule"]
        self.assertEqual((nodule["type"], nodule["solid_component_mm"], nodule["multiple"]), ("part_solid", 7.0, False))
        self.assertAlmostEqual(deadline_days(dets, "R003"), 90 + 22.5, delta=1)

    def test_benign_calcified_nodule(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT chest", "8 mm calcified granuloma in the right upper lobe.")])
        self.assertEqual(statuses, {})

    def test_exclusions_need_human_review(self):
        for extra in ([condition("C50.9", "Breast cancer")], [condition("Z94.0", "Kidney transplant status")]):
            _, dets, _ = run([patient(), *extra, rad("a", T0, "CT chest", "9 mm solid nodule in the right lower lobe.")])
            d = next(x for x in dets if x.rule_id == "R003")
            self.assertEqual(d.loop_status, "needs_human_review")
            self.assertTrue(any("Fleischner 2017 does not apply" in line for line in d.evidence_chain))
        _, dets, _ = run([patient(birth="1996-01-01"), rad("a", T0, "CT chest", "9 mm solid nodule in the right lower lobe.")])
        self.assertTrue(any("under 35" in line for line in dets[0].evidence_chain))

    def test_stepped_followup_high_vs_low_risk(self):
        history = [rad("a", "2025-01-10T09:00:00Z", "CT chest", "7 mm solid nodule in the right middle lobe."),
                   rad("b", "2025-12-10T09:00:00Z", "CT chest", "Stable 7 mm solid nodule in the right middle lobe.")]
        statuses, _, _ = run([patient(), smoking("8517006"), *history])          # former smoker → high risk
        self.assertEqual(sorted(statuses["R003"]), ["closed", "open"])            # next CT at 18–24 months
        statuses, _, _ = run([patient(), smoking("266919005"), *history])        # never smoker → low risk
        self.assertEqual(statuses, {"R003": "closed"})                            # 18–24 month CT optional

    def test_solid_nodule_stable_two_years_is_done(self):
        statuses, _, reports = run([patient(),
            rad("a", "2024-01-10T09:00:00Z", "CT chest", "7 mm solid nodule in the right middle lobe."),
            rad("b", "2025-01-10T09:00:00Z", "CT chest", "Stable 7 mm solid nodule."),
            rad("c", "2026-01-12T09:00:00Z", "CT chest", "No change in the 7 mm right middle lobe nodule.")])
        self.assertEqual(statuses, {"R003": ["closed", "closed"]})
        self.assertTrue(any("stable ≥2 years" in m for m in reports[-1]["details"]["mapping"]))

    def test_stability_stated_in_text(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT chest", "8 mm solid nodule in the left upper lobe, stable for 2 years.")])
        self.assertEqual(statuses, {})

    def test_growth_triggers_workup(self):
        statuses, _, _ = run([patient(),
            rad("a", "2025-06-10T09:00:00Z", "CT chest", "7 mm solid nodule in the right middle lobe."),
            rad("b", "2025-12-10T09:00:00Z", "CT chest", "10 mm solid nodule in the right middle lobe.")])
        self.assertEqual(statuses, {"R003": "closed", "R046": "open"})
        statuses, _, _ = run([patient(), rad("a", T0, "CT chest", "Interval increase in the 9 mm right upper lobe nodule.")])
        self.assertEqual(statuses, {"R046": "open"})


class TestACRIncidentalFindings(unittest.TestCase):

    def test_adrenal(self):
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "Incidental 1.5 cm left adrenal nodule, indeterminate.")])[0],
                         {"R037": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen",
                                             "2.1 cm left adrenal nodule measuring 5 HU, consistent with lipid-rich adenoma.")])[0], {})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "4.5 cm right adrenal mass.")])[0], {"R038": "open"})
        self.assertEqual(run([patient(), condition("C34.1", "Lung cancer"),
                              rad("a", T0, "CT abdomen", "1.2 cm left adrenal nodule.")])[0], {"R038": "open"})

    def test_adrenal_word_is_not_renal(self):
        _, _, reports = run([patient(), rad("a", T0, "CT abdomen", "Incidental 18 mm left adrenal nodule.")])
        self.assertEqual([f["kind"] for f in reports[0]["details"]["radiology"]["incidental"]], ["adrenal"])

    def test_explicit_recommendation_wins(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT abdomen",
                                             "Incidental 18 mm left adrenal nodule. Recommend adrenal protocol CT in 12 months.")])
        self.assertEqual(statuses, {"R030": "open"})

    def test_renal(self):
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen",
                                             "2.1 cm solid enhancing mass in the left kidney, suspicious for renal cell carcinoma.")])[0],
                         {"R039": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "2.5 cm right renal cyst with thin septa, Bosniak IIF.")])[0],
                         {"R040": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "3 cm simple renal cyst, Bosniak I.")])[0], {})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "Subcentimeter renal hypodensities, too small to characterize.")])[0], {})

    def test_renal_mass_referral_closes(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT abdomen", "2.1 cm enhancing solid renal mass."),
                              referral("2026-01-20T09:00:00Z")])
        self.assertEqual(statuses, {"R039": "closed", "R008": "open"})    # the referral itself awaits its visit

    def test_renal_biopsy_advice_is_one_loop(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT abdomen",
                                             "2.1 cm enhancing left renal mass, suspicious for RCC. Recommend urology referral and biopsy.")])
        self.assertEqual(statuses, {"R039": "open"})

    def test_pancreatic_cyst(self):
        _, dets, _ = run([patient(), rad("a", T0, "CT abdomen", "1.2 cm cystic lesion in the pancreatic tail, likely side-branch IPMN.")])
        self.assertEqual([d.rule_id for d in dets], ["R041"])
        self.assertAlmostEqual(deadline_days(dets, "R041"), 2 * 365.25 + 30, delta=2)
        statuses, _, _ = run([patient(), rad("a", T0, "MRI abdomen MRCP",
                                             "3.2 cm pancreatic head cyst with an enhancing mural nodule. Main pancreatic duct measures 8 mm.")])
        self.assertEqual(statuses, {"R042": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "4 cm pancreatic pseudocyst.")])[0], {})

    def test_thyroid_incidental_age_threshold(self):
        nodule = "1.2 cm nodule in the right thyroid lobe."
        self.assertEqual(run([patient(birth="1960-01-01"), rad("a", T0, "CT chest", nodule)])[0], {})
        self.assertEqual(run([patient(birth="1996-01-01"), rad("a", T0, "CT chest", nodule)])[0], {"R043": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "CT neck", "1.8 cm hypodense left thyroid nodule.")])[0], {"R043": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "PET/CT skull base to mid-thigh",
                                             "8 mm FDG-avid nodule in the right thyroid lobe.")])[0], {"R043": "open"})

    def test_thyroid_ultrasound_tirads(self):
        self.assertEqual(run([patient(), rad("a", T0, "US thyroid",
                                             "1.2 cm solid hypoechoic nodule in the right lobe, ACR TI-RADS TR5.")])[0], {"R036": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "US thyroid",
                                             "1.2 cm solid hypoechoic nodule in the left lobe, TI-RADS TR4.")])[0], {"R032": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "US thyroid", "8 mm spongiform nodule, TI-RADS TR1.")])[0], {})

    def test_abdominal_aortic_aneurysm(self):
        _, dets, _ = run([patient(), rad("a", T0, "CT abdomen", "Infrarenal abdominal aortic aneurysm measuring 4.2 cm.")])
        self.assertEqual([d.rule_id for d in dets], ["R044"])
        self.assertAlmostEqual(deadline_days(dets, "R044"), 365.25 + 30, delta=1)
        self.assertEqual(run([patient(sex="female"), rad("a", T0, "CT abdomen",
                                                         "Fusiform infrarenal aortic aneurysm, maximal diameter 5.2 cm.")])[0],
                         {"R045": "open"})
        self.assertEqual(run([patient(sex="male"), rad("a", T0, "CT abdomen",
                                                       "Fusiform infrarenal aortic aneurysm, maximal diameter 5.2 cm.")])[0],
                         {"R044": "open"})
        self.assertEqual(run([patient(), rad("a", T0, "CT abdomen", "No abdominal aortic aneurysm.")])[0], {})

    def test_aaa_followup_needs_aortic_imaging(self):
        resources = [patient(), rad("a", T0, "CT abdomen", "Infrarenal abdominal aortic aneurysm measuring 4.2 cm.")]
        head = rad("b", "2026-06-01T09:00:00Z", "CT head", "Normal.")
        aorta = rad("c", "2026-12-01T09:00:00Z", "US abdominal aorta", "Abdominal aortic aneurysm 4.3 cm.")
        self.assertEqual(run(resources + [head], when=datetime(2027, 6, 1))[0]["R044"], "open")
        self.assertIn("closed", run(resources + [aorta], when=datetime(2027, 6, 1))[0]["R044"])


class TestCriticalFindingList(unittest.TestCase):

    def test_default_list_loads_with_hash(self):
        active = load_critical_findings()
        self.assertEqual(len(active["hash"]), 64)
        self.assertTrue(any(f["id"] == "pulmonary_embolism" for f in active["data"]["findings"]))

    def test_hospital_list_and_window_are_used(self):
        custom = {"name": "Test hospital", "findings": [
            {"id": "pe", "category": 1, "window_minutes": 30, "label": {"en": "PE"}, "patterns": ["pulmonary embol\\w*"]},
            {"id": "sbo", "category": 2, "window_minutes": 240, "label": {"en": "SBO"}, "patterns": ["bowel obstruction"]},
        ]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(custom, f)
        old = os.environ.get("CLINLOOP_CRITICAL_FINDINGS")
        os.environ["CLINLOOP_CRITICAL_FINDINGS"] = f.name
        try:
            _, dets, _ = run([patient(), rad("a", T0, "CT chest", "Acute pulmonary embolism.")])
            self.assertAlmostEqual(deadline_days(dets, "R035") * 1440, 30, delta=0.5)
            _, dets, _ = run([patient(), rad("a", T0, "CT abdomen", "Small bowel obstruction.")])
            self.assertAlmostEqual(deadline_days(dets, "R035") * 1440, 240, delta=0.5)
            statuses, _, _ = run([patient(), rad("a", T0, "CT chest", "Small right pneumothorax.")])
            self.assertEqual(statuses, {})   # not on this hospital's list
        finally:
            if old is None:
                os.environ.pop("CLINLOOP_CRITICAL_FINDINGS")
            else:
                os.environ["CLINLOOP_CRITICAL_FINDINGS"] = old
            os.unlink(f.name)


class TestLiveRunBundle(unittest.TestCase):
    """The 30-patient radiology live-run set (docs/RADIOLOGY_LIVE_RUN.md), evaluated on 2026-10-08."""

    EXPECTED = {
        "RP-01": {"R003": "open"}, "RP-02": {"R003": "open"}, "RP-03": {"R030": "open"},
        "RP-04": {"R019": "closed", "R034": "open"}, "RP-05": {"R030": "open"}, "RP-06": {"R018": "open"},
        "RP-07": {"R027": "delayed", "R028": "open"}, "RP-08": {"R036": "open"}, "RP-09": {}, "RP-10": {},
        "RP-11": {"R031": "open"}, "RP-12": {"R003": "open"}, "RP-13": {"R033": "open"}, "RP-14": {"R035": "open"},
        "RP-15": {"R003": "open"}, "RP-16": {"R030": "open"}, "RP-17": {"R037": "open"}, "RP-18": {"R030": "open"},
        "RP-19": {"R039": "open"}, "RP-20": {"R041": "open"}, "RP-21": {"R042": "open"}, "RP-22": {"R043": "open"},
        "RP-23": {"R044": "open"}, "RP-24": {"R045": "open"}, "RP-25": {"R003": "open"},
        "RP-26": {"R003": ["closed", "open"]}, "RP-27": {"R003": "closed", "R046": "open"},
        "RP-28": {"R003": "open"}, "RP-29": {"R035": "closed"}, "RP-30": {},
    }

    def test_every_patient(self):
        with open(os.path.join(ROOT, "data", "radiology_test_bundle.json"), encoding="utf-8") as f:
            events, warnings = bundle_to_events(json.load(f))
        self.assertEqual(warnings, [])
        self.assertEqual(sorted(events), sorted(self.EXPECTED))
        for pid, expected in self.EXPECTED.items():
            dets = ClinLoopDetector(evaluation_time=datetime(2026, 10, 8)).process_patient("f", pid, events[pid])
            got = {}
            for d in dets:
                got.setdefault(d.rule_id, []).append(d.loop_status.replace("needs_human_review", "open"))
            got = {k: sorted(v) if len(v) > 1 else v[0] for k, v in got.items()}
            self.assertEqual(got, expected, pid)


class TestIndependentReviewCases(unittest.TestCase):
    """Report wordings from an independent review that the first version got wrong."""

    CASES = [
     # 1 decimal sizes
     ("CT abdomen","Right kidney 2.5 cm lesion, Bosniak IIF.",{"R040"}),
     ("CT abdomen","Left adrenal 4.5 cm mass.",{"R038"}),
     ("CT abdomen","Left adrenal gland: 1.8 cm nodule, 30 HU.",{"R037"}),
     ("CT neck","Left thyroid lobe 1.6 cm nodule.",{"R043"}),
     # 2 longest axis
     ("CT abdomen","AAA measuring 5.6 x 5.2 cm.",{"R045"}),
     ("US thyroid","Thyroid nodule 1.6 x 0.8 x 1.0 cm, TR4.",{"R036"}),
     ("CT abdomen","Left adrenal mass 4 x 3 cm.",{"R038"}),
     # 3 critical with prior/known
     ("Chest radiograph","Compared to prior, new large left pneumothorax.",{"R035"}),
     ("CTA chest","Compared with the prior CT, there is new acute pulmonary embolism.",{"R035"}),
     ("Chest radiograph","In this patient with known COPD, new large right pneumothorax.",{"R035"}),
     ("Chest radiograph","Assessment: large right tension pneumothorax.",{"R035"}),
     # 4 list negation
     ("Chest radiograph","Lungs: no consolidation, large right pneumothorax.",{"R035"}),
     ("CT chest","Lungs: no consolidation, 9 mm solid nodule in the right lower lobe.",{"R003"}),
     ("CT abdomen","Kidneys: no hydronephrosis, 3 cm enhancing solid mass in the left kidney.",{"R039"}),
     ("Chest radiograph","Without prior studies, recommend CT chest in 3 months.",{"R030"}),
     ("CT abdomen","No acute findings, recommend CT in 3 months.",{"R030"}),
     # 5 Korean 간
     ("흉부 CT","추적 기간 중 새로 생긴 9 mm 결절.",{"R003"}),
     ("흉부 CT","6개월간 새로 생긴 9 mm 결절.",{"R003"}),
     # 7 growth wording
     ("CT chest","Right lower lobe nodule now 9 mm, was 6 mm.",{"R046"}),
     ("CT chest","Right lower lobe nodule measures 9 mm, previously 6 mm.",{"R046"}),
     # 8 wording
     ("CT chest","Suggest follow-up CT in 3 months.",{"R030"}),
     ("CT chest","Advise repeat CT in 3 months.",{"R030"}),
     ("CT chest","Repeat CT in 3 months.",{"R030"}),
     ("US abdomen","Follow-up ultrasound in 6 months.",{"R032"}),
     ("CT abdomen","MRI 추가 검사 권고.",{"R031"}),
     # 9 communication
     ("CT head","Acute subdural hematoma. Results will be called to Dr Lee.",{"R035"}),
     ("CT head","Acute subdural hematoma. Findings were discussed with the patient.",{"R035"}),
     ("CT head","Acute subdural hematoma. Findings discussed with radiology resident.",{"R035"}),
     # 10 Korean negation
     ("두부 CT","뇌출혈은 보이지 않음.",set()),
     ("두부 CT","급성 뇌경색은 관찰되지 않음.",set()),
     ("흉부 X선","기흉은 보이지 않음.",set()),
     ("흉부 CT","7 mm 폐결절은 보이지 않음.",set()),
     ("US thyroid","조직검사는 필요하지 않음.",set()),
     ("CT abdomen","1년 후 CT 권고 안 함.",set()),
     # 11
     ("CT chest","Previously described 7 mm nodule is no longer seen.",set()),
     # 12
     ("CT head","There is no intracranial hemorrhage, mass effect, hydrocephalus, extra-axial collection, or acute infarct.",set()),
     # 13
     ("Chest radiograph","Pneumothorax resolved.",set()),
     ("Chest radiograph","Interval resolution of the pneumothorax.",set()),
     ("Chest radiograph","Left pneumothorax has decreased in size.",set()),
     ("CTA chest","Type B aortic dissection, unchanged from prior.",set()),
     ("CTA chest","Pulmonary embolism decreased in burden.",set()),
     ("CT abdomen","Postoperative free air, expected.",set()),
     ("CTA chest","Pulmonary embolism: none.",set()),
     ("MRI brain","Subacute infarct in the left MCA territory.",set()),
     # 14 negated growth
     ("CT chest","7 mm nodule in the right lower lobe without growth.",{"R003"}),
     ("CT chest","7 mm right lower lobe nodule, not increased.",{"R003"}),
     ("CT chest","7 mm right lower lobe nodule has not grown.",{"R003"}),
     ("CT chest","No significant interval growth of the 7 mm right lower lobe nodule.",{"R003"}),
     ("CT chest","7 mm right lower lobe nodule adjacent to enlarged lymph nodes.",{"R003"}),
     # 15
     ("CT chest","Recommend 6-month follow-up CT.",{"R030"}),
     ("CT chest","A 6 month follow-up CT is recommended.",{"R030"}),
     ("CT abdomen","Recommend follow-up in 6 months with CT.",{"R030"}),
     ("CT chest","The 6-month follow-up CT showed a stable appearance.",set()),
     # 16 hedges
     ("CT abdomen","Recommend CT in 1 year if clinically indicated.",set()),
     ("복부 CT","임상적으로 필요시 6개월 후 CT 권고.",set()),
     # 19
     ("US thyroid","1.2 cm solid nodule, TI-RADS: 7 points (TR5).",{"R036"}),
     ("US thyroid","1.2 cm solid nodule, K-TIRADS 4.",{"R036"}),
     # 21 cap
     ("CT chest","Recommend CT in 99999999999 years.",set()),
     ("CT chest","Recommend CT in 0 months.",set()),
    ]

    def test_cases(self):
        for title, text, expected in self.CASES:
            with self.subTest(text=text):
                statuses, _, _ = run([patient(), rad("a", T0, title, text)])
                self.assertEqual(set(statuses), expected)

    def test_anatomical_descriptors_are_not_regions(self):
        statuses, _, _ = run([patient(), rad("a", T0, "CT abdomen", "Pancreatic head cyst 2 cm. Recommend MRI in 1 month."),
                              rad("b", "2026-01-20T09:00:00Z", "MRI brain", "Normal.")], when=datetime(2026, 3, 1))
        self.assertEqual(statuses["R031"], "open")
        statuses, _, _ = run([patient(), rad("a", T0, "US abdomen", "Gallbladder neck stone. Recommend ultrasound in 2 weeks."),
                              rad("b", "2026-01-15T09:00:00Z", "US thyroid", "Normal.")], when=datetime(2026, 3, 1))
        self.assertEqual(statuses["R032"], "open")
        self.assertNotIn("pelvis", regions_in("CT renal pelvis"))

    def test_korean_title_without_space(self):
        statuses, _, _ = run([patient(), rad("a", T0, "복부CT", "Recommend CT in 1 month."),
                              rad("b", "2026-01-25T09:00:00Z", "복부CT", "Normal.")], when=datetime(2026, 3, 1))
        self.assertEqual(statuses, {"R030": "closed"})
        self.assertNotIn("chest", regions_in("장폐색 의심 복부 CT"))
        self.assertNotIn("chest", regions_in("폐경 후 골반 초음파"))

    def test_partial_fhir_date(self):
        events, _ = bundle_to_events([patient(), rad("a", "2026-01", "CT chest", "9 mm solid nodule in the right lower lobe.")])
        self.assertTrue(events["P"])


if __name__ == "__main__":
    unittest.main()
