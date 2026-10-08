"""
clinical_api.py — Pilot endpoints: FHIR ingest, worklist, workflow, metrics

Mounted by api.py. Every endpoint touching patient data requires a bearer
token (see auth.py); every state change is written to the hash-chained
audit log in loop_store.py.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import ROLE_RANK, User, require_role
from .clinical_ontology import OBLIGATION_RULES, format_window
from .fhir_ingest import bundle_to_events, patient_strata
from .loop_detector import ClinLoopDetector
from .loop_store import DEFER_REASONS, LoopStore, WorkflowError
from .safety_clock import normalize_timestamp

logger = logging.getLogger("clinloop.clinical_api")

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "clinloop.db")
_store: Optional[LoopStore] = None

# Deferral reasons a navigator may record; the rest are clinical judgments
NAVIGATOR_DEFER_REASONS = {"completed_elsewhere", "patient_declined", "duplicate", "patient_deceased"}


def get_store() -> LoopStore:
    global _store
    if _store is None:
        _store = LoopStore(os.environ.get("CLINLOOP_DB", DEFAULT_DB))
    return _store


def set_store(store: LoopStore) -> None:
    """Swap the store (tests, or a deployment wiring its own database)."""
    global _store
    _store = store


router = APIRouter(prefix="/api/v1")


class DeferRequest(BaseModel):
    reason_code: str = Field(..., description=f"One of: {', '.join(DEFER_REASONS)}")
    note: str = ""
    until: Optional[str] = Field(None, description="ISO date when the loop should resurface")


class CloseRequest(BaseModel):
    evidence: str = Field(..., description="What closed the loop, e.g. order or visit reference")


class AssignRequest(BaseModel):
    owner: str


def _workflow(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError:
        raise HTTPException(404, "Loop not found")
    except WorkflowError as e:
        raise HTTPException(409, str(e))


# ── Rules (public: the rule library is meant to be open) ────────────────────

@router.get("/rules", tags=["Rule Library"])
def list_rules():
    return {"rules": [{
        "rule_id": r.rule_id, "name": r.name, "description": r.description,
        "trigger_event": r.trigger_event.value, "trigger_condition": r.trigger_condition,
        "required_followups": [f.value for f in r.required_followups], "followup_logic": r.followup_logic,
        "deadline": format_window(r.deadline_days), "deadline_days": r.deadline_days,
        "severity": r.severity.value, "domain": r.clinical_domain, "ltl_formula": r.ltl_formula,
        "references": r.references, "review_status": r.review_status, "evidence_note": r.evidence_note,
    } for r in OBLIGATION_RULES]}


# ── Ingest ───────────────────────────────────────────────────────────────────

@router.post("/fhir/ingest", tags=["Clinical Pilot"])
def ingest_fhir(bundle: Dict[str, Any] = Body(..., description="FHIR R4 Bundle"),
                evaluation_time: Optional[str] = Query(None, description="ISO time to evaluate at (default: now)"),
                user: User = Depends(require_role("admin"))):
    """Map a FHIR Bundle to events, run the engine, and record every loop."""
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(422, "Body must be a FHIR Bundle")
    when = normalize_timestamp(evaluation_time) if evaluation_time else None
    events_by_patient, warnings = bundle_to_events(bundle)
    strata = patient_strata(bundle)
    detector = ClinLoopDetector(evaluation_time=when)
    detections = []
    for pid, events in events_by_patient.items():
        detections.extend(detector.process_patient("fhir-ingest", pid, events))
    store = get_store()
    counts = store.upsert_detections(detections, strata=strata, actor=user.name)
    store.record_ingest("manual-upload", user.name, ok=True, patients=len(events_by_patient),
                        events=sum(len(v) for v in events_by_patient.values()), warnings=len(warnings))
    return {
        "patients": len(events_by_patient),
        "events": sum(len(v) for v in events_by_patient.values()),
        "loops": counts,
        "active_loops": sum(1 for d in detections if d.loop_status in ("open", "needs_human_review")),
        "warnings": warnings,
    }


# ── Worklist and loops ───────────────────────────────────────────────────────

@router.get("/me", tags=["Clinical Pilot"])
def whoami(user: User = Depends(require_role("viewer"))):
    return {"user": user.name, "role": user.role}


@router.get("/worklist", tags=["Clinical Pilot"])
def worklist(owner: Optional[str] = None, include_inactive: bool = False,
             user: User = Depends(require_role("viewer"))):
    loops = get_store().worklist(owner=owner, include_inactive=include_inactive)
    return {"count": len(loops), "loops": loops, "defer_reasons": DEFER_REASONS}


@router.get("/loops/{loop_key:path}/audit", tags=["Clinical Pilot"])
def loop_audit(loop_key: str, user: User = Depends(require_role("viewer"))):
    return {"loop_key": loop_key, "audit": get_store().audit_trail(loop_key)}


@router.get("/loops/{loop_key:path}", tags=["Clinical Pilot"])
def get_loop(loop_key: str, user: User = Depends(require_role("viewer"))):
    return _workflow(get_store().get, loop_key)


@router.post("/loops/{loop_key:path}/acknowledge", tags=["Clinical Pilot"])
def acknowledge(loop_key: str, user: User = Depends(require_role("navigator"))):
    return _workflow(get_store().acknowledge, loop_key, user.name, role=user.role)


@router.post("/loops/{loop_key:path}/defer", tags=["Clinical Pilot"])
def defer(loop_key: str, req: DeferRequest, user: User = Depends(require_role("navigator"))):
    if req.reason_code not in NAVIGATOR_DEFER_REASONS and ROLE_RANK[user.role] < ROLE_RANK["clinician"]:
        raise HTTPException(403, f"Reason '{req.reason_code}' is a clinical judgment and requires a clinician")
    return _workflow(get_store().defer, loop_key, user.name, req.reason_code, req.note, req.until, role=user.role)


@router.post("/loops/{loop_key:path}/close", tags=["Clinical Pilot"])
def close(loop_key: str, req: CloseRequest, user: User = Depends(require_role("navigator"))):
    return _workflow(get_store().close, loop_key, user.name, req.evidence, role=user.role)


@router.post("/loops/{loop_key:path}/assign", tags=["Clinical Pilot"])
def assign(loop_key: str, req: AssignRequest, user: User = Depends(require_role("clinician"))):
    return _workflow(get_store().assign, loop_key, req.owner, user.name, role=user.role)


# ── Metrics, escalation, audit ───────────────────────────────────────────────

@router.get("/metrics/open-loop-rate", tags=["Clinical Pilot"])
def open_loop_rate(stratify_by: Optional[str] = Query(None, description="rule | age_group | language | sex"),
                   user: User = Depends(require_role("viewer"))):
    return get_store().open_loop_rate(stratify_by=stratify_by)


@router.post("/watchdog/escalate", tags=["Clinical Pilot"])
def escalate_now(user: User = Depends(require_role("admin"))):
    return {"escalated": get_store().escalate_overdue(actor=user.name)}


def _max_silence_hours() -> float:
    return float(os.environ.get("CLINLOOP_FEED_MAX_SILENCE_HOURS", "24"))


@router.get("/feed/status", tags=["Clinical Pilot"])
def feed_status(user: User = Depends(require_role("viewer"))):
    """Is clinical data still arriving? STALE / FAILING / NEVER mean the worklist cannot be trusted."""
    return get_store().feed_status(_max_silence_hours())


@router.post("/fhir/sync", tags=["Clinical Pilot"])
def sync_now(user: User = Depends(require_role("admin"))):
    """Run one sync from the configured FHIR server (CLINLOOP_FHIR_BASE)."""
    from .fhir_sync import client_from_env, sync_once
    client = client_from_env()
    if client is None:
        raise HTTPException(503, "No FHIR server configured (set CLINLOOP_FHIR_BASE)")
    return sync_once(get_store(), client)


@router.get("/audit/verify", tags=["Clinical Pilot"])
def verify_audit(user: User = Depends(require_role("admin"))):
    ok = get_store().verify_audit_chain()
    return {"audit_chain_intact": ok}


async def escalation_loop(interval_seconds: int = 60):
    """Background escalation of unacknowledged overdue loops, and the feed-silence alarm."""
    while True:
        try:
            escalated = get_store().escalate_overdue()
            if escalated:
                logger.warning("Escalated %d overdue loops", len(escalated))
            alarm = get_store().check_feed(_max_silence_hours())
            if alarm:
                logger.critical("CLINICAL DATA FEED %s: last success %s. The worklist may be incomplete.",
                                alarm["status"], alarm["last_success"])
        except Exception as e:  # never let the safety loop die silently
            logger.error("Escalation loop error: %s", e)
        await asyncio.sleep(interval_seconds)
