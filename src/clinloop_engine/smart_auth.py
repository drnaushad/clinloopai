"""
smart_auth.py — SMART Backend Services login for the FHIR sync (system-to-system, no user)

The hospital's FHIR server (Epic, Cerner/Oracle Health, Medplum, HAPI behind an OAuth server) gives
ClinLoop a client id and registers ClinLoop's PUBLIC key. ClinLoop proves who it is by signing a
short-lived JWT with its private key, and trades it for an access token
(SMART App Launch "Backend Services": OAuth 2.0 client credentials with a JWT client assertion).

    1. Discover the token endpoint: <base>/.well-known/smart-configuration
       (falling back to the CapabilityStatement's oauth-uris extension).
    2. POST grant_type=client_credentials, scope, client_assertion_type=…jwt-bearer,
       client_assertion=<JWT: iss = sub = client id, aud = token endpoint, exp ≤ 5 min, unique jti>.
    3. Use the access token until shortly before it expires; on a 401, get a new one once.

The private key never leaves the server and is never logged. A sandbox that only supports a client
secret (some Medplum and HAPI setups) can use CLINLOOP_FHIR_CLIENT_SECRET instead of a key.

Configuration (environment):
  CLINLOOP_FHIR_CLIENT_ID      client id issued by the FHIR server
  CLINLOOP_FHIR_PRIVATE_KEY    path to ClinLoop's private key (PEM; RSA → RS384, EC P-384 → ES384)
  CLINLOOP_FHIR_KEY_ID         key id (kid) registered with the server (default: the key's thumbprint)
  CLINLOOP_FHIR_CLIENT_SECRET  client secret, only for sandboxes without key-based login
  CLINLOOP_FHIR_SECRET_METHOD  how the secret is sent: basic (Authorization header, default) or post (form body)
  CLINLOOP_FHIR_TOKEN_URL      token endpoint, when the server does not publish smart-configuration
  CLINLOOP_FHIR_SCOPE          scopes to request (default: read-only access to the types ClinLoop reads)

CLI:
  python -m src.clinloop_engine.smart_auth --new-key DIR   # key pair + the JWKS to register
"""

import argparse
import json
import ipaddress
import logging
import math
import os
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger("clinloop.smart_auth")

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
ASSERTION_LIFETIME = 300          # seconds; SMART allows at most five minutes
REFRESH_MARGIN = 60               # get a new token this long before the old one expires


class SMARTAuthError(RuntimeError):
    pass


def read_only_scopes(resource_types: List[str], v2: bool) -> str:
    """system/<Type>.rs (SMART v2) or system/<Type>.read (v1) for each type ClinLoop reads, and Patient."""
    suffix = "rs" if v2 else "read"
    return " ".join(f"system/{t}.{suffix}" for t in sorted(set(resource_types) | {"Patient"}))


def _algorithm(private_key) -> str:
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    if isinstance(private_key, rsa.RSAPrivateKey):
        return "RS384"
    if isinstance(private_key, ec.EllipticCurvePrivateKey) and private_key.curve.name == "secp384r1":
        return "ES384"
    raise SMARTAuthError("The private key must be RSA (RS384) or EC P-384 (ES384), as SMART Backend Services requires")


def public_jwk(private_key, kid: Optional[str] = None) -> Dict[str, Any]:
    """The public half as a JWK, with its kid (the RFC 7638 thumbprint unless one is given)."""
    import jwt
    alg = _algorithm(private_key)
    algo = jwt.algorithms.RSAAlgorithm if alg == "RS384" else jwt.algorithms.ECAlgorithm
    jwk = json.loads(algo.to_jwk(private_key.public_key()))
    if not kid:
        import base64
        import hashlib
        members = ("e", "kty", "n") if jwk["kty"] == "RSA" else ("crv", "kty", "x", "y")
        canonical = json.dumps({k: jwk[k] for k in members}, separators=(",", ":"), sort_keys=True)
        kid = base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()
    return {**jwk, "kid": kid, "alg": alg, "use": "sig", "key_ops": ["verify"]}


def load_private_key(path: str):
    from cryptography.hazmat.primitives import serialization
    try:
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    except (OSError, ValueError, TypeError) as e:
        raise SMARTAuthError(f"Cannot read the FHIR private key ({type(e).__name__})") from None


