"""
imaging_ai.py — On-premise analysis of DICOM images (X-ray, CT, MRI, ultrasound)

What it does with one DICOM file:

  1. Reads the header: modality, body part, description, date, view, image type.
  2. Safety checks that need no AI (and catch real errors):
       * the image's PatientID does not match the selected patient  → refused
       * screenshot / secondary capture instead of an original acquisition
       * identifiers burned into the pixels
       * body part or date missing (follow-up matching would be unreliable)
  3. Records the study (FHIR ImagingStudy): "a chest radiograph was done".
  4. Runs the imaging models the hospital has enabled for that modality and
     body part, and records each finding as a FHIR Observation, so a finding
     the radiologist's report does not address opens a review loop (R047).

Models (CLINLOOP_IMAGING_MODELS, comma-separated):
  * txrv    TorchXRayVision DenseNet-121 (Cohen et al., MIDL 2022), chest
            radiographs, 18 findings. RESEARCH USE ONLY: not a medical device.
            Needs `pip install torchxrayvision` and its weights (downloaded once).
  * vendor models over HTTP (CLINLOOP_IMAGING_MODELS_CONFIG = JSON file),
    e.g. an MFDS-approved product's on-premise inference endpoint, for any
    modality (CT, MRI, ultrasound, mammography). ClinLoop POSTs the DICOM
    file and reads {"findings": [{"label", "score", "positive"?}]}.

The AI is a second reader. It never diagnoses, never reaches the patient, and
its findings only ever ask a radiologist to look again. Pixel data is never
stored; only the header summary and the findings are.
"""

import base64
import hashlib
import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from .imaging_fhir import (
    DICOM_MODALITY, ai_finding_key, ai_observation_resource, dicom_regions, dicom_datetime,
    imaging_study_resource, is_research_use,
)

logger = logging.getLogger("clinloop.imaging_ai")
MAX_DICOM_BYTES = 200 * 1024 * 1024


class ImagingError(ValueError):
    pass


# ── Reading DICOM ───────────────────────────────────────────────────────────

def read_dicom(content: bytes):
    try:
        import pydicom
    except ImportError as e:
        raise ImagingError("pydicom is not installed on the server") from e
    if not content:
        raise ImagingError("Empty file")
    if len(content) > MAX_DICOM_BYTES:
        raise ImagingError("DICOM file too large")
    try:
        ds = pydicom.dcmread(io.BytesIO(content), force=True)
    except Exception as e:
        raise ImagingError(f"Not a readable DICOM file ({type(e).__name__})") from e
    # force=True reads almost anything: require the basic identity of a DICOM object
    if not any(t in ds for t in ("SOPClassUID", "StudyInstanceUID", "Modality")):
        raise ImagingError("Not a DICOM file (no SOP Class, Study UID or Modality)")
    return ds


def _get(ds, name: str, default=None):
    v = getattr(ds, name, default)
    if v is None or v == "":
        return default
    if isinstance(v, (list, tuple)) or v.__class__.__name__ == "MultiValue":
        return [str(x) for x in v]
    return str(v)


def dicom_summary(ds) -> Dict[str, Any]:
    """Header facts ClinLoop uses. Patient name and birth date are never returned."""
    modality = (_get(ds, "Modality") or "").upper()
    body = _get(ds, "BodyPartExamined") or ""
    desc = _get(ds, "StudyDescription") or ""
    sdesc = _get(ds, "SeriesDescription") or ""
    image_type = _get(ds, "ImageType") or []
    return {
        "modality": modality, "modality_kind": DICOM_MODALITY.get(modality),
        "body_part": body, "study_description": desc, "series_description": sdesc,
        "regions": dicom_regions(body, desc, sdesc),
        "study_uid": _get(ds, "StudyInstanceUID"), "series_uid": _get(ds, "SeriesInstanceUID"),
        "accession": _get(ds, "AccessionNumber"),
        "study_date": _get(ds, "StudyDate") or _get(ds, "AcquisitionDate") or _get(ds, "SeriesDate"),
        "tz_offset": _get(ds, "TimezoneOffsetFromUTC"),
        "study_time": _get(ds, "StudyTime") or _get(ds, "AcquisitionTime"),
        "view_position": _get(ds, "ViewPosition"), "laterality": _get(ds, "ImageLaterality") or _get(ds, "Laterality"),
        "image_type": image_type if isinstance(image_type, list) else [image_type],
        "rows": int(getattr(ds, "Rows", 0) or 0), "columns": int(getattr(ds, "Columns", 0) or 0),
        "frames": int(getattr(ds, "NumberOfFrames", 1) or 1),
        "photometric": _get(ds, "PhotometricInterpretation"),
        "manufacturer": _get(ds, "Manufacturer"),
        "burned_in_annotation": (_get(ds, "BurnedInAnnotation") or "").upper() == "YES",
        "has_pixels": "PixelData" in ds,
    }


