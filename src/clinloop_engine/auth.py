"""
auth.py — Bearer-token authentication with clinical roles

Tokens come from the CLINLOOP_API_TOKENS environment variable:

    CLINLOOP_API_TOKENS="tok-abc:dr.lee:clinician,tok-def:nurse.park:navigator,tok-ghi:it.admin:admin"

Roles (each includes the permissions of the ones before it):
    viewer     read the worklist, loops, metrics and rules
    navigator  + acknowledge, close with evidence, defer for logistical reasons
    clinician  + defer for clinical reasons, assign owners
    admin      + ingest data, run escalation, read the full audit log

If CLINLOOP_API_TOKENS is unset, a random admin token is generated for this
process and logged once, so the API is never open by default.

In public demo mode (CLINLOOP_DEMO=1, see demo.py) a published view-only token is
added; it can read only the synthetic demo data and cannot upload or change anything.

With single sign-on configured (oidc.py), tokens issued by the hospital's identity provider are
accepted too; the person's role comes from their groups at the provider.
"""

import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("clinloop.auth")

ROLE_RANK = {"viewer": 0, "navigator": 1, "clinician": 2, "admin": 3}


@dataclass(frozen=True)
class User:
    name: str
    role: str


def _load_tokens() -> Dict[str, User]:
    raw = os.environ.get("CLINLOOP_API_TOKENS", "").strip()
    tokens: Dict[str, User] = {}
    for item in filter(None, (x.strip() for x in raw.split(","))):
        parts = item.split(":")
        if len(parts) != 3 or parts[2] not in ROLE_RANK or len(parts[0]) < 16:
            raise RuntimeError(
                f"Invalid CLINLOOP_API_TOKENS entry '{parts[0][:4]}…': expected token:user:role "
                f"with a token of at least 16 characters and role in {list(ROLE_RANK)}")
        tokens[parts[0]] = User(parts[1], parts[2])
    if not tokens:
        token = secrets.token_urlsafe(24)
        tokens[token] = User("local-admin", "admin")
        logger.warning("CLINLOOP_API_TOKENS not set. Generated a one-time admin token for this process: %s", token)
    if os.environ.get("CLINLOOP_DEMO", "").strip().lower() in ("1", "true", "yes"):
        from .demo import DEMO_TOKEN, DEMO_USER
        tokens[DEMO_TOKEN] = User(DEMO_USER, "viewer")   # published, read-only, synthetic data only
    return tokens


_TOKENS = _load_tokens()
_bearer = HTTPBearer(auto_error=False)


def known_users() -> Dict[str, str]:
    """{user name: role} for every configured person (the read-only public demo account excluded).
    Used to offer real names when a loop is assigned, and to refuse a name nobody signs in with."""
    demo_user = None
    if os.environ.get("CLINLOOP_DEMO", "").strip().lower() in ("1", "true", "yes"):
        from .demo import DEMO_USER
        demo_user = DEMO_USER
    out: Dict[str, str] = {}
    for user in _TOKENS.values():
        if user.name == demo_user:
            continue
        if user.name not in out or ROLE_RANK[user.role] > ROLE_RANK[out[user.name]]:
            out[user.name] = user.role          # one person with several tokens: their highest role
    return out


# People who signed in through the identity provider, so they can be offered when a loop is assigned.
# clinical_api installs a listener that keeps them in the database across restarts.
_sso_listener: Optional[Callable[[User], None]] = None
_sso_seen: Dict[str, float] = {}


def set_sso_listener(listener: Optional[Callable[[User], None]]) -> None:
    global _sso_listener
    _sso_listener = listener


def _remember(user: User) -> None:
    if _sso_listener is None or time.time() - _sso_seen.get(user.name, 0) < 600:
        return
    _sso_seen[user.name] = time.time()
    try:
        _sso_listener(user)
    except Exception:            # remembering a name must never stop a sign-in
        logger.exception("Could not record a single sign-on user")


class NoRole(Exception):
    """A valid hospital sign-in without any ClinLoop role."""


def authenticate(token: str) -> Optional[User]:
    for known, user in _TOKENS.items():
        if hmac.compare_digest(known, token):   # constant-time comparison
            return user
    from . import oidc
    if oidc.enabled() and token.count(".") == 2:
        try:
            who = oidc.verify(token)
        except oidc.OIDCError as e:
            if e.no_role:
                raise NoRole(str(e)) from None
            logger.info("Single sign-on token refused: %s", e)
            return None
        user = User(who["name"], who["role"])
        _remember(user)
        return user
    return None


def require_role(minimum: str):
    """FastAPI dependency: the caller must hold at least `minimum` role."""
    def dependency(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> User:
        try:
            user = authenticate(creds.credentials) if creds else None
        except NoRole as e:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid bearer token",
                                headers={"WWW-Authenticate": "Bearer"})
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role '{minimum}' or higher")
        return user
    return dependency
