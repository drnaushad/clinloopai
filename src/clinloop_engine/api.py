"""
ClinLoop AI - FastAPI Backend Service (clinical edition by default; research features need CLINLOOP_PROFILE=research)
Exposes REST endpoints for the web cockpit. Runs on synthetic data only.

Run from the repository root:
    uvicorn src.clinloop_engine.api:app --host 127.0.0.1 --port 8124
"""

from src.clinloop_engine.compute import compute_status
from src.clinloop_engine.local_llm_engine import (
    get_engine_status as get_local_llm_status,
    get_best_model,
    generate_kakao_message as llm_generate_kakao,
    generate_differential_diagnosis as llm_generate_diff,
    generate_ethics_review as llm_generate_ethics,
    generate_clinical_text,
)

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import json
import logging
import os
import time

from src.clinloop_engine.counterfactual_engine import get_counterfactual_analysis
from src.clinloop_engine.patient_outreach_agent import generate_dynamic_outreach, OutreachRequest
from src.clinloop_engine.evidence_agent import run_evidence_synthesis
from src.clinloop_engine.safety_clock import safety_clock_loop, get_clock_status
import asyncio
from contextlib import asynccontextmanager
from src.clinloop_engine.biomcp_server import handle_call_tool as handle_guideline_library
from src.clinloop_engine import biomcp_client
from src.clinloop_engine.auth import User, require_role
from src.clinloop_engine.safety.agent_guard import AgentGuardException
from src.clinloop_engine.ehr_mcp_server import handle_call_tool as handle_ehr
from src.clinloop_engine.pacs_mcp_server import handle_call_tool as handle_pacs
from src.clinloop_engine.clinical_api import router as clinical_router, escalation_loop, get_store
from src.clinloop_engine.imaging_api import router as imaging_router
from src.clinloop_engine.patient_graph import router as graph_router

logger = logging.getLogger("clinloop.api")
from src.clinloop_engine.cds_hooks import router as cds_router
from src.clinloop_engine.fhir_sync import sync_loop
from src.clinloop_engine.imaging_scanner import scan_loop
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine import demo

