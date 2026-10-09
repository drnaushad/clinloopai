"""
test_demo_mode.py — Public demo mode (CLINLOOP_DEMO=1): synthetic data, view-only, no hospital links.

Skipped when the optional API dependencies (fastapi, httpx) are not installed.
"""

import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import auth, clinical_api, demo
    from src.clinloop_engine.api import app
    from src.clinloop_engine.loop_store import LoopStore
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False

DEMO_ENV = {"CLINLOOP_DEMO": "1", "CLINLOOP_API_TOKENS": ""}
H = {"Authorization": "Bearer clinloop-public-demo-viewer"}


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestDemoMode(unittest.TestCase):

    def setUp(self):
        self.prev = clinical_api.get_store()
        with mock.patch.dict(os.environ, DEMO_ENV):
            tokens = auth._load_tokens()
        patcher = mock.patch.dict(auth._TOKENS, tokens)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(clinical_api.set_store, self.prev)

    def test_demo_token_is_view_only_and_off_by_default(self):
        with mock.patch.dict(os.environ, DEMO_ENV):
            tokens = auth._load_tokens()
        self.assertEqual(tokens[demo.DEMO_TOKEN].role, "viewer")
        self.assertTrue(any(u.role == "admin" for u in tokens.values()))   # the operator's own admin token
        with mock.patch.dict(os.environ, {"CLINLOOP_DEMO": "", "CLINLOOP_API_TOKENS": ""}):
            self.assertNotIn(demo.DEMO_TOKEN, auth._load_tokens())

    def test_startup_loads_synthetic_patients_into_a_fresh_store(self):
        env = dict(DEMO_ENV, CLINLOOP_FHIR_BASE="https://hospital.example/fhir", CLINLOOP_IMAGE_SCAN="1")
        with mock.patch.dict(os.environ, env):
            with TestClient(app) as client:
                self.assertNotIn("CLINLOOP_FHIR_BASE", os.environ)          # hospital links removed
                self.assertNotIn("CLINLOOP_IMAGE_SCAN", os.environ)
                self.assertIsNot(clinical_api.get_store(), self.prev)
                rows = client.get("/api/v1/worklist", headers=H)
                self.assertEqual(rows.status_code, 200, rows.text)
                self.assertGreater(len(rows.json()["loops"]), 0)
                cfg = client.get("/config.js").text
                self.assertIn("window.CLINLOOP_DEMO", cfg)
                self.assertIn(demo.DEMO_TOKEN, cfg)

    def test_demo_token_cannot_upload_or_change_anything(self):
        with mock.patch.dict(os.environ, DEMO_ENV):
            demo.seed(LoopStore())
            client = TestClient(app)
            with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
                bundle = json.load(f)
            self.assertEqual(client.post("/api/v1/fhir/ingest", json=bundle, headers=H).status_code, 403)
            key = client.get("/api/v1/worklist", headers=H).json()["loops"][0]["loop_key"]
            for action in ("acknowledge", "close", "defer", "assign"):
                r = client.post(f"/api/v1/loops/{key}/{action}", json={}, headers=H)
                self.assertIn(r.status_code, (403, 422), action)
                if r.status_code == 422:      # body checked first; the role check still applies
                    self.assertEqual(client.post(f"/api/v1/loops/{key}/{action}",
                                                 json={"reason": "duplicate", "evidence": "x", "owner": "x",
                                                       "note": "x"}, headers=H).status_code, 403, action)

    def test_config_has_no_demo_settings_outside_demo_mode(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_DEMO": ""}):
            self.assertNotIn("CLINLOOP_DEMO", TestClient(app).get("/config.js").text)


if __name__ == "__main__":
    unittest.main()