class SMARTBackendAuth(requests.auth.AuthBase):
    """requests auth that adds a SMART Backend Services access token, fetched and renewed as needed."""

    def __init__(self, fhir_base: str, client_id: str, private_key=None, kid: Optional[str] = None,
                 client_secret: Optional[str] = None, token_url: Optional[str] = None,
                 scope: Optional[str] = None, resource_types: Optional[List[str]] = None,
                 timeout: float = 30.0, session: Optional[requests.Session] = None, secret_method: str = "basic"):
        if private_key is None and not client_secret:
            raise SMARTAuthError("SMART login needs a private key (or, for a sandbox, a client secret)")
        self.fhir_base = fhir_base.rstrip("/")
        self.client_id = client_id
        self.private_key = private_key
        self.alg = _algorithm(private_key) if private_key is not None else None
        self.kid = public_jwk(private_key, kid)["kid"] if private_key is not None else None
        self.client_secret = client_secret
        if secret_method not in ("basic", "post"):
            raise SMARTAuthError("The client secret method must be 'basic' or 'post'")
        self.secret_method = secret_method
        self._token_url = token_url
        self._scope = scope
        self.resource_types = resource_types or []
        self.timeout = timeout
        self.http = session or requests.Session()      # separate from the FHIR session: no bearer header here
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self._config: Optional[Dict[str, Any]] = None

    # ── discovery ─────────────────────────────────────────────────────────────
    def configuration(self) -> Dict[str, Any]:
        """The server's smart-configuration (or what the CapabilityStatement says), fetched once."""
        if self._config is not None:
            return self._config
        cfg: Dict[str, Any] = {}
        try:
            r = self.http.get(f"{self.fhir_base}/.well-known/smart-configuration",
                              headers={"Accept": "application/json"}, timeout=self.timeout, allow_redirects=False)
            try:
                if r.status_code == 200:
                    decoded = r.json()
                    if isinstance(decoded, dict):
                        cfg = decoded
            finally:
                r.close()
        except (requests.RequestException, ValueError):
            pass
        if not cfg.get("token_endpoint"):
            try:
                r = self.http.get(f"{self.fhir_base}/metadata", headers={"Accept": "application/fhir+json"},
                                  timeout=self.timeout, allow_redirects=False)
                try:
                    if r.status_code == 200:
                        metadata = r.json()
                        rest = metadata.get("rest", []) if isinstance(metadata, dict) else []
                        if not isinstance(rest, list):
                            raise ValueError()
                        for entry in rest:
                            security = entry.get("security", {}) if isinstance(entry, dict) else {}
                            extensions = security.get("extension", []) if isinstance(security, dict) else []
                            if not isinstance(extensions, list):
                                raise ValueError()
                            for ext in extensions:
                                if isinstance(ext, dict) and str(ext.get("url", "")).endswith("oauth-uris"):
                                    subs = ext.get("extension", [])
                                    if not isinstance(subs, list):
                                        raise ValueError()
                                    for sub in subs:
                                        if isinstance(sub, dict) and sub.get("url") == "token":
                                            cfg["token_endpoint"] = sub.get("valueUri")
                finally:
                    r.close()
            except (requests.RequestException, ValueError):
                pass
        for field in ("capabilities", "scopes_supported"):
            if field in cfg and (not isinstance(cfg[field], list)
                                 or any(not isinstance(value, str) for value in cfg[field])):
                raise SMARTAuthError("SMART discovery scope metadata is malformed")
        self._config = cfg
        return cfg

    @property
    def token_url(self) -> str:
        url = self._token_url or self.configuration().get("token_endpoint")
        if not url:
            raise SMARTAuthError("The FHIR server publishes no token endpoint: set CLINLOOP_FHIR_TOKEN_URL")
        try:
            if not isinstance(url, str):
                raise ValueError()
            endpoint = urlsplit(url)
            endpoint.port                    # validate any explicit port
            hostname = endpoint.hostname or ""
            try:
                loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                loopback = hostname.lower() == "localhost"
            if (not hostname or endpoint.username is not None or endpoint.password is not None or endpoint.fragment
                    or not (endpoint.scheme == "https" or (endpoint.scheme == "http" and loopback))):
                raise ValueError()
        except (TypeError, ValueError):
            raise SMARTAuthError("Token endpoint must be HTTPS without embedded credentials or fragments; HTTP is limited to loopback testing") from None
        return url

    @property
    def scope(self) -> str:
        if self._scope:
            return self._scope
        cfg = self.configuration()
        v2 = "permission-v2" in (cfg.get("capabilities") or []) or any(
            str(s).endswith(".rs") for s in cfg.get("scopes_supported") or [])
        return read_only_scopes(self.resource_types, v2)

    # ── token ─────────────────────────────────────────────────────────────────
    def client_assertion(self, now: Optional[float] = None) -> str:
        import jwt
        now = time.time() if now is None else now
        claims = {"iss": self.client_id, "sub": self.client_id, "aud": self.token_url,
                  "exp": int(now) + ASSERTION_LIFETIME, "iat": int(now), "jti": str(uuid.uuid4())}
        return jwt.encode(claims, self.private_key, algorithm=self.alg, headers={"kid": self.kid, "typ": "JWT"})

    def _request_token(self) -> None:
        data = {"grant_type": "client_credentials", "scope": self.scope}
        auth = None
        if self.private_key is not None:
            data.update(client_assertion_type=CLIENT_ASSERTION_TYPE, client_assertion=self.client_assertion())
        elif self.secret_method == "post":                     # client_secret_post (sandboxes)
            data.update(client_id=self.client_id, client_secret=self.client_secret)
        else:
            auth = (self.client_id, self.client_secret)       # client_secret_basic (sandboxes)
        try:
            r = self.http.post(self.token_url, data=data, auth=auth, timeout=self.timeout,
                               headers={"Accept": "application/json"}, allow_redirects=False)
        except requests.RequestException as e:
            raise SMARTAuthError(f"Token endpoint unreachable ({type(e).__name__})") from None
        try:
            if r.status_code != 200:
                try:     # Only standard codes are safe: even `error` can echo source data.
                    body = r.json()
                    err = body.get("error", "") if isinstance(body, dict) else ""
                    allowed = {"invalid_request", "invalid_client", "invalid_grant", "unauthorized_client",
                               "unsupported_grant_type", "invalid_scope", "server_error", "temporarily_unavailable"}
                    if not isinstance(err, str) or err not in allowed:
                        err = ""
                except ValueError:
                    err = ""
                raise SMARTAuthError(f"Token request refused: HTTP {r.status_code}{' ' + err if err else ''}")
            try:
                body = r.json()
                if not isinstance(body, dict):
                    raise ValueError()
                token = body["access_token"]
                lifetime = body.get("expires_in", 300)
                token_type = body.get("token_type", "bearer")
                if (not isinstance(token, str) or not 1 <= len(token) <= 16384 or not token.isascii()
                        or any(ord(c) < 33 or ord(c) > 126 for c in token)
                        or isinstance(lifetime, bool) or not isinstance(lifetime, (int, float, str))
                        or not isinstance(token_type, str) or token_type.lower() != "bearer"):
                    raise ValueError()
                lifetime = float(lifetime)
                deadline = time.time() + lifetime
                if lifetime <= 0 or not math.isfinite(lifetime) or not math.isfinite(deadline):
                    raise ValueError()
            except (ValueError, KeyError, TypeError, OverflowError):
                raise SMARTAuthError("Token endpoint returned an invalid access-token response") from None
        finally:
            r.close()
        self._token = token
        self._expires_at = deadline
        # Even scope/expiry fields can contain source data from a broken server.
        logger.info("FHIR access token obtained")

    def token(self) -> str:
        with self._lock:
            if not self._token or time.time() >= self._expires_at - REFRESH_MARGIN:
                self._request_token()
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None

    def __call__(self, r):
        r.headers["Authorization"] = f"Bearer {self.token()}"
        return r


