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

# Definitive diagnoses, guarantees and medication instructions a drafted patient message must never make.
# A short phrase list, not a complete filter: a clinician still approves every message before it is sent.
_CLAIM_PATTERNS = [
    r"\byou (have|definitely have|certainly have) (cancer|a tumou?r|malignancy|leukemia|lymphoma)\b",
    r"\b(100\s*%|guaranteed?) (cure|cured|safe|benign|normal)\b",
    r"\b(definitely|certainly|absolutely) (benign|malignant|cancer|not cancer|nothing serious|normal)\b",
    r"\bnothing to worry about\b",
    r"\bno need (for|to have) (a )?follow[- ]?up\b",
    r"\b(stop|discontinue|double|skip) (taking )?your (medication|medicine|dose|pills?)\b",
    r"(암|악성\s*종양|종양)(입니다|이에요|예요|이 확실)",
    r"(확실히|틀림없이|100\s*%)\s*(양성|정상|암|완치)",
    r"걱정(하실|할)\s*(필요|것)(는|이)?\s*없",
    r"(복용|약)(을|를)?\s*(중단|끊)(하세요|하십시오)",
]
_CLAIM_RE = re.compile("|".join(_CLAIM_PATTERNS), re.IGNORECASE)


def detect_unsupported_clinical_claims(text: str) -> bool:
    """Detects definitive diagnostic claims, guarantees or medication instructions (English and Korean)."""
    return bool(text) and bool(_CLAIM_RE.search(text))

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
