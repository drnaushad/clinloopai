"""
test_second_reader_silent.py — The model second reader in the clinical (core) edition: silent only

The reader may run in the clinical edition to measure what it would add, but its suggestions go to the
quality team's log and never into the patient record, the worklist or any loop. Synthetic data only.
"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, ".."))

TOKENS = {"admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
          "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

from test_second_reader import NOW, PATIENT, UNUSUAL, FakeModel, loops, report  # noqa: E402

from src.clinloop_engine import second_reader as sr  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore, WorkflowError  # noqa: E402

MRI = [{"category": "imaging_followup", "quote": "Please obtain a dedicated pelvic MRI", "reason": "MRI recommended"}]


def _h(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


class TestModes(unittest.TestCase):

    def test_clinical_edition_never_runs_live(self):
        for value, core_mode, research_mode in (("", "off", "off"), ("silent", "silent", "silent"),
                                                ("1", "silent", "live"), ("on", "silent", "live")):
            with mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": value, "CLINLOOP_PROFILE": "core"}):
                self.assertEqual(sr.mode(), core_mode, value)
                self.assertFalse(sr.enabled())                       # never opens R058 in the clinical edition
            with mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": value, "CLINLOOP_PROFILE": "research"}):
                self.assertEqual(sr.mode(), research_mode, value)
        with mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": "1"}):
            os.environ.pop("CLINLOOP_PROFILE", None)
            self.assertEqual(sr.mode(), "silent")                    # the default profile is the clinical one


class TestSilentReading(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        self.env = mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": "1", "CLINLOOP_PROFILE": "core"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_suggestion_goes_to_the_quality_log_not_the_record(self):
        rep = report(UNUSUAL)
        returned = sr.second_read_patient(self.store, "P", [PATIENT, rep], model=FakeModel(MRI), now=NOW)
        self.assertEqual(returned, [])                               # nothing joins the patient's record
        self.assertNotIn("R058", loops([PATIENT, rep]))
        self.assertEqual(self.store.worklist(include_inactive=True), [])
        rows = self.store.second_reader_suggestions()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["category"], rows[0]["quote"], rows[0]["report_ref"]),
                         ("imaging_followup", "Please obtain a dedicated pelvic MRI at the earliest convenience.", "DiagnosticReport/r1"))
        self.assertIn("clinical interpretation requires clinician review", rows[0]["reason"])
        self.assertEqual(self.store.second_read("P|r1")["flags"], 1)
        # Read once: the same report is not sent again, and the suggestion is not filed twice
        model = FakeModel(MRI)
        sr.second_read_patient(self.store, "P", [PATIENT, rep], model=model, now=NOW)
        self.assertEqual((model.prompts, len(self.store.second_reader_suggestions())), ([], 1))
        audit = [e["action"] for e in self.store.audit_trail()]
        self.assertIn("second_reader_suggestion", audit)

    def test_a_caller_cannot_force_live_flags_in_the_clinical_edition(self):
        flags = sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL)], model=FakeModel(MRI), now=NOW,
                                       silent=False)
        self.assertEqual(flags, [])
        self.assertEqual(len(self.store.second_reader_suggestions()), 1)

    def test_invented_quote_and_tracked_item_are_not_filed(self):
        rep = report("IMPRESSION: 9 mm solid RUL nodule. Recommend follow-up chest CT in 3 months.", title="CT chest")
        model = FakeModel([{"category": "imaging_followup", "quote": "Recommend follow-up chest CT in 3 months",
                            "reason": "tracked already"},
                           {"category": "biopsy_or_workup", "quote": "Biopsy the right upper lobe mass", "reason": "invented"}])
        sr.second_read_patient(self.store, "P", [PATIENT, rep], model=model, now=NOW)
        self.assertEqual(self.store.second_reader_suggestions(), [])

    def test_sync_runs_silently_and_the_worklist_has_only_the_rules(self):
        from src.clinloop_engine import fhir_sync
        rep = report(UNUSUAL)
        with mock.patch.object(sr, "local_model", return_value=FakeModel(MRI)), \
                mock.patch.object(fhir_sync, "patient_record", return_value=([PATIENT, rep], [])):
            client = mock.Mock(spec=["changed_patients"])
            client.changed_patients.return_value = ({"P"}, None)
            fhir_sync.sync_once(self.store, client, source="test", now=NOW)
        self.assertEqual(len(self.store.second_reader_suggestions()), 1)
        self.assertNotIn("R058", {l["rule_id"] for l in self.store.worklist(include_inactive=True)})


class TestQualityReview(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        with mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": "silent"}):
            sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL)], model=FakeModel(MRI), now=NOW)
        self.sid = self.store.second_reader_suggestions()[0]["id"]

    def test_urgent_real_miss_needs_a_safety_referral(self):
        with self.assertRaises(WorkflowError):
            self.store.review_second_reader_suggestion(self.sid, "real_miss", "dr.kim", "clinician", urgent=True)
        row = self.store.review_second_reader_suggestion(self.sid, "real_miss", "dr.kim", "clinician", urgent=True,
                                                         safety_referral="Told Dr Lee (gynaecology) by phone 10:05")
        self.assertEqual((row["verdict"], row["urgent"]), ("real_miss", 1))
        actions = [e["action"] for e in self.store.audit_trail()]
        self.assertTrue(self.store.verify_audit_chain())
        self.assertIn("second_reader_review", actions)
        self.assertIn("safety_referral", actions)
        with self.assertRaises(WorkflowError):
            self.store.review_second_reader_suggestion(self.sid, "maybe", "dr.kim", "clinician")

    def test_summary_counts_and_precision(self):
        self.store.review_second_reader_suggestion(self.sid, "real_miss", "dr.kim", "clinician")
        s = sr.silent_summary(self.store)
        c = s["categories"]["imaging_followup"]
        self.assertEqual((c["n"], c["reviewed"], c["real_miss"], c["precision"]), (1, 1, 1, 1.0))
        self.assertEqual(s["total"]["precision_ci95"], [0.207, 1.0])     # one review proves little
        self.assertFalse(s["reaches_clinical_care"])
        self.assertIsNone(s["categories"]["critical_finding"]["precision"])

    def test_endpoints_counts_for_all_quotes_for_the_team_verdicts_by_clinicians(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine import clinical_api
        from src.clinloop_engine.api import app
        clinical_api.set_store(self.store)
        client = TestClient(app)
        summary = client.get("/api/v1/quality/second-reader", headers=_h("viewer")).json()
        self.assertEqual(summary["total"]["n"], 1)
        self.assertNotIn("pelvic", str(summary))                         # counts only
        self.assertEqual(client.get("/api/v1/quality/second-reader/suggestions", headers=_h("viewer")).status_code, 403)
        listed = client.get("/api/v1/quality/second-reader/suggestions", headers=_h("navigator")).json()
        self.assertEqual(listed["items"][0]["label"]["ko"], "추적 영상검사")
        url = f"/api/v1/quality/second-reader/suggestions/{self.sid}/review"
        self.assertEqual(client.post(url, headers=_h("navigator"), json={"verdict": "not_needed"}).status_code, 403)
        r = client.post(url, headers=_h("clinician"), json={"verdict": "real_miss", "urgent": True})
        self.assertEqual(r.status_code, 409)
        r = client.post(url, headers=_h("clinician"), json={"verdict": "already_handled", "note": "ordered in clinic"})
        self.assertEqual((r.status_code, r.json()["verdict"]), (200, "already_handled"))
        self.assertEqual(client.post(f"/api/v1/quality/second-reader/suggestions/{'0' * 32}/review",
                                     headers=_h("clinician"), json={"verdict": "not_needed"}).status_code, 404)
        reads = [e for e in self.store.access_log() if e["action"] == "view_second_reader_suggestions"]
        self.assertTrue(reads)


if __name__ == "__main__":
    unittest.main()
