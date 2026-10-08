"""
test_governance.py — Specialist rule sign-off, critical-finding list approval, shadow mode
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {
    "admin": "test-admin-token-0123456789",
    "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234",
    "viewer": "test-viewer-token-0123456789",
}
os.environ.setdefault("CLINLOOP_API_TOKENS", ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items()))

from src.clinloop_engine import governance  # noqa: E402
from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore, WorkflowError  # noqa: E402

try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:
    HAVE_API = False

RULE = next(r for r in OBLIGATION_RULES if r.rule_id == "R003")


def _h(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


class TestRuleSignoff(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()

    def test_pending_until_approved(self):
        self.assertEqual(governance.all_rule_statuses(self.store)["R003"]["status"], "pending")
        fp = governance.rule_fingerprint(RULE)
        self.store.add_rule_review("R003", fp, "approve", "dr.kim", "clinician", "Thoracic radiology")
        status = governance.all_rule_statuses(self.store)["R003"]
        self.assertEqual((status["status"], status["approvers"]), ("approved", ["dr.kim"]))

    def test_two_approvals_policy(self):
        fp = governance.rule_fingerprint(RULE)
        with mock.patch.dict(os.environ, {"CLINLOOP_SIGNOFF_APPROVALS": "2"}):
            self.store.add_rule_review("R003", fp, "approve", "dr.kim", "clinician", "Radiology")
            self.store.add_rule_review("R003", fp, "approve", "dr.kim", "clinician", "Radiology")   # same person twice
            self.assertEqual(governance.all_rule_statuses(self.store)["R003"]["status"], "pending")
            self.store.add_rule_review("R003", fp, "approve", "dr.park", "clinician", "Pulmonology")
            self.assertEqual(governance.all_rule_statuses(self.store)["R003"]["status"], "approved")

    def test_rejection_and_change_request_block(self):
        fp = governance.rule_fingerprint(RULE)
        self.store.add_rule_review("R003", fp, "approve", "dr.kim", "clinician", "Radiology")
        self.store.add_rule_review("R003", fp, "request_changes", "dr.park", "clinician", "Pulmonology",
                                   "Use 6-12 months lower bound for high-risk patients")
        self.assertEqual(governance.all_rule_statuses(self.store)["R003"]["status"], "changes_requested")

    def test_signoff_is_bound_to_the_rule_version(self):
        self.store.add_rule_review("R003", "old-fingerprint", "approve", "dr.kim", "clinician", "Radiology")
        self.assertEqual(governance.all_rule_statuses(self.store)["R003"]["status"], "stale")

    def test_fingerprint_changes_with_the_definition(self):
        import dataclasses
        changed = dataclasses.replace(RULE, deadline_days=RULE.deadline_days + 1)
        self.assertNotEqual(governance.rule_fingerprint(RULE), governance.rule_fingerprint(changed))

    def test_rejection_needs_a_reason_and_specialty_is_required(self):
        fp = governance.rule_fingerprint(RULE)
        with self.assertRaises(WorkflowError):
            self.store.add_rule_review("R003", fp, "reject", "dr.kim", "clinician", "Radiology", "")
        with self.assertRaises(WorkflowError):
            self.store.add_rule_review("R003", fp, "approve", "dr.kim", "clinician", "  ")

    def test_reviews_are_in_the_audit_chain(self):
        fp = governance.rule_fingerprint(RULE)
        self.store.add_rule_review("R003", fp, "approve", "dr.kim", "clinician", "Radiology")
        self.assertTrue(any(e["action"] == "rule_review:approve" for e in self.store.audit_trail()))
        self.assertTrue(self.store.verify_audit_chain())


class TestCriticalListApproval(unittest.TestCase):

    def test_approval_is_bound_to_content(self):
        store = LoopStore()
        self.assertEqual(governance.critical_list_status(store)["status"], "not_approved")
        current = governance.critical_list_status(store)["content_hash"]
        store.add_config_approval(governance.CRITICAL_FINDINGS_KIND, current, "dr.lee", "clinician",
                                  "Chair, Department of Radiology")
        self.assertEqual(governance.critical_list_status(store)["status"], "approved")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"name": "edited", "findings": [{"id": "pe", "category": 1, "window_minutes": 30,
                                                       "label": {"en": "PE"}, "patterns": ["pulmonary embol\\w*"]}]}, f)
        try:
            with mock.patch.dict(os.environ, {"CLINLOOP_CRITICAL_FINDINGS": f.name}):
                self.assertEqual(governance.critical_list_status(store)["status"], "changed_since_approval")
        finally:
            os.unlink(f.name)


@unittest.skipUnless(HAVE_API, "API dependencies not installed")
class TestGovernanceAPI(unittest.TestCase):

    def setUp(self):
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        with open(os.path.join(ROOT, "data", "radiology_test_bundle.json"), encoding="utf-8") as f:
            bundle = json.load(f)
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-10-08T00:00:00", json=bundle, headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)

    def _review(self, rule_id, role="clinician", fingerprint=None, decision="approve"):
        rules = {r["rule_id"]: r for r in self.client.get("/api/v1/governance/rules").json()["rules"]}
        return self.client.post(f"/api/v1/governance/rules/{rule_id}/review", headers=_h(role), json={
            "decision": decision, "specialty": "Radiology",
            "fingerprint": fingerprint or rules[rule_id]["fingerprint"], "note": "Reviewed against guideline"})

    def test_status_is_public_and_review_needs_a_clinician(self):
        self.assertEqual(self.client.get("/api/v1/governance/summary").status_code, 200)
        self.assertEqual(self._review("R003", role="navigator").status_code, 403)
        r = self._review("R003")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "approved")
        rules = {x["rule_id"]: x for x in self.client.get("/api/v1/rules").json()["rules"]}
        self.assertEqual(rules["R003"]["signoff"]["status"], "approved")

    def test_reviewing_an_old_version_is_refused(self):
        self.assertEqual(self._review("R003", fingerprint="0" * 64).status_code, 409)

    def test_worklist_shows_signoff_and_shadow_mode_hides_unapproved(self):
        wl = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()
        self.assertGreater(wl["count"], 0)
        self.assertEqual(wl["shadow_count"], 0)
        self.assertTrue(all(loop["rule_signoff"] == "pending" for loop in wl["loops"]))
        with mock.patch.dict(os.environ, {"CLINLOOP_ENFORCE_SIGNOFF": "1"}):
            wl = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()
            self.assertEqual(wl["count"], 0)
            self.assertGreater(wl["shadow_count"], 0)
            self._review("R003")
            wl = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()
            self.assertEqual({loop["rule_id"] for loop in wl["loops"]}, {"R003"})
            # R035 also needs the hospital's critical-finding list approved
            self._review("R035")
            wl = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()
            self.assertNotIn("R035", {loop["rule_id"] for loop in wl["loops"]})
            crit = self.client.get("/api/v1/governance/critical-findings").json()
            r = self.client.post("/api/v1/governance/critical-findings/approve", headers=_h("clinician"),
                                 json={"title": "Chair of Radiology", "content_hash": crit["content_hash"]})
            self.assertEqual(r.json()["status"], "approved")
            wl = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()
            self.assertIn("R035", {loop["rule_id"] for loop in wl["loops"]})

    def test_shadow_loops_do_not_escalate(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_ENFORCE_SIGNOFF": "1"}):
            r = self.client.post("/api/v1/watchdog/escalate", headers=_h("admin"))
            self.assertEqual(r.json()["escalated"], [])

    def test_critical_list_approval_bound_to_hash(self):
        r = self.client.post("/api/v1/governance/critical-findings/approve", headers=_h("clinician"),
                             json={"title": "Chair of Radiology", "content_hash": "0" * 64})
        self.assertEqual(r.status_code, 409)


if __name__ == "__main__":
    unittest.main()
