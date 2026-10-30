import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from src.clinloop_engine.agent_execution import AgentExecutionContext
from src.clinloop_engine.digital_signature import sign_agent_context
from src.clinloop_engine.biomcp_server import handle_call_tool as handle_biomcp

logger = logging.getLogger("clinloop.evidence_agent")

@dataclass
class EvidenceQueryPlan:
    clinical_question: str
    patient_context_summary: str
    candidate_sources: List[str]
    selected_tools: List[str]
    rationale: str
    missing_context: List[str]
    uncertainty: List[str]

@dataclass
class EvidenceCandidate:
    source_name: str
    source_version: Optional[str]
    source_uri: Optional[str]
    retrieved_at: str
    recommendation_text: str
    applicability: dict
    exclusions: List[str]
    temporal_expression: Optional[str]
    evidence_grade: Optional[str]
    evidence_span: Optional[str]
    uncertainty: List[str]

def analyze_and_route_biomcp(clinical_context: str) -> EvidenceQueryPlan:
    """
    Agent Level 1 (A1 = PROPOSE / ROUTE).
    Formulates the query plan but does NOT execute the policy.
    """
    context_lower = clinical_context.lower()
    selected = []
    sources = []
    rationale = "Default routing"
    
    if "hsil" in context_lower or "cervical" in context_lower:
        selected.append("biomcp_query_guidelines")
        sources.append("ASCCP")
        rationale = "Cervical dysplasia detected."
    elif "nodule" in context_lower or "ggn" in context_lower:
        selected.append("biomcp_query_fleischner")
        sources.append("Fleischner Society")
        rationale = "Incidental lung nodule detected."
    elif "warfarin" in context_lower or "bleeding" in context_lower:
        selected.append("biomcp_query_openfda_safety")
        sources.append("FDA Open Safety Data")
        rationale = "High-risk anticoagulant mentioned."
    elif "critical" in context_lower and "lab" in context_lower:
        selected.append("biomcp_query_clsi_critical_lab")
        sources.append("CLSI Panic Values")
        rationale = "Critical lab panic value flagged."
        
    return EvidenceQueryPlan(
        clinical_question="Which current evidence and applicability criteria require clinician verification?",
        patient_context_summary=clinical_context[:100],
        candidate_sources=sources,
        selected_tools=selected,
        rationale=rationale,
        missing_context=[],
        uncertainty=["Unknown patient smoking history"] if "nodule" in context_lower else []
    )

from src.clinloop_engine.safety.agent_guard import validate_agent_request, validate_agent_output

def run_evidence_synthesis(clinical_context: str, task: str = "differential_diagnosis", lang: str = "ko") -> List[EvidenceCandidate]:

    # 3M. Agent Guard: Validate Request
    validate_agent_request("EvidenceAgent", clinical_context)

    """
    Agent executes the plan and returns bounded EvidenceCandidates.
    It does NOT return operational clinical deadlines as authoritative truth.
    """
    plan = analyze_and_route_biomcp(clinical_context)
    candidates = []
    
    for tool in plan.selected_tools:
        # Mocking the parameter extraction for the tools
        args = {}
        if tool == "biomcp_query_fleischner":
            # Fleischner intervals depend on nodule size; never assume one.
            size_match = re.search(r"(\d+(?:\.\d+)?)\s*mm", clinical_context, re.IGNORECASE)
            if not size_match:
                plan.missing_context.append("nodule size (mm)")
                continue
            args = {"nodule_size_mm": float(size_match.group(1))}
        elif tool == "biomcp_query_guidelines":
            args = {"finding_category": "Pap Smear", "finding_value": "HSIL"}
        elif tool == "biomcp_query_clsi_critical_lab":
            args = {"specimen": "blood", "isolate": "unknown"}
            
        res = handle_biomcp(tool, args)
        if res:
            # This adapter calls the bundled static reference library, not a
            # verified retrieval provider. Its canned text and deadlines cannot
            # establish evidence, patient applicability, or a grounded answer.
            # A real retrieval/verification adapter is required before this
            # function may emit EvidenceCandidates. Never fabricate defaults.
            continue

    # --- NEW INTEGRATION WIRING ---
    ctx = AgentExecutionContext(agent_name="EvidenceAgent", model_name="BioMCP", autonomy_level="A1")
    ctx.record_input({"context": clinical_context, "task": task})
    ctx.human_review_required = True
    ctx.safety_flags.append("static_reference_library_is_not_verified_evidence")
    ctx.record_output({"candidates_count": len(candidates), "verified_evidence_available": False})
    
    # Sign the execution envelope
    sig = sign_agent_context(ctx)
    logger.info(f"EvidenceAgent Execution Signed: {sig[:12]}...")
    
    return candidates
