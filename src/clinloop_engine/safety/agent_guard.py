import re
from typing import Dict, Any, List

class AgentGuardException(Exception):
    pass

class PromptInjectionError(AgentGuardException):
    pass

class CapabilityViolationError(AgentGuardException):
    pass

PROHIBITED_INTENTS = [
    r"ignore (your|all) (previous )?(instructions|rules)",
    r"close this loop",
    r"order a (ct|mri|medication) immediately",
    r"you have cancer",
    r"override (system|safety)",
    r"bypass (guard|policy)"
]

def detect_prompt_injection(text: str) -> bool:
    """Scans untrusted clinical text for hostile injection attacks."""
    if not text:
        return False
    text_lower = text.lower()
    for pattern in PROHIBITED_INTENTS:
        if re.search(pattern, text_lower):
            return True
    return False

def validate_agent_request(agent_name: str, payload: str):
    """Runs BEFORE tool execution or agent generation."""
    if detect_prompt_injection(payload):
        raise PromptInjectionError(f"[{agent_name}] Hostile prompt injection detected and blocked.")

def detect_unsupported_clinical_claims(text: str) -> bool:
    """Detects if the AI hallucinated definitive diagnostic claims."""
    claims = ["you have cancer", "100% cure", "definitely benign", "stop taking your medication"]
    text_lower = text.lower()
    return any(c in text_lower for c in claims)

def detect_prohibited_action(action_intent: str, agent_role: str) -> bool:
    """Prevents agents from executing unauthorized EHR writes."""
    if agent_role == "outreach_agent" and "write_order" in action_intent:
        return True
    if agent_role == "evidence_agent" and ("write_" in action_intent or "message_patient" in action_intent):
        return True
    return False

def validate_agent_output(agent_name: str, output_text: str):
    """Runs BEFORE downstream use of agent output."""
    if detect_unsupported_clinical_claims(output_text):
        raise CapabilityViolationError(f"[{agent_name}] Output contains unsupported definitive clinical claims.")
