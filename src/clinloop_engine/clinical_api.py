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

from . import governance
from .auth import ROLE_RANK, User, require_role
from .clinical_ontology import OBLIGATION_RULES, RULE_NAMES_KO, format_window
from .fhir_ingest import bundle_to_events, patient_strata
from .loop_detector import ClinLoopDetector, hospital_detector, lapse_after_death
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


class OutreachDraftRequest(BaseModel):
    language: str = Field("ko", description="ko | en")
    channel: str = Field("kakao", description="kakao | sms")
    scheduling_link: Optional[str] = None


class RuleReviewRequest(BaseModel):
    decision: str = Field(..., description="approve | reject | request_changes")
    specialty: str = Field(..., description="Reviewer's specialty, e.g. 'Radiology (thoracic)'")
    fingerprint: str = Field(..., description="Fingerprint of the rule version reviewed (from /governance/rules)")
    note: str = ""


class CriticalListApprovalRequest(BaseModel):
    title: str = Field(..., description="Approver's title, e.g. 'Chair, Department of Radiology'")
    content_hash: str = Field(..., description="Hash of the list version approved (from /governance/critical-findings)")
    note: str = ""


class OutreachDecisionRequest(BaseModel):
    approve: bool
    text: Optional[str] = Field(None, description="Edited text to send instead of the draft")
    note: str = ""


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
    signoff = governance.all_rule_statuses(get_store())
    return {"rules": [{
        "rule_id": r.rule_id, "name": r.name, "name_ko": RULE_NAMES_KO.get(r.rule_id, r.name),
        "description": r.description, "patient_outreach": r.patient_outreach,
        "trigger_event": r.trigger_event.value, "trigger_condition": r.trigger_condition,
        "required_followups": [f.value for f in r.required_followups], "followup_logic": r.followup_logic,
        "deadline": format_window(r.deadline_days), "deadline_days": r.deadline_days,
        "severity": r.severity.value, "domain": r.clinical_domain, "ltl_formula": r.ltl_formula,
        "references": r.references, "review_status": r.review_status, "evidence_note": r.evidence_note,
        "signoff": {k: signoff[r.rule_id][k] for k in ("status", "approvals", "approvals_required", "fingerprint")},
    } for r in OBLIGATION_RULES]}


# ── Governance: specialist sign-off and critical-finding list approval ──────
# Reading the status is public (it contains no patient data); deciding needs a clinician.

@router.get("/governance/summary", tags=["Governance"])
def governance_summary():
    return governance.summary(get_store())


@router.get("/governance/rules", tags=["Governance"])
def governance_rules():
    statuses = governance.all_rule_statuses(get_store())
    rules = {r.rule_id: r for r in OBLIGATION_RULES}
    return {"approvals_required": governance.approvals_required(),
            "enforce_signoff": governance.enforcement_enabled(),
            "rules": [{**s, "name": rules[rid].name, "name_ko": RULE_NAMES_KO.get(rid, rules[rid].name),
                       "domain": rules[rid].clinical_domain, "severity": rules[rid].severity.value,
                       "description": rules[rid].description, "ltl_formula": rules[rid].ltl_formula,
                       "deadline": format_window(rules[rid].deadline_days),
                       "required_followups": [f.value for f in rules[rid].required_followups],
                       "followup_logic": rules[rid].followup_logic,
                       "references": rules[rid].references, "evidence_note": rules[rid].evidence_note}
                      for rid, s in statuses.items()]}


@router.post("/governance/rules/{rule_id}/review", tags=["Governance"])
def review_rule(rule_id: str, req: RuleReviewRequest, user: User = Depends(require_role("clinician"))):
    """A named specialist approves, rejects or requests changes to the current version of a rule."""
    rule = next((r for r in OBLIGATION_RULES if r.rule_id == rule_id), None)
    if rule is None:
        raise HTTPException(404, f"Unknown rule {rule_id}")
    current = governance.rule_fingerprint(rule)
    if req.fingerprint != current:
        raise HTTPException(409, "The rule has changed since you opened it: reload and review the current version")
    _workflow(get_store().add_rule_review, rule_id, current, req.decision, user.name, user.role,
              req.specialty, req.note)
    return governance.all_rule_statuses(get_store())[rule_id]


@router.get("/governance/rule-check", tags=["Governance"])
def rule_check():
    """Can every rule fire on hospital data, and can every loop be closed? (Static check of the rule set.)"""
    from .rule_check import check_rules
    return check_rules()


@router.get("/governance/critical-findings", tags=["Governance"])
def critical_findings():
    return governance.critical_list_status(get_store())


@router.post("/governance/critical-findings/approve", tags=["Governance"])
def approve_critical_findings(req: CriticalListApprovalRequest, user: User = Depends(require_role("clinician"))):
    """Approve the active critical-finding list (bound to its content hash)."""
    current = governance.critical_list_status(get_store())["content_hash"]
    if req.content_hash != current:
        raise HTTPException(409, "The critical-finding list has changed: reload and review the current version")
    _workflow(get_store().add_config_approval, governance.CRITICAL_FINDINGS_KIND, current, user.name, user.role,
              req.title, req.note)
    return governance.critical_list_status(get_store())


