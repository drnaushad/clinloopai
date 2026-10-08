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

    def test_open_loop_rate_by_language(self):
        self._ingest()
        r = self.client.get("/api/v1/metrics/open-loop-rate?stratify_by=language", headers=_h("viewer"))
        self.assertIn("vi", r.json()["groups"])

    def test_cors_is_not_wildcard(self):
        r = self.client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
        self.assertNotEqual(r.headers.get("access-control-allow-origin"), "*")


if __name__ == "__main__":
    unittest.main()