# Initialize FastAPI App
@asynccontextmanager
async def lifespan(_app: FastAPI):
    if demo.enabled():
        # Public demo: synthetic patients in a fresh in-memory database, no hospital links
        demo.disconnect_hospital()
        demo.seed(LoopStore(":memory:"))
    # Background safety tasks: the Safety Clock watchdog over the demo cases,
    # and escalation of unacknowledged overdue loops in the pilot registry
    tasks = [asyncio.create_task(safety_clock_loop()), asyncio.create_task(escalation_loop()),
             asyncio.create_task(sync_loop(get_store)),    # no-op unless CLINLOOP_FHIR_BASE is set
             asyncio.create_task(scan_loop(get_store))]    # no-op unless CLINLOOP_IMAGE_SCAN=1 and a PACS
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(
    title="ClinLoop AI - Clinical Safety Platform API",
    description="Backend microservice for Neuro-Symbolic Closed-Loop Clinical Safety, Counterfactual Causal Simulations, and Patient Outreach.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def private_validation_error(_request: Request, exc: RequestValidationError):
    # Pydantic errors include submitted values; count only, never echo or log them.
    logger.warning("Request validation failed: %d field errors", len(exc.errors()))
    return JSONResponse(status_code=422, content={
        "detail": "Request validation failed. Check required fields and supported formats."
    })


# CORS: only the cockpit origins may call the API from a browser. Override
# with a comma-separated CLINLOOP_CORS_ORIGINS. Bearer tokens travel in a
# header, so cookies/credentials are never needed.
_cors_origins = [o.strip() for o in os.environ.get(
    "CLINLOOP_CORS_ORIGINS",
    "http://localhost:8123,http://127.0.0.1:8123,https://clinloopai.app",
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(clinical_router)
app.include_router(imaging_router)
app.include_router(graph_router)
app.include_router(cds_router)
from src.clinloop_engine.pilot import router as pilot_router  # noqa: E402
app.include_router(pilot_router)

# Load Cases Data
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cases.json")

def load_cases() -> List[Dict[str, Any]]:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# Models

class DynamicOutreachRequest(BaseModel):
    scenario_id: str
    clinical_context: str
    lang: str = "ko"

class CloseLoopRequest(BaseModel):
    clinician_id: str = Field("DOC-CLIN-042", description="ID of the attending physician closing the loop")
    action_type: str = Field("order_placed", description="Type of clinical order placed")
    notes: Optional[str] = Field("Simulated outpatient consult order placed in hospital EMR", description="Clinical rationale")

class EvidenceSynthesisRequest(BaseModel):
    clinical_context: str = Field(..., description="De-identified clinical context/scenario")
    task: str = Field("differential_diagnosis", description="Task type: kakao_message, differential_diagnosis")
    lang: str = Field("ko", description="Language: ko, en")

class BioMcpToolCallRequest(BaseModel):
    tool: str = Field(..., description="BioMCP tool name (e.g. biomcp_query_guidelines, biomcp_query_fleischner)")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")

def _require_profile(feature: str) -> None:
    """409 when the core profile locks this feature off (profile.py)."""
    from src.clinloop_engine.profile import OutsideIntendedUse, require
    try:
        require(feature)
    except OutsideIntendedUse as e:
        raise HTTPException(status_code=409, detail=str(e))


# Endpoints
@app.get("/api/v1/health", tags=["System"])
def health_check():
    return {
        "status": "online",
        "service": "ClinLoop AI Production Core",
        "version": "2.0.0",
        "standard_support": ["HL7 FHIR R4 (read-only ingest)", "MCP client (BioMCP)"],
    }

@app.get("/api/v1/cases", tags=["Triage Worklist"])
def list_cases(status_filter: Optional[str] = None, user: User = Depends(require_role("viewer"))):
    cases = load_cases()
    if status_filter and status_filter != "all":
        cases = [c for c in cases if c.get("ground_truth_status") == status_filter]
    return {
        "total": len(cases),
        "cases": cases
    }

@app.get("/api/v1/cases/{scenario_id}", tags=["Triage Worklist"])
def get_case(scenario_id: str, user: User = Depends(require_role("viewer"))):
    cases = load_cases()
    for c in cases:
        if c.get("scenario_id") == scenario_id:
            return c
    raise HTTPException(status_code=404, detail=f"Case {scenario_id} not found")

@app.get("/api/v1/cases/{scenario_id}/counterfactual", tags=["Counterfactual Causal Engine"])
def get_case_counterfactual(scenario_id: str, user: User = Depends(require_role("viewer"))):
    cf = get_counterfactual_analysis(scenario_id)
    if not cf:
        raise HTTPException(status_code=404, detail=f"Counterfactual trajectory for {scenario_id} not found")
    return {
        "scenario_id": cf.scenario_id,
        "condition_name": cf.condition_name,
        "delta_5yr_survival": f"+{cf.delta_5yr_survival * 100:.1f}%",
        "qaly_gain": cf.qaly_gain,
        "liability_avoided_krw": f"{cf.malpractice_cost_avoidance_krw:,} KRW",
        "neglected_path": [vars(s) for s in cf.neglected_path],
        "intervened_path": [vars(s) for s in cf.intervened_path],
        "evidence_rationale": cf.clinical_evidence_rationale,
        "evidence_type": "illustrative_scenario",
        "disclaimer": (
            "Hand-written illustrative trajectory based on published stage-specific survival. "
            "Not a patient-level prediction and not a measured effect of ClinLoop AI."
        ),
    }


@app.post("/api/v1/cases/{scenario_id}/close-loop", tags=["Clinical Action Hub"])
def close_clinical_loop(scenario_id: str, req: CloseLoopRequest, user: User = Depends(require_role("navigator"))):
    cases = load_cases()
    target_case = None
    for c in cases:
        if c.get("scenario_id") == scenario_id:
            target_case = c
            break
    
    if not target_case:
        raise HTTPException(status_code=404, detail=f"Case {scenario_id} not found")

    # Generate HL7 FHIR Task representing the loop closure
    fhir_task = {
        "resourceType": "Task",
        "id": f"TASK-CLOSE-{scenario_id}",
        "status": "completed",
        "intent": "order",
        "priority": "urgent",
        "code": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/task-code",
                "code": "fulfill"
            }]
        },
        "description": f"Clinical loop closed for {scenario_id}: {target_case.get('missing_followup')}",
        "for": {
            "reference": f"Patient/{target_case.get('patient_id')}"
        },
        "owner": {
            "reference": f"Practitioner/{req.clinician_id}"
        },
        "executionPeriod": {
            "end": "2026-09-21T14:30:00+09:00"
        }
    }

    return {
        "status": "closed",
        "scenario_id": scenario_id,
        "risk_score": 0.0,
        "mtl_robustness": "+Infinity (Invariant Satisfied)",
        "clinician_id": req.clinician_id,
        "fhir_task": fhir_task
    }

