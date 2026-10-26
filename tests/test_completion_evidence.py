"""Synthetic safety regressions: affirmative completion, real deadlines, task scope."""
import unittest
from datetime import datetime

from src.clinloop_engine.browser_analyse import analyse_bundle
from src.clinloop_engine.clinical_ontology import is_fulfilling_status
from src.clinloop_engine.fhir_ingest import bundle_to_events
from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine.note_reader import find_plans
from src.clinloop_engine.temporal_hypergraph import DynamicTemporalHypergraph

NOW = datetime(2026, 10, 24)
PATIENT = {"resourceType": "Patient", "id": "synthetic-P", "birthDate": "1960-01-01"}
FIT = {"resourceType": "Observation", "id": "synthetic-fit", "status": "final",
       "subject": {"reference": "Patient/synthetic-P"}, "effectiveDateTime": "2026-05-01T09:00:00Z",
       "code": {"text": "Fecal immunochemical test"}, "valueCodeableConcept": {"text": "Positive"}}


def procedure(status="completed"):
    resource = {"resourceType": "Procedure", "id": "synthetic-colonoscopy", "status": status,
                "subject": {"reference": "Patient/synthetic-P"}, "performedDateTime": "2026-06-01T09:00:00Z",
                "code": {"text": "Colonoscopy"}}
    if status is None:
        resource.pop("status")
    return resource


def detect(resources):
    events, warnings = bundle_to_events([PATIENT, FIT] + resources, evaluation_time=NOW)
    detections = ClinLoopDetector(evaluation_time=NOW).process_patient("synthetic", PATIENT["id"], events[PATIENT["id"]])
    return next(d for d in detections if d.rule_id == "R017"), warnings


class TestAffirmativeCompletion(unittest.TestCase):
    def test_invalid_or_missing_procedure_status_never_closes(self):
        for status in (None, "", " ", "status-not-mapped", "unknown", "cancelled", "active", "final", "in-progress", "not-done"):
            with self.subTest(status=status):
                result, _ = detect([procedure(status)])
                self.assertNotEqual(result.loop_status, "closed")
                self.assertIn("completion not established", " ".join(result.evidence_chain))
        result, warnings = detect([procedure()])
        self.assertEqual(result.loop_status, "closed")
        self.assertEqual(warnings, [])

    def test_unknown_status_warning_contains_no_source_payload(self):
        resource = procedure("SENSITIVE_STATUS_SENTINEL")
        resource["id"] = "SENSITIVE_IDENTIFIER_SENTINEL"
        _, warnings = detect([resource])
        self.assertTrue(any("completion requires human review" in warning for warning in warnings))
        self.assertNotIn("SENSITIVE", " ".join(warnings))

    def test_direct_events_cannot_bypass_status_requirement(self):
        trigger = {"event_id": "synthetic-fit", "patient_id": "synthetic-P", "event_type": "lab_result",
                   "timestamp": "2026-05-01T09:00:00", "status": "completed",
                   "details": {"test": "FIT", "result": "positive"}}
        for status in (None, "unmapped", "active", "arrived", "checked-in", "pending", "completed"):
            with self.subTest(status=status):
                followup = {"event_id": "synthetic-col", "patient_id": "synthetic-P", "event_type": "colonoscopy",
                            "timestamp": "2026-06-01T09:00:00", "details": {}}
                if status is not None:
                    followup["status"] = status
                graph = DynamicTemporalHypergraph(evaluation_time=NOW)
                graph.build_from_patient_trajectory([trigger, followup])
                loop = next(e for e in graph.get_all_loops() if e.obligation_rule.rule_id == "R017")
                self.assertEqual(loop.status == "closed", status == "completed")
        self.assertFalse(is_fulfilling_status(None))

    def test_mapping_warning_does_not_echo_identifiers_or_invalid_dates(self):
        resource = procedure()
        resource["id"] = "SENSITIVE_IDENTIFIER_SENTINEL"
        resource["performedDateTime"] = "SENSITIVE_DATE_SENTINEL"
        _, warnings = bundle_to_events([PATIENT, resource])
        self.assertTrue(any("unreadable date" in warning for warning in warnings))
        self.assertNotIn("SENSITIVE", " ".join(warnings))

    def test_check_in_does_not_mean_attended_procedure(self):
        for status in ("booked", "arrived", "checked-in", "fulfilled"):
            with self.subTest(status=status):
                appointment = {"resourceType": "Appointment", "id": "synthetic-visit", "status": status,
                               "description": "Colonoscopy", "start": "2026-06-01T09:00:00Z",
                               "participant": [{"actor": {"reference": "Patient/synthetic-P"}}]}
                result, _ = detect([appointment])
                self.assertEqual(result.loop_status == "closed", status == "fulfilled")

    def test_order_is_not_a_performed_endoscopic_ultrasound(self):
        report = {"resourceType": "DiagnosticReport", "id": "synthetic-pancreas", "status": "final",
                  "subject": {"reference": "Patient/synthetic-P"}, "effectiveDateTime": "2026-05-01T09:00:00Z",
                  "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": "MRI pancreas"},
                  "conclusion": "Pancreatic cyst 3 cm with mural nodule."}
        order = {"resourceType": "ServiceRequest", "id": "synthetic-order", "status": "active",
                 "intent": "order", "subject": {"reference": "Patient/synthetic-P"},
                 "authoredOn": "2026-05-02T09:00:00Z", "code": {"text": "Endoscopic ultrasound"}}
        for status in ("active", "completed"):
            with self.subTest(status=status):
                order["status"] = status
                events, warnings = bundle_to_events([PATIENT, report, order])
                self.assertEqual(warnings, [])
                self.assertFalse(any(e["event_type"] == "endoscopic_ultrasound" for e in events[PATIENT["id"]]))
                rows = ClinLoopDetector(evaluation_time=NOW).process_patient("synthetic", PATIENT["id"], events[PATIENT["id"]])
                self.assertNotEqual(next(d for d in rows if d.rule_id == "R042").loop_status, "closed")

    def test_persistent_registry_reopens_when_completion_becomes_unknown(self):
        store = LoopStore()
        result, _ = detect([procedure()])
        store.upsert_detections([result])
        self.assertEqual(store.worklist(), [])
        result, _ = detect([procedure(None)])
        store.upsert_detections([result])
        self.assertEqual(len(store.worklist()), 1)
        self.assertEqual(store.worklist()[0]["workflow_state"], "new")
        self.assertTrue(store.verify_audit_chain())

    def test_closed_task_does_not_claim_all_care_completed(self):
        result, _ = detect([procedure()])
        self.assertIn("overall care completion is not established", result.missing_step)
        self.assertTrue(any("Completion scope" in line for line in result.basis))
        self.assertTrue(any("완료 범위" in line for line in result.basis_ko))


