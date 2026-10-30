"""
Analyse one FHIR Bundle without a server: the engine call path of ``POST /api/v1/fhir/ingest``
(``bundle_to_events`` → ``hospital_detector(...).process_patient`` → ``lapse_after_death``),
minus the loop store, the PACS and the access log.

The public website runs this module in the visitor's browser (Pyodide) from the "Analyse patient"
page (analyse.html): the bundle never leaves the browser and nothing is stored. Keep its imports to
the engine modules ``bundle_to_events`` and the detector already need, so the page stays small;
``scripts/build_engine_manifest.py`` lists the files the page downloads, and a test keeps the list in
sync with what this module imports.
"""

import json
from typing import Any, Dict, List, Optional

from .fhir_ingest import bundle_to_events, resolved_resources
from .loop_detector import hospital_detector, lapse_after_death
from .safety_clock import normalize_timestamp, utc_now

ACTIVE = ("open", "needs_human_review")


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _row(d) -> Dict[str, Any]:
    """The fields the page shows: what is due, by when, what is missing and why (plain language)."""
    return {
        "patient_id": d.patient_id,
        "rule_id": d.rule_id,
        "rule_name": d.rule_name,
        "status": d.loop_status,
        "severity": d.severity,
        "trigger_event": d.trigger_event,
        "trigger_time": _iso(d.trigger_time),
        "deadline": _iso(d.deadline),
        "missing": d.missing_step,
        "recommended_action": d.recommended_action,
        "basis": list(d.basis or []),
        "basis_ko": list(d.basis_ko or []),
        "evidence": [str(e) for e in (d.evidence_chain or [])],
        "should_abstain": bool(d.should_abstain),
    }


def analyse_bundle(bundle: Dict[str, Any], evaluation_time: Optional[str] = None) -> Dict[str, Any]:
    """Map a FHIR Bundle to events and run the hospital detector, as the ingest endpoint does."""
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise ValueError("Body must be a FHIR Bundle")
    when = normalize_timestamp(evaluation_time) if evaluation_time else None
    resources = resolved_resources(bundle)
    events_by_patient, warnings = bundle_to_events(resources, evaluation_time=when)
    detector = hospital_detector(when)
    detections: List = []
    for pid, events in events_by_patient.items():
        detections.extend(lapse_after_death(detector.process_patient("in-browser", pid, events), resources))
    rows = [_row(d) for d in detections]
    order = {"open": 0, "needs_human_review": 1}
    rows.sort(key=lambda r: (order.get(r["status"], 2), r["deadline"] or "", r["rule_id"]))
    return {
        "evaluation_time": _iso(when or utc_now()),
        "patients": len(events_by_patient),
        "events": sum(len(v) for v in events_by_patient.values()),
        "active_loops": sum(1 for d in detections if d.loop_status in ACTIVE),
        "detections": rows,
        "warnings": list(warnings),
    }


def analyse_json(text: str, evaluation_time: Optional[str] = None) -> str:
    """JSON in, JSON out: the form the browser page calls through Pyodide."""
    return json.dumps(analyse_bundle(json.loads(text), evaluation_time or None), ensure_ascii=False, default=str)
