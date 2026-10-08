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


if __name__ == "__main__":
    unittest.main()
