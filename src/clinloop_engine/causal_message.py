import logging
from dataclasses import dataclass

logger = logging.getLogger("clinloop.causal_message")

@dataclass
class MessageTemplate:
    template_id: str
    framing: str
    text_template: str
    estimated_engagement_score: float

# The four causal frameworks optimized for reducing patient dropout
TEMPLATES = {
    "fear_reduction": MessageTemplate(
        template_id="T1-FEAR",
        framing="Reassurance & Next Steps",
        text_template="We noticed a finding on your recent test. This is very common, and the next step is a simple check-up to ensure everything is fine. We are here with you.",
        estimated_engagement_score=0.88
    ),
    "social_proof": MessageTemplate(
        template_id="T2-SOCIAL",
        framing="Normative Alignment",
        text_template="Many of our patients with similar results schedule a follow-up right away to stay ahead. We've reserved a spot for you.",
        estimated_engagement_score=0.75
    ),
    "family_impact": MessageTemplate(
        template_id="T3-FAMILY",
        framing="Protecting Loved Ones",
        text_template="Taking care of this now is the best way to stay healthy for yourself and your loved ones. Please schedule your follow-up.",
        estimated_engagement_score=0.92
    ),
    "spiritual_framing": MessageTemplate(
        template_id="T4-SPIRIT",
        framing="Wholistic Care",
        text_template="Your health is a precious gift. We invite you to complete this follow-up as a step in caring for your whole self.",
        estimated_engagement_score=0.70
    )
}

def recommend_message_template(patient_features: dict) -> MessageTemplate:
    """
    Simulates a Causal Forest heterogeneous treatment effect (HTE) model 
    to pick the best message framing based on patient features.
    """
    sdoh_flag = patient_features.get('sdoh_flag', False)
    age = patient_features.get('age', 50)
    urgency = patient_features.get('urgency_level', 'LOW')
    
    # A simple deterministic rule tree replacing the causalml black box
    if urgency == "CRITICAL" and sdoh_flag:
        # High fear barrier for vulnerable patients
        best = TEMPLATES["fear_reduction"]
    elif age > 65 and sdoh_flag:
        best = TEMPLATES["family_impact"]
    elif age < 40:
        best = TEMPLATES["social_proof"]
    else:
        best = TEMPLATES["fear_reduction"]
        
    logger.info(f"Causal model recommended {best.framing} framing for patient.")
    return best