# ── Unified MCP Tool Router ─────────────────────────────────────────────
class McpToolCallRequest(BaseModel):
    tool: str = Field(..., description="MCP tool name (e.g. biomcp_query_guidelines, ehr_query_encounters, pacs_fetch_dicom_metadata)")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")

@app.post("/api/v1/biomcp/call", tags=["BioMCP (MCP server)"])
def biomcp_call(req: McpToolCallRequest, user: User = Depends(require_role("clinician"))):
    """
    Call a read-only tool on the connected BioMCP server over MCP (PubMed/PubTator3,
    ClinicalTrials.gov, openFDA, MyGene/MyVariant …). Never put patient data in a query.
    """
    try:
        return {"status": "ok", **biomcp_client.call_tool(req.tool, req.arguments)}
    except biomcp_client.BioMCPDisabled as e:
        raise HTTPException(status_code=409, detail=str(e))
    except biomcp_client.BioMCPError as e:
        raise HTTPException(status_code=502, detail=f"BioMCP: {e}")

@app.get("/api/v1/biomcp/status", tags=["BioMCP (MCP server)"])
def biomcp_status(user: User = Depends(require_role("viewer"))):
    """Connection status of the BioMCP server, including the tools ClinLoop may call."""
    return biomcp_client.status()          # cached: a fresh probe starts a subprocess

@app.post("/api/v1/guidelines/call", tags=["Guideline Library (static)"])
def guideline_library_call(req: McpToolCallRequest, user: User = Depends(require_role("viewer"))):
    """Curated, static guideline lookups built into ClinLoop (not a live connection)."""
    try:
        return {"status": "static", "tool": req.tool, "result": handle_guideline_library(req.tool, req.arguments)}
    except Exception as e:     # the reason, not Python's exception text
        logger.info("Tool call refused: %s", e)
        raise HTTPException(status_code=400, detail="Unknown tool or invalid arguments")

@app.post("/api/v1/ehr/call", tags=["EHR connector (mock)"])
def ehr_mcp_call(req: McpToolCallRequest, user: User = Depends(require_role("clinician"))):
    """MOCK: returns canned responses; no EHR is connected and nothing is written anywhere."""
    try:
        result = handle_ehr(req.tool, req.arguments)
        return {"status": "simulated", "simulated": True, "tool": req.tool, "result": result}
    except Exception as e:     # the reason, not Python's exception text
        logger.info("Tool call refused: %s", e)
        raise HTTPException(status_code=400, detail="Unknown tool or invalid arguments")

@app.post("/api/v1/pacs/call", tags=["PACS connector (mock)"])
def pacs_mcp_call(req: McpToolCallRequest, user: User = Depends(require_role("clinician"))):
    """MOCK: returns canned responses; no PACS is connected."""
    try:
        result = handle_pacs(req.tool, req.arguments)
        return {"status": "simulated", "simulated": True, "tool": req.tool, "result": result}
    except Exception as e:     # the reason, not Python's exception text
        logger.info("Tool call refused: %s", e)
        raise HTTPException(status_code=400, detail="Unknown tool or invalid arguments")

@app.get("/api/v1/mcp/tools", tags=["MCP Protocol Registry"])
def list_all_mcp_tools():
    """Tools by server, with each server's real connection type."""
    from src.clinloop_engine.biomcp_server import TOOLS as LIBRARY_TOOLS
    from src.clinloop_engine.ehr_mcp_server import TOOLS as EHR_TOOLS
    from src.clinloop_engine.pacs_mcp_server import TOOLS as PACS_TOOLS
    bio = biomcp_client.status()
    return {
        "servers": [
            {"name": "BioMCP", "connection": bio["status"], "tools": bio.get("allowed_tools", [])},
            {"name": "ClinLoop guideline library", "connection": "static", "tools": LIBRARY_TOOLS},
            {"name": "EHR connector", "connection": "mock", "tools": EHR_TOOLS},
            {"name": "PACS connector", "connection": "mock", "tools": PACS_TOOLS},
        ]
    }


