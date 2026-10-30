"""
ecg.py — Electrocardiograms: the follow-up an ECG creates

Two ECG findings carry a follow-up obligation that is easy to miss:
  * atrial fibrillation or flutter: becomes part of the problem list, so the AF anticoagulation
    decision (R054, CHA₂DS₂-VASc) applies even when AF was only ever written on an ECG;
  * a corrected QT interval of 500 ms or more: QT-prolonging medicines and electrolytes are reviewed
    and the ECG repeated within 24 hours (R059).

Recognised inputs:
  * FHIR Observation or DiagnosticReport for an ECG (LOINC 11524-6, 18844-1, 8601-7, 34534-8; or ECG/EKG,
    electrocardiogram, 심전도 in the name), with the interpretation as text or SCP-ECG statement codes;
  * a QTc observation (LOINC 8636-3), in ms or s;
  * PTB-XL (ptbxl_database.csv): report text (often German) and SCP-ECG statements, via load_ptbxl().

An ECG is also an event of its own, so a repeat ECG closes R059.
"""

import ast
import csv
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .report_text import affirmed, sentence

ECG_LOINC = {"11524-6", "18844-1", "8601-7", "34534-8", "93000"}
QTC_LOINC = {"8636-3"}
SCP_SYSTEM = "urn:scp-ecg"
QTC_LIMIT_MS = 500

# SCP-ECG statements (as used by PTB-XL) that matter for follow-up, with a plain name
SCP = {"AFIB": "atrial fibrillation", "AFLT": "atrial flutter", "LNGQT": "prolonged QT",
       "3AVB": "complete heart block", "IMI": "inferior myocardial infarction", "AMI": "anterior myocardial infarction",
       "ASMI": "anteroseptal myocardial infarction", "LMI": "lateral myocardial infarction",
       "LBBB": "left bundle branch block", "WPW": "Wolff-Parkinson-White pattern", "NORM": "normal ECG"}

_ECG_TEXT = re.compile(r"\b(?:ecg|ekg|electrocardiogra\w*|12[- ]lead)\b|심전도", re.I)
_QTC_TEXT = re.compile(r"\bqtc\b|corrected q-?t|q-?t interval corr", re.I)
_AF = re.compile(r"atrial fibrillation|atrial flutter|\bafib\b|\ba-?fib\b|vorhofflimmern|vorhofflattern|"
                 r"심방\s*세동|심방\s*조동", re.I)
# Negated or uncertain in the same clause. Known or paroxysmal AF ("history of AF") still needs the
# anticoagulation decision, so a history is not a negation
_AF_NEGATED = re.compile(r"(?:\bno\b|\bnot\b|without|\bkein\w*|rule out|r/o|possible|probable|consider|없음|배제)"
                         r"[^.;\n?!]{0,40}$", re.I)
# Machine printouts give "QT/QTc 400/512 ms": the QTc is the second number
_NUMBER = r"\d+(?:\.\d+)?"
_QT_QTC_PAIR = re.compile(rf"\bqt\s*/\s*qtc\w*\s*[:=]?\s*{_NUMBER}\s*/\s*({_NUMBER})(?![\d.])"
                          r"\s*([A-Za-zµμ]+)?", re.I)
_QTC_VALUE = re.compile(rf"\bqtc\w*\b[^0-9\n]{{0,15}}?({_NUMBER})(?![\d.])\s*([A-Za-zµμ]+)?", re.I)
_AF_UNCERTAIN_BEFORE = re.compile(r"(?:rule\s*out|r/o|possible|probable|consider|suspect\w*|cannot\s+(?:exclude|rule\s*out)|"
                                    r"can\s*not\s+(?:exclude|rule\s*out)|의심|가능성|배제)[^.;\n?!]{0,40}$", re.I)
_AF_UNCERTAIN_AFTER = re.compile(r"^\s*(?:\?|(?:cannot|can\s*not|could\s*not)\s+be\s+(?:excluded|ruled\s*out)|"
                                   r"(?:is\s+)?(?:possible|probable|suspected)|의심|가능성|배제\s*(?:불가|못))", re.I)


