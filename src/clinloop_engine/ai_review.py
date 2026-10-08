"""
ai_review.py — Imaging-AI as a second reader: findings the report does not address

An approved imaging-AI product (or ClinLoop's on-premise model runner) flags a
finding on a study. ClinLoop compares it with the radiologist's report for the
same study:

  * the report mentions the finding, confirming OR refuting it ("no nodule")
      → the radiologist addressed it: nothing to do;
  * the report does not mention it at all
      → R047: a radiologist reviews the images and documents a decision
        (1 day for critical findings, 7 days otherwise);
  * a later report or addendum that addresses it closes the loop
      (AI_FINDING_REVIEWED), as does a clinician closing it with evidence;
  * no report yet → no loop (the comparison waits for the report).

The AI never makes a diagnosis and never reaches the patient: it can only ask
a radiologist to look again. Findings from research-use models are ignored
unless the hospital sets CLINLOOP_IMAGING_RESEARCH_AI=1.
"""

import os
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from .clinical_ontology import EventType
from .imaging_fhir import AI_FINDINGS, is_research_use
from .radiology import expand_regions, regions_compatible
from .safety_clock import normalize_timestamp

REPORT_WINDOW = timedelta(days=30)        # a report this long after the study is not "its" report
CRITICAL_REVIEW_DAYS = 1.0
REVIEW_DAYS = 7.0


def research_ai_enabled() -> bool:
    return os.environ.get("CLINLOOP_IMAGING_RESEARCH_AI", "").strip().lower() in ("1", "true", "yes", "on")


def _mentions(report: Dict[str, Any], key: str) -> Optional[re.Match]:
    text = report["details"].get("conclusion") or ""
    return re.search(AI_FINDINGS[key]["report"], text, re.I)


def _same_study(ai: Dict[str, Any], report: Dict[str, Any]) -> Optional[bool]:
    """True/False when both sides name their study, None when it cannot be told."""
    a = ai["details"].get("study_ref")
    r = report["details"].get("imaging_studies") or []
    if a and r:
        return a in r
    return None


def apply_ai_review(events: List[Dict[str, Any]]) -> None:
    """Add R047 triggers and AI_FINDING_REVIEWED events to one patient's events (in place)."""
    ts = lambda e: normalize_timestamp(e["timestamp"])  # noqa: E731
    reports = sorted((e for e in events if e["event_type"] == EventType.RADIOLOGY_REPORT.value
                      and e.get("status") not in ("pending", "cancelled")), key=ts)
    derived: List[Dict[str, Any]] = []

    for ai in [e for e in events if e["event_type"] == EventType.AI_FINDING.value]:
        d = ai["details"]
        key = d.get("finding_key")
        spec = AI_FINDINGS.get(key or "", {})
        notes: List[str] = d.setdefault("mapping", [])
        if not d.get("positive") or not spec or spec.get("track") is False:
            continue
        if d.get("research_use") and not research_ai_enabled():
            notes.append("research-use model: shown for information, not used for review loops "
                         "(set CLINLOOP_IMAGING_RESEARCH_AI=1 to include)")
            continue
        study_time = normalize_timestamp(d.get("study_time") or ai["timestamp"])
        regions = d.get("regions") or spec.get("regions") or []
        candidates = []
        for r in reports:
            t = ts(r)
            if not (study_time - timedelta(hours=1) <= t <= study_time + REPORT_WINDOW):
                continue
            same = _same_study(ai, r)
            if same is False:
                continue
            covered = (r["details"].get("radiology") or {}).get("study_regions") or []
            if same or not regions or not covered or regions_compatible(expand_regions(regions), covered):
                candidates.append(r)
        if not candidates:
            notes.append("no radiology report for this study yet: compared once the report arrives")
            continue
        first = candidates[0]
        m = _mentions(first, key)
        label = f"{spec['en']} ({d.get('product') or 'imaging AI'}, score {d.get('score', '–')})"
        if m:
            notes.append(f"report of {ts(first).date()} addresses the AI finding ('{m.group(0)}'): no review needed")
            continue
        days = CRITICAL_REVIEW_DAYS if spec.get("critical") else REVIEW_DAYS
        trigger_time = max(ts(ai), ts(first))
        trigger = {
            **{k: v for k, v in ai.items() if k not in ("details", "event_id", "timestamp")},
            "event_id": f"{ai['event_id']}:discrepancy",
            "timestamp": trigger_time.isoformat(),
            "details": {**{k: v for k, v in d.items() if k != "mapping"},
                        "extra_conditions": ["ai_report_discrepancy"],
                        "rule_deadline_days": {"R047": days},
                        "followup_match": {"R047": {"finding_key": key, "for_ai_event": ai["event_id"]}},
                        "evidence_span": (f"AI: {label}. Report of {ts(first).date()} "
                                          f"(\"{(first['details'].get('conclusion') or '')[:160]}\") does not mention it."),
                        "mapping": [f"AI finding not addressed in the report → radiologist review within {days:g} day(s)"]},
        }
        derived.append(trigger)
        notes.append(f"not mentioned in the report of {ts(first).date()} → R047 review")
        for later in candidates[1:]:
            m = _mentions(later, key)
            if m and ts(later) > trigger_time:
                derived.append({
                    **{k: v for k, v in later.items() if k not in ("details", "event_id", "event_type")},
                    "event_id": f"{later['event_id']}:ai-review:{ai['event_id']}",
                    "event_type": EventType.AI_FINDING_REVIEWED.value,
                    "details": {"finding_key": key, "for_ai_event": ai["event_id"], "evidence_span": m.group(0),
                                "mapping": ["later report/addendum addresses the AI finding→ai_finding_reviewed"]},
                })
                break
    events.extend(derived)
