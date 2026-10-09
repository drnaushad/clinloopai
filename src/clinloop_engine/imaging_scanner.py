"""
imaging_scanner.py — Automatic image scanning: new PACS studies → the hospital's imaging AI → review loops

OFF unless the hospital turns it on (CLINLOOP_IMAGE_SCAN=1) and a PACS is
configured (CLINLOOP_PACS_DICOMWEB). Each run:

  1. Asks the PACS (QIDO-RS) for studies acquired in the last
     CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS days, for the configured modalities.
     A study is read only once its image count is the same on two runs (and
     it is at least CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES old): a half-arrived
     study is never read. Images arriving after a study was read re-open it.
  2. Matches the study's PatientID to exactly ONE patient on the FHIR server,
     by the identifier system in CLINLOOP_PACS_ID_SYSTEM (required: another
     site's MRN with the same digits must never match). No match, or more than
     one: the study is not analysed and is listed for a person to check. A
     patient is never guessed.
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

Every study is recorded in a ledger (image_scan_studies): pending, scanned,
no_model, unmatched, refused, failed or abandoned. An outage (FHIR, PACS or a
product failing study after study) stops the run and costs no study a retry;
a study that itself keeps failing is abandoned after MAX_ATTEMPTS and raises
an alarm (status ATTENTION). If one product reads a study and another fails,
the findings are filed and the study is retried. Runs are recorded apart from
the FHIR feed monitor, so a working scanner can never hide a dead record feed,
and a database lease keeps two processes (API workers, the CLI) from scanning
at once. Dates and times are the hospital's (CLINLOOP_LOCAL_TZ).

Configuration (environment):
  CLINLOOP_IMAGE_SCAN=1                   turn scanning on
  CLINLOOP_IMAGE_SCAN_MINUTES             interval (default 10)
  CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS       how far back to look for new studies (default 2)
  CLINLOOP_IMAGE_SCAN_MODALITIES          default CR,DX,MG,CT,MR,US
  CLINLOOP_IMAGE_SCAN_MAX_STUDIES         studies analysed per run (default 50; the rest wait)
  CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES      minimum age of a study before it is read (default 5)
  CLINLOOP_PACS_ID_SYSTEM                 FHIR identifier system of the PACS PatientID (required)
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
import socket
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from .imaging_fhir import DICOM_MODALITY, _local_tz, dicom_regions, regulatory_unverified
from .loop_store import LoopStore
from .safety_clock import utc_now

logger = logging.getLogger("clinloop.image_scan")

MAX_ATTEMPTS = 5                 # failures of one study before it is abandoned (outages are not counted)
MAX_CONSECUTIVE_OUTAGES = 3      # PACS or product failing study after study: stop the run, try again next run
LEASE_MINUTES = 60.0
_RUNNING = threading.Lock()      # one scan at a time in this process; a database lease covers other processes
TERMINAL = {"scanned", "no_model", "refused", "abandoned"}
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
    settle_minutes: float = 5.0           # minimum wait; the image count must also be unchanged between two runs
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
                   settle_minutes=num("CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES", 5, float),
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
    expected = dicom_patient_ids(patient, strict=True)
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
    n_findings = sum(1 for r in resources.values() if r["resourceType"] == "Observation")
    errors = list(dict.fromkeys(errors))
    if not ran:
        # "Scanned, nothing found" would be false reassurance: a study no model read is a failure, retried
        return {"status": "failed", "resources": [], "models": [], "infra": bool(errors),
                "detail": "; ".join(errors) or "no model produced a result"}
    if errors:
        # One product read it, another failed: file what was found, and retry so every product reads it
        return {"status": "failed", "resources": list(resources.values()), "models": sorted(set(ran)), "infra": True,
                "findings": n_findings,
                "detail": f"{'; '.join(errors)}. {n_findings} finding(s) from {', '.join(sorted(set(ran)))} filed; retried"}
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
    from .loop_detector import hospital_detector
    resources, _ = patient_record(patient_id, store, fhir, pacs)
    events_by_patient, _ = bundle_to_events(resources)
    detector = hospital_detector(now)
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
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    try:
        if not store.acquire_lease("image-scan", owner, LEASE_MINUTES, now):
            return {"ok": False, "error": "a scan is already running in another process", "busy": True}
        try:
            return _scan_once(store, pacs, fhir, models, cfg, now, local_now)
        finally:
            store.release_lease("image-scan", owner)
    finally:
        _RUNNING.release()


def _hospital_now() -> datetime:
    """Now in the hospital's time zone (CLINLOOP_LOCAL_TZ), naive like DICOM dates and times; never the container's."""
    tz = _local_tz()
    return datetime.now(tz).replace(tzinfo=None) if tz else datetime.now()


def _count(value) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _scan_once(store, pacs, fhir, models, cfg, now, local_now) -> Dict[str, Any]:
    from .imaging_ai import registered_models
    from .pacs_client import PACSError
    cfg = cfg or ScanConfig.from_env()
    now = now or utc_now()
    local_now = local_now or _hospital_now()        # DICOM dates and times are the hospital's local time

    def fail_run(msg: str) -> Dict[str, Any]:
        store.record_scan_run(ok=False, error=msg, now=now)
        return {"ok": False, "error": msg}

    usable, skipped = eligible_models(models if models is not None else registered_models(), cfg)
    if not usable:
        return fail_run("no imaging model may run automatically" + (f" ({'; '.join(skipped)})" if skipped else
                        ": configure an approved product (CLINLOOP_IMAGING_MODELS_CONFIG)"))
    match_fhir_id = _flag("CLINLOOP_PACS_MATCH_FHIR_ID")
    if fhir is None and not match_fhir_id:
        return fail_run("no FHIR server to match PatientIDs to patients (set CLINLOOP_FHIR_BASE)")
    if fhir is not None and not os.environ.get("CLINLOOP_PACS_ID_SYSTEM") and not match_fhir_id:
        # Without it, another site's MRN with the same digits could match: images filed to the wrong patient
        return fail_run("set CLINLOOP_PACS_ID_SYSTEM to the FHIR identifier system of the PACS PatientID "
                        "(required for automatic scanning)")
    date_to = local_now.strftime("%Y%m%d")
    date_from = (local_now - timedelta(days=cfg.lookback_days)).strftime("%Y%m%d")
    tally = {"found": 0, "scanned": 0, "findings": 0, "waiting": 0, "skipped_done": 0, "deferred": 0, "reopened": 0}
    by_status: Dict[str, int] = {}
    patients: Dict[str, None] = {}
    try:
        studies = pacs.new_studies(date_from, date_to, cfg.modalities)
    except (PACSError, requests.RequestException, ValueError) as e:
        return fail_run(f"PACS query failed: {e}")
    truncated = list(getattr(pacs, "truncated", []) or [])
    tally["found"] = len(studies)

    def record(uid, status, **kw) -> int:
        by_status[status] = by_status.get(status, 0) + 1
        return store.set_scan_study(uid, status, now=now, **kw)

    retrieved, outages, aborted = 0, 0, None
    for study in sorted(studies, key=lambda s: (s.get("study_date") or "", s.get("study_time") or "")):
        uid = study["study_uid"]
        done = store.scan_study(uid)
        n = _count(study.get("n_instances"))
        if done and (done["status"] in TERMINAL or (done["status"] == "unmatched" and done["attempts"] >= MAX_ATTEMPTS)):
            grew = n is not None and done["instances"] is not None and n > done["instances"]
            if grew and done["status"] in ("scanned", "no_model"):
                # Images arrived after it was read: read it again, once the count settles
                store.set_scan_study(uid, "pending", patient_id=done["patient_id"], instances=n, reset_attempts=True,
                                     detail=f"{n - done['instances']} more image(s) arrived after it was "
                                            f"{done['status'].replace('_', ' ')}: read again", now=now)
                tally["reopened"] += 1
                tally["waiting"] += 1
            else:
                tally["skipped_done"] += 1
            continue
        acquired = _acquired(study)
        if acquired and local_now - acquired < timedelta(minutes=cfg.settle_minutes):
            tally["waiting"] += 1                   # images may still be arriving
            continue
        if n is not None and (done is None or done["instances"] != n):
            # Read only once the image count is the same on two runs: a half-arrived study is not read
            store.set_scan_study(uid, done["status"] if done else "pending", instances=n, now=now,
                                 detail=done["detail"] if done else "waiting for all images to arrive")
            tally["waiting"] += 1
            continue
        if retrieved >= cfg.max_studies:
            tally["deferred"] += 1                  # next run
            continue
        try:
            patient, why = resolve_patient(study.get("pacs_patient_id") or "", fhir, store)
        except Exception as e:                       # FHIR down: stop; no study loses a retry to an outage
            aborted = f"FHIR server unreachable ({type(e).__name__}): run stopped, studies wait for the next run"
            break
        if patient is None:
            record(uid, "unmatched", detail=why, count_attempt=True, instances=n)
            continue
        retrieved += 1
        try:
            result = scan_study(study, patient, pacs, usable, cfg)
        except (PACSError, requests.RequestException) as e:
            result = {"status": "failed", "resources": [], "models": [], "infra": True,
                      "detail": f"PACS retrieval failed: {e}"}
        except Exception as e:                      # one bad study never stops the run
            logger.exception("Image scan of one study failed")
            result = {"status": "failed", "resources": [], "models": [], "detail": f"error: {type(e).__name__}"}
        if result["resources"]:
            sha = hashlib.sha256(uid.encode()).hexdigest()
            for r in result["resources"]:
                kind = "dicom-study" if r["resourceType"] == "ImagingStudy" else "imaging-ai"
                store.add_external_resource(r, kind, "image-scan", "system", source_sha256=sha,
                                            summary=(r.get("description") if kind == "dicom-study"
                                                     else f"{r['device']['display']}: {r['code']['text']}"))
            patients[patient["id"]] = None
        if result["status"] == "scanned":
            tally["scanned"] += 1
        tally["findings"] += result.get("findings", 0)
        infra = bool(result.get("infra"))
        attempts = record(uid, result["status"], patient_id=patient["id"], models=result.get("models"),
                          findings=result.get("findings", 0), detail=result.get("detail", ""), instances=n,
                          count_attempt=result["status"] == "failed" and not infra)
        if result["status"] == "failed" and attempts >= MAX_ATTEMPTS:
            store.set_scan_study(uid, "abandoned", patient_id=patient["id"], now=now,
                                 detail=f"gave up after {attempts} failures: {result.get('detail', '')}")
            by_status["abandoned"] = by_status.get("abandoned", 0) + 1
        outages = outages + 1 if infra else 0
        if outages >= MAX_CONSECUTIVE_OUTAGES:
            aborted = f"{outages} studies in a row failed on the PACS or a product ({result.get('detail', '')[:120]}): run stopped"
            break
    loops = {"new": 0, "updated": 0, "resolved_by_engine": 0}
    for pid in patients:
        try:
            for k, v in evaluate(store, pid, fhir, pacs, now).items():
                loops[k] = loops.get(k, 0) + v
        except Exception as e:                      # findings are filed; the next FHIR sync re-checks the patient
            logger.warning("Re-check after image scan failed: %s", type(e).__name__)
    summary = {**tally, "by_status": by_status, "loops": loops, "models": [m.name for m in usable],
               "models_not_run": skipped, "window": f"{date_from}-{date_to}", "truncated": truncated}
    if aborted:
        store.record_scan_run(ok=False, found=tally["found"], scanned=tally["scanned"], findings=tally["findings"],
                              error=aborted, now=now)
        return {"ok": False, "error": aborted, **summary}
    note = (f"study list cut short for {', '.join(truncated)}: shorten CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS"
            if truncated else None)
    store.record_scan_run(ok=True, found=tally["found"], scanned=tally["scanned"], findings=tally["findings"],
                          error=note, now=now)
    return {"ok": True, **summary}


def status(store: LoopStore) -> Dict[str, Any]:
    from .imaging_ai import registered_models
    from .pacs_client import client_from_env
    cfg = ScanConfig.from_env()
    usable, skipped = eligible_models(registered_models(), cfg)
    minutes = float(os.environ.get("CLINLOOP_IMAGE_SCAN_MINUTES", "10") or 10)
    s = store.scan_status(max_silence_hours=max(2.0, 3 * minutes / 60))
    from .fhir_sync import client_from_env as fhir_from_env
    id_ok = bool(os.environ.get("CLINLOOP_PACS_ID_SYSTEM")) or _flag("CLINLOOP_PACS_MATCH_FHIR_ID")
    return {"enabled": enabled(), "pacs_configured": client_from_env() is not None,
            "fhir_configured": fhir_from_env() is not None, "patient_id_system_configured": id_ok,
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
