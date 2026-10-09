"""
cds_hooks.py — Open loops inside the EHR, through CDS Hooks (HL7 CDS Hooks 2.0)

Clinicians work in their EHR, not on a separate website. CDS Hooks is the HL7 standard that Epic,
Oracle Health (Cerner) and other EHRs use to show decision-support "cards" in the chart. With this
service registered, opening a patient's chart (the `patient-view` hook) shows that patient's open
follow-up obligations, each with what is missing, the deadline, the rule and its evidence, and a link
to act on it in the ClinLoop worklist.

  GET  /cds-services                                  discovery (public, as the standard requires)
  POST /cds-services/clinloop-open-loops              patient-view: cards for the patient's open loops
  POST /cds-services/clinloop-open-loops/feedback     card accepted / overridden (recorded in the audit log)

Safety and governance:
  - Read-only: a card never changes a loop, an order or the chart. Acting happens in the worklist.
  - Only rules a specialist has signed off are shown when sign-off is enforced (shadow-mode rules stay silent).
  - Deferred and closed loops are not shown; at most CLINLOOP_CDS_MAX_CARDS cards (default 5), most
    dangerous first, then one summary card for the rest, so a chart never fills with alerts.

Authentication (the EHR is the client):
  - CDS Hooks JWT: the EHR signs a JWT (RS384/ES384) for each call. Only EHRs listed in
    CLINLOOP_CDS_CLIENTS are trusted, with their key set from the configured URL (never from the token's
    own `jku`):  CLINLOOP_CDS_CLIENTS='[{"iss": "https://ehr.hospital.local", "jwks_url": "https://…/jwks"}]'
    ("jwks" may hold the key set inline for an air-gapped site). The audience must be this service's URL
    (CLINLOOP_CDS_AUDIENCE when behind a proxy); tokens are short-lived and used once.
  - Or a ClinLoop API token (viewer role or higher), for EHRs or tests without JWT support.
"""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request

from . import governance
from .auth import authenticate
from .clinical_api import get_store
from .safety_clock import normalize_timestamp, utc_now

logger = logging.getLogger("clinloop.cds_hooks")

SERVICE_ID = "clinloop-open-loops"
ALGORITHMS = ["RS384", "ES384", "RS256", "ES256"]
INDICATOR = {"critical": "critical", "high": "warning"}       # anything else: info

router = APIRouter(tags=["CDS Hooks (EHR integration)"])

_seen_jti: Dict[str, float] = {}
_jti_lock = threading.Lock()


def _clients() -> List[Dict[str, Any]]:
    raw = os.environ.get("CLINLOOP_CDS_CLIENTS", "").strip()
    if not raw:
        return []
    try:
        clients = json.loads(raw)
    except ValueError:
        logger.error("CLINLOOP_CDS_CLIENTS is not valid JSON; no EHR is trusted")
        return []
    return [c for c in clients if isinstance(c, dict) and c.get("iss") and (c.get("jwks_url") or c.get("jwks"))]


def _signing_key(client: Dict[str, Any], token: str):
    import jwt
    if client.get("jwks"):
        kid = jwt.get_unverified_header(token).get("kid")
        keys = jwt.PyJWKSet.from_dict(client["jwks"]).keys
        for k in keys:
            if kid is None or k.key_id == kid:
                return k.key
        raise jwt.InvalidTokenError("no matching key in the configured key set")
    return jwt.PyJWKClient(client["jwks_url"], cache_keys=True).get_signing_key_from_jwt(token).key


def _check_jwt(token: str, audience: str) -> Optional[str]:
    """The trusted EHR's issuer if the CDS Hooks JWT is valid, else None."""
    import jwt
    try:
        iss = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.InvalidTokenError:
        return None
    client = next((c for c in _clients() if c["iss"] == iss), None)
    if client is None:
        return None
    try:
        claims = jwt.decode(token, _signing_key(client, token), algorithms=ALGORITHMS, audience=audience,
                            issuer=iss, options={"require": ["exp", "iat", "jti", "iss", "aud"]}, leeway=30)
    except (jwt.InvalidTokenError, jwt.PyJWKClientError, ValueError) as e:
        logger.warning("CDS Hooks JWT rejected: %s", type(e).__name__)
        return None
    if claims["exp"] - claims["iat"] > 600:          # the standard asks for tokens of at most 5 minutes
        return None
    with _jti_lock:                                   # each token once
        now = time.time()
        for k in [k for k, exp in _seen_jti.items() if exp < now]:
            _seen_jti.pop(k)
        if claims["jti"] in _seen_jti:
            return None
        _seen_jti[claims["jti"]] = claims["exp"] + 60
    return iss