def qa_checks(ds, summary: Dict[str, Any], expected_patient_ids: List[str],
              expected_modality: Optional[str] = None) -> List[Dict[str, str]]:
    """Non-diagnostic safety checks. 'critical' means the image must not be filed to this patient."""
    checks: List[Dict[str, str]] = []
    pid = _get(ds, "PatientID")
    if expected_patient_ids:
        if not pid:
            checks.append({"level": "critical", "code": "no_patient_id",
                           "message": "The image has no PatientID, so it cannot be verified to belong to this patient. "
                                      "Nothing was filed."})
        elif pid not in expected_patient_ids:
            checks.append({"level": "critical", "code": "patient_mismatch",
                           "message": "The PatientID in the image does not match the selected patient. "
                                      "Nothing was filed. Check for a wrong-patient image."})
    if expected_modality and summary["modality"] and expected_modality.upper() != summary["modality"]:
        checks.append({"level": "warning", "code": "modality_mismatch",
                       "message": f"Expected {expected_modality.upper()}, the image is {summary['modality']}."})
    if any(t.upper() in ("DERIVED", "SECONDARY") for t in summary["image_type"]) or \
            str(_get(ds, "SOPClassUID") or "").startswith("1.2.840.10008.5.1.4.1.1.7"):
        checks.append({"level": "warning", "code": "not_original",
                       "message": "Secondary capture or derived image (e.g. a screenshot or reformat), "
                                  "not an original acquisition: AI results may be unreliable."})
    if summary["burned_in_annotation"]:
        checks.append({"level": "warning", "code": "burned_in_phi",
                       "message": "Identifiers are burned into the pixels: do not share this image outside the hospital."})
    if not summary["has_pixels"]:
        checks.append({"level": "warning", "code": "no_pixels", "message": "No pixel data: only the header was read."})
    if not summary["regions"]:
        checks.append({"level": "warning", "code": "region_unknown",
                       "message": "Body part not stated: this study cannot close region-specific follow-ups."})
    if not summary["study_date"]:
        checks.append({"level": "warning", "code": "date_unknown",
                       "message": "Study date missing: the upload time is used."})
    elif summary["study_date"] > datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d"):
        checks.append({"level": "warning", "code": "date_in_future", "message": "Study date is in the future."})
    return checks


