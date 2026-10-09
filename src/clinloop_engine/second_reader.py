"""
second_reader.py — A model-based second reader for reports: what the rules may have missed goes to a person

The rule-based reader (radiology.py, fhir_ingest.py) reads what it has been taught. Blind evaluations
showed a long tail of wording it had not seen (docs/ACCURACY_EVALUATION.md). This module asks the
hospital's OWN language model (Ollama on the hospital network) to read the same report and list every
actionable item, each with an exact quote. Items the rules already track are dropped; each remaining
item opens R058: a clinician reviews the report and either acts (the follow-up closes it) or closes it
as not needed.

Safeguards:
  * OFF unless the hospital sets CLINLOOP_SECOND_READER=1.
  * On-premise only: the model server must resolve to a private address; identifiers are removed from
    the report before it is sent (scrub_identifiers, plus the patient's own names).
  * A fixed list of categories; every item must quote the report word for word, or it is discarded.
  * The model never opens or closes a real obligation and never reaches the patient: its flags only ask
    a person to look again, marked "needs human review" with the quote as evidence.
  * Each report is read once (re-read only if its text changes); recent reports only
    (CLINLOOP_SECOND_READER_LOOKBACK_DAYS, default 30); at most CLINLOOP_SECOND_READER_MAX reports per
    sync run (default 20).
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from .clinical_ontology import EventType
from .imaging_fhir import CLINLOOP_TAG_SYSTEM

logger = logging.getLogger("clinloop.second_reader")

IMAGING_RULES = {"R003", "R019", "R034", "R030", "R031", "R032", "R033", "R037", "R040", "R041", "R043", "R044"}
WORKUP_RULES = {"R036", "R018", "R020", "R046", "R038", "R039", "R042", "R045", "R009"}
# Acting on the flag within the review window usually means ORDERING the study: an order counts
_IMAGING = [EventType.IMAGING_ORDER, EventType.IMAGING_CT, EventType.IMAGING_MRI, EventType.IMAGING_ULTRASOUND,
            EventType.IMAGING_XRAY, EventType.IMAGING_PET, EventType.FOLLOWUP_CT]
_WORKUP = [EventType.BIOPSY_ORDER, EventType.BIOPSY_RESULT, EventType.BREAST_BIOPSY, EventType.SPECIALIST_REFERRAL,
           EventType.REFERRAL_VISIT, EventType.IMAGING_PET, EventType.ENDOSCOPIC_ULTRASOUND]

# category → (rules that already cover it, follow-ups that close the review, review deadline in days, wording)
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "imaging_followup": {"rules": IMAGING_RULES | {"R020", "R046"}, "followups": _IMAGING, "days": 7.0,
                         "en": "follow-up imaging", "ko": "추적 영상검사"},
    "biopsy_or_workup": {"rules": WORKUP_RULES, "followups": _WORKUP, "days": 7.0,
                         "en": "biopsy or work-up", "ko": "조직검사·정밀검사"},
    "specialist_referral": {"rules": WORKUP_RULES, "followups": [EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT],
                            "days": 7.0, "en": "specialist referral", "ko": "타과 의뢰"},
    "critical_finding": {"rules": {"R035"}, "followups": [EventType.CRITICAL_VALUE_NOTIFICATION], "days": 1.0,
                         "en": "critical finding to communicate", "ko": "위급 소견 통보"},
    "abnormal_pathology": {"rules": {"R009"}, "followups": [EventType.SPECIALIST_REFERRAL, EventType.REFERRAL_VISIT,
                                                           EventType.PATIENT_NOTIFICATION],
                           "days": 3.0, "en": "abnormal pathology", "ko": "이상 병리 결과"},
}
FOLLOWUP_TYPES = sorted({f for c in CATEGORIES.values() for f in c["followups"]}, key=lambda e: e.value)

SYSTEM_PROMPT = (
    "You are a careful radiologist and pathologist double-checking one report for a hospital follow-up safety "
    "system. You list only actions the report itself calls for, quoting it exactly. You never invent findings, "
    "never diagnose, and answer with JSON only.")
PROMPT = """Read the report below and list every item that needs action after this report:
- imaging_followup: the report recommends follow-up or further imaging (any modality, any interval), or contains a finding that standard guidelines follow with imaging (e.g. a solid lung nodule of 6 mm or more, an indeterminate adrenal/renal/pancreatic/thyroid lesion, an aortic aneurysm).
- biopsy_or_workup: the report recommends biopsy, tissue sampling, PET/CT or other work-up, or describes a finding suspicious for cancer.
- specialist_referral: the report recommends referral or consultation to a specialty.
- critical_finding: an acute, life-threatening finding that must be communicated now (e.g. intracranial haemorrhage, pulmonary embolism, pneumothorax, free air, aortic dissection, acute stroke).
- abnormal_pathology: a pathology diagnosis of malignancy, high-grade dysplasia or a precancerous lesion.
Do NOT list: findings that are negated ("no ..."), resolved, stable and called benign, or quoted from a prior study; advice that is only conditional ("if clinically indicated", "필요시"); items the report says are not needed; the exam name or clinical history.
For each item give "category" (one of the five above), "quote" (the exact words from the report, 4-25 words, copied character for character) and "reason" (under 15 words).
Answer with JSON only: {"items": [{"category": "...", "quote": "...", "reason": "..."}]}. If nothing needs action: {"items": []}.