@app.get("/api/v1/ethics/hippocratic-charter", tags=["Ethics & safety"])
def get_hippocratic_charter():
    """Returns the 5-pillar safety charter with the honest implementation status of each pillar."""
    return {
        "charter_name": "Digital Hippocratic 5-Pillar Safety Charter (Primum Non Nocere)",
        "version": "2026.2-research",
        "pillars": [
            {
                "id": 1,
                "name": "Clinician Autonomy",
                "mechanism": "ClinLoop never places orders or closes loops itself; FHIR Tasks are previews a clinician must act on.",
                "status": "implemented",
            },
            {
                "id": 2,
                "name": "Alert Fatigue Mitigation",
                "mechanism": "Risk-ranked worklist; per-clinician alert budget and precision-first thresholds.",
                "status": "ranking implemented; alert budget planned",
            },
            {
                "id": 3,
                "name": "Equity Monitoring",
                "mechanism": "Detection-rate disparity ratio across vulnerable groups (sdoh_monitor).",
                "status": "implemented; not yet evaluated on real patient data",
            },
            {
                "id": 4,
                "name": "On-Premise Data Isolation",
                "mechanism": "Local LLM inference (Ollama); regex-based PHI scrubbing before any text generation.",
                "status": "partial: PHI scrubbing cannot detect free-text names and is not a sufficient sole safeguard",
            },
            {
                "id": 5,
                "name": "Deterministic Auditability",
                "mechanism": "Guideline-cited rules decide every alert; each detection carries its evidence chain.",
                "status": "implemented",
            },
        ],
    }

@app.get("/api/v1/health-economics", tags=["Ethics & safety"])
def get_health_economics():
    """Returns the planned health-economic evaluation framework. No outcomes have been measured yet."""
    return {
        "framework": "Markov Health-State Transition Model (Annual Cycles)",
        "states": ["Healthy/Controlled", "Localized Neoplasm (Stage I)", "Regional Spread (Stage II-III)", "Distant Metastasis (Stage IV)", "Mortality"],
        "evidence_status": (
            "No clinical or economic outcomes have been measured yet. "
            "QALY, ICER and cost figures will be reported only after the validation studies below."
        ),
        "planned_evaluation": {
            "stage_1": "Retrospective validation against blinded two-clinician chart review (IRB-approved)",
            "stage_2": "Silent prospective deployment: alert burden and system reliability",
            "stage_3": "Pre-registered stepped-wedge cluster-randomized trial",
            "primary_endpoint": "Proportion of actionable findings closed within the guideline window",
            "secondary_endpoints": ["Time to diagnosis", "Cancer stage at diagnosis", "Clinician alert burden"],
        },
    }


# ---------------------------------------------------------------------------
# Local LLM Endpoints (DeepSeek-R1 70B / 32B / Llama3 — Ollama On-Premise)
# ---------------------------------------------------------------------------

class LocalLLMRequest(BaseModel):
    task: str = Field("kakao_message_ko", description="Task type: kakao_message_ko | kakao_message_en | differential_diagnosis | ethics_review | custom")
    clinical_context: str = Field(..., description="De-identified clinical context string (PHI already removed)")
    model: Optional[str] = Field(None, description="Specific model override. If None, uses best available.")
    custom_prompt: Optional[str] = Field(None, description="Custom prompt for 'custom' task type")
    temperature: float = Field(0.25, ge=0.0, le=1.0, description="Sampling temperature")
    max_tokens: int = Field(400, ge=50, le=2000, description="Maximum tokens to generate")

@app.get("/api/v1/local-llm/status", tags=["Local LLM Engine (On-Premise Ollama)"])
def get_local_llm_engine_status():
    """Whether the on-premise model is reachable and which models it has. Public (the cockpit shows
    it), so the server's internal address is left out."""
    status = dict(get_local_llm_status())
    for key in ("base_url", "url", "host", "ollama_url"):
        status.pop(key, None)
    return status


@app.get("/api/v1/models/registry", tags=["Local LLM Engine (On-Premise Ollama)"])
def get_model_registry():
    """The three model roles (text, second reader, vision): configured model, whether exactly that model
    is installed (digest, declared capabilities), allowed use and fallback (none). Public like the
    status above; no addresses."""
    from src.clinloop_engine.model_registry import registry
    return registry()


