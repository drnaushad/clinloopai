"""
ct_organs.py — CT organ segmentation and measurement (whole CT series, 3-D)

One CT series (a zip of its DICOM files, or a NIfTI volume) is segmented into
organs by TotalSegmentator (Wasserthal J et al., Radiology: AI 2023; Apache-2.0,
RESEARCH USE ONLY, not a medical device). From the organ masks ClinLoop
measures, with explicit, cited thresholds:

  * aorta: maximum short-axis diameter per axial slice
        abdominal ≥ 3.0 cm  → aneurysm        (SVS 2018 AAA definition)
        thoracic  ≥ 4.0 cm  → dilatation      (ACR incidental-findings white paper, 2021)
  * spleen: craniocaudal length > 13 cm → splenomegaly (common adult upper limit)
  * every organ: volume (ml), and whether it is fully inside the scan

An abnormal measurement becomes a research-use imaging-AI finding (FHIR
Observation, device = TotalSegmentator). As with any imaging AI, it is compared
with the radiologist's report of the same study: if the report never mentions
the aorta's size or the spleen, a radiologist-review loop opens (R047). Research
findings open loops only with CLINLOOP_IMAGING_RESEARCH_AI=1.

What it deliberately does NOT do:
  * no diagnosis, nothing sent to a patient;
  * a measurement never closes a loop. The organs a CT covers are shown, but a
    chest CT that happens to include the adrenals does not close an adrenal
    follow-up: that stays a radiologist's call;
  * an organ cut off by the edge of the scan is not measured for size;
  * a NIfTI file has no PatientID, so its results are shown and never filed.

Enable: CLINLOOP_IMAGING_MODELS=totalseg (and `pip install TotalSegmentator`;
weights in TOTALSEG_HOME_DIR, baked into the Docker image with
--build-arg WITH_CT_SEGMENTATION=1). CLINLOOP_CT_SEG_FAST=0 uses the full
1.5 mm model (more precise, several minutes per CT on CPU).
"""

import gzip
import hashlib
import io
import logging
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .imaging_ai import ImagingError, dicom_summary, qa_checks
from .imaging_fhir import ai_observation_resource, dicom_datetime, imaging_study_resource

logger = logging.getLogger("clinloop.ct_organs")

MAX_SERIES_FILES = 2000
MAX_SERIES_BYTES = 1024 * 1024 * 1024        # uncompressed
MIN_SLICES = 20

PRODUCT = "TotalSegmentator"
REGULATORY = "Research use only — not a medical device (Wasserthal J et al., Radiology: AI 2023)"

ABDOMINAL_AORTA_CM = 3.0
THORACIC_AORTA_CM = 4.0
SPLEEN_LENGTH_CM = 13.0

# Organ label → body region (ClinLoop vocabulary), for the "organs covered" summary
ORGAN_REGION = {
    "liver": "liver", "gallbladder": "biliary", "spleen": "spleen", "pancreas": "pancreas",
    "kidney_left": "kidney", "kidney_right": "kidney", "adrenal_gland_left": "adrenal",
    "adrenal_gland_right": "adrenal", "urinary_bladder": "bladder", "prostate": "prostate",
    "lung_upper_lobe_left": "lung", "lung_lower_lobe_left": "lung", "lung_upper_lobe_right": "lung",
    "lung_middle_lobe_right": "lung", "lung_lower_lobe_right": "lung", "heart": "chest",
    "thyroid_gland": "thyroid", "brain": "brain", "stomach": "abdomen", "colon": "abdomen",
    "small_bowel": "abdomen", "duodenum": "abdomen", "aorta": "aorta",
}
ORGANS_SHOWN = list(ORGAN_REGION)
LUNG_OR_HEART = {"lung_upper_lobe_left", "lung_lower_lobe_left", "lung_upper_lobe_right",
                 "lung_middle_lobe_right", "lung_lower_lobe_right", "heart"}


def available() -> Optional[str]:
    try:
        import nibabel  # noqa: F401
        import totalsegmentator  # noqa: F401
    except ImportError:
        return "not installed (pip install TotalSegmentator)"
    return None


def enabled() -> bool:
    names = [n.strip().lower() for n in os.environ.get("CLINLOOP_IMAGING_MODELS", "").split(",")]
    return "totalseg" in names


def describe() -> Dict[str, Any]:
    from .imaging_fhir import is_research_use
    return {"name": PRODUCT, "version": _version(), "regulatory": REGULATORY, "research_use": is_research_use(REGULATORY),
            "intended_use": "CT series (3-D): organ volumes, aortic diameter, spleen length — for radiologist review only",
            "modalities": ["CT"], "body_regions": ["chest", "abdomen", "pelvis"], "threshold": None,
            "status": "ready" if available() is None else available()}


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("TotalSegmentator")
    except Exception:
        return ""