REPORT:
"""


def enabled() -> bool:
    return os.environ.get("CLINLOOP_SECOND_READER", "").strip().lower() in ("1", "true", "yes", "on")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def local_model() -> Optional[Callable[[str, str], Dict[str, Any]]]:
    """The hospital's on-premise model, or None when it is not on a private address."""
    from .imaging_ai import _on_premise
    from .local_llm_engine import OLLAMA_BASE_URL, generate_clinical_text
    if not _on_premise(OLLAMA_BASE_URL):
        logger.error("Second reader: the model server (CLINLOOP_OLLAMA_URL) is not on a private address: not used")
        return None

    def call(prompt: str, system: str) -> Dict[str, Any]:
        return generate_clinical_text(prompt, temperature=0.0, max_tokens=600, system_prompt=system)
    return call


def read_report(text: str, model: Callable[[str, str], Dict[str, Any]],
                names: Optional[List[str]] = None) -> Dict[str, Any]:
    """The model's actionable items for one report, each verified against the report's own words."""
    from .document_reader import scrub_identifiers
    from .imaging_ai import _json_object
    clean = scrub_identifiers(text or "", names)[:6000]
    out = model(PROMPT + clean, SYSTEM_PROMPT)
    if out.get("error") or not out.get("text"):
        return {"available": False, "reason": out.get("error") or "no answer", "items": []}
    parsed = _json_object(out["text"])
    if not isinstance(parsed.get("items"), list):
        return {"available": False, "reason": "answer was not the expected JSON", "items": [], "model": out.get("model")}
    haystack, items, seen, dropped = _norm(clean), [], set(), 0
    for it in parsed["items"]:
        if not isinstance(it, dict) or it.get("category") not in CATEGORIES:
            dropped += 1
            continue
        quote = str(it.get("quote") or "").strip()
        if len(quote) < 4 or _norm(quote) not in haystack:
            dropped += 1                      # no exact quote, no flag: nothing invented reaches a clinician
            continue
        if it["category"] in seen:
            continue
        seen.add(it["category"])
        items.append({"category": it["category"], "quote": quote[:300], "reason": str(it.get("reason") or "")[:200]})
    return {"available": True, "model": out.get("model"), "items": items, "dropped": dropped}


def uncovered(items: List[Dict[str, Any]], opened: Set[str]) -> List[Dict[str, Any]]:
    """Items no rule already tracks for this report."""
    return [i for i in items if not (CATEGORIES[i["category"]]["rules"] & opened)]