class TestClinicalDeadlinePreservation(unittest.TestCase):
    def report(self, when, text, all_rows=False):
        resource = {"resourceType": "DiagnosticReport", "id": "synthetic-report", "status": "final",
                    "subject": {"reference": "Patient/synthetic-P"}, "effectiveDateTime": when,
                    "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": "CT chest"}, "conclusion": text}
        bundle = {"resourceType": "Bundle", "entry": [{"resource": r} for r in [PATIENT, resource]]}
        rows = analyse_bundle(bundle, when.replace("Z", ""))["detections"]
        return rows if all_rows else rows[0]

    def test_four_weeks_stays_28_days_in_browser_pipeline(self):
        result = self.report("2026-01-10T09:00:00Z", "Study limited by motion. Repeat CT chest in 4 weeks is recommended.")
        self.assertEqual(result["deadline"], "2026-02-07T09:00:00")
        self.assertTrue(any("no scheduling grace" in line for line in result["basis"]))
        self.assertTrue(any("추가 유예 기간을 더하지 않음" in line for line in result["basis_ko"]))
        self.assertFalse(any("Deadline source:" in line for line in result["basis_ko"]))

    def test_calendar_months_preserve_month_ends_and_leap_years(self):
        for start, interval, due in (("2026-01-31", "1 month", "2026-02-28"),
                                     ("2024-02-29", "1 year", "2025-02-28"),
                                     ("2026-01-10", "3 months", "2026-04-10")):
            with self.subTest(start=start, interval=interval):
                result = self.report(start + "T09:00:00Z", f"Repeat CT chest in {interval} is recommended.")
                self.assertEqual(result["deadline"], due + "T09:00:00")

    def test_note_plans_keep_explicit_interval(self):
        plans = find_plans("Plan: Repeat potassium in 1 week. Repeat CT chest in 4 weeks. Follow-up in clinic in 6 weeks.")["plans"]
        tracked = [p for p in plans if p["tracked"]]
        self.assertEqual(len(tracked), 3)
        for plan in tracked:
            self.assertEqual(plan["due_days"], plan["interval_days"])

    def test_calendar_conversion_does_not_duplicate_nodule_and_biopsy_alternatives(self):
        rows = self.report("2026-02-11T09:00:00Z",
                           "10 mm solid pulmonary nodule in the right upper lobe. "
                           "Recommend CT chest in 3 months or biopsy.", all_rows=True)
        self.assertEqual([row["rule_id"] for row in rows], ["R003"])
        self.assertEqual(rows[0]["deadline"], "2026-05-11T09:00:00")
