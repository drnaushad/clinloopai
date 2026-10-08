"""
temporal_hypergraph.py — Dynamic Temporal Hypergraph (DTH) Engine

The core innovation of ClinLoop AI: models clinical events as a
temporal hypergraph where hyperedges connect multiple heterogeneous
clinical entities that together form a clinical obligation chain.

Unlike simple directed graphs, hyperedges capture the reality that
a single clinical obligation (e.g., "incidental nodule follow-up")
simultaneously involves:
  - The imaging event
  - The finding details
  - Patient demographics/risk factors
  - The guideline-mandated follow-up
  - The time constraint
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import networkx as nx
import numpy as np

from .clinical_ontology import (
    EventType, Severity, LoopStatus, ObligationRule,
    OBLIGATION_RULES, get_rules_for_event, get_severity_score,
    get_deadline_days, is_fulfilling_status, format_window,
)
from .safety_clock import normalize_timestamp, utc_now


# Imaging events whose body region is checked against what the obligation asks for
REGION_CHECKED_TYPES = {
    EventType.IMAGING_CT.value, EventType.IMAGING_MRI.value, EventType.IMAGING_ULTRASOUND.value,
    EventType.IMAGING_XRAY.value, EventType.IMAGING_PET.value,
}


def _required_regions(trigger: "ClinicalNode", rule: ObligationRule) -> List[str]:
    regions = trigger.details.get("followup_regions")
    if isinstance(regions, dict):
        return list(regions.get(rule.rule_id) or [])
    return []


def _details_match(trigger: "ClinicalNode", rule: ObligationRule, node: "ClinicalNode") -> bool:
    """A trigger may require its follow-up to carry matching details (e.g. the same AI finding)."""
    spec = trigger.details.get("followup_match")
    want = spec.get(rule.rule_id) if isinstance(spec, dict) else None
    if not want:
        return True
    only_for = want.get("_only_for")          # the match applies to these follow-up types only
    if only_for and node.event_type not in only_for:
        return True
    return all(node.details.get(k) == v for k, v in want.items() if k != "_only_for")


def _type_ok(trigger: "ClinicalNode", rule: ObligationRule, node: "ClinicalNode") -> bool:
    """A trigger may narrow which of the rule's follow-up types count (a note's 'CT' plan: CT studies only)."""
    spec = trigger.details.get("followup_types")
    allowed = spec.get(rule.rule_id) if isinstance(spec, dict) else None
    return not allowed or node.event_type in allowed


def _region_ok(required: List[str], node: "ClinicalNode") -> bool:
    """A study of unknown region does not close a region-specific loop (a clinician can close it with evidence)."""
    covered = node.details.get("body_regions") or []
    return bool(set(required) & set(covered))


@dataclass
class ClinicalNode:
    """A node in the temporal hypergraph representing a clinical event."""
    node_id: str
    patient_id: str
    event_type: str         # EventType.value
    timestamp: datetime
    details: Dict = field(default_factory=dict)
    status: str = "completed"

    @property
    def event_enum(self) -> Optional[EventType]:
        try:
            return EventType(self.event_type)
        except ValueError:
            return None


@dataclass
class TemporalHyperedge:
    """
    A hyperedge connecting multiple clinical nodes that form
    an obligation chain. Unlike a simple edge, this connects
    a trigger event to ALL its required follow-up events,
    along with contextual nodes (demographics, risk factors).
    
    This is the key structural innovation over simple graphs.
    """
    edge_id: str
    obligation_rule: ObligationRule
    trigger_node: ClinicalNode
    expected_followup_types: List[str]     # EventType values
    actual_followup_nodes: List[ClinicalNode] = field(default_factory=list)
    deadline: Optional[datetime] = None
    deadline_days: float = 0.0
    status: str = "open"                   # open | closed | delayed | abstain
    risk_score: float = 0.0
    evidence_chain: List[str] = field(default_factory=list)
    evaluation_time: Optional[datetime] = None

    @property
    def _now(self) -> datetime:
        return self.evaluation_time or utc_now()

    @property
    def satisfied_at(self) -> Optional[datetime]:
        """
        When the obligation was fulfilled, or None if it is still unmet.

        Honors the rule's followup_logic: with "all" (the default) every
        required follow-up type must occur and the loop closes at the latest
        of them; with "any" the earliest qualifying follow-up closes it.
        """
        first_by_type: Dict[str, datetime] = {}
        for n in self.actual_followup_nodes:
            if n.event_type not in first_by_type or n.timestamp < first_by_type[n.event_type]:
                first_by_type[n.event_type] = n.timestamp
        times = [first_by_type[ft] for ft in self.expected_followup_types if ft in first_by_type]
        if self.obligation_rule.followup_logic == "any":
            return min(times) if times else None
        if len(times) < len(self.expected_followup_types):
            return None
        return max(times)

    @property
    def is_complete(self) -> bool:
        """Check if the required follow-ups have been fulfilled (per followup_logic)."""
        return self.satisfied_at is not None

    @property
    def is_overdue(self) -> bool:
        """Check if the deadline has passed at the evaluation time."""
        if self.deadline is None:
            return False
        return self._now > self.deadline

    @property
    def days_elapsed(self) -> float:
        """Days since the trigger event."""
        return (self._now - self.trigger_node.timestamp).total_seconds() / 86400

    @property
    def days_until_deadline(self) -> float:
        """Days remaining until deadline (negative if overdue)."""
        if self.deadline is None:
            return float('inf')
        return (self.deadline - self._now).total_seconds() / 86400


class DynamicTemporalHypergraph:
    """
    The main hypergraph engine that:
    1. Ingests patient clinical events
    2. Constructs temporal hyperedges based on obligation rules
    3. Identifies open (unclosed) loops
    4. Computes temporal gaps and risk factors
    """

    def __init__(self, evaluation_time: Optional[datetime] = None):
        self.nodes: Dict[str, ClinicalNode] = {}
        self.hyperedges: Dict[str, TemporalHyperedge] = {}
        self.graph = nx.DiGraph()  # Internal graph for visualization/traversal
        self.evaluation_time = normalize_timestamp(evaluation_time) if evaluation_time else utc_now()
        self._edge_counter = 0

    def _next_edge_id(self) -> str:
        self._edge_counter += 1
        return f"HE-{self._edge_counter:04d}"

    def _parse_timestamp(self, ts) -> datetime:
        """Parse a timestamp onto the engine's naive-UTC time base."""
        return normalize_timestamp(ts)

    def build_from_patient_trajectory(self, events: List[Dict]) -> None:
        """
        Construct the hypergraph from a list of clinical events.
        
        Each event dict has: event_id, patient_id, event_type, timestamp, details
        """
        # Step 1: Create nodes
        nodes_list = []
        for evt in events:
            node = ClinicalNode(
                node_id=evt["event_id"],
                patient_id=evt["patient_id"],
                event_type=evt["event_type"],
                timestamp=self._parse_timestamp(evt["timestamp"]),
                details=evt.get("details", {}),
                status=evt.get("status", "completed"),
            )
            self.nodes[node.node_id] = node
            nodes_list.append(node)
            self.graph.add_node(node.node_id, **{
                "event_type": node.event_type,
                "timestamp": str(node.timestamp),
            })

        # Step 2: Sort by timestamp
        nodes_list.sort(key=lambda n: n.timestamp)

        # Step 3: Build temporal edges between consecutive events
        for i in range(len(nodes_list) - 1):
            self.graph.add_edge(
                nodes_list[i].node_id,
                nodes_list[i + 1].node_id,
                weight=(nodes_list[i + 1].timestamp - nodes_list[i].timestamp).total_seconds() / 86400,
            )

        # Step 4: Identify obligation chains (hyperedges)
        self._build_obligation_hyperedges(nodes_list)

    def _infer_condition(self, node: "ClinicalNode") -> str:
        """
        Infer the clinical trigger condition from event details.

        Handles multiple data schemas:
        - Explicit ``condition`` key (most scenarios)
        - Radiology reports with ``finding`` + ``nodule_size_mm``
        - Discharge events with ``primary_diagnosis``
        - Culture results with organism / bacteremia fields
        - Standard ABNORMAL/NORMAL flags
        """
        details = node.details

        # 1. Explicit condition field always wins
        if details.get("condition"):
            return details["condition"]

        # 2. Radiology-report nodule logic (R003)
        finding = details.get("finding", "")
        nodule_size = details.get("nodule_size_mm")
        if finding in ("incidental_pulmonary_nodule", "pulmonary_nodule"):
            try:
                if nodule_size is not None and float(nodule_size) >= 6.0:
                    return "incidental_nodule_ge_6mm"
                elif nodule_size is not None:
                    return "incidental_nodule_lt_6mm"
            except (TypeError, ValueError):
                pass

        # 3. Discharge diagnosis conditions (R014, R016)
        # Match whole tokens: a substring test for "mi" would also fire on
        # "anemia", "hypokalemia" or "septicemia".
        primary_dx = str(details.get("primary_diagnosis", "")).lower()
        dx_tokens = set(re.split(r"[^a-z0-9]+", primary_dx))
        if dx_tokens & {"mi", "stemi", "nstemi", "ami"} or "myocardial_infarction" in primary_dx:
            return "post_mi_discharge"
        if "heart_failure" in primary_dx or "hf_new" in dx_tokens:
            return "new_heart_failure"

        # 4. Culture results — bacteremia (R015)
        organism = details.get("organism", "")
        result = details.get("result", "")
        if organism or (result and result.lower() in ("positive", "growth")):
            # R006 positive_post_discharge is already covered by explicit condition;
            # handle bacteremia confirmed cases
            if details.get("bacteremia") or details.get("culture_type") == "blood":
                return "bacteremia_confirmed"

        # 5. Standard flag fallback
        flag = details.get("flag", "")
        if flag in ("ABNORMAL", "HIGH", "LOW", "CRITICAL", "PANIC"):
            return "abnormal"
        if flag == "NORMAL":
            return "normal"

        return ""

    def _infer_conditions(self, node: "ClinicalNode") -> List[str]:
        """
        All trigger conditions an event satisfies.

        One result can carry several obligations at once: a panic potassium
        is both "abnormal" (notify, follow up) and "critical_value" (call a
        clinician within the hour). Additional conditions come from
        structured fields, so FHIR ingestion can set them reliably.
        """
        details = node.details
        conditions = [self._infer_condition(node)]
        flag = str(details.get("flag", "")).upper()
        is_abnormal = conditions[0] not in ("", "normal") or flag in (
            "ABNORMAL", "HIGH", "LOW", "CRITICAL", "PANIC")

        if flag in ("CRITICAL", "PANIC") or details.get("critical") is True:
            conditions.append("critical_value")
        if details.get("resulted_after_discharge") is True and is_abnormal:
            conditions.append("abnormal_post_discharge")

        test = str(details.get("test", "")).strip().lower()
        result = str(details.get("result", "")).strip().lower()
        if test in ("fit", "fecal_immunochemical_test", "fobt") and result in ("positive", "detected"):
            conditions.append("positive_fit")

        birads = str(details.get("birads", "")).strip().upper()
        if birads[:1] in ("4", "5"):
            conditions.append("birads_4_5")

        lung_rads = str(details.get("lung_rads", "")).strip().upper()
        if lung_rads == "3":
            conditions.append("lung_rads_3")
        elif lung_rads == "4A":
            conditions.append("lung_rads_4a")
        elif lung_rads in ("4B", "4X"):
            conditions.append("lung_rads_4b_4x")

        modality = str(details.get("recommended_modality", "")).lower()
        if modality in ("ct", "mri", "ultrasound", "xray") and details.get("recommended_interval_days"):
            conditions.append(f"radiologist_rec_{modality}")
        if details.get("biopsy_recommended") is True:
            conditions.append("radiologist_rec_biopsy")
        if details.get("critical_imaging") is True:
            conditions.append("critical_imaging_finding")
        # Conditions decided upstream with the patient's context (radiology.decide_obligations)
        extra = details.get("extra_conditions")
        if isinstance(extra, (list, tuple)):
            conditions.extend(str(c) for c in extra)

        if details.get("hcc_risk") is True:
            conditions.append("hcc_risk")
        if details.get("hcc_surveillance") is True:
            conditions.append("hcc_surveillance")

        # Discharge diagnoses (whole-token matching, as for MI above)
        dx = str(details.get("primary_diagnosis", "")).lower()
        if dx:
            tokens = set(re.split(r"[^a-z0-9]+", dx))
            if "heart_failure" in dx or tokens & {"chf", "hfref", "hfpef"}:
                conditions.append("heart_failure_discharge")
            if tokens & {"preeclampsia", "eclampsia", "hellp"} or "gestational_hypertension" in dx \
                    or "hypertensive_disorder_of_pregnancy" in dx:
                conditions.append("hypertensive_disorder_pregnancy")
            if "gestational_diabetes" in dx or tokens & {"gdm"}:
                conditions.append("gestational_diabetes_delivery")
            if ("self_harm" in dx or "suicid" in dx or "intentional_overdose" in dx
                    or "intentional_self" in dx or details.get("psychiatric_admission") is True):
                conditions.append("mental_health_discharge")

        return [c for c in dict.fromkeys(conditions) if c]

    def _build_obligation_hyperedges(self, nodes_list: List[ClinicalNode]) -> None:
        """
        For each trigger event, check if matching obligation rules exist,
        and create hyperedges connecting the trigger to its required follow-ups.
        """
        for node in nodes_list:
            event_enum = node.event_enum
            if event_enum is None:
                continue

            # Infer every trigger condition and collect their rules (once each)
            matching_rules: List[ObligationRule] = []
            for condition in self._infer_conditions(node):
                for rule in get_rules_for_event(event_enum, condition):
                    if rule not in matching_rules:
                        matching_rules.append(rule)

            for rule in matching_rules:
                # Check if follow-up nodes exist
                deadline_days = get_deadline_days(rule, node.details)
                deadline = node.timestamp + timedelta(days=deadline_days)
                followup_nodes = self._find_followup_nodes(
                    node, rule.required_followups, deadline, nodes_list, rule
                )

                edge_id = self._next_edge_id()
                hyperedge = TemporalHyperedge(
                    edge_id=edge_id,
                    obligation_rule=rule,
                    trigger_node=node,
                    expected_followup_types=[ft.value for ft in rule.required_followups],
                    actual_followup_nodes=followup_nodes,
                    deadline=deadline,
                    deadline_days=deadline_days,
                    evaluation_time=self.evaluation_time,
                )

                # Determine status: closed on time, closed late, or still open
                satisfied_at = hyperedge.satisfied_at
                if satisfied_at is None:
                    hyperedge.status = LoopStatus.OPEN.value
                elif satisfied_at > deadline:
                    hyperedge.status = LoopStatus.DELAYED.value
                else:
                    hyperedge.status = LoopStatus.CLOSED.value

                # Build evidence chain
                hyperedge.evidence_chain = [
                    f"Trigger: {node.event_type} at {node.timestamp.isoformat()} "
                    f"(details: {node.details})",
                    f"Rule: {rule.name} [{rule.rule_id}]",
                    f"Required: {[ft.value for ft in rule.required_followups]}",
                    f"Deadline: {deadline.isoformat()} ({format_window(deadline_days)})",
                    f"Found follow-ups: {[fn.event_type for fn in followup_nodes]}",
                    f"Status: {hyperedge.status}",
                ]
                # Surface follow-ups that exist but did not happen: "CT was
                # cancelled" is more actionable than "no CT".
                required_values = {ft.value for ft in rule.required_followups}
                not_done = [
                    f"{n.event_type} [{n.status}] on {n.timestamp.date().isoformat()}"
                    for n in nodes_list
                    if n.event_type in required_values and n.timestamp > node.timestamp
                    and not is_fulfilling_status(n.status)
                ]
                if not_done:
                    hyperedge.evidence_chain.append(
                        f"Not counted as follow-up (did not take place): {not_done}"
                    )
                required_regions = _required_regions(node, rule)
                if required_regions:
                    hyperedge.evidence_chain.append(
                        f"Follow-up study must cover: {', '.join(required_regions)}")
                    wrong_region = [
                        f"{n.event_type} [{', '.join(n.details.get('body_regions') or []) or 'region unknown'}] "
                        f"on {n.timestamp.date().isoformat()}"
                        for n in nodes_list
                        if n.event_type in required_values and n.event_type in REGION_CHECKED_TYPES
                        and node.timestamp < n.timestamp <= self.evaluation_time
                        and is_fulfilling_status(n.status) and not _region_ok(required_regions, n)
                    ]
                    if wrong_region:
                        hyperedge.evidence_chain.append(
                            f"Not counted as follow-up (different or unknown body region): {wrong_region}")
                review = ((node.details.get("review_notes") or {}).get(rule.rule_id)
                          if isinstance(node.details.get("review_notes"), dict) else None) \
                    or node.details.get("review_note_all")
                if review:
                    hyperedge.evidence_chain.append(f"Human review: {review}")

                self.hyperedges[edge_id] = hyperedge

    def _find_followup_nodes(
        self,
        trigger: ClinicalNode,
        required_types: List[EventType],
        deadline: datetime,
        all_nodes: List[ClinicalNode],
        rule: Optional[ObligationRule] = None,
    ) -> List[ClinicalNode]:
        """
        Find follow-up nodes that match the required types after the trigger.

        Excludes follow-ups that did not actually happen (cancelled, no-show,
        merely scheduled), events dated after the evaluation time, and imaging
        of a different body region than the obligation asks for.
        """
        followups = []
        required_values = {ft.value for ft in required_types}
        required_regions = _required_regions(trigger, rule) if rule else []

        for node in all_nodes:
            if node.timestamp <= trigger.timestamp:
                continue
            if node.timestamp > self.evaluation_time:
                continue
            if not is_fulfilling_status(node.status):
                continue
            if node.patient_id != trigger.patient_id:
                continue
            if node.event_type in required_values:
                if (required_regions and node.event_type in REGION_CHECKED_TYPES
                        and not _region_ok(required_regions, node)):
                    continue
                if rule is not None and not (_details_match(trigger, rule, node) and _type_ok(trigger, rule, node)):
                    continue
                followups.append(node)

        return followups

    def detect_open_loops(self) -> List[TemporalHyperedge]:
        """Return all hyperedges representing unclosed clinical loops."""
        return [
            he for he in self.hyperedges.values()
            if he.status in (LoopStatus.OPEN.value, LoopStatus.DELAYED.value)
        ]

    def detect_closed_loops(self) -> List[TemporalHyperedge]:
        """Return all properly closed loops."""
        return [
            he for he in self.hyperedges.values()
            if he.status == LoopStatus.CLOSED.value
        ]

    def get_all_loops(self) -> List[TemporalHyperedge]:
        """Return all detected obligation chains."""
        return list(self.hyperedges.values())

    def get_temporal_gaps(self) -> List[Dict]:
        """Calculate time gaps between trigger events and their follow-ups."""
        gaps = []
        for he in self.hyperedges.values():
            for fn in he.actual_followup_nodes:
                gap_days = (fn.timestamp - he.trigger_node.timestamp).total_seconds() / 86400
                gaps.append({
                    "edge_id": he.edge_id,
                    "rule_id": he.obligation_rule.rule_id,
                    "trigger_type": he.trigger_node.event_type,
                    "followup_type": fn.event_type,
                    "gap_days": gap_days,
                    "deadline_days": he.obligation_rule.deadline_days,
                    "within_deadline": gap_days <= he.obligation_rule.deadline_days,
                })
        return gaps

    def get_graph_stats(self) -> Dict:
        """Return summary statistics of the hypergraph."""
        statuses = {}
        for he in self.hyperedges.values():
            statuses[he.status] = statuses.get(he.status, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "total_hyperedges": len(self.hyperedges),
            "status_distribution": statuses,
            "total_graph_edges": self.graph.number_of_edges(),
        }

    def export_causal_json(self) -> Dict:
        """
        GRAPH ENGINEERING EXTENSION:
        Export the temporal hypergraph with explicit causal weights, 
        bilingual localized node labels, and temporal decay properties 
        ready for advanced D3.js / React-Force-Graph rendering.
        """
        export_data = {"nodes": [], "hyperedges": []}
        
        # Bilingual mapping for nodes
        bilingual_map = {
            "lab_result": {"en": "Lab Result", "ko": "검사결과"},
            "radiology_report": {"en": "Radiology CT", "ko": "영상판독"},
            "imaging_order": {"en": "CT Order", "ko": "영상오더"},
            "medication_change": {"en": "Rx Modification", "ko": "처방변경"},
            "patient_notification": {"en": "Patient Notice", "ko": "환자안내"},
            "specialist_referral": {"en": "Referral Placed", "ko": "전문의 의뢰"},
            "referral_visit": {"en": "Specialist Visit", "ko": "전문의 진료"},
            "closure_action": {"en": "Loop Resolved", "ko": "루프 종결"}
        }
        
        for node_id, node in self.nodes.items():
            labels = bilingual_map.get(node.event_type, {"en": node.event_type.upper(), "ko": node.event_type.upper()})
            export_data["nodes"].append({
                "id": node.node_id,
                "type": node.event_type,
                "timestamp": node.timestamp.isoformat(),
                "label_en": labels["en"],
                "label_ko": labels["ko"]
            })
            
        for edge_id, he in self.hyperedges.items():
            # Causal weight increases as deadline approaches/passes (Temporal Decay)
            base_weight = 1.0
            if he.status == LoopStatus.OPEN.value and he.deadline:
                days_left = (he.deadline - self.evaluation_time).total_seconds() / 86400
                if days_left < 0:
                    base_weight = min(5.0, 1.0 + abs(days_left) * 0.2)
                elif days_left < 14:
                    base_weight = 1.0 + ((14 - days_left) * 0.1)
                    
            export_data["hyperedges"].append({
                "id": he.edge_id,
                "rule": he.obligation_rule.rule_id,
                "trigger_node": he.trigger_node.node_id,
                "followup_nodes": [n.node_id for n in he.actual_followup_nodes],
                "status": he.status,
                "causal_weight": round(base_weight, 2),
                "is_overdue": he.is_overdue
            })
            
        return export_data
