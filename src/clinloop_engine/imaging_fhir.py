"""
imaging_fhir.py — Imaging studies and imaging-AI findings as FHIR resources

Every imaging source ClinLoop reads (the PACS over DICOMweb, an uploaded
DICOM file, an approved imaging-AI product, ClinLoop's own on-premise model
runner) is turned into standard FHIR R4 resources first:

  * ImagingStudy   "a CT of the chest was performed on 2026-03-02"
                   (study labels only: modality, body part, date, status)
  * Observation    "AI product X scored 'lung nodule' 0.87 on that study"

so the same ingestion, engine, governance and audit path handles all of them.
Pixel data and patient names are never stored.
"""

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .radiology import expand_regions, regions_in

CLINLOOP_TAG_SYSTEM = "https://clinloopai.app/fhir/tags"
# DICOM dates/times are local and carry no zone. ClinLoop's pilots are in Korea; set
# CLINLOOP_LOCAL_TZ to the hospital's IANA zone elsewhere ("UTC" if the PACS stores UTC).
DEFAULT_LOCAL_TZ = "Asia/Seoul"
REGULATORY_URL = "https://clinloopai.app/fhir/StructureDefinition/regulatory-status"
OCR_CONFIDENCE_URL = "https://clinloopai.app/fhir/StructureDefinition/ocr-confidence"
DICOM_UID_SYSTEM = "urn:dicom:uid"
DCM_SYSTEM = "http://dicom.nema.org/resources/ontology/DCM"

# DICOM modality → ClinLoop imaging modality
DICOM_MODALITY = {
    "CT": "ct", "MR": "mri", "US": "ultrasound", "CR": "xray", "DX": "xray", "DR": "xray", "RG": "xray",
    "PT": "pet", "MG": "mammography", "XA": "angiography", "NM": "nuclear", "RF": "fluoroscopy",
}

# DICOM BodyPartExamined defined terms that run words together
_BODY_PART_WORDS = {
    "ABDOMENPELVIS": "abdomen pelvis", "ABDPELVIS": "abdomen pelvis", "CHESTABDOMEN": "chest abdomen",
    "CHESTABDPELVIS": "chest abdomen pelvis", "CHEST_TO_PELVIS": "chest abdomen pelvis",
    "HEADNECK": "head neck", "WHOLEBODY": "whole-body", "CSPINE": "spine", "TSPINE": "spine",
    "LSPINE": "spine", "SSPINE": "spine", "BRAIN": "brain", "SKULL": "skull", "AORTA": "abdominal aorta",
}


def dicom_regions(body_part: Optional[str] = "", *descriptions: Optional[str]) -> List[str]:
    """Body regions covered by a study, from BodyPartExamined and the study/series descriptions."""
    texts = []
    bp = (body_part or "").strip().upper()
    if bp:
        texts.append(_BODY_PART_WORDS.get(bp, bp.replace("_", " ").lower()))
    texts.extend(d for d in descriptions if d)
    found = set()
    for t in texts:
        found |= regions_in(t)
    return expand_regions(found)


def _fhir_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:40]


def _local_tz(offset: Optional[str] = None):
    """DICOM times are local: use the file's TimezoneOffsetFromUTC ('+0900'), else CLINLOOP_LOCAL_TZ."""
    if offset and re.fullmatch(r"[+-]\d{4}", offset.strip()):
        sign = 1 if offset.strip()[0] == "+" else -1
        return timezone(sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5])))
    name = os.environ.get("CLINLOOP_LOCAL_TZ", DEFAULT_LOCAL_TZ).strip()
    if name.upper() in ("", "NONE", "NAIVE"):
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        logging.getLogger("clinloop.imaging").error(
            "CLINLOOP_LOCAL_TZ=%r is not a valid IANA time zone: DICOM times are read as UTC", name)
        return None


