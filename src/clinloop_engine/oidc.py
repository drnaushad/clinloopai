"""
oidc.py — Staff sign-in through the hospital's identity provider (OpenID Connect)

With this configured, staff sign in with their hospital account instead of a token issued by hand:
the clinical pages send them to the identity provider (Keycloak, Microsoft Entra ID, ADFS, Okta…)
with the authorization-code flow and PKCE, and then call the API with the token the provider
issued. The API accepts such a token only if:

  * its signature verifies against the provider's published keys (JWKS; asymmetric algorithms only),
  * it was issued by the configured issuer, for ClinLoop's audience, and has not expired,
  * the person holds a group or role that maps to a ClinLoop role (viewer … admin).

People without a mapped role are refused (403), even with a valid hospital login. Tokens issued by
hand (CLINLOOP_API_TOKENS) keep working, for service accounts and for sites without single sign-on.

Configuration (environment):
  CLINLOOP_OIDC_ISSUER       issuer URL, e.g. https://login.hospital.local/realms/clinical
  CLINLOOP_OIDC_CLIENT_ID    ClinLoop's client id at the provider (a public client: PKCE, no secret)
  CLINLOOP_OIDC_AUDIENCE     audience the API requires in tokens (default: the client id)
  CLINLOOP_OIDC_ROLE_CLAIM   claim holding the person's groups or roles, dotted for nesting
                             (default "roles"; Keycloak: "realm_access.roles"; Entra ID: "roles" or "groups")
  CLINLOOP_OIDC_ROLE_MAP     JSON {provider group or role: ClinLoop role}
                             (default: clinloop-viewer, clinloop-navigator, clinloop-clinician, clinloop-admin)
  CLINLOOP_OIDC_USER_CLAIM   claim used as the user name (default: preferred_username, then email, then sub)
  CLINLOOP_OIDC_SCOPE        scopes the pages request (default "openid profile")
  CLINLOOP_OIDC_SEND         which token the pages send: access_token (default) or id_token
"""

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("clinloop.oidc")

ASYMMETRIC_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
DEFAULT_ROLE_MAP = {"clinloop-viewer": "viewer", "clinloop-navigator": "navigator",
                    "clinloop-clinician": "clinician", "clinloop-admin": "admin"}
DISCOVERY_TTL = 3600
LEEWAY_SECONDS = 60


class OIDCError(Exception):
    """The token is not acceptable (bad signature, wrong issuer or audience, expired, or no role)."""

    def __init__(self, message: str, no_role: bool = False):
        super().__init__(message)
        self.no_role = no_role


def enabled() -> bool:
    return bool(os.environ.get("CLINLOOP_OIDC_ISSUER") and os.environ.get("CLINLOOP_OIDC_CLIENT_ID"))


_lock = threading.Lock()
_discovery: Dict[str, Any] = {"config": None, "fetched": 0.0, "issuer": None}
_jwks_clients: Dict[str, Any] = {}


def discovery() -> Dict[str, Any]:
    """The provider's openid-configuration, cached for an hour."""
    issuer = os.environ.get("CLINLOOP_OIDC_ISSUER", "").rstrip("/")
    with _lock:
        if (_discovery["config"] and _discovery["issuer"] == issuer
                and time.time() - _discovery["fetched"] < DISCOVERY_TTL):
            return _discovery["config"]
    try:
        r = requests.get(f"{issuer}/.well-known/openid-configuration", timeout=10,
                         headers={"Accept": "application/json"})
        r.raise_for_status()
        cfg = r.json()
    except (requests.RequestException, ValueError) as e:
        raise OIDCError(f"Identity provider unreachable ({type(e).__name__})") from None
    if str(cfg.get("issuer", "")).rstrip("/") != issuer:
        raise OIDCError("The identity provider's discovery document names a different issuer")
    with _lock:
        _discovery.update(config=cfg, fetched=time.time(), issuer=issuer)
    return cfg