# ── Reading a CT series ─────────────────────────────────────────────────────

def _series_files(content: bytes) -> List[bytes]:
    """The member files of a zip (in memory: nothing is written to disk by name)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        raise ImagingError("Send the CT series as a .zip of its DICOM files, or a .nii/.nii.gz volume") from e
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_SERIES_FILES:
        raise ImagingError(f"Too many files in the zip (max {MAX_SERIES_FILES})")
    if sum(i.file_size for i in infos) > MAX_SERIES_BYTES:
        raise ImagingError("The zip is too large once unpacked")
    return [zf.read(i) for i in infos]


def read_dicom_series(content: bytes):
    """
    DICOM series (zip) → (nibabel image in RAS, header dataset of the first slice, notes).
    One series only: the largest CT series in the zip. Mixed patients are refused.
    """
    import nibabel as nib
    import pydicom

    slices = []
    for raw in _series_files(content):
        try:
            ds = pydicom.dcmread(io.BytesIO(raw), force=True)
        except Exception:
            continue
        if "PixelData" in ds and "ImagePositionPatient" in ds and "ImageOrientationPatient" in ds:
            slices.append(ds)
    if not slices:
        raise ImagingError("No CT image slices found in the zip")
    patients = {str(getattr(s, "PatientID", "") or "") for s in slices}
    if len(patients) > 1:
        raise ImagingError("The zip holds images of more than one patient: nothing was read")
    notes = []
    by_series = Counter(str(getattr(s, "SeriesInstanceUID", "")) for s in slices)
    series_uid, _ = by_series.most_common(1)[0]
    if len(by_series) > 1:
        notes.append(f"{len(by_series)} series in the zip: the largest ({by_series[series_uid]} images) was used")
    slices = [s for s in slices if str(getattr(s, "SeriesInstanceUID", "")) == series_uid]
    modality = str(getattr(slices[0], "Modality", "") or "").upper()
    if modality != "CT":
        raise ImagingError(f"Organ measurement needs a CT series (this is {modality or 'unknown'})")

    iop = np.array([float(x) for x in slices[0].ImageOrientationPatient])
    row_cos, col_cos = iop[:3], iop[3:]
    normal = np.cross(row_cos, col_cos)
    slices.sort(key=lambda s: float(np.dot(normal, [float(x) for x in s.ImagePositionPatient])))
    positions = np.array([np.dot(normal, [float(x) for x in s.ImagePositionPatient]) for s in slices])
    gaps = np.diff(positions)
    if len(slices) < MIN_SLICES:
        raise ImagingError(f"Only {len(slices)} slices: organ measurement needs a CT volume (≥ {MIN_SLICES} slices)")
    if np.any(gaps <= 1e-3):
        raise ImagingError("Duplicate slice positions (several acquisitions mixed?): send a single series")
    step = float(np.median(gaps))
    if np.max(np.abs(gaps - step)) > 0.1 * step:
        notes.append("uneven slice spacing: measurements along the body axis are approximate")
    rows, cols = int(slices[0].Rows), int(slices[0].Columns)
    if any(int(s.Rows) != rows or int(s.Columns) != cols for s in slices):
        raise ImagingError("Slices of different sizes in one series")

    vol = np.empty((cols, rows, len(slices)), dtype=np.float32)    # (i = column, j = row, k = slice)
    for k, s in enumerate(slices):
        arr = s.pixel_array.astype(np.float32)
        arr = arr * float(getattr(s, "RescaleSlope", 1) or 1) + float(getattr(s, "RescaleIntercept", 0) or 0)
        vol[:, :, k] = arr.T
    dr, dc = (float(x) for x in slices[0].PixelSpacing)                 # row spacing, column spacing
    origin = np.array([float(x) for x in slices[0].ImagePositionPatient])
    affine = np.eye(4)
    affine[:3, 0] = row_cos * dc            # along a row: next column
    affine[:3, 1] = col_cos * dr            # down a column: next row
    affine[:3, 2] = normal * step
    affine[:3, 3] = origin
    affine = np.diag([-1, -1, 1, 1]) @ affine        # DICOM LPS → NIfTI RAS
    img = nib.as_closest_canonical(nib.Nifti1Image(vol, affine))
    return img, slices[0], notes


def read_nifti(content: bytes):
    import nibabel as nib
    raw = gzip.decompress(content) if content[:2] == b"\x1f\x8b" else content
    try:
        img = nib.Nifti1Image.from_bytes(raw)
    except Exception as e:
        raise ImagingError(f"Not a readable NIfTI volume ({type(e).__name__})") from e
    if img.ndim != 3 or min(img.shape) < 2:
        raise ImagingError("A 3-D CT volume is needed")
    return nib.as_closest_canonical(img)


# ── Segmentation ─────────────────────────────────────────────────────────────

Segmenter = Callable[[Any], Tuple[Any, Dict[int, str]]]


def _segment_file(in_path: str, out_path: str, fast: bool, device: str) -> None:
    """Runs in a fresh process: TotalSegmentator on one NIfTI file."""
    import nibabel as nib
    from totalsegmentator.python_api import totalsegmentator
    _no_usage_stats()
    seg = totalsegmentator(nib.load(in_path), None, ml=True, fast=fast, device=device, quiet=True)
    nib.save(seg, out_path)


def totalsegmentator_segmenter(img) -> Tuple[Any, Dict[int, str]]:
    """
    TotalSegmentator 'total' task; returns (label image, label → organ name).

    Each CT runs in its own short-lived process: nnU-Net's internal
    multiprocessing deadlocks when called repeatedly inside a threaded web
    server, and a separate process also keeps the model's memory (and any
    crash) out of the API. CLINLOOP_CT_SEG_TIMEOUT (s) bounds a run.
    """
    import multiprocessing
    import tempfile
    import nibabel as nib
    from totalsegmentator.map_to_binary import class_map
    fast = os.environ.get("CLINLOOP_CT_SEG_FAST", "1").strip() not in ("0", "false", "no")
    device = os.environ.get("CLINLOOP_CT_SEG_DEVICE", "cpu")
    timeout = float(os.environ.get("CLINLOOP_CT_SEG_TIMEOUT", "900"))
    with tempfile.TemporaryDirectory(prefix="clinloop-ct-") as tmp:
        in_path, out_path = os.path.join(tmp, "ct.nii.gz"), os.path.join(tmp, "seg.nii.gz")
        nib.save(img, in_path)
        proc = multiprocessing.get_context("spawn").Process(target=_segment_file,
                                                            args=(in_path, out_path, fast, device), daemon=False)
        proc.start()
        proc.join(timeout)
        if proc.is_alive():
            proc.terminate()
            proc.join(10)
            raise ImagingError(f"CT segmentation took longer than {timeout:g} s and was stopped")
        if proc.exitcode != 0 or not os.path.exists(out_path):
            raise ImagingError(f"CT segmentation failed (exit code {proc.exitcode})")
        seg = nib.load(out_path)
        seg = nib.Nifti1Image(np.asarray(seg.dataobj), seg.affine, seg.header)     # read before the folder goes
    return nib.as_closest_canonical(seg), dict(class_map["total"])


def _no_usage_stats() -> None:
    """TotalSegmentator reports run counts to its authors' server by default: a hospital system must not phone home."""
    try:
        from totalsegmentator.config import get_config_key, set_config_key, setup_totalseg
        setup_totalseg()
        if get_config_key("send_usage_stats") is not False:
            set_config_key("send_usage_stats", False)
    except Exception as e:      # read-only home: the Docker image disables it at build time
        logger.debug("Could not update TotalSegmentator config: %s", e)


