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
    COLONOSCOPY = "colonoscopy"
    BREAST_BIOPSY = "breast_biopsy"
    CRITICAL_VALUE_NOTIFICATION = "critical_value_notification"
    DIAGNOSIS = "diagnosis"                       # active problem-list entry (FHIR Condition)
    BP_CHECK = "bp_check"
    POSTPARTUM_GLUCOSE_TEST = "postpartum_glucose_test"
    HCV_RNA_TEST = "hcv_rna_test"
    LIVER_IMAGING = "liver_imaging"               # ultrasound (or multiphase CT/MRI) of the liver
    MENTAL_HEALTH_FOLLOWUP = "mental_health_followup"
    IMAGING_CT = "imaging_ct"                     # any completed CT study
    IMAGING_MRI = "imaging_mri"                   # any completed MRI study
    IMAGING_ULTRASOUND = "imaging_ultrasound"     # any completed ultrasound study
    IMAGING_XRAY = "imaging_xray"                 # any completed radiograph
    IMAGING_PET = "imaging_pet"                   # any completed PET or PET/CT study
    ENDOSCOPIC_ULTRASOUND = "endoscopic_ultrasound"
    RISK_FACTOR = "risk_factor"                   # e.g. smoking status (context only, never a trigger)
    AI_FINDING = "ai_finding"                     # positive finding from an imaging-AI product (second reader)
    AI_FINDING_REVIEWED = "ai_finding_reviewed"   # a radiologist addressed the AI finding (report/addendum)
    CLINICAL_NOTE_PLAN = "clinical_note_plan"     # a concrete plan written in a clinician's note (note_reader)
    DIAGNOSTIC_PATTERN = "diagnostic_pattern"     # a dangerous combination across events (motifs.py)
    SECOND_READER_FLAG = "second_reader_flag"     # an actionable report item no rule tracked (second_reader.py)
    ECG = "ecg"                                   # an electrocardiogram and its interpretation (fhir_ingest, ecg)


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
    # No rule may drive alerts in a real deployment until a named specialist
    # has signed it off (see docs/LIFE_SAVING_ROADMAP.md §3.1, §6).
    review_status: str = "pending_specialist_review"
    evidence_note: str = ""          # caveats on the deadline, shown to reviewers
    # False for loops a clinician must handle personally (e.g. after self-harm):
    # ClinLoop never drafts a patient message for them.
    patient_outreach: bool = True


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
        name="Incidental Lung Nodule → Fleischner Follow-up CT",
        description=("Incidental lung nodule needing follow-up under Fleischner 2017 (by size, solid / part-solid / "
                     "ground-glass, single / multiple, risk, and stepped follow-up of a known nodule)"),
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="incidental_nodule_ge_6mm",
        required_followups=[EventType.FOLLOWUP_CT, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT],
        deadline_days=180.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[lung nodule≥6mm] → ◇_{≤180d} (FOLLOWUP_CT ∨ BIOPSY))",
        references=["Fleischner Society 2017 Guidelines",
                     "Lacson R et al. JACR 2020"],
        followup_logic="any",
        evidence_note=("Deadline from the Fleischner 2017 table (upper bound of the interval): solid 6–8 mm 12 months, "
                       ">8 mm 3 months, multiple 3–6 months, ground-glass ≥6 mm 12 months, part-solid ≥6 mm 3–6 months; "
                       "stepped follow-up for a stable nodule; unknown risk managed as high risk. Lung nodules only, "
                       "not screening LDCT (Lung-RADS). Age <35, known cancer or immunocompromise → human review. "
                       "Tissue sampling also closes the loop."),
    ),
    ObligationRule(
        rule_id="R004",
        name="Elevated PSA → Urology Referral / Biopsy",
        description="Significantly elevated PSA requires urological evaluation",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="elevated_psa",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[PSA>threshold] → ◇_{≤30d} (SPECIALIST_REFERRAL ∨ BIOPSY_ORDER ∨ BIOPSY_RESULT))",
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

    # ── Wave 1: highest-yield loops (docs/LIFE_SAVING_ROADMAP.md §2) ─────────
    ObligationRule(
        rule_id="R017",
        name="Positive FIT → Diagnostic Colonoscopy",
        description="A positive fecal immunochemical test requires diagnostic colonoscopy",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="positive_fit",
        required_followups=[EventType.COLONOSCOPY],
        deadline_days=90.0,
        severity=Severity.HIGH,
        clinical_domain="cancer_screening",
        ltl_formula="□(LAB_RESULT[FIT+] → ◇_{≤90d} COLONOSCOPY)",
        references=["Corley DA et al. JAMA 2017;317:1631-1641",
                    "Korean National Cancer Screening Program (FIT from age 50)"],
        evidence_note=("Risk of advanced-stage cancer rises with longer FIT+-to-colonoscopy "
                       "intervals; programme targets are often shorter than 90 days."),
    ),
    ObligationRule(
        rule_id="R018",
        name="Mammography BI-RADS 4/5 → Tissue Diagnosis",
        description="Suspicious (BI-RADS 4) or highly suggestive (BI-RADS 5) findings require biopsy",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="birads_4_5",
        required_followups=[EventType.BREAST_BIOPSY],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="cancer_screening",
        ltl_formula="□(RADIOLOGY_REPORT[BI-RADS 4/5] → ◇_{≤30d} BREAST_BIOPSY)",
        references=["ACR BI-RADS Atlas, 5th ed. (2013)"],
        evidence_note="BI-RADS mandates tissue diagnosis; the 30-day window is a quality target.",
    ),
    ObligationRule(
        rule_id="R019",
        name="Lung-RADS 4A → 3-Month LDCT",
        description="Lung-RADS category 4A on screening LDCT requires 3-month LDCT (or PET/CT)",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="lung_rads_4a",
        required_followups=[EventType.FOLLOWUP_CT],
        deadline_days=90.0,
        severity=Severity.HIGH,
        clinical_domain="cancer_screening",
        ltl_formula="□(RADIOLOGY_REPORT[Lung-RADS 4A] → ◇_{≤90d+grace} FOLLOWUP_CT)",
        references=["ACR Lung-RADS v2022"],
        evidence_note="Scheduled interval plus a grace period (25%, 7–30 days), as for R030–R033.",
    ),
    ObligationRule(
        rule_id="R020",
        name="Lung-RADS 4B/4X → Diagnostic Work-up",
        description="Lung-RADS 4B/4X requires diagnostic CT, PET/CT, tissue sampling or referral",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="lung_rads_4b_4x",
        required_followups=[EventType.FOLLOWUP_CT, EventType.BIOPSY_ORDER,
                            EventType.SPECIALIST_REFERRAL],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="cancer_screening",
        ltl_formula="□(RADIOLOGY_REPORT[Lung-RADS 4B/4X] → ◇_{≤30d} (CT ∨ BIOPSY ∨ REFERRAL))",
        references=["ACR Lung-RADS v2022"],
        followup_logic="any",
        evidence_note="Lung-RADS gives no explicit interval for 4B/4X; 30 days is a proposed target.",
    ),
    ObligationRule(
        rule_id="R021",
        name="Abnormal Result After Discharge → Clinician Review",
        description="An abnormal result finalised after the patient left hospital must be reviewed by a responsible clinician",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="abnormal_post_discharge",
        required_followups=[EventType.PROVIDER_REVIEW],
        deadline_days=3.0,
        severity=Severity.HIGH,
        clinical_domain="transitions_of_care",
        ltl_formula="□(LAB_RESULT[abnormal ∧ after_discharge] → ◇_{≤3d} PROVIDER_REVIEW)",
        references=["Roy CL et al. Ann Intern Med 2005;143:121-128"],
    ),
    ObligationRule(
        rule_id="R022",
        name="Critical Value → Documented Clinician Notification ≤1 Hour",
        description="A critical (panic) result must be communicated to a responsible clinician and documented",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="critical_value",
        required_followups=[EventType.CRITICAL_VALUE_NOTIFICATION],
        deadline_days=1.0 / 24.0,
        severity=Severity.CRITICAL,
        clinical_domain="laboratory",
        ltl_formula="□(LAB_RESULT[critical] → ◇_{≤1h} CRITICAL_VALUE_NOTIFICATION)",
        references=["CLSI GP47 Management of Critical- and Significant-Risk Results",
                    "The Joint Commission NPSG.02.03.01"],
        evidence_note="Institutions set the exact window; 1 hour is a common upper limit.",
        patient_outreach=False,
    ),

    # ── Wave 2 (docs/LIFE_SAVING_ROADMAP.md §2) ──────────────────────────────
    ObligationRule(
        rule_id="R023",
        name="Heart Failure Discharge → Clinic Visit ≤7 Days",
        description="Patients discharged after heart failure hospitalisation need an early follow-up visit",
        trigger_event=EventType.DISCHARGE,
        trigger_condition="heart_failure_discharge",
        required_followups=[EventType.FOLLOWUP_APPOINTMENT],
        deadline_days=7.0,
        severity=Severity.HIGH,
        clinical_domain="cardiology",
        ltl_formula="□(DISCHARGE[heart_failure] → ◇_{≤7d} FOLLOWUP_APPOINTMENT)",
        references=["Heidenreich PA et al. 2022 AHA/ACC/HFSA Heart Failure Guideline. Circulation 2022"],
    ),
    ObligationRule(
        rule_id="R024",
        name="Hypertensive Disorder of Pregnancy → Postpartum BP Check",
        description="Postpartum blood pressure evaluation: within 72 hours if severe, otherwise within 7–10 days",
        trigger_event=EventType.DISCHARGE,
        trigger_condition="hypertensive_disorder_pregnancy",
        required_followups=[EventType.BP_CHECK],
        deadline_days=10.0,
        severity=Severity.HIGH,
        clinical_domain="maternal",
        ltl_formula="□(DISCHARGE[HDP] → ◇_{≤10d (≤72h if severe)} BP_CHECK)",
        references=["ACOG Committee Opinion No. 736: Optimizing Postpartum Care (2018)"],
    ),
    ObligationRule(
        rule_id="R025",
        name="Gestational Diabetes → Postpartum Glucose Test (4–12 Weeks)",
        description="Women with gestational diabetes need a 75 g OGTT 4–12 weeks after delivery",
        trigger_event=EventType.DISCHARGE,
        trigger_condition="gestational_diabetes_delivery",
        required_followups=[EventType.POSTPARTUM_GLUCOSE_TEST],
        deadline_days=84.0,
        severity=Severity.MODERATE,
        clinical_domain="maternal",
        ltl_formula="□(DISCHARGE[GDM delivery] → ◇_{≤12w} POSTPARTUM_GLUCOSE_TEST)",
        references=["ADA Standards of Care in Diabetes 2024, Section 15", "ACOG Practice Bulletin No. 190"],
    ),
    ObligationRule(
        rule_id="R026",
        name="HCV Antibody Positive → HCV RNA Test",
        description="A reactive hepatitis C antibody needs an RNA test to establish current infection",
        trigger_event=EventType.LAB_RESULT,
        trigger_condition="hcv_antibody_positive",
        required_followups=[EventType.HCV_RNA_TEST],
        deadline_days=30.0,
        severity=Severity.MODERATE,
        clinical_domain="infectious_disease",
        ltl_formula="□(LAB_RESULT[HCV Ab+] → ◇_{≤30d} HCV_RNA_TEST)",
        references=["CDC Recommendations for Hepatitis C Screening Among Adults, MMWR 2020;69(RR-2)"],
        evidence_note="CDC recommends reflex RNA testing on the same specimen; 30 days is a proposed outer limit.",
    ),
    ObligationRule(
        rule_id="R027",
        name="HCC Risk (Chronic HBV / Cirrhosis) → Liver Surveillance Imaging",
        description="Patients at high risk of hepatocellular carcinoma need liver ultrasound every 6 months",
        trigger_event=EventType.DIAGNOSIS,
        trigger_condition="hcc_risk",
        required_followups=[EventType.LIVER_IMAGING],
        deadline_days=213.0,
        severity=Severity.HIGH,
        clinical_domain="hepatology",
        ltl_formula="□(DIAGNOSIS[HBV ∨ cirrhosis] → ◇_{≤6m} LIVER_IMAGING)",
        references=["KASL-NCC 2022 HCC Practice Guideline", "AASLD 2023 HCC Practice Guidance"],
        evidence_note="6-month interval plus 1 month scheduling tolerance.",
    ),
    ObligationRule(
        rule_id="R028",
        name="HCC Surveillance Imaging → Next Imaging in 6 Months",
        description="Each surveillance ultrasound in a high-risk patient starts the next 6-month interval",
        trigger_event=EventType.LIVER_IMAGING,
        trigger_condition="hcc_surveillance",
        required_followups=[EventType.LIVER_IMAGING],
        deadline_days=213.0,
        severity=Severity.HIGH,
        clinical_domain="hepatology",
        ltl_formula="□(LIVER_IMAGING[surveillance] → ◇_{≤6m} LIVER_IMAGING)",
        references=["KASL-NCC 2022 HCC Practice Guideline", "AASLD 2023 HCC Practice Guidance"],
        evidence_note="6-month interval plus 1 month scheduling tolerance.",
    ),
    ObligationRule(
        rule_id="R029",
        name="Self-Harm or Psychiatric Discharge → Mental-Health Follow-up ≤7 Days",
        description="After an ED visit for self-harm or a psychiatric admission, follow-up within 7 days",
        trigger_event=EventType.DISCHARGE,
        trigger_condition="mental_health_discharge",
        required_followups=[EventType.MENTAL_HEALTH_FOLLOWUP],
        deadline_days=7.0,
        severity=Severity.CRITICAL,
        clinical_domain="mental_health",
        ltl_formula="□(DISCHARGE[self_harm ∨ psychiatric] → ◇_{≤7d} MENTAL_HEALTH_FOLLOWUP)",
        references=["NCQA HEDIS FUH / FUM 7-day follow-up measures"],
        evidence_note=("Deploy only with psychiatry co-design and crisis protocols. Clinician-handled: "
                       "ClinLoop never contacts the patient for this rule."),
        patient_outreach=False,
    ),

    # ── Radiologist-recommended follow-up (deadline taken from the report) ───
    ObligationRule(
        rule_id="R030",
        name="Radiologist-Recommended CT",
        description="Follow-up CT recommended in the radiology report, within the stated interval",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="radiologist_rec_ct",
        required_followups=[EventType.IMAGING_CT],
        deadline_days=90.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[recommend CT in T] → ◇_{≤T+grace} IMAGING_CT)",
        references=["ACR Actionable Reporting Work Group, JACR 2014;11:552-558"],
        evidence_note=("Interval from the report plus a grace period (25%, 7–30 days). The follow-up study must cover "
                       "the body region the recommendation names (an abdominal CT covers the adrenals; a head CT does not)."),
    ),
    ObligationRule(
        rule_id="R031",
        name="Radiologist-Recommended MRI",
        description="Follow-up MRI recommended in the radiology report, within the stated interval",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="radiologist_rec_mri",
        required_followups=[EventType.IMAGING_MRI],
        deadline_days=90.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[recommend MRI in T] → ◇_{≤T+grace} IMAGING_MRI)",
        references=["ACR Actionable Reporting Work Group, JACR 2014;11:552-558"],
        evidence_note=("Interval from the report plus a grace period (25%, 7–30 days). The follow-up study must cover "
                       "the body region the recommendation names (an abdominal CT covers the adrenals; a head CT does not)."),
    ),
    ObligationRule(
        rule_id="R032",
        name="Radiologist-Recommended Ultrasound",
        description="Follow-up ultrasound recommended in the radiology report, within the stated interval",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="radiologist_rec_ultrasound",
        required_followups=[EventType.IMAGING_ULTRASOUND],
        deadline_days=90.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[recommend US in T] → ◇_{≤T+grace} IMAGING_ULTRASOUND)",
        references=["ACR Actionable Reporting Work Group, JACR 2014;11:552-558"],
        evidence_note=("Interval from the report plus a grace period (25%, 7–30 days). The follow-up study must cover "
                       "the body region the recommendation names (an abdominal CT covers the adrenals; a head CT does not)."),
    ),
    ObligationRule(
        rule_id="R033",
        name="Radiologist-Recommended Radiograph",
        description="Follow-up radiograph (e.g. chest X-ray to document resolution) recommended in the report",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="radiologist_rec_xray",
        required_followups=[EventType.IMAGING_XRAY],
        deadline_days=90.0,
        severity=Severity.MODERATE,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[recommend radiograph in T] → ◇_{≤T+grace} IMAGING_XRAY)",
        references=["ACR Actionable Reporting Work Group, JACR 2014;11:552-558",
                    "BTS Guidelines for community-acquired pneumonia in adults (2009): repeat CXR ~6 weeks"],
        evidence_note=("Interval from the report plus a grace period. A recommendation without an interval "
                       "uses a 30-day default. The follow-up radiograph must cover the same body region."),
    ),
    ObligationRule(
        rule_id="R034",
        name="Lung-RADS 3 → 6-Month LDCT",
        description="Lung-RADS category 3 on screening LDCT requires 6-month LDCT",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="lung_rads_3",
        required_followups=[EventType.FOLLOWUP_CT],
        deadline_days=182.6,
        severity=Severity.MODERATE,
        clinical_domain="cancer_screening",
        ltl_formula="□(RADIOLOGY_REPORT[Lung-RADS 3] → ◇_{≤6mo+grace} FOLLOWUP_CT)",
        references=["ACR Lung-RADS v2022"],
        evidence_note="Scheduled interval plus a grace period (25%, 7–30 days).",
    ),
    ObligationRule(
        rule_id="R035",
        name="Critical Imaging Finding → Documented Clinician Communication ≤1 Hour",
        description=("An emergent imaging finding (e.g. acute PE, aortic dissection, intracranial haemorrhage, "
                     "pneumothorax, free air) must be communicated directly to a responsible clinician"),
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="critical_imaging_finding",
        required_followups=[EventType.CRITICAL_VALUE_NOTIFICATION],
        deadline_days=1.0 / 24.0,
        severity=Severity.CRITICAL,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[critical finding] → ◇_{≤1h} CRITICAL_VALUE_NOTIFICATION)",
        references=["ACR Practice Parameter for Communication of Diagnostic Imaging Findings (2020)",
                    "The Joint Commission NPSG.02.03.01"],
        evidence_note=("Closed by a documented communication: a FHIR Communication, or a statement in the "
                       "report itself ('discussed with Dr …', 'communicated to …'). Institutions set the "
                       "window and the list of critical findings."),
        patient_outreach=False,
    ),
    ObligationRule(
        rule_id="R036",
        name="Radiologist-Recommended Tissue Sampling → Biopsy/FNA",
        description="Biopsy or fine-needle aspiration recommended in the radiology report (e.g. TI-RADS, renal or liver mass)",
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="radiologist_rec_biopsy",
        required_followups=[EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT, EventType.PATHOLOGY_RESULT],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(RADIOLOGY_REPORT[recommend biopsy/FNA] → ◇_{≤30d} (BIOPSY ∨ PATHOLOGY))",
        references=["ACR Actionable Reporting Work Group, JACR 2014;11:552-558",
                    "ACR TI-RADS, JACR 2017;14:587-595"],
        followup_logic="any",
        evidence_note=("30 days is a proposed target. Not applied when BI-RADS, Lung-RADS or the lung-nodule "
                       "rule already governs the same finding."),
    ),
    ObligationRule(
        rule_id="R037",
        name='Incidental Adrenal Nodule → Adrenal CT/MRI',
        description='Indeterminate adrenal nodule 1–4 cm needs adrenal protocol CT or MRI (12 months for 1–2 cm)',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="adrenal_nodule_followup",
        required_followups=[EventType.IMAGING_CT, EventType.IMAGING_MRI],
        deadline_days=395.25,
        severity=Severity.MODERATE,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[adrenal 1–4 cm, indeterminate] → ◇_{≤T} (CT ∨ MRI)[adrenal])',
        references=['ACR Incidental Findings: adrenal (Mayo-Smith WW et al. JACR 2017;14:1038-1044)'],
        followup_logic="any",
        evidence_note='1–2 cm: 12 months + grace; 2–4 cm: characterise (90 days, proposed). Benign features (adenoma ≤10 HU, myelolipoma, stable ≥1 year) are excluded. Follow-up must cover the adrenals.',
    ),
    ObligationRule(
        rule_id="R038",
        name='Adrenal Mass ≥4 cm (or Nodule with Known Cancer) → Specialist Work-up',
        description='Adrenal mass ≥4 cm, or adrenal nodule ≥1 cm in a patient with cancer, needs referral, PET/CT or biopsy',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="adrenal_mass_workup",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT, EventType.IMAGING_PET, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[adrenal ≥4 cm ∨ (≥1 cm ∧ cancer)] → ◇_{≤30d} (REFERRAL ∨ PET ∨ BIOPSY))',
        references=['ACR Incidental Findings: adrenal (Mayo-Smith WW et al. JACR 2017;14:1038-1044)'],
        followup_logic="any",
        evidence_note='30 days is a proposed target. Biochemical (hormonal) evaluation is also advised and is not tracked.',
    ),
    ObligationRule(
        rule_id="R039",
        name='Suspicious Renal Mass → Urology Referral',
        description='Solid enhancing renal mass or Bosniak III/IV cyst needs urology referral or biopsy',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="suspicious_renal_mass",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[solid renal mass ∨ Bosniak III/IV] → ◇_{≤30d} (REFERRAL ∨ BIOPSY))',
        references=['ACR Incidental Findings: renal (Herts BR et al. JACR 2018;15:264-273)', 'Silverman SG et al. Bosniak v2019. Radiology 2019;292:475-488'],
        followup_logic="any",
        evidence_note='30 days is a proposed target.',
    ),
    ObligationRule(
        rule_id="R040",
        name='Indeterminate Renal Lesion / Bosniak IIF → Renal CT/MRI',
        description='Indeterminate renal lesion ≥1 cm or Bosniak IIF cyst needs renal mass protocol CT or MRI',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="renal_lesion_followup",
        required_followups=[EventType.IMAGING_CT, EventType.IMAGING_MRI],
        deadline_days=90.0,
        severity=Severity.MODERATE,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[indeterminate renal ∨ Bosniak IIF] → ◇_{≤T} (CT ∨ MRI)[kidney])',
        references=['ACR Incidental Findings: renal (Herts BR et al. JACR 2018;15:264-273)', 'Silverman SG et al. Bosniak v2019. Radiology 2019;292:475-488'],
        followup_logic="any",
        evidence_note='Bosniak IIF: 6 months + grace; indeterminate ≥1 cm: 90 days (proposed). Simple cysts, Bosniak I–II, angiomyolipoma and lesions too small to characterise are excluded.',
    ),
    ObligationRule(
        rule_id="R041",
        name='Incidental Pancreatic Cyst → MRI/MRCP Surveillance',
        description='Incidental pancreatic cyst needs MRI/MRCP surveillance at a size-based interval',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="pancreatic_cyst_followup",
        required_followups=[EventType.IMAGING_MRI, EventType.IMAGING_CT, EventType.ENDOSCOPIC_ULTRASOUND],
        deadline_days=395.25,
        severity=Severity.MODERATE,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[pancreatic cyst] → ◇_{≤T(size)} (MRI ∨ CT ∨ EUS)[pancreas])',
        references=['ACR Incidental Findings: pancreatic cysts (Megibow AJ et al. JACR 2017;14:911-923)'],
        followup_logic="any",
        evidence_note='<1.5 cm: 2 years; 1.5–2.5 cm: 1 year; >2.5 cm: 6 months or EUS-FNA (each + grace). ACR also adjusts by age (≥80) and growth: specialist review required.',
    ),
    ObligationRule(
        rule_id="R042",
        name='Pancreatic Cyst with Worrisome Features → EUS / Specialist',
        description='Pancreatic cyst with main duct ≥7 mm, mural nodule or solid component needs EUS or pancreas specialist',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="pancreatic_cyst_worrisome",
        required_followups=[EventType.ENDOSCOPIC_ULTRASOUND, EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[pancreatic cyst ∧ worrisome] → ◇_{≤30d} (EUS ∨ REFERRAL ∨ BIOPSY))',
        references=['ACR Incidental Findings: pancreatic cysts (Megibow AJ et al. JACR 2017;14:911-923)'],
        followup_logic="any",
        evidence_note='30 days is a proposed target.',
    ),
    ObligationRule(
        rule_id="R043",
        name='Incidental Thyroid Nodule on CT/MRI/PET → Thyroid Ultrasound',
        description='Thyroid nodule ≥1.5 cm (≥1 cm under 35), with suspicious features, or FDG-avid needs thyroid ultrasound',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="incidental_thyroid_nodule",
        required_followups=[EventType.IMAGING_ULTRASOUND],
        deadline_days=90.0,
        severity=Severity.MODERATE,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[thyroid nodule meeting ACR criteria] → ◇_{≤90d} ULTRASOUND[thyroid])',
        references=['ACR Incidental Findings: thyroid (Hoang JK et al. JACR 2015;12:143-150)'],
        followup_logic="any",
        evidence_note='90 days is a proposed target. Age unknown → the 1 cm threshold is used. On thyroid ultrasound, ACR TI-RADS criteria apply instead (R036 FNA, R032 follow-up).',
    ),
    ObligationRule(
        rule_id="R044",
        name='Abdominal Aortic Aneurysm → Surveillance Imaging',
        description='Incidental abdominal aortic dilatation ≥2.5 cm needs surveillance imaging at a diameter-based interval',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="aaa_surveillance",
        required_followups=[EventType.IMAGING_ULTRASOUND, EventType.IMAGING_CT, EventType.IMAGING_MRI],
        deadline_days=365.25,
        severity=Severity.MODERATE,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[abdominal aorta ≥2.5 cm] → ◇_{≤T(diameter)} (US ∨ CT ∨ MRI)[abdominal aorta])',
        references=['ACR Incidental Findings: vascular (Khosa F et al. JACR 2013;10:789-794)', 'Chaikof EL et al. SVS AAA guidelines. J Vasc Surg 2018;67:2-77'],
        followup_logic="any",
        evidence_note='2.5–2.9 cm 5 years; 3.0–3.4 cm 3 years; 3.5–3.9 cm 2 years; 4.0–4.4 cm 1 year; ≥4.5 cm 6 months (each + grace).',
    ),
    ObligationRule(
        rule_id="R045",
        name='Abdominal Aortic Aneurysm at Repair Threshold → Vascular Surgery',
        description='AAA ≥5.5 cm (≥5.0 cm in women) needs vascular surgery referral',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="aaa_repair_threshold",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT],
        deadline_days=14.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[AAA ≥5.5 cm (♀ ≥5.0)] → ◇_{≤14d} REFERRAL)',
        references=['Chaikof EL et al. SVS AAA guidelines. J Vasc Surg 2018;67:2-77', 'ACR Incidental Findings: vascular (Khosa F et al. JACR 2013)'],
        followup_logic="any",
        evidence_note='14 days is a proposed target; a symptomatic or ruptured aneurysm is a critical finding (R035).',
    ),
    ObligationRule(
        rule_id="R046",
        name='Growing or Suspicious Lung Nodule → Work-up',
        description='Lung nodule that grew, or persistent part-solid nodule with solid component ≥6 mm, needs PET/CT, tissue sampling or specialist referral',
        trigger_event=EventType.RADIOLOGY_REPORT,
        trigger_condition="suspicious_lung_nodule",
        required_followups=[EventType.IMAGING_PET, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT, EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT],
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula='□(RADIOLOGY_REPORT[nodule growth ∨ persistent part-solid ≥6 mm solid] → ◇_{≤30d} (PET ∨ BIOPSY ∨ REFERRAL))',
        references=['Fleischner Society 2017 (MacMahon H et al. Radiology 2017;284:228-243)'],
        followup_logic="any",
        evidence_note="Growth = report says so, or ≥2 mm larger than the patient's previous report. 30 days is a proposed target.",
    ),
    ObligationRule(
        rule_id="R047",
        name="Imaging-AI Finding Not Addressed in the Report → Radiologist Review",
        description=("An imaging-AI product flagged a finding (e.g. lung nodule, pneumothorax) that the radiology "
                     "report does not mention; a radiologist must review the images and document a decision"),
        trigger_event=EventType.AI_FINDING,
        trigger_condition="ai_report_discrepancy",
        required_followups=[EventType.AI_FINDING_REVIEWED],
        deadline_days=7.0,
        severity=Severity.HIGH,
        clinical_domain="radiology",
        ltl_formula="□(AI_FINDING[positive ∧ ¬mentioned in report] → ◇_{≤7d} AI_FINDING_REVIEWED)",
        references=["ACR Data Science Institute: AI in clinical practice (second-reader use)",
                    "MFDS 인공지능 의료기기 허가·심사 가이드라인"],
        evidence_note=("The AI is a second reader, never a diagnosis. Critical findings (pneumothorax, free air, "
                       "intracranial haemorrhage) are due within 1 day. Closed by a report or addendum that addresses "
                       "the finding (confirming or refuting it), or by a clinician closing the loop with evidence. "
                       "Findings from research-use models count only when the hospital enables them."),
        patient_outreach=False,
    ),
    # ── Plans written in clinicians' notes (note_reader.py) ───────────────────
    ObligationRule(
        rule_id="R048",
        name="Note Plan: Repeat Lab Test",
        description="A clinician's note plans to repeat or check a lab test (e.g. 'repeat potassium in 1 week')",
        trigger_event=EventType.CLINICAL_NOTE_PLAN,
        trigger_condition="note_plan_lab",
        required_followups=[EventType.LAB_RESULT, EventType.FOLLOWUP_LAB, EventType.INR_RECHECK,
                            EventType.HBA1C_RECHECK, EventType.HCV_RNA_TEST, EventType.POSTPARTUM_GLUCOSE_TEST],
        followup_logic="any",
        deadline_days=30.0,
        severity=Severity.MODERATE,
        clinical_domain="clinical documentation",
        ltl_formula="□(NOTE_PLAN[repeat test X in T] → ◇_{≤T+grace} LAB_RESULT[X])",
        references=["Singh H et al. Missed follow-up of test results. JAMA Intern Med 2013;173:702-704",
                    "Joint Commission Sentinel Event Alert 47 (diagnostic error, follow-up of results)"],
        evidence_note=("Closed by a result of the same test (potassium plan → potassium result). 'Repeat labs' with no "
                       "named test is closed by any lab result. Interval from the note plus 15% (at least 3 days); "
                       "30 days when the note states none. Conditional, cancelled or already-done plans are not tracked."),
    ),
    ObligationRule(
        rule_id="R049",
        name="Note Plan: Imaging",
        description="A clinician's note plans an imaging study (e.g. 'CT chest in 3 months', '3개월 후 흉부 CT')",
        trigger_event=EventType.CLINICAL_NOTE_PLAN,
        trigger_condition="note_plan_imaging",
        required_followups=[EventType.IMAGING_CT, EventType.FOLLOWUP_CT, EventType.IMAGING_MRI,
                            EventType.IMAGING_ULTRASOUND, EventType.LIVER_IMAGING, EventType.IMAGING_XRAY,
                            EventType.IMAGING_PET, EventType.ECHOCARDIOGRAM],
        followup_logic="any",
        deadline_days=90.0,
        severity=Severity.HIGH,
        clinical_domain="clinical documentation",
        ltl_formula="□(NOTE_PLAN[imaging M of region R in T] → ◇_{≤T+grace} IMAGING[M ∧ covers R])",
        references=["Callen JL et al. Failure to follow-up test results for ambulatory patients. J Gen Intern Med 2012;27:1334-48"],
        evidence_note=("Closed only by a study of the same modality that covers the region the note names. Interval from "
                       "the note plus the radiology grace period; 90 days when the note states none."),
    ),
    ObligationRule(
        rule_id="R050",
        name="Note Plan: Specialist Referral",
        description="A clinician's note plans a referral (e.g. 'refer to cardiology', '심장내과 협진 의뢰')",
        trigger_event=EventType.CLINICAL_NOTE_PLAN,
        trigger_condition="note_plan_referral",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT, EventType.FOLLOWUP_APPOINTMENT],
        followup_logic="any",
        deadline_days=30.0,
        severity=Severity.MODERATE,
        clinical_domain="clinical documentation",
        ltl_formula="□(NOTE_PLAN[refer to S] → ◇_{≤30d} (REFERRAL[S] ∨ VISIT[S]))",
        references=["Gandhi TK et al. Communication breakdown in the outpatient referral process. J Gen Intern Med 2000;15:626-31"],
        evidence_note="Closed by a referral order or a visit to the same specialty. 30 days when the note states no interval.",
    ),
    ObligationRule(
        rule_id="R051",
        name="Note Plan: Follow-up Visit",
        description="A clinician's note plans a follow-up visit (e.g. 'RTC 6 weeks', '6주 후 외래 재방문')",
        trigger_event=EventType.CLINICAL_NOTE_PLAN,
        trigger_condition="note_plan_visit",
        required_followups=[EventType.FOLLOWUP_APPOINTMENT, EventType.REFERRAL_VISIT],
        followup_logic="any",
        deadline_days=30.0,
        severity=Severity.MODERATE,
        clinical_domain="clinical documentation",
        ltl_formula="□(NOTE_PLAN[follow-up in T] → ◇_{≤T+grace} FOLLOWUP_APPOINTMENT)",
        references=["Joint Commission Sentinel Event Alert 47 (diagnostic error, follow-up)"],
        evidence_note="Closed by a follow-up appointment that took place. Booked-but-not-attended visits do not count.",
    ),
    # ── Diagnostic patterns across events (motifs.py) ────────────────────────
    ObligationRule(
        rule_id="R052",
        name="Iron-Deficiency Anaemia → GI Investigation",
        description=("Low haemoglobin and low ferritin within 90 days in a man ≥ 18 or a woman ≥ 50, with no colonoscopy "
                     "or GI referral in the past year: investigate for gastrointestinal (colorectal) cancer"),
        trigger_event=EventType.DIAGNOSTIC_PATTERN,
        trigger_condition="pattern_ida",
        required_followups=[EventType.COLONOSCOPY, EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT],
        followup_logic="any",
        deadline_days=60.0,
        severity=Severity.HIGH,
        clinical_domain="diagnostic safety",
        ltl_formula="□(Hb↓ ∧ ferritin↓ within 90d ∧ (male ∨ age ≥ 50) → ◇_{≤60d (14d if ≥60)} (COLONOSCOPY ∨ GI_REFERRAL))",
        references=["Snook J et al. BSG guidelines for the management of iron deficiency anaemia in adults. Gut 2021;70:2030-51",
                    "NICE NG12: Suspected cancer: recognition and referral (IDA ≥ 60 years)"],
        evidence_note=("Thresholds: Hb < 13 g/dL (men) / < 12 g/dL (women), ferritin < 30 µg/L. Women under 50 are excluded "
                       "(menstrual loss is the usual cause); clinicians may still investigate. Age ≥ 60: 14 days."),
    ),
    ObligationRule(
        rule_id="R053",
        name="Creatinine Rise (AKI Warning) → Repeat Creatinine",
        description="Creatinine ≥ 1.5 × baseline and ≥ 0.3 mg/dL higher: acute kidney injury until shown otherwise",
        trigger_event=EventType.DIAGNOSTIC_PATTERN,
        trigger_condition="pattern_creatinine_rise",
        required_followups=[EventType.LAB_RESULT],
        followup_logic="any",
        deadline_days=3.0,
        severity=Severity.HIGH,
        clinical_domain="diagnostic safety",
        ltl_formula="□(Cr ≥ 1.5 × baseline → ◇_{≤3d} Cr)",
        references=["KDIGO Clinical Practice Guideline for Acute Kidney Injury. Kidney Int Suppl 2012;2:1-138",
                    "NICE NG148: Acute kidney injury (AKI detection algorithm)"],
        evidence_note=("Baseline: lowest creatinine in the previous 7 days, else the median of the previous 8–365 days "
                       "(NHS England AKI algorithm). Same unit only. Closed by a repeat creatinine."),
    ),
    ObligationRule(
        rule_id="R054",
        name="Atrial Fibrillation, High Stroke Risk → Anticoagulation Decision",
        description=("Atrial fibrillation with CHA₂DS₂-VASc ≥ 2 (men) / ≥ 3 (women) and no anticoagulant: decide on "
                     "anticoagulation (or document why not)"),
        trigger_event=EventType.DIAGNOSTIC_PATTERN,
        trigger_condition="pattern_af_no_anticoagulation",
        required_followups=[EventType.MEDICATION_CHANGE],
        followup_logic="any",
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="diagnostic safety",
        ltl_formula="□(AF ∧ CHA₂DS₂-VASc ≥ 2♂/3♀ ∧ ¬OAC → ◇_{≤30d} OAC ∨ documented decision)",
        references=["Hindricks G et al. 2020 ESC Guidelines for atrial fibrillation. Eur Heart J 2021;42:373-498",
                    "Joglar JA et al. 2023 ACC/AHA/ACCP/HRS Guideline for Atrial Fibrillation. Circulation 2024;149:e1-e156"],
        evidence_note=("CHA₂DS₂-VASc from the problem list (heart failure, hypertension, diabetes, stroke/TIA, vascular "
                       "disease), age and sex. A clinician closes the loop with evidence when anticoagulation is "
                       "contraindicated or declined."),
    ),
    ObligationRule(
        rule_id="R055",
        name="Persistent Microscopic Haematuria → Urology Evaluation",
        description="≥ 3 RBC/hpf on two urine tests within 12 months at age ≥ 35: urological evaluation",
        trigger_event=EventType.DIAGNOSTIC_PATTERN,
        trigger_condition="pattern_haematuria",
        required_followups=[EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT, EventType.FOLLOWUP_APPOINTMENT,
                            EventType.IMAGING_CT],
        followup_logic="any",
        deadline_days=90.0,
        severity=Severity.MODERATE,
        clinical_domain="diagnostic safety",
        ltl_formula="□(RBC ≥ 3/hpf twice in 12mo ∧ age ≥ 35 → ◇_{≤90d} (UROLOGY ∨ CT[kidney ∨ bladder]))",
        references=["Barocas DA et al. Microhematuria: AUA/SUFU Guideline. J Urol 2020;204:778-86"],
        evidence_note="Two positive tests reduce false alarms (menstruation, exercise). Closed by a urology referral or visit, or a CT covering the urinary tract.",
    ),
    ObligationRule(
        rule_id="R056",
        name="Lung Nodule Measured Larger Across Reports → Review and Work-up",
        description=("The same lung nodule (linked across reports by lobe and size) is ≥ 2 mm larger than its smallest "
                     "earlier measurement, and the latest report does not call it growing"),
        trigger_event=EventType.DIAGNOSTIC_PATTERN,
        trigger_condition="pattern_nodule_growth",
        required_followups=[EventType.IMAGING_PET, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT,
                            EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT],
        followup_logic="any",
        deadline_days=30.0,
        severity=Severity.HIGH,
        clinical_domain="diagnostic safety",
        ltl_formula="□(NODULE[same lesion, size − min(earlier) ≥ 2 mm] ∧ ¬report says growing → ◇_{≤30d} (PET ∨ BIOPSY ∨ REFERRAL))",
        references=["MacMahon H et al. Fleischner Society 2017. Radiology 2017;284:228-243",
                    "Callister MEJ et al. BTS guidelines for pulmonary nodules. Thorax 2015;70:ii1-ii54"],
        evidence_note=("Catches growth that is never written down: 'stable 8 mm' after 6 mm, or 6 → 7 → 8 mm over three "
                       "scans. The lesion match is probable, so the loop asks a radiologist to confirm it; a re-measurement "
                       "showing no growth closes it with evidence. Volume-doubling time < 400 days is flagged as suspicious."),
    ),
    ObligationRule(
        rule_id="R057",
        name="Critical Imaging-AI Finding on an Unreported Study → Read the Study Now",
        description=("An approved imaging-AI product flagged a critical finding (intracranial haemorrhage, pneumothorax, "
                     "free intraperitoneal air) on a study that has no radiology report yet; a radiologist must read it"),
        trigger_event=EventType.AI_FINDING,
        trigger_condition="ai_critical_unread",
        required_followups=[EventType.AI_FINDING_REVIEWED],
        deadline_days=1.0 / 24,
        severity=Severity.CRITICAL,
        clinical_domain="radiology",
        ltl_formula="□(AI_FINDING[critical ∧ study unreported] → ◇_{≤60min} RADIOLOGY_REPORT[same study])",
        references=["ACR Practice Parameter for Communication of Diagnostic Imaging Findings (2020)",
                    "FDA: Computer-assisted triage and notification software (CADt), 21 CFR 892.2080",
                    "MFDS 인공지능 의료기기 허가·심사 가이드라인"],
        evidence_note=("Worklist triage, the purpose of approved triage products: the AI result moves the study up, it never "
                       "diagnoses or reaches the patient. Closed by the first report of the same study (StudyInstanceUID, or "
                       "the first report after the study covering its body region); R047 then checks that the report "
                       "addressed the finding. Not raised when the study was already reported. 60 minutes is the default "
                       "(CLINLOOP_AI_CRITICAL_READ_MINUTES); research-use products count only when the hospital enables them."),
        patient_outreach=False,
    ),
    ObligationRule(
        rule_id="R058",
        name="Report Item No Rule Tracked (Second Reader) → Clinician Review",
        description=("The hospital's own language model, reading the report as a second reader, found an action the "
                     "report calls for (follow-up imaging, work-up, referral, a critical finding, abnormal pathology) that "
                     "no rule tracked; a clinician reads the report and acts or closes it as not needed"),
        trigger_event=EventType.SECOND_READER_FLAG,
        trigger_condition="second_reader_flag",
        required_followups=[EventType.IMAGING_ORDER, EventType.IMAGING_CT, EventType.IMAGING_MRI,
                            EventType.IMAGING_ULTRASOUND, EventType.IMAGING_XRAY, EventType.IMAGING_PET,
                            EventType.FOLLOWUP_CT, EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT, EventType.BREAST_BIOPSY,
                            EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT, EventType.ENDOSCOPIC_ULTRASOUND,
                            EventType.CRITICAL_VALUE_NOTIFICATION, EventType.PATIENT_NOTIFICATION],
        followup_logic="any",
        deadline_days=7.0,
        severity=Severity.HIGH,
        clinical_domain="diagnostic safety",
        ltl_formula="□(SECOND_READER_FLAG[quote verified ∧ no rule opened] → ◇_{≤7d} (matching follow-up ∨ clinician closes))",
        references=["Singh H et al. Types and origins of diagnostic errors in primary care. JAMA Intern Med 2013;173:418-25",
                    "Lacson R et al. Factors associated with radiologists' recommendations. JACR 2015"],
        evidence_note=("A safety net for the rules' long tail. Every flag quotes the report word for word (or is discarded), "
                       "only items no rule tracked are flagged, and each is marked for human review: the model never "
                       "opens or closes a clinical obligation itself. Closed by the follow-up of its kind (imaging, "
                       "work-up, referral, communication) or by a clinician. Critical findings 1 day, pathology 3 days, "
                       "otherwise 7 days to review. On-premise model only; off unless CLINLOOP_SECOND_READER=1."),
        patient_outreach=False,
    ),
    ObligationRule(
        rule_id="R059",
        name="Prolonged QTc ≥500 ms → Medication Review / Repeat ECG ≤24 h",
        description=("An ECG with a corrected QT interval of 500 ms or more: a clinician reviews QT-prolonging "
                     "medicines and electrolytes, and repeats the ECG, within 24 hours"),
        trigger_event=EventType.ECG,
        trigger_condition="prolonged_qtc",
        required_followups=[EventType.PROVIDER_REVIEW, EventType.ECG],
        followup_logic="any",
        deadline_days=1.0,
        severity=Severity.HIGH,
        clinical_domain="cardiology",
        ltl_formula="□(ECG[QTc ≥ 500 ms] → ◇_{≤1d} (PROVIDER_REVIEW ∨ ECG))",
        references=["Drew BJ et al. Prevention of torsade de pointes in hospital settings: AHA/ACCF scientific "
                    "statement. Circulation 2010;121:1047-60",
                    "Rautaharju PM et al. AHA/ACCF/HRS recommendations for the standardization and interpretation of "
                    "the ECG, part IV (ST segment, T and U waves, QT interval). Circulation 2009;119:e241-50"],
        evidence_note=("QTc ≥ 500 ms (or a rise of ≥ 60 ms) markedly raises the risk of torsade de pointes. The "
                       "repeat ECG or a documented review closes it; the review checks QT-prolonging drugs, potassium "
                       "and magnesium."),
        patient_outreach=False,
    ),
]


