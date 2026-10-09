"""
test_hospital_data.py — Behaviour found by running a full hospital-style EHR export (Synthea FHIR bulk data)

Each test reproduces one problem a real hospital feed showed, with small synthetic resources:
renewals counted as medication changes, known heart failure counted as new, AKI warnings on
dialysis, decades-old obligations on today's worklist, and labs with ranges but no flags.
"""

import os
import sys
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector, hospital_detector  # noqa: E402

P = {"resourceType": "Patient", "id": "P", "gender": "male", "birthDate": "1950-01-01"}
NOW = datetime(2023, 4, 1)


def rules(resources, when=NOW, detector=None):
    events, warnings = bundle_to_events([P] + resources)
    det = detector or ClinLoopDetector(evaluation_time=when)
    return [d for d in det.process_patient("t", "P", events.get("P", []))], warnings


def med(rid, when, text="lisinopril 10 MG Oral Tablet", dose=None):
    r = {"resourceType": "MedicationRequest", "id": rid, "status": "active", "intent": "order",
         "subject": {"reference": "Patient/P"}, "authoredOn": when, "medicationCodeableConcept": {"text": text}}
    if dose:
        r["dosageInstruction"] = [{"text": dose}]
    return r


def lab(rid, when, loinc, text, value, unit="mg/dL", **extra):
    return {"resourceType": "Observation", "id": rid, "status": "final", "subject": {"reference": "Patient/P"},
            "category": [{"coding": [{"code": "laboratory"}]}], "effectiveDateTime": when,
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc}], "text": text},
            "valueQuantity": {"value": value, "unit": unit}, **extra}


def encounter(rid, cls, start, end, reason):
    return {"resourceType": "Encounter", "id": rid, "status": "finished", "class": {"code": cls},
            "subject": {"reference": "Patient/P"}, "period": {"start": start, "end": end},
            "reasonCode": [{"text": reason}]}


