"""
imaging_api.py — Imaging endpoints: outside reports, DICOM analysis, imaging-AI results, PACS

  POST /api/v1/documents/outside-report/extract   read a PDF/image report (nothing stored)
  POST /api/v1/documents/outside-report           file the (checked) report and re-evaluate the patient
  POST /api/v1/documents/clinical-note/extract   read a clinician's note: the plans it contains (nothing stored)
  POST /api/v1/documents/clinical-note           file the note; its plans become tracked follow-ups (R048–R051)
  POST /api/v1/imaging/analyze                    DICOM: header checks, study record, imaging models
  POST /api/v1/imaging/ct-organs                  CT series: organ segmentation and measurements (3-D)
  POST /api/v1/imaging/ai-results                 results from an approved imaging-AI product (FHIR or DICOM SR)
  GET  /api/v1/imaging/models                     imaging models and their regulatory status (public)
  GET  /api/v1/patients/{id}/documents            what was added for a patient outside the FHIR feed
  POST /api/v1/pacs/check                         is the PACS reachable (admin)

Files travel as base64 in JSON. Uploaded files are never stored: only the
FHIR resources derived from them (scrubbed text, study labels, findings)
and the file's SHA-256 hash. Every filing is audited.
"""

import base64
import binascii
import hashlib
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import User, require_role
from .clinical_api import get_store
from .fhir_ingest import bundle_to_events, patient_strata
from .loop_detector import ClinLoopDetector, hospital_detector, lapse_after_death

router = APIRouter(prefix="/api/v1")
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
MAX_CT_UPLOAD_BYTES = 400 * 1024 * 1024     # a zipped CT series


FHIR_ID = r"^[A-Za-z0-9\-.]{1,64}$"


class FileUpload(BaseModel):
    patient_id: str = Field(..., pattern=FHIR_ID, description="FHIR Patient id")
    filename: str = ""
    content_base64: str


class OutsideReportFiling(FileUpload):
    title: Optional[str] = Field(None, description="Study title, as checked by the person filing")
    date: Optional[str] = Field(None, description="Report date YYYY-MM-DD, as checked")
    conclusion: Optional[str] = Field(None, description="Impression text, as checked/corrected")
    confirmed: bool = Field(False, description="The person checked title, date and impression against the original")


class ClinicalNote(BaseModel):
    patient_id: str = Field(..., pattern=FHIR_ID)
    text: Optional[str] = Field(None, description="The note as text (or send a PDF/image file instead)")
    filename: str = ""
    content_base64: Optional[str] = None
    date: Optional[str] = Field(None, description="Note date YYYY-MM-DD (default: today)")
    note_type: str = Field("Clinical note", max_length=80)
    suggest_with_llm: bool = Field(False, description="Also ask the hospital's local LLM for plans the rules missed")


class DicomUpload(FileUpload):
    expected_modality: Optional[str] = None


class AIResults(BaseModel):
    patient_id: str = Field(..., pattern=FHIR_ID)
    bundle: Optional[Dict[str, Any]] = Field(None, description="FHIR Bundle of AI Observations (and ImagingStudy)")
    dicom_sr_base64: Optional[str] = None
    regulatory: str = Field("not stated", description="Regulatory status of the product, e.g. 'MFDS approved (Class II)'")


