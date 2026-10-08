import logging
from typing import Dict, Any, Optional, List
from src.clinloop_engine.safety.agent_guard import validate_agent_request, validate_agent_output
from dataclasses import dataclass, asdict
from src.clinloop_engine.local_llm_engine import generate_kakao_message
from src.clinloop_engine.causal_message import recommend_message_template

logger = logging.getLogger("clinloop.patient_outreach_agent")

@dataclass
class OutreachRequest:
    patient_id: str
    obligation_id: str
    message_category: str
    approved_facts: dict
    preferred_language: str
    health_literacy_mode: Optional[str]
    permitted_channel: str
    scheduling_link: Optional[str]
    urgency_level: str
    prohibited_topics: List[str]

@dataclass
class OutreachDraft:
    message_text: str
    language: str
    facts_used: List[str]
    safety_flags: List[str]
    unsupported_claims_detected: List[str]
    requires_human_review: bool

def generate_dynamic_outreach(request: OutreachRequest) -> OutreachDraft:

    # 3M. Agent Guard: Validate Request
    validate_agent_request("OutreachAgent", str(request.approved_facts))

    """
    Agent Level 1 (A1 = DRAFT).
    Converts approved clinical workflow intents into understandable communication
    without inventing clinical facts.
    """
    # Simulate LLM generation constrained by the request parameters
    context = f"{request.approved_facts.get('finding', 'Finding')} requires action within {request.approved_facts.get('timeframe', 'a specific time')}."
    

    # --- NEW INTEGRATION WIRING ---
    patient_features = {
        'urgency_level': request.urgency_level,
        'language': request.preferred_language,
        'sdoh_flag': getattr(request, 'sdoh_flag', False),
        'age': 50 # Default fallback
    }
    recommended_tmpl = recommend_message_template(patient_features)
    logger.info(f"Using template {recommended_tmpl.template_id} ({recommended_tmpl.framing})")
    
    # Use the infrastructure LLM for translation/simplification
    raw_response = generate_kakao_message(context, lang=request.preferred_language)
    
    # Construct the strictly bounded OutreachDraft
    draft = OutreachDraft(
        message_text=raw_response.get("kakao_message_text", "Please contact the clinic."),
        language=request.preferred_language,
        facts_used=[str(k) for k in request.approved_facts.keys()],
        safety_flags=[],
        unsupported_claims_detected=[],
        requires_human_review=True if request.urgency_level == "CRITICAL" else False
    )
    
    # Append the booking link if provided (but remember: click != closure)
    if request.scheduling_link:
        draft.message_text += f"\n\n[예약하기/Book Here]: {request.scheduling_link}"
        
    return draft