def dicom_datetime(date: Optional[str], time: Optional[str] = None, tz_offset: Optional[str] = None) -> Optional[str]:
    """DICOM DA/TM ('20260302', '093000.123') → ISO 8601 in the hospital's time zone, or None."""
    date = (date or "").strip()
    if not re.fullmatch(r"\d{8}", date):
        return None
    t = re.sub(r"[^\d]", "", (time or "").split(".")[0])[:6].ljust(6, "0") if time else "000000"
    try:
        dt = datetime(int(date[:4]), int(date[4:6]), int(date[6:8]), int(t[:2]), int(t[2:4]), int(t[4:6]))
    except ValueError:
        try:
            dt = datetime(int(date[:4]), int(date[4:6]), int(date[6:8]))
        except ValueError:
            return None          # e.g. "20260230"
    tz = _local_tz(tz_offset)
    return (dt.replace(tzinfo=tz) if tz else dt).isoformat()


def imaging_study_resource(meta: Dict[str, Any], patient_id: str, source: str) -> Dict[str, Any]:
    """
    FHIR ImagingStudy from DICOM study attributes:
      study_uid, accession, modalities [..], body_part, description, series_descriptions [..],
      study_date, study_time, n_series, n_instances, status ('available' | 'registered' | 'cancelled')
    """
    uid = meta.get("study_uid") or ""
    modalities = [m for m in meta.get("modalities") or [] if m]
    started = dicom_datetime(meta.get("study_date"), meta.get("study_time"), meta.get("tz_offset"))
    resource: Dict[str, Any] = {
        "resourceType": "ImagingStudy",
        "id": "img-" + _fhir_id(uid or str(meta), patient_id),
        "meta": {"tag": [{"system": CLINLOOP_TAG_SYSTEM, "code": source}]},
        "status": meta.get("status", "available"),
        "subject": {"reference": f"Patient/{patient_id}"},
        "identifier": ([{"system": DICOM_UID_SYSTEM, "value": f"urn:oid:{uid}"}] if uid else [])
        + ([{"type": {"text": "Accession"}, "value": meta["accession"]}] if meta.get("accession") else []),
        "modality": [{"system": DCM_SYSTEM, "code": m} for m in modalities],
        "description": meta.get("description") or None,
        "numberOfSeries": meta.get("n_series"),
        "numberOfInstances": meta.get("n_instances"),
        "series": [{"uid": s.get("uid", ""), "modality": {"system": DCM_SYSTEM, "code": s.get("modality", "")},
                    "description": s.get("description"),
                    "bodySite": {"display": s.get("body_part")} if s.get("body_part") else None}
                   for s in meta.get("series", [])],
    }
    if meta.get("body_part") and not resource["series"]:
        resource["series"] = [{"uid": "", "modality": {"system": DCM_SYSTEM, "code": modalities[0] if modalities else ""},
                               "bodySite": {"display": meta["body_part"]}}]
    if started:
        resource["started"] = started
    return {k: v for k, v in resource.items() if v not in (None, [], "")}


# ── Imaging-AI findings ─────────────────────────────────────────────────────
#
# Vendors name findings differently ("Nodule", "Lung Lesion", "결절"). Each
# label maps to one finding key; `report` lists how a radiologist would write
# about it, to tell whether the report addressed the finding.

