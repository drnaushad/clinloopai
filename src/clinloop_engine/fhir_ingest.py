"""
fhir_ingest.py — HL7 FHIR R4 → ClinLoop event adapter

Converts a FHIR R4 Bundle (or a list of resources) from a hospital's
read-only FHIR endpoint into the per-patient event lists the detection
engine consumes.

Design principles:
  * Status is preserved, never assumed. A booked Appointment becomes a
    "scheduled" event, which does NOT close a loop; only fulfilled /
    completed resources do ("click ≠ closure").
  * Every mapping decision is recorded on the event (`details["mapping"]`
    and, for text extraction, `details["evidence_span"]`) so a clinician can
    audit why an event was classified the way it was.
  * Text extraction is deliberately conservative and rule-based. When a
    hospital codes a concept differently, it should set the explicit
    ClinLoop extension (CLINLOOP_EVENT_TYPE_URL) rather than rely on text.

Supported resources: Observation, DiagnosticReport, ServiceRequest,
Appointment, Communication, Encounter, MedicationRequest, Procedure, Condition.
"""

import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .clinical_ontology import (
    EventType, is_fulfilling_status,
)
from .ai_review import apply_ai_review
from .imaging_fhir import (
    CLINLOOP_TAG_SYSTEM, DEFAULT_AI_THRESHOLD, DICOM_MODALITY, OCR_CONFIDENCE_URL, REGULATORY_URL,
    ai_finding_key, dicom_regions, norm_ref, regulatory_unverified, study_uid_from,
)
from .motifs import ANTICOAGULANT_NAMES, apply_patterns
from .note_reader import analyte_of, find_plans, plan_label, specialty_of, MODALITY_EVENTS
from .radiology import _CHEST_CT, _LIVER, decide_obligations, map_radiology_report
from .report_text import affirmed as _affirmed, first_affirmed as _first_affirmed
from .report_text import not_negated as _not_negated, span as _span
from .safety_clock import normalize_timestamp

# Explicit override: any resource may carry
#   {"url": CLINLOOP_EVENT_TYPE_URL, "valueCode": "<EventType value>"}
CLINLOOP_EVENT_TYPE_URL = "https://clinloopai.app/fhir/StructureDefinition/event-type"

INTERPRETATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"

# v3 ObservationInterpretation → ClinLoop flag
INTERPRETATION_FLAGS = {
    "HH": "CRITICAL", "LL": "CRITICAL", "AA": "CRITICAL",
    "H": "HIGH", "HU": "HIGH", "L": "LOW", "LU": "LOW",
    "A": "ABNORMAL", "POS": "ABNORMAL", "DET": "ABNORMAL",
    "N": "NORMAL", "NEG": "NORMAL", "ND": "NORMAL",
}

# LOINC codes used for condition inference. Verify against the local
# laboratory's LOINC mapping before deployment.
LOINC_FIT = {"29771-3", "57905-2", "56490-6", "56491-4"}
LOINC_TSH = {"3016-3"}
LOINC_HBA1C = {"4548-4", "17856-6"}
LOINC_PSA = {"2857-1"}
LOINC_INR = {"6301-6", "34714-6"}
LOINC_HCV_AB = {"16128-1", "13955-0"}
LOINC_HCV_RNA = {"11011-4", "20416-4", "38180-6"}
LOINC_BP = {"85354-9", "55284-4", "8480-6", "8462-4"}

# HCC risk: chronic hepatitis B and cirrhosis (ICD-10 / text). Verify locally.
HCC_RISK_ICD10 = ("B18.0", "B18.1", "K70.3", "K74.3", "K74.4", "K74.5", "K74.6")
HCC_RISK_TEXT = re.compile(r"chronic hepatitis b|hepatitis b, chronic|\bchb\b|cirrhosis|만성\s*b형\s*간염|간경변", re.I)

# Context for radiology decisions (Fleischner exclusions, ACR adrenal work-up)
# Malignancy: ICD-10 C00–C97 except C44 (non-melanoma skin), or personal history Z85
_MALIGNANCY_TEXT = re.compile(r"cancer|carcinoma|malignan\w*|lymphoma|leuk(?:a)?emia|myeloma|melanoma|sarcoma|암\b|암$", re.I)
_IMMUNO_ICD10 = ("B20", "B21", "B22", "B23", "B24", "D80", "D81", "D82", "D83", "D84", "Z94", "Z79.6")
_IMMUNO_TEXT = re.compile(r"\bhiv\b|transplant|immunodeficien\w*|immunosuppress\w*|이식|면역결핍", re.I)

# Smoking status (LOINC 72166-2) → current / former / never (SNOMED CT)
LOINC_SMOKING = {"72166-2"}
SMOKING_SNOMED = {
    "449868002": "current", "428041000124106": "current", "77176002": "current",
    "428071000124103": "current", "428061000124105": "current", "65568007": "current",
    "8517006": "former", "266919005": "never",
}

# Monitoring labs that satisfy R010 for a given drug (by LOINC code)
DRUG_MONITORING_LOINC = {
    "levothyroxine": {"3016-3"},                       # TSH
    "lithium": {"14334-7"},                            # serum lithium
    "metformin": {"2160-0", "33914-3", "62238-1"},     # creatinine / eGFR
    "lisinopril": {"2823-3", "2160-0"},                # potassium, creatinine
    "methotrexate": {"6690-2", "1742-6", "718-7"},     # WBC, ALT, haemoglobin
}
ANTICOAGULANTS = {"warfarin", "coumadin", "와파린"}

# Thresholds (document local overrides with the lab director)
PSA_THRESHOLD_NG_ML = 4.0
HBA1C_UNCONTROLLED_PCT = 9.0

# FHIR status → ClinLoop status. Statuses not listed are kept lower-cased.
STATUS_MAP = {
    # results / reports
    "final": "completed", "amended": "completed", "corrected": "completed",
    "appended": "completed", "preliminary": "pending", "registered": "pending",
    "partial": "pending",
    # appointments
    "fulfilled": "completed", "arrived": "completed", "checked-in": "completed",
    "booked": "scheduled", "pending": "scheduled", "proposed": "scheduled",
    "waitlist": "scheduled", "noshow": "no_show",
    # requests / procedures / communications / encounters
    "active": "completed", "on-hold": "pending", "in-progress": "pending",
    "preparation": "planned", "finished": "completed",
    # imaging studies
    "available": "completed",
}


