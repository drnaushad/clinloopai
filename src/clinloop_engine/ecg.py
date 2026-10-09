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
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

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
_AF_NEGATED = re.compile(r"(?:\bno\b|\bnot\b|without|\bkein\w*|resolved|history of|\bhx\b|rule out|r/o|"
                         r"\?|possible|probable|consider|없음|배제)[^.;\n]{0,40}$", re.I)
_QTC_VALUE = re.compile(r"\bqtc\w*\b[^0-9\n]{0,15}(\d{3}(?:\.\d)?|0\.\d{2,3})\s*(ms|msec|s\b)?", re.I)


def _codes(concept: Optional[Dict]) -> set:
    return {c.get("code") for c in (concept or {}).get("coding", []) if c.get("code")}


def is_ecg(resource: Dict) -> bool:
    code = resource.get("code") or {}
    text = " ".join([code.get("text") or ""] + [c.get("display") or "" for c in code.get("coding", [])]
                    + [(c.get("text") or "") for c in resource.get("category", []) if isinstance(c, dict)])
    return bool(_codes(code) & (ECG_LOINC | QTC_LOINC)) or bool(_ECG_TEXT.search(text)) or bool(_QTC_TEXT.search(text))


def qtc_ms(resource: Dict, text: str) -> Optional[float]:
    """The QTc in ms, from a QTc observation's value or from the interpretation text."""
    code = resource.get("code") or {}
    q = resource.get("valueQuantity") or {}
    if (_codes(code) & QTC_LOINC or _QTC_TEXT.search(code.get("text") or "")) and isinstance(q.get("value"), (int, float)):
        unit = str(q.get("unit") or q.get("code") or "ms").lower()
        return float(q["value"]) * (1000 if unit in ("s", "sec") or q["value"] < 2 else 1)
    for comp in resource.get("component", []):
        cq = comp.get("valueQuantity") or {}
        if (_codes(comp.get("code")) & QTC_LOINC or _QTC_TEXT.search((comp.get("code") or {}).get("text") or "")) \
                and isinstance(cq.get("value"), (int, float)):
            return float(cq["value"]) * (1000 if cq["value"] < 2 else 1)
    m = _QTC_VALUE.search(text or "")
    if m:
        value = float(m.group(1))
        return value * 1000 if value < 2 else value
    return None


def scp_statements(resource: Dict) -> List[str]:
    """SCP-ECG statements present (PTB-XL gives likelihood 0 for statements without one; 1–49 means uncertain)."""
    out = []
    for comp in resource.get("component", []):
        for c in (comp.get("code") or {}).get("coding", []):
            if c.get("system") == SCP_SYSTEM and c.get("code"):
                likelihood = (comp.get("valueQuantity") or {}).get("value", 100)
                if not (0 < float(likelihood) < 50):
                    out.append(c["code"].upper())
    return out


def af_in_text(text: str) -> bool:
    for m in _AF.finditer(text or ""):
        if not _AF_NEGATED.search(text[max(0, m.start() - 60):m.start()]):
            return True
    return False


def map_ecg(resource: Dict, ts: Optional[str], text: str) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
    """Events for one ECG: the ECG itself (prolonged_qtc when QTc ≥ 500 ms) and AF as a diagnosis."""
    from .clinical_ontology import EventType
    statements = scp_statements(resource)
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
    events = [(EventType.ECG.value, ts, details)]
    if {"AFIB", "AFLT"} & set(statements) or af_in_text(text):
        events.append((EventType.DIAGNOSIS.value, ts, {
            "diagnosis": "atrial fibrillation (on ECG)", "codes": ["I48"],
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