def _signing_key(token: str):
    import jwt
    jwks_uri = discovery().get("jwks_uri")
    if not jwks_uri:
        raise OIDCError("The identity provider publishes no signing keys (jwks_uri)")
    with _lock:
        client = _jwks_clients.get(jwks_uri)
        if client is None:
            client = _jwks_clients[jwks_uri] = jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=DISCOVERY_TTL)
    try:
        return client.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as e:
        raise OIDCError(f"No matching signing key ({type(e).__name__})") from None


def _claim(claims: Dict[str, Any], path: str) -> Any:
    value: Any = claims
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def role_map() -> Dict[str, str]:
    raw = os.environ.get("CLINLOOP_OIDC_ROLE_MAP")
    if not raw:
        return dict(DEFAULT_ROLE_MAP)
    try:
        mapping = json.loads(raw)
    except ValueError:
        raise OIDCError("CLINLOOP_OIDC_ROLE_MAP is not valid JSON") from None
    from .auth import ROLE_RANK
    bad = [v for v in mapping.values() if v not in ROLE_RANK]
    if not isinstance(mapping, dict) or bad:
        raise OIDCError(f"CLINLOOP_OIDC_ROLE_MAP maps to unknown roles: {bad}")
    return mapping


def verify(token: str) -> Dict[str, str]:
    """{name, role} for a valid provider token; OIDCError otherwise."""
    import jwt
    from .auth import ROLE_RANK
    cfg = discovery()
    algorithms = [a for a in (cfg.get("id_token_signing_alg_values_supported") or ASYMMETRIC_ALGORITHMS)
                  if a in ASYMMETRIC_ALGORITHMS] or ["RS256"]
    audience = os.environ.get("CLINLOOP_OIDC_AUDIENCE") or os.environ.get("CLINLOOP_OIDC_CLIENT_ID")
    try:
        claims = jwt.decode(token, _signing_key(token), algorithms=algorithms, audience=audience,
                            issuer=cfg["issuer"], leeway=LEEWAY_SECONDS,
                            options={"require": ["exp", "iat", "iss", "aud"]})
    except jwt.PyJWTError as e:
        raise OIDCError(f"Token not accepted ({type(e).__name__})") from None
    name = None
    for key in filter(None, [os.environ.get("CLINLOOP_OIDC_USER_CLAIM"), "preferred_username", "email", "sub"]):
        value = _claim(claims, key)
        if isinstance(value, str) and value.strip():
            name = value.strip()[:64]
            break
    held = _claim(claims, os.environ.get("CLINLOOP_OIDC_ROLE_CLAIM") or "roles")
    held = [held] if isinstance(held, str) else (held if isinstance(held, list) else [])
    mapping = role_map()
    roles = [mapping[g] for g in held if isinstance(g, str) and g in mapping]
    if not name:
        raise OIDCError("The token names no user")
    if not roles:
        raise OIDCError("Signed in, but no ClinLoop role is assigned to this account", no_role=True)
    return {"name": name, "role": max(roles, key=lambda r: ROLE_RANK[r])}


def web_config() -> Optional[Dict[str, Any]]:
    """What the pages need to start a sign-in (public values only), or None when not configured."""
    if not enabled():
        return None
    try:
        cfg = discovery()
    except OIDCError as e:
        logger.error("Single sign-on unavailable: %s", e)
        return None
    out = {"client_id": os.environ["CLINLOOP_OIDC_CLIENT_ID"],
           "authorization_endpoint": cfg.get("authorization_endpoint"),
           "token_endpoint": cfg.get("token_endpoint"),
           "end_session_endpoint": cfg.get("end_session_endpoint"),
           "scope": os.environ.get("CLINLOOP_OIDC_SCOPE") or "openid profile",
           "send": "id_token" if os.environ.get("CLINLOOP_OIDC_SEND") == "id_token" else "access_token"}
    if not out["authorization_endpoint"] or not out["token_endpoint"]:
        logger.error("Single sign-on unavailable: the provider publishes no authorization or token endpoint")
        return None
    return out


def reset_cache() -> None:
    """For tests and after a configuration change."""
    with _lock:
        _discovery.update(config=None, fetched=0.0, issuer=None)
        _jwks_clients.clear()