# ── Small FHIR helpers ───────────────────────────────────────────────────────

def _codings(concept: Optional[Dict]) -> List[Dict]:
    return (concept or {}).get("coding", []) or []


def _concept_text(concept: Optional[Dict]) -> str:
    if not concept:
        return ""
    parts = [concept.get("text", "")] + [c.get("display", "") for c in _codings(concept)]
    return " ".join(p for p in parts if p)


def _codes(concept: Optional[Dict]) -> set:
    return {c.get("code") for c in _codings(concept) if c.get("code")}


def _all_category_text(resource: Dict) -> str:
    cats = resource.get("category", [])
    if isinstance(cats, dict):
        cats = [cats]
    return " ".join(_concept_text(c) + " " + " ".join(_codes(c)) for c in cats).lower()


def _ref_id(reference: Optional[Dict], resource_type: str = "Patient") -> Optional[str]:
    ref = (reference or {}).get("reference", "")
    prefix = f"{resource_type}/"
    if ref.startswith(prefix):
        return ref[len(prefix):]
    return None


def _patient_id(resource: Dict) -> Optional[str]:
    for key in ("subject", "patient", "for"):
        pid = _ref_id(resource.get(key))
        if pid:
            return pid
    for participant in resource.get("participant", []):     # Appointment
        pid = _ref_id(participant.get("actor"))
        if pid:
            return pid
    return None


def _first(*values):
    for v in values:
        if v:
            return v
    return None


def _explicit_event_type(resource: Dict) -> Optional[str]:
    for ext in resource.get("extension", []):
        if ext.get("url") == CLINLOOP_EVENT_TYPE_URL and ext.get("valueCode"):
            return ext["valueCode"]
    return None


def _status(resource: Dict) -> str:
    raw = str(resource.get("status", "completed")).lower()
    return STATUS_MAP.get(raw, raw)


def _flag_from_interpretation(resource: Dict) -> Optional[str]:
    for interp in resource.get("interpretation", []):
        for code in _codes(interp):
            if code in INTERPRETATION_FLAGS:
                return INTERPRETATION_FLAGS[code]
    return None


# ── Resource mappers ─────────────────────────────────────────────────────────

def _map_observation(r: Dict) -> List[Tuple[str, str, Dict]]:
    """Returns [(event_type, timestamp, details)]."""
    ts = _first(r.get("effectiveDateTime"), (r.get("effectivePeriod") or {}).get("end"), r.get("issued"))
    code_text = _concept_text(r.get("code")).lower()
    codes = _codes(r.get("code"))

    # Imaging-AI output (approved product or ClinLoop's model runner): a second reader, not a lab result
    if _is_ai_observation(r):
        return _map_ai_observation(r, ts)

    # Smoking status is context for lung-nodule risk, not a lab result
    if codes & LOINC_SMOKING or "smoking status" in code_text or "tobacco smoking" in code_text:
        value_codes = _codes(r.get("valueCodeableConcept"))
        value_text = _concept_text(r.get("valueCodeableConcept")).lower()
        status = next((SMOKING_SNOMED[c] for c in value_codes if c in SMOKING_SNOMED), None)
        if status is None:
            status = ("never" if re.search(r"never|비흡연", value_text) else
                      "former" if re.search(r"former|ex-?smoker|과거", value_text) else
                      "current" if re.search(r"current|smoker|흡연", value_text) else None)
        if status is None:
            return []
        return [(EventType.RISK_FACTOR.value, ts, {"smoking": status, "mapping": [f"Observation(smoking status)→risk_factor: {status}"]})]

    # Vital signs are not lab results: a high BP reading must not raise
    # "abnormal lab" alerts. A recorded BP is evidence of a BP check.
    if "vital-signs" in _all_category_text(r) or codes & LOINC_BP or "blood pressure" in code_text:
        if codes & LOINC_BP or "blood pressure" in code_text or "혈압" in code_text:
            return [(EventType.BP_CHECK.value, ts, {"mapping": ["Observation(blood pressure)→bp_check"]})]
        return []
    details: Dict[str, Any] = {"test": _concept_text(r.get("code")) or None, "loinc": sorted(codes)}
    analyte = analyte_of(_concept_text(r.get("code")), sorted(codes))
    if analyte:
        details["analyte"] = analyte          # matches a note's "repeat potassium" plan (R048)

    value = None
    if "valueQuantity" in r:
        value = (r["valueQuantity"] or {}).get("value")
        details["value"] = value
        details["unit"] = (r["valueQuantity"] or {}).get("unit")
    value_text = _concept_text(r.get("valueCodeableConcept")) or str(r.get("valueString", ""))
    if value_text:
        details["result"] = value_text

    flag = _flag_from_interpretation(r)
    if flag:
        details["flag"] = flag
    mapping = ["Observation→lab_result"]

    is_culture = "culture" in code_text or "배양" in code_text or "microbiology" in _all_category_text(r)
    if is_culture:
        positive = flag in ("ABNORMAL", "CRITICAL") or bool(
            re.search(r"\b(growth|positive|isolated)\b", value_text, re.I)
            and not re.search(r"\bno growth\b", value_text, re.I))
        details["result"] = "positive" if positive else "negative"
        if "blood" in code_text:
            details["culture_type"] = "blood"
        return [(EventType.CULTURE_RESULT.value, ts, {**details, "mapping": ["Observation(culture)→culture_result"]})]

    if codes & LOINC_FIT or re.search(r"\b(fit|fecal immunochemical|immunochemical.*stool|분변잠혈)\b", code_text):
        details["test"] = "FIT"
        details.pop("analyte", None)
        positive = flag in ("ABNORMAL", "CRITICAL", "HIGH") or bool(
            re.search(r"\b(positive|detected|양성)\b", value_text, re.I)
            and not re.search(r"\bnot detected\b", value_text, re.I))
        details["result"] = "positive" if positive else "negative"
        # The colonoscopy rule (R017) is the obligation; a generic
        # "abnormal result" flag would add duplicate alerts for one finding.
        details.pop("flag", None)
        mapping.append("FIT code/text")
    elif codes & LOINC_INR:
        # INR is judged against the therapeutic target (2–3 on warfarin), not
        # the reference range, so only a critical value raises an alert.
        if flag != "CRITICAL":
            details.pop("flag", None)
        mapping.append("INR: reference-range flag ignored unless critical")
    elif codes & LOINC_HCV_AB or re.search(r"\b(hcv|hepatitis c)\b.*\b(ab|antibod\w*)\b", code_text):
        reactive = flag in ("ABNORMAL", "HIGH", "CRITICAL") or bool(
            re.search(r"\b(positive|reactive|detected|양성)\b", value_text, re.I)
            and not re.search(r"\b(non-?reactive|not detected)\b", value_text, re.I))
        details.pop("flag", None)   # R026 is the obligation; avoid generic duplicates
        if reactive:
            details["condition"] = "hcv_antibody_positive"
            mapping.append("HCV antibody reactive→hcv_antibody_positive")
    elif codes & LOINC_TSH and flag in ("HIGH", "LOW", "ABNORMAL", "CRITICAL"):
        details["condition"] = "abnormal_thyroid"
        mapping.append("TSH out of range→abnormal_thyroid")
    elif codes & LOINC_HBA1C and isinstance(value, (int, float)) and value >= HBA1C_UNCONTROLLED_PCT:
        details["condition"] = "uncontrolled_hba1c"
        mapping.append(f"HbA1c ≥{HBA1C_UNCONTROLLED_PCT}%→uncontrolled_hba1c")
    elif codes & LOINC_PSA and isinstance(value, (int, float)) and value > PSA_THRESHOLD_NG_ML:
        details["condition"] = "elevated_psa"
        mapping.append(f"PSA >{PSA_THRESHOLD_NG_ML}→elevated_psa")
    elif re.search(r"cervical|pap\b|자궁경부", code_text):
        m = re.search(r"\b(HSIL|LSIL|ASC-H|ASC-US|AGC|AIS|squamous cell carcinoma)\b", value_text, re.I)
        if m:
            details["condition"] = "abnormal_cervical_cytology"
            details["evidence_span"] = value_text
            mapping.append(f"cytology '{m.group(1)}'→abnormal_cervical_cytology")

    details["mapping"] = mapping
    events = [(EventType.LAB_RESULT.value, ts, details)]

    # Results that themselves satisfy a pending obligation
    if codes & LOINC_HCV_RNA or re.search(r"\b(hcv|hepatitis c)\b.*\brna\b", code_text):
        events.append((EventType.HCV_RNA_TEST.value, ts, {"mapping": ["HCV RNA→hcv_rna_test"]}))
    if re.search(r"glucose tolerance|\bogtt\b|75\s*g|포도당\s*부하", code_text):
        events.append((EventType.POSTPARTUM_GLUCOSE_TEST.value, ts, {"mapping": ["OGTT→postpartum_glucose_test"]}))
    if codes & LOINC_HBA1C:
        events.append((EventType.HBA1C_RECHECK.value, ts, {"loinc": sorted(codes), "mapping": ["HbA1c→hba1c_recheck"]}))
    if codes & LOINC_INR:
        events.append((EventType.INR_RECHECK.value, ts, {"loinc": sorted(codes), "mapping": ["INR→inr_recheck"]}))
    return events