def _caller(request: Request) -> str:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(401, "CDS Hooks call without a bearer token", headers={"WWW-Authenticate": "Bearer"})
    user = authenticate(token)
    if user is not None:
        return f"api:{user.name}"
    audience = os.environ.get("CLINLOOP_CDS_AUDIENCE") or str(request.url).split("?")[0]
    iss = _check_jwt(token, audience)
    if iss is None:
        raise HTTPException(401, "Untrusted or invalid CDS Hooks token", headers={"WWW-Authenticate": "Bearer"})
    return f"ehr:{iss}"


@router.get("/cds-services")
def discovery() -> Dict[str, Any]:
    return {"services": [{
        "hook": "patient-view",
        "id": SERVICE_ID,
        "title": "ClinLoop open follow-ups",
        "description": ("Follow-up obligations for this patient that are still open: abnormal results not acted on, "
                        "imaging follow-up due, referrals not completed. Each card shows the rule, the deadline and "
                        "the evidence."),
        "usageRequirements": "Read-only. Shows only rules a specialist has signed off when sign-off is enforced.",
    }]}


def _days_overdue(deadline: Optional[str], now: datetime) -> Optional[int]:
    if not deadline:
        return None
    try:
        return (now - normalize_timestamp(deadline)).days
    except (TypeError, ValueError):
        return None


# Plain words for the engine's event names in "what is missing"
_PLAIN = {
    "critical_value_notification": "documented call to the treating clinician",
    "followup_ct": "follow-up CT", "followup_lab": "monitoring lab", "followup_appointment": "clinic visit",
    "referral_visit": "specialist visit", "specialist_referral": "specialist referral", "bp_check": "blood-pressure check",
    "inr_recheck": "INR recheck", "hba1c_recheck": "HbA1c recheck", "hcv_rna_test": "HCV RNA test",
    "imaging_ct": "CT", "imaging_mri": "MRI", "imaging_ultrasound": "ultrasound", "imaging_xray": "X-ray",
    "imaging_pet": "PET-CT", "lab_result": "repeat test", "culture_result": "repeat culture",
    "patient_notification": "patient notified", "provider_review": "clinician review",
}