def flag_resource(patient_id: str, report: Dict[str, Any], item: Dict[str, Any], model: str) -> Dict[str, Any]:
    """One untracked item as a FHIR Observation (preliminary: a suggestion for review, not a result)."""
    rid = report["id"]
    when = report.get("effectiveDateTime") or report.get("issued")
    return {
        "resourceType": "Observation",
        "id": "sr-" + hashlib.sha256(f"{patient_id}|{rid}|{item['category']}".encode()).hexdigest()[:40],
        "status": "preliminary",
        "meta": {"tag": [{"system": CLINLOOP_TAG_SYSTEM, "code": "second-reader"}]},
        "category": [{"text": "second-reader"}],
        "code": {"text": item["category"]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": when,
        "valueString": item["quote"],
        "note": [{"text": item.get("reason") or ""}],
        "derivedFrom": [{"reference": f"DiagnosticReport/{rid}"}],
        "device": {"display": f"second reader ({model or 'local model'})"},
    }


def _report_kind(r: Dict[str, Any]) -> Optional[str]:
    cats = " ".join(c.get("code", "") + " " + (c.get("text") or "") for cat in r.get("category", [])
                    for c in (cat.get("coding") or []) + [cat]).lower()
    if re.search(r"\brad\b|radiolog|imaging", cats):
        return "radiology"
    if re.search(r"\bpat\b|patholog|\bsp\b", cats):
        return "pathology"
    return None


def second_read_patient(store, patient_id: str, resources: List[Dict[str, Any]],
                        model: Optional[Callable[[str, str], Dict[str, Any]]] = None,
                        budget: Optional[Dict[str, int]] = None, now: Optional[datetime] = None,
                        lookback_days: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Second-read this patient's recent, unread reports. Returns the flags filed (FHIR Observations); they are
    also stored, so the next evaluation of the patient opens R058 for each.
    """
    from .fhir_ingest import bundle_to_events, patient_names
    from .loop_detector import ClinLoopDetector
    from .safety_clock import normalize_timestamp, utc_now
    now = now or utc_now()
    lookback = lookback_days if lookback_days is not None else int(os.environ.get("CLINLOOP_SECOND_READER_LOOKBACK_DAYS", "30"))
    reports = []
    for r in resources:
        if r.get("resourceType") != "DiagnosticReport" or r.get("status") not in ("final", "amended", "corrected"):
            continue
        kind, text = _report_kind(r), (r.get("conclusion") or "").strip()
        when = r.get("effectiveDateTime") or r.get("issued")
        if not kind or not text or not when:
            continue
        try:
            if normalize_timestamp(when) < now - timedelta(days=lookback):
                continue
        except (ValueError, TypeError):
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        done = store.second_read(f"{patient_id}|{r['id']}")
        if done and done["text_hash"] == digest:
            continue
        reports.append((r, kind, text, digest))
    if not reports:
        return []
    model = model or local_model()
    if model is None:
        return []
    # What the rules already opened, per report
    events, _ = bundle_to_events(resources)
    opened: Dict[str, Set[str]] = {}
    for d in ClinLoopDetector(evaluation_time=now).process_patient("second-reader", patient_id, events.get(patient_id, [])):
        m = re.match(r"DiagnosticReport/([^:]+):", str(d.trigger_event_id))
        if m:
            opened.setdefault(m.group(1), set()).add(d.rule_id)
    names = patient_names(resources, patient_id)
    flags: List[Dict[str, Any]] = []
    for r, kind, text, digest in reports:
        if budget is not None:
            if budget.get("left", 0) <= 0:
                break
            budget["left"] -= 1
        result = read_report(text, model, names)
        key = f"{patient_id}|{r['id']}"
        if not result["available"]:
            store.set_second_read(key, patient_id, digest, "failed", detail=result.get("reason", ""), now=now)
            continue
        new = uncovered(result["items"], opened.get(r["id"], set()))
        for item in new:
            res = flag_resource(patient_id, r, item, result.get("model") or "")
            store.add_external_resource(res, "second-reader", "second-reader", "system",
                                        summary=f"{CATEGORIES[item['category']]['en']}: \"{item['quote'][:120]}\"")
            flags.append(res)
        store.set_second_read(key, patient_id, digest, "read", items=len(result["items"]), flags=len(new),
                              model=result.get("model") or "", now=now)
    return flags


def map_flag(r: Dict[str, Any], ts: Optional[str]) -> List[tuple]:
    """A second-reader flag → the event that opens R058 (fhir_ingest calls this)."""
    category = (r.get("code") or {}).get("text") or ""
    spec = CATEGORIES.get(category)
    if not spec:
        return []
    quote = r.get("valueString") or ""
    report_ref = next((x.get("reference") for x in r.get("derivedFrom", []) if "DiagnosticReport" in str(x.get("reference"))), None)
    return [(EventType.SECOND_READER_FLAG.value, ts, {
        "condition": "second_reader_flag", "category": category, "report_ref": report_ref,
        "model": (r.get("device") or {}).get("display"),
        "rule_deadline_days": {"R058": spec["days"]},
        "followup_types": {"R058": [f.value for f in spec["followups"]]},
        "review_notes": {"R058": (f"The model-based second reader found {spec['en']} that no rule tracked. A person reads "
                                  f"the report and acts, or closes this as not needed. The model's reason: "
                                  f"{((r.get('note') or [{}])[0].get('text') or '').strip() or 'not given'}")},
        "evidence_span": f"\"{quote}\"",
        "mapping": [f"Observation(second reader)→second_reader_flag: {category}"],
    })]


def status(store) -> Dict[str, Any]:
    from .imaging_ai import _on_premise
    from .local_llm_engine import OLLAMA_BASE_URL
    return {"enabled": enabled(), "model_server": OLLAMA_BASE_URL, "model_server_on_premise": _on_premise(OLLAMA_BASE_URL),
            "categories": {k: {"en": v["en"], "ko": v["ko"], "review_days": v["days"]} for k, v in CATEGORIES.items()},
            **store.second_read_counts()}
