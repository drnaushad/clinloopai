"""
data_generator.py — Synthetic Clinical Scenario Generator

Generates 300 realistic patient trajectories with ground-truth labels
for benchmarking the ClinLoop AI detection engine.

Scenario categories:
  - CLOSED: All obligations correctly fulfilled
  - OPEN:   Missing required follow-up (the dangerous gap)
  - DELAYED: Follow-up exists but past the allowed deadline
"""

import json
import os
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

import numpy as np
import pandas as pd

from .clinical_ontology import (
    EventType, Severity, LoopStatus, OBLIGATION_RULES, ObligationRule
)

# Reproducibility
SEED = 42
random.seed(SEED)
np.random.seed(SEED)


@dataclass
class ClinicalEvent:
    """A single event in a patient's clinical timeline."""
    event_id: str
    patient_id: str
    event_type: str   # EventType.value
    timestamp: str    # ISO 8601
    details: Dict = field(default_factory=dict)
    status: str = "completed"

    def to_dict(self):
        return asdict(self)


@dataclass
class PatientScenario:
    """A complete patient trajectory with ground truth."""
    scenario_id: str
    patient_id: str
    patient_age: int
    patient_sex: str
    scenario_name: str
    scenario_category: str      # brief description
    applicable_rule_id: str
    events: List[ClinicalEvent] = field(default_factory=list)
    ground_truth_status: str = "closed"   # LoopStatus.value
    ground_truth_severity: str = "low"    # Severity.value
    ground_truth_risk_score: float = 0.0
    missing_followup: str = ""            # what's missing
    clinical_narrative: str = ""

    def to_dict(self):
        d = asdict(self)
        return d


# ── Scenario Templates ──────────────────────────────────────────────────────

def _ts(base: datetime, delta_days: float) -> str:
    """Generate ISO timestamp from base + delta."""
    return (base + timedelta(days=delta_days)).isoformat()


def _make_id(prefix: str, idx: int) -> str:
    return f"{prefix}-{idx:04d}"