# ── Connections and live evidence (public: no patient data, no secrets) ─────

@router.get("/connections/status", tags=["Connections"])
def connections_status():
    """
    What ClinLoop is really connected to, checked live (cached for 5 minutes).
    Only service health is returned: no hostnames, credentials or patient data.
    """
    from . import biomcp_client, literature
    from .local_llm_engine import get_available_models

    cached = literature._cache.get("health|local_llm", literature.HEALTH_TTL)
    if cached is None:
        models = get_available_models()
        cached = {"status": "ok" if models else "unavailable",
                  "model": models[0]["name"] if models else None}
        literature._cache.put("health|local_llm", cached)

    fhir_configured = bool(os.environ.get("CLINLOOP_FHIR_BASE"))
    return {
        "clinloop_api": {"status": "ok"},
        "biomcp": {k: v for k, v in biomcp_client.status().items() if k != "error"},
        "pubmed": literature.pubmed_status(),
        "europe_pmc": literature.europepmc_status(),
        "fhir_server": {"status": "configured" if fhir_configured else "not_configured",
                        "feed": get_store().feed_status(_max_silence_hours())["status"]},
        "local_llm": cached,
        "cloud_llm": {"status": "not_used", "note": "This build uses only the on-premise LLM"},
        "pacs": {"status": "configured" if os.environ.get("CLINLOOP_PACS_DICOMWEB") else "not_configured",
                 "note": "Study labels only (DICOMweb QIDO-RS); no pixel data"},
        "imaging_ai": _imaging_ai_status(),
        "omop_cdm": {"status": "not_connected", "note": "No OMOP database is connected"},
        "ehr_writeback": {"status": "not_connected", "note": "Read-only by design; FHIR Tasks are previews"},
        "guideline_library": {"status": "static", "rules": len(OBLIGATION_RULES),
                              "note": "Curated rule and guideline library in code"},
    }


def _imaging_ai_status() -> Dict[str, Any]:
    from .imaging_ai import registered_models
    models = registered_models()
    ready = [m.name for m in models if m.available() is None]
    return {"status": "ok" if ready else ("not_ready" if models else "not_configured"), "models": ready,
            "note": "Second reader only: findings open radiologist-review loops, never a diagnosis"}


@router.get("/evidence/{rule_id}", tags=["Connections"])
def rule_evidence(rule_id: str, source: str = Query("pubmed", pattern="^(pubmed|europepmc|biomcp)$"),
                  limit: int = Query(5, ge=1, le=20)):
    """Live literature for one rule from PubMed, Europe PMC or BioMCP (rule-level query only)."""
    from .literature import LiteratureError, evidence_for_rule
    from .biomcp_client import BioMCPError, rule_articles
    try:
        if source == "biomcp":
            return rule_articles(rule_id)
        return evidence_for_rule(rule_id, source, limit)
    except BioMCPError as e:
        raise HTTPException(502, f"BioMCP unreachable: {e}")
    except KeyError:
        raise HTTPException(404, f"Unknown rule {rule_id}")
    except LiteratureError as e:
        raise HTTPException(502, f"{'Europe PMC' if source == 'europepmc' else 'PubMed'} unreachable: {e}")


# ── Ingest ───────────────────────────────────────────────────────────────────

@router.post("/fhir/ingest", tags=["Clinical Pilot"])
def ingest_fhir(bundle: Dict[str, Any] = Body(..., description="FHIR R4 Bundle"),
                evaluation_time: Optional[str] = Query(None, description="ISO time to evaluate at (default: now)"),
                user: User = Depends(require_role("admin"))):
    """Map a FHIR Bundle to events, run the engine, and record every loop."""
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(422, "Body must be a FHIR Bundle")
    when = normalize_timestamp(evaluation_time) if evaluation_time else None
    store = get_store()
    # Keep each patient's records, so later uploads (outside reports, DICOM) are judged in context
    from .fhir_ingest import _patient_id, _resources
    by_patient: Dict[str, list] = {}
    for r in _resources(bundle):
        pid = r.get("id") if r.get("resourceType") == "Patient" else _patient_id(r)
        if pid:
            by_patient.setdefault(pid, []).append(r)
    from .fhir_sync import patient_record
    from .pacs_client import client_from_env as pacs_from_env
    pacs = pacs_from_env()
    resources, record_warnings = [], []
    for pid, items in by_patient.items():
        store.save_snapshot(pid, items)
        # the snapshot just saved, plus uploads and the PACS's studies for this patient
        record, w = patient_record(pid, store, None, pacs)
        resources += record
        record_warnings += w
    events_by_patient, warnings = bundle_to_events(resources)
    warnings += record_warnings
    strata = patient_strata(bundle)
    detector = hospital_detector(when)
    detections = []
    for pid, events in events_by_patient.items():
        detections.extend(lapse_after_death(detector.process_patient("fhir-ingest", pid, events), resources))
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
    store = get_store()
    loops = store.worklist(owner=owner, include_inactive=include_inactive)
    statuses = governance.all_rule_statuses(store)
    for loop in loops:
        loop["rule_signoff"] = statuses.get(loop["rule_id"], {}).get("status", "pending")
    live = governance.live_rule_ids(store)
    shadow = 0
    if live is not None:
        shadow = sum(1 for loop in loops if loop["rule_id"] not in live)
        loops = [loop for loop in loops if loop["rule_id"] in live]
    return {"count": len(loops), "loops": loops, "defer_reasons": DEFER_REASONS,
            "shadow_count": shadow, "governance": governance.summary(store)}


