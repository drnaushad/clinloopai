"""
test_profile.py — The core profile locks every research feature off, whatever its own setting says

Synthetic resources only (the fixtures of test_imaging, test_ai_triage and test_second_reader).
"""

import os
import sys
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from src.clinloop_engine import ai_review, ct_organs, governance, imaging_scanner, note_reader, profile  # noqa: E402
from src.clinloop_engine import second_reader as sr  # noqa: E402
from src.clinloop_engine.imaging_ai import registered_models  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore  # noqa: E402

TOKENS = {"admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
          "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

ALL_ON = {"CLINLOOP_IMAGING_MODELS": "txrv,vlm,totalseg", "CLINLOOP_IMAGE_SCAN": "1",
          "CLINLOOP_IMAGING_RESEARCH_AI": "1", "CLINLOOP_SECOND_READER": "1", "CLINLOOP_VLM_URL": "http://10.0.0.5:11434"}


class TestProfileSwitch(unittest.TestCase):

    def test_default_is_research_and_changes_nothing(self):
        with mock.patch.dict(os.environ, ALL_ON):
            os.environ.pop("CLINLOOP_PROFILE", None)
            self.assertEqual(profile.name(), "research")
            self.assertTrue(imaging_scanner.enabled() and sr.enabled() and ai_review.research_ai_enabled())
            self.assertTrue(ct_organs.enabled())
            self.assertEqual(len(registered_models()), 2)
            self.assertEqual(profile.excluded_rules(), frozenset())

    def test_core_locks_every_research_feature_off(self):
        with mock.patch.dict(os.environ, {**ALL_ON, "CLINLOOP_PROFILE": "core"}):
            self.assertFalse(imaging_scanner.enabled())
            self.assertFalse(sr.enabled())
            self.assertFalse(ai_review.research_ai_enabled())
            self.assertFalse(ct_organs.enabled())
            self.assertEqual(registered_models(), [])
            out = note_reader.llm_suggestions("Plan: repeat CT chest in 3 months.", [])
            self.assertFalse(out["available"])
            self.assertIn("core profile", out["reason"])
            self.assertEqual(profile.describe()["excluded_rules"], ["R047", "R057", "R058"])
            self.assertEqual(sorted(profile.describe()["locked_features"]), sorted(profile.RESEARCH_FEATURES))
            from src.clinloop_engine.rule_check import check_rules
            check = check_rules()
            self.assertEqual(check["excluded_by_profile"], ["R047", "R057", "R058"])
            self.assertEqual(check["rules"], 62)

    def test_a_typo_never_widens_the_scope(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "reserach"}):
            self.assertEqual(profile.name(), "core")

    def test_profile_is_part_of_the_rule_set_version_and_summary(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "research"}):
            research = governance.ruleset_version()
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core"}):
            core = governance.ruleset_version()
            self.assertEqual(governance.summary(LoopStore())["profile"]["profile"], "core")
        self.assertNotEqual(research, core)


