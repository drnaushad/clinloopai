"""
test_loop_store.py — Persistent loop registry, workflow, escalation, audit
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.loop_store import LoopStore, WorkflowError

EVAL = datetime(2026, 9, 1)


def _events(with_colonoscopy=False, colonoscopy_status="completed"):
    events = [{"event_id": "fit-1", "patient_id": "P1", "event_type": "lab_result",
               "timestamp": "2026-05-01T09:00:00", "details": {"test": "FIT", "result": "positive"},
               "status": "completed"}]
    if with_colonoscopy:
        events.append({"event_id": "col-1", "patient_id": "P1", "event_type": "colonoscopy",
                       "timestamp": "2026-06-01T09:00:00", "details": {}, "status": colonoscopy_status})
    return events


def _ingest(store, events, now=EVAL):
    dets = ClinLoopDetector(evaluation_time=now).process_patient("t", "P1", events)
    return store.upsert_detections(dets, strata={"P1": {"insurance": "medical_aid"}})


class TestLoopStoreWorkflow(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        _ingest(self.store, _events())
        self.key = self.store.worklist()[0]["loop_key"]

    def test_open_loop_appears_on_worklist(self):
        loop = self.store.get(self.key)
        self.assertEqual((loop["rule_id"], loop["workflow_state"]), ("R017", "new"))
        self.assertEqual(self.key, "P1|R017|fit-1")

    def test_rerun_is_idempotent(self):
        counts = _ingest(self.store, _events())
        self.assertEqual(counts["new"], 0)
        self.assertEqual(len(self.store.worklist()), 1)

    def test_record_shows_followup_resolves_loop(self):
        counts = _ingest(self.store, _events(with_colonoscopy=True))
        self.assertEqual(counts["resolved_by_engine"], 1)
        self.assertEqual(self.store.worklist(), [])

    def test_cancelled_followup_reopens_resolved_loop(self):
        _ingest(self.store, _events(with_colonoscopy=True))
        _ingest(self.store, _events(with_colonoscopy=True, colonoscopy_status="cancelled"))
        self.assertEqual(self.store.get(self.key)["workflow_state"], "new")

    def test_close_requires_evidence(self):
        with self.assertRaises(WorkflowError):
            self.store.close(self.key, "dr.lee", evidence="")
        loop = self.store.close(self.key, "dr.lee", evidence="Colonoscopy booked: order #C-2231, 2026-09-10")
        self.assertEqual(loop["workflow_state"], "closed_by_clinician")

    def test_defer_requires_coded_reason_and_note(self):
        with self.assertRaises(WorkflowError):
            self.store.defer(self.key, "dr.lee", reason_code="busy")
        with self.assertRaises(WorkflowError):
            self.store.defer(self.key, "dr.lee", reason_code="not_clinically_indicated")
        loop = self.store.defer(self.key, "dr.lee", reason_code="patient_declined",
                                note="Informed refusal documented")
        self.assertEqual(loop["workflow_state"], "deferred")
        self.assertEqual(self.store.worklist(), [])

    def test_expired_deferral_resurfaces(self):
        self.store.defer(self.key, "dr.lee", reason_code="completed_elsewhere",
                         until="2026-09-15T00:00:00")
        self.assertEqual(self.store.worklist(now=datetime(2026, 9, 10)), [])
        resurfaced = self.store.worklist(now=datetime(2026, 9, 20))
        self.assertTrue(resurfaced[0]["deferral_expired"])

    def test_unacknowledged_overdue_loop_escalates_up_the_chain(self):
        first = self.store.escalate_overdue(now=EVAL)
        self.assertEqual(first[0]["to"], "department_lead")
        self.assertEqual(self.store.escalate_overdue(now=EVAL + timedelta(hours=1)), [])
        second = self.store.escalate_overdue(now=EVAL + timedelta(hours=25))
        self.assertEqual(second[0]["to"], "patient_safety_officer")

    def test_acknowledged_loop_does_not_escalate(self):
        self.store.acknowledge(self.key, "nurse.park", role="navigator")
        self.assertEqual(self.store.escalate_overdue(now=EVAL), [])

    def test_audit_chain_detects_tampering(self):
        self.store.acknowledge(self.key, "nurse.park", role="navigator")
        self.store.close(self.key, "dr.lee", evidence="Colonoscopy done at partner hospital 2026-08-30")
        self.assertTrue(self.store.verify_audit_chain())
        actions = [e["action"] for e in self.store.audit_trail(self.key)]
        self.assertEqual(actions, ["loop_opened", "acknowledge", "close"])
        self.store._db.execute("UPDATE audit_log SET actor='someone_else' WHERE action='close'")
        self.assertFalse(self.store.verify_audit_chain())

    def test_open_loop_rate_and_strata(self):
        rate = self.store.open_loop_rate(now=EVAL)
        self.assertEqual(rate["groups"]["all"], {"eligible": 1, "missed": 1, "rate_per_1000": 1000.0})
        by_ins = self.store.open_loop_rate(now=EVAL, stratify_by="insurance")
        self.assertIn("medical_aid", by_ins["groups"])

    def test_persists_to_disk(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "loops.db")
            _ingest(LoopStore(path), _events())
            self.assertEqual(len(LoopStore(path).worklist()), 1)


if __name__ == "__main__":
    unittest.main()
