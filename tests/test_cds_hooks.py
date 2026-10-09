"""
test_cds_hooks.py — Open loops as CDS Hooks cards in the EHR (patient-view)

A test RSA key stands in for the EHR's signing key. Synthetic patients only.
Skipped when the optional API dependencies are not installed.
"""

import json
import os
import sys
import time
import unittest
import uuid
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {"admin": "test-admin-token-0123456789", "viewer": "test-viewer-token-0123456789"}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    from src.clinloop_engine.loop_store import LoopStore
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False

EHR = "https://ehr.hospital.example"
URL = "http://testserver/cds-services/clinloop-open-loops"


def _key_pair(kid="ehr-1"):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public_jwk.update(kid=kid, alg="RS384", use="sig")
    return private, {"keys": [public_jwk]}


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestCDSHooks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.private, cls.jwks = _key_pair()

    def setUp(self):
        self.prev = clinical_api.get_store()
        clinical_api.set_store(LoopStore())
        self.addCleanup(clinical_api.set_store, self.prev)
        self.client = TestClient(app)
        env = mock.patch.dict(os.environ, {"CLINLOOP_CDS_CLIENTS": json.dumps([{"iss": EHR, "jwks": self.jwks}]),
                                           "CLINLOOP_PUBLIC_URL": "https://clinloop.hospital.example"})
        env.start()
        self.addCleanup(env.stop)
        with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
            bundle = json.load(f)
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00", json=bundle,
                             headers={"Authorization": f"Bearer {TOKENS['admin']}"})
        self.assertEqual(r.status_code, 200, r.text)
        rows = self.client.get("/api/v1/worklist", headers={"Authorization": f"Bearer {TOKENS['viewer']}"}).json()["loops"]
        self.patient = rows[0]["patient_id"]
        self.expected = [x["loop_key"] for x in rows if x["patient_id"] == self.patient]

    def token(self, **over):
        now = int(time.time())
        claims = {"iss": EHR, "aud": URL, "iat": now, "exp": now + 300, "jti": str(uuid.uuid4()), "sub": "app"}
        claims.update(over)
        return jwt.encode(claims, self.private, algorithm="RS384", headers={"kid": "ehr-1"})

    def call(self, token, patient=None):
        body = {"hook": "patient-view", "hookInstance": str(uuid.uuid4()),
                "context": {"patientId": patient or self.patient, "userId": "Practitioner/dr-1"}}
        return self.client.post("/cds-services/clinloop-open-loops", json=body,
                                headers={"Authorization": f"Bearer {token}"})

    def test_discovery_is_public_and_names_the_hook(self):
        services = self.client.get("/cds-services").json()["services"]
        self.assertEqual([(s["hook"], s["id"]) for s in services], [("patient-view", "clinloop-open-loops")])

    def test_signed_ehr_call_gets_the_patients_open_loops(self):
        r = self.call(self.token())
        self.assertEqual(r.status_code, 200, r.text)
        cards = r.json()["cards"]
        self.assertEqual([c["uuid"] for c in cards], self.expected[:5])
        card = cards[0]
        self.assertLessEqual(len(card["summary"]), 140)
        self.assertIn(card["indicator"], ("info", "warning", "critical"))
        self.assertTrue(card["links"][0]["url"].startswith("https://clinloop.hospital.example/worklist.html"))
        self.assertIn("not a diagnosis", card["detail"])

    def test_untrusted_or_invalid_tokens_are_refused(self):
        self.assertEqual(self.call("").status_code, 401)
        self.assertEqual(self.call(self.token(iss="https://other-ehr.example")).status_code, 401)
        self.assertEqual(self.call(self.token(aud="https://elsewhere/cds")).status_code, 401)
        self.assertEqual(self.call(self.token(exp=int(time.time()) - 120)).status_code, 401)
        other, _ = _key_pair()                         # signed by a key the EHR does not publish
        forged = jwt.encode({"iss": EHR, "aud": URL, "iat": int(time.time()), "exp": int(time.time()) + 300,
                             "jti": "x"}, other, algorithm="RS384", headers={"kid": "ehr-1"})
        self.assertEqual(self.call(forged).status_code, 401)
        once = self.token()
        self.assertEqual(self.call(once).status_code, 200)
        self.assertEqual(self.call(once).status_code, 401)      # a token is used once

    def test_api_token_works_and_unknown_patient_gets_no_cards(self):
        r = self.call(TOKENS["viewer"], patient="nobody")
        self.assertEqual((r.status_code, r.json()), (200, {"cards": []}))

    def test_shadow_mode_rules_stay_silent(self):
        with mock.patch("src.clinloop_engine.governance.live_rule_ids", return_value=set()):
            self.assertEqual(self.call(self.token()).json(), {"cards": []})

    def test_card_limit_and_feedback_is_audited(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_CDS_MAX_CARDS": "1"}):
            cards = self.call(self.token()).json()["cards"]
        if len(self.expected) > 1:
            self.assertEqual(len(cards), 2)
            self.assertIn("more open follow-ups", cards[-1]["summary"])
        fb = {"feedback": [{"card": cards[0]["uuid"], "outcome": "overridden",
                            "overrideReason": {"reason": {"code": "completed_elsewhere"}, "userComment": "done at clinic X"},
                            "outcomeTimestamp": "2026-09-01T10:00:00Z"}]}
        r = self.client.post("/cds-services/clinloop-open-loops/feedback", json=fb,
                             headers={"Authorization": f"Bearer {self.token(aud=URL + '/feedback')}"})
        self.assertEqual(r.status_code, 200, r.text)
        trail = clinical_api.get_store().audit_trail(cards[0]["uuid"])
        self.assertEqual(trail[-1]["action"], "cds_card_feedback")
        self.assertEqual(trail[-1]["detail"]["override_reason"], "completed_elsewhere")
        self.assertTrue(clinical_api.get_store().verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