class TestCoreProfileRules(unittest.TestCase):
    """R047, R057 and R058 can only be opened by research features: the core profile never opens them."""

    def test_imaging_ai_rules_are_not_opened(self):
        from test_ai_triage import TestCriticalFindingOnUnreadStudy as T
        t = T()
        t.setUp()
        when = datetime(2026, 1, 10, 12, 0)
        resources = [t.ai(), t.report("No acute intracranial abnormality.")]
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "research"}):
            self.assertTrue({"R047", "R057"} <= set(t.run_at(resources, when)[0]))
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core"}):
            statuses = t.run_at(resources, when)[0]
        self.assertFalse({"R047", "R057"} & set(statuses))
        bleed = [t.ai(), t.report("Acute 1.5 cm right parietal intraparenchymal hemorrhage.")]
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core"}):
            statuses = t.run_at(bleed, when)[0]
        self.assertEqual(set(statuses), {"R035"})   # the report's own critical result is still tracked

    def test_second_reader_flags_are_not_opened(self):
        from test_second_reader import NOW, PATIENT, UNUSUAL, FakeModel, loops, report
        rep = report(UNUSUAL)
        model = FakeModel([{"category": "imaging_followup", "quote": "Please obtain a dedicated pelvic MRI",
                            "reason": "MRI recommended"}])
        flags = sr.second_read_patient(LoopStore(), "P", [PATIENT, rep], model=model, now=NOW)
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core"}):
            self.assertNotIn("R058", loops([PATIENT, rep] + flags))
        self.assertIn("R058", loops([PATIENT, rep] + flags))


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestCoreProfileAPI(unittest.TestCase):

    def setUp(self):
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        self.h = {"Authorization": f"Bearer {TOKENS['admin']}"}

    def test_research_endpoints_refuse_in_core(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core"}):
            r = self.client.post("/api/v1/imaging/ai-results", headers=self.h,
                                 json={"patient_id": "SYN-1", "bundle": {"resourceType": "Bundle", "entry": []}})
            self.assertEqual(r.status_code, 409, r.text)
            self.assertIn("intended use", r.json()["detail"])
            r = self.client.post("/api/v1/reports/second-read/preview", headers=self.h,
                                 json={"text": UNUSUAL_TEXT, "title": "Pelvis US", "category": "RAD"})
            self.assertEqual(r.status_code, 409, r.text)
            ch = {"Authorization": f"Bearer {TOKENS['clinician']}"}
            r = self.client.post("/api/v1/local-llm/generate", headers=ch,
                                 json={"task": "differential_diagnosis", "clinical_context": "synthetic"})
            self.assertEqual(r.status_code, 409, r.text)
            r = self.client.post("/api/v1/agent/evidence-synthesis", headers=ch,
                                 json={"clinical_context": "synthetic lung nodule", "task": "summary", "lang": "en"})
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(self.client.get("/api/v1/governance/summary").json()["profile"]["profile"], "core")


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestDocumentationAudit(unittest.TestCase):
    """Core profile: R022 and R035 leave the worklist, cards and escalation, and become a next-day audit."""

    def setUp(self):
        from test_clinloop import _make_hyperkalemia_events
        from src.clinloop_engine.loop_detector import ClinLoopDetector
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.client = TestClient(app)
        note = {"event_type": "critical_value_notification", "details": {}, "status": "completed"}
        cases = {"P-NONE": None, "P-LATE": "2026-09-01T14:00:00", "P-ONTIME": "2026-09-01T12:00:00"}
        for pid, when in cases.items():
            events = _make_hyperkalemia_events(pid)
            if when:
                events.append({**note, "event_id": f"n-{pid}", "patient_id": pid, "timestamp": when})
            self.store.upsert_detections(ClinLoopDetector(evaluation_time=datetime(2026, 9, 2)).process_patient("t", pid, events))
        self.h = {"Authorization": f"Bearer {TOKENS['admin']}"}

    def rules_on_worklist(self):
        return {l["rule_id"] for l in self.client.get("/api/v1/worklist", headers=self.h).json()["loops"]}

    def test_research_profile_keeps_the_live_alert(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "research", "CLINLOOP_ENFORCE_SIGNOFF": "0"}):
            self.assertIn("R022", self.rules_on_worklist())

    def test_core_profile_moves_it_to_the_next_day_audit(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core", "CLINLOOP_ENFORCE_SIGNOFF": "0"}):
            on_list = self.rules_on_worklist()
            self.assertNotIn("R022", on_list)
            self.assertIn("R001", on_list)                    # the abnormal result itself is still followed up
            self.assertNotIn("R022", governance.live_rule_ids(self.store))
            escalated = self.store.escalate_overdue(now=datetime(2026, 9, 5), rule_ids=governance.live_rule_ids(self.store))
            self.assertFalse([e for e in escalated if "|R022|" in e["loop_key"]])
            audit = self.client.get("/api/v1/quality/documentation-audit", headers=self.h).json()
        self.assertTrue(audit["replaces_live_alert"])
        by_patient = {i["patient_id"]: i["result"] for i in audit["items"] if i["rule_id"] == "R022"}
        self.assertEqual(by_patient, {"P-NONE": "not_documented", "P-LATE": "documented_late",
                                      "P-ONTIME": "documented_on_time"})
        self.assertEqual(audit["items"][0]["result"], "not_documented")     # missing documentation first
        viewer = {"Authorization": f"Bearer {TOKENS['viewer']}"}
        self.assertEqual(self.client.get("/api/v1/quality/documentation-audit", headers=viewer).status_code, 403)


class TestBioMCPOptional(unittest.TestCase):
    """BioMCP is a reviewer aid: off in the core profile unless the hospital turns it on."""

    def test_switch(self):
        from src.clinloop_engine import biomcp_client as b
        cases = [("core", "", False), ("core", "1", True), ("core", "0", False),
                 ("research", "", True), ("research", "0", False), ("research", "1", True)]
        for prof, setting, expected in cases:
            with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": prof, "CLINLOOP_BIOMCP": setting}):
                self.assertEqual(b.enabled(), expected, (prof, setting))

    def test_off_means_nothing_is_started_and_calls_are_refused(self):
        from src.clinloop_engine import biomcp_client as b
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core", "CLINLOOP_BIOMCP": ""}), \
                mock.patch.object(b, "_with_session", side_effect=AssertionError("must not connect")):
            s = b.status(force=True)
            self.assertEqual(s["status"], "disabled")
            self.assertIn("CLINLOOP_BIOMCP=1", s["reason"])
            with self.assertRaises(b.BioMCPDisabled):
                b.call_tool("article_searcher", {"keywords": ["Fleischner"]})

    @unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
    def test_api_says_off_not_unreachable(self):
        client = TestClient(app)
        with mock.patch.dict(os.environ, {"CLINLOOP_PROFILE": "core", "CLINLOOP_BIOMCP": ""}):
            r = client.post("/api/v1/biomcp/call", json={"tool": "article_searcher", "arguments": {"keywords": ["x"]}},
                            headers={"Authorization": f"Bearer {TOKENS['clinician']}"})
            self.assertEqual(r.status_code, 409)
            self.assertIn("core profile", r.json()["detail"])
            self.assertEqual(client.get("/api/v1/evidence/R001?source=biomcp").status_code, 409)


UNUSUAL_TEXT = "IMPRESSION: 4.8 cm complex right adnexal cyst. Please obtain a dedicated pelvic MRI."

if __name__ == "__main__":
    unittest.main()
