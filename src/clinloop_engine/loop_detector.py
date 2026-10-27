"""
loop_detector.py — ClinLoop AI Main Detection Pipeline

Combines the Temporal Hypergraph, Safety Clock, and Risk Scorer
into a single detection pipeline that processes patient trajectories
and outputs prioritized open loops with full evidence chains.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import os
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
    basis: List[str] = field(default_factory=list)   # plain-language reasons a clinician can check (basis.py)
    basis_ko: List[str] = field(default_factory=list)  # the same in Korean

    def to_dict(self):
        return asdict(self)


def _review_reason(reason: str, ko: bool = False) -> str:
    """Why a person must look, in clinical words (the score itself stays in the technical detail)."""
    if ko:
        from .basis import REVIEW_SPARSE_KO
        return REVIEW_SPARSE_KO if reason.startswith("Uncertainty") else f"의료진 검토 필요: {reason}"
    if reason.startswith("Uncertainty"):
        return ("Needs a person's review: the record ClinLoop can see holds too little to tell whether this "
                "follow-up happened. Check the chart.")
    return f"Needs a person's review: {reason}"


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

    def __init__(self, evaluation_time: Optional[datetime] = None, history_days: Optional[float] = None):
        """
        history_days: drop obligations whose deadline passed more than this many days before the
        evaluation time. A hospital's full record reaches back decades; a PSA from 1977 that was never
        followed up is history for a chart review, not today's worklist. None keeps everything.
        """
        self.history_days = history_days
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
        if (not isinstance(patient_id, str) or not patient_id.strip()
                or any(not isinstance(event, dict) or event.get("patient_id") != patient_id for event in events)):
            raise ValueError("Patient trajectory contains an unresolved or mixed patient identity")
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
        # Core profile: rules only device-like features can open are not evaluated (profile.py)
        from .profile import excluded_rules
        excluded = excluded_rules()

        for he in all_loops:
            if he.obligation_rule.rule_id in excluded:
                continue
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
            if assessment.should_abstain and he.status == LoopStatus.OPEN.value:
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
                missing_step = "Tracked obligation satisfied; overall care completion is not established"

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
                basis=list(he.basis) + ([_review_reason(assessment.abstain_reason)]
                                        if assessment.should_abstain and assessment.abstain_reason else []),
                basis_ko=list(he.basis_ko) + ([_review_reason(assessment.abstain_reason, ko=True)]
                                              if assessment.should_abstain and assessment.abstain_reason else []),
            )
            detections.append(detection)


        if self.history_days is not None:
            cutoff = evaluation_time - timedelta(days=self.history_days)
            detections = [d for d in detections
                          if datetime.fromisoformat(d.deadline or d.trigger_time) >= cutoff]

        # Unresolved loops first, highest risk first. An overdue critical loop
        # must outrank a low-risk one that merely needs human review; ties go
        # to the human-review case so low-confidence items stay visible. A loop
        # completed late ("delayed") needs no action now: it ranks after every
        # loop that is still open, however high its historical risk.
        detections.sort(key=lambda d: (
            d.loop_status == LoopStatus.CLOSED.value,
            d.loop_status == LoopStatus.DELAYED.value,
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


def hospital_detector(evaluation_time: Optional[datetime] = None) -> "ClinLoopDetector":
    """
    The detector for real hospital data: obligations whose deadline passed more than
    CLINLOOP_HISTORY_DAYS (default 365; 0 = keep all) before the evaluation time are left out.
    """
    days = float(os.environ.get("CLINLOOP_HISTORY_DAYS", "365") or 0)
    return ClinLoopDetector(evaluation_time=evaluation_time, history_days=days if days > 0 else None)


def lapse_after_death(detections: List["LoopDetection"], resources) -> List["LoopDetection"]:
    """
    Leave out obligations that were not yet done or due when the patient died (Patient.deceasedDateTime):
    they lapsed, they were not missed (anything recorded after the death cannot have fulfilled them). Obligations already overdue before the death are kept, since
    they were missed while the patient was alive.
    """
    from .fhir_ingest import _resources
    from .safety_clock import normalize_timestamp
    died = {r.get("id"): normalize_timestamp(r["deceasedDateTime"]) for r in _resources(resources)
            if r.get("resourceType") == "Patient" and r.get("deceasedDateTime")}
    if not died:
        return detections
    return [d for d in detections
            if not (d.patient_id in died and d.loop_status in ("open", "needs_human_review", "delayed")
                    and d.deadline and datetime.fromisoformat(d.deadline) > died[d.patient_id])]
