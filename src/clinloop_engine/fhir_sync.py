"""
fhir_sync.py — Scheduled, read-only sync from a hospital FHIR R4 server

Each run:
  1. Asks the server which resources changed since the last cursor
     (`_lastUpdated=gt<cursor>`, following Bundle paging links) and collects
     the patients they belong to.
  2. Fetches the FULL history of each changed patient. An incremental pull
     alone would make follow-ups recorded earlier look missing and flood the
     worklist with false alarms.
  3. Runs the detection engine on that history and records every loop.
  4. Advances the cursor only if the whole run succeeded, and records the run
     so the feed monitor can raise an alarm when data stops arriving.

Configuration (environment):
  CLINLOOP_FHIR_BASE           FHIR base URL, e.g. https://fhir.hospital.local/r4
  CLINLOOP_FHIR_TOKEN          bearer token for the FHIR server (read-only scope)
  CLINLOOP_FHIR_SYNC_MINUTES   interval for the API's background sync (default 15)
  CLINLOOP_FHIR_INITIAL_DAYS   look-back for the very first sync (default 365)

Production deployments should obtain the token via SMART Backend Services
(client-credentials with a signed JWT); this module accepts any bearer token.

CLI:
  python -m src.clinloop_engine.fhir_sync --once
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode

import requests

from .fhir_ingest import _patient_id, bundle_to_events, patient_strata
from .loop_detector import ClinLoopDetector, hospital_detector, lapse_after_death
from .loop_store import LoopStore
from .safety_clock import utc_now

logger = logging.getLogger("clinloop.fhir_sync")

# Resource types ClinLoop reads (all search parameters used are standard R4)
CLINICAL_TYPES = ["Observation", "DiagnosticReport", "ServiceRequest", "Appointment", "Communication",
                  "Encounter", "MedicationRequest", "Procedure", "Condition"]
# Read when the server supports them; a server without ImagingStudy does not fail the sync
OPTIONAL_TYPES = ["ImagingStudy"]
PAGE_SIZE = 100
MAX_PAGES = 1000   # hard stop against paging loops


class FHIRSyncError(RuntimeError):
    pass


class FHIRClient:
    """Minimal read-only FHIR R4 REST client with Bundle paging."""

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 30.0,
                 session: Optional[requests.Session] = None):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/fhir+json"})
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def search(self, resource_type: str, params: Dict[str, str]) -> Iterable[Dict]:
        url = f"{self.base}/{resource_type}?{urlencode({**params, '_count': PAGE_SIZE})}"
        for _ in range(MAX_PAGES):
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                raise FHIRSyncError(f"GET {resource_type} failed: HTTP {resp.status_code}")
            bundle = resp.json()
            for entry in bundle.get("entry", []):
                if entry.get("resource"):
                    yield entry["resource"]
            url = next((l["url"] for l in bundle.get("link", []) if l.get("relation") == "next"), None)
            if not url:
                return
        raise FHIRSyncError(f"Paging for {resource_type} exceeded {MAX_PAGES} pages")

    def changed_patients(self, since: str) -> Tuple[Set[str], Optional[str]]:
        """Patients with any clinical resource updated after `since`, and the newest lastUpdated seen."""
        patients: Set[str] = set()
        newest: Optional[str] = None
        for rtype in CLINICAL_TYPES + OPTIONAL_TYPES + ["Patient"]:
            try:
                found = list(self.search(rtype, {"_lastUpdated": f"gt{since}"}))
            except FHIRSyncError:
                if rtype in OPTIONAL_TYPES:
                    continue
                raise
            for r in found:
                pid = r.get("id") if rtype == "Patient" else _patient_id(r)
                if pid:
                    patients.add(pid)
                updated = (r.get("meta") or {}).get("lastUpdated")
                if updated and (newest is None or updated > newest):
                    newest = updated
        return patients, newest

    def patient_history(self, patient_id: str) -> List[Dict]:
        resources: List[Dict] = []
        for rtype in CLINICAL_TYPES + OPTIONAL_TYPES:
            # `patient` is a standard R4 search parameter on every type read here
            try:
                resources.extend(self.search(rtype, {"patient": f"Patient/{patient_id}"}))
            except FHIRSyncError:
                if rtype not in OPTIONAL_TYPES:
                    raise
        try:
            resources.extend(self.search("Patient", {"_id": patient_id}))
        except FHIRSyncError:
            pass  # demographics are optional (used only for equity strata)
        return resources


def patient_record(patient_id: str, store: LoopStore, client: Optional["FHIRClient"] = None,
                   pacs=None) -> Tuple[List[Dict], List[str]]:
    """
    Everything ClinLoop knows about one patient: the FHIR history, resources
    added in ClinLoop (outside reports, DICOM uploads, imaging-AI results) and
    the imaging studies in the PACS.
    """
    from .pacs_client import PACSError, imaging_studies_for
    warnings: List[str] = []
    resources = client.patient_history(patient_id) if client else store.snapshot(patient_id)
    resources = resources + store.external_resources(patient_id)
    if pacs is not None:
        patient = next((r for r in resources if r.get("resourceType") == "Patient" and r.get("id") == patient_id), None)
        try:
            resources += imaging_studies_for(pacs, patient_id, patient)
        except (PACSError, requests.RequestException) as e:
            # Without PACS data, follow-up scans can look missing: more alerts, never fewer
            warnings.append(f"PACS unreachable for this patient: {e}")
    return resources, warnings


def sync_once(store: LoopStore, client: FHIRClient, source: str = "fhir-sync",
              now: Optional[datetime] = None, initial_days: int = 365, pacs=None) -> Dict:
    """One sync run. Never raises: failures are recorded for the feed monitor."""
    now = now or utc_now()
    since = store.get_cursor(source) or (now - timedelta(days=initial_days)).isoformat() + "Z"
    try:
        patients, newest = client.changed_patients(since)
        detector = hospital_detector(now)
        n_events, n_warnings, counts = 0, 0, {"new": 0, "updated": 0, "resolved_by_engine": 0}
        from . import second_reader
        budget = {"left": int(os.environ.get("CLINLOOP_SECOND_READER_MAX", "20"))}
        for pid in sorted(patients):
            history, record_warnings = patient_record(pid, store, client, pacs)
            if second_reader.enabled():
                try:     # the second reader never blocks the sync: on any failure the rules' result stands
                    history = history + second_reader.second_read_patient(store, pid, history, budget=budget, now=now)
                except Exception as e:
                    logger.warning("Second reader failed for a patient: %s", type(e).__name__)
            events_by_patient, warnings = bundle_to_events(history)
            warnings += record_warnings
            n_warnings += len(warnings)
            strata = patient_strata(history)
            for p, events in events_by_patient.items():
                n_events += len(events)
                result = store.upsert_detections(lapse_after_death(detector.process_patient(source, p, events), history),
                                                 strata=strata, actor=source)
                for k, v in result.items():
                    counts[k] += v
        store.record_ingest(source, source, ok=True, patients=len(patients), events=n_events,
                            warnings=n_warnings, now=now)
        if newest:
            store.set_cursor(source, newest)
        return {"ok": True, "since": since, "patients": len(patients), "events": n_events,
                "warnings": n_warnings, "loops": counts, "cursor": newest or since}
    except (FHIRSyncError, requests.RequestException, ValueError) as e:
        logger.error("FHIR sync failed: %s", e)
        store.record_ingest(source, source, ok=False, error=str(e), now=now)
        return {"ok": False, "since": since, "error": str(e)}


def client_from_env() -> Optional[FHIRClient]:
    base = os.environ.get("CLINLOOP_FHIR_BASE")
    if not base:
        return None
    return FHIRClient(base, token=os.environ.get("CLINLOOP_FHIR_TOKEN"))


async def sync_loop(get_store, interval_minutes: Optional[float] = None):
    """Background sync for the API process (enabled when CLINLOOP_FHIR_BASE is set)."""
    client = client_from_env()
    if client is None:
        return
    minutes = interval_minutes or float(os.environ.get("CLINLOOP_FHIR_SYNC_MINUTES", "15"))
    initial = int(os.environ.get("CLINLOOP_FHIR_INITIAL_DAYS", "365"))
    while True:
        # Run the blocking HTTP calls off the event loop
        from .pacs_client import client_from_env as pacs_from_env
        result = await asyncio.to_thread(sync_once, get_store(), client, "fhir-sync", None, initial, pacs_from_env())
        logger.info("FHIR sync: %s", result)
        await asyncio.sleep(minutes * 60)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sync ClinLoop from a FHIR R4 server")
    ap.add_argument("--once", action="store_true", help="run a single sync and exit")
    ap.add_argument("--db", default=None, help="loop registry path (default: CLINLOOP_DB)")
    args = ap.parse_args(argv)
    client = client_from_env()
    if client is None:
        print("Set CLINLOOP_FHIR_BASE (and CLINLOOP_FHIR_TOKEN).", file=sys.stderr)
        return 2
    from .clinical_api import DEFAULT_DB
    store = LoopStore(args.db or os.environ.get("CLINLOOP_DB", DEFAULT_DB))
    result = sync_once(store, client, initial_days=int(os.environ.get("CLINLOOP_FHIR_INITIAL_DAYS", "365")))
    print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
