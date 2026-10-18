"""
test_sso.py — Staff sign-in through the hospital's identity provider (OpenID Connect)

A stub identity provider publishes a discovery document and signing keys, "logs in" anyone at its
authorize endpoint (redirecting back with a code) and issues signed tokens at its token endpoint,
checking PKCE. Synthetic accounts only.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# The API's token table is read once per process: the same test tokens as the other API test files
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in {
    "admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}.items())

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

CLIENT_ID = "clinloop-web"


class StubIdP:
    """A minimal OpenID provider. `accounts` maps a login name to its groups."""

    def __init__(self, accounts=None, host="127.0.0.1", public_host=None, role_claim="roles"):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "stub-key-1"
        self.accounts = accounts or {"dr.kim": ["clinloop-clinician"], "nurse.park": ["clinloop-navigator"],
                                     "visitor": ["library-users"]}
        self.login_as = "dr.kim"
        self.role_claim = role_claim
        self.codes = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=None, headers=None):
                data = json.dumps(body).encode() if body is not None else b""
                self.send_response(code)
                self.send_header("Access-Control-Allow-Origin", "*")      # the pages call the token endpoint
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/.well-known/openid-configuration":
                    return self._send(200, {"issuer": stub.issuer, "jwks_uri": f"{stub.issuer}/jwks",
                                            "authorization_endpoint": f"{stub.issuer}/authorize",
                                            "token_endpoint": f"{stub.issuer}/token",
                                            "end_session_endpoint": f"{stub.issuer}/logout",
                                            "id_token_signing_alg_values_supported": ["RS256"]})
                if url.path == "/jwks":
                    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(stub.key.public_key()))
                    return self._send(200, {"keys": [{**jwk, "kid": stub.kid, "alg": "RS256", "use": "sig"}]})
                if url.path == "/authorize":                 # "logs in" stub.login_as and returns at once
                    q = {k: v[0] for k, v in parse_qs(url.query).items()}
                    if q.get("code_challenge_method") != "S256" or q.get("client_id") != CLIENT_ID:
                        return self._send(400, {"error": "invalid_request"})
                    code = secrets.token_urlsafe(16)
                    stub.codes[code] = {**q, "user": stub.login_as}
                    back = q["redirect_uri"] + "?" + urlencode({"code": code, "state": q["state"]})
                    return self._send(302, headers={"Location": back})
                self._send(404, {})

            def do_POST(self):
                if urlparse(self.path).path != "/token":
                    return self._send(404, {})
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                grant = stub.codes.pop(form.get("code"), None)        # codes are single-use
                if not grant or form.get("redirect_uri") != grant["redirect_uri"]:
                    return self._send(400, {"error": "invalid_grant"})
                challenge = base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
                if challenge != grant["code_challenge"]:
                    return self._send(400, {"error": "invalid_grant"})
                user = grant["user"]
                self._send(200, {"access_token": stub.token(user), "id_token": stub.token(user, nonce=grant.get("nonce")),
                                 "token_type": "Bearer", "expires_in": 300})

        self.server = ThreadingHTTPServer((host, 0), Handler)
        self.issuer = f"http://{public_host or host}:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def token(self, user, aud=CLIENT_ID, issuer=None, exp_in=300, nonce=None, key=None, alg="RS256", **extra):
        now = int(time.time())
        groups = self.accounts.get(user, [])
        claims = {"iss": issuer or self.issuer, "sub": f"sub-{user}", "aud": aud, "iat": now, "exp": now + exp_in,
                  "preferred_username": user, **extra}
        if self.role_claim == "realm_access.roles":
            claims["realm_access"] = {"roles": groups}
        else:
            claims[self.role_claim] = groups
        if nonce:
            claims["nonce"] = nonce
        return jwt.encode(claims, key or self.key, algorithm=alg, headers={"kid": self.kid})

    def close(self):
        self.server.shutdown()


def _use(idp, **env):
    from src.clinloop_engine import auth, oidc
    os.environ.update(CLINLOOP_OIDC_ISSUER=idp.issuer, CLINLOOP_OIDC_CLIENT_ID=CLIENT_ID, **env)
    oidc.reset_cache()
    auth._sso_seen.clear()


def _clear():
    from src.clinloop_engine import oidc
    for k in [k for k in os.environ if k.startswith("CLINLOOP_OIDC_")]:
        os.environ.pop(k)
    oidc.reset_cache()


class TestTokenVerification(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.idp = StubIdP()

    @classmethod
    def tearDownClass(cls):
        cls.idp.close()

    def setUp(self):
        _use(self.idp)

    def tearDown(self):
        _clear()

    def test_hospital_token_gives_the_mapped_role(self):
        from src.clinloop_engine.auth import authenticate
        self.assertEqual(authenticate(self.idp.token("dr.kim")).role, "clinician")
        self.assertEqual(authenticate(self.idp.token("nurse.park")).name, "nurse.park")

    def test_tokens_that_must_be_refused(self):
        from src.clinloop_engine.auth import authenticate
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        refused = {
            "wrong audience": self.idp.token("dr.kim", aud="another-app"),
            "wrong issuer": self.idp.token("dr.kim", issuer="https://evil.example"),
            "expired": self.idp.token("dr.kim", exp_in=-600),
            "not signed by the provider": self.idp.token("dr.kim", key=other),
            "garbage": "a.b.c",
        }
        # A symmetric token "signed" with the public key must never pass (algorithm confusion)
        from cryptography.hazmat.primitives import serialization
        pem = self.idp.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        refused["HS256 with the public key"] = jwt.encode(
            {"iss": self.idp.issuer, "aud": CLIENT_ID, "iat": int(time.time()), "exp": int(time.time()) + 300,
             "preferred_username": "attacker", "roles": ["clinloop-admin"]},
            hashlib.sha256(pem).digest(), algorithm="HS256", headers={"kid": self.idp.kid})
        for why, token in refused.items():
            self.assertIsNone(authenticate(token), why)

    def test_valid_login_without_a_clinloop_role_is_forbidden_not_unknown(self):
        from src.clinloop_engine.auth import NoRole, authenticate
        with self.assertRaises(NoRole):
            authenticate(self.idp.token("visitor"))

    def test_nested_role_claim_and_custom_map(self):
        from src.clinloop_engine.auth import authenticate
        keycloak = StubIdP(accounts={"dr.lee": ["ward-7-doctors"]}, role_claim="realm_access.roles")
        try:
            _use(keycloak, CLINLOOP_OIDC_ROLE_CLAIM="realm_access.roles",
                 CLINLOOP_OIDC_ROLE_MAP=json.dumps({"ward-7-doctors": "clinician"}))
            self.assertEqual(authenticate(keycloak.token("dr.lee")).role, "clinician")
        finally:
            keycloak.close()

    def test_static_tokens_still_work_and_sso_is_off_without_settings(self):
        from src.clinloop_engine.auth import authenticate
        self.assertEqual(authenticate("test-admin-token-0123456789").role, "admin")
        _clear()
        self.assertIsNone(authenticate(self.idp.token("dr.kim")))


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    from src.clinloop_engine.loop_store import LoopStore
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestSSOThroughTheAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.idp = StubIdP()

    @classmethod
    def tearDownClass(cls):
        cls.idp.close()

    def setUp(self):
        _use(self.idp)
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.client = TestClient(app)

    def tearDown(self):
        _clear()

    def _h(self, user):
        return {"Authorization": f"Bearer {self.idp.token(user)}"}

    def test_sign_in_roles_and_refusals(self):
        self.assertEqual(self.client.get("/api/v1/me", headers=self._h("dr.kim")).json(),
                         {"user": "dr.kim", "role": "clinician"})
        r = self.client.get("/api/v1/me", headers=self._h("visitor"))
        self.assertEqual(r.status_code, 403)
        self.assertIn("no ClinLoop role", r.json()["detail"])
        self.assertEqual(self.client.post("/api/v1/watchdog/escalate", headers=self._h("dr.kim")).status_code, 403)

    def test_people_who_signed_in_can_be_assigned_loops(self):
        self.client.get("/api/v1/me", headers=self._h("nurse.park"))
        staff = {u["user"] for u in self.client.get("/api/v1/users", headers=self._h("dr.kim")).json()["users"]}
        self.assertIn("nurse.park", staff)
        self.assertIn("dr.kim", staff)
        self.assertIn("clinician.user", staff)                      # token holders are still listed

    def test_pages_get_the_public_sign_in_settings(self):
        body = self.client.get("/config.js").text
        self.assertIn("window.CLINLOOP_OIDC", body)
        cfg = json.loads(body.split("window.CLINLOOP_OIDC = ", 1)[1].split(";\n", 1)[0])
        self.assertEqual(cfg["client_id"], CLIENT_ID)
        self.assertEqual(cfg["token_endpoint"], f"{self.idp.issuer}/token")
        self.assertNotIn("secret", body.lower())
        _clear()
        self.assertNotIn("CLINLOOP_OIDC", self.client.get("/config.js").text)


if __name__ == "__main__":
    unittest.main()
