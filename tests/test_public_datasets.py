"""
test_public_datasets.py — OMOP CDM and MIMIC-IV / MIMIC-IV-Note / MIMIC-CXR readers

The fixtures are made-up rows in the official column layouts (tests/fixtures/omop, mimic, mimic_note,
mimic_cxr). No real MIMIC or OMOP data is stored in this repository.
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import mimic_ingest, omop_ingest  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events, icd_label  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector, lapse_after_death  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def loops(resources, pid, when):
    events, warnings = bundle_to_events(resources)
    found = ClinLoopDetector(evaluation_time=when).process_patient("t", pid, events.get(pid, []))
    return {d.rule_id: d for d in lapse_after_death(found, resources)}, warnings


class TestOMOP(unittest.TestCase):

    def setUp(self):
        self.people = omop_ingest.load_cdm(os.path.join(FIX, "omop"))

    def test_tables_become_fhir_with_vocabulary_codes(self):
        p1 = self.people["1"]
        kinds = {r["resourceType"] for r in p1}
        self.assertTrue({"Patient", "Encounter", "Condition", "Observation", "MedicationRequest",
                         "DiagnosticReport"} <= kinds)
        k = next(r for r in p1 if r.get("id") == "m1000")
        self.assertEqual(k["code"]["coding"][0], {"system": "http://loinc.org", "code": "2823-3",
                                                  "display": "Potassium [Moles/volume] in Serum or Plasma"})
        self.assertEqual(k["referenceRange"], [{"low": {"value": 3.5}, "high": {"value": 5.1}}])
        stay = next(r for r in p1 if r.get("id") == "v10")
        self.assertEqual((stay["class"]["code"], stay["reasonCode"][0]["text"]), ("IMP", "Heart failure"))
        self.assertEqual(next(r for r in self.people["2"] if r["resourceType"] == "Patient")["deceasedDateTime"],
                         "2023-01-20")

    def test_rules_run_on_omop_data(self):
        found, _ = loops(self.people["1"], "1", "2023-06-01T00:00:00")
        self.assertIn("R004", found)                 # PSA 7.2 (LOINC from the vocabulary)
        self.assertIn("R010", found)                 # lisinopril started in clinic
        self.assertTrue({"R003", "R030"} & set(found))   # nodule in the radiology note (Fleischner for a smoker)
        self.assertIn("R023", found)                 # heart-failure discharge
        self.assertNotIn("R001", found)              # the high potassium was taken in hospital

    def test_cli_prints_counts_only(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            omop_ingest.main([os.path.join(FIX, "omop")])
        self.assertIn("persons: 2", buf.getvalue())
        self.assertNotIn("nodule", buf.getvalue())


class TestMIMIC(unittest.TestCase):

    def setUp(self):
        self.people = mimic_ingest.load(os.path.join(FIX, "mimic"), ["19990001", "19990002"],
                                        os.path.join(FIX, "mimic_note"), os.path.join(FIX, "mimic_cxr"))

    def test_every_module_is_read(self):
        ids = {r["id"] for r in self.people["19990001"]}
        self.assertTrue({"29990001", "ed-39990001", "lab-2", "micro-1", "rx-501-1", "note-19990001-RR-1",
                         "note-19990001-DS-1", "cxr-59990001"} <= ids)
        self.assertNotIn("micro-2", ids)             # an antibiotic row is not a second culture
        cxr = [r for r in self.people["19990001"] if r["id"] == "cxr-59990001"]
        self.assertEqual(len(cxr), 1)                # one report per study, not per image
        self.assertEqual(cxr[0]["effectiveDateTime"], "2150-03-01")

    def test_obligations_from_a_whole_mimic_style_record(self):
        found, _ = loops(self.people["19990001"], "19990001", "2150-06-01T00:00:00")
        expected = {"R030": "nodule on CT", "R051": "cardiology visit in the discharge summary",
                    "R048": "repeat potassium in the discharge summary", "R023": "heart-failure discharge",
                    "R015": "Staph aureus bacteraemia", "R002": "outpatient high potassium"}
        for rule, why in expected.items():
            self.assertIn(rule, found, why)
        self.assertNotIn("R016", found)              # "acute on chronic" heart failure is not a new diagnosis
        self.assertNotIn("R010", found)              # lisinopril started in hospital: monitored there (MIMIC orders are inpatient)

    def test_sample_and_bulk_output(self):
        self.assertEqual(mimic_ingest.choose_subjects(os.path.join(FIX, "mimic"), 1),
                         mimic_ingest.choose_subjects(os.path.join(FIX, "mimic"), 1))   # reproducible
        with tempfile.TemporaryDirectory() as out:
            counts = mimic_ingest.write_bulk(self.people, out)
            self.assertTrue(os.path.exists(os.path.join(out, "Observation.000.ndjson")))
            self.assertEqual(counts["Patient"], 2)


class TestECG(unittest.TestCase):

    @staticmethod
    def ecg_obs(rid, when, text="", qtc=None):
        r = {"resourceType": "Observation", "id": rid, "status": "final", "subject": {"reference": "Patient/P"},
             "code": {"coding": [{"system": "http://loinc.org", "code": "11524-6"}], "text": "12-lead ECG"},
             "effectiveDateTime": when, "valueString": text}
        if qtc is not None:
            r["component"] = [{"code": {"coding": [{"system": "http://loinc.org", "code": "8636-3"}]},
                               "valueQuantity": {"value": qtc, "unit": "ms"}}]
        return r

    def test_prolonged_qtc_needs_review_or_repeat_ecg_within_a_day(self):
        P = {"resourceType": "Patient", "id": "P", "gender": "female", "birthDate": "1950-01-01"}
        first = self.ecg_obs("e1", "2023-03-01T08:00:00", "Sinus rhythm. QTc 528 ms.")
        found, _ = loops([P, first], "P", "2023-03-03T00:00:00")
        self.assertEqual(found["R059"].loop_status, "open")
        repeat = self.ecg_obs("e2", "2023-03-01T20:00:00", "Sinus rhythm", qtc=470)
        found, _ = loops([P, first, repeat], "P", "2023-03-03T00:00:00")
        self.assertEqual(found["R059"].loop_status, "closed")
        self.assertNotIn("R059", loops([P, self.ecg_obs("e3", "2023-03-01T08:00:00", qtc=462)], "P",
                                       "2023-03-03T00:00:00")[0])
        self.assertIn("R059", loops([P, self.ecg_obs("e4", "2023-03-01T08:00:00", qtc=0.51)], "P",
                                    "2023-03-03T00:00:00")[0])          # seconds are converted

    def test_af_on_an_ecg_reaches_the_anticoagulation_rule(self):
        P = {"resourceType": "Patient", "id": "P", "gender": "male", "birthDate": "1945-01-01"}
        htn = {"resourceType": "Condition", "id": "c", "subject": {"reference": "Patient/P"},
               "clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"text": "Essential hypertension"},
               "onsetDateTime": "2020-01-01"}
        af = self.ecg_obs("e1", "2023-01-10T08:00:00", "Atrial fibrillation with rapid ventricular response")
        self.assertIn("R054", loops([P, htn, af], "P", "2023-04-01T00:00:00")[0])
        no_af = self.ecg_obs("e2", "2023-01-10T08:00:00", "Sinus rhythm. No atrial fibrillation.")
        self.assertNotIn("R054", loops([P, htn, no_af], "P", "2023-04-01T00:00:00")[0])

    def test_ptbxl_statements_and_german_reports(self):
        from src.clinloop_engine import ecg
        people = ecg.load_ptbxl(os.path.join(FIX, "ptbxl", "ptbxl_database.csv"))
        self.assertEqual(sorted(people), ["90001", "90002", "90003"])
        dx = {pid: [e for e in bundle_to_events(rs)[0].get(pid, []) if e["event_type"] == "diagnosis"]
              for pid, rs in people.items()}
        self.assertEqual(len(dx["90001"]), 1)          # AFIB statement and "vorhofflimmern"
        self.assertEqual(dx["90002"], [])
        self.assertEqual(dx["90003"], [])              # "kein vorhofflimmern", AFIB likelihood 15: uncertain


class TestCodedDiagnoses(unittest.TestCase):

    def test_icd_codes_without_names(self):
        self.assertEqual(icd_label(["I50.23"]), "chronic heart failure")
        self.assertEqual(icd_label(["I50.9"]), "heart failure")
        self.assertEqual(icd_label(["42731"]), "atrial fibrillation")
        self.assertEqual(icd_label(["Z99.2", "I10"]), "end-stage renal disease on dialysis")
        self.assertEqual(icd_label(["I10"]), "")


if __name__ == "__main__":
    unittest.main()
