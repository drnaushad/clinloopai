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
"""

import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Dict, Optional

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
    return tokens


_TOKENS = _load_tokens()
_bearer = HTTPBearer(auto_error=False)


def authenticate(token: str) -> Optional[User]:
    for known, user in _TOKENS.items():
        if hmac.compare_digest(known, token):   # constant-time comparison
            return user
    return None


def require_role(minimum: str):
    """FastAPI dependency: the caller must hold at least `minimum` role."""
    def dependency(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> User:
        user = authenticate(creds.credentials) if creds else None
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid bearer token",
                                headers={"WWW-Authenticate": "Bearer"})
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role '{minimum}' or higher")
        return user
    return dependency