@router.get("/loops/{loop_key:path}/audit", tags=["Clinical Pilot"])
def loop_audit(loop_key: str, user: User = Depends(require_role("viewer"))):
    return {"loop_key": loop_key, "audit": get_store().audit_trail(loop_key)}


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


# ── Patient outreach ─────────────────────────────────────────────────────────

@router.get("/loops/{loop_key:path}/outreach", tags=["Patient Outreach"])
def list_outreach(loop_key: str, user: User = Depends(require_role("viewer"))):
    return {"messages": get_store().outreach_messages(loop_key)}


@router.post("/loops/{loop_key:path}/outreach", tags=["Patient Outreach"])
def draft_outreach(loop_key: str, req: OutreachDraftRequest, user: User = Depends(require_role("navigator"))):
    """Draft a diagnosis-free message to the patient. Nothing is sent until a clinician approves it."""
    from .outreach import OutreachNotAllowed, draft_message
    if req.channel not in ("kakao", "sms"):
        raise HTTPException(422, "channel must be 'kakao' or 'sms'")
    loop = _workflow(get_store().get, loop_key)
    try:
        draft = draft_message(loop, req.language, req.scheduling_link)
    except OutreachNotAllowed as e:
        raise HTTPException(409, str(e))
    return _workflow(get_store().add_outreach_draft, loop_key, user.name, user.role,
                     draft["text"], draft["language"], req.channel, draft["safety_flags"])


@router.post("/outreach/{message_id}/decision", tags=["Patient Outreach"])
def decide_outreach(message_id: str, req: OutreachDecisionRequest,
                    user: User = Depends(require_role("clinician"))):
    """A clinician approves (optionally editing the text) and sends, or rejects, a draft."""
    from .outreach import OutreachNotAllowed, check_text, provider_from_env
    if req.approve:
        msg = _workflow(get_store().get_outreach, message_id)
        try:
            check_text(req.text if req.text is not None else msg["draft_text"])
        except OutreachNotAllowed as e:
            raise HTTPException(422, str(e))
    return _workflow(get_store().decide_outreach, message_id, user.name, user.role, req.approve,
                     final_text=req.text, provider=provider_from_env() if req.approve else None, note=req.note)


# ── Metrics, escalation, audit ───────────────────────────────────────────────

@router.get("/metrics/open-loop-rate", tags=["Clinical Pilot"])
def open_loop_rate(stratify_by: Optional[str] = Query(None, description="rule | age_group | language | sex"),
                   user: User = Depends(require_role("viewer"))):
    return get_store().open_loop_rate(stratify_by=stratify_by)


@router.get("/metrics/breakdowns", tags=["Clinical Pilot"])
def breakdowns(user: User = Depends(require_role("viewer"))):
    """Where follow-up breaks, hospital-wide: per rule, per owner (workload), per equity stratum, and bottlenecks."""
    return get_store().breakdowns()


@router.post("/watchdog/escalate", tags=["Clinical Pilot"])
def escalate_now(user: User = Depends(require_role("admin"))):
    store = get_store()
    return {"escalated": store.escalate_overdue(actor=user.name, rule_ids=governance.live_rule_ids(store))}


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


# Must be the last /loops/{key} GET route: the greedy path parameter would
# otherwise swallow /loops/{key}/audit and /loops/{key}/outreach.
@router.get("/loops/{loop_key:path}", tags=["Clinical Pilot"])
def get_loop(loop_key: str, user: User = Depends(require_role("viewer"))):
    return _workflow(get_store().get, loop_key)


async def escalation_loop(interval_seconds: int = 60):
    """Background escalation of unacknowledged overdue loops, and the feed-silence alarm."""
    while True:
        try:
            store = get_store()
            escalated = store.escalate_overdue(rule_ids=governance.live_rule_ids(store))
            if escalated:
                logger.warning("Escalated %d overdue loops", len(escalated))
            alarm = get_store().check_feed(_max_silence_hours())
            if alarm:
                logger.critical("CLINICAL DATA FEED %s: last success %s. The worklist may be incomplete.",
                                alarm["status"], alarm["last_success"])
        except Exception as e:  # never let the safety loop die silently
            logger.error("Escalation loop error: %s", e)
        await asyncio.sleep(interval_seconds)
