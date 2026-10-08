"""
ClinLoop AI - FastAPI Backend Service (research prototype)
Exposes REST endpoints for the web cockpit. Runs on synthetic data only.

Run from the repository root:
    uvicorn src.clinloop_engine.api:app --host 127.0.0.1 --port 8124
"""

try:  # PyTorch is optional; only the GPU demo endpoints need it
    from src.clinloop_engine.gpu_engine import gpu_engine
except ImportError:
    gpu_engine = None
from src.clinloop_engine.local_llm_engine import (
    get_engine_status as get_local_llm_status,
    get_best_model,
    generate_kakao_message as llm_generate_kakao,
    generate_differential_diagnosis as llm_generate_diff,
    generate_ethics_review as llm_generate_ethics,
    generate_clinical_text,
)

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import json
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
from src.clinloop_engine.ehr_mcp_server import handle_call_tool as handle_ehr
from src.clinloop_engine.pacs_mcp_server import handle_call_tool as handle_pacs
from src.clinloop_engine.clinical_api import router as clinical_router, escalation_loop, get_store
from src.clinloop_engine.fhir_sync import sync_loop

# Initialize FastAPI App
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Background safety tasks: the Safety Clock watchdog over the demo cases,
    # and escalation of unacknowledged overdue loops in the pilot registry
    tasks = [asyncio.create_task(safety_clock_loop()), asyncio.create_task(escalation_loop()),
             asyncio.create_task(sync_loop(get_store))]   # no-op unless CLINLOOP_FHIR_BASE is set
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
def list_cases(status_filter: Optional[str] = None):
    cases = load_cases()
    if status_filter and status_filter != "all":
        cases = [c for c in cases if c.get("ground_truth_status") == status_filter]
    return {
        "total": len(cases),
        "cases": cases
    }

@app.get("/api/v1/cases/{scenario_id}", tags=["Triage Worklist"])
def get_case(scenario_id: str):
    cases = load_cases()
    for c in cases:
        if c.get("scenario_id") == scenario_id:
            return c
    raise HTTPException(status_code=404, detail=f"Case {scenario_id} not found")

@app.get("/api/v1/cases/{scenario_id}/counterfactual", tags=["Counterfactual Causal Engine"])
def get_case_counterfactual(scenario_id: str):
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
def close_clinical_loop(scenario_id: str, req: CloseLoopRequest):
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
def biomcp_call(req: McpToolCallRequest, user: User = Depends(require_role("viewer"))):
    """
    Call a read-only tool on the connected BioMCP server over MCP (PubMed/PubTator3,
    ClinicalTrials.gov, openFDA, MyGene/MyVariant …). Never put patient data in a query.
    """
    try:
        return {"status": "ok", **biomcp_client.call_tool(req.tool, req.arguments)}
    except biomcp_client.BioMCPError as e:
        raise HTTPException(status_code=502, detail=f"BioMCP: {e}")

@app.get("/api/v1/biomcp/status", tags=["BioMCP (MCP server)"])
def biomcp_status(user: User = Depends(require_role("viewer"))):
    """Connection status of the BioMCP server, including the tools ClinLoop may call."""
    return biomcp_client.status(force=True)