AI_FINDINGS: Dict[str, Dict[str, Any]] = {
    "lung_nodule": {"labels": r"nodule|\bmass\b|lung lesion|결절|종괴", "en": "Lung nodule or mass", "ko": "폐결절·종괴",
                    "report": r"nodul\w*|\bmass(?:es)?\b(?!\s+effect)|(?:lung|pulmonary|nodular|rounded|focal|spiculated)\s+"
                              r"(?:lesion|opacit\w*)|결절|종괴", "regions": ["chest"]},
    "pneumothorax": {"labels": r"pneumothorax|기흉", "en": "Pneumothorax", "ko": "기흉",
                     "report": r"pneumothora\w*|기흉", "regions": ["chest"], "critical": True},
    "consolidation": {"labels": r"consolidation|pneumonia|lung opacity|airspace|infiltrat\w*|경화|폐렴",
                      "en": "Consolidation / pneumonia", "ko": "경화·폐렴",
                      "report": r"consolidat\w*|pneumoni\w*|opacit\w*|airspace|infiltrat\w*|경화|폐렴|음영", "regions": ["chest"]},
    "pleural_effusion": {"labels": r"effusion|흉수", "en": "Pleural effusion", "ko": "흉수",
                         "report": r"(?<!pericardial )(?<!joint )(?<!knee )\beffusions?\b|흉수|pleural fluid", "regions": ["chest"]},
    "cardiomegaly": {"labels": r"cardiomegaly|enlarged cardiomediastinum|심비대", "en": "Cardiomegaly", "ko": "심비대",
                     "report": r"cardiomegal\w*|heart size|cardiac (?:silhouette|enlargement)|cardiomediastin\w*|심비대|심장\s*크기",
                     "regions": ["chest"]},
    # CT measurements (ct_organs): addressed only by wording about the aorta's size or the spleen
    "aortic_aneurysm": {"labels": r"aortic aneurysm|aortic dilat\w*|aneurysm|\bAAA\b|대동맥류|대동맥\s*확장",
                        "en": "Aortic aneurysm / dilatation", "ko": "대동맥류·대동맥 확장",
                        "report": r"aneurysm\w*|\bAAA\b|ectas\w*|ectatic|aort\w*[^.]{0,40}?(?:dilat\w*|diameter|calib(?:er|re)|"
                                  r"enlarg\w*|normal|unremarkable|\d(?:\.\d)?\s*cm)|(?:dilat\w*|calib(?:er|re)|normal|enlarg\w*)\s+"
                                  r"(?:[a-z\-]+\s+){0,2}aort\w*|대동맥류|대동맥[^.]{0,20}?(?:확장|직경|정상)",
                        "regions": ["abdomen", "chest"]},
    "splenomegaly": {"labels": r"splenomegaly|enlarged spleen|비장\s*비대|비종대", "en": "Splenomegaly", "ko": "비장비대",
                     "report": r"splenomegal\w*|spleen|splenic size|비장|비종대", "regions": ["abdomen"]},
    "atelectasis": {"labels": r"atelectasis|무기폐", "en": "Atelectasis", "ko": "무기폐",
                    "report": r"atelecta\w*|(?:lobar|lobe|lung|segmental)\s+collapse|무기폐", "regions": ["chest"]},
    # No default region: a fracture is compared only with the report of the same study or body region
    "fracture": {"labels": r"fracture|골절", "en": "Fracture", "ko": "골절", "report": r"fractur\w*|골절", "regions": []},
    "pneumoperitoneum": {"labels": r"pneumoperitoneum|free (?:intraperitoneal )?air|기복증", "en": "Free intraperitoneal air", "ko": "기복증",
                         "report": r"pneumoperitoneum|free (?:intraperitoneal )?air|기복증|유리\s*공기", "regions": ["abdomen"],
                         "critical": True},
    "intracranial_hemorrhage": {"labels": r"intracranial h(?:a)?emorrhage|\bich\b|h(?:a)?emorrhage|뇌출혈|두개내\s*출혈",
                                "en": "Intracranial haemorrhage", "ko": "두개내 출혈",
                                "report": r"(?<!scalp )(?<!soft tissue )(?<!subgaleal )h(?:a)?emorrhag\w*|"
                                          r"(?:intracranial|subdural|epidural|extradural|subarachnoid|intraparenchymal|"
                                          r"intraventricular|parenchymal)\s+h(?:a)?ematoma|\bich\b|bleed\w*|뇌출혈|두개내\s*출혈|"
                                          r"경막(?:하|외)\s*혈종|지주막하\s*출혈", "regions": ["head"],
                                "critical": True},
    "breast_malignancy": {"labels": r"malignan\w*|abnormality score|cancer|breast lesion|악성", "en": "Suspicious breast lesion",
                          "ko": "유방 악성 의심 병변",
                          "report": r"bi-?rads|\bmass\b|calcification\w*|asymmetr\w*|distortion|lesion|종괴|석회화|병변",
                          "regions": ["breast"]},
    # Read by some models but not actionable as a missed follow-up: kept, not tracked
    "chronic_or_minor": {"labels": r"emphysema|fibrosis|edema|oedema|pleural[_ ]thickening|hernia|폐기종|섬유화",
                         "en": "Chronic or minor finding", "ko": "만성·경미 소견", "report": r".", "regions": ["chest"],
                         "track": False},
}
_AI_LABEL_RX = [(key, re.compile(spec["labels"], re.I)) for key, spec in AI_FINDINGS.items()]
DEFAULT_AI_THRESHOLD = 0.5


