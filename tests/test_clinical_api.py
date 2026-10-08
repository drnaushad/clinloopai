"""
test_clinical_api.py — Pilot API end to end: auth, FHIR ingest, workflow, metrics

Skipped when the optional API dependencies (fastapi, httpx) are not installed.
"""

import json
import os
import sys
import unittest
from urllib.parse import quote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {
    "admin": "test-admin-token-0123456789",
    "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234",
    "viewer": "test-viewer-token-0123456789",
}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    from src.clinloop_engine.loop_store import LoopStore
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


def _h(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestClinicalAPI(unittest.TestCase):

    def setUp(self):
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
            self.bundle = json.load(f)

    def _ingest(self):
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00",
                             json=self.bundle, headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_patient_data_requires_a_token(self):
        self.assertEqual(self.client.get("/api/v1/worklist").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/worklist",
                                         headers={"Authorization": "Bearer wrong"}).status_code, 401)

    def test_rule_library_is_public(self):
        from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES
        rules = self.client.get("/api/v1/rules").json()["rules"]
        self.assertEqual(len(rules), len(OBLIGATION_RULES))
        self.assertEqual(next(r for r in rules if r["rule_id"] == "R022")["deadline"], "1 hour")

    def test_only_admin_can_ingest(self):
        r = self.client.post("/api/v1/fhir/ingest", json=self.bundle, headers=_h("clinician"))
        self.assertEqual(r.status_code, 403)

    def test_ingest_builds_ranked_worklist(self):
        summary = self._ingest()
        self.assertEqual(summary["patients"], 7)
        self.assertEqual(summary["warnings"], [])
        loops = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()["loops"]
        rules = {l["rule_id"] for l in loops}
        self.assertTrue({"R017", "R003", "R009", "R006"} <= rules)
        self.assertEqual(loops[0]["severity"], "critical")   # post-discharge culture first

    def test_workflow_roles_and_audit(self):
        self._ingest()
        loops = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()["loops"]
        key = next(l["loop_key"] for l in loops if l["rule_id"] == "R017")
        path = f"/api/v1/loops/{quote(key, safe='')}"

        self.assertEqual(self.client.post(path + "/acknowledge", headers=_h("viewer")).status_code, 403)
        self.assertEqual(self.client.post(path + "/acknowledge", headers=_h("navigator")).status_code, 200)

        # A navigator may not make a clinical deferral
        r = self.client.post(path + "/defer", json={"reason_code": "not_clinically_indicated", "note": "x"},
                             headers=_h("navigator"))
        self.assertEqual(r.status_code, 403)
        # Closure without evidence is refused
        r = self.client.post(path + "/close", json={"evidence": ""}, headers=_h("clinician"))
        self.assertEqual(r.status_code, 409)
        r = self.client.post(path + "/close", json={"evidence": "Colonoscopy booked, order C-2231"},
                             headers=_h("clinician"))
        self.assertEqual(r.json()["workflow_state"], "closed_by_clinician")

        audit = self.client.get(path + "/audit", headers=_h("viewer")).json()["audit"]
        self.assertEqual([a["action"] for a in audit], ["loop_opened", "acknowledge", "close"])
        self.assertEqual(audit[-1]["actor"], "clinician.user")
        self.assertTrue(self.client.get("/api/v1/audit/verify", headers=_h("admin")).json()["audit_chain_intact"])

    def _key(self, rule_id):
        loops = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()["loops"]
        return f"/api/v1/loops/{quote(next(l['loop_key'] for l in loops if l['rule_id'] == rule_id), safe='')}"

    def test_get_single_loop_and_subroutes_resolve(self):
        self._ingest()
        path = self._key("R017")
        self.assertEqual(self.client.get(path, headers=_h("viewer")).json()["rule_id"], "R017")
        self.assertIn("audit", self.client.get(path + "/audit", headers=_h("viewer")).json())
        self.assertIn("messages", self.client.get(path + "/outreach", headers=_h("viewer")).json())

    def test_outreach_draft_approve_send(self):
        import tempfile
        self._ingest()
        path = self._key("R017")
        with tempfile.TemporaryDirectory() as d:
            os.environ["CLINLOOP_OUTBOX"] = os.path.join(d, "outbox.jsonl")
            try:
                draft = self.client.post(path + "/outreach", json={"language": "ko"}, headers=_h("navigator"))
                self.assertEqual(draft.status_code, 200, draft.text)
                msg = draft.json()
                self.assertEqual(msg["status"], "draft")
                for word in ("FIT", "colonoscopy", "대장", "cancer", "암"):
                    self.assertNotIn(word, msg["draft_text"])        # no diagnosis on a lock screen
                decision = f"/api/v1/outreach/{msg['id']}/decision"
                # Navigators draft; only clinicians approve
                self.assertEqual(self.client.post(decision, json={"approve": True},
                                                  headers=_h("navigator")).status_code, 403)
                self.assertEqual(self.client.post(decision, json={"approve": True, "text": "You have cancer."},
                                                  headers=_h("clinician")).status_code, 422)
                sent = self.client.post(decision, json={"approve": True}, headers=_h("clinician")).json()
                self.assertEqual(sent["status"], "sent")
                with open(os.environ["CLINLOOP_OUTBOX"], encoding="utf-8") as f:
                    out = json.loads(f.readline())
                self.assertEqual(out["patient_id"], "SYN-001")
                self.assertNotIn("phone", out)                         # ClinLoop holds no contact details
                again = self.client.post(decision, json={"approve": True}, headers=_h("clinician"))
                self.assertEqual(again.status_code, 409)               # one decision per draft
                loop = self.client.get(path, headers=_h("viewer")).json()
                self.assertEqual(loop["workflow_state"], "acknowledged")   # messaging is not closure
            finally:
                os.environ.pop("CLINLOOP_OUTBOX", None)

    def test_clinician_only_rules_cannot_be_messaged(self):
        self._ingest()
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": {
            "resourceType": "Encounter", "id": "e9", "status": "finished", "class": {"code": "EMER"},
            "subject": {"reference": "Patient/SYN-009"},
            "period": {"start": "2026-08-20T09:00:00Z", "end": "2026-08-20T15:00:00Z"},
            "reasonCode": [{"text": "Intentional self-harm by drug overdose"}]}}]}
        self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00", json=bundle, headers=_h("admin"))
        r = self.client.post(self._key("R029") + "/outreach", json={}, headers=_h("navigator"))
        self.assertEqual(r.status_code, 409)

    def test_feed_status_after_ingest(self):
        self.assertEqual(self.client.get("/api/v1/feed/status", headers=_h("viewer")).json()["status"], "NEVER")
        self._ingest()
        self.assertEqual(self.client.get("/api/v1/feed/status", headers=_h("viewer")).json()["status"], "OK")

    def test_open_loop_rate_by_language(self):
        self._ingest()
        r = self.client.get("/api/v1/metrics/open-loop-rate?stratify_by=language", headers=_h("viewer"))
        self.assertIn("vi", r.json()["groups"])

    def test_config_js_points_pages_at_this_server(self):
        r = self.client.get("/config.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("window.location.origin", r.text)
        self.assertIn("javascript", r.headers["content-type"])

    def test_project_files_are_not_served_without_a_web_root(self):
        self.assertEqual(self.client.get("/src/clinloop_engine/api.py").status_code, 404)

    def test_cors_is_not_wildcard(self):
        r = self.client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
        self.assertNotEqual(r.headers.get("access-control-allow-origin"), "*")


if __name__ == "__main__":
    unittest.main()
