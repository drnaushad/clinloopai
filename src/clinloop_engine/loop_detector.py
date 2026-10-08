"""
loop_detector.py — ClinLoop AI Main Detection Pipeline

Combines the Temporal Hypergraph, Safety Clock, and Risk Scorer
into a single detection pipeline that processes patient trajectories
and outputs prioritized open loops with full evidence chains.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional
import json

from .clinical_ontology import Severity, LoopStatus, OBLIGATION_RULES, get_severity_score, format_window
from .temporal_hypergraph import DynamicTemporalHypergraph, TemporalHyperedge
from .safety_clock import SafetyClock
from .risk_scorer import RiskScorer, RiskAssessment, prioritize_risks
from .fhir_integration import fhir_create_task
import json


@dataclass
class LoopDetection:
    """A single detected loop with full context."""
    detection_id: str
    patient_id: str
    scenario_id: str
    loop_type: str              # e.g., "incidental_nodule_open"
    loop_status: str            # open | closed | delayed | needs_human_review
    risk_score: float
    severity: str
    rule_id: str
    rule_name: str
    trigger_event: str
    trigger_time: str
    missing_step: str
    deadline: str
    clock_state: str
    recommended_action: str
    explanation: List[str] = field(default_factory=list)
    evidence_chain: List[str] = field(default_factory=list)
    should_abstain: bool = False
    trigger_event_id: str = ""      # source event id: stable loop identity across runs

    def to_dict(self):
        return asdict(self)


class ClinLoopDetector:
    """
    The main ClinLoop AI detection engine.
    
    Pipeline:
    1. Build Dynamic Temporal Hypergraph from patient events
    2. Identify all obligation chains (hyperedges)
    3. Run Safety Clock on each open/delayed chain
    4. Compute multi-factor risk scores
    5. Apply abstention logic for ambiguous cases
    6. Return prioritized list of detected loops
    """

    def __init__(self, evaluation_time: Optional[datetime] = None):
        self.safety_clock = SafetyClock(steepness=8.0, threshold=1.0)
        self.risk_scorer = RiskScorer(
            abstention_threshold=0.7,
            safety_clock=self.safety_clock,
        )
        self.evaluation_time = evaluation_time
        self._detection_counter = 0

    def _next_detection_id(self) -> str:
        self._detection_counter += 1
        return f"DET-{self._detection_counter:04d}"

    def process_patient(
        self,
        scenario_id: str,
        patient_id: str,
        events: List[Dict],
        category: str = "",
    ) -> List[LoopDetection]:
        """
        Process a single patient's clinical trajectory.
        
        Args:
            scenario_id: Unique identifier for this scenario
            patient_id: Patient identifier
            events: List of event dicts from the trajectory
            category: Scenario category for reference
        
        Returns:
            List of LoopDetection objects, sorted by risk priority
        """
        # Step 1: Build the temporal hypergraph
        graph = DynamicTemporalHypergraph(evaluation_time=self.evaluation_time)
        graph.build_from_patient_trajectory(events)

        # Step 2: Get all obligation chains
        all_loops = graph.get_all_loops()
        # Score against the graph's resolved clock so status and risk agree
        evaluation_time = graph.evaluation_time

        if not all_loops:
            return []

        # Step 3: Score each loop
        detections = []
        risk_assessments = []

        for he in all_loops:
            severity = he.obligation_rule.severity
            is_open = he.status in (LoopStatus.OPEN.value, LoopStatus.DELAYED.value)

            # Compute risk
            assessment = self.risk_scorer.score(
                obligation_id=he.edge_id,
                rule_id=he.obligation_rule.rule_id,
                rule_name=he.obligation_rule.name,
                severity=severity,
                trigger_time=he.trigger_node.timestamp,
                deadline_days=he.deadline_days,
                event_details=he.trigger_node.details,
                n_events=len(events),
                is_open=is_open,
                evaluation_time=evaluation_time,
            )
            risk_assessments.append(assessment)

            # Determine final status
            if assessment.should_abstain:
                final_status = LoopStatus.ABSTAIN.value
            else:
                final_status = he.status

            # Build missing step description
            if is_open:
                fulfilled = {fn.event_type for fn in he.actual_followup_nodes}
                missing = ([] if he.satisfied_at is not None else
                           [ft for ft in he.expected_followup_types if ft not in fulfilled])
                if missing:
                    joiner = " or " if he.obligation_rule.followup_logic == "any" else ", "
                    missing_step = f"Missing: {joiner.join(missing)} within {format_window(he.deadline_days)}"
                else:
                    missing_step = f"Completed late: follow-up came after the {format_window(he.deadline_days)} deadline"
            else:
                missing_step = "All follow-ups completed"

            detection = LoopDetection(
                detection_id=self._next_detection_id(),
                patient_id=patient_id,
                scenario_id=scenario_id,
                loop_type=category,
                loop_status=final_status,
                risk_score=assessment.normalized_risk,
                severity=severity.value,
                rule_id=he.obligation_rule.rule_id,
                rule_name=he.obligation_rule.name,
                trigger_event=he.trigger_node.event_type,
                trigger_time=he.trigger_node.timestamp.isoformat(),
                missing_step=missing_step,
                deadline=he.deadline.isoformat() if he.deadline else "",
                clock_state=assessment.clock_state if is_open else "CLOSED",
                recommended_action=assessment.recommended_action,
                explanation=assessment.explanation,
                evidence_chain=list(he.evidence_chain),
                should_abstain=assessment.should_abstain,
                trigger_event_id=he.trigger_node.node_id,
            )
            detections.append(detection)


        # Unresolved loops first, highest risk first. An overdue critical loop
        # must outrank a low-risk one that merely needs human review; ties go
        # to the human-review case so low-confidence items stay visible.
        detections.sort(key=lambda d: (
            d.loop_status == LoopStatus.CLOSED.value,
            -d.risk_score,
            not d.should_abstain,
        ))

        # Build local previews only; this code has no EHR transport connection.
        for det in detections:
            if det.loop_status in (
                LoopStatus.OPEN.value,
                LoopStatus.DELAYED.value,
                LoopStatus.ABSTAIN.value,
            ):
                try:
                    action_desc = (
                        "Human review required: " + det.recommended_action
                        if det.should_abstain
                        else det.recommended_action
                    )
                    task_resource = fhir_create_task(
                        obligation_id=det.detection_id,
                        patient_id=det.patient_id,
                        action_desc=action_desc,
                        deadline_str=det.deadline
                    )
                    det.evidence_chain.append(
                        f"FHIR Task preview (not transmitted): {json.dumps(task_resource, ensure_ascii=False)}"
                    )
                except Exception as exc:
                    det.explanation.append(
                        f"FHIR Task preview generation failed ({type(exc).__name__}); no task was created."
                    )

        return detections


    def process_batch(
        self, scenarios: List[Dict]
    ) -> Dict[str, List[LoopDetection]]:
        """
        Process a batch of patient scenarios.
        
        Args:
            scenarios: List of scenario dicts (from data_generator)
        
        Returns:
            Dict mapping scenario_id -> list of detections
        """
        results = {}
        for scenario in scenarios:
            sid = scenario["scenario_id"]
            pid = scenario["patient_id"]
            events = scenario["events"]
            category = scenario.get("scenario_category", "")

            detections = self.process_patient(sid, pid, events, category)
            results[sid] = detections

        return results

    def get_predictions(self, scenarios: List[Dict]) -> List[Dict]:
        """
        Generate prediction labels for benchmarking.
        
        Returns list of dicts with scenario_id and predicted status.
        The prediction is the most severe detection for each scenario.
        """
        batch_results = self.process_batch(scenarios)
        predictions = []

        for scenario in scenarios:
            sid = scenario["scenario_id"]
            detections = batch_results.get(sid, [])

            if not detections:
                # No obligations detected — predict closed
                pred_status = LoopStatus.CLOSED.value
                pred_risk = 0.0
                pred_abstain = False
            else:
                # Use the highest-risk detection
                top = detections[0]
                pred_status = top.loop_status
                pred_risk = top.risk_score
                pred_abstain = top.should_abstain

            predictions.append({
                "scenario_id": sid,
                "predicted_status": pred_status,
                "predicted_risk": pred_risk,
                "predicted_abstain": pred_abstain,
                "n_detections": len(detections),
                "ground_truth_status": scenario["ground_truth_status"],
                "ground_truth_severity": scenario.get("ground_truth_severity", ""),
            })

        return predictions
