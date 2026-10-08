"""
model.py — High-Level ClinLoop AI Model Interface

Provides an intuitive, production-ready interface for inference, loop detection,
risk scoring, and explainable evidence chain generation.
"""

from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from src.clinloop_engine.loop_detector import ClinLoopDetector, LoopDetection
from src.clinloop_engine.clinical_ontology import Severity, LoopStatus
from src.clinloop_engine.data_generator import PatientScenario, ClinicalEvent


class ClinLoopModel:
    """High-level model wrapper for the ClinLoop Neuro-Symbolic Safety Engine."""

    def __init__(self, evaluation_time: Optional[datetime] = None):
        self.detector = ClinLoopDetector(evaluation_time=evaluation_time)

    def detect_loops(
        self,
        patient_id: str,
        events: List[Union[ClinicalEvent, Dict[str, Any]]],
        scenario_id: str = "custom_scenario",
        category: str = ""
    ) -> List[LoopDetection]:
        """Runs open-loop detection on a single patient timeline."""
        dict_events = []
        for e in events:
            if hasattr(e, "to_dict"):
                dict_events.append(e.to_dict())
            elif isinstance(e, dict):
                dict_events.append(e)
            else:
                dict_events.append(vars(e))

        return self.detector.process_patient(
            scenario_id=scenario_id,
            patient_id=patient_id,
            events=dict_events,
            category=category
        )

    def predict_scenarios(
        self,
        scenarios: List[Union[PatientScenario, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Runs batch inference on a list of clinical scenarios."""
        dict_scenarios = []
        for s in scenarios:
            if hasattr(s, "to_dict"):
                dict_scenarios.append(s.to_dict())
            elif isinstance(s, dict):
                dict_scenarios.append(s)
            else:
                dict_scenarios.append(vars(s))
        return self.detector.get_predictions(dict_scenarios)

    def explain(self, detection: LoopDetection) -> str:
        """Formats a human-readable clinical explanation for a detected loop."""
        lines = [
            f"=== ClinLoop Alert: [{detection.severity.upper()}] {detection.rule_name} ===",
            f"Patient ID: {detection.patient_id}",
            f"Status: {detection.loop_status.upper()}",
            f"Risk Score: {detection.risk_score:.2f}",
            f"Trigger Event: {detection.trigger_event} at {detection.trigger_time}",
            f"Missing Obligation: {detection.missing_step}",
            f"Safety Deadline: {detection.deadline} ({detection.clock_state})",
            f"Recommended Action: {detection.recommended_action}",
            "\nClinical Rationale:"
        ]
        for exp in detection.explanation:
            lines.append(f"  • {exp}")
        if detection.evidence_chain:
            lines.append("\nAudit Evidence Chain:")
            for ev in detection.evidence_chain:
                lines.append(f"  → {ev}")
        return "\n".join(lines)


def get_model(evaluation_time: Optional[datetime] = None) -> ClinLoopModel:
    """Factory helper to obtain an initialized ClinLoopModel."""
    return ClinLoopModel(evaluation_time=evaluation_time)