_MALIGNANT = re.compile(r"(adenocarcinoma|carcinoma|malignan\w*|high-grade dysplasia|melanoma|lymphoma|sarcoma|암|"
                        # High-grade cervical cytology/histology: colposcopy and treatment are due (ASCCP 2019)
                        r"\bHSIL\b|high[- ]grade squamous intraepithelial lesion|\bASC-H\b|\bAGC\b|"
                        r"atypical glandular cells|\bCIN\s*(?:2|3|II|III)\b|"
                        # High-risk breast lesions: surgical excision is usually advised
                        r"atypical (?:ductal|lobular) hyperplasia|\bADH\b|\bALH\b|lobular (?:carcinoma|neoplasia) in situ|\bLCIS\b|"
                        # Precancer of the endometrium: gynecologic oncology referral
                        r"atypical endometrial hyperplasia|endometrioid intraepithelial neoplasia|\bEIN\b)",
                        re.I)


def _map_diagnostic_report(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("effectiveDateTime"), (r.get("effectivePeriod") or {}).get("end"), r.get("issued"))
    category = _all_category_text(r)
    code_text = _concept_text(r.get("code"))
    conclusion = " ".join(filter(None, [r.get("conclusion", ""),
                                        " ".join(_concept_text(c) for c in r.get("conclusionCode", []))]))
    details: Dict[str, Any] = {"report": code_text or None, "conclusion": conclusion or None}
    studies = [norm_ref(s.get("reference")) for s in r.get("imagingStudy", []) if s.get("reference")]
    if studies:
        details["imaging_studies"] = studies
    tags = {t.get("code") for t in (r.get("meta") or {}).get("tag", []) if t.get("system") == CLINLOOP_TAG_SYSTEM}
    if "outside-report" in tags:
        confidence = next((x.get("valueDecimal") for x in r.get("extension", []) if x.get("url") == OCR_CONFIDENCE_URL), None)
        method = "OCR" if "ocr" in tags else "PDF text"
        details["outside_report"] = {"method": method, "confidence": confidence,
                                     "confirmed": "human-confirmed" in tags}
    if "outside-report" in tags and "human-confirmed" not in tags:
        details["review_note_all"] = (
            f"Read from an outside report ({method}"
            + (f", recognition confidence {confidence:.0f}%" if isinstance(confidence, (int, float)) else "")
            + "): check the text and the date against the original document."
            + (" The report date was not found; the upload date was used." if "date-unknown" in tags else ""))

    if "rad" in category or "imaging" in category or "radiology" in category:
        return map_radiology_report(ts, code_text, conclusion, details)

    if "pat" in category or "pathology" in category or "sp" in category.split():
        mapping = ["DiagnosticReport(PAT)→pathology_result"]
        # Read the diagnosis, not the clinical history ("r/o melanoma vs SK" is the question, not the answer)
        dx = re.search(r"(?:^|\n)\s*(?:final\s+)?(?:pathologic(?:al)?\s+)?diagnos[ie]s\s*[:：]|(?:^|\n)\s*(?:병리\s*)?진단\s*[:：]",
                       conclusion, re.I)
        m = _first_affirmed(_MALIGNANT, conclusion[dx.end():] if dx else conclusion)
        if m:
            details.update(condition="abnormal", evidence_span=_span(conclusion, m))
            mapping.append(f"'{m.group(1)}'→abnormal")
        details["mapping"] = mapping
        return [(EventType.PATHOLOGY_RESULT.value, ts, details)]

    return []  # lab DiagnosticReports: the referenced Observations carry the data