def condition(rid, onset, text):
    return {"resourceType": "Condition", "id": rid, "subject": {"reference": "Patient/P"}, "onsetDateTime": onset,
            "clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"text": text}}


class TestHospitalExport(unittest.TestCase):

    def test_a_renewal_is_not_a_medication_change(self):
        found, _ = rules([med("m1", "2022-01-10T09:00:00"), med("m2", "2022-07-10T09:00:00"),
                          med("m3", "2023-01-10T09:00:00")])
        self.assertEqual([d.trigger_event_id for d in found if d.rule_id == "R010"],
                         ["MedicationRequest/m1:medication_change"])        # the start only

    def test_a_new_dose_or_a_restart_is_a_change(self):
        found, _ = rules([med("m1", "2021-01-10T09:00:00"), med("m2", "2021-03-10T09:00:00", "lisinopril 20 MG Oral Tablet"),
                          med("m3", "2022-09-10T09:00:00", "lisinopril 20 MG Oral Tablet")])   # 18 months later: restart
        self.assertEqual(sum(d.rule_id == "R010" for d in found), 3)

    def test_warfarin_dose_change_with_the_same_tablet_is_a_change(self):
        tab = "warfarin sodium 5 MG Oral Tablet"
        found, _ = rules([med("w1", "2023-01-02T09:00:00", tab, "5 mg daily"),
                          med("w2", "2023-02-02T09:00:00", tab, "7.5 mg daily"),
                          med("w3", "2023-03-02T09:00:00", tab, "7.5 mg daily")])
        triggers = sorted(d.trigger_event_id for d in found if d.trigger_event == "medication_change")
        self.assertIn("MedicationRequest/w2:medication_change", triggers)
        self.assertNotIn("MedicationRequest/w3:medication_change", triggers)

    def test_known_heart_failure_is_not_a_new_diagnosis(self):
        known = [condition("c1", "2019-05-01", "Chronic congestive heart failure (disorder)"),
                 encounter("e1", "IMP", "2023-02-01T08:00:00", "2023-02-05T10:00:00", "Chronic congestive heart failure")]
        found, _ = rules(known)
        self.assertNotIn("R016", {d.rule_id for d in found})               # no "new HF → echo"
        self.assertIn("R023", {d.rule_id for d in found})                  # but the 7-day visit is still due
        first, _ = rules([encounter("e1", "IMP", "2023-02-01T08:00:00", "2023-02-05T10:00:00", "Heart failure")])
        self.assertIn("R016", {d.rule_id for d in first})

    def test_no_aki_warning_on_dialysis_but_again_after_transplant(self):
        crea = [lab(f"k{i}", f"2022-0{m}-01T08:00:00", "2160-0", "Creatinine", v)
                for i, (m, v) in enumerate([(1, 4.0), (2, 4.1), (3, 8.5)])]
        dialysis = {"resourceType": "Procedure", "id": "d1", "status": "completed", "subject": {"reference": "Patient/P"},
                    "code": {"text": "Renal dialysis (procedure)"}, "performedDateTime": "2022-02-15T08:00:00"}
        self.assertIn("R053", {d.rule_id for d in rules(crea)[0]})
        self.assertNotIn("R053", {d.rule_id for d in rules(crea + [dialysis])[0]})
        later = [lab("t0", "2022-09-15T08:00:00", "2160-0", "Creatinine", 1.0),     # a working transplant
                 lab("t1", "2022-10-01T08:00:00", "2160-0", "Creatinine", 1.0),
                 lab("t2", "2022-10-15T08:00:00", "2160-0", "Creatinine", 1.1),
                 lab("t3", "2022-11-01T08:00:00", "2160-0", "Creatinine", 2.2)]     # months after the last session
        self.assertIn("R053", {d.rule_id for d in rules(crea + [dialysis] + later)[0]})
        esrd = condition("c2", "2021-06-01", "End-stage renal disease (disorder)")
        self.assertNotIn("R053", {d.rule_id for d in rules(crea + [esrd])[0]})

    def test_reference_range_flags_a_result_without_an_interpretation(self):
        rng = {"referenceRange": [{"low": {"value": 3.5}, "high": {"value": 5.1}}]}
        found, _ = rules([lab("p1", "2023-03-30T08:00:00", "2823-3", "Potassium", 6.2, "mmol/L", **rng)])
        self.assertTrue({"R001", "R002"} & {d.rule_id for d in found})
        normal, _ = rules([lab("p1", "2023-03-30T08:00:00", "2823-3", "Potassium", 4.2, "mmol/L", **rng)])
        self.assertFalse({"R001", "R002"} & {d.rule_id for d in normal})
        two = {"referenceRange": [{"low": {"value": 3.5}, "high": {"value": 5.1}},
                                  {"low": {"value": 3.4}, "high": {"value": 4.7}, "appliesTo": [{"text": "neonate"}]}]}
        self.assertTrue({"R001", "R002"} & {d.rule_id for d in rules(
            [lab("p1", "2023-03-30T08:00:00", "2823-3", "Potassium", 6.2, "mmol/L", **two)])[0]})

    def test_referral_recorded_as_a_procedure(self):
        psa = lab("p1", "2023-02-01T08:00:00", "2857-1", "Prostate specific Ag", 6.1, "ng/mL")

        def proc(text):
            return {"resourceType": "Procedure", "id": "r1", "status": "completed", "subject": {"reference": "Patient/P"},
                    "code": {"text": text}, "performedPeriod": {"start": "2023-02-10T09:00:00"}}
        r004 = {d.rule_id: d for d in rules([psa, proc("Referral to urology service (procedure)")])[0]}["R004"]
        self.assertEqual(r004.loop_status, "closed")
        dental = {d.rule_id: d for d in rules([psa, proc("Patient referral for dental care (procedure)")])[0]}["R004"]
        self.assertEqual(dental.loop_status, "open")          # not a urology referral

    def test_a_feed_without_flags_or_ranges_says_so(self):
        labs = [lab(f"l{i}", "2023-03-01T08:00:00", "2345-7", "Glucose", 90 + i) for i in range(25)]
        _, warnings = rules(labs)
        self.assertTrue(any("no interpretation flag and no reference range" in w for w in warnings))
        _, few = rules(labs[:5])
        self.assertFalse(any("no interpretation flag" in w for w in few))

    def test_hospital_worklist_leaves_out_decades_old_obligations(self):
        psa = [lab("old", "1977-03-26T03:31:03", "2857-1", "Prostate specific Ag", 4.6, "ng/mL"),
               lab("new", "2023-03-01T08:00:00", "2857-1", "Prostate specific Ag", 5.2, "ng/mL")]
        everything, _ = rules(psa)
        self.assertEqual(sum(d.rule_id == "R004" for d in everything), 2)
        with mock.patch.dict(os.environ, {"CLINLOOP_HISTORY_DAYS": "365"}):
            recent, _ = rules(psa, detector=hospital_detector(NOW))
        self.assertEqual([d.trigger_event_id for d in recent if d.rule_id == "R004"], ["Observation/new:lab_result"])
        with mock.patch.dict(os.environ, {"CLINLOOP_HISTORY_DAYS": "0"}):
            self.assertEqual(sum(d.rule_id == "R004" for d in rules(psa, detector=hospital_detector(NOW))[0]), 2)


if __name__ == "__main__":
    unittest.main()