# ── Measurements ────────────────────────────────────────────────────────────

def _short_axis_cm(mask2d: np.ndarray, dx: float, dy: float) -> Tuple[float, float]:
    """(short-axis, long-axis) diameter in cm of one cross-section, from its second moments (ellipse fit)."""
    ys, xs = np.nonzero(mask2d)
    pts = np.stack([xs * dx, ys * dy], axis=1)
    if len(pts) < 3:
        d = 2 * np.sqrt(len(pts) * dx * dy / np.pi) / 10
        return d, d
    cov = np.cov(pts, rowvar=False) + np.eye(2) * (dx * dy / 12)    # + pixel-size term
    ev = np.sort(np.linalg.eigvalsh(cov))
    return 4 * np.sqrt(ev[0]) / 10, 4 * np.sqrt(ev[1]) / 10


def measure(seg, labels: Dict[int, str]) -> Dict[str, Any]:
    """Organ volumes, coverage and the aorta and spleen measurements from a label image in RAS."""
    from scipy import ndimage
    data = np.asarray(seg.dataobj).astype(np.int32)
    dx, dy, dz = (float(z) for z in seg.header.get_zooms()[:3])
    voxel_ml = dx * dy * dz / 1000.0
    name_to_label = {v: k for k, v in labels.items()}
    nz = data.shape[2]

    organs, covered = [], set()
    counts = np.bincount(data.ravel(), minlength=max(labels) + 1)
    for name in ORGANS_SHOWN:
        lab = name_to_label.get(name)
        if lab is None or counts[lab] == 0:
            continue
        zs = np.nonzero(np.any(data == lab, axis=(0, 1)))[0]
        complete = bool(zs.min() > 0 and zs.max() < nz - 1)
        organs.append({"organ": name, "volume_ml": round(float(counts[lab]) * voxel_ml, 1),
                       "craniocaudal_cm": round(float(zs.max() - zs.min() + 1) * dz / 10, 1), "complete": complete})
        covered.add(ORGAN_REGION[name])

    findings: List[Dict[str, Any]] = []
    measurements: Dict[str, Any] = {}
    tolerance_cm = max(dx, dy) / 10

    # Aorta: short-axis diameter per axial slice; thoracic where lung or heart is in the slice
    lab = name_to_label.get("aorta")
    thorax_labels = [name_to_label[n] for n in LUNG_OR_HEART if n in name_to_label]
    if lab is not None and counts[lab] > 0:
        best = {"abdominal": None, "thoracic": None}
        n_slices = 0
        for k in range(nz):
            sl = data[:, :, k] == lab
            if not sl.any():
                continue
            n_slices += 1
            part = "thoracic" if np.isin(data[:, :, k], thorax_labels).any() else "abdominal"
            comps, n = ndimage.label(sl)
            for c in range(1, n + 1):
                m = comps == c
                if m.sum() * dx * dy < 50:                        # < 0.5 cm²: fragment
                    continue
                short, long_ = _short_axis_cm(m, dx, dy)
                if long_ > 1.6 * short:                          # oblique cut (arch, bifurcation): not a cross-section
                    continue
                if best[part] is None or short > best[part]["diameter_cm"]:
                    best[part] = {"diameter_cm": round(float(short), 1), "slice": int(k)}
        measurements["aorta"] = {"abdominal_max_cm": (best["abdominal"] or {}).get("diameter_cm"),
                                 "thoracic_max_cm": (best["thoracic"] or {}).get("diameter_cm"),
                                 "slices": n_slices, "precision_cm": round(tolerance_cm, 2),
                                 "method": "short-axis diameter of each axial cross-section (ellipse fit)"}
        # One aortic finding per CT (abdominal and/or thoracic), so one review and one record
        over = []
        for part, limit, body in (("abdominal", ABDOMINAL_AORTA_CM, "ABDOMEN"), ("thoracic", THORACIC_AORTA_CM, "CHEST")):
            b = best[part]
            if b and b["diameter_cm"] >= limit and n_slices >= 5:
                over.append((part, b["diameter_cm"], limit, body))
        if over:
            worst = max(over, key=lambda x: x[1] - x[2])
            names = {"abdominal": "Abdominal aortic aneurysm", "thoracic": "Thoracic aortic dilatation"}
            findings.append({
                "label": " and ".join(names[p] for p, *_ in over) + " ("
                         + "; ".join(f"{p} aorta {d:.1f} cm ≥ {lim:.1f} cm" for p, d, lim, _ in over) + ")",
                "finding_key": "aortic_aneurysm", "body_part": ", ".join(x[3] for x in over),
                "value_cm": worst[1], "threshold_cm": worst[2], "borderline": all(d - lim < tolerance_cm for _, d, lim, _ in over),
            })

    lab = name_to_label.get("spleen")
    spleen = next((o for o in organs if o["organ"] == "spleen"), None)
    if lab is not None and spleen:
        measurements["spleen"] = {"craniocaudal_cm": spleen["craniocaudal_cm"], "volume_ml": spleen["volume_ml"],
                                  "complete": spleen["complete"]}
        if spleen["complete"] and spleen["craniocaudal_cm"] > SPLEEN_LENGTH_CM:
            findings.append({
                "label": f"Splenomegaly (spleen {spleen['craniocaudal_cm']:.1f} cm craniocaudal > {SPLEEN_LENGTH_CM:.0f} cm)",
                "finding_key": "splenomegaly", "body_part": "ABDOMEN", "value_cm": spleen["craniocaudal_cm"],
                "threshold_cm": SPLEEN_LENGTH_CM, "borderline": spleen["craniocaudal_cm"] - SPLEEN_LENGTH_CM < dz / 10,
            })
    return {"organs": organs, "covered_regions": sorted(covered), "measurements": measurements, "findings": findings,
            "voxel_mm": [round(dx, 2), round(dy, 2), round(dz, 2)]}


