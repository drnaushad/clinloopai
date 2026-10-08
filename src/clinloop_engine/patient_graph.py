"""
patient_graph.py — One patient's clinical knowledge graph, from the temporal hypergraph

What the engine reasons over, made visible: every clinical event ClinLoop read
for the patient (diagnoses, lab values, orders, medications, appointments,
imaging studies, radiology reports, imaging-AI findings) is a node on a time
axis, and every clinical obligation is a hyperedge that links the event that
created it to the follow-up(s) that fulfilled it, or to the follow-up that is
still MISSING, with its deadline and status.

  GET /api/v1/patients/{id}/graph        (viewer)

Node      = one clinical event (a FHIR resource can yield several), in a lane
Hyperedge = one obligation: trigger → follow-up(s) | expected follow-up (missing)
Edge      = a direct relation: "same study" (study ↔ report ↔ AI finding), "same record"
            (several facts read from one FHIR resource),
            "derived from" (an AI-review event from the AI finding that caused it,
            a diagnostic pattern from each event it was built from)

The graph is built by the same code that opens the loops, so what is drawn is
exactly what the engine decided, with the evidence chain of each obligation.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import User, require_role
from .clinical_ontology import EventType
from .temporal_hypergraph import DynamicTemporalHypergraph, _required_regions

LANES = [
    ("diagnoses", "Diagnoses & risk factors", "진단·위험인자"),
    ("labs", "Lab values & pathology", "검사 수치·병리"),
    ("orders", "Orders & referrals", "오더·의뢰"),
    ("medications", "Medications", "약물"),
    ("appointments", "Appointments & communication", "예약·연락"),
    ("imaging", "Imaging studies & procedures", "영상 검사·시술"),
    ("reports", "Radiology reports", "영상 판독"),
    ("ai", "Imaging AI", "영상 AI"),
    ("notes", "Clinical notes: plans", "진료기록 계획"),
    ("patterns", "Diagnostic patterns", "진단 패턴"),
]
_E = EventType
LANE_OF = {
    **{e.value: "diagnoses" for e in (_E.DIAGNOSIS, _E.RISK_FACTOR)},
    **{e.value: "labs" for e in (_E.LAB_RESULT, _E.FOLLOWUP_LAB, _E.INR_RECHECK, _E.HBA1C_RECHECK, _E.HCV_RNA_TEST,
                                 _E.POSTPARTUM_GLUCOSE_TEST, _E.CULTURE_RESULT, _E.PATHOLOGY_RESULT, _E.BIOPSY_RESULT)},
    **{e.value: "orders" for e in (_E.LAB_ORDER, _E.IMAGING_ORDER, _E.BIOPSY_ORDER, _E.SPECIALIST_REFERRAL,
                                   _E.COLPOSCOPY_REFERRAL)},
    _E.MEDICATION_CHANGE.value: "medications",
    **{e.value: "appointments" for e in (_E.FOLLOWUP_APPOINTMENT, _E.REFERRAL_VISIT, _E.COLPOSCOPY_VISIT,
                                         _E.PATIENT_NOTIFICATION, _E.CALLBACK, _E.CRITICAL_VALUE_NOTIFICATION,
                                         _E.PROVIDER_REVIEW, _E.DISCHARGE, _E.MENTAL_HEALTH_FOLLOWUP, _E.BP_CHECK,
                                         _E.POST_OP_WOUND_CHECK, _E.SEPSIS_BUNDLE_COMPLETION)},
    **{e.value: "imaging" for e in (_E.IMAGING_CT, _E.IMAGING_MRI, _E.IMAGING_ULTRASOUND, _E.IMAGING_XRAY,
                                    _E.IMAGING_PET, _E.FOLLOWUP_CT, _E.LIVER_IMAGING, _E.ECHOCARDIOGRAM,
                                    _E.COLONOSCOPY, _E.BREAST_BIOPSY, _E.ENDOSCOPIC_ULTRASOUND)},
    **{e.value: "reports" for e in (_E.RADIOLOGY_REPORT, _E.IMAGING_RESULT)},
    **{e.value: "ai" for e in (_E.AI_FINDING, _E.AI_FINDING_REVIEWED)},
    _E.CLINICAL_NOTE_PLAN.value: "notes",
    _E.DIAGNOSTIC_PATTERN.value: "patterns",
}


_NAMES = {"imaging_ct": "CT", "imaging_mri": "MRI", "imaging_ultrasound": "Ultrasound", "imaging_xray": "X-ray",
          "imaging_pet": "PET", "followup_ct": "Follow-up CT", "liver_imaging": "Liver imaging",
          "endoscopic_ultrasound": "Endoscopic ultrasound", "ai_finding_reviewed": "AI finding reviewed",
          "hba1c_recheck": "HbA1c recheck", "inr_recheck": "INR recheck", "hcv_rna_test": "HCV RNA test",
          "bp_check": "BP check"}


def _pretty(event_type: str) -> str:
    return _NAMES.get(event_type) or event_type.replace("_", " ").capitalize()


def _top_regions(regions: List[str]) -> List[str]:
    """'abdomen, adrenal, kidney, liver, …' → 'abdomen' (organs inside a listed region are implied)."""
    from .radiology import ORGAN_PARENT
    rs = list(dict.fromkeys(regions or []))
    return [r for r in rs if ORGAN_PARENT.get(r) not in rs]


def node_label(event_type: str, d: Dict[str, Any]) -> str:
    """A short clinical label for one event, from what the mapper extracted."""
    t = event_type
    if t in (_E.LAB_RESULT.value, _E.FOLLOWUP_LAB.value, _E.CULTURE_RESULT.value):
        value = " ".join(str(x) for x in (d.get("value"), d.get("unit")) if x not in (None, ""))
        flag = f" ({d['flag']})" if d.get("flag") else ""
        return f"{d.get('test') or _pretty(t)} {value or d.get('result') or ''}".strip() + flag
    if t == _E.DIAGNOSIS.value:
        return str(d.get("diagnosis") or "Diagnosis")
    if t == _E.RISK_FACTOR.value:
        return f"Smoking: {d['smoking']}" if d.get("smoking") else "Risk factor"
    if t == _E.MEDICATION_CHANGE.value:
        return str(d.get("medication") or d.get("drug") or "Medication change")
    if t == _E.DIAGNOSTIC_PATTERN.value:
        return {"ida": "Pattern: iron-deficiency anaemia", "creatinine-rise": "Pattern: creatinine rise (AKI warning)",
                "af-oac": "Pattern: AF without anticoagulation", "haematuria": "Pattern: persistent haematuria",
                "nodule-growth": "Pattern: lung nodule measured larger"
                }.get(d.get("pattern"), "Diagnostic pattern")
    if t == _E.CLINICAL_NOTE_PLAN.value:
        plan = d.get("plan") or {}
        label = d.get("plan_label") or "Plan in a note"
        return label if plan.get("tracked", True) else f"{label} — not tracked: {plan.get('reason')}"
    if t == _E.AI_FINDING.value:
        return f"AI: {d.get('finding_label') or 'finding'}" + (" (positive)" if d.get("positive") else "")
    if t in (_E.RADIOLOGY_REPORT.value, _E.PATHOLOGY_RESULT.value):
        return str(d.get("report") or _pretty(t))
    if t in LANE_OF and LANE_OF[t] == "imaging" and d.get("body_regions"):
        return f"{_pretty(t)} · {', '.join(_top_regions(d['body_regions']))}"
    return _pretty(t)


def _short(text: Any, n: int = 220) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def build_patient_graph(patient_id: str, events: List[Dict[str, Any]],
                        evaluation_time: Optional[datetime] = None) -> Dict[str, Any]:
    """The knowledge graph of one patient's events (as produced by fhir_ingest.bundle_to_events)."""
    g = DynamicTemporalHypergraph(evaluation_time=evaluation_time)
    g.build_from_patient_trajectory(events)
    by_id = {e["event_id"]: e for e in events}

    nodes: List[Dict[str, Any]] = []
    for n in sorted(g.nodes.values(), key=lambda x: x.timestamp):
        d = n.details or {}
        derived = ":discrepancy" in n.node_id or ":ai-review:" in n.node_id or n.node_id.startswith("pattern:")
        detail = d.get("conclusion") or d.get("evidence_span") or ""
        nodes.append({
            "id": n.node_id, "type": n.event_type, "lane": LANE_OF.get(n.event_type, "appointments"),
            "time": n.timestamp.isoformat(), "status": n.status, "label": _short(node_label(n.event_type, d), 90),
            "detail": _short(detail), "source": (by_id.get(n.node_id) or {}).get("source"),
            "derived": derived, "future": n.timestamp > g.evaluation_time,
        })

    hyperedges: List[Dict[str, Any]] = []
    for he in g.hyperedges.values():
        rule = he.obligation_rule
        found = {f.event_type for f in he.actual_followup_nodes}
        missing = [ft for ft in he.expected_followup_types if ft not in found]
        if rule.followup_logic == "any" and found:
            missing = []
        regions = _required_regions(he.trigger_node, rule)
        narrowed = (he.trigger_node.details.get("followup_types") or {}).get(rule.rule_id)
        if narrowed:                      # a note's "CT" plan: only CT counts
            missing = [ft for ft in missing if ft in narrowed][:1] or missing[:1]
        elif he.trigger_node.event_type == _E.CLINICAL_NOTE_PLAN.value:
            missing = missing[:1]         # "lab result", not every lab-like event type
        match = (he.trigger_node.details.get("followup_match") or {}).get(rule.rule_id) or {}
        what = ", ".join(str(v).replace("_", " ") for k, v in match.items() if k in ("analyte", "specialty"))
        hyperedges.append({
            "id": he.edge_id, "rule_id": rule.rule_id, "rule_name": rule.name,
            "severity": rule.severity.value, "status": he.status,
            "trigger": he.trigger_node.node_id,
            "followups": [f.node_id for f in he.actual_followup_nodes],
            "expected": [{"type": ft, "label": _pretty(ft) + (f" · {', '.join(regions)}" if regions and LANE_OF.get(ft) == "imaging" else "")
                          + (f" · {what}" if what else ""),
                          "lane": LANE_OF.get(ft, "appointments")} for ft in missing],
            "followup_logic": rule.followup_logic,
            "deadline": he.deadline.isoformat() if he.deadline else None,
            "overdue": bool(he.is_overdue and he.status == "open"),
            "evidence": he.evidence_chain,
        })

    # Direct relations: the same imaging study (study ↔ report ↔ AI finding), and AI-review derivations
    edges: List[Dict[str, Any]] = []
    study_of: Dict[str, List[str]] = {}
    for e in events:
        d = e.get("details") or {}
        keys = {d.get("study_uid"), d.get("study_ref"), e.get("source") if LANE_OF.get(e["event_type"]) == "imaging" else None}
        keys |= set((d.get("radiology") or {}).get("imaging_studies") or d.get("imaging_studies") or [])
        for k in keys - {None, ""}:
            study_of.setdefault(str(k), []).append(e["event_id"])
    seen = set()
    for members in study_of.values():
        for a in members:
            for b in members:
                if a < b and (a, b) not in seen and a in g.nodes and b in g.nodes:
                    seen.add((a, b))
                    edges.append({"source": a, "target": b, "kind": "same_study"})
    by_source: Dict[str, List[str]] = {}
    for e in events:
        if e.get("source") and e["event_id"] in g.nodes:
            by_source.setdefault(e["source"], []).append(e["event_id"])
    for members in by_source.values():
        for other in members[1:]:          # several facts read from one record
            if (min(members[0], other), max(members[0], other)) not in seen:
                edges.append({"source": members[0], "target": other, "kind": "same_record"})
    for n in nodes:                       # a pattern node hangs off every event it was built from
        for origin in (g.nodes[n["id"]].details.get("evidence_events") or []):
            if origin in g.nodes:
                edges.append({"source": origin, "target": n["id"], "kind": "derived_from"})
    for n in nodes:
        if n["derived"] and not n["id"].startswith("pattern:"):
            origin = n["id"].split(":ai-review:")[-1] if ":ai-review:" in n["id"] else n["id"].rsplit(":discrepancy", 1)[0]
            if origin in g.nodes and origin != n["id"]:
                edges.append({"source": origin, "target": n["id"], "kind": "derived_from"})

    statuses: Dict[str, int] = {}
    for h in hyperedges:
        statuses[h["status"]] = statuses.get(h["status"], 0) + 1
    return {
        "patient_id": patient_id,
        "evaluation_time": g.evaluation_time.isoformat(),
        "lanes": [{"id": i, "en": en, "ko": ko} for i, en, ko in LANES],
        "nodes": nodes, "hyperedges": hyperedges, "edges": edges,
        "stats": {"events": len(nodes), "obligations": len(hyperedges), "status": statuses,
                  "relations": len(edges)},
    }