# ── Public demo: rules and MedGemma 27B on fixed synthetic reports (demo mode only; see demo_reader.py) ──

def _demo_case(case_id: str):
    from src.clinloop_engine import demo_reader
    if not demo.enabled():
        raise HTTPException(status_code=404, detail="Not found")
    c = demo_reader.case(case_id)
    if c is None:
        raise HTTPException(status_code=404, detail="No such synthetic report")
    return demo_reader, c


@app.get("/api/v1/demo/reports", tags=["Public demo"])
def demo_reports():
    from src.clinloop_engine import demo_reader
    if not demo.enabled():
        raise HTTPException(status_code=404, detail="Not found")
    cat = demo_reader.catalog()
    return {"note": cat["note"], "model": cat["model"],
            "cases": [{k: c[k] for k in ("id", "title", "language", "teaches")} for c in cat["cases"]]}


@app.get("/api/v1/demo/reports/{case_id}", tags=["Public demo"])
def demo_report(case_id: str):
    reader, c = _demo_case(case_id)
    rules = reader.rules_for(c)
    saved = dict(c["saved_reading"], items=reader.compare(rules, c["saved_reading"]["items"]))
    return {"id": c["id"], "title": c["title"], "date": c["date"], "language": c["language"], "patient": c["patient"],
            "text": c["text"], "teaches": c["teaches"], "rules": rules, "model_reading": saved,
            "model": reader.catalog()["model"]}


@app.post("/api/v1/demo/reports/{case_id}/live", tags=["Public demo"])
def demo_report_live(case_id: str, request: Request):
    reader, c = _demo_case(case_id)
    visitor = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "")
    try:
        out = reader.live_read(c, visitor)
    except reader.Busy as e:
        raise HTTPException(status_code=429, detail=str(e))
    if out.get("available"):
        out["items"] = reader.compare(reader.rules_for(c), out["items"])
    out["live_left_this_hour"] = reader.quota_left(visitor)
    return out

@app.post("/api/v1/local-llm/generate", tags=["Local LLM Engine (On-Premise Ollama)"])
def generate_with_local_llm(req: LocalLLMRequest, user: User = Depends(require_role("clinician"))):
    """
    Generate clinical text using the best available local LLM (DeepSeek-R1 70B priority).
    All inference runs 100% on-premise. PHI must be de-identified BEFORE this call.
    Supports: KakaoTalk messages, differential diagnosis, ethics review, custom prompts.
    Research feature: refused in the core profile.
    """
    _require_profile("llm_assistant")
    ctx = req.clinical_context

    if req.task == "kakao_message_ko":
        return llm_generate_kakao(ctx, lang="ko")
    elif req.task == "kakao_message_en":
        return llm_generate_kakao(ctx, lang="en")
    elif req.task == "differential_diagnosis":
        return llm_generate_diff(ctx)
    elif req.task == "ethics_review":
        return llm_generate_ethics(ctx)
    elif req.task == "custom":
        if not req.custom_prompt:
            raise HTTPException(status_code=400, detail="custom_prompt required for task='custom'")
        # Plain substitution: str.format on user input fails on stray braces
        prompt = req.custom_prompt.replace("{context}", ctx)
        return generate_clinical_text(prompt, model=req.model, temperature=req.temperature, max_tokens=req.max_tokens)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task: {req.task}. Use: kakao_message_ko | kakao_message_en | differential_diagnosis | ethics_review | custom")



# ---------------------------------------------------------------------------
# Compute: measured hardware (CPU or GPU) and where each part of ClinLoop runs
# ---------------------------------------------------------------------------
@app.get("/api/v1/compute/status", tags=["System"])
def get_compute_status():
    """The hardware this server really has (CPU, or the GPU it found) and where each part of
    ClinLoop runs. The rules engine always runs on the CPU; a GPU only speeds up optional imaging
    models. Values are measured on this machine, never assumed."""
    return compute_status()


@app.get("/api/v1/gpu/telemetry", tags=["System"], include_in_schema=False)
def get_gpu_telemetry():
    """Older name for /api/v1/compute/status."""
    return compute_status()


# ---------------------------------------------------------------------------
# API Key & Hospital Security Credential Management
# ---------------------------------------------------------------------------
class APIKeyConfigRequest(BaseModel):
    gemini_key: Optional[str] = None
    anthropic_key: Optional[str] = None
    openai_key: Optional[str] = None
    ncbi_key: Optional[str] = None
    fhir_token: Optional[str] = None
    active_mode: Optional[str] = 'on_premise'