# ── One series, end to end ──────────────────────────────────────────────────

def analyze_ct_series(content: bytes, filename: str, patient_id: str, expected_patient_ids: List[str],
                      segmenter: Optional[Segmenter] = None) -> Dict[str, Any]:
    """
    Segment and measure one CT series. Returns the measurements, QA checks and,
    for a DICOM series of the right patient, the FHIR resources to file.
    """
    name = (filename or "").lower()
    is_nifti = name.endswith((".nii", ".nii.gz")) or content[:2] == b"\x1f\x8b" or content[344:348] in (b"n+1\x00", b"ni1\x00")
    notes: List[str] = []
    header = None
    if is_nifti:
        img = read_nifti(content)
        qa = [{"level": "critical", "code": "no_patient_id",
               "message": "A NIfTI volume carries no PatientID, so it cannot be verified to belong to this patient. "
                          "Measurements are shown; nothing was filed. Send the DICOM series to file results."}]
        summary = {"modality": "CT", "study_uid": None, "series_uid": None, "body_part": "", "regions": []}
    else:
        img, header, notes = read_dicom_series(content)
        summary = dicom_summary(header)
        qa = qa_checks(header, summary, expected_patient_ids, "CT")

    if segmenter is None:
        reason = available()
        if reason:
            raise ImagingError(f"CT organ measurement is unavailable: TotalSegmentator {reason}")
        segmenter = totalsegmentator_segmenter
    seg, labels = segmenter(img)
    if tuple(seg.shape[:3]) != tuple(img.shape[:3]):
        raise ImagingError("Segmentation does not match the CT volume")
    result = measure(seg, labels)
    if not result["organs"]:
        qa.append({"level": "warning", "code": "no_organs",
                   "message": "No organs were found: is this a body CT (chest, abdomen or pelvis)?"})
    for o in result["organs"]:
        if o["organ"] == "spleen" and not o["complete"]:
            qa.append({"level": "info", "code": "spleen_cut_off",
                       "message": "The spleen is cut off by the edge of the scan: its size is not judged."})
        if o["organ"] == "aorta" and not o["complete"]:
            qa.append({"level": "info", "code": "aorta_partial",
                       "message": "The aorta continues beyond the scan: only the part inside the scan was measured."})

    critical = [c for c in qa if c["level"] == "critical"]
    resources: List[Dict[str, Any]] = []
    if not critical and header is not None:
        when = (dicom_datetime(summary["study_date"], summary["study_time"], summary["tz_offset"])
                or datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat())
        study = imaging_study_resource({
            "study_uid": summary["study_uid"], "accession": summary["accession"], "modalities": ["CT"],
            "description": summary["study_description"] or summary["series_description"],
            "study_date": summary["study_date"], "study_time": summary["study_time"], "tz_offset": summary["tz_offset"],
            "series": [{"uid": summary["series_uid"] or "", "modality": "CT",
                        "description": summary["series_description"], "body_part": summary["body_part"]}],
        }, patient_id, source="dicom-upload")
        resources.append(study)
        for f in result["findings"]:
            obs = ai_observation_resource(patient_id, f["label"], None, True, PRODUCT, _version(), REGULATORY,
                                          f"ImagingStudy/{study['id']}", when, body_part=f["body_part"],
                                          source="imaging-ai", finding_key=f["finding_key"],
                                          study_uid=summary["study_uid"])
            # The measurement, not a probability: a component, so it is never read as a model score
            obs["method"] = {"text": "CT organ segmentation and measurement (second reader)"}
            obs["component"] = [{"code": {"text": "aorta short-axis diameter" if f["finding_key"] == "aortic_aneurysm"
                                          else "spleen craniocaudal length"},
                                 "valueQuantity": {"value": f["value_cm"], "unit": "cm",
                                                   "system": "http://unitsofmeasure.org", "code": "cm"},
                                 "referenceRange": [{"text": f"threshold {f['threshold_cm']:g} cm"}]}]
            resources.append(obs)

    return {"summary": {k: summary.get(k) for k in ("modality", "study_uid", "series_uid", "body_part", "regions",
                                                    "study_date", "study_description", "series_description")},
            "shape": list(img.shape), "notes": notes, "qa": qa, "model": describe(), **result,
            "filed": not critical and header is not None, "resources": resources,
            "sha256": hashlib.sha256(content).hexdigest()}