# ── API ─────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1")


@router.get("/patients/{patient_id}/graph", tags=["Imaging & Documents"])
def patient_graph(patient_id: str,
                  evaluation_time: Optional[str] = Query(None, description="ISO time to evaluate at (default: now)"),
                  user: User = Depends(require_role("viewer"))):
    """
    The patient's clinical knowledge graph: events by lane on a time axis, obligations as
    hyperedges (trigger → follow-up, or the missing follow-up and its deadline), study links,
    and each loop's worklist state.
    """
    from .clinical_api import get_store
    from .fhir_ingest import bundle_to_events
    from .fhir_sync import client_from_env, patient_record
    from .imaging_api import FHIR_ID, _patient_resource
    from .loop_store import loop_key
    from .pacs_client import client_from_env as pacs_from_env
    from .safety_clock import normalize_timestamp
    if not re.fullmatch(FHIR_ID, patient_id):
        raise HTTPException(422, "Invalid patient id")
    when = None
    if evaluation_time:
        try:
            when = normalize_timestamp(evaluation_time)
        except (TypeError, ValueError):
            raise HTTPException(422, "evaluation_time must be an ISO date-time")
    _patient_resource(patient_id)
    store = get_store()
    resources, warnings = patient_record(patient_id, store, client_from_env(), pacs_from_env())
    events_by_patient, w2 = bundle_to_events(resources)
    graph = build_patient_graph(patient_id, events_by_patient.get(patient_id, []), when)
    for h in graph["hyperedges"]:
        try:
            row = store.get(loop_key(patient_id, h["rule_id"], h["trigger"]))
            h["worklist"] = {"loop_key": row["loop_key"], "state": row["workflow_state"], "owner": row["owner"]}
        except KeyError:
            h["worklist"] = None
    graph["warnings"] = warnings + w2
    return graph
