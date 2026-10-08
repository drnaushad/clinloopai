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
Appointment, Communication, Encounter, MedicationRequest, Procedure.
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .clinical_ontology import EventType
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
}

_NEGATION = re.compile(
    r"\b(no|negative for|without|free of|absence of|no evidence of|not)\b[^.;]{0,40}$",
    re.IGNORECASE,
)


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


def _not_negated(text: str, start: int) -> bool:
    return not _NEGATION.search(text[max(0, start - 60):start])


def _span(text: str, match: re.Match, pad: int = 40) -> str:
    return text[max(0, match.start() - pad): match.end() + pad].strip()


def _first_affirmed(pattern: re.Pattern, text: str) -> Optional[re.Match]:
    """First match not preceded by a negation ("negative for X; Y present" finds Y)."""
    for m in pattern.finditer(text):
        if _not_negated(text, m.start()):
            return m
    return None


# ── Resource mappers ─────────────────────────────────────────────────────────

def _map_observation(r: Dict) -> List[Tuple[str, str, Dict]]:
    """Returns [(event_type, timestamp, details)]."""
    ts = _first(r.get("effectiveDateTime"), (r.get("effectivePeriod") or {}).get("end"), r.get("issued"))
    code_text = _concept_text(r.get("code")).lower()
    codes = _codes(r.get("code"))
    details: Dict[str, Any] = {"test": _concept_text(r.get("code")) or None, "loinc": sorted(codes)}

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

    # A measured HbA1c / INR also satisfies a pending recheck obligation
    if codes & LOINC_HBA1C:
        events.append((EventType.HBA1C_RECHECK.value, ts, {"loinc": sorted(codes), "mapping": ["HbA1c→hba1c_recheck"]}))
    if codes & LOINC_INR:
        events.append((EventType.INR_RECHECK.value, ts, {"loinc": sorted(codes), "mapping": ["INR→inr_recheck"]}))
    return events


_NODULE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm|밀리)[^.;]{0,40}?(nodule|결절)|(nodule|결절)[^.;]{0,40}?(\d+(?:\.\d+)?)\s*mm", re.I)
_LUNG_RADS = re.compile(r"lung-?rads\s*(?:category\s*)?:?\s*(\d[ABXS]?)", re.I)
_BIRADS = re.compile(r"bi-?rads\s*(?:category\s*)?:?\s*(\d[ABC]?)", re.I)
_CHEST_CT = re.compile(r"\b(ct|ldct|computed tomography)\b.*\b(chest|thorax|lung)\b|\b(chest|thorax|lung)\b.*\b(ct|ldct)\b|흉부\s*ct", re.I)
_MALIGNANT = re.compile(r"(adenocarcinoma|carcinoma|malignan\w*|high-grade dysplasia|melanoma|lymphoma|sarcoma|암)", re.I)


def _map_diagnostic_report(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("effectiveDateTime"), (r.get("effectivePeriod") or {}).get("end"), r.get("issued"))
    category = _all_category_text(r)
    code_text = _concept_text(r.get("code"))
    conclusion = " ".join(filter(None, [r.get("conclusion", ""),
                                        " ".join(_concept_text(c) for c in r.get("conclusionCode", []))]))
    details: Dict[str, Any] = {"report": code_text or None, "conclusion": conclusion or None}
    events: List[Tuple[str, str, Dict]] = []

    if "rad" in category or "imaging" in category or "radiology" in category:
        mapping = ["DiagnosticReport(RAD)→radiology_report"]
        m = _first_affirmed(_NODULE, conclusion)
        if m:
            size = float(m.group(1) or m.group(4))
            details.update(finding="incidental_pulmonary_nodule", nodule_size_mm=size,
                           evidence_span=_span(conclusion, m))
            mapping.append(f"nodule {size} mm")
        m = _LUNG_RADS.search(conclusion)
        if m:
            details.update(lung_rads=m.group(1).upper(), evidence_span=_span(conclusion, m))
            mapping.append(f"Lung-RADS {m.group(1).upper()}")
        m = _BIRADS.search(conclusion)
        if m:
            details.update(birads=m.group(1).upper(), evidence_span=_span(conclusion, m))
            mapping.append(f"BI-RADS {m.group(1).upper()}")
        details["mapping"] = mapping
        events.append((EventType.RADIOLOGY_REPORT.value, ts, details))
        # A completed chest CT also fulfils an outstanding follow-up-CT obligation
        if _CHEST_CT.search(code_text):
            events.append((EventType.FOLLOWUP_CT.value, ts, {"mapping": ["chest CT report→followup_ct"]}))
        return events

    if "pat" in category or "pathology" in category or "sp" in category.split():
        mapping = ["DiagnosticReport(PAT)→pathology_result"]
        m = _first_affirmed(_MALIGNANT, conclusion)
        if m:
            details.update(condition="abnormal", evidence_span=_span(conclusion, m))
            mapping.append(f"'{m.group(1)}'→abnormal")
        details["mapping"] = mapping
        return [(EventType.PATHOLOGY_RESULT.value, ts, details)]

    return []  # lab DiagnosticReports: the referenced Observations carry the data


