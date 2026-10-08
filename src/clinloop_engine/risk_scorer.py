"""
risk_scorer.py — Multi-Factor Risk Scoring Engine

Computes the composite risk score for each unclosed clinical loop:

    Risk_i(t) = Severity_i × TimeRisk_i(t) × Uncertainty_i 
                × FailureProbability_i × Actionability_i

Each factor is scored [0, 1]. The final score determines priority order.
Includes an abstention mechanism: if uncertainty > threshold,
the system flags the case as NEEDS_HUMAN_REVIEW rather than
making a potentially erroneous automated judgment.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np

from .clinical_ontology import Severity, LoopStatus, get_severity_score
from .safety_clock import SafetyClock, SafetyClockReading, ClockState


@dataclass
class RiskAssessment:
    """Complete risk assessment for one clinical obligation."""
    obligation_id: str
    rule_id: str
    rule_name: str

    # Individual risk factors
    severity_score: float       # From clinical ontology
    time_risk_score: float      # From Safety Clock
    uncertainty_score: float    # Based on data completeness
    failure_probability: float  # Historical failure rate estimate
    actionability_score: float  # Whether clear next action exists

    # Composite
    composite_risk: float       # Product of all factors
    normalized_risk: float      # Scaled to [0, 1]

    # Decision
    recommended_action: str
    should_abstain: bool
    abstain_reason: str = ""

    # Evidence
    explanation: List[str] = field(default_factory=list)
    clock_state: str = ""


class RiskScorer:
    """
    Multi-factor risk scoring engine with abstention capability.
    
    Key design principle: It is SAFER to flag something for human review
    than to either (a) miss a dangerous open loop or (b) generate a
    false alarm that contributes to alert fatigue.
    """

    def __init__(
        self,
        abstention_threshold: float = 0.7,
        safety_clock: Optional[SafetyClock] = None,
    ):
        """
        Args:
            abstention_threshold: If uncertainty exceeds this,
                                  output NEEDS_HUMAN_REVIEW.
            safety_clock: SafetyClock instance for time-risk computation.
        """
        self.abstention_threshold = abstention_threshold
        self.safety_clock = safety_clock or SafetyClock()

        # Simulated historical failure probabilities by rule type
        # In production, these would be learned from real hospital data
        self._failure_priors = {
            "R001": 0.25,  # 25% of abnormal labs not followed up
            "R002": 0.20,
            "R003": 0.55,  # 55% of incidental findings lost to follow-up
            "R004": 0.30,
            "R005": 0.22,
            "R006": 0.15,  # Critical cultures usually caught
            "R007": 0.35,
            "R008": 0.40,  # Referral no-shows are common
            "R009": 0.18,
            "R010": 0.30,
            "R011": 0.10,  # Normal results low risk
            "R012": 0.20,
            "R013": 0.45,  # HbA1c retesting: high non-adherence in uncontrolled diabetes
            "R014": 0.20,  # Post-MI follow-up: high urgency ensures moderate compliance
            "R015": 0.12,  # Bacteremia repeat culture: inpatient protocol-driven, low miss rate
            "R016": 0.35,  # New HF echocardiogram: outpatient scheduling delays common
        }

        # Actionability scores (does a clear next step exist?)
        self._actionability = {
            "R001": 0.95,  # Clear: notify patient
            "R002": 0.90,  # Clear: schedule appointment
            "R003": 0.90,  # Clear: order follow-up CT
            "R004": 0.85,  # Clear: urology referral
            "R005": 0.90,  # Clear: colposcopy referral
            "R006": 0.95,  # Clear: callback patient
            "R007": 0.95,  # Clear: order INR
            "R008": 0.70,  # Moderate: patient may refuse
            "R009": 0.90,  # Clear: notify + refer
            "R010": 0.80,  # Moderate: depends on drug
            "R011": 0.60,  # Low: just needs review
            "R012": 0.80,
            "R013": 0.75,  # Moderate: depends on patient adherence/lifestyle
            "R014": 0.95,  # Clear: schedule cardiology outpatient visit
            "R015": 0.95,  # Clear: order repeat blood culture (inpatient protocol)
            "R016": 0.90,  # Clear: order echocardiogram
        }

    def compute_uncertainty(self, event_details: Dict, n_events: int) -> float:
        """
        Estimate uncertainty based on data completeness.
        
        Higher uncertainty when:
          - Few events in the trajectory (sparse data)
          - Key details are missing
          - Ambiguous clinical information
        """
        # Base uncertainty inversely proportional to data richness
        base = max(0.1, 1.0 - (n_events / 10.0))

        # Missing critical details increase uncertainty
        missing_penalties = 0.0
        critical_keys = ["condition", "flag", "test", "result", "finding"]
        present = sum(1 for k in critical_keys if k in event_details and event_details[k])
        if len(critical_keys) > 0:
            completeness = present / len(critical_keys)
            missing_penalties = (1.0 - completeness) * 0.3

        uncertainty = min(1.0, base + missing_penalties)
        return round(uncertainty, 3)

    def score(
        self,
        obligation_id: str,
        rule_id: str,
        rule_name: str,
        severity: Severity,
        trigger_time: datetime,
        deadline_days: float,
        event_details: Dict,
        n_events: int,
        is_open: bool,
        evaluation_time: Optional[datetime] = None,
    ) -> RiskAssessment:
        """
        Compute the full risk assessment for one obligation.
        
        Returns a RiskAssessment with all factor scores and final decision.
        """
        # Factor 1: Severity
        severity_score = get_severity_score(severity)

        # Factor 2: Time Risk (from Safety Clock)
        clock_reading = self.safety_clock.evaluate(
            obligation_id, rule_id,
            trigger_time, deadline_days,
            evaluation_time,
        )
        time_risk_score = clock_reading.time_risk

        # Factor 3: Uncertainty
        uncertainty_score = self.compute_uncertainty(event_details, n_events)

        # Factor 4: Failure Probability
        failure_prob = self._failure_priors.get(rule_id, 0.25)

        # Factor 5: Actionability
        actionability = self._actionability.get(rule_id, 0.75)

        # Composite Risk Score
        # We use a modified product that emphasizes severity and time risk
        # while using uncertainty as a penalty (higher uncertainty = more need for review)
        if is_open:
            composite = (
                severity_score *
                time_risk_score *
                (1.0 - uncertainty_score * 0.3) *  # Uncertainty reduces confidence, not risk
                failure_prob *
                actionability
            )
        else:
            composite = 0.0  # Closed loops have zero risk

        # Normalize to [0, 1]
        normalized = min(1.0, composite / 0.5)  # 0.5 is roughly max expected composite

        # Abstention decision
        should_abstain = uncertainty_score > self.abstention_threshold and is_open
        abstain_reason = ""
        if should_abstain:
            abstain_reason = (
                f"Uncertainty ({uncertainty_score:.2f}) exceeds threshold "
                f"({self.abstention_threshold}). Insufficient data for confident "
                f"automated assessment. Flagged for human review."
            )

        # Generate recommended action
        if not is_open:
            recommended_action = "No action needed — loop is closed."
        elif should_abstain:
            recommended_action = "NEEDS HUMAN REVIEW — insufficient data for automated judgment."
        elif clock_reading.clock_state == ClockState.BLACK:
            recommended_action = f"URGENT: Immediately verify and act — {clock_reading.urgency_label}"
        elif clock_reading.clock_state == ClockState.RED:
            recommended_action = f"HIGH PRIORITY: {clock_reading.urgency_label}. Act today."
        elif clock_reading.clock_state == ClockState.YELLOW:
            recommended_action = f"Schedule action soon — {clock_reading.urgency_label}"
        else:
            recommended_action = f"Monitor — {clock_reading.urgency_label}"

        # Build explanation
        explanation = [
            f"Rule: {rule_name} [{rule_id}]",
            f"Severity: {severity.value} (score: {severity_score:.2f})",
            f"Time Risk: {time_risk_score:.3f} (clock: {clock_reading.clock_state.value})",
            f"Uncertainty: {uncertainty_score:.3f}",
            f"Historical Failure Rate: {failure_prob:.2f}",
            f"Actionability: {actionability:.2f}",
            f"Composite Risk: {composite:.4f} → Normalized: {normalized:.3f}",
        ]
        if should_abstain:
            explanation.append(f"⚠ ABSTENTION: {abstain_reason}")

        return RiskAssessment(
            obligation_id=obligation_id,
            rule_id=rule_id,
            rule_name=rule_name,
            severity_score=severity_score,
            time_risk_score=time_risk_score,
            uncertainty_score=uncertainty_score,
            failure_probability=failure_prob,
            actionability_score=actionability,
            composite_risk=composite,
            normalized_risk=normalized,
            recommended_action=recommended_action,
            should_abstain=should_abstain,
            abstain_reason=abstain_reason,
            explanation=explanation,
            clock_state=clock_reading.clock_state.value,
        )


def prioritize_risks(assessments: List[RiskAssessment]) -> List[RiskAssessment]:
    """
    Sort risk assessments by priority:
    1. Abstention cases go to top (need human attention)
    2. Then sorted by normalized_risk descending
    """
    # Separate abstentions and scored cases
    abstentions = [a for a in assessments if a.should_abstain]
    scored = [a for a in assessments if not a.should_abstain and a.normalized_risk > 0]
    closed = [a for a in assessments if a.normalized_risk == 0 and not a.should_abstain]

    # Sort scored by risk descending
    scored.sort(key=lambda a: a.normalized_risk, reverse=True)

    return abstentions + scored + closed