class TestKeyRequest(BaseModel):
    provider: str  # 'gemini', 'ncbi', 'fhir'
    api_key: str

_configured_keys = {
    'gemini': bool(os.getenv('GEMINI_API_KEY')),
    'anthropic': bool(os.getenv('ANTHROPIC_API_KEY')),
    'openai': bool(os.getenv('OPENAI_API_KEY')),
    'ncbi': bool(os.getenv('NCBI_API_KEY')),
    'fhir': bool(os.getenv('CLINLOOP_FHIR_TOKEN') or os.getenv('FHIR_TOKEN')),
    'active_mode': 'on_premise'
}

@app.get('/api/v1/config/api-keys', tags=['API Key & Credential Management'])
def get_api_key_status(user: User = Depends(require_role("viewer"))):
    """Returns safe metadata status of configured API keys without exposing secret strings."""
    return {
        'status': 'success',
        'active_mode': _configured_keys['active_mode'],
        'providers': {
            'gemini': {'configured': _configured_keys['gemini'], 'engine': 'Google Gemini 2.5 / Medical Flash'},
            'anthropic': {'configured': _configured_keys['anthropic'], 'engine': 'Anthropic Claude 3.5 Sonnet / Opus (Medical Reasoning)'},
            'openai': {'configured': _configured_keys['openai'], 'engine': 'OpenAI o1 / GPT-4o / Astra Multimodal'},
            'ncbi': {'configured': _configured_keys['ncbi'], 'engine': 'NCBI Entrez E-Utilities (PubMed)'},
            'fhir': {'configured': _configured_keys['fhir'], 'engine': 'HL7 FHIR R4 SMART on FHIR'}
        },
        # Measured on this server, not assumed
        'compute': compute_status()['summary'],
        'outbound_literature_calls': os.environ.get('CLINLOOP_LITERATURE', 'on').strip().lower() != 'off',
    }

@app.post('/api/v1/config/api-keys', tags=['API Key & Credential Management'])
def save_api_key_config(req: APIKeyConfigRequest, user: User = Depends(require_role("admin"))):
    """Safely updates configured credentials and switches active execution mode."""
    if req.gemini_key:
        _configured_keys['gemini'] = True
    if req.anthropic_key:
        _configured_keys['anthropic'] = True
    if req.openai_key:
        _configured_keys['openai'] = True
    if req.ncbi_key:
        _configured_keys['ncbi'] = True
    if req.fhir_token:
        _configured_keys['fhir'] = True
    if req.active_mode:
        _configured_keys['active_mode'] = req.active_mode

    return {
        'status': 'recorded',
        'message': 'Key presence recorded for this session only. Keys are not stored, transmitted or verified.',
        'active_mode': _configured_keys['active_mode']
    }

@app.post('/api/v1/config/test-api-key', tags=['API Key & Credential Management'])
def test_api_key(req: TestKeyRequest, user: User = Depends(require_role("admin"))):
    """Connectivity testing is not implemented; reports that honestly instead of simulating success."""
    provider = req.provider.lower()
    if provider not in ('gemini', 'anthropic', 'openai', 'astra', 'ncbi', 'fhir'):
        raise HTTPException(status_code=400, detail=f'Unknown provider: {provider}')
    return {
        'status': 'not_verified',
        'provider': provider,
        'message': 'Connectivity testing is not implemented for this connector; no request was sent.',
    }

@app.post("/api/v1/agent/evidence-synthesis", tags=["Autonomous Evidence Synthesis Agent (RAG)"])
def agent_evidence_synthesis(req: EvidenceSynthesisRequest, user: User = Depends(require_role("clinician"))):
    """
    Research routing prototype using the bundled, unverified reference library.
    No verified evidence candidates are emitted until an evidence retrieval and
    applicability verification adapter is implemented. Model output does not
    establish medical accuracy. Refused in the core profile.
    """
    _require_profile("llm_assistant")
    try:
        result = run_evidence_synthesis(req.clinical_context, req.task, req.lang)
        return result
    except (AgentGuardException, ValueError) as e:     # refused input (the prompt-injection guard): the caller's fault
        raise HTTPException(status_code=422, detail=str(e)[:300])
    except Exception as e:
        logger.exception("Agent request failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: the request could not be completed")