def _codes(concept: Optional[Dict]) -> set:
    return {c.get("code") for c in (concept or {}).get("coding", []) if c.get("code")}


def is_ecg(resource: Dict) -> bool:
    code = resource.get("code") or {}
    text = " ".join([code.get("text") or ""] + [c.get("display") or "" for c in code.get("coding", [])]
                    + [(c.get("text") or "") for c in resource.get("category", []) if isinstance(c, dict)])
    return bool(_codes(code) & (ECG_LOINC | QTC_LOINC)) or bool(_ECG_TEXT.search(text)) or bool(_QTC_TEXT.search(text))


def _qtc_quantity_ms(quantity: Dict) -> Optional[float]:
    value = quantity.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    unit = str(quantity.get("code") or quantity.get("unit") or "").strip().lower()
    if unit in {"s", "sec", "second", "seconds"}:
        return float(value) * 1000
    if unit in {"ms", "msec", "millisecond", "milliseconds"}:
        return float(value)
    if unit:
        return None  # Unknown declared units must never be silently reinterpreted.
    return float(value) * (1000 if value < 2 else 1)  # Legacy unitless input.


def qtc_ms(resource: Dict, text: str) -> Optional[float]:
    """QTc in ms. An explicit declared unit takes precedence over magnitude."""
    code = resource.get("code") or {}
    q = resource.get("valueQuantity") or {}
    if _codes(code) & QTC_LOINC or _QTC_TEXT.search(code.get("text") or ""):
        value = _qtc_quantity_ms(q)
        if value is not None:
            return value
    for comp in resource.get("component", []):
        if _codes(comp.get("code")) & QTC_LOINC or _QTC_TEXT.search((comp.get("code") or {}).get("text") or ""):
            value = _qtc_quantity_ms(comp.get("valueQuantity") or {})
            if value is not None:
                return value
    pair = _QT_QTC_PAIR.search(text or "")
    if pair:
        return _qtc_quantity_ms({"value": float(pair.group(1)), "unit": pair.group(2) or ""})
    m = _QTC_VALUE.search(text or "")
    if m:
        quantity = {"value": float(m.group(1))}
        if m.group(2):
            quantity["unit"] = m.group(2)
        return _qtc_quantity_ms(quantity)
    return None


def scp_statements(resource: Dict) -> List[str]:
    """SCP-ECG statements present (PTB-XL gives likelihood 0 for statements without one; 1–49 means uncertain)."""
    return _scp_interpretation(resource)[0]


def _scp_interpretation(resource: Dict) -> Tuple[List[str], bool]:
    """Keep legacy unknown likelihood 0, but never assert from malformed probabilities."""
    out = []
    invalid = False
    for comp in resource.get("component", []):
        for c in (comp.get("code") or {}).get("coding", []):
            if c.get("system") == SCP_SYSTEM and c.get("code"):
                likelihood = (comp.get("valueQuantity") or {}).get("value", 100)
                try:
                    if isinstance(likelihood, bool):
                        raise ValueError
                    value = float(likelihood)
                    if not math.isfinite(value) or not 0 <= value <= 100:
                        raise ValueError
                except (ValueError, TypeError, OverflowError):
                    invalid = True
                    continue
                if not (0 < value < 50):
                    out.append(c["code"].upper())
    return out, invalid


def _af_interpretation(text: str) -> Tuple[List[re.Match], bool]:
    confirmed, uncertain = [], False
    for m in _AF.finditer(text or ""):
        before = text[max(0, m.start() - 60):m.start()]
        clause = re.split(r"[.;\n?!]", before)[-1]
        if before.rstrip().endswith("?") or _AF_UNCERTAIN_BEFORE.search(clause) \
                or _AF_UNCERTAIN_AFTER.search(text[m.end():]):
            uncertain = True
            continue
        if not _AF_NEGATED.search(clause) and affirmed(text, m):
            confirmed.append(m)
    return confirmed, uncertain