class ScenarioFactory:
    """Generates diverse clinical scenarios."""

    def __init__(self):
        self.counter = 0
        self.base_date = datetime(2026, 1, 15, 9, 0, 0)

    def _next_id(self) -> int:
        self.counter += 1
        return self.counter

    def _random_base(self) -> datetime:
        """Random starting date within a 6-month window."""
        offset = random.randint(0, 180)
        return self.base_date + timedelta(days=offset)

    def _random_patient(self, idx: int) -> tuple:
        pid = _make_id("PT", idx)
        age = random.randint(25, 82)
        sex = random.choice(["M", "F"])
        return pid, age, sex

    # ── SCENARIO GENERATORS ─────────────────────────────────────────────

    def incidental_nodule_open(self) -> PatientScenario:
        """HIGH RISK: Incidental lung nodule found, NO follow-up CT scheduled."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        nodule_size = round(random.uniform(6.0, 15.0), 1)

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.IMAGING_ORDER.value, _ts(base, 0),
                {"modality": "CT_CHEST", "indication": random.choice(
                    ["chest_pain", "cough", "trauma", "preoperative"])},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.IMAGING_RESULT.value, _ts(base, 0.1),
                {"modality": "CT_CHEST", "status": "completed"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.RADIOLOGY_REPORT.value, _ts(base, 0.5),
                {"finding": "incidental_pulmonary_nodule",
                 "nodule_size_mm": nodule_size,
                 "recommendation": f"follow_up_CT_in_6_months",
                 "location": random.choice(["RLL", "RUL", "LLL", "LUL", "RML"])},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 4), pid,
                EventType.DISCHARGE.value, _ts(base, 1.0),
                {"primary_diagnosis": "ruled_out_acute_condition",
                 "discharge_instructions": "follow_up_with_PCP"},
            ),
            # NO follow-up CT event — this is the open loop
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Incidental Lung Nodule {nodule_size}mm — No Follow-up",
            scenario_category="incidental_nodule_open",
            applicable_rule_id="R003",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.85,
            missing_followup="FOLLOWUP_CT within 180 days",
            clinical_narrative=(
                f"Patient (age {age}{sex}) presented to ED with "
                f"{events[0].details['indication']}. CT chest showed incidental "
                f"{nodule_size}mm pulmonary nodule in {events[2].details['location']}. "
                f"Patient discharged after primary condition ruled out. "
                f"Radiologist recommended follow-up CT in 6 months. "
                f"No follow-up CT was ever scheduled or performed."
            ),
        )

    def incidental_nodule_closed(self) -> PatientScenario:
        """CLOSED: Incidental lung nodule with proper follow-up."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        nodule_size = round(random.uniform(6.0, 12.0), 1)
        followup_days = random.randint(120, 175)

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.IMAGING_ORDER.value, _ts(base, 0),
                {"modality": "CT_CHEST", "indication": "chest_pain"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.RADIOLOGY_REPORT.value, _ts(base, 0.5),
                {"finding": "incidental_pulmonary_nodule",
                 "nodule_size_mm": nodule_size,
                 "recommendation": "follow_up_CT_in_6_months",
                 "location": "RLL"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.PATIENT_NOTIFICATION.value, _ts(base, 2),
                {"method": "phone_call", "content": "incidental_finding_explained"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 4), pid,
                EventType.FOLLOWUP_CT.value, _ts(base, followup_days),
                {"modality": "CT_CHEST", "result": "stable_nodule",
                 "comparison": "prior_CT"},
            ),
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Incidental Lung Nodule {nodule_size}mm — Properly Followed",
            scenario_category="incidental_nodule_closed",
            applicable_rule_id="R003",
            events=events,
            ground_truth_status=LoopStatus.CLOSED.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.0,
            missing_followup="",
            clinical_narrative=(
                f"Patient properly notified and follow-up CT performed at day {followup_days}."
            ),
        )

    def elevated_psa_open(self) -> PatientScenario:
        """HIGH RISK: Elevated PSA, no biopsy or urology referral."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        sex = "M"
        age = random.randint(50, 75)
        base = self._random_base()
        psa_value = round(random.uniform(4.5, 15.0), 1)

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.LAB_ORDER.value, _ts(base, 0),
                {"test": "PSA", "ordering_provider": "PCP"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.LAB_RESULT.value, _ts(base, 1),
                {"test": "PSA", "value": psa_value, "unit": "ng/mL",
                 "reference_range": "0-4.0", "flag": "HIGH",
                 "condition": "elevated_psa"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.PROVIDER_REVIEW.value, _ts(base, 2),
                {"action": "result_viewed_in_inbox"},
            ),
            # Provider saw it in inbox but NO referral, NO biopsy
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Elevated PSA {psa_value} ng/mL — No Urology Referral",
            scenario_category="elevated_psa_open",
            applicable_rule_id="R004",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.82,
            missing_followup="SPECIALIST_REFERRAL or BIOPSY_ORDER within 30 days",
            clinical_narrative=(
                f"Male patient age {age} with PSA {psa_value} ng/mL (elevated). "
                f"Provider viewed the result but no urology referral or biopsy was ordered."
            ),
        )

    def elevated_psa_closed(self) -> PatientScenario:
        """CLOSED: Elevated PSA with appropriate urology referral."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        sex = "M"
        age = random.randint(50, 75)
        base = self._random_base()
        psa_value = round(random.uniform(4.5, 10.0), 1)

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.LAB_RESULT.value, _ts(base, 1),
                {"test": "PSA", "value": psa_value, "flag": "HIGH",
                 "condition": "elevated_psa"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.PATIENT_NOTIFICATION.value, _ts(base, 2),
                {"method": "phone_call"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.SPECIALIST_REFERRAL.value, _ts(base, 3),
                {"specialty": "urology", "reason": "elevated_PSA"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 4), pid,
                EventType.REFERRAL_VISIT.value, _ts(base, 18),
                {"specialty": "urology", "outcome": "biopsy_discussed"},
            ),
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Elevated PSA {psa_value} — Properly Referred",
            scenario_category="elevated_psa_closed",
            applicable_rule_id="R004",
            events=events,
            ground_truth_status=LoopStatus.CLOSED.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.0,
            missing_followup="",
            clinical_narrative=f"Elevated PSA properly managed with urology referral and visit.",
        )

    def abnormal_pap_open(self) -> PatientScenario:
        """HIGH RISK: Abnormal cervical cytology, no colposcopy."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        sex = "F"
        age = random.randint(25, 55)
        base = self._random_base()

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.LAB_RESULT.value, _ts(base, 3),
                {"test": "cervical_cytology", "result": "HSIL",
                 "flag": "ABNORMAL", "condition": "abnormal_cervical_cytology"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.PATIENT_NOTIFICATION.value, _ts(base, 5),
                {"method": "letter", "content": "abnormal_pap_result"},
            ),
            # No colposcopy referral
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name="Abnormal Pap (HSIL) — No Colposcopy",
            scenario_category="abnormal_pap_open",
            applicable_rule_id="R005",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.80,
            missing_followup="COLPOSCOPY_REFERRAL within 30 days",
            clinical_narrative=(
                f"Female age {age} with HSIL on cervical cytology. "
                f"Patient notified by letter but no colposcopy referral placed."
            ),
        )

    def post_discharge_culture_open(self) -> PatientScenario:
        """CRITICAL: Positive blood culture after discharge, no callback."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        organism = random.choice(["S. aureus", "E. coli", "K. pneumoniae", "P. aeruginosa"])

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.DISCHARGE.value, _ts(base, 0),
                {"primary_diagnosis": "fever_of_unknown_origin",
                 "status": "discharged_stable"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.CULTURE_RESULT.value, _ts(base, 1.5),
                {"specimen": "blood", "result": "positive",
                 "organism": organism, "condition": "positive_post_discharge",
                 "sensitivity": "pending"},
            ),
            # No callback!
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Post-discharge Positive Blood Culture ({organism}) — No Callback",
            scenario_category="post_discharge_culture_critical",
            applicable_rule_id="R006",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.CRITICAL.value,
            ground_truth_risk_score=0.98,
            missing_followup="CALLBACK within 24 hours",
            clinical_narrative=(
                f"Patient discharged with fever workup. Blood culture returned positive "
                f"for {organism} 1.5 days post-discharge. No callback was made."
            ),
        )

    def post_discharge_culture_closed(self) -> PatientScenario:
        """CLOSED: Positive culture with timely callback."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.DISCHARGE.value, _ts(base, 0),
                {"primary_diagnosis": "UTI"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.CULTURE_RESULT.value, _ts(base, 1.5),
                {"specimen": "blood", "result": "positive",
                 "organism": "E. coli", "condition": "positive_post_discharge"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.CALLBACK.value, _ts(base, 1.8),
                {"method": "phone", "outcome": "patient_recalled_to_ED"},
            ),
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name="Post-discharge Culture — Proper Callback",
            scenario_category="post_discharge_culture_closed",
            applicable_rule_id="R006",
            events=events,
            ground_truth_status=LoopStatus.CLOSED.value,
            ground_truth_severity=Severity.CRITICAL.value,
            ground_truth_risk_score=0.0,
            missing_followup="",
            clinical_narrative="Positive culture detected and patient called back within 7 hours.",
        )

    def warfarin_change_open(self) -> PatientScenario:
        """HIGH: Warfarin dose changed, no INR recheck."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.MEDICATION_CHANGE.value, _ts(base, 0),
                {"drug": "warfarin", "old_dose": "5mg", "new_dose": "7.5mg",
                 "reason": "subtherapeutic_INR",
                 "condition": "anticoagulant_dose_change"},
            ),
            # No INR recheck
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name="Warfarin Dose ↑ — No INR Recheck",
            scenario_category="warfarin_no_inr",
            applicable_rule_id="R007",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.78,
            missing_followup="INR_RECHECK within 7 days",
            clinical_narrative=(
                f"Patient's warfarin dose increased from 5mg to 7.5mg "
                f"but no INR recheck was ordered within 7 days."
            ),
        )

    def specialist_referral_delayed(self) -> PatientScenario:
        """DELAYED: Referral visit happened but way past deadline."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        delay_days = random.randint(45, 90)

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.SPECIALIST_REFERRAL.value, _ts(base, 0),
                {"specialty": random.choice(["cardiology", "gastroenterology",
                                              "neurology", "endocrinology"]),
                 "reason": "further_evaluation", "condition": "any"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.REFERRAL_VISIT.value, _ts(base, delay_days),
                {"status": "completed_late"},
            ),
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Specialist Referral — Delayed Visit ({delay_days} days)",
            scenario_category="referral_delayed",
            applicable_rule_id="R008",
            events=events,
            ground_truth_status=LoopStatus.DELAYED.value,
            ground_truth_severity=Severity.MODERATE.value,
            ground_truth_risk_score=0.45,
            missing_followup=f"REFERRAL_VISIT was {delay_days - 30} days late",
            clinical_narrative=(
                f"Specialist referral placed but patient visited {delay_days} days later "
                f"(deadline: 30 days). {delay_days - 30} days overdue."
            ),
        )

    def normal_lab_closed(self) -> PatientScenario:
        """CLOSED: Normal lab properly reviewed — negative example."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        test = random.choice(["CBC", "BMP", "LFT", "lipid_panel", "HbA1c"])

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.LAB_ORDER.value, _ts(base, 0),
                {"test": test},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.LAB_RESULT.value, _ts(base, 1),
                {"test": test, "flag": "NORMAL", "condition": "normal"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.PROVIDER_REVIEW.value, _ts(base, 2),
                {"action": "reviewed_and_filed"},
            ),
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Normal {test} — Properly Reviewed",
            scenario_category="normal_lab_closed",
            applicable_rule_id="R011",
            events=events,
            ground_truth_status=LoopStatus.CLOSED.value,
            ground_truth_severity=Severity.LOW.value,
            ground_truth_risk_score=0.0,
            missing_followup="",
            clinical_narrative=f"Normal {test} result reviewed by provider within 2 days.",
        )

    def abnormal_thyroid_closed(self) -> PatientScenario:
        """CLOSED: Abnormal thyroid function with proper follow-up."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.LAB_RESULT.value, _ts(base, 1),
                {"test": "TSH", "value": 8.5, "flag": "HIGH",
                 "condition": "abnormal_thyroid"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 2), pid,
                EventType.PATIENT_NOTIFICATION.value, _ts(base, 3),
                {"method": "phone_call"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 3), pid,
                EventType.MEDICATION_CHANGE.value, _ts(base, 5),
                {"drug": "levothyroxine", "dose": "50mcg", "condition": "requires_monitoring"},
            ),
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 4), pid,
                EventType.FOLLOWUP_LAB.value, _ts(base, 48),
                {"test": "TSH", "value": 3.2, "flag": "NORMAL"},
            ),
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name="Abnormal TSH — Properly Managed",
            scenario_category="abnormal_thyroid_closed",
            applicable_rule_id="R012",
            events=events,
            ground_truth_status=LoopStatus.CLOSED.value,
            ground_truth_severity=Severity.MODERATE.value,
            ground_truth_risk_score=0.0,
            missing_followup="",
            clinical_narrative="Elevated TSH treated with levothyroxine; follow-up labs normal at 48 days.",
        )

    def abnormal_pathology_open(self) -> PatientScenario:
        """HIGH: Abnormal pathology, no notification or referral."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.PATHOLOGY_RESULT.value, _ts(base, 5),
                {"specimen": "colon_biopsy", "result": "adenocarcinoma",
                 "grade": "moderately_differentiated",
                 "condition": "abnormal"},
            ),
            # No notification, no referral
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name="Colon Adenocarcinoma on Biopsy — No Follow-up",
            scenario_category="abnormal_pathology_open",
            applicable_rule_id="R009",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.92,
            missing_followup="PATIENT_NOTIFICATION within 5 days + SPECIALIST_REFERRAL within 14 days",
            clinical_narrative=(
                f"Colon biopsy returned adenocarcinoma. Patient was not notified "
                f"and no oncology referral was placed."
            ),
        )

    def abnormal_lab_open(self) -> PatientScenario:
        """HIGH: Abnormal lab, no notification or follow-up appointment."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        test = random.choice(["potassium", "creatinine", "glucose", "hemoglobin"])
        values_map = {
            "potassium": (6.2, "mEq/L", "3.5-5.0"),
            "creatinine": (2.8, "mg/dL", "0.7-1.3"),
            "glucose": (320, "mg/dL", "70-100"),
            "hemoglobin": (6.5, "g/dL", "12.0-16.0"),
        }
        val, unit, ref = values_map[test]

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.LAB_RESULT.value, _ts(base, 1),
                {"test": test, "value": val, "unit": unit,
                 "reference_range": ref, "flag": "CRITICAL",
                 "condition": "abnormal"},
            ),
            # No notification, no follow-up
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"Critical {test} ({val} {unit}) — No Follow-up",
            scenario_category="abnormal_lab_open",
            applicable_rule_id="R001",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.HIGH.value,
            ground_truth_risk_score=0.88,
            missing_followup="PATIENT_NOTIFICATION within 3 days",
            clinical_narrative=(
                f"Critical {test} value of {val} {unit} (ref: {ref}). "
                f"No patient notification or follow-up appointment."
            ),
        )

    def medication_change_open(self) -> PatientScenario:
        """MODERATE: Med change requiring monitoring, no follow-up labs."""
        idx = self._next_id()
        pid, age, sex = self._random_patient(idx)
        base = self._random_base()
        drug = random.choice(["metformin", "lisinopril", "methotrexate", "lithium"])

        events = [
            ClinicalEvent(
                _make_id("EVT", idx * 10 + 1), pid,
                EventType.MEDICATION_CHANGE.value, _ts(base, 0),
                {"drug": drug, "action": "dose_increased",
                 "condition": "requires_monitoring"},
            ),
            # No follow-up labs
        ]

        return PatientScenario(
            scenario_id=_make_id("SC", idx), patient_id=pid,
            patient_age=age, patient_sex=sex,
            scenario_name=f"{drug.capitalize()} Dose Change — No Follow-up Labs",
            scenario_category="medication_change_open",
            applicable_rule_id="R010",
            events=events,
            ground_truth_status=LoopStatus.OPEN.value,
            ground_truth_severity=Severity.MODERATE.value,
            ground_truth_risk_score=0.55,
            missing_followup="FOLLOWUP_LAB within 14 days",
            clinical_narrative=f"{drug.capitalize()} dose increased but no monitoring labs ordered.",
        )


def generate_all_scenarios(n_total: int = 300) -> List[PatientScenario]:
    """
    Generate a balanced dataset of clinical scenarios.
    
    Distribution (designed for realistic clinical prevalence):
      - ~35% CLOSED (properly managed)
      - ~45% OPEN  (missing follow-up — the dangerous gaps)
      - ~20% DELAYED (late follow-up)
    """
    factory = ScenarioFactory()
    scenarios = []

    # Define how many of each type
    # OPEN scenarios (dangerous — what ClinLoop must catch)
    generators_open = [
        (factory.incidental_nodule_open, 30),
        (factory.elevated_psa_open, 20),
        (factory.abnormal_pap_open, 15),
        (factory.post_discharge_culture_open, 20),
        (factory.warfarin_change_open, 15),
        (factory.abnormal_pathology_open, 15),
        (factory.abnormal_lab_open, 20),
        (factory.medication_change_open, 10),
    ]

    # CLOSED scenarios (negative examples — must not false-alert)
    generators_closed = [
        (factory.incidental_nodule_closed, 20),
        (factory.elevated_psa_closed, 15),
        (factory.post_discharge_culture_closed, 15),
        (factory.normal_lab_closed, 30),
        (factory.abnormal_thyroid_closed, 15),
    ]

    # DELAYED scenarios
    generators_delayed = [
        (factory.specialist_referral_delayed, 60),
    ]

    for gen_func, count in generators_open + generators_closed + generators_delayed:
        for _ in range(count):
            scenarios.append(gen_func())

    # Shuffle for realistic distribution
    random.shuffle(scenarios)

    # Trim to target count
    scenarios = scenarios[:n_total]

    return scenarios


def save_scenarios(scenarios: List[PatientScenario], output_dir: str):
    """Save generated scenarios to JSON and CSV."""
    os.makedirs(output_dir, exist_ok=True)

    # Full JSON
    json_path = os.path.join(output_dir, "clinical_scenarios.json")
    data = [s.to_dict() for s in scenarios]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    # Summary CSV
    csv_path = os.path.join(output_dir, "scenarios_summary.csv")
    rows = []
    for s in scenarios:
        rows.append({
            "scenario_id": s.scenario_id,
            "patient_id": s.patient_id,
            "age": s.patient_age,
            "sex": s.patient_sex,
            "category": s.scenario_category,
            "rule_id": s.applicable_rule_id,
            "ground_truth_status": s.ground_truth_status,
            "severity": s.ground_truth_severity,
            "risk_score": s.ground_truth_risk_score,
            "missing_followup": s.missing_followup,
            "n_events": len(s.events),
        })
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False, encoding="utf-8")

    print(f"  ✓ Saved {len(scenarios)} scenarios to {json_path}")
    print(f"  ✓ Saved summary to {csv_path}")

    # Print distribution
    status_counts = df["ground_truth_status"].value_counts()
    severity_counts = df["severity"].value_counts()
    print(f"\n  Status distribution:")
    for status, count in status_counts.items():
        print(f"    {status:20s}: {count:3d} ({100*count/len(df):.1f}%)")
    print(f"\n  Severity distribution:")
    for sev, count in severity_counts.items():
        print(f"    {sev:20s}: {count:3d}")

    return json_path, csv_path