@app.get("/api/v1/agent/safety-clock/status", tags=["Autonomous Safety Clock Agent"])
def agent_safety_clock_status(user: User = Depends(require_role("viewer"))):
    """
    Returns live telemetry from the autonomous 24/7 background watchdog.
    """
    return get_clock_status()

@app.post("/api/v1/agent/patient-outreach/generate", tags=["Patient Outreach Agent (Dynamic)"])
def agent_generate_patient_outreach(req: DynamicOutreachRequest, user: User = Depends(require_role("clinician"))):
    """
    Draft patient communication from supplied facts for clinician review.
    A model or static reference lookup does not verify the clinical facts or
    guarantee accuracy. This endpoint does not send a message.
    Research feature: refused in the core profile (loop messages go through outreach.py instead).
    """
    _require_profile("llm_assistant")
    try:
        request = OutreachRequest(
            patient_id=req.scenario_id,
            obligation_id="OBL-" + req.scenario_id,
            message_category="follow_up",
            approved_facts={"finding": req.clinical_context, "timeframe": "ASAP"},
            preferred_language=req.lang,
            health_literacy_mode="simple",
            permitted_channel="kakao",
            scheduling_link="https://clinloopai.app/book",
            urgency_level="CRITICAL",
            prohibited_topics=["diagnosis"]
        )
        draft = generate_dynamic_outreach(request)
        return {"kakao_message_text": draft.message_text, "language": draft.language}
    except (AgentGuardException, ValueError) as e:     # refused input (the prompt-injection guard): the caller's fault
        raise HTTPException(status_code=422, detail=str(e)[:300])
    except Exception as e:
        logger.exception("Agent request failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: the request could not be completed")


# ---------------------------------------------------------------------------
# Web UI (cockpit + worklist) served by the same container
# ---------------------------------------------------------------------------
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

_WEB_ROOT = os.environ.get("CLINLOOP_WEB_ROOT")


@app.get("/config.js", include_in_schema=False)
def web_config():
    """Point the pages at this server: same origin, so no CORS and no address to type."""
    body = "window.CLINLOOP_API_BASE = window.location.origin;\n"
    from . import oidc
    sso = oidc.web_config()
    if sso:                 # hospital single sign-on: public values only (no secret exists for a PKCE client)
        body += f"window.CLINLOOP_OIDC = {json.dumps(sso)};\n"
    if demo.enabled():
        body += demo.web_config()
    return Response(body,
                    media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/.well-known/jwks.json", include_in_schema=False)
def fhir_client_jwks():
    """ClinLoop's PUBLIC key for SMART Backend Services, for FHIR servers that fetch keys from a URL
    (CLINLOOP_FHIR_PRIVATE_KEY). Only the public half is ever served."""
    from .smart_auth import SMARTAuthError, load_private_key, public_jwk
    path = os.environ.get("CLINLOOP_FHIR_PRIVATE_KEY")
    if not path:
        raise HTTPException(404, "No FHIR client key configured")
    try:
        key = public_jwk(load_private_key(path), os.environ.get("CLINLOOP_FHIR_KEY_ID") or None)
    except SMARTAuthError as e:
        logger.error("JWKS not served: %s", e)
        raise HTTPException(503, "FHIR client key unavailable")
    return Response(json.dumps({"keys": [key]}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=3600"})


# Only a dedicated directory holding the UI files is served (never the
# project root, which holds source code and, in development, the database).
if _WEB_ROOT and os.path.isdir(_WEB_ROOT):
    from fastapi.responses import FileResponse

    def _page_route(name: str):
        def page():
            return FileResponse(os.path.join(_WEB_ROOT, f"{name}.html"), media_type="text/html")
        return page

    # Clean addresses ("/worklist"); "/worklist.html" keeps working through the static mount below
    for _page in ("worklist", "patient", "quality", "governance", "imaging", "pilot", "analyse", "reports", "validation", "deployment", "review", "private"):
        if os.path.isfile(os.path.join(_WEB_ROOT, f"{_page}.html")):
            app.add_api_route(f"/{_page}", _page_route(_page), methods=["GET"], include_in_schema=False)
    app.mount("/", StaticFiles(directory=_WEB_ROOT, html=True), name="web")


# Must stay at the end of the module: uvicorn.run() blocks, so any route
# declared below it would never be registered.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8124)