def _decode(b64: str, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    try:
        data = base64.b64decode(b64.split(",", 1)[-1], validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "content_base64 is not valid base64")
    if not data:
        raise HTTPException(422, "Empty file")
    if len(data) > limit:
        raise HTTPException(413, "File too large")
    return data


def _patient_resource(patient_id: str) -> Dict[str, Any]:
    """The patient's FHIR Patient resource (FHIR server, else the last upload); 404 if the patient is unknown."""
    from .fhir_sync import client_from_env
    client = client_from_env()
    if client is not None:
        try:
            found = [r for r in client.search("Patient", {"_id": patient_id}) if r.get("id") == patient_id]
        except Exception:
            raise HTTPException(503, "FHIR server unreachable: cannot confirm the patient")
    else:
        found = [r for r in get_store().snapshot(patient_id)
                 if r.get("resourceType") == "Patient" and r.get("id") == patient_id]
    if not found:
        raise HTTPException(404, f"Unknown patient '{patient_id}': load the patient's record first")
    return found[0]


def _patient_ids(patient: Dict[str, Any]) -> List[str]:
    from .pacs_client import dicom_patient_ids
    return dicom_patient_ids(patient)


def _patient_names(patient: Dict[str, Any]) -> List[str]:
    names = []
    for n in patient.get("name", []):
        names += [n.get("text") or "", n.get("family") or ""] + list(n.get("given") or [])
        names.append(" ".join(list(n.get("given") or []) + [n.get("family") or ""]).strip())
        names.append(((n.get("family") or "") + "".join(n.get("given") or [])).strip())   # 홍길동
        names.append(((n.get("family") or "") + " " + " ".join(n.get("given") or [])).strip())   # 홍 길동
    return [x for x in names if x and len(x) >= 2]


def evaluate_patient(patient_id: str, actor: str) -> Dict[str, Any]:
    """Re-run the engine on everything known about one patient and record the loops."""
    from .fhir_sync import client_from_env, patient_record
    from .pacs_client import client_from_env as pacs_from_env
    store = get_store()
    resources, warnings = patient_record(patient_id, store, client_from_env(), pacs_from_env())
    events_by_patient, w2 = bundle_to_events(resources)
    detections = []
    detector = hospital_detector()
    for pid, events in events_by_patient.items():
        detections.extend(lapse_after_death(detector.process_patient("imaging", pid, events), resources))
    counts = store.upsert_detections(detections, strata=patient_strata(resources), actor=actor)
    return {"loops": counts, "warnings": warnings + w2,
            "active": [{"rule_id": d.rule_id, "rule_name": d.rule_name, "status": d.loop_status, "deadline": d.deadline}
                       for d in detections if d.loop_status in ("open", "needs_human_review")]}


# ── Outside reports ─────────────────────────────────────────────────────────

@router.post("/documents/outside-report/extract", tags=["Imaging & Documents"])
def extract_outside_report(req: FileUpload, user: User = Depends(require_role("navigator"))):
    """Read a report from another hospital (PDF or image). Nothing is stored: check the result, then file it."""
    from .document_reader import DocumentError, extract_text, parse_report, scrub_identifiers
    names = _patient_names(_patient_resource(req.patient_id))
    data = _decode(req.content_base64)
    try:
        extracted = extract_text(data, req.filename)
    except DocumentError as e:
        raise HTTPException(422, str(e))
    parsed = parse_report(extracted["text"])
    parsed["conclusion"] = scrub_identifiers(parsed["conclusion"], names)
    return {"method": extracted["method"], "confidence": extracted["confidence"], "pages": extracted["pages"],
            "text": scrub_identifiers(extracted["text"], names), "parsed": parsed,
            "sha256": hashlib.sha256(data).hexdigest()}


@router.post("/documents/outside-report", tags=["Imaging & Documents"])
def file_outside_report(req: OutsideReportFiling, user: User = Depends(require_role("navigator"))):
    """File an outside report for a patient and re-evaluate their loops."""
    from .document_reader import DocumentError, extract_text, outside_report_resource, parse_report
    names = _patient_names(_patient_resource(req.patient_id))
    data = _decode(req.content_base64)
    try:
        extracted = extract_text(data, req.filename)
    except DocumentError as e:
        raise HTTPException(422, str(e))
    parsed = parse_report(extracted["text"])
    for field in ("title", "date", "conclusion"):
        value = getattr(req, field)
        if value is not None and str(value).strip():
            parsed[field] = str(value).strip()
    if parsed.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", parsed["date"]):
        raise HTTPException(422, "date must be YYYY-MM-DD")
    if len((parsed.get("conclusion") or "").strip()) < 5:
        raise HTTPException(422, "No report text found: enter the impression")
    resource = outside_report_resource(req.patient_id, data, extracted, parsed,
                                       confirmed_by=user.name if req.confirmed else None, names=names)
    store = get_store()
    store.add_external_resource(resource, "outside-report", user.name, user.role,
                                source_sha256=hashlib.sha256(data).hexdigest(),
                                summary=f"{resource['code']['text']} {parsed.get('date') or ''} "
                                        f"({extracted['method']}{', confirmed' if req.confirmed else ''})".strip())
    return {"resource": resource, **evaluate_patient(req.patient_id, user.name)}


# ── Clinical notes ──────────────────────────────────────────────────────────

def _note_text(req: ClinicalNote) -> Dict[str, Any]:
    from .document_reader import DocumentError, extract_text
    if req.text and req.text.strip():
        text = req.text
        if len(text) > 200_000:
            raise HTTPException(413, "Note too long")
        return {"text": text, "method": "text", "confidence": None}
    if not req.content_base64:
        raise HTTPException(422, "Send the note as text or as a file")
    try:
        return extract_text(_decode(req.content_base64), req.filename)
    except DocumentError as e:
        raise HTTPException(422, str(e))


@router.post("/documents/clinical-note/extract", tags=["Imaging & Documents"])
def extract_clinical_note(req: ClinicalNote, user: User = Depends(require_role("navigator"))):
    """The follow-up plans in a note, with the sentence each came from. Nothing is stored."""
    from .note_reader import find_plans, llm_suggestions, plan_label
    _patient_resource(req.patient_id)
    got = _note_text(req)
    found = find_plans(got["text"])
    for p in found["plans"]:
        p["label"] = plan_label(p)
    out = {"method": got["method"], "confidence": got.get("confidence"), **found}
    if req.suggest_with_llm:
        out["llm"] = llm_suggestions(got["text"], found["plans"], _patient_names(_patient_resource(req.patient_id)))
    return out


@router.post("/documents/clinical-note", tags=["Imaging & Documents"])
def file_clinical_note(req: ClinicalNote, user: User = Depends(require_role("navigator"))):
    """File a note (identifiers removed) for a patient: its plans become tracked follow-ups, and the patient is re-evaluated."""
    import base64 as _b64
    from datetime import date as _date
    from .document_reader import scrub_identifiers
    from .note_reader import find_plans
    patient = _patient_resource(req.patient_id)
    got = _note_text(req)
    when = req.date or _date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
        raise HTTPException(422, "date must be YYYY-MM-DD")
    text = scrub_identifiers(got["text"], _patient_names(patient))
    # Plans are read from the note as written: identifier removal must never change what is tracked
    before = {(p["kind"], p["target"], p["tracked"]) for p in find_plans(got["text"])["plans"]}
    after = {(p["kind"], p["target"], p["tracked"]) for p in find_plans(text)["plans"]}
    scrub_warning = None if before == after else (
        "Removing identifiers changed which plans are found: check the note "
        f"(lost: {sorted(map(str, before - after))}, new: {sorted(map(str, after - before))})")
    sha = hashlib.sha256(got["text"].encode("utf-8")).hexdigest()
    resource = {
        "resourceType": "DocumentReference",
        "id": "note-" + hashlib.sha256(f"{req.patient_id}|{sha}".encode()).hexdigest()[:32],
        "meta": {"tag": [{"system": "https://clinloopai.app/fhir/tags", "code": "clinical-note"}]},
        "status": "current", "docStatus": "final",
        "type": {"text": req.note_type or "Clinical note"},
        "subject": {"reference": f"Patient/{req.patient_id}"},
        "date": f"{when}T12:00:00",
        "author": [{"display": user.name}],
        "content": [{"attachment": {"contentType": "text/plain; charset=utf-8",
                                    "data": _b64.b64encode(text.encode("utf-8")).decode()}}],
    }
    found = find_plans(text)
    store = get_store()
    store.add_external_resource(resource, "clinical-note", user.name, user.role, source_sha256=sha,
                                summary=f"{resource['type']['text']} {when}: {found['tracked']} plan(s) tracked")
    result = {"resource_id": resource["id"], "plans": found["plans"], **evaluate_patient(req.patient_id, user.name)}
    if scrub_warning:
        result["warnings"] = [scrub_warning] + list(result.get("warnings") or [])
    return result


# ── DICOM images ────────────────────────────────────────────────────────────

@router.post("/imaging/analyze", tags=["Imaging & Documents"])
def analyze_image(req: DicomUpload, user: User = Depends(require_role("navigator"))):
    """
    Read one DICOM image: safety checks, the study record, and the hospital's imaging models.
    A wrong-patient image is refused. AI findings are a second reader for radiologist review only.
    """
    from .imaging_ai import ImagingError, analyze_dicom
    patient = _patient_resource(req.patient_id)
    data = _decode(req.content_base64)
    try:
        result = analyze_dicom(data, req.patient_id, _patient_ids(patient), req.expected_modality)
    except ImagingError as e:
        raise HTTPException(422, str(e))
    store = get_store()
    if result["filed"]:
        for r in result["resources"]:
            kind = "dicom-study" if r["resourceType"] == "ImagingStudy" else "imaging-ai"
            store.add_external_resource(r, kind, user.name, user.role, source_sha256=result["sha256"],
                                        summary=(r.get("description") if kind == "dicom-study"
                                                 else f"{r['device']['display']}: {r['code']['text']}"))
        result.update(evaluate_patient(req.patient_id, user.name))
    else:
        store._audit(user.name, user.role, "imaging_refused", None,
                     {"patient_id": req.patient_id, "sha256": result["sha256"],
                      "qa": [c["code"] for c in result["qa"] if c["level"] == "critical"]})
        store._db.commit()
    return result


@router.post("/imaging/ct-organs", tags=["Imaging & Documents"])
def measure_ct_series(req: FileUpload, user: User = Depends(require_role("navigator"))):
    """
    One CT series (zip of its DICOM files, or NIfTI): organ segmentation (TotalSegmentator, research use),
    organ volumes, aortic diameter and spleen length. An abnormal measurement is a second-reader finding
    compared with the radiologist's report (R047). A NIfTI volume has no PatientID: shown, never filed.
    """
    from . import ct_organs as ct
    from .imaging_ai import ImagingError
    if not ct.enabled():
        raise HTTPException(503, "CT organ measurement is not enabled (CLINLOOP_IMAGING_MODELS=totalseg)")
    patient = _patient_resource(req.patient_id)
    data = _decode(req.content_base64, MAX_CT_UPLOAD_BYTES)
    try:
        result = ct.analyze_ct_series(data, req.filename, req.patient_id, _patient_ids(patient))
    except ImagingError as e:
        raise HTTPException(422, str(e))
    store = get_store()
    if result["filed"]:
        for r in result["resources"]:
            kind = "dicom-study" if r["resourceType"] == "ImagingStudy" else "imaging-ai"
            store.add_external_resource(r, kind, user.name, user.role, source_sha256=result["sha256"],
                                        summary=(r.get("description") if kind == "dicom-study"
                                                 else f"{r['device']['display']}: {r['code']['text']}"))
        result.update(evaluate_patient(req.patient_id, user.name))
    else:
        store._audit(user.name, user.role, "ct_organs_not_filed", None,
                     {"patient_id": req.patient_id, "sha256": result["sha256"],
                      "qa": [c["code"] for c in result["qa"] if c["level"] == "critical"]})
        store._db.commit()
    return result


@router.post("/imaging/ai-results", tags=["Imaging & Documents"])
def receive_ai_results(req: AIResults, user: User = Depends(require_role("admin"))):
    """
    Results from an approved imaging-AI product, sent by the hospital's integration engine:
    a FHIR Bundle of Observations (device = product), or the product's DICOM SR.
    """
    from .imaging_ai import ImagingError, parse_dicom_sr
    from .imaging_fhir import ai_observation_resource, dicom_datetime, imaging_study_resource
    patient = _patient_resource(req.patient_id)
    resources: List[Dict[str, Any]] = []
    if req.bundle:
        for e in req.bundle.get("entry", []):
            r = e.get("resource", e)
            if r.get("resourceType") in ("Observation", "ImagingStudy") and r.get("id"):
                subject = (r.get("subject") or {}).get("reference")
                if subject and subject != f"Patient/{req.patient_id}":
                    raise HTTPException(409, f"{r['resourceType']}/{r['id']} is for {subject}, not Patient/{req.patient_id}: "
                                             "nothing filed")
                r["subject"] = {"reference": f"Patient/{req.patient_id}"}
                if r["resourceType"] == "Observation":   # read as imaging AI, never as a lab result
                    r.setdefault("meta", {}).setdefault("tag", []).append(
                        {"system": "https://clinloopai.app/fhir/tags", "code": "imaging-ai"})
                if r["resourceType"] == "Observation" and req.regulatory != "not stated":
                    r.setdefault("extension", []).append(
                        {"url": "https://clinloopai.app/fhir/StructureDefinition/regulatory-status",
                         "valueString": req.regulatory})
                resources.append(r)
    elif req.dicom_sr_base64:
        try:
            sr = parse_dicom_sr(_decode(req.dicom_sr_base64))
        except ImagingError as e:
            raise HTTPException(422, str(e))
        if not sr["patient_id"] or sr["patient_id"] not in _patient_ids(patient):
            raise HTTPException(409, "The SR's PatientID is missing or does not match the patient: nothing filed")
        when = dicom_datetime(sr["study_date"], sr["study_time"]) or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
        study = imaging_study_resource({"study_uid": sr["study_uid"], "study_date": sr["study_date"],
                                        "study_time": sr["study_time"]}, req.patient_id, source="ai-sr")
        ref = f"ImagingStudy/{study['id']}" if sr["study_uid"] else None
        from .imaging_fhir import ai_finding_key
        for f in sr["findings"]:
            resources.append(ai_observation_resource(req.patient_id, f["label"], f["score"], f.get("positive"),
                                                     sr["product"], "", req.regulatory, ref, when, source="ai-sr",
                                                     finding_key=ai_finding_key(f["label"]), study_uid=sr["study_uid"]))
    else:
        raise HTTPException(422, "Send a FHIR bundle or a DICOM SR")
    if not resources:
        raise HTTPException(422, "No imaging-AI results found")
    store = get_store()
    for r in resources:
        store.add_external_resource(r, "imaging-ai" if r["resourceType"] == "Observation" else "dicom-study",
                                    user.name, user.role, summary=r.get("code", {}).get("text") or r.get("description") or "")
    return {"filed": len(resources), **evaluate_patient(req.patient_id, user.name)}


@router.get("/imaging/models", tags=["Imaging & Documents"])
def imaging_models():
    """Imaging models the hospital has enabled, with their regulatory status (public: no patient data)."""
    from .ai_review import research_ai_enabled
    from .document_reader import ocr_available
    from .imaging_ai import registered_models
    try:
        import pydicom  # noqa: F401
        dicom = True
    except ImportError:
        dicom = False
    from . import ct_organs
    models = [m.describe() for m in registered_models()]
    if ct_organs.enabled():
        models.append(ct_organs.describe())
    return {"models": models,
            "research_findings_open_loops": research_ai_enabled(),
            "dicom_reader": "ready" if dicom else "not installed (pip install pydicom)",
            "ocr": "ready (Tesseract kor+eng)" if ocr_available() else "not installed (apt install tesseract-ocr tesseract-ocr-kor)"}


@router.get("/patients/{patient_id}/documents", tags=["Imaging & Documents"])
def patient_documents(patient_id: str, user: User = Depends(require_role("viewer"))):
    if not re.fullmatch(FHIR_ID, patient_id):
        raise HTTPException(422, "Invalid patient id")
    return {"patient_id": patient_id, "documents": get_store().external_resource_list(patient_id)}


class SecondReadPreview(BaseModel):
    text: str = Field(..., min_length=10, max_length=20000, description="Report text (identifiers are removed before the model sees it)")
    category: str = Field("RAD", pattern="^(RAD|PAT)$")
    title: str = Field("", max_length=200)


@router.get("/reports/second-read/status", tags=["Imaging & Documents"])
def second_read_status(user: User = Depends(require_role("viewer"))):
    """The model-based second reader: on or off, on-premise model server, reports read and flags raised."""
    from .second_reader import status
    return status(get_store())


@router.post("/reports/second-read/preview", tags=["Imaging & Documents"])
def second_read_preview(req: SecondReadPreview, user: User = Depends(require_role("navigator"))):
    """
    What the rules and the second reader each find in one report, side by side. Nothing is filed: the
    background sync does that for real reports (CLINLOOP_SECOND_READER=1).
    """
    from .loop_detector import ClinLoopDetector
    from .second_reader import CATEGORIES, local_model, read_report, uncovered
    model = local_model()
    if model is None:
        raise HTTPException(503, "No on-premise model server (CLINLOOP_OLLAMA_URL must be a private address)")
    when = "2026-01-01T09:00:00Z"
    res = [{"resourceType": "Patient", "id": "preview", "gender": "unknown"},
           {"resourceType": "DiagnosticReport", "id": "preview-report", "status": "final",
            "category": [{"coding": [{"code": req.category}]}], "code": {"text": req.title},
            "subject": {"reference": "Patient/preview"}, "effectiveDateTime": when, "conclusion": req.text}]
    events, _ = bundle_to_events(res)
    from datetime import datetime as _dt
    rules = sorted({d.rule_id for d in ClinLoopDetector(evaluation_time=_dt(2026, 1, 2)).process_patient(
        "preview", "preview", events.get("preview", []))})
    result = read_report(req.text, model)
    new = uncovered(result["items"], set(rules)) if result["available"] else []
    return {"rules_opened": rules, "second_reader": result,
            "would_flag": [{**i, "label": CATEGORIES[i["category"]]["en"]} for i in new]}


@router.get("/imaging/scan/status", tags=["Imaging & Documents"])
def image_scan_status(user: User = Depends(require_role("viewer"))):
    """Automatic image scanning: on or off, which models may run, the last runs, and studies needing a person."""
    from .imaging_scanner import status
    return status(get_store())


@router.post("/imaging/scan/run", tags=["Imaging & Documents"])
def image_scan_run(user: User = Depends(require_role("admin"))):
    """Run one scan now (admin). Same safeguards as the background scan."""
    from .fhir_sync import client_from_env as fhir_from_env
    from .imaging_scanner import enabled, scan_once
    from .pacs_client import client_from_env as pacs_from_env
    if not enabled():
        raise HTTPException(409, "Image scanning is off (set CLINLOOP_IMAGE_SCAN=1)")
    pacs = pacs_from_env()
    if pacs is None:
        raise HTTPException(409, "No PACS configured (set CLINLOOP_PACS_DICOMWEB)")
    store = get_store()
    store._audit(user.name, user.role, "image_scan_run", None, {})
    store._db.commit()
    return scan_once(store, pacs, fhir_from_env())


@router.post("/pacs/check", tags=["Imaging & Documents"])
def pacs_check(user: User = Depends(require_role("admin"))):
    from .pacs_client import client_from_env
    client = client_from_env()
    if client is None:
        return {"status": "not_configured", "note": "Set CLINLOOP_PACS_DICOMWEB to the PACS's DICOMweb (QIDO-RS) URL"}
    return {"status": "ok" if client.ping() else "unreachable"}