def _is_ai_observation(r: Dict) -> bool:
    tags = {t.get("code") for t in (r.get("meta") or {}).get("tag", []) if t.get("system") == CLINLOOP_TAG_SYSTEM}
    if "imaging-ai" in tags:
        return True
    return bool(r.get("device")) and "imaging" in _all_category_text(r)


def _ai_threshold(key: Optional[str]) -> float:
    """Per-finding operating point: CLINLOOP_AI_THRESHOLD_<KEY>, else CLINLOOP_AI_THRESHOLD, else 0.5."""
    for name in (f"CLINLOOP_AI_THRESHOLD_{(key or '').upper()}", "CLINLOOP_AI_THRESHOLD"):
        try:
            return float(os.environ[name])
        except (KeyError, ValueError):
            continue
    return DEFAULT_AI_THRESHOLD


def _map_ai_observation(r: Dict, ts: Optional[str]) -> List[Tuple[str, str, Dict]]:
    label = _concept_text(r.get("code"))
    product = (r.get("device") or {}).get("display") or "imaging AI"
    regulatory = next((x.get("valueString") for x in r.get("extension", []) if x.get("url") == REGULATORY_URL), "")
    body = _concept_text(r.get("bodySite"))
    regions = dicom_regions("", body) if body else []
    key = ai_finding_key(label, regions)
    score = (r.get("valueQuantity") or {}).get("value")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    if score is not None and (r.get("valueQuantity") or {}).get("unit") in ("%", "percent"):
        score = score / 100.0
    interp = _flag_from_interpretation(r)
    codes = {c for i in r.get("interpretation", []) for c in _codes(i)}
    if codes & {"POS", "A", "AA", "H", "DET"} or interp in ("ABNORMAL", "HIGH", "CRITICAL"):
        positive, basis = True, "vendor flagged positive"
    elif codes & {"NEG", "N", "ND"}:
        positive, basis = False, "vendor flagged negative"
    elif score is not None and score > 1:
        positive, basis = False, f"score {score:g} on an unknown scale: set a vendor flag or label map"
    elif score is not None:
        positive, basis = score >= _ai_threshold(key), f"score {score:g} vs threshold {_ai_threshold(key):g}"
    else:
        positive, basis = False, "no score or flag"
    links = r.get("derivedFrom", [])
    study_ref = next((norm_ref(x.get("reference")) for x in links if "ImagingStudy" in str(x.get("reference"))), None)
    study_uid = next((study_uid_from((x.get("identifier") or {}).get("value")) for x in links
                      if "dicom" in str((x.get("identifier") or {}).get("system", "")).lower()
                      or str((x.get("identifier") or {}).get("value", "")).startswith("urn:oid:")), None)
    details = {"finding_label": label, "finding_key": key, "score": score, "positive": positive,
               "product": product, "regulatory": regulatory or "not stated",
               "research_use": regulatory_unverified(regulatory), "study_ref": study_ref, "study_uid": study_uid,
               "study_time": ts,
               "regions": regions,
               "mapping": [f"Observation(imaging AI: {product})→ai_finding '{label}'"
                           f"{' → ' + key if key else ' (label not mapped)'}: {'positive' if positive else 'negative'} ({basis})"]}
    return [(EventType.AI_FINDING.value, ts, details)]


def _map_imaging_study(r: Dict) -> List[Tuple[str, str, Dict]]:
    """ImagingStudy (from the PACS or a FHIR server): the study was performed, of this modality and body region."""
    ts = r.get("started")
    modalities = {c for m in r.get("modality", []) for c in [m.get("code")] if c}
    modalities |= {(s.get("modality") or {}).get("code") for s in r.get("series", []) if (s.get("modality") or {}).get("code")}
    body = [_concept_text(s.get("bodySite")) or (s.get("bodySite") or {}).get("display") or "" for s in r.get("series", [])]
    descriptions = [r.get("description") or ""] + [s.get("description") or "" for s in r.get("series", [])] \
        + [_concept_text(c) for c in r.get("procedureCode", [])]
    regions = sorted(set().union(*[set(dicom_regions(b, *descriptions)) for b in (body or [""])]))
    details = {"study": " / ".join(filter(None, descriptions)) or None, "modalities": sorted(modalities),
               "body_regions": regions,
               "study_uid": study_uid_from(next((i.get("value") for i in r.get("identifier", [])
                                                 if "dicom" in str(i.get("system"))), None)),
               "study_ref": f"ImagingStudy/{r.get('id')}",
               "mapping": [f"ImagingStudy({', '.join(sorted(modalities)) or '?'})"
                           f" [{', '.join(regions) or 'region unknown'}]"]}
    events: List[Tuple[str, str, Dict]] = []
    etype_for = {"ct": EventType.IMAGING_CT, "mri": EventType.IMAGING_MRI, "ultrasound": EventType.IMAGING_ULTRASOUND,
                 "xray": EventType.IMAGING_XRAY, "pet": EventType.IMAGING_PET, "mammography": EventType.IMAGING_XRAY}
    if "MG" in {m.upper() for m in modalities} and "breast" not in regions:
        regions = sorted(set(regions) | {"breast"})       # a mammogram is breast imaging whatever the body part says
        details["body_regions"] = regions
    for m in sorted(modalities):
        kind = DICOM_MODALITY.get(m.upper())
        if kind in etype_for:
            etype = etype_for[kind].value
            events.append((etype, ts, {**details, "mapping": details["mapping"] + [f"→{etype}"]}))
            if kind in ("ct", "pet") and "chest" in regions:
                events.append((EventType.FOLLOWUP_CT.value, ts, {**details, "mapping": details["mapping"] + ["chest CT→followup_ct"]}))
            if kind == "ultrasound" and re.search(r"echo|cardiac|heart|\btte\b|\btee\b|심장|심초음파",
                                                  " ".join(descriptions + body), re.I):
                events.append((EventType.ECHOCARDIOGRAM.value, ts, {**details, "mapping": details["mapping"] + ["→echocardiogram"]}))
            if kind in ("ct", "mri", "ultrasound") and ("liver" in regions or _LIVER.search(" ".join(descriptions))):
                events.append((EventType.LIVER_IMAGING.value, ts, {**details, "mapping": details["mapping"] + ["→liver_imaging"]}))
    return events