def ai_finding_key(label: str, study_regions: Optional[List[str]] = None) -> Optional[str]:
    """Finding key for a vendor label ('Nodule', 'Lung Lesion', '결절'), or None if unknown."""
    label = label or ""
    for key, rx in _AI_LABEL_RX:
        if rx.search(label):
            if key == "breast_malignancy" and study_regions and "breast" not in study_regions:
                continue      # "malignancy score" means a breast lesion only on breast imaging
            if key == "intracranial_hemorrhage" and re.fullmatch(r"\s*h(?:a)?emorrhage\s*", label, re.I) \
                    and study_regions and "head" not in study_regions:
                continue
            return key
    return None


def ai_observation_resource(patient_id: str, label: str, score: Optional[float], positive: Optional[bool],
                            product: str, version: str, regulatory: str, study_ref: Optional[str],
                            when: str, body_part: Optional[str] = None, source: str = "imaging-ai",
                            finding_key: Optional[str] = None, study_uid: Optional[str] = None) -> Dict[str, Any]:
    """
    FHIR Observation for one imaging-AI output (positive or not).

    The id depends on the patient, the study, the product and the finding (not on
    the time or the exact label set), so re-analysing the same image updates the
    same record instead of adding a duplicate.
    """
    study_key = study_uid or study_ref or when
    obs: Dict[str, Any] = {
        "resourceType": "Observation",
        "id": "ai-" + _fhir_id(patient_id, study_key, product, finding_key or label.lower()),
        "meta": {"tag": [{"system": CLINLOOP_TAG_SYSTEM, "code": "imaging-ai"},
                         {"system": CLINLOOP_TAG_SYSTEM, "code": source}]},
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                  "code": "imaging"}]}],
        "code": {"text": label},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": when,
        "device": {"display": f"{product} {version}".strip()},
        "method": {"text": "Imaging AI (second reader)"},
        "extension": [{"url": REGULATORY_URL, "valueString": regulatory}],
    }
    if score is not None:
        obs["valueQuantity"] = {"value": round(float(score), 4), "unit": "probability"}
    if positive is not None:
        obs["interpretation"] = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                              "code": "POS" if positive else "NEG"}]}]
    if study_ref or study_uid:
        link: Dict[str, Any] = {"reference": study_ref} if study_ref else {}
        if study_uid:
            link["identifier"] = {"system": DICOM_UID_SYSTEM, "value": f"urn:oid:{study_uid}"}
        obs["derivedFrom"] = [link]
    if body_part:
        obs["bodySite"] = {"text": body_part}
    return obs


def is_research_use(regulatory: str) -> bool:
    return bool(re.search(r"research|not a medical device|investigational|연구용", regulatory or "", re.I))


def regulatory_unverified(regulatory: str) -> bool:
    """No stated approval (research use, or nothing stated): such findings open no loops unless allowed."""
    r = (regulatory or "").strip().lower()
    return is_research_use(r) or r in ("", "not stated", "unknown")


def study_uid_from(value: Optional[str]) -> Optional[str]:
    """'urn:oid:1.2.3' / '1.2.3' → '1.2.3'."""
    if not value:
        return None
    v = str(value).strip()
    return v[8:] if v.lower().startswith("urn:oid:") else v


def norm_ref(ref: Optional[str]) -> Optional[str]:
    """'https://fhir.x/r4/ImagingStudy/123/_history/2' → 'ImagingStudy/123'."""
    if not ref:
        return None
    parts = [p for p in str(ref).split("/_history")[0].split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else str(ref)
