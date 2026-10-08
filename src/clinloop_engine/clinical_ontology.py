"""
clinical_ontology.py — Clinical Domain Knowledge & Obligation Rules

Defines the medical knowledge graph that ClinLoop AI uses to determine
what clinical events MUST follow other events, and within what time windows.
This is the 'Symbolic' half of our Neuro-Symbolic architecture.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Event Types ──────────────────────────────────────────────────────────────

class EventType(Enum):
    """All clinical event types tracked by ClinLoop AI."""
    LAB_ORDER = "lab_order"
    LAB_RESULT = "lab_result"
    IMAGING_ORDER = "imaging_order"
    IMAGING_RESULT = "imaging_result"
    RADIOLOGY_REPORT = "radiology_report"
    SPECIALIST_REFERRAL = "specialist_referral"
    REFERRAL_VISIT = "referral_visit"
    MEDICATION_CHANGE = "medication_change"
    FOLLOWUP_LAB = "followup_lab"
    PATIENT_NOTIFICATION = "patient_notification"
    FOLLOWUP_APPOINTMENT = "followup_appointment"
    DISCHARGE = "discharge"
    PATHOLOGY_RESULT = "pathology_result"
    CULTURE_RESULT = "culture_result"
    CALLBACK = "callback"
    BIOPSY_ORDER = "biopsy_order"
    BIOPSY_RESULT = "biopsy_result"
    COLPOSCOPY_REFERRAL = "colposcopy_referral"
    COLPOSCOPY_VISIT = "colposcopy_visit"
    INR_RECHECK = "inr_recheck"
    FOLLOWUP_CT = "followup_ct"
    PROVIDER_REVIEW = "provider_review"
    POST_OP_WOUND_CHECK = "post_op_wound_check"
    HBA1C_RECHECK = "hba1c_recheck"
    ECHOCARDIOGRAM = "echocardiogram"
    SEPSIS_BUNDLE_COMPLETION = "sepsis_bundle_completion"


# ── Severity Classification ─────────────────────────────────────────────────

class Severity(Enum):
    """Clinical severity levels for missed obligations."""
    CRITICAL = "critical"   # Immediate life-threat (e.g., missed sepsis callback)
    HIGH = "high"           # Serious harm risk (e.g., missed cancer follow-up)
    MODERATE = "moderate"   # Delayed care risk (e.g., missed referral visit)
    LOW = "low"             # Minor inconvenience (e.g., routine follow-up)

SEVERITY_SCORES: Dict[Severity, float] = {
    Severity.CRITICAL: 1.0,
    Severity.HIGH: 0.8,
    Severity.MODERATE: 0.5,
    Severity.LOW: 0.2,
}


# ── Loop Status ──────────────────────────────────────────────────────────────

class LoopStatus(Enum):
    """Status of a clinical obligation loop."""
    CLOSED = "closed"               # All obligations fulfilled
    OPEN = "open"                   # Missing required follow-up
    DELAYED = "delayed"             # Follow-up exists but past deadline
    ABSTAIN = "needs_human_review"  # Insufficient data to determine


# ── Obligation Rules ─────────────────────────────────────────────────────────

@dataclass
class ObligationRule:
    """
    A formal clinical obligation rule.
    
    In Linear Temporal Logic (LTL) notation:
        □ (trigger_condition → ◇_{≤ deadline_days} required_followup)
    
    Meaning: Globally, whenever trigger_condition occurs,
    eventually within deadline_days, required_followup must occur.
    
    followup_logic:
        "all" (conjunction) — ALL required_followups must be present for closure.
        "any" (disjunction) — at least ONE required_followup suffices.
        Default is "all" for patient safety (strictest interpretation).
    """
    rule_id: str
    name: str
    description: str
    trigger_event: EventType
    trigger_condition: str           # e.g., "abnormal", "incidental_nodule_ge_6mm"
    required_followups: List[EventType]
    deadline_days: float             # maximum allowed days for follow-up
    severity: Severity
    clinical_domain: str             # e.g., "laboratory", "radiology", "pharmacy"
    ltl_formula: str                 # formal LTL expression
    references: List[str] = field(default_factory=list)
    followup_logic: str = "all"      # "all" (conjunction) or "any" (disjunction)


# ── Complete Rule Set ────────────────────────────────────────────────────────

OBLIGATION_RULES: List[ObligationRule] = [
    ObligationRule(
        rule_id="R001",
        name="Abnormal Lab → Patient Notification",
        description="Abnormal lab results must be communicated to the patient within 3 days",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="abnormal",
        required_followups=[EventType.PATIENT_NOTIFICATION],
        deadline_days=3.0,
        severity=Severity.HIGH,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[abnormal] → ◇_{≤3d} PATIENT_NOTIFICATION)",
        references=["Callen JL et al. J Gen Intern Med 2012;27:1334-1348"],
    ),
    ObligationRule(
        rule_id="R002",
        name="Abnormal Lab → Follow-up Appointment",
        description="Abnormal lab results require a follow-up appointment within 14 days",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="abnormal",
        required_followups=[EventType.FOLLOWUP_APPOINTMENT],
        deadline_days=14.0,
        severity=Severity.HIGH,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[abnormal] → ◇_{≤14d} FOLLOWUP_APPOINTMENT)",
        references=["Singh H et al. BMJ Qual Saf 2014"],
    ),
    ObligationRule(
        rule_id="R003",
        name="Incidental Lung Nodule ≥6mm → Follow-up CT",
        description="Incidental pulmonary nodule ≥6mm on CT requires follow-up CT within 6 months",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="incidental_nodule_ge_6mm",
        required_followups=[EventType.FOLLOWUP_CT],
        deadline_days=180.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[nodule≥6mm] → ◇_{≤180d} FOLLOWUP_CT)",
        references=["Fleischner Society 2017 Guidelines",
                     "Lacson R et al. JACR 2020"],
    ),
    ObligationRule(
        rule_id="R004",
        name="Elevated PSA → Urology Referral / Biopsy",
        description="Significantly elevated PSA requires urological evaluation",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="elevated_psa",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.BIOPSY_ORDER],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[PSA>threshold] → ◇_{≤30d} (SPECIALIST_REFERRAL ∨ BIOPSY_ORDER))",
        references=["AUA/SUO Early Detection of Prostate Cancer 2023"],
        followup_logic="any",  # Referral OR Biopsy — disjunctive
    ),
    ObligationRule(
        rule_id="R005",
        name="Abnormal Cervical Cytology → Colposcopy Referral",
        description="Abnormal Pap smear requires colposcopy within 30 days",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="abnormal_cervical_cytology",
        required_followups=[EventType.COLPOSCOPY_REFERRAL],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[abnormal_pap] → ◇_{≤30d} COLPOSCOPY_REFERRAL)",
        references=["ASCCP 2019 Risk-Based Management Guidelines"],
    ),
    ObligationRule(
        rule_id="R006",
        name="Post-discharge Positive Culture → Callback",
        description="Positive blood/urine culture finalized after discharge requires urgent callback",
        trigger_event=EventType.CULTURE_RESULT,
        trigger_condition="positive_post_discharge",
        required_followups=[EventType.CALLBACK],
        deadline_days=1.0,
        severity=Severity.CRITICAL,
        clinical_domain="laboratory",
        ltl_formula="□(CULTURE_RESULT[positive] ∧ POST_DISCHARGE → ◇_{≤24h} CALLBACK)",
        references=["CDC DxEx Core Elements 2026"],
    ),
    ObligationRule(
        rule_id="R007",
        name="Warfarin Dose Change → INR Recheck",
        description="Any warfarin/anticoagulant dose change requires INR recheck within 7 days",
        trigger_event=EventType.MEDICATION_CHANGE,
        trigger_condition="anticoagulant_dose_change",
        required_followups=[EventType.INR_RECHECK],
        deadline_days=7.0,
        severity=Severity.HIGH,
        clinical_domain="pharmacy",
        ltl_formula="□(MEDICATION_CHANGE[warfarin] → ◇_{≤7d} INR_RECHECK)",
        references=["ACCP Antithrombotic Therapy Guidelines"],
    ),
    ObligationRule(
        rule_id="R008",
        name="Specialist Referral → Referral Visit",
        description="A specialist referral should be completed within 30 days",
        trigger_event=EventType.SPECIALIST_REFERRAL,
        trigger_condition="any",
        required_followups=[EventType.REFERRAL_VISIT],
        deadline_days=30.0,
        severity=Severity.MODERATE,
        clinical_domain="referral",
        ltl_formula="□(SPECIALIST_REFERRAL → ◇_{≤30d} REFERRAL_VISIT)",
        references=["AHRQ/PSNet Health IT Safe Practices"],
    ),
    ObligationRule(
        rule_id="R009",
        name="Abnormal Pathology → Notification + Referral",
        description="Abnormal pathology results require patient notification and specialist referral",
        trigger_event=EventType.PATHOLOGY_RESULT,
        trigger_condition="abnormal",
        required_followups=[EventType.PATIENT_NOTIFICATION, EventType.SPECIALIST_REFERRAL],
        deadline_days=5.0,
        severity=Severity.HIGH,
        clinical_domain="pathology",
        ltl_formula="□(PATHOLOGY_RESULT[abnormal] → ◇_{≤5d} (NOTIFICATION ∧ ◇_{≤14d} REFERRAL))",
        references=["Singh H et al. BMJ Qual Saf 2014"],
    ),
    ObligationRule(
        rule_id="R010",
        name="Medication Change → Follow-up Labs",
        description="New medication or dose change requires follow-up labs within 14 days",
        trigger_event=EventType.MEDICATION_CHANGE,
        trigger_condition="requires_monitoring",
        required_followups=[EventType.FOLLOWUP_LAB],
        deadline_days=14.0,
        severity=Severity.MODERATE,
        clinical_domain="pharmacy",
        ltl_formula="□(MEDICATION_CHANGE[monitoring_required] → ◇_{≤14d} FOLLOWUP_LAB)",
        references=["ISMP Medication Safety Best Practices"],
    ),
    ObligationRule(
        rule_id="R011",
        name="Normal Lab → Provider Review",
        description="Even normal results should be reviewed/acknowledged by ordering provider",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="normal",
        required_followups=[EventType.PROVIDER_REVIEW],
        deadline_days=7.0,
        severity=Severity.LOW,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[normal] → ◇_{≤7d} PROVIDER_REVIEW)",
        references=["AHRQ Closing the Loop on Test Results"],
    ),
    ObligationRule(
        rule_id="R012",
        name="Abnormal Thyroid Function → Follow-up Labs",
        description="Abnormal TSH/T4 requires repeat labs within 6-8 weeks",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="abnormal_thyroid",
        required_followups=[EventType.FOLLOWUP_LAB],
        deadline_days=56.0,
        severity=Severity.MODERATE,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[abnormal_TSH] → ◇_{≤56d} FOLLOWUP_LAB)",
        references=["ATA Hypothyroidism Guidelines 2014"],
    ),
    ObligationRule(
        rule_id="R013",
        name="Uncontrolled HbA1c (≥9%) → Repeat HbA1c in 3 Months",
        description="Patients with HbA1c ≥9% require repeat testing within 90 days per ADA Standards of Care",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="uncontrolled_hba1c",
        required_followups=[EventType.HBA1C_RECHECK],
        deadline_days=90.0,
        severity=Severity.MODERATE,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[HbA1c≥9%] → ◇_{≤90d} HBA1C_RECHECK)",
        references=["ADA Standards of Medical Care in Diabetes 2024", "PMID: 38078589"],
    ),
    ObligationRule(
        rule_id="R014",
        name="Post-MI Discharge → Cardiology Follow-up ≤14 Days",
        description="Post-myocardial infarction discharge requires cardiology outpatient review within 14 days",
        trigger_event=EventType.DISCHARGE,
        trigger_condition="post_mi_discharge",
        required_followups=[EventType.FOLLOWUP_APPOINTMENT],
        deadline_days=14.0,
        severity=Severity.CRITICAL,
        clinical_domain="cardiology",
        ltl_formula="□(DISCHARGE[post_MI] → ◇_{≤14d} FOLLOWUP_APPOINTMENT)",
        references=["ACC/AHA 2021 Heart Attack Guideline", "PMID: 34756653"],
    ),
    ObligationRule(
        rule_id="R015",
        name="Positive Blood Culture (Bacteremia) → Repeat Culture at 48h",
        description="Any positive blood culture for bacteremia requires repeat culture within 48 hours to confirm clearance",
        trigger_event=EventType.CULTURE_RESULT,
        trigger_condition="bacteremia_confirmed",
        required_followups=[EventType.CULTURE_RESULT, EventType.CALLBACK],
        deadline_days=2.0,
        severity=Severity.CRITICAL,
        clinical_domain="laboratory",
        ltl_formula="□(CULTURE_RESULT[bacteremia] → ◇_{≤48h} REPEAT_CULTURE)",
        references=["IDSA Bacteremia Management Guidelines 2024", "CDC Core Elements 2026"],
    ),
    ObligationRule(
        rule_id="R016",
        name="New Heart Failure Diagnosis → Echocardiogram",
        description="New diagnosis of heart failure requires echocardiogram within 30 days per ACC/AHA guidelines",
        trigger_event=EventType.DISCHARGE,
        trigger_condition="new_heart_failure",
        required_followups=[EventType.ECHOCARDIOGRAM],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="cardiology",
        ltl_formula="□(DISCHARGE[heart_failure_new] → ◇_{≤30d} ECHOCARDIOGRAM)",
        references=["ACC/AHA 2022 Heart Failure Guidelines", "PMID: 35379503"],
    ),
]


# ── Finding-specific deadlines ──────────────────────────────────────────────
#
# Some rules need a deadline that depends on the trigger's details.
#
# R003: Fleischner 2017 recommends CT at 6–12 months for a solid 6–8 mm
#       nodule, but CT at ~3 months, PET/CT or tissue sampling for >8 mm.
#       The 180-day window would let a 12 mm nodule wait six months.
# R010: the generic 14-day lab window is wrong for drugs whose recheck
#       interval differs; low-harm monitoring labs use the guideline's
#       upper bound so a loop is only violated once the window has passed.

FLEISCHNER_LARGE_NODULE_MM = 8.0
FLEISCHNER_LARGE_NODULE_DAYS = 90.0

MONITORING_WINDOW_DAYS: Dict[str, float] = {
    "levothyroxine": 56.0,  # TSH 6–8 weeks after dose change (ATA 2014)
    "lithium": 7.0,         # Serum lithium ~1 week after dose change (NICE CG185)
}


def get_deadline_days(rule: ObligationRule, details: Dict) -> float:
    """Deadline for one triggered obligation, applying finding/drug-specific windows."""
    if rule.rule_id == "R003":
        try:
            if float(details.get("nodule_size_mm", 0)) > FLEISCHNER_LARGE_NODULE_MM:
                return FLEISCHNER_LARGE_NODULE_DAYS
        except (TypeError, ValueError):
            pass
    if rule.rule_id == "R010":
        drug = str(details.get("drug", "")).strip().lower()
        if drug in MONITORING_WINDOW_DAYS:
            return MONITORING_WINDOW_DAYS[drug]
    return rule.deadline_days


# ── Follow-up event statuses ────────────────────────────────────────────────
#
# A follow-up only closes a loop if it actually happened. A cancelled CT, a
# no-show visit or a booked-but-not-yet-attended appointment leaves the
# patient exactly as exposed as no follow-up at all ("click ≠ closure").

NON_FULFILLING_STATUSES = frozenset({
    "cancelled", "canceled", "no_show", "no-show", "noshow",
    "entered-in-error", "entered_in_error", "not-done", "not_done",
    "revoked", "declined", "refused", "failed", "rejected",
    "scheduled", "booked", "planned", "proposed", "pending", "draft",
})


def is_fulfilling_status(status: Optional[str]) -> bool:
    """True if an event with this status counts as a completed follow-up."""
    return str(status or "completed").strip().lower() not in NON_FULFILLING_STATUSES


def get_rule_by_id(rule_id: str) -> Optional[ObligationRule]:
    """Look up an obligation rule by its ID."""
    for rule in OBLIGATION_RULES:
        if rule.rule_id == rule_id:
            return rule
    return None


def get_rules_for_event(event_type: EventType, condition: str) -> List[ObligationRule]:
    """Find all obligation rules that match a given event type and condition."""
    matching = []
    for rule in OBLIGATION_RULES:
        if rule.trigger_event == event_type:
            if rule.trigger_condition == condition or rule.trigger_condition == "any":
                matching.append(rule)
    return matching


def get_severity_score(severity: Severity) -> float:
    """Get the numeric score for a severity level."""
    return SEVERITY_SCORES[severity]
