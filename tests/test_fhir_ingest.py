"""
test_fhir_ingest.py — FHIR R4 ingestion adapter

Runs the synthetic example bundle (data/fhir_example_bundle.json) through
the adapter and the detection engine, and pins the mapping decisions that
decide whether a patient is caught.
"""

import json
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events, CLINLOOP_EVENT_TYPE_URL
from src.clinloop_engine.loop_detector import ClinLoopDetector

EVAL = datetime(2026, 9, 1)


def _load_bundle():
    with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
        return json.load(f)


def _detect(events_by_patient, pid):
    dets = ClinLoopDetector(evaluation_time=EVAL).process_patient("fhir", pid, events_by_patient[pid])
    return {d.rule_id: d.loop_status for d in dets}


class TestFHIRExampleBundle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.events, cls.warnings = bundle_to_events(_load_bundle())

    def test_no_warnings_and_all_patients_mapped(self):
        self.assertEqual(self.warnings, [])
        self.assertEqual(len(self.events), 7)

    def test_positive_fit_without_colonoscopy(self):
        self.assertEqual(_detect(self.events, "SYN-001"), {"R017": "open"})

    def test_large_nodule_with_no_show_ct(self):
        status = _detect(self.events, "SYN-002")
        self.assertEqual(status["R003"], "open")
        ct = [e for e in self.events["SYN-002"] if e["event_type"] == "followup_ct"][0]
        self.assertEqual(ct["status"], "no_show")

    def test_critical_potassium_notification_closes_r022(self):
        self.assertEqual(_detect(self.events, "SYN-003")["R022"], "closed")

    def test_pathology_negation_does_not_hide_cancer(self):
        path = [e for e in self.events["SYN-004"] if e["event_type"] == "pathology_result"][0]
        self.assertEqual(path["details"]["condition"], "abnormal")
        self.assertIn("adenocarcinoma", path["details"]["evidence_span"].lower())
        self.assertEqual(_detect(self.events, "SYN-004")["R009"], "open")

    def test_post_discharge_positive_culture(self):
        self.assertEqual(_detect(self.events, "SYN-005")["R006"], "open")

    def test_therapeutic_inr_is_not_an_abnormal_result(self):
        self.assertEqual(_detect(self.events, "SYN-006"), {"R007": "closed"})

    def test_post_mi_with_fulfilled_visit(self):
        self.assertEqual(_detect(self.events, "SYN-007"), {"R014": "closed"})


class TestFHIRMappingRules(unittest.TestCase):

    def _one(self, resource):
        events, warnings = bundle_to_events([resource])
        self.assertEqual(warnings, [])
        return list(events.values())[0]

    def test_booked_appointment_is_not_fulfilment(self):
        events = self._one({"resourceType": "Appointment", "id": "a", "status": "booked",
                            "start": "2026-05-01T09:00:00Z", "description": "Clinic review",
                            "participant": [{"actor": {"reference": "Patient/P"}}]})
        self.assertEqual(events[0]["status"], "scheduled")

    def test_negated_pathology_is_not_abnormal(self):
        events = self._one({"resourceType": "DiagnosticReport", "id": "d", "status": "final",
                            "category": [{"coding": [{"code": "PAT"}]}],
                            "subject": {"reference": "Patient/P"}, "issued": "2026-05-01T09:00:00Z",
                            "conclusion": "Benign colonic mucosa. No evidence of malignancy."})
        self.assertNotIn("condition", events[0]["details"])

    def test_explicit_extension_overrides_mapping(self):
        events = self._one({"resourceType": "Procedure", "id": "p", "status": "completed",
                            "subject": {"reference": "Patient/P"},
                            "performedDateTime": "2026-05-01T09:00:00Z", "code": {"text": "Local code 9911"},
                            "extension": [{"url": CLINLOOP_EVENT_TYPE_URL, "valueCode": "colonoscopy"}]})
        self.assertEqual(events[0]["event_type"], "colonoscopy")

    def test_missing_patient_is_reported_not_dropped_silently(self):
        _, warnings = bundle_to_events([{"resourceType": "Observation", "id": "o", "status": "final",
                                         "effectiveDateTime": "2026-05-01T09:00:00Z",
                                         "code": {"text": "Potassium"}}])
        self.assertEqual(len(warnings), 1)

    def test_event_ids_are_stable_across_resource_order(self):
        resources = [r["resource"] for r in _load_bundle()["entry"]]
        a, _ = bundle_to_events(resources)
        b, _ = bundle_to_events(list(reversed(resources)))
        ids = lambda ev: sorted(e["event_id"] for events in ev.values() for e in events)
        self.assertEqual(ids(a), ids(b))

    def test_entered_in_error_is_ignored(self):
        events, _ = bundle_to_events([{"resourceType": "Observation", "id": "o",
                                       "status": "entered-in-error", "subject": {"reference": "Patient/P"},
                                       "effectiveDateTime": "2026-05-01T09:00:00Z", "code": {"text": "K"}}])
        self.assertEqual(events, {})

    def test_monitoring_lab_after_drug_change_fulfils_r010(self):
        events, _ = bundle_to_events([
            {"resourceType": "MedicationRequest", "id": "m", "status": "active",
             "subject": {"reference": "Patient/P"}, "authoredOn": "2026-03-01T09:00:00Z",
             "medicationCodeableConcept": {"text": "Lithium carbonate 300 mg"}},
            {"resourceType": "Observation", "id": "o", "status": "final",
             "subject": {"reference": "Patient/P"}, "effectiveDateTime": "2026-03-06T09:00:00Z",
             "code": {"coding": [{"system": "http://loinc.org", "code": "14334-7"}], "text": "Lithium"}},
        ])
        dets = ClinLoopDetector(evaluation_time=EVAL).process_patient("fhir", "P", events["P"])
        self.assertEqual({d.rule_id: d.loop_status for d in dets}["R010"], "closed")



