"""
imaging_scanner.py — Automatic image scanning: new PACS studies → the hospital's imaging AI → review loops

OFF unless the hospital turns it on (CLINLOOP_IMAGE_SCAN=1) and a PACS is
configured (CLINLOOP_PACS_DICOMWEB). Each run:

  1. Asks the PACS (QIDO-RS) for studies acquired in the last
     CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS days, for the configured modalities.
     A study acquired less than CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES ago is left
     for the next run (its images may still be arriving).
  2. Matches the study's PatientID to exactly ONE patient on the FHIR server
     (MRN, or the identifier system in CLINLOOP_PACS_ID_SYSTEM). No match, or
     more than one: the study is not analysed and is listed for a person to
     check. A patient is never guessed.
  3. Chooses the series an enabled model applies to (modality, body part).
     No applicable model: no image is retrieved at all.
  4. Retrieves those images (WADO-RS), in memory only, and checks every image's
     header against the patient (a wrong-patient image stops the study).
  5. Runs the models: single-image products per image (chest X-ray,
     mammography), whole-series products per series (CT, MRI).
  6. Files the study and each positive finding (FHIR ImagingStudy and
     Observation; never the pixels) and re-checks the patient. When the
     radiologist's report arrives and does not address a finding, R047 asks a
     radiologist to look again. The AI never diagnoses and never reaches the
     patient.

Which models run: only those with a stated regulatory approval. A research-use
model (or one with no stated approval) runs automatically only with
CLINLOOP_IMAGE_SCAN_RESEARCH=1, for shadow-mode evaluation; its findings still
open no loops unless CLINLOOP_IMAGING_RESEARCH_AI=1.

Every study is recorded once in a ledger (image_scan_studies): scanned,
no_model, unmatched, refused or failed. Failed and unmatched studies are
retried on later runs, up to MAX_ATTEMPTS. Runs are recorded apart from the
FHIR feed monitor, so a working scanner can never hide a dead record feed.

Configuration (environment):
  CLINLOOP_IMAGE_SCAN=1                   turn scanning on
  CLINLOOP_IMAGE_SCAN_MINUTES             interval (default 10)
  CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS       how far back to look for new studies (default 2)
  CLINLOOP_IMAGE_SCAN_MODALITIES          default CR,DX,MG,CT,MR,US
  CLINLOOP_IMAGE_SCAN_MAX_STUDIES         studies analysed per run (default 50; the rest wait)
  CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES      default 20
  CLINLOOP_IMAGE_SCAN_MAX_IMAGES          images per series for single-image models (default 4)
  CLINLOOP_IMAGE_SCAN_MAX_SERIES_MB       largest series sent to a series model (default 600)
  CLINLOOP_IMAGE_SCAN_RESEARCH=1          also run research-use models (shadow mode)

CLI:
  python -m src.clinloop_engine.imaging_scanner --once
"""

import argparse
import asyncio
import hashlib
import logging
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from .imaging_fhir import DICOM_MODALITY, dicom_regions, regulatory_unverified
from .loop_store import LoopStore
from .safety_clock import utc_now

logger = logging.getLogger("clinloop.image_scan")