def _plain(text: str) -> str:
    out = re.sub(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b", lambda m: _PLAIN.get(m.group(0), m.group(0).replace("_", " ")), text or "")
    return re.sub(r"^Missing:\s*", "Not yet recorded: ", out)


def _source_line(loop: Dict[str, Any]) -> Optional[str]:
    """What started the obligation, in the record's own words (never a raw data dump)."""
    first = next((e for e in (loop.get("evidence_chain") or []) if isinstance(e, str) and e.startswith("Trigger:")), "")
    m = re.match(r"Trigger: (\w+) at (\S+)", first)
    if not m:
        return None
    quote = None
    for key in ("conclusion", "evidence_span", "medication", "test", "primary_diagnosis", "order"):
        q = re.search(rf"'{key}': '((?:[^'\\]|\\.)*)'", first)
        if q and q.group(1).strip():
            quote = q.group(1).strip()
            break
    when = m.group(2).replace("T", " ")[:16]
    if quote and len(quote) > 220:
        quote = quote[:220].rsplit(" ", 1)[0] + " …"
    return f"{_plain(m.group(1))}, {when}" + (f": “{quote}”" if quote else "")


def _card(loop: Dict[str, Any], base: str, now: datetime) -> Dict[str, Any]:
    overdue = _days_overdue(loop.get("deadline"), now)
    when = (f"overdue by {overdue} day{'s' if overdue != 1 else ''}" if overdue and overdue > 0 else
            f"due {str(loop.get('deadline'))[:10]}" if loop.get("deadline") else "")
    missing = _plain(loop.get("missing_step") or "Follow-up not yet recorded")
    summary = f"{loop.get('rule_name') or loop['rule_id']}: {missing}"
    source = _source_line(loop)
    # No stored risk wording here: it was computed at import and may be stale; the deadline is current
    detail = "\n".join(
        [f"**{missing}** ({when})." if when else f"**{missing}**.",
         *(["", f"From: {source}"] if source else []),
         "", f"Rule {loop['rule_id']}: {loop.get('rule_name') or ''}. A reminder of a follow-up obligation, "
             "not a diagnosis. If it was done elsewhere or is not needed, record that in ClinLoop."])
    link = f"{base}/worklist.html#loop={loop['loop_key']}" if base else None
    card = {
        "uuid": f"{loop['loop_key']}",
        "summary": summary[:140],
        "indicator": INDICATOR.get(str(loop.get("severity")), "info"),
        "detail": detail,
        "source": {"label": f"ClinLoop AI · rule {loop['rule_id']}", "topic": {"code": loop["rule_id"],
                                                                             "display": loop.get("rule_name")}},
        "overrideReasons": [
            {"code": "completed_elsewhere", "display": "Done elsewhere"},
            {"code": "not_indicated", "display": "Not clinically indicated"},
            {"code": "patient_declined", "display": "Patient declined"},
        ],
    }
    if link:
        card["source"]["url"] = link
        card["links"] = [{"label": "Open in ClinLoop worklist", "url": link, "type": "absolute"}]
    return card


@router.post(f"/cds-services/{SERVICE_ID}")
def patient_view(request: Request, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    caller = _caller(request)
    if body.get("hook") != "patient-view":
        raise HTTPException(400, "This service answers the patient-view hook")
    patient_id = str((body.get("context") or {}).get("patientId") or "").strip()
    if not patient_id:
        raise HTTPException(400, "context.patientId is required")
    store = get_store()
    loops = store.worklist(patient_id=patient_id)
    live = governance.live_rule_ids(store)
    if live is not None:
        loops = [loop for loop in loops if loop["rule_id"] in live]     # shadow-mode rules stay silent
    now = utc_now()
    base = os.environ.get("CLINLOOP_PUBLIC_URL", "").rstrip("/")
    limit = max(1, int(os.environ.get("CLINLOOP_CDS_MAX_CARDS", "5") or 5))
    cards = [_card(loop, base, now) for loop in loops[:limit]]
    if len(loops) > limit:
        more = {"uuid": f"{patient_id}:more", "indicator": "info",
                "summary": f"{len(loops) - limit} more open follow-ups for this patient in ClinLoop",
                "source": {"label": "ClinLoop AI"}}
        if base:
            more["links"] = [{"label": "Open the patient in ClinLoop", "type": "absolute",
                              "url": f"{base}/patient.html#patient={patient_id}"}]
        cards.append(more)
    store.record_audit(caller, "ehr", "cds_patient_view", None,
                       {"patient_id": patient_id, "hook_instance": body.get("hookInstance"),
                        "user": (body.get("context") or {}).get("userId"), "cards": [c["uuid"] for c in cards]})
    return {"cards": cards}


@router.post(f"/cds-services/{SERVICE_ID}/feedback")
def feedback(request: Request, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """What the clinician did with each card. Recorded only: closing a loop needs evidence in the worklist."""
    caller = _caller(request)
    store = get_store()
    items = body.get("feedback") if isinstance(body.get("feedback"), list) else []
    for item in items[:50]:
        if not isinstance(item, dict):
            continue
        reason = ((item.get("overrideReason") or {}).get("reason") or {}).get("code")
        store.record_audit(caller, "ehr", "cds_card_feedback", str(item.get("card") or "")[:200] or None,
                           {"outcome": item.get("outcome"), "override_reason": reason,
                            "comment": str((item.get("overrideReason") or {}).get("userComment") or "")[:500],
                            "at": item.get("outcomeTimestamp")})
    return {}