def _rad(rid, pid, when, title, conclusion, status="final"):
    return {"resourceType": "DiagnosticReport", "id": rid, "status": status,
            "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": title},
            "subject": {"reference": f"Patient/{pid}"}, "effectiveDateTime": when, "conclusion": conclusion}


class TestFHIRWaveTwoMapping(unittest.TestCase):

    def _rules(self, resources, when=EVAL):
        events, warnings = bundle_to_events(resources)
        self.assertEqual(warnings, [])
        pid = next(iter(events))
        dets = ClinLoopDetector(evaluation_time=when).process_patient("fhir", pid, events[pid])
        return {d.rule_id: d.loop_status for d in dets}, events[pid]

    def test_radiologist_recommendation_becomes_a_loop(self):
        statuses, events = self._rules([
            _rad("r1", "P", "2026-01-10T09:00:00Z", "CT abdomen and pelvis",
                 "Indeterminate 1.8 cm left adrenal nodule. Recommend adrenal protocol CT in 3 months."),
        ])
        self.assertEqual(statuses, {"R030": "open"})
        report = next(e for e in events if e["event_type"] == "radiology_report")
        self.assertIn("Recommend adrenal protocol CT in 3 months", report["details"]["evidence_span"])

    def test_completed_study_of_same_modality_closes_recommendation(self):
        statuses, _ = self._rules([
            _rad("r1", "P", "2026-01-10T09:00:00Z", "CT abdomen", "Recommend CT in 3 months."),
            _rad("r2", "P", "2026-04-01T09:00:00Z", "CT adrenal protocol", "Stable adrenal adenoma."),
        ])
        self.assertEqual(statuses["R030"], "closed")

    def test_nodule_with_tighter_radiologist_interval_is_one_loop(self):
        statuses, _ = self._rules([
            _rad("r1", "P", "2026-01-10T09:00:00Z", "CT chest",
                 "7 mm solid nodule in the right upper lobe. Recommend follow-up CT in 3 months."),
        ])
        self.assertEqual(set(statuses), {"R030"})   # not both R003 and R030

    def test_vital_signs_are_not_lab_results(self):
        statuses, events = self._rules([
            {"resourceType": "Observation", "id": "bp", "status": "final",
             "category": [{"coding": [{"code": "vital-signs"}]}],
             "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9"}], "text": "Blood pressure"},
             "interpretation": [{"coding": [{"code": "H"}]}],
             "subject": {"reference": "Patient/P"}, "effectiveDateTime": "2026-03-01T09:00:00Z"}])
        self.assertEqual([e["event_type"] for e in events], ["bp_check"])
        self.assertEqual(statuses, {})

    def test_hbv_condition_and_surveillance_ultrasound(self):
        statuses, events = self._rules([
            {"resourceType": "Condition", "id": "c", "subject": {"reference": "Patient/P"},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "B18.1"}],
                      "text": "Chronic hepatitis B"}, "recordedDate": "2024-05-01"},
            _rad("us", "P", "2025-02-01T09:00:00Z", "US abdomen", "Coarse liver echotexture. No focal lesion."),
        ], when=datetime(2026, 1, 1))
        self.assertEqual(statuses["R027"], "delayed")   # first scan 9 months after diagnosis
        self.assertEqual(statuses["R028"], "open")      # 6-month rescan overdue

    def test_hcv_antibody_and_rna(self):
        statuses, _ = self._rules([
            {"resourceType": "Observation", "id": "ab", "status": "final", "subject": {"reference": "Patient/P"},
             "effectiveDateTime": "2026-03-01T09:00:00Z", "valueCodeableConcept": {"text": "Reactive"},
             "code": {"coding": [{"system": "http://loinc.org", "code": "16128-1"}], "text": "HCV Ab"}},
        ])
        self.assertEqual(statuses, {"R026": "open"})

    def test_psychiatric_admission_and_followup(self):
        statuses, _ = self._rules([
            {"resourceType": "Encounter", "id": "e", "status": "finished", "subject": {"reference": "Patient/P"},
             "class": {"code": "IMP"}, "serviceType": {"text": "Psychiatry"},
             "period": {"start": "2026-03-01T09:00:00Z", "end": "2026-03-10T09:00:00Z"},
             "reasonCode": [{"text": "Major depressive disorder"}]},
            {"resourceType": "Appointment", "id": "a", "status": "fulfilled", "start": "2026-03-14T09:00:00Z",
             "serviceType": [{"text": "Psychiatry outpatient"}],
             "participant": [{"actor": {"reference": "Patient/P"}}]},
        ])
        self.assertEqual(statuses["R029"], "closed")


if __name__ == "__main__":
    unittest.main()