MAX_ATTEMPTS = 5
_RUNNING = threading.Lock()      # one scan at a time: "Run now" during a background run never double-sends
TERMINAL = {"scanned", "no_model", "refused"}
# Series that are not images to analyse: reports, presentation states, key objects, segmentations …
SKIP_MODALITIES = {"SR", "PR", "KO", "SEG", "REG", "RTSTRUCT", "RTPLAN", "RTDOSE", "DOC", "OT", "SC"}
SKIP_SERIES = re.compile(r"localizer|scout|topogram|surview|dose (?:report|info)|screen ?save|report|summary", re.I)
# Projection images: every image of the study is a separate view worth reading
PROJECTION = {"CR", "DX", "MG", "XA", "RF", "IO", "PX"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _flag("CLINLOOP_IMAGE_SCAN")


@dataclass
class ScanConfig:
    lookback_days: int = 2
    modalities: List[str] = field(default_factory=lambda: ["CR", "DX", "MG", "CT", "MR", "US"])
    max_studies: int = 50
    settle_minutes: float = 20.0
    max_images: int = 4
    max_series_mb: float = 600.0
    allow_research: bool = False

    @classmethod
    def from_env(cls) -> "ScanConfig":
        def num(name, default, cast=int):
            try:
                return cast(os.environ.get(name, default))
            except (TypeError, ValueError):
                return cast(default)
        mods = [m.strip().upper() for m in os.environ.get("CLINLOOP_IMAGE_SCAN_MODALITIES", "").split(",") if m.strip()]
        return cls(lookback_days=num("CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS", 2),
                   modalities=mods or cls().modalities,
                   max_studies=num("CLINLOOP_IMAGE_SCAN_MAX_STUDIES", 50),
                   settle_minutes=num("CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES", 20, float),
                   max_images=num("CLINLOOP_IMAGE_SCAN_MAX_IMAGES", 4),
                   max_series_mb=num("CLINLOOP_IMAGE_SCAN_MAX_SERIES_MB", 600, float),
                   allow_research=_flag("CLINLOOP_IMAGE_SCAN_RESEARCH"))


def eligible_models(models, cfg: ScanConfig) -> Tuple[List[Any], List[str]]:
    """Models that may run without a person starting them, and why the others may not."""
    ok, skipped = [], []
    for m in models:
        if regulatory_unverified(m.regulatory) and not cfg.allow_research:
            skipped.append(f"{m.name}: research use or no stated approval (CLINLOOP_IMAGE_SCAN_RESEARCH=1 for shadow mode)")
        elif m.available():
            skipped.append(f"{m.name}: {m.available()}")
        else:
            ok.append(m)
    return ok, skipped


# ── Which patient is this? ──────────────────────────────────────────────────

def resolve_patient(pacs_patient_id: str, fhir, store: LoopStore) -> Tuple[Optional[Dict[str, Any]], str]:
    """The ONE FHIR Patient whose MRN (or configured identifier) is this PACS PatientID, else (None, reason)."""
    if not pacs_patient_id or any(c in pacs_patient_id for c in "*?\\,|"):
        return None, "PatientID missing or not a plain identifier"
    system = os.environ.get("CLINLOOP_PACS_ID_SYSTEM")
    candidates: List[Dict[str, Any]] = []
    if fhir is not None:
        token = f"{system}|{pacs_patient_id}" if system else pacs_patient_id
        found = list(fhir.search("Patient", {"identifier": token}))
        for p in found:
            for i in p.get("identifier", []):
                if i.get("value") != pacs_patient_id:
                    continue
                is_mrn = any(c.get("code") == "MR" for c in (i.get("type") or {}).get("coding", []))
                if (system and i.get("system") == system) or (not system and is_mrn):
                    candidates.append(p)
                    break
    elif _flag("CLINLOOP_PACS_MATCH_FHIR_ID"):
        candidates = [r for r in store.snapshot(pacs_patient_id)
                      if r.get("resourceType") == "Patient" and r.get("id") == pacs_patient_id]
    else:
        return None, "no FHIR server to match the PatientID (set CLINLOOP_FHIR_BASE)"
    unique = {p["id"]: p for p in candidates if p.get("id")}
    if len(unique) == 1:
        return next(iter(unique.values())), ""
    if not unique:
        return None, "no patient with this PatientID"
    return None, f"PatientID matches {len(unique)} patients: not guessed"


# ── One study ───────────────────────────────────────────────────────────────

def _series_summary(series: Dict[str, Any], study: Dict[str, Any]) -> Dict[str, Any]:
    modality = (series.get("modality") or "").upper()
    return {"modality": modality, "modality_kind": DICOM_MODALITY.get(modality),
            "body_part": series.get("body_part") or "",
            "regions": dicom_regions(series.get("body_part"), study.get("description"), series.get("description"))}


def _plan(study: Dict[str, Any], series_list: List[Dict[str, Any]], models: List[Any],
          pacs=None) -> List[Tuple[Dict, List, List]]:
    """(series, single-image models, whole-series models) for each series some model applies to."""
    plan = []
    for s in series_list:
        modality = (s.get("modality") or "").upper()
        if not s.get("uid") or modality in SKIP_MODALITIES or SKIP_SERIES.search(s.get("description") or ""):
            continue
        summary = _series_summary(s, study)
        if pacs is not None and not s.get("body_part") and any(
                m.modalities and modality in m.modalities and m.body_regions for m in models):
            # The series query gave no body part: read one image's header (no pixels) before deciding
            first = (pacs.instances(study["study_uid"], s["uid"]) or [None])[0]
            if first:
                h = pacs.instance_header(study["study_uid"], s["uid"], first["uid"])
                s = {**s, "body_part": h["body_part"], "description": s.get("description") or h["description"]}
                study = {**study, "description": study.get("description") or h["study_description"]}
                if SKIP_SERIES.search(s.get("description") or ""):
                    continue
                summary = _series_summary(s, study)
        applies = [m for m in models if m.applies(summary) is None]
        single = [m for m in applies if getattr(m, "input", "instance") != "series"]
        whole = [m for m in applies if getattr(m, "input", "instance") == "series"]
        if single or whole:
            plan.append((s, single, whole))
    return plan


def _pick(instances: List[Dict[str, Any]], modality: str, n: int) -> List[Dict[str, Any]]:
    """Which images a single-image model reads: every view of a radiograph (up to n); the middle of a stack."""
    if not instances:
        return []
    if modality in PROJECTION:
        return instances[:n]
    return [instances[len(instances) // 2]]


def scan_study(study: Dict[str, Any], patient: Dict[str, Any], pacs, models: List[Any],
               cfg: ScanConfig) -> Dict[str, Any]:
    """Retrieve, check and analyse one study. Returns status, resources to file, models run and a detail."""
    from .imaging_ai import ImagingError, analyze_dicom, analyze_series
    from .pacs_client import dicom_patient_ids
    pid = patient["id"]
    expected = dicom_patient_ids(patient)
    series_list = study.get("series") or pacs.series(study["study_uid"])
    plan = _plan(study, series_list, models, pacs)
    if not plan:
        return {"status": "no_model", "resources": [], "models": [],
                "detail": "no enabled model applies to this study's series: no image retrieved"}
    resources: Dict[str, Dict[str, Any]] = {}
    ran: List[str] = []
    errors: List[str] = []
    for series, single, whole in plan:
        instances = pacs.instances(study["study_uid"], series["uid"])
        modality = (series.get("modality") or "").upper()
        if single:
            for inst in _pick(instances, modality, cfg.max_images):
                content = pacs.retrieve_instance(study["study_uid"], series["uid"], inst["uid"])
                try:
                    result = analyze_dicom(content, pid, expected, None, models=single, with_preview=False,
                                           source="pacs-scan")
                except ImagingError as e:
                    return {"status": "failed", "resources": [], "models": ran, "detail": f"unreadable image: {e}"}
                if not result["filed"]:
                    codes = ", ".join(c["code"] for c in result["qa"] if c["level"] == "critical")
                    return {"status": "refused", "resources": [], "models": ran,
                            "detail": f"safety check failed ({codes}): nothing filed for this study"}
                _merge(resources, result["resources"])
                ran += [m["name"] for m in result["models"] if m.get("ran")]
                errors += [f"{m['name']} {m['reason']}" for m in result["models"]
                           if not m.get("ran") and str(m.get("reason", "")).startswith("failed")]
        if whole:
            limit = cfg.max_series_mb * 1024 * 1024
            contents, size = [], 0
            for inst in instances:
                content = pacs.retrieve_instance(study["study_uid"], series["uid"], inst["uid"])
                size += len(content)
                if size > limit:
                    return {"status": "failed", "resources": [], "models": ran,
                            "detail": f"series larger than {cfg.max_series_mb:g} MB: not sent "
                                      "(raise CLINLOOP_IMAGE_SCAN_MAX_SERIES_MB)"}
                contents.append(content)
            try:
                result = analyze_series(contents, pid, expected, whole, source="pacs-scan")
            except ImagingError as e:
                return {"status": "failed", "resources": [], "models": ran, "detail": f"unreadable series: {e}"}
            if not result["filed"]:
                codes = ", ".join(c["code"] for c in result["qa"])
                return {"status": "refused", "resources": [], "models": ran,
                        "detail": f"safety check failed ({codes}): nothing filed for this study"}
            _merge(resources, result["resources"])
            ran += [m["name"] for m in result["models"] if m.get("ran")]
            errors += [f"{m['name']} {m['reason']}" for m in result["models"]
                       if not m.get("ran") and str(m.get("reason", "")).startswith("failed")]
    if not ran:
        # "Scanned, nothing found" would be false reassurance: a study no model read is a failure, retried
        return {"status": "failed", "resources": [], "models": [],
                "detail": "; ".join(dict.fromkeys(errors)) or "no model produced a result"}
    n_findings = sum(1 for r in resources.values() if r["resourceType"] == "Observation")
    return {"status": "scanned", "resources": list(resources.values()), "models": sorted(set(ran)),
            "findings": n_findings,
            "detail": f"{n_findings} positive finding(s) from {', '.join(sorted(set(ran))) or 'no model'}"}


def _merge(into: Dict[str, Dict[str, Any]], resources: List[Dict[str, Any]]) -> None:
    """Same study or same finding from several images: one resource, the strongest score."""
    for r in resources:
        key = f"{r['resourceType']}/{r['id']}"
        old = into.get(key)
        if old is None or (r.get("valueQuantity") or {}).get("value", 0) > (old.get("valueQuantity") or {}).get("value", 0):
            into[key] = r


# ── One run ─────────────────────────────────────────────────────────────────

def _acquired(study: Dict[str, Any]) -> Optional[datetime]:
    d, t = study.get("study_date") or "", re.sub(r"[^0-9]", "", str(study.get("study_time") or ""))[:6]
    try:
        return datetime.strptime(d + (t.ljust(6, "0") if t else "000000"), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def evaluate(store: LoopStore, patient_id: str, fhir, pacs, now: datetime) -> Dict[str, int]:
    """Re-check one patient with the new findings and record the loops."""
    from .fhir_ingest import bundle_to_events, patient_strata
    from .fhir_sync import patient_record
    from .loop_detector import ClinLoopDetector
    resources, _ = patient_record(patient_id, store, fhir, pacs)
    events_by_patient, _ = bundle_to_events(resources)
    detector = ClinLoopDetector(evaluation_time=now)
    counts = {"new": 0, "updated": 0, "resolved_by_engine": 0}
    for p, events in events_by_patient.items():
        for k, v in store.upsert_detections(detector.process_patient("image-scan", p, events),
                                            strata=patient_strata(resources), actor="image-scan").items():
            counts[k] = counts.get(k, 0) + v
    return counts


def scan_once(store: LoopStore, pacs, fhir=None, models: Optional[List[Any]] = None,
              cfg: Optional[ScanConfig] = None, now: Optional[datetime] = None,
              local_now: Optional[datetime] = None) -> Dict[str, Any]:
    """One scan run. Never raises: failures are recorded for the scan monitor."""
    if not _RUNNING.acquire(blocking=False):
        return {"ok": False, "error": "a scan is already running", "busy": True}
    try:
        return _scan_once(store, pacs, fhir, models, cfg, now, local_now)
    finally:
        _RUNNING.release()


def _scan_once(store, pacs, fhir, models, cfg, now, local_now) -> Dict[str, Any]:
    from .imaging_ai import registered_models
    from .pacs_client import PACSError
    cfg = cfg or ScanConfig.from_env()
    now = now or utc_now()
    local_now = local_now or datetime.now()          # DICOM dates and times are the scanner's local time
    usable, skipped = eligible_models(models if models is not None else registered_models(), cfg)
    if not usable:
        msg = "no imaging model may run automatically" + (f" ({'; '.join(skipped)})" if skipped else
                                                          ": configure an approved product (CLINLOOP_IMAGING_MODELS_CONFIG)")
        store.record_scan_run(ok=False, error=msg, now=now)
        return {"ok": False, "error": msg}
    date_to = local_now.strftime("%Y%m%d")
    date_from = (local_now - timedelta(days=cfg.lookback_days)).strftime("%Y%m%d")
    tally = {"found": 0, "scanned": 0, "findings": 0, "waiting": 0, "skipped_done": 0, "deferred": 0}
    by_status: Dict[str, int] = {}
    patients: Dict[str, None] = {}
    try:
        studies = pacs.new_studies(date_from, date_to, cfg.modalities)
    except (PACSError, requests.RequestException, ValueError) as e:
        store.record_scan_run(ok=False, error=f"PACS query failed: {e}", now=now)
        return {"ok": False, "error": f"PACS query failed: {e}"}
    tally["found"] = len(studies)
    retrieved = 0
    for study in sorted(studies, key=lambda s: (s.get("study_date") or "", s.get("study_time") or "")):
        uid = study["study_uid"]
        done = store.scan_study(uid)
        if done and (done["status"] in TERMINAL or done["attempts"] >= MAX_ATTEMPTS):
            tally["skipped_done"] += 1
            continue
        acquired = _acquired(study)
        if acquired and local_now - acquired < timedelta(minutes=cfg.settle_minutes):
            tally["waiting"] += 1                   # images may still be arriving
            continue
        if retrieved >= cfg.max_studies:
            tally["deferred"] += 1                  # next run
            continue
        try:
            patient, why = resolve_patient(study.get("pacs_patient_id") or "", fhir, store)
        except Exception as e:                       # FHIR down: try again next run
            store.set_scan_study(uid, "failed", detail=f"patient lookup failed ({type(e).__name__})", now=now)
            by_status["failed"] = by_status.get("failed", 0) + 1
            continue
        if patient is None:
            store.set_scan_study(uid, "unmatched", detail=why, now=now)
            by_status["unmatched"] = by_status.get("unmatched", 0) + 1
            continue
        retrieved += 1
        try:
            result = scan_study(study, patient, pacs, usable, cfg)
        except (PACSError, requests.RequestException) as e:
            result = {"status": "failed", "resources": [], "models": [], "detail": f"PACS retrieval failed: {e}"}
        except Exception as e:                      # one bad study never stops the run
            logger.exception("Image scan of one study failed")
            result = {"status": "failed", "resources": [], "models": [], "detail": f"error: {type(e).__name__}"}
        if result["status"] == "scanned":
            sha = hashlib.sha256(uid.encode()).hexdigest()
            for r in result["resources"]:
                kind = "dicom-study" if r["resourceType"] == "ImagingStudy" else "imaging-ai"
                store.add_external_resource(r, kind, "image-scan", "system", source_sha256=sha,
                                            summary=(r.get("description") if kind == "dicom-study"
                                                     else f"{r['device']['display']}: {r['code']['text']}"))
            patients[patient["id"]] = None
            tally["scanned"] += 1
            tally["findings"] += result.get("findings", 0)
        store.set_scan_study(uid, result["status"], patient_id=patient["id"], models=result.get("models"),
                             findings=result.get("findings", 0), detail=result.get("detail", ""), now=now)
        by_status[result["status"]] = by_status.get(result["status"], 0) + 1
    loops = {"new": 0, "updated": 0, "resolved_by_engine": 0}
    for pid in patients:
        try:
            for k, v in evaluate(store, pid, fhir, pacs, now).items():
                loops[k] = loops.get(k, 0) + v
        except Exception as e:                      # findings are filed; the next FHIR sync re-checks the patient
            logger.warning("Re-check after image scan failed: %s", type(e).__name__)
    store.record_scan_run(ok=True, found=tally["found"], scanned=tally["scanned"], findings=tally["findings"], now=now)
    return {"ok": True, **tally, "by_status": by_status, "loops": loops, "models": [m.name for m in usable],
            "models_not_run": skipped, "window": f"{date_from}-{date_to}"}


def status(store: LoopStore) -> Dict[str, Any]:
    from .imaging_ai import registered_models
    from .pacs_client import client_from_env
    cfg = ScanConfig.from_env()
    usable, skipped = eligible_models(registered_models(), cfg)
    minutes = float(os.environ.get("CLINLOOP_IMAGE_SCAN_MINUTES", "10") or 10)
    s = store.scan_status(max_silence_hours=max(2.0, 3 * minutes / 60))
    return {"enabled": enabled(), "pacs_configured": client_from_env() is not None,
            "interval_minutes": minutes, "modalities": cfg.modalities, "lookback_days": cfg.lookback_days,
            "research_models_allowed": cfg.allow_research,
            "models": [{"name": m.name, "regulatory": m.regulatory, "input": getattr(m, "input", "instance"),
                        "modalities": m.modalities, "body_regions": m.body_regions} for m in usable],
            "models_not_run": skipped, **s}


async def scan_loop(get_store, interval_minutes: Optional[float] = None):
    """Background scanning for the API process (only with CLINLOOP_IMAGE_SCAN=1 and a PACS)."""
    from .fhir_sync import client_from_env as fhir_from_env
    from .pacs_client import client_from_env as pacs_from_env
    if not enabled():
        return
    pacs = pacs_from_env()
    if pacs is None:
        logger.error("CLINLOOP_IMAGE_SCAN=1 but no PACS (CLINLOOP_PACS_DICOMWEB): image scanning not started")
        return
    minutes = interval_minutes or float(os.environ.get("CLINLOOP_IMAGE_SCAN_MINUTES", "10") or 10)
    while True:
        result = await asyncio.to_thread(scan_once, get_store(), pacs, fhir_from_env())
        logger.info("Image scan: %s", {k: v for k, v in result.items() if k in ("ok", "found", "scanned", "findings", "error")})
        await asyncio.sleep(minutes * 60)


def main(argv: Optional[List[str]] = None) -> int:
    from .fhir_sync import client_from_env as fhir_from_env
    from .pacs_client import client_from_env as pacs_from_env
    ap = argparse.ArgumentParser(description="Scan new PACS studies with the hospital's imaging AI")
    ap.add_argument("--once", action="store_true", help="run one scan and exit")
    ap.add_argument("--db", default=None, help="loop registry path (default: CLINLOOP_DB)")
    args = ap.parse_args(argv)
    pacs = pacs_from_env()
    if pacs is None:
        print("Set CLINLOOP_PACS_DICOMWEB (and CLINLOOP_FHIR_BASE to match patients).", file=sys.stderr)
        return 2
    from .clinical_api import DEFAULT_DB
    store = LoopStore(args.db or os.environ.get("CLINLOOP_DB", DEFAULT_DB))
    result = scan_once(store, pacs, fhir_from_env())
    print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