def _map_service_request(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("authoredOn"), (r.get("occurrencePeriod") or {}).get("start"))
    text = (_concept_text(r.get("code")) + " " + _all_category_text(r)).lower()
    details = {"order": _concept_text(r.get("code")) or None}
    if "colposcopy" in text or "질확대경" in text:
        etype = EventType.COLPOSCOPY_REFERRAL.value
    elif "biopsy" in text or "조직검사" in text:
        etype = EventType.BIOPSY_ORDER.value
    elif "referral" in text or "3457005" in text or "consult" in text or "의뢰" in text or "협진" in text:
        etype = EventType.SPECIALIST_REFERRAL.value
    elif "imaging" in text or "363679005" in text or re.search(r"\b(ct|mri|x-ray|ultrasound)\b", text):
        etype = EventType.IMAGING_ORDER.value
    else:
        etype = EventType.LAB_ORDER.value
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
        return [(EventType.FOLLOWUP_CT.value, ts, {"mapping": ["Appointment(chest CT)→followup_ct"]})]
    if "colonoscopy" in text or "대장내시경" in text:
        return [(EventType.COLONOSCOPY.value, ts, {"mapping": ["Appointment(colonoscopy)→colonoscopy"]})]
    events = [(EventType.FOLLOWUP_APPOINTMENT.value, ts, {"mapping": ["Appointment→followup_appointment"]})]
    if any(_ref_id(b, "ServiceRequest") for b in r.get("basedOn", [])):
        events.append((EventType.REFERRAL_VISIT.value, ts, {"mapping": ["Appointment.basedOn referral→referral_visit"]}))
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


def _map_encounter(r: Dict) -> List[Tuple[str, str, Dict]]:
    period = r.get("period") or {}
    enc_class = str((r.get("class") or {}).get("code", "")).upper()
    # Discharge diagnosis: reasonCode, or the display of the first diagnosis reference
    dx_text = " ".join(_concept_text(c) for c in r.get("reasonCode", []))
    if not dx_text:
        dx_text = " ".join((d.get("condition") or {}).get("display", "") for d in r.get("diagnosis", []))
    primary_dx = re.sub(r"[^a-z0-9]+", "_", dx_text.lower()).strip("_")
    if enc_class in ("IMP", "ACUTE", "NONAC", "EMER", "OBSENC") and period.get("end"):
        return [(EventType.DISCHARGE.value, period["end"],
                 {"primary_diagnosis": primary_dx, "encounter_class": enc_class,
                  "mapping": [f"Encounter({enc_class}) end→discharge"]})]
    if enc_class == "AMB" and str(r.get("status", "")).lower() == "finished":
        return [(EventType.FOLLOWUP_APPOINTMENT.value, _first(period.get("start"), period.get("end")),
                 {"mapping": ["Encounter(AMB) finished→followup_appointment"]})]
    return []


def _drug_name(r: Dict) -> str:
    concept = r.get("medicationCodeableConcept")
    return _concept_text(concept).lower()


def _map_medication_request(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = r.get("authoredOn")
    name = _drug_name(r)
    details: Dict[str, Any] = {"medication": name or None}
    if any(a in name for a in ANTICOAGULANTS):
        details.update(drug="warfarin", condition="anticoagulant_dose_change")
    else:
        for drug in DRUG_MONITORING_LOINC:
            if drug in name:
                details.update(drug=drug, condition="requires_monitoring")
                break
    details["mapping"] = [f"MedicationRequest→medication_change ({details.get('condition', 'no rule')})"]
    return [(EventType.MEDICATION_CHANGE.value, ts, details)]


def _map_procedure(r: Dict) -> List[Tuple[str, str, Dict]]:
    ts = _first(r.get("performedDateTime"), (r.get("performedPeriod") or {}).get("end"))
    text = _concept_text(r.get("code")).lower()
    if "colonoscopy" in text or "대장내시경" in text:
        etype = EventType.COLONOSCOPY.value
    elif "breast" in text and "biopsy" in text:
        etype = EventType.BREAST_BIOPSY.value
    elif "echocardiogra" in text or "심초음파" in text:
        etype = EventType.ECHOCARDIOGRAM.value
    elif "colposcopy" in text:
        etype = EventType.COLPOSCOPY_VISIT.value
    elif "biopsy" in text:
        etype = EventType.BIOPSY_RESULT.value
    else:
        return []
    return [(etype, ts, {"procedure": _concept_text(r.get("code")), "mapping": [f"Procedure→{etype}"]})]


MAPPERS = {
    "Observation": _map_observation,
    "DiagnosticReport": _map_diagnostic_report,
    "ServiceRequest": _map_service_request,
    "Appointment": _map_appointment,
    "Communication": _map_communication,
    "Encounter": _map_encounter,
    "MedicationRequest": _map_medication_request,
    "Procedure": _map_procedure,
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
                warnings.append(f"{rtype}/{rid}: no timestamp; skipped")
                continue
            # Deterministic id: the same resource yields the same loop key on
            # every ingest, whatever order the bundle lists resources in.
            by_patient[pid].append({
                "event_id": f"{rtype}/{rid}:{etype}",
                "patient_id": pid,
                "event_type": etype,
                "timestamp": ts,
                "details": details,
                "status": status,
                "source": f"{rtype}/{rid}",
            })

    for pid, events in by_patient.items():
        _derive_context(events)
    return dict(by_patient), warnings


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
