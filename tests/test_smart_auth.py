"""
test_smart_auth.py — SMART Backend Services login for the FHIR sync, and the connection check

A stub server plays both parts: an OAuth token endpoint that checks ClinLoop's signed client
assertion against the registered public key (as Epic, Medplum or a SMART sandbox would), and a
FHIR R4 server that only answers with a current access token. Synthetic data only.
"""

import copy
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# The API's token table is read once per process, at import: use the same test tokens as the other
# API test files, whichever of them is imported first
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in {
    "admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}.items())

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from src.clinloop_engine.fhir_ingest import _patient_id
from src.clinloop_engine.fhir_sync import FHIRClient, check_connection, client_from_env, sync_once
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine.smart_auth import (ASSERTION_LIFETIME, CLIENT_ASSERTION_TYPE, SMARTAuthError,
                                            SMARTBackendAuth, new_key, public_jwk)

NOW = datetime(2026, 9, 1)
CLIENT_ID = "clinloop-backend"


def _resources():
    with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    out = []
    for e in bundle["entry"]:
        r = copy.deepcopy(e["resource"])
        r["meta"] = {"lastUpdated": "2026-08-30T00:00:00Z"}
        out.append(r)
    return out


class StubSMART:
    """OAuth token endpoint + FHIR R4 search, in one HTTP server."""

    def __init__(self, public_key=None, secret=None, forbidden=(), expires_in=3600, publish_config=True):
        self.public_key, self.secret, self.forbidden = public_key, secret, set(forbidden)
        self.expires_in, self.publish_config = expires_in, publish_config
        self.resources = _resources()
        self.tokens = set()
        self.token_requests = 0
        self.seen_jti = set()
        self.assertions = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/fhir+json"):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if urlparse(self.path).path != "/auth/token":
                    return self._send(404, {})
                stub.token_requests += 1
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                if form.get("grant_type") != "client_credentials" or "scope" not in form:
                    return self._send(400, {"error": "invalid_request"}, "application/json")
                if stub.secret:
                    import base64
                    expected = "Basic " + base64.b64encode(f"{CLIENT_ID}:{stub.secret}".encode()).decode()
                    basic = self.headers.get("Authorization") == expected
                    post = (form.get("client_id"), form.get("client_secret")) == (CLIENT_ID, stub.secret)
                    if basic == post:                    # exactly one method (RFC 6749 §2.3)
                        return self._send(401, {"error": "invalid_client"}, "application/json")
                else:
                    if form.get("client_assertion_type") != CLIENT_ASSERTION_TYPE:
                        return self._send(400, {"error": "invalid_client"}, "application/json")
                    try:
                        claims = jwt.decode(form["client_assertion"], stub.public_key, algorithms=["RS384", "ES384"],
                                            audience=f"{stub.base}/auth/token", issuer=CLIENT_ID,
                                            options={"require": ["exp", "jti", "iss", "sub", "aud"]})
                    except jwt.PyJWTError:
                        return self._send(400, {"error": "invalid_client"}, "application/json")
                    if claims["sub"] != CLIENT_ID or claims["jti"] in stub.seen_jti \
                            or claims["exp"] - time.time() > ASSERTION_LIFETIME + 5:
                        return self._send(400, {"error": "invalid_client"}, "application/json")
                    stub.seen_jti.add(claims["jti"])
                    stub.assertions.append((jwt.get_unverified_header(form["client_assertion"]), claims))
                token = f"tok-{stub.token_requests}"
                stub.tokens.add(token)
                self._send(200, {"access_token": token, "token_type": "bearer", "expires_in": stub.expires_in,
                                 "scope": form["scope"]}, "application/json")

            def do_GET(self):
                url = urlparse(self.path)
                path = url.path.strip("/")
                if path == ".well-known/smart-configuration":
                    if not stub.publish_config:
                        return self._send(404, {})
                    return self._send(200, {"token_endpoint": f"{stub.base}/auth/token",
                                            "capabilities": ["client-confidential-asymmetric", "permission-v2"],
                                            "token_endpoint_auth_methods_supported": ["private_key_jwt"]},
                                      "application/json")
                if path == "metadata":
                    return self._send(200, {"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1",
                                            "software": {"name": "Stub SMART"},
                                            "rest": [{"mode": "server", "resource": [
                                                {"type": t} for t in {r["resourceType"] for r in stub.resources}],
                                                "security": {"extension": [{"url": "http://fhir-registry.smarthealthit.org/StructureDefinition/oauth-uris",
                                                                            "extension": [{"url": "token", "valueUri": f"{stub.base}/auth/token"}]}]}}]})
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] not in stub.tokens:
                    return self._send(401, {"resourceType": "OperationOutcome"})
                rtype = path.split("/")[-1]
                if rtype in stub.forbidden:
                    return self._send(403, {"resourceType": "OperationOutcome"})
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                hits = [r for r in stub.resources if r["resourceType"] == rtype]
                if "_lastUpdated" in q:
                    hits = [r for r in hits if r["meta"]["lastUpdated"] > q["_lastUpdated"][2:]]
                if "patient" in q:
                    hits = [r for r in hits if _patient_id(r) == q["patient"].split("/")[-1]]
                if "_id" in q:
                    hits = [r for r in hits if r["id"] == q["_id"]]
                self._send(200, {"resourceType": "Bundle", "type": "searchset",
                                 "entry": [{"resource": r} for r in hits], "link": []})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