def auth_from_env(fhir_base: str, resource_types: List[str]) -> Optional[SMARTBackendAuth]:
    """SMART login when CLINLOOP_FHIR_CLIENT_ID is set; None means a static token (or none) is used."""
    client_id = os.environ.get("CLINLOOP_FHIR_CLIENT_ID")
    if not client_id:
        return None
    key_path = os.environ.get("CLINLOOP_FHIR_PRIVATE_KEY")
    return SMARTBackendAuth(
        fhir_base, client_id,
        private_key=load_private_key(key_path) if key_path else None,
        kid=os.environ.get("CLINLOOP_FHIR_KEY_ID") or None,
        client_secret=os.environ.get("CLINLOOP_FHIR_CLIENT_SECRET") or None,
        token_url=os.environ.get("CLINLOOP_FHIR_TOKEN_URL") or None,
        scope=os.environ.get("CLINLOOP_FHIR_SCOPE") or None,
        resource_types=resource_types,
        secret_method=(os.environ.get("CLINLOOP_FHIR_SECRET_METHOD") or "basic").strip().lower())


def new_key(directory: str, kind: str = "rsa") -> Dict[str, Any]:
    """Write a new private key (readable by the owner only) and return the public JWKS to register."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072) if kind == "rsa" \
        else ec.generate_private_key(ec.SECP384R1())
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "clinloop_fhir_private.pem")
    if os.path.exists(path):
        raise SMARTAuthError(f"{path} already exists; not overwriting a key")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    jwks = {"keys": [public_jwk(key)]}
    with open(os.path.join(directory, "clinloop_fhir_jwks.json"), "w", encoding="utf-8") as f:
        json.dump(jwks, f, indent=2)
    return {"private_key": path, "jwks": jwks}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="SMART Backend Services keys for ClinLoop's FHIR login")
    ap.add_argument("--new-key", metavar="DIR", help="create a key pair in DIR and print the JWKS to register")
    ap.add_argument("--ec", action="store_true", help="EC P-384 (ES384) instead of RSA 3072 (RS384)")
    args = ap.parse_args(argv)
    if not args.new_key:
        ap.print_help()
        return 2
    out = new_key(args.new_key, "ec" if args.ec else "rsa")
    print(f"Private key: {out['private_key']} (keep it on the ClinLoop server only)", file=sys.stderr)
    print("Register this public key set with the FHIR server (or serve it at /.well-known/jwks.json):", file=sys.stderr)
    print(json.dumps(out["jwks"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