def af_in_text(text: str) -> bool:
    return bool(_af_interpretation(text or "")[0])


def map_ecg(resource: Dict, ts: Optional[str], text: str) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
    """Events for one ECG: the ECG itself (prolonged_qtc when QTc ≥ 500 ms) and AF as a diagnosis."""
    from .clinical_ontology import EventType
    statements, invalid_statements = _scp_interpretation(resource)
    af_matches, uncertain_af = _af_interpretation(text or "")
    qtc = qtc_ms(resource, text)
    details: Dict[str, Any] = {"ecg": True, "interpretation": (text or "")[:500] or None,
                               "statements": [SCP.get(s, s) for s in statements], "mapping": ["ECG→ecg"]}
    if qtc is not None:
        details["qtc_ms"] = round(qtc)
        if qtc >= QTC_LIMIT_MS:
            details["condition"] = "prolonged_qtc"
            details["evidence_span"] = f"QTc {round(qtc)} ms (≥ {QTC_LIMIT_MS} ms)"
            details["mapping"].append(f"QTc {round(qtc)} ms ≥ {QTC_LIMIT_MS}→prolonged_qtc")
    elif "LNGQT" in statements:
        details["mapping"].append("long QT statement without a QTc value: no R059 (the value decides)")
    if invalid_statements or uncertain_af or (qtc is None and _QTC_TEXT.search(text or "")):
        details["review_required"] = True
        details["review_note"] = "ECG interpretation contains uncertain findings or unsupported values; verify the original report"
        details["review_note_all"] = details["review_note"]
        details["mapping"].append("unverified ECG assertion/value: human review required; no diagnosis inferred from that evidence")
    events = [(EventType.ECG.value, ts, details)]
    if {"AFIB", "AFLT"} & set(statements) or af_matches:
        events.append((EventType.DIAGNOSIS.value, ts, {
            "diagnosis": "atrial fibrillation (on ECG)", "codes": ["I48"],
            "evidence_span": sentence(text, af_matches[0].start(), af_matches[0].end()).strip() if af_matches else "SCP-ECG AFIB/AFLT statement",
            "mapping": ["ECG shows atrial fibrillation/flutter→diagnosis (AF anticoagulation decision, R054)"]}))
    return events


def load_ptbxl(database_csv: str, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
    """FHIR resources per patient from PTB-XL's ptbxl_database.csv (sex: 0 male, 1 female)."""
    out: Dict[str, List[Dict]] = defaultdict(list)
    seen = set()
    with open(database_csv, encoding="utf-8", errors="replace", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            if limit and i >= limit:
                break
            pid = str(int(float(r["patient_id"]))) if r.get("patient_id") else f"ecg-{r['ecg_id']}"
            if pid not in seen:
                seen.add(pid)
                patient = {"resourceType": "Patient", "id": pid,
                           "gender": {"0": "male", "1": "female"}.get(str(r.get("sex", "")).split(".")[0], "unknown")}
                out[pid].append(patient)
            try:
                codes = ast.literal_eval(r.get("scp_codes") or "{}")
            except (ValueError, SyntaxError):
                codes = {}
            out[pid].append({
                "resourceType": "Observation", "id": f"ecg-{r['ecg_id']}", "status": "final",
                "subject": {"reference": f"Patient/{pid}"},
                "code": {"coding": [{"system": "http://loinc.org", "code": "11524-6", "display": "EKG study"}],
                         "text": "12-lead ECG"},
                "effectiveDateTime": (r.get("recording_date") or "").replace(" ", "T") or None,
                "valueString": r.get("report", ""),
                "component": [{"code": {"coding": [{"system": SCP_SYSTEM, "code": k}]},
                               "valueQuantity": {"value": float(v)}} for k, v in codes.items()]})
    return dict(out)