def _map_service_request(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("authoredOn"), (r.get("occurrencePeriod") or {}).get("start"))
    text = (_concept_text(r.get("code")) + " " + _all_category_text(r)).lower()
    details = {"order": _concept_text(r.get("code")) or None}
    if "colposcopy" in text or "질확대경" in text:
        etype = EventType.COLPOSCOPY_REFERRAL.value
    elif _EUS.search(text):
        etype = EventType.ENDOSCOPIC_ULTRASOUND.value
    elif ("biopsy" in text or "aspiration" in text or re.search(r"\bfna\b", text)
          or "조직검사" in text or "세침" in text):
        etype = EventType.BIOPSY_ORDER.value
    elif "referral" in text or "3457005" in text or "consult" in text or "의뢰" in text or "협진" in text:
        etype = EventType.SPECIALIST_REFERRAL.value
    elif "imaging" in text or "363679005" in text or re.search(r"\b(ct|mri|x-ray|ultrasound)\b", text):
        etype = EventType.IMAGING_ORDER.value
    else:
        etype = EventType.LAB_ORDER.value
    if etype == EventType.BIOPSY_ORDER.value:
        sites = biopsy_regions(_concept_text(r.get("code")) + " " + " ".join(_concept_text(b) for b in r.get("bodySite", [])))
        if sites:
            details["body_regions"] = sites
    if etype == EventType.SPECIALIST_REFERRAL.value:
        spec = specialty_of(_concept_text(r.get("code")) + " " + " ".join(
            _concept_text(c) for c in r.get("performerType", []) if isinstance(r.get("performerType"), list))
            + " " + _concept_text(r.get("performerType") if isinstance(r.get("performerType"), dict) else None))
        if spec:
            details["specialty"] = spec
    details["mapping"] = [f"ServiceRequest→{etype}"]
    return [(etype, ts, details)]