def pixel_image(ds) -> Optional[np.ndarray]:
    """2-D float image in [0, 1] as a radiologist would view it (rescale, window, MONOCHROME1 inverted)."""
    if "PixelData" not in ds:
        return None
    from pydicom.pixels import apply_modality_lut, apply_voi_lut
    arr = ds.pixel_array
    colour = int(getattr(ds, "SamplesPerPixel", 1) or 1) > 1
    if arr.ndim == 4 or (arr.ndim == 3 and not colour):            # multi-frame: middle frame
        arr = arr[arr.shape[0] // 2]
    if arr.ndim == 3:                                               # colour (e.g. ultrasound)
        arr = arr[..., :3].astype(np.float32).mean(axis=-1)
    else:
        arr = apply_modality_lut(arr, ds)
        try:
            arr = apply_voi_lut(arr, ds) if "WindowCenter" in ds or "VOILUTSequence" in ds else arr
        except Exception:
            pass
    arr = arr.astype(np.float32)
    lo, hi = np.percentile(arr, 0.5), np.percentile(arr, 99.5)
    arr = np.clip((arr - lo) / (hi - lo if hi > lo else 1.0), 0, 1)
    if str(getattr(ds, "PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        arr = 1.0 - arr
    return arr


def _safe_preview(img: Optional[np.ndarray]) -> Optional[str]:
    if img is None or img.ndim != 2:
        return None
    try:
        return preview_png(img)
    except Exception as e:          # a preview must never stop the analysis
        logger.warning("Preview failed: %s", e)
        return None


def preview_png(img: np.ndarray, size: int = 512) -> str:
    from PIL import Image
    pil = Image.fromarray((img * 255).astype(np.uint8))
    pil.thumbnail((size, size))
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ── Models ──────────────────────────────────────────────────────────────────

class ImagingModel:
    name = "model"
    version = ""
    regulatory = "not stated"
    intended_use = ""
    modalities: List[str] = []
    body_regions: List[str] = []
    threshold = 0.5

    def available(self) -> Optional[str]:
        """None when ready, else the reason it is not."""
        return None

    def applies(self, summary: Dict[str, Any]) -> Optional[str]:
        """None when the model applies to this image, else why not."""
        if self.modalities and summary["modality"] not in self.modalities:
            return f"for {', '.join(self.modalities)} only"
        if self.body_regions and not set(self.body_regions) & set(summary["regions"]):
            return f"for {', '.join(self.body_regions)} only"
        return None

    def predict(self, ds, img: np.ndarray, content: bytes) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "version": self.version, "regulatory": self.regulatory,
                "research_use": is_research_use(self.regulatory), "intended_use": self.intended_use,
                "modalities": self.modalities, "body_regions": self.body_regions, "threshold": self.threshold,
                "status": "ready" if self.available() is None else self.available()}


class TorchXRayVisionModel(ImagingModel):
    name = "TorchXRayVision DenseNet-121 (all)"
    version = "densenet121-res224-all"
    regulatory = "Research use only — not a medical device (Cohen JP et al., MIDL 2022)"
    intended_use = "Frontal chest radiographs (PA/AP): 18 findings, as a second reader for review only"
    modalities = ["CR", "DX", "DR"]
    body_regions = ["chest"]
    threshold = 0.5          # the weights are calibrated so 0.5 is each finding's operating point
    _model = None

    def available(self) -> Optional[str]:
        try:
            import torch  # noqa: F401
            import torchxrayvision  # noqa: F401
        except ImportError:
            return "not installed (pip install torch torchxrayvision)"
        return None

    def applies(self, summary):
        reason = super().applies(summary)
        if reason:
            return reason
        if (summary.get("view_position") or "").upper() in ("LL", "RL", "LAT", "LATERAL"):
            return "frontal views only"
        if summary.get("photometric") not in ("MONOCHROME1", "MONOCHROME2"):
            return "greyscale radiographs only"
        return None

    def _load(self):
        if TorchXRayVisionModel._model is None:
            import torchxrayvision as xrv
            # CLINLOOP_MODEL_DIR: pre-installed weights for hospitals without internet access
            model = xrv.models.DenseNet(weights=self.version, cache_dir=os.environ.get("CLINLOOP_MODEL_DIR") or None)
            model.eval()
            TorchXRayVisionModel._model = model
        return TorchXRayVisionModel._model

    def predict(self, ds, img, content):
        import torch
        import torchxrayvision as xrv
        model = self._load()
        # The authors' own DICOM reader: raw pixels scaled by 2^BitsStored to [-1024, 1024].
        # (The display image is contrast-stretched; a model must see what it was trained on.)
        x = xrv.utils.read_xray_dcm(io.BytesIO(content))
        if x.ndim == 3:
            x = x[x.shape[0] // 2]
        h, w = x.shape
        side = min(h, w)                                   # centre crop to a square
        x = x[(h - side) // 2:(h - side) // 2 + side, (w - side) // 2:(w - side) // 2 + side]
        t = torch.from_numpy(x.astype(np.float32))[None, None]
        t = torch.nn.functional.interpolate(t, size=(224, 224), mode="area")
        with torch.no_grad():
            out = model(t)[0].numpy()
        return [{"label": p, "score": float(s)} for p, s in zip(model.pathologies, out) if p]


class HTTPImagingModel(ImagingModel):
    """An approved product's on-premise inference endpoint (DICOM in, JSON findings out)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.name = cfg["name"]
        self.version = str(cfg.get("version", ""))
        self.regulatory = cfg.get("regulatory", "not stated")
        self.intended_use = cfg.get("intended_use", "")
        self.modalities = [m.upper() for m in cfg.get("modalities", [])]
        self.body_regions = cfg.get("body_regions", [])
        self.threshold = float(cfg.get("threshold", 0.5))
        self.url = cfg["url"]
        self.token = os.environ.get(cfg["token_env"]) if cfg.get("token_env") else None
        self.label_map = cfg.get("label_map", {})
        self.timeout = float(cfg.get("timeout", 60))

    def predict(self, ds, img, content):
        import requests
        headers = {"Content-Type": "application/dicom", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        r = requests.post(self.url, data=content, headers=headers, timeout=self.timeout)
        if r.status_code != 200:
            raise ImagingError(f"{self.name}: HTTP {r.status_code}")
        out = []
        for f in (r.json() or {}).get("findings", []):
            label = self.label_map.get(f.get("label"), f.get("label"))
            if label:
                out.append({"label": label, "score": f.get("score"), "positive": f.get("positive")})
        return out


def registered_models() -> List[ImagingModel]:
    models: List[ImagingModel] = []
    names = [n.strip().lower() for n in os.environ.get("CLINLOOP_IMAGING_MODELS", "").split(",") if n.strip()]
    if "txrv" in names:
        models.append(TorchXRayVisionModel())
    path = os.environ.get("CLINLOOP_IMAGING_MODELS_CONFIG")
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                models.extend(HTTPImagingModel(cfg) for cfg in json.load(f))
        except (OSError, ValueError, KeyError) as e:
            logger.error("Imaging model config %s unreadable: %s", path, e)
    return models


# ── One file, end to end ────────────────────────────────────────────────────

def analyze_dicom(content: bytes, patient_id: str, expected_patient_ids: Optional[List[str]] = None,
                  expected_modality: Optional[str] = None, models: Optional[List[ImagingModel]] = None,
                  with_preview: bool = True) -> Dict[str, Any]:
    """Header summary, QA checks, model findings and the FHIR resources to file (if safe to file)."""
    ds = read_dicom(content)
    summary = dicom_summary(ds)
    qa = qa_checks(ds, summary, expected_patient_ids if expected_patient_ids is not None else [patient_id],
                   expected_modality)
    img = None
    if summary["has_pixels"]:
        try:
            img = pixel_image(ds)
        except Exception as e:
            qa.append({"level": "warning", "code": "pixels_unreadable",
                       "message": f"Pixel data could not be decoded ({type(e).__name__}): models skipped."})
    when = dicom_datetime(summary["study_date"], summary["study_time"], summary["tz_offset"]) or datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    study = imaging_study_resource({
        "study_uid": summary["study_uid"], "accession": summary["accession"],
        "modalities": [summary["modality"]] if summary["modality"] else [],
        "description": summary["study_description"] or summary["series_description"],
        "study_date": summary["study_date"], "study_time": summary["study_time"], "tz_offset": summary["tz_offset"],
        "series": [{"uid": summary["series_uid"] or "", "modality": summary["modality"],
                    "description": summary["series_description"], "body_part": summary["body_part"]}],
    }, patient_id, source="dicom-upload")
    study_ref = f"ImagingStudy/{study['id']}"

    model_results, observations = [], []
    for model in (models if models is not None else registered_models()):
        info = model.describe()
        reason = model.available() or model.applies(summary) or (None if img is not None else "no image")
        if reason:
            model_results.append({**info, "ran": False, "reason": reason, "findings": []})
            continue
        try:
            raw = model.predict(ds, img, content)
        except Exception as e:
            logger.warning("Imaging model %s failed: %s", model.name, e)
            model_results.append({**info, "ran": False, "reason": f"failed: {type(e).__name__}", "findings": []})
            continue
        # One observation per finding type: the strongest of the labels that mean it (e.g. "Nodule", "Mass")
        by_key: Dict[str, Dict[str, Any]] = {}
        findings = []
        for f in raw:
            try:
                score = float(f["score"]) if f.get("score") is not None else None
            except (TypeError, ValueError):
                score = None
            positive = f.get("positive")
            if isinstance(positive, str):
                positive = positive.strip().lower() in ("true", "1", "yes", "positive", "pos")
            if positive is None and isinstance(score, (int, float)):
                positive = score >= model.threshold
            key = ai_finding_key(f["label"], summary["regions"])
            findings.append({"label": f["label"], "score": score, "positive": bool(positive), "finding_key": key})
            k = key or f["label"]
            if positive and (k not in by_key or (score or 0) > (by_key[k]["score"] or 0)):
                by_key[k] = {"label": f["label"], "score": score}
        for k, best in by_key.items():
            labels = " / ".join(sorted({x["label"] for x in findings if (x["finding_key"] or x["label"]) == k and x["positive"]}))
            observations.append(ai_observation_resource(
                patient_id, labels, best["score"], True, model.name, model.version, model.regulatory,
                study_ref, when, body_part=summary["body_part"] or None, source="imaging-ai",
                finding_key=k, study_uid=summary["study_uid"]))
        findings.sort(key=lambda x: -(x["score"] if isinstance(x["score"], float) else 0))
        model_results.append({**info, "ran": True, "findings": findings})

    critical = [c for c in qa if c["level"] == "critical"]
    return {
        "summary": summary, "qa": qa, "models": model_results,
        "filed": not critical,
        "resources": [] if critical else [study] + observations,
        "preview": _safe_preview(img) if with_preview else None,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


# ── Results that an approved product sends as DICOM SR ─────────────────────

def parse_dicom_sr(content: bytes) -> Dict[str, Any]:
    """
    Findings from a DICOM Structured Report written by an imaging-AI product (best effort).

    Walks the content tree: CODE items whose concept name mentions "finding" give
    the label; a NUM item in the same container whose concept name mentions
    probability/likelihood/score/confidence gives its score. Vendors differ, so a
    hospital should check the result for its product once (the label_map of an
    HTTP model, or a vendor FHIR feed, avoids the guesswork).
    """
    ds = read_dicom(content)
    findings: List[Dict[str, Any]] = []

    def meaning(seq) -> str:
        try:
            return str(seq[0].CodeMeaning)
        except (AttributeError, IndexError, TypeError):
            return ""

    def score_of(it) -> Optional[Dict[str, Any]]:
        name = meaning(getattr(it, "ConceptNameCodeSequence", None)).lower()
        if str(getattr(it, "ValueType", "")) != "NUM" or not any(k in name for k in ("probab", "likelihood", "score", "confidence")):
            return None
        try:
            mv = it.MeasuredValueSequence[0]
            v = float(mv.NumericValue)
            unit = meaning(getattr(mv, "MeasurementUnitsCodeSequence", None)).strip().lower()
        except (AttributeError, IndexError, ValueError, TypeError):
            return None
        if unit in ("%", "percent"):
            return {"score": v / 100.0}
        if 0 <= v <= 1:
            return {"score": v}
        return {"score": None, "raw_score": v, "unit": unit or None}     # unknown scale: never rescaled by guess

    def walk(items):
        """Each CODE finding takes the score inside it, else the next score before another finding."""
        pending = None
        for it in items or []:
            vt = str(getattr(it, "ValueType", ""))
            name = meaning(getattr(it, "ConceptNameCodeSequence", None)).lower()
            if vt == "CODE" and any(k in name for k in ("finding", "abnormality", "detection")):
                f = {"label": meaning(getattr(it, "ConceptCodeSequence", None)), "score": None}
                for child in getattr(it, "ContentSequence", None) or []:
                    sc = score_of(child)
                    if sc:
                        f.update(sc)
                        break
                if f["label"]:
                    findings.append(f)
                    pending = f if f["score"] is None and "raw_score" not in f else None
                continue
            sc = score_of(it)
            if sc and pending is not None:
                pending.update(sc)
                pending = None
                continue
            if hasattr(it, "ContentSequence") and vt == "CONTAINER":
                walk(it.ContentSequence)

    walk(getattr(ds, "ContentSequence", None))
    return {"product": " ".join(filter(None, [_get(ds, "Manufacturer"), _get(ds, "ManufacturerModelName"),
                                              _get(ds, "SoftwareVersions") if isinstance(_get(ds, "SoftwareVersions"), str) else None])) or "imaging AI (DICOM SR)",
            "study_uid": _get(ds, "StudyInstanceUID"), "patient_id": _get(ds, "PatientID"),
            "study_date": _get(ds, "StudyDate") or _get(ds, "ContentDate"), "study_time": _get(ds, "StudyTime"),
            # An SR lists what the product detected: a finding without a usable score is still a detection
            "findings": [{**f, "positive": True if f.get("score") is None else None} for f in findings]}