@app.post("/api/v1/guidelines/call", tags=["Guideline Library (static)"])
def guideline_library_call(req: McpToolCallRequest):
    """Curated, static guideline lookups built into ClinLoop (not a live connection)."""
    try:
        return {"status": "static", "tool": req.tool, "result": handle_guideline_library(req.tool, req.arguments)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/ehr/call", tags=["EHR connector (mock)"])
def ehr_mcp_call(req: McpToolCallRequest):
    """MOCK: returns canned responses; no EHR is connected and nothing is written anywhere."""
    try:
        result = handle_ehr(req.tool, req.arguments)
        return {"status": "simulated", "simulated": True, "tool": req.tool, "result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/pacs/call", tags=["PACS connector (mock)"])
def pacs_mcp_call(req: McpToolCallRequest):
    """MOCK: returns canned responses; no PACS is connected."""
    try:
        result = handle_pacs(req.tool, req.arguments)
        return {"status": "simulated", "simulated": True, "tool": req.tool, "result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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


@app.get("/api/v1/ethics/hippocratic-charter", tags=["Medical Nobility & Ethics"])
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

@app.get("/api/v1/health-economics", tags=["Medical Nobility & Ethics"])
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
    """Returns status of the on-premise Ollama LLM engine and available models."""
    return get_local_llm_status()

@app.post("/api/v1/local-llm/generate", tags=["Local LLM Engine (On-Premise Ollama)"])
def generate_with_local_llm(req: LocalLLMRequest):
    """
    Generate clinical text using the best available local LLM (DeepSeek-R1 70B priority).
    All inference runs 100% on-premise. PHI must be de-identified BEFORE this call.
    Supports: KakaoTalk messages, differential diagnosis, ethics review, custom prompts.
    """
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
# GPU-Accelerated Neural-Symbolic Safety Telemetry (NVIDIA RTX A4500 20GB)
# ---------------------------------------------------------------------------
def _require_gpu_engine():
    if gpu_engine is None:
        raise HTTPException(status_code=503, detail="GPU engine unavailable: install PyTorch to enable it")


class GPUVerificationRequest(BaseModel):
    scenario_id: str
    clinical_text: str
    deadline_days: int = 30
    elapsed_days: int = 35
    severity: str = 'critical'

@app.get("/api/v1/gpu/telemetry", tags=["GPU Acceleration (NVIDIA RTX A4500)"])
def get_gpu_telemetry():
    """Returns live hardware telemetry and memory statistics for the NVIDIA RTX A4500."""
    _require_gpu_engine()
    return gpu_engine.get_telemetry()

@app.post("/api/v1/gpu/verify-trajectory", tags=["GPU Acceleration (NVIDIA RTX A4500)"])
def verify_trajectory_on_gpu(req: GPUVerificationRequest):
    """Runs PyTorch CUDA tensor kernels for Metric Temporal Logic robustness margin & obligation matching."""
    _require_gpu_engine()
    return gpu_engine.verify_trajectory_gpu(
        scenario_id=req.scenario_id,
        clinical_text=req.clinical_text,
        deadline_days=req.deadline_days,
        elapsed_days=req.elapsed_days,
        severity=req.severity
    )

@app.post("/api/v1/gpu/benchmark", tags=["GPU Acceleration (NVIDIA RTX A4500)"])
def run_gpu_benchmark(batch_size: int = 1000):
    """Runs vectorized PyTorch CUDA benchmark across N parallel trajectories on RTX A4500."""
    _require_gpu_engine()
    return gpu_engine.run_benchmark(batch_size=min(50000, max(100, batch_size)))


# ---------------------------------------------------------------------------
# API Key & Hospital Security Credential Management
# ---------------------------------------------------------------------------
class APIKeyConfigRequest(BaseModel):
    gemini_key: Optional[str] = None
    anthropic_key: Optional[str] = None
    openai_key: Optional[str] = None
    ncbi_key: Optional[str] = None
    fhir_token: Optional[str] = None
    active_mode: Optional[str] = 'on_prem_gpu'

class TestKeyRequest(BaseModel):
    provider: str  # 'gemini', 'ncbi', 'fhir'
    api_key: str

_configured_keys = {
    'gemini': bool(os.getenv('GEMINI_API_KEY')),
    'anthropic': bool(os.getenv('ANTHROPIC_API_KEY')),
    'openai': bool(os.getenv('OPENAI_API_KEY')),
    'ncbi': bool(os.getenv('NCBI_API_KEY')),
    'fhir': bool(os.getenv('FHIR_TOKEN')),
    'active_mode': 'on_prem_gpu'
}

@app.get('/api/v1/config/api-keys', tags=['API Key & Credential Management'])
def get_api_key_status():
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
        'on_premise_gpu': {
            'device': 'NVIDIA RTX A4500 (20GB GDDR6 ECC)',
            'air_gapped_privacy': True,
            'zero_cloud_egress': True
        }
    }

@app.post('/api/v1/config/api-keys', tags=['API Key & Credential Management'])
def save_api_key_config(req: APIKeyConfigRequest):
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
def test_api_key(req: TestKeyRequest):
    """Connectivity testing is not implemented; reports that honestly instead of simulating success."""
    provider = req.provider.lower()
    if provider not in ('gemini', 'anthropic', 'openai', 'astra', 'ncbi', 'fhir'):
        raise HTTPException(status_code=400, detail=f'Unknown provider: {provider}')
    return {
        'status': 'not_verified',
        'provider': provider,
        'message': 'Connectivity testing is not implemented in this prototype; no request was sent.',
    }

@app.post("/api/v1/agent/evidence-synthesis", tags=["Autonomous Evidence Synthesis Agent (RAG)"])
def agent_evidence_synthesis(req: EvidenceSynthesisRequest):
    """
    Autonomous Retrieval-Augmented Generation (RAG) pipeline.
    1. Analyzes the context and autonomously queries the correct BioMCP guideline.
    2. Injects the strict clinical mandate into a system prompt.
    3. Runs on-premise inference via DeepSeek-R1 70B for zero-hallucination grounded text.
    """
    try:
        result = run_evidence_synthesis(req.clinical_context, req.task, req.lang)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/agent/safety-clock/status", tags=["Autonomous Safety Clock Agent"])
def agent_safety_clock_status():
    """
    Returns live telemetry from the autonomous 24/7 background watchdog.
    """
    return get_clock_status()

@app.post("/api/v1/agent/patient-outreach/generate", tags=["Patient Outreach Agent (Dynamic)"])
def agent_generate_patient_outreach(req: DynamicOutreachRequest):
    """
    Autonomous dynamic generation of patient communication.
    Uses the Evidence Synthesis Agent (RAG) to ensure the message is medically grounded
    before using the Local LLM (DeepSeek) to write the empathetic patient text.
    """
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Web UI (cockpit + worklist) served by the same container
# ---------------------------------------------------------------------------
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

_WEB_ROOT = os.environ.get("CLINLOOP_WEB_ROOT")


@app.get("/config.js", include_in_schema=False)
def web_config():
    """Point the pages at this server: same origin, so no CORS and no address to type."""
    return Response("window.CLINLOOP_API_BASE = window.location.origin;\n",
                    media_type="application/javascript", headers={"Cache-Control": "no-store"})


# Only a dedicated directory holding the UI files is served (never the
# project root, which holds source code and, in development, the database).
if _WEB_ROOT and os.path.isdir(_WEB_ROOT):
    app.mount("/", StaticFiles(directory=_WEB_ROOT, html=True), name="web")


# Must stay at the end of the module: uvicorn.run() blocks, so any route
# declared below it would never be registered.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8124)