# ── Korean rule names (clinician-facing UI) ──────────────────────────────────

RULE_NAMES_KO: Dict[str, str] = {
    "R001": "이상 검사결과 → 환자 통보",
    "R002": "이상 검사결과 → 추적 외래",
    "R003": "우연 폐결절 → Fleischner 추적 CT",
    "R004": "PSA 상승 → 비뇨의학과 의뢰/조직검사",
    "R005": "자궁경부 세포검사 이상 → 질확대경 의뢰",
    "R006": "퇴원 후 배양 양성 → 환자 연락",
    "R007": "와파린 용량 변경 → INR 재검",
    "R008": "전문의 의뢰 → 의뢰 진료",
    "R009": "병리 이상 → 환자 통보 + 전문의 의뢰",
    "R010": "약물 변경 → 모니터링 검사",
    "R011": "정상 검사결과 → 주치의 확인",
    "R012": "갑상선기능 이상 → 재검",
    "R013": "당화혈색소 ≥9% → 3개월 내 재검",
    "R014": "급성심근경색 퇴원 → 14일 내 심장내과 외래",
    "R015": "균혈증 → 48시간 내 혈액배양 재검",
    "R016": "신규 심부전 → 심초음파",
    "R017": "분변잠혈(FIT) 양성 → 대장내시경",
    "R018": "유방촬영 BI-RADS 4/5 → 조직검사",
    "R019": "Lung-RADS 4A → 3개월 저선량 CT",
    "R020": "Lung-RADS 4B/4X → 정밀검사",
    "R021": "퇴원 후 이상 결과 → 의료진 확인",
    "R022": "위험(패닉) 수치 → 1시간 내 의료진 보고",
    "R023": "심부전 퇴원 → 7일 내 외래",
    "R024": "임신성 고혈압 질환 → 산후 혈압 측정",
    "R025": "임신성 당뇨 → 산후 4–12주 당부하검사",
    "R026": "C형간염 항체 양성 → HCV RNA 검사",
    "R027": "간암 고위험(만성 B형간염·간경변) → 감시 영상검사",
    "R028": "간암 감시 영상 → 6개월 후 재검",
    "R029": "자해·정신과 퇴원 → 7일 내 정신건강 추적",
    "R030": "영상의학과 권고 → 추적 CT",
    "R031": "영상의학과 권고 → 추적 MRI",
    "R032": "영상의학과 권고 → 추적 초음파",
    "R033": "영상의학과 권고 → 추적 X선 촬영",
    "R034": "Lung-RADS 3 → 6개월 저선량 CT",
    "R035": "영상 위급 소견 → 1시간 내 의료진 직접 보고",
    "R036": "영상의학과 권고 → 조직검사/세침흡인",
    "R037": "우연 부신 결절 → 부신 CT/MRI",
    "R038": "부신 종괴 ≥4cm(또는 암 환자) → 전문의 정밀검사",
    "R039": "의심 신장 종괴 → 비뇨의학과 의뢰",
    "R040": "불확정 신장 병변/Bosniak IIF → 신장 CT/MRI",
    "R041": "우연 췌장 낭종 → MRI/MRCP 추적",
    "R042": "우려 소견 동반 췌장 낭종 → 내시경초음파/전문의",
    "R043": "CT/MRI/PET 우연 갑상선 결절 → 갑상선 초음파",
    "R044": "복부대동맥류 → 추적 영상검사",
    "R045": "수술 기준 복부대동맥류 → 혈관외과 의뢰",
    "R046": "커지거나 의심되는 폐결절 → 정밀검사",
    "R047": "영상 AI 소견이 판독문에 없음 → 영상의학과 재검토",
    "R048": "진료기록 계획: 검사 재검",
    "R049": "진료기록 계획: 영상 검사",
    "R050": "진료기록 계획: 타과 의뢰",
    "R051": "진료기록 계획: 외래 재방문",
    "R052": "철결핍성 빈혈 → 위장관 검사",
    "R053": "크레아티닌 상승(급성 신손상 경고) → 재검",
    "R054": "심방세동 고위험 → 항응고 치료 결정",
    "R055": "지속 현미경적 혈뇨 → 비뇨의학과 평가",
    "R056": "보고서 간 폐결절 크기 증가 → 재검토 및 정밀검사",
    "R057": "판독 전 검사의 영상 AI 위급 소견 → 즉시 판독",
    "R058": "규칙이 놓친 판독문 조치 사항(2차 판독 모델) → 의료진 검토",
    "R059": "QTc 500ms 이상 연장 → 24시간 내 약물 검토·심전도 재검",
}
assert set(RULE_NAMES_KO) == {r.rule_id for r in OBLIGATION_RULES}, "every rule needs a Korean name"


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
    # Report-specific deadline decided from the patient's context (radiology.decide_obligations)
    per_rule = details.get("rule_deadline_days") if isinstance(details, dict) else None
    if isinstance(per_rule, dict) and rule.rule_id in per_rule:
        try:
            return float(per_rule[rule.rule_id])
        except (TypeError, ValueError):
            pass
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
    if rule.rule_id == "R024" and details.get("severe_hypertension") is True:
        return 3.0   # severe hypertension: BP check within 72 hours (ACOG CO 736)
    if rule.rule_id in LUNG_RADS_INTERVAL_RULES:
        return rule.deadline_days + radiology_grace_days(rule.deadline_days)
    if rule.rule_id in RADIOLOGIST_REC_RULES:
        try:
            interval = float(details["recommended_interval_days"])
            return interval + radiology_grace_days(interval)
        except (KeyError, TypeError, ValueError):
            pass
    return rule.deadline_days


RADIOLOGIST_REC_RULES = {"R030", "R031", "R032", "R033"}
# Scheduled screening intervals: a few days' slip is on time, not a missed follow-up
LUNG_RADS_INTERVAL_RULES = {"R019", "R034"}


def radiology_grace_days(interval_days: float) -> float:
    """Scheduling tolerance after a radiologist's stated interval: 25%, at least 7 and at most 30 days."""
    return min(30.0, max(7.0, 0.25 * interval_days))


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
    "stopped", "on-hold", "on_hold", "suspended", "superseded",
})


def is_fulfilling_status(status: Optional[str]) -> bool:
    """True if an event with this status counts as a completed follow-up."""
    return str(status or "completed").strip().lower() not in NON_FULFILLING_STATUSES


def format_window(days: float) -> str:
    """Human-readable deadline window: '1 hour', '3 days', '6 months'-style."""
    if days < 1.0:
        hours = round(days * 24)
        return f"{hours} hour{'s' if hours != 1 else ''}"
    whole = int(days) if float(days).is_integer() else round(days, 1)
    return f"{whole} day{'s' if whole != 1 else ''}"


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