class TestSMARTBackendServices(unittest.TestCase):

    def setUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.stub = StubSMART(public_key=self.key.public_key())

    def tearDown(self):
        self.stub.close()

    def _auth(self, **kw):
        return SMARTBackendAuth(self.stub.base, CLIENT_ID, private_key=self.key,
                                resource_types=["Observation", "DiagnosticReport"], **kw)

    def test_sync_logs_in_with_a_signed_assertion_and_reuses_the_token(self):
        result = sync_once(LoopStore(), FHIRClient(self.stub.base, auth=self._auth()), now=NOW)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["patients"], 7)
        self.assertEqual(self.stub.token_requests, 1)                 # one login for the whole run
        header, claims = self.stub.assertions[0]
        self.assertEqual((header["alg"], header["typ"]), ("RS384", "JWT"))
        self.assertEqual(header["kid"], public_jwk(self.key)["kid"])
        self.assertLessEqual(claims["exp"] - claims["iat"], ASSERTION_LIFETIME)

    def test_scopes_are_read_only_and_follow_smart_v2(self):
        scope = self._auth().scope
        self.assertEqual(scope, "system/DiagnosticReport.rs system/Observation.rs system/Patient.rs")
        self.assertNotIn("write", scope)

    def test_expired_or_revoked_token_is_renewed_once(self):
        auth = self._auth()
        client = FHIRClient(self.stub.base, auth=auth)
        self.assertTrue(sync_once(LoopStore(), client, now=NOW)["ok"])
        auth._expires_at = time.time()                               # expiry: renewed before the next call
        self.assertTrue(sync_once(LoopStore(), client, now=NOW)["ok"])
        self.assertEqual(self.stub.token_requests, 2)
        self.stub.tokens.clear()                                     # revoked by the server: 401, log in again
        self.assertTrue(sync_once(LoopStore(), client, now=NOW)["ok"])
        self.assertEqual(self.stub.token_requests, 3)
        self.assertEqual(len(self.stub.seen_jti), 3)                 # every assertion is new

    def test_unregistered_key_fails_loudly_without_leaking_it(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        store = LoopStore()
        result = sync_once(store, FHIRClient(self.stub.base, auth=SMARTBackendAuth(
            self.stub.base, CLIENT_ID, private_key=other)), now=NOW)
        self.assertFalse(result["ok"])
        self.assertIn("Token request refused: HTTP 400 invalid_client", result["error"])
        self.assertNotIn("PRIVATE", result["error"])
        self.assertNotEqual(store.feed_status(now=NOW)["status"], "OK")       # the feed alarm shows it

    def test_ec_p384_key_signs_es384(self):
        key = ec.generate_private_key(ec.SECP384R1())
        stub = StubSMART(public_key=key.public_key())
        try:
            auth = SMARTBackendAuth(stub.base, CLIENT_ID, private_key=key)
            self.assertTrue(sync_once(LoopStore(), FHIRClient(stub.base, auth=auth), now=NOW)["ok"])
            self.assertEqual(stub.assertions[0][0]["alg"], "ES384")
        finally:
            stub.close()
        with self.assertRaises(SMARTAuthError):              # P-256 is not a SMART Backend Services algorithm
            SMARTBackendAuth(self.stub.base, CLIENT_ID, private_key=ec.generate_private_key(ec.SECP256R1()))

    def test_token_endpoint_from_capability_statement_or_setting(self):
        stub = StubSMART(public_key=self.key.public_key(), publish_config=False)
        try:
            auth = SMARTBackendAuth(stub.base, CLIENT_ID, private_key=self.key)
            self.assertEqual(auth.token_url, f"{stub.base}/auth/token")
            self.assertTrue(sync_once(LoopStore(), FHIRClient(stub.base, auth=auth), now=NOW)["ok"])
        finally:
            stub.close()

    def test_client_secret_for_sandboxes(self):
        stub = StubSMART(secret="sandbox-secret")
        try:
            ok = SMARTBackendAuth(stub.base, CLIENT_ID, client_secret="sandbox-secret")
            self.assertTrue(sync_once(LoopStore(), FHIRClient(stub.base, auth=ok), now=NOW)["ok"])
            post = SMARTBackendAuth(stub.base, CLIENT_ID, client_secret="sandbox-secret", secret_method="post")
            self.assertTrue(sync_once(LoopStore(), FHIRClient(stub.base, auth=post), now=NOW)["ok"])
            bad = SMARTBackendAuth(stub.base, CLIENT_ID, client_secret="wrong")
            self.assertIn("HTTP 401", sync_once(LoopStore(), FHIRClient(stub.base, auth=bad), now=NOW)["error"])
        finally:
            stub.close()


class TestConnectionCheck(unittest.TestCase):

    def test_check_reports_version_login_and_unreadable_types_without_patient_data(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        stub = StubSMART(public_key=key.public_key(), forbidden={"Communication"})
        try:
            client = FHIRClient(stub.base, auth=SMARTBackendAuth(stub.base, CLIENT_ID, private_key=key))
            report = check_connection(client)
            self.assertEqual(report["fhir_version"], "4.0.1")
            self.assertEqual(report["login"]["method"], "SMART Backend Services")
            self.assertTrue(report["types"]["Observation"]["readable"])
            self.assertFalse(report["types"]["Communication"]["readable"])
            self.assertIn("scopes", report["types"]["Communication"]["hint"])
            self.assertFalse(report["ok"])
            self.assertNotIn("SYN-0", json.dumps(report))                 # no patient data in the report
        finally:
            stub.close()

    def test_check_stops_at_a_failed_login(self):
        stub = StubSMART(public_key=rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key())
        try:
            other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            report = check_connection(FHIRClient(stub.base, auth=SMARTBackendAuth(stub.base, CLIENT_ID, private_key=other)))
            self.assertFalse(report["ok"])
            self.assertIn("error", report["login"])
            self.assertEqual(report["types"], {})
        finally:
            stub.close()


class TestKeysAndConfiguration(unittest.TestCase):

    def test_new_key_is_private_to_the_owner_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out = new_key(d)
            self.assertEqual(stat.S_IMODE(os.stat(out["private_key"]).st_mode), 0o600)
            jwk = out["jwks"]["keys"][0]
            self.assertEqual((jwk["kty"], jwk["alg"]), ("RSA", "RS384"))
            self.assertNotIn("d", jwk)                                       # public half only
            with self.assertRaises(SMARTAuthError):
                new_key(d)

    def test_environment_selects_smart_login_and_a_bad_key_stops_startup(self):
        saved = {k: os.environ.pop(k, None) for k in ("CLINLOOP_FHIR_BASE", "CLINLOOP_FHIR_CLIENT_ID",
                                                       "CLINLOOP_FHIR_PRIVATE_KEY", "CLINLOOP_FHIR_TOKEN")}
        try:
            with tempfile.TemporaryDirectory() as d:
                out = new_key(d, "ec")
                os.environ.update(CLINLOOP_FHIR_BASE="https://fhir.example.org/r4", CLINLOOP_FHIR_CLIENT_ID=CLIENT_ID,
                                  CLINLOOP_FHIR_PRIVATE_KEY=out["private_key"])
                client = client_from_env()
                self.assertIsInstance(client.session.auth, SMARTBackendAuth)
                self.assertEqual(client.session.auth.alg, "ES384")
                os.environ["CLINLOOP_FHIR_PRIVATE_KEY"] = os.path.join(d, "missing.pem")
                from src.clinloop_engine.fhir_sync import FHIRSyncError
                with self.assertRaises(FHIRSyncError):
                    client_from_env()
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestJWKSEndpoint(unittest.TestCase):

    def test_public_key_is_served_and_private_parts_are_not(self):
        saved = os.environ.pop("CLINLOOP_FHIR_PRIVATE_KEY", None)
        try:
            client = TestClient(app)
            self.assertEqual(client.get("/.well-known/jwks.json").status_code, 404)
            with tempfile.TemporaryDirectory() as d:
                os.environ["CLINLOOP_FHIR_PRIVATE_KEY"] = new_key(d)["private_key"]
                r = client.get("/.well-known/jwks.json")
                self.assertEqual(r.status_code, 200)
                key = r.json()["keys"][0]
                self.assertEqual(key["alg"], "RS384")
                self.assertTrue(set(key).isdisjoint({"d", "p", "q", "dp", "dq", "qi"}))
        finally:
            os.environ.pop("CLINLOOP_FHIR_PRIVATE_KEY", None)
            if saved is not None:
                os.environ["CLINLOOP_FHIR_PRIVATE_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
