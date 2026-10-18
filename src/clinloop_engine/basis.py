"""
basis.py — Why a loop exists, in plain words a clinician can check against the record

Non-device clinical decision support rests on one condition (REGULATORY_ASSESSMENT.md §2, criterion 4):
the professional can independently review the basis of what the software shows, so they need not rely
on it. The evidence chain and the risk-score breakdown are complete but written for engineers. This
module states the same facts the way a clinician reads a chart:

    Finding    what started it, with the value or the report's own sentence, and when
    Rule       which rule, what it expects, and by when
    Reasoning  how the deadline or the obligation was worked out (e.g. the Fleischner category)
    Found      which follow-up the record holds so far, or that none is recorded
    Reference  the guideline the rule cites

Only facts already in the record and the rule are used: nothing is inferred or scored here.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

_EVENT_NAMES = {
    "lab_result": "lab result", "radiology_report": "radiology report", "pathology_result": "pathology result",
    "culture_result": "culture result", "medication_change": "medication change", "discharge": "discharge",
    "specialist_referral": "referral", "clinical_note_plan": "plan in a clinical note", "ecg": "ECG",
    "echocardiogram": "echocardiogram", "diagnosis": "diagnosis", "diagnostic_pattern": "pattern across results",
    "colonoscopy_finding": "colonoscopy finding", "liver_imaging": "liver imaging",
}
# Follow-up steps as clinicians say them (also used for the EHR cards, cds_hooks.py)
FOLLOWUP_NAMES = {
    "critical_value_notification": "documented call to the treating clinician",
    "followup_ct": "follow-up CT", "followup_lab": "monitoring lab", "followup_appointment": "clinic visit",
    "referral_visit": "specialist visit", "specialist_referral": "specialist referral", "bp_check": "blood-pressure check",
    "inr_recheck": "INR recheck", "hba1c_recheck": "HbA1c recheck", "hcv_rna_test": "HCV RNA test",
    "imaging_ct": "CT", "imaging_mri": "MRI", "imaging_ultrasound": "ultrasound", "imaging_xray": "X-ray",
    "imaging_pet": "PET-CT", "lab_result": "repeat test", "culture_result": "repeat culture",
    "patient_notification": "patient notified", "provider_review": "clinician review",
}
_QUOTE_KEYS = ("evidence_span", "plan_text", "conclusion", "interpretation")
_MAX_QUOTE = 240


def _name(event_type: str) -> str:
    return _EVENT_NAMES.get(event_type, event_type.replace("_", " "))


def _step(event_type: str) -> str:
    return FOLLOWUP_NAMES.get(event_type, event_type.replace("_", " "))


def _when(ts: Optional[datetime]) -> str:
    return ts.strftime("%Y-%m-%d %H:%M") if ts else "unknown time"


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_QUOTE else text[:_MAX_QUOTE].rsplit(" ", 1)[0] + " …"


def _quote(details: Dict[str, Any]) -> Optional[str]:
    """The record's own words. The evidence span is a character window and can start or end inside a
    word ('…grade dysplasia' for 'High-grade dysplasia', '…mm adrenal nodule' without its size), which
    can change the meaning. When the span comes from the report text, the whole sentence(s) around it
    are quoted instead."""
    from .report_text import sentence
    span = details.get("evidence_span")
    for key in ("conclusion", "plan_text", "interpretation"):
        text = details.get(key)
        if isinstance(span, str) and span.strip() and isinstance(text, str):
            at = text.find(span.strip())
            if at >= 0:
                return _short(sentence(text, at, at + len(span.strip())).strip(" ;."))
    for key in _QUOTE_KEYS:
        text = details.get(key)
        if isinstance(text, str) and text.strip():
            return _short(text)
    return None


def _value(details: Dict[str, Any]) -> Optional[str]:
    value = details.get("value")
    if value is None or isinstance(value, (dict, list)):
        return None
    test = details.get("analyte") or details.get("test") or "result"
    unit = details.get("unit") or ""
    flag = details.get("flag")
    text = f"{test} {value}{(' ' + unit) if unit else ''}"
    return text + (f" (flagged {str(flag).lower()})" if flag else "")


def _what(event_type: str, details: Dict[str, Any]) -> str:
    for key in ("report", "test", "medication", "drug", "diagnosis", "primary_diagnosis", "order", "specialty",
                "organism", "specimen"):
        v = details.get(key)
        if isinstance(v, str) and v.strip():
            return f"{_name(event_type)}: {v.strip().replace('_', ' ')}"
    return _name(event_type)


def _reasoning(details: Dict[str, Any]) -> List[str]:
    """The mapping notes that explain a decision; plain resource-type routing ('Observation→lab_result')
    is technical detail and left out."""
    out = []
    for line in details.get("mapping") or []:
        if not isinstance(line, str) or "code/text" in line:
            continue
        head, _, tail = (part.strip() for part in line.partition("→"))
        if tail and (re.fullmatch(r"[a-z_]+", tail)
                     or re.fullmatch(r"[A-Z][A-Za-z]*(\([^)]*\))?( (start|end))?", head)):
            continue       # routing to an event type: "Observation→lab_result", "Encounter(IMP) end→discharge"
        out.append(line)
    return out


def build(trigger, rule, deadline: Optional[datetime], window: str, followups, status: str,
          expected: List[str], logic: str) -> List[str]:
    """Plain-language basis for one loop. ``trigger`` and ``followups`` are graph nodes (event_type,
    timestamp, details, status); ``expected`` the follow-up types the rule asks for."""
    details = trigger.details or {}
    lines = []
    finding = _value(details) or _what(trigger.event_type, details)
    lines.append(f"Finding: {finding}, {_when(trigger.timestamp)}.")
    quote = _quote(details)
    if quote:
        lines.append(f"The record says: “{quote}”")
    joiner = " or " if logic == "any" else " and "
    wanted = joiner.join(_step(t) for t in expected) or "follow-up"
    # A clock time on a deadline weeks away is false precision: the date is what matters
    long_window = bool(deadline and trigger.timestamp and (deadline - trigger.timestamp).days >= 2)
    by = deadline.strftime("%Y-%m-%d") if long_window else _when(deadline)
    lines.append(f"Rule {rule.rule_id} ({rule.name}) expects: {wanted} by {by} ({window}).")
    for line in _reasoning(details):
        lines.append(f"How this was worked out: {line}.")
    if followups:
        found = "; ".join(f"{_step(f.event_type)} on {_when(f.timestamp)}" for f in followups)
        lines.append(f"Found in the record: {found}.")
    else:
        lines.append("Found in the record: no matching follow-up yet.")
    if followups and logic != "any" and status != "closed":
        done = {f.event_type for f in followups}
        missing = [t for t in expected if t not in done]
        if missing:                 # e.g. patient told, but no referral yet: say which part is outstanding
            lines.append(f"Still missing: {', '.join(_step(t) for t in missing)}.")
    if status == "delayed":
        lines.append("The follow-up came after the deadline.")
    refs = [r for r in (rule.references or []) if isinstance(r, str) and r.strip()]
    if refs:
        lines.append(f"Reference: {refs[0]}")
    return lines