def _map_appointment(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = r.get("start")
    text = (_concept_text(r.get("appointmentType")) + " "
            + " ".join(_concept_text(s) for s in r.get("serviceType", [])) + " "
            + " ".join(_concept_text(s) for s in r.get("specialty", [])) + " "
            + str(r.get("description", ""))).lower()
    if "colposcopy" in text or "질확대경" in text:
        return [(EventType.COLPOSCOPY_VISIT.value, ts, {"mapping": ["Appointment(colposcopy)→colposcopy_visit"]})]
    if _CHEST_CT.search(text):
        return [(EventType.FOLLOWUP_CT.value, ts, {"body_regions": ["chest", "lung"],
                                                    "mapping": ["Appointment(chest CT)→followup_ct"]})]
    if "colonoscopy" in text or "대장내시경" in text:
        return [(EventType.COLONOSCOPY.value, ts, {"mapping": ["Appointment(colonoscopy)→colonoscopy"]})]
    if _PSYCH.search(text):
        return [(EventType.MENTAL_HEALTH_FOLLOWUP.value, ts, {"mapping": ["Appointment(mental health)→mental_health_followup"]}),
                (EventType.FOLLOWUP_APPOINTMENT.value, ts, {"mapping": ["Appointment→followup_appointment"]})]
    if "blood pressure" in text or "혈압" in text:
        return [(EventType.BP_CHECK.value, ts, {"mapping": ["Appointment(BP check)→bp_check"]})]
    spec = specialty_of(text)
    extra = {"specialty": spec} if spec else {}
    events = [(EventType.FOLLOWUP_APPOINTMENT.value, ts, {**extra, "mapping": ["Appointment→followup_appointment"]})]
    if any(_ref_id(b, "ServiceRequest") for b in r.get("basedOn", [])):
        events.append((EventType.REFERRAL_VISIT.value, ts, {**extra, "mapping": ["Appointment.basedOn referral→referral_visit"]}))
    return events


def _map_communication(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("sent"), r.get("received"))
    recipients = [x.get("reference", "") for x in r.get("recipient", [])]
    text = (_all_category_text(r) + " " + _concept_text(r.get("topic")) + " "
            + " ".join(_concept_text(c) for c in r.get("reasonCode", []))).lower()
    if "critical" in text or "panic" in text:
        etype = EventType.CRITICAL_VALUE_NOTIFICATION.value
    elif any(ref.startswith("Patient/") or ref.startswith("RelatedPerson/") for ref in recipients):
        etype = EventType.PATIENT_NOTIFICATION.value
    elif "callback" in text:
        etype = EventType.CALLBACK.value
    else:
        etype = EventType.PROVIDER_REVIEW.value
    medium = [_concept_text(m) for m in r.get("medium", [])]
    return [(etype, ts, {"method": ", ".join(medium) or None, "mapping": [f"Communication→{etype}"]})]


_EUS = re.compile(r"endoscopic ultrasound|\beus\b|내시경\s*초음파", re.I)
_PSYCH = re.compile(r"psychiatr|mental health|behavioral health|정신", re.I)


def _map_encounter(r: Dict) -> List[Tuple[str, str, Dict]]:
    period = r.get("period") or {}
    enc_class = str((r.get("class") or {}).get("code", "")).upper()
    # Discharge diagnosis: reasonCode, or the display of the first diagnosis reference
    dx_text = " ".join(_concept_text(c) for c in r.get("reasonCode", []))
    if not dx_text:
        dx_text = " ".join((d.get("condition") or {}).get("display", "") for d in r.get("diagnosis", []))
    primary_dx = re.sub(r"[^a-z0-9]+", "_", dx_text.lower()).strip("_")
    service = " ".join([_concept_text(r.get("serviceType"))]
                       + [_concept_text(t) for t in r.get("type", [])]).lower()
    if enc_class in ("IMP", "ACUTE", "NONAC", "EMER", "OBSENC") and period.get("end"):
        details = {"primary_diagnosis": primary_dx, "encounter_class": enc_class,
                   "mapping": [f"Encounter({enc_class}) end→discharge"]}
        if enc_class in ("IMP", "ACUTE") and _PSYCH.search(service):
            details["psychiatric_admission"] = True
        if "severe" in primary_dx and re.search(r"preeclampsia|eclampsia|hypertens", primary_dx):
            details["severe_hypertension"] = True
        return [(EventType.DISCHARGE.value, period["end"], details)]
    if enc_class == "AMB" and str(r.get("status", "")).lower() == "finished":
        when = _first(period.get("start"), period.get("end"))
        events = [(EventType.FOLLOWUP_APPOINTMENT.value, when,
                   {"mapping": ["Encounter(AMB) finished→followup_appointment"]})]
        if _PSYCH.search(service):
            events.append((EventType.MENTAL_HEALTH_FOLLOWUP.value, when,
                           {"mapping": ["Encounter(AMB, mental health)→mental_health_followup"]}))
        return events
    return []


def _map_condition(r: Dict) -> List[Tuple[str, str, Dict]]:
    """Active problem-list entries: all as context; HCC risk carries an obligation, cancer and immunocompromise inform radiology."""
    clinical = _codes(r.get("clinicalStatus")) or {"active"}
    if not clinical & {"active", "recurrence", "relapse"}:
        return []
    verification = next(iter(_codes(r.get("verificationStatus"))), None)
    if verification in ("refuted", "entered-in-error"):
        return []
    text = _concept_text(r.get("code"))
    codes = _codes(r.get("code"))
    details: Dict[str, Any] = {"diagnosis": text, "codes": sorted(codes)}
    if verification:
        details["verification"] = verification
    mapping: List[str] = []
    if any(c.startswith(HCC_RISK_ICD10) for c in codes) or HCC_RISK_TEXT.search(text):
        details["hcc_risk"] = True
        mapping.append("Condition(HBV/cirrhosis)→diagnosis, hcc_risk")
    malignant = any(re.match(r"^C(?:[0-8]\d|9[0-7])", c) and not c.startswith("C44") for c in codes) \
        or any(c.startswith("Z85") for c in codes) or bool(_MALIGNANCY_TEXT.search(text))
    if malignant:
        details["malignancy"] = True
        mapping.append("Condition(malignancy)→diagnosis, context for radiology decisions")
    if any(c.startswith(_IMMUNO_ICD10) for c in codes) or _IMMUNO_TEXT.search(text):
        details["immunocompromised"] = True
        mapping.append("Condition(immunocompromise)→diagnosis, context for radiology decisions")
    if not mapping:      # every active diagnosis is context (patient graph); only the flags above carry obligations
        mapping.append("Condition→diagnosis (context, no obligation of its own)")
    details["mapping"] = mapping
    ts = _first(r.get("onsetDateTime"), r.get("recordedDate"))
    return [(EventType.DIAGNOSIS.value, ts, details)]


def _drug_name(r: Dict) -> str:
    concept = r.get("medicationCodeableConcept")
    return _concept_text(concept).lower()


def _map_medication_request(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = r.get("authoredOn")
    name = _drug_name(r)
    details: Dict[str, Any] = {"medication": name or None}
    if ANTICOAGULANT_NAMES.search(name or ""):
        details["anticoagulant"] = True       # closes R054 (AF anticoagulation decision)
    if any(a in name for a in ANTICOAGULANTS):
        details.update(drug="warfarin", condition="anticoagulant_dose_change")
    else:
        for drug in DRUG_MONITORING_LOINC:
            if drug in name:
                details.update(drug=drug, condition="requires_monitoring")
                break
    details["mapping"] = [f"MedicationRequest→medication_change ({details.get('condition', 'no rule')})"]
    return [(EventType.MEDICATION_CHANGE.value, ts, details)]


_LUNG_SITE = re.compile(r"\blung|pulmonary|\blobe\b|\b(?:RUL|RML|RLL|LUL|LLL)\b|lingula|bronch\w*|transthoracic|"
                        r"\bEBUS\b|폐|[우좌][상중하]엽|기관지", re.I)


_OTHER_BIOPSY_SITES = [(site, re.compile(rx, re.I)) for site, rx in (
    ("colon", r"\bcolon|colonic|rect(?:um|al)|sigmoid|대장|직장"), ("stomach", r"stomach|gastric|위\s*조직|위내시경"),
    ("esophagus", r"esophag\w*|oesophag\w*|식도"), ("skin", r"\bskin\b|punch|피부"),
    ("cervix", r"cervi(?:x|cal)|자궁경부"), ("uterus", r"endometri\w*|자궁내막"), ("prostate", r"prostat\w*|전립선"))]


def biopsy_regions(text: str) -> List[str]:
    """Where tissue was (or will be) sampled, from the procedure wording; [] when it does not say."""
    from .radiology import expand_regions, regions_in
    found = set(regions_in(text or ""))
    if _LUNG_SITE.search(text or ""):
        found |= {"lung", "chest"}
    for site, rx in _OTHER_BIOPSY_SITES:
        if rx.search(text or ""):
            found.add(site)
    return expand_regions(found) if found else []


def _map_procedure(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("performedDateTime"), (r.get("performedPeriod") or {}).get("end"))
    text = _concept_text(r.get("code")).lower()
    if "colonoscopy" in text or "대장내시경" in text:
        etype = EventType.COLONOSCOPY.value
    elif _EUS.search(text):
        etype = EventType.ENDOSCOPIC_ULTRASOUND.value
    elif "breast" in text and "biopsy" in text:
        etype = EventType.BREAST_BIOPSY.value
    elif "echocardiogra" in text or "심초음파" in text:
        etype = EventType.ECHOCARDIOGRAM.value
    elif "colposcopy" in text:
        etype = EventType.COLPOSCOPY_VISIT.value
    elif "biopsy" in text or "aspiration" in text or re.search(r"\bfna\b", text) or "조직검사" in text or "세침" in text:
        etype = EventType.BIOPSY_RESULT.value
    else:
        return []
    details = {"procedure": _concept_text(r.get("code")), "mapping": [f"Procedure→{etype}"]}
    if etype in (EventType.BIOPSY_RESULT.value, EventType.BREAST_BIOPSY.value):
        sites = biopsy_regions(_concept_text(r.get("code")) + " " + " ".join(_concept_text(b) for b in r.get("bodySite", [])))
        if sites:
            details["body_regions"] = sites
    return [(etype, ts, details)]


def note_text(r: Dict) -> str:
    """Plain text of a DocumentReference (text/plain or text/html attachments carried inline)."""
    import base64
    import html as _html
    parts = []
    for c in r.get("content", []):
        a = c.get("attachment") or {}
        ctype = str(a.get("contentType") or "text/plain").lower()
        if not a.get("data") or not (ctype.startswith("text/plain") or ctype.startswith("text/html")):
            continue
        try:
            raw = base64.b64decode(a["data"]).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            continue
        if "html" in ctype:
            raw = _html.unescape(re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", raw, flags=re.I))
            raw = re.sub(r"<[^>]+>", " ", raw)
        parts.append(raw)
    return "\n".join(parts)


def _map_document_reference(r: Dict) -> List[Tuple[str, str, Dict]]:
    """
    A clinician's note: each concrete plan in it ("repeat potassium in 1 week", "refer to cardiology",
    "3개월 후 흉부 CT") becomes an obligation (R048–R051), closed by the matching event.
    """
    if str(r.get("docStatus") or "").lower() in ("preliminary", "entered-in-error") \
            or str(r.get("status") or "").lower() in ("superseded", "entered-in-error"):
        return []                                 # a superseded version: its replacement carries the plans
    ts = _first(r.get("date"), ((r.get("context") or {}).get("period") or {}).get("start"))
    text = note_text(r)
    if not text.strip():
        return []
    note_type = _concept_text(r.get("type")) or r.get("description") or "Clinical note"
    setting = specialty_of(_concept_text((r.get("context") or {}).get("practiceSetting")) + " " + note_type)
    found = find_plans(text)
    out = []
    for i, p in enumerate(found["plans"]):
        rule = p["rule_id"]
        d: Dict[str, Any] = {
            "note_type": note_type, "plan": p, "plan_label": plan_label(p), "evidence_span": p["evidence"],
            "event_suffix": f"plan{i + 1}-{p['kind']}-{p['target'] or 'any'}",
        }
        if not p["tracked"]:
            d["condition"] = "note_plan_not_tracked"
            d["mapping"] = [f"DocumentReference→plan '{plan_label(p)}': not tracked ({p['reason']})"]
        else:
            d["condition"] = f"note_plan_{p['kind']}"
            d["rule_deadline_days"] = {rule: p["due_days"]}
            if p["kind"] == "lab" and p["target"]:
                d["followup_match"] = {rule: {"analyte": p["target"]}}
            if p["kind"] == "referral" and p["target"]:
                d["followup_match"] = {rule: {"specialty": p["target"]}}
            if p["kind"] == "visit":
                # A visit long before the planned interval is another visit, not this one ("RTC 6 months" is not
                # closed by tomorrow's dermatology appointment); a specialty, when known, must not differ.
                if p["interval_stated"] and p["interval_days"] >= 14:
                    d["followup_not_before_days"] = {rule: round(0.5 * p["interval_days"], 1)}
                spec = p["target"] or setting
                if spec:
                    d["followup_match"] = {rule: {"specialty": spec, "_lenient": True}}
            if p["kind"] == "imaging":
                d["followup_types"] = {rule: MODALITY_EVENTS.get(p["target"], [])}
                if p.get("regions"):
                    d["followup_regions"] = {rule: list(p["regions"])}
            d["mapping"] = [f"DocumentReference({note_type})→plan '{plan_label(p)}' → {rule}, due in "
                            f"{p['due_days']:g} days{'' if p['interval_stated'] else ' (no interval in the note: default)'}"]
        out.append((EventType.CLINICAL_NOTE_PLAN.value, ts, d))
    return out


MAPPERS = {
    "Observation": _map_observation,
    "DiagnosticReport": _map_diagnostic_report,
    "ServiceRequest": _map_service_request,
    "Appointment": _map_appointment,
    "Communication": _map_communication,
    "Encounter": _map_encounter,
    "MedicationRequest": _map_medication_request,
    "Procedure": _map_procedure,
    "Condition": _map_condition,
    "ImagingStudy": _map_imaging_study,
    "DocumentReference": _map_document_reference,
}


# ── Public API ───────────────────────────────────────────────────────────────

def _resources(bundle_or_resources: Any) -> Iterable[Dict]:
    if isinstance(bundle_or_resources, dict) and bundle_or_resources.get("resourceType") == "Bundle":
        for entry in bundle_or_resources.get("entry", []):
            if entry.get("resource"):
                yield entry["resource"]
    elif isinstance(bundle_or_resources, dict):
        yield bundle_or_resources
    else:
        yield from bundle_or_resources


def bundle_to_events(bundle_or_resources: Any) -> Tuple[Dict[str, List[Dict]], List[str]]:
    """
    Convert FHIR resources into ClinLoop events grouped by patient.

    Returns (events_by_patient, warnings). Resources that cannot be mapped
    (unsupported type, no patient, no timestamp) are skipped with a warning
    rather than silently dropped.
    """
    by_patient: Dict[str, List[Dict]] = defaultdict(list)
    warnings: List[str] = []
    patients = _patient_context(bundle_or_resources)

    for r in _resources(bundle_or_resources):
        rtype = r.get("resourceType", "?")
        rid = r.get("id", "?")
        mapper = MAPPERS.get(rtype)
        explicit = _explicit_event_type(r)
        if mapper is None and not explicit:
            continue
        pid = _patient_id(r)
        if not pid:
            warnings.append(f"{rtype}/{rid}: no patient reference; skipped")
            continue
        status = _status(r)
        if status == "entered-in-error":
            continue
        mapped = mapper(r) if mapper else []
        if explicit:
            ts = mapped[0][1] if mapped else _first(
                r.get("effectiveDateTime"), r.get("issued"), r.get("authoredOn"), r.get("sent"),
                r.get("start"), r.get("performedDateTime"))
            base = mapped[0][2] if mapped else {}
            mapped = [(explicit, ts, {**base, "mapping": [f"explicit extension→{explicit}"]})]
        for etype, ts, details in mapped:
            if not ts:
                if f"{rtype}/{rid}: no timestamp; skipped" not in warnings:
                    warnings.append(f"{rtype}/{rid}: no timestamp; skipped")
                continue
            # Deterministic id: the same resource yields the same loop key on
            # every ingest, whatever order the bundle lists resources in.
            suffix = details.pop("event_suffix", None)   # several plans from one note
            by_patient[pid].append({
                "event_id": f"{rtype}/{rid}:{etype}" + (f":{suffix}" if suffix else ""),
                "patient_id": pid,
                "event_type": etype,
                "timestamp": ts,
                "details": details,
                "status": status,
                "source": f"{rtype}/{rid}",
            })

    for pid, events in by_patient.items():
        _derive_context(events)
        decide_obligations(events, patients.get(pid, {}))
        apply_patterns(events, patients.get(pid, {}))
        apply_ai_review(events)
    return dict(by_patient), warnings


def _patient_context(bundle_or_resources: Any) -> Dict[str, Dict[str, Any]]:
    """Birth date and administrative sex per patient (for age- and sex-specific radiology guidance)."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in _resources(bundle_or_resources):
        if r.get("resourceType") != "Patient" or not r.get("id"):
            continue
        ctx: Dict[str, Any] = {}
        birth = str(r.get("birthDate", ""))
        m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", birth)
        if m:
            ctx["birth_date"] = datetime(int(m.group(1)), int(m.group(2) or 7), int(m.group(3) or 1))
        if r.get("gender"):
            ctx["sex"] = str(r["gender"]).lower()
        out[r["id"]] = ctx
    return out


def _derive_context(events: List[Dict]) -> None:
    """
    Add facts that need more than one resource:
      * results finalised after the patient's latest prior discharge
        (R006 positive culture callback, R021 abnormal-result review);
      * drug-specific monitoring labs after a medication change (R010).
    """
    def ts(e):
        return normalize_timestamp(e["timestamp"])

    discharges = sorted(ts(e) for e in events if e["event_type"] == EventType.DISCHARGE.value)

    # Liver imaging in a patient with HCC risk is surveillance, and starts the next interval
    risk_since = min((ts(e) for e in events if e["event_type"] == EventType.DIAGNOSIS.value
                      and e["details"].get("hcc_risk")), default=None)
    if risk_since is not None:
        for e in events:
            if e["event_type"] == EventType.LIVER_IMAGING.value and ts(e) >= risk_since \
                    and is_fulfilling_status(e["status"]):
                e["details"]["hcc_surveillance"] = True
    med_changes = [e for e in events if e["event_type"] == EventType.MEDICATION_CHANGE.value
                   and e["details"].get("condition") == "requires_monitoring"]
    derived: List[Dict] = []

    for e in events:
        if e["event_type"] not in (EventType.LAB_RESULT.value, EventType.CULTURE_RESULT.value):
            continue
        t = ts(e)
        # Discharged within the 30 days before this result, with no readmission evidence
        prior = [d for d in discharges if d < t and (t - d).days <= 30]
        if prior:
            e["details"]["resulted_after_discharge"] = True
            if e["event_type"] == EventType.CULTURE_RESULT.value and e["details"].get("result") == "positive":
                e["details"].setdefault("condition", "positive_post_discharge")

        loinc = set(e["details"].get("loinc", []))
        for med in med_changes:
            drug = med["details"].get("drug")
            if loinc & DRUG_MONITORING_LOINC.get(drug, set()) and ts(med) < t:
                derived.append({
                    **{k: v for k, v in e.items() if k != "details"},
                    "event_id": f"{e['source']}:followup_lab",
                    "event_type": EventType.FOLLOWUP_LAB.value,
                    "details": {"drug": drug, "mapping": [f"{drug} monitoring lab→followup_lab"]},
                })
                break
    events.extend(derived)


def patient_strata(bundle_or_resources: Any, as_of: Optional[datetime] = None) -> Dict[str, Dict[str, str]]:
    """
    Equity strata from Patient resources: decade age group, preferred
    language and sex. Used only to stratify the open-loop rate (never to
    rank patients). Names, addresses and identifiers are not read.
    """
    as_of = as_of or datetime.now()
    strata: Dict[str, Dict[str, str]] = {}
    for r in _resources(bundle_or_resources):
        if r.get("resourceType") != "Patient" or not r.get("id"):
            continue
        s: Dict[str, str] = {}
        birth = str(r.get("birthDate", ""))
        if re.match(r"^\d{4}", birth):
            age = as_of.year - int(birth[:4])
            s["age_group"] = "80+" if age >= 80 else f"{(age // 10) * 10}s"
        for comm in r.get("communication", []):
            lang = _codes(comm.get("language")) or {_concept_text(comm.get("language"))}
            if lang:
                s["language"] = sorted(lang)[0]
                if comm.get("preferred"):
                    break
        if r.get("gender"):
            s["sex"] = r["gender"]
        strata[r["id"]] = s
    return strata
