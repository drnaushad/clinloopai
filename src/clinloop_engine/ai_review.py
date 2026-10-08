"""
ai_review.py — Imaging-AI as a second reader: findings the report does not address

An approved imaging-AI product (or ClinLoop's on-premise model runner) flags a
finding on a study. ClinLoop compares it with the radiologist's report of THAT
study:

  * the report mentions the finding, confirming OR refuting it ("no nodule")
      → the radiologist addressed it: nothing to do;
  * the report does not mention it at all
      → R047: a radiologist reviews the images and documents a decision
        (1 day for critical findings, 7 days otherwise);
  * a later report or addendum of the same study that addresses it closes the
    loop (AI_FINDING_REVIEWED), as does a clinician closing it with evidence;
  * no report yet → no loop (the comparison waits for the report).

Which report belongs to the study: first by DICOM StudyInstanceUID (or the same
ImagingStudy reference); only when neither side names its study, the first
report after the study whose body region covers the finding. A report written
before the study is never "its" report.

The same finding from two sources (the vendor's feed and an upload, or a
re-analysis) is reviewed once. The AI never makes a diagnosis and never reaches
the patient: it can only ask a radiologist to look again. Findings from
research-use products, or products with no stated approval, are ignored unless
the hospital sets CLINLOOP_IMAGING_RESEARCH_AI=1.
"""

import os
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set

from .clinical_ontology import EventType
from .imaging_fhir import AI_FINDINGS
from .radiology import expand_regions, regions_compatible
from .safety_clock import normalize_timestamp

REPORT_WINDOW = timedelta(days=30)        # a report this long after the study is not "its" report
CLOCK_SKEW = timedelta(minutes=10)
CRITICAL_REVIEW_DAYS = 1.0
REVIEW_DAYS = 7.0
IMAGING_EVENT_TYPES = {EventType.IMAGING_CT.value, EventType.IMAGING_MRI.value, EventType.IMAGING_ULTRASOUND.value,
                       EventType.IMAGING_XRAY.value, EventType.IMAGING_PET.value}


def research_ai_enabled() -> bool:
    return os.environ.get("CLINLOOP_IMAGING_RESEARCH_AI", "").strip().lower() in ("1", "true", "yes", "on")


def _mentions(report: Dict[str, Any], key: str) -> Optional[re.Match]:
    text = report["details"].get("conclusion") or ""
    return re.search(AI_FINDINGS[key]["report"], text, re.I)


def apply_ai_review(events: List[Dict[str, Any]]) -> None:
    """Add R047 triggers and AI_FINDING_REVIEWED events to one patient's events (in place)."""
    ts = lambda e: normalize_timestamp(e["timestamp"])  # noqa: E731

    # ImagingStudy reference → StudyInstanceUID (from the studies in the record)
    ref_uid: Dict[str, str] = {}
    for e in events:
        d = e["details"]
        if e["event_type"] in IMAGING_EVENT_TYPES and d.get("study_ref") and d.get("study_uid"):
            ref_uid[d["study_ref"]] = d["study_uid"]

    def report_ids(r: Dict[str, Any]) -> Set[str]:
        refs = r["details"].get("imaging_studies") or []
        return {x for ref in refs for x in (ref, ref_uid.get(ref)) if x}

    def ai_ids(d: Dict[str, Any]) -> Set[str]:
        return {x for x in (d.get("study_uid"), d.get("study_ref"), ref_uid.get(d.get("study_ref") or "")) if x}

    reports = sorted((e for e in events if e["event_type"] == EventType.RADIOLOGY_REPORT.value
                      and e.get("status") not in ("pending", "cancelled")), key=ts)

    # One review per finding per study, whichever source(s) reported it: keep the strongest
    best: Dict[tuple, Dict[str, Any]] = {}
    for ai in (e for e in events if e["event_type"] == EventType.AI_FINDING.value):
        d = ai["details"]
        key = d.get("finding_key")
        spec = AI_FINDINGS.get(key or "", {})
        notes: List[str] = d.setdefault("mapping", [])
        if not d.get("positive") or not spec or spec.get("track") is False:
            continue
        if d.get("research_use") and not research_ai_enabled():
            notes.append("research use or no stated approval: shown for information, not used for review loops "
                         "(CLINLOOP_IMAGING_RESEARCH_AI=1 to include)")
            continue
        ids = ai_ids(d)
        study_key = min(ids) if ids else str(normalize_timestamp(d.get("study_time") or ai["timestamp"]).date())
        k = (study_key, key)
        if k not in best or (d.get("score") or 0) > (best[k]["details"].get("score") or 0):
            if k in best:
                best[k]["details"]["mapping"].append("same finding reported again for this study: reviewed once")
            best[k] = ai
        else:
            notes.append("same finding reported again for this study: reviewed once")

    derived: List[Dict[str, Any]] = []
    for ai in best.values():
        d = ai["details"]
        key = d["finding_key"]
        spec = AI_FINDINGS[key]
        notes = d["mapping"]
        study_time = normalize_timestamp(d.get("study_time") or ai["timestamp"])
        ids = ai_ids(d)
        regions = d.get("regions") or spec.get("regions") or []

        same = [r for r in reports if ids and report_ids(r) & ids]
        if same:
            candidates = same
        else:
            candidates = []
            if not regions:
                notes.append("no study link and no body region: cannot tell which report is this study's")
                continue
            for r in reports:
                if report_ids(r) and ids:
                    continue                      # the report names a different study
                t = ts(r)
                if not (study_time - CLOCK_SKEW <= t <= study_time + REPORT_WINDOW):
                    continue
                covered = (r["details"].get("radiology") or {}).get("study_regions") or []
                if covered and regions_compatible(expand_regions(regions), covered):
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
        derived.append({
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
        })
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
