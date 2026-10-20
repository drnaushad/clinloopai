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
  CLINLOOP_FHIR_CLIENT_ID      SMART Backend Services login (with CLINLOOP_FHIR_PRIVATE_KEY): see
                               smart_auth.py. Takes precedence over a static token.
  CLINLOOP_FHIR_TOKEN          static bearer token (read-only scope), for servers without SMART login
  CLINLOOP_FHIR_MODE           search (default) or bulk: Bulk FHIR export for servers that serve
                               population data only that way (e.g. Epic); see bulk_fhir.py
  CLINLOOP_FHIR_SYNC_MINUTES   interval for the API's background sync (default 15)
  CLINLOOP_FHIR_INITIAL_DAYS   look-back for the very first sync (default 365)

CLI:
  python -m src.clinloop_engine.fhir_sync --check   # can ClinLoop log in and read each type? (no patient data shown)
  python -m src.clinloop_engine.fhir_sync --once
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode, urljoin, urlparse

import requests

from .fhir_ingest import _patient_id, bundle_to_events, patient_strata, superseded_reports
from .loop_detector import ClinLoopDetector, hospital_detector, lapse_after_death
from .loop_store import LoopStore
from .safety_clock import utc_now
from .smart_auth import SMARTAuthError, SMARTBackendAuth, auth_from_env

logger = logging.getLogger("clinloop.fhir_sync")

# Resource types ClinLoop reads (all search parameters used are standard R4)
CLINICAL_TYPES = ["Observation", "DiagnosticReport", "ServiceRequest", "Appointment", "Communication",
                  "Encounter", "MedicationRequest", "Procedure", "Condition",
                  "DocumentReference"]      # clinical notes: plans in them become R048–R051 obligations
# Read when the server supports them; a server without ImagingStudy does not fail the sync
OPTIONAL_TYPES = ["ImagingStudy"]
PAGE_SIZE = 100
MAX_PAGES = 1000   # hard stop against paging loops


class FHIRSyncError(RuntimeError):
    pass


def search_bundle(body: Dict, resource_type: str) -> Dict:
    """Reject a successful HTTP status carrying an error or a non-search payload."""
    if not isinstance(body, dict) or body.get("resourceType") != "Bundle" or body.get("type") != "searchset":
        raise FHIRSyncError("FHIR search did not return a searchset Bundle")
    if not isinstance(body.get("entry", []), list):
        raise FHIRSyncError("FHIR search entries are malformed")
    for entry in body.get("entry", []):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            raise FHIRSyncError("FHIR search entry has no resource")
        if resource.get("resourceType") == "OperationOutcome":
            if any(i.get("severity") in {"error", "fatal"} for i in resource.get("issue", [])):
                raise FHIRSyncError("FHIR search returned an error outcome")
        elif resource.get("resourceType") != resource_type:
            raise FHIRSyncError("FHIR search returned an unexpected resource type")
    return body


class FHIRClient:
    """Minimal read-only FHIR R4 REST client with Bundle paging."""

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 30.0,
                 session: Optional[requests.Session] = None, auth=None):
        """``auth``: a SMARTBackendAuth (or any requests auth) that supplies and renews the token."""
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/fhir+json"})
        if auth is not None:
            self.session.auth = auth
        elif token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, url: str) -> requests.Response:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=False)
        except SMARTAuthError as e:
            raise FHIRSyncError(f"FHIR login failed: {e}") from None
        invalidate = getattr(self.session.auth, "invalidate", None)
        if resp.status_code == 401 and invalidate:      # token revoked or expired early: log in again, once
            invalidate()
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=False)
            except SMARTAuthError as e:
                raise FHIRSyncError(f"FHIR login failed: {e}") from None
        return resp

    def search(self, resource_type: str, params: Dict[str, str]) -> Iterable[Dict]:
        url = f"{self.base}/{resource_type}?{urlencode({**params, '_count': PAGE_SIZE})}"
        for _ in range(MAX_PAGES):
            resp = self._get(url)
            if resp.status_code != 200:
                raise FHIRSyncError(f"GET {resource_type} failed: HTTP {resp.status_code}")
            try:
                bundle = search_bundle(resp.json(), resource_type)
            except ValueError:
                raise FHIRSyncError("FHIR search returned unreadable JSON") from None
            for entry in bundle.get("entry", []):
                if entry.get("resource", {}).get("resourceType") != "OperationOutcome":
                    yield entry["resource"]
            url = next((l["url"] for l in bundle.get("link", []) if l.get("relation") == "next"), None)
            if not url:
                return
            url = urljoin(self.base + "/", url)
            target, origin = urlparse(url), urlparse(self.base)
            if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
                raise FHIRSyncError("FHIR paging link left the configured origin")
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
    if client is not None and hasattr(client, "bind"):      # Bulk FHIR: history from the local copy
        client.bind(store)
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
    if hasattr(client, "bind"):
        client.bind(store)
    try:
        patients, newest = client.changed_patients(since)
        store.note_patients(patients)          # the denominator for rates per 1,000 patients
        detector = hospital_detector(now)
        n_events, n_warnings, counts = 0, 0, {"new": 0, "updated": 0, "resolved_by_engine": 0}
        from . import second_reader
        budget = {"left": int(os.environ.get("CLINLOOP_SECOND_READER_MAX", "20"))}
        for pid in sorted(patients):
            history, record_warnings = patient_record(pid, store, client, pacs)
            if second_reader.running():
                try:     # the second reader never blocks the sync: on any failure the rules' result stands
                    # live: its flags join the record (R058); silent: they go to the quality log, [] comes back
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
            # Loops a preliminary report opened move to its final version
            store.supersede_sources(superseded_reports(history), actor=source)
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


def check_connection(client: FHIRClient, now: Optional[datetime] = None) -> Dict:
    """
    Can ClinLoop read this FHIR server the way the sync does? Reads the CapabilityStatement, logs in,
    then makes the sync's own search (`_lastUpdated=gt…`, one result) for each resource type.
    The report holds HTTP outcomes and counts only: no resource content, no patient data.
    """
    since = ((now or utc_now()) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    report: Dict = {"base": client.base, "ok": False, "fhir_version": None, "login": None, "types": {}, "problems": []}
    try:      # the CapabilityStatement is public on most servers: read it without logging in
        meta = requests.get(f"{client.base}/metadata", headers={"Accept": "application/fhir+json"},
                            timeout=client.timeout)
        if meta.status_code == 200:
            cap = meta.json()
            report["fhir_version"] = cap.get("fhirVersion")
            declared = {r.get("type"): r for rest in cap.get("rest", []) for r in rest.get("resource", [])}
            report["software"] = (cap.get("software") or {}).get("name")
        else:
            declared = {}
            report["problems"].append(f"CapabilityStatement: HTTP {meta.status_code}")
    except (requests.RequestException, ValueError) as e:
        report["problems"].append(f"Server unreachable ({type(e).__name__})")
        return report
    if report["fhir_version"] and not str(report["fhir_version"]).startswith("4.0"):
        report["problems"].append(f"FHIR version {report['fhir_version']}: ClinLoop reads R4 (4.0.x)")
    bulk = hasattr(client, "export_url")
    if bulk:
        group = bool(getattr(client, "group_id", None))
        operations = [op for rest in cap.get("rest", [])
                      for op in ([o for r in rest.get("resource", []) if r.get("type") == "Group"
                                  for o in r.get("operation", [])] if group else rest.get("operation", []))]
        names = {str(op.get("name", "")).lstrip("$").lower() for op in operations}
        supported = bool(names & ({"export", "group-export"} if group else {"export", "system-export"}))
        report["mode"] = "bulk export"
        report["export"] = {"url": client.export_url, "declared": supported}
        if not supported:
            report["problems"].append("The CapabilityStatement declares no matching $export operation")
    auth = client.session.auth
    if isinstance(auth, SMARTBackendAuth):
        try:
            auth.invalidate()
            auth.token()
            report["login"] = {"method": "SMART Backend Services" + ("" if auth.private_key is not None
                                                                    else " (client secret)"),
                               "token_endpoint": auth.token_url, "scope": auth.scope}
        except SMARTAuthError as e:
            report["login"] = {"method": "SMART Backend Services", "error": str(e)}
            report["problems"].append(f"Login failed: {e}")
            return report
    else:
        report["login"] = {"method": "static bearer token" if "Authorization" in client.session.headers else "none"}
    if bulk:            # no searches: the export itself is what the sync uses (it is started by a sync, not here)
        report["ok"] = not report["problems"]
        return report
    for rtype in CLINICAL_TYPES + OPTIONAL_TYPES + ["Patient"]:
        entry: Dict = {"declared": rtype in declared if declared else None}
        url = f"{client.base}/{rtype}?{urlencode({'_lastUpdated': f'gt{since}', '_count': 1})}"
        try:
            resp = client._get(url)
            entry["status"] = resp.status_code
            if resp.status_code == 200:
                search_bundle(resp.json(), rtype)
                entry["readable"] = True
            else:
                entry["readable"] = False
                hint = {401: "not logged in", 403: "not allowed: check the scopes granted to ClinLoop",
                        400: "this search is not supported (ClinLoop searches by _lastUpdated)",
                        404: "resource type not available"}.get(resp.status_code, "error")
                entry["hint"] = hint
                if rtype not in OPTIONAL_TYPES:
                    report["problems"].append(f"{rtype}: HTTP {resp.status_code} ({hint})")
        except (FHIRSyncError, requests.RequestException, ValueError) as e:
            entry.update(readable=False, error=type(e).__name__)
            if rtype not in OPTIONAL_TYPES:
                report["problems"].append(f"{rtype}: {type(e).__name__}")
        report["types"][rtype] = entry
    report["ok"] = not report["problems"]
    return report


def client_from_env() -> Optional[FHIRClient]:
    base = os.environ.get("CLINLOOP_FHIR_BASE")
    if not base:
        return None
    try:
        auth = auth_from_env(base, CLINICAL_TYPES + OPTIONAL_TYPES)
    except SMARTAuthError as e:          # a bad key must stop the sync loudly, not fall back to no login
        raise FHIRSyncError(str(e)) from None
    token = os.environ.get("CLINLOOP_FHIR_TOKEN")
    mode = (os.environ.get("CLINLOOP_FHIR_MODE") or "search").strip().lower()
    if mode == "bulk":
        from .bulk_fhir import bulk_client_from_env
        return bulk_client_from_env(base, token, auth)
    if mode != "search":
        raise FHIRSyncError("CLINLOOP_FHIR_MODE must be 'search' or 'bulk'")
    return FHIRClient(base, token=token, auth=auth)


async def sync_loop(get_store, interval_minutes: Optional[float] = None):
    """Background sync for the API process (enabled when CLINLOOP_FHIR_BASE is set)."""
    try:
        client = client_from_env()
    except FHIRSyncError as e:       # e.g. an unreadable key: no sync at all, and the feed alarm must say so
        logger.error("FHIR sync not started: %s", e)
        get_store().record_ingest("fhir-sync", "fhir-sync", ok=False, error=f"not started: {e}")
        return
    if client is None:
        return
    minutes = interval_minutes or float(os.environ.get("CLINLOOP_FHIR_SYNC_MINUTES", "15"))
    initial = int(os.environ.get("CLINLOOP_FHIR_INITIAL_DAYS", "365"))
    while True:
        # Run the blocking HTTP calls off the event loop
        from .pacs_client import client_from_env as pacs_from_env
        try:
            result = await asyncio.to_thread(sync_once, get_store(), client, "fhir-sync", None, initial, pacs_from_env())
            logger.info("FHIR sync: %s", result)
        except Exception:          # never let the sync loop die: the feed alarm reports the gap
            logger.exception("FHIR sync crashed; retrying at the next interval")
        await asyncio.sleep(minutes * 60)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sync ClinLoop from a FHIR R4 server")
    ap.add_argument("--once", action="store_true", help="run a single sync and exit")
    ap.add_argument("--check", action="store_true",
                    help="check login and which resource types can be read (prints no patient data)")
    ap.add_argument("--db", default=None, help="loop registry path (default: CLINLOOP_DB)")
    args = ap.parse_args(argv)
    try:
        client = client_from_env()
    except FHIRSyncError as e:
        print(f"Cannot start: {e}", file=sys.stderr)
        return 2
    if client is None:
        print("Set CLINLOOP_FHIR_BASE, and CLINLOOP_FHIR_CLIENT_ID with CLINLOOP_FHIR_PRIVATE_KEY "
              "(or CLINLOOP_FHIR_TOKEN).", file=sys.stderr)
        return 2
    if args.check:
        import json
        report = check_connection(client)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["ok"] else 1
    from .clinical_api import DEFAULT_DB
    store = LoopStore(args.db or os.environ.get("CLINLOOP_DB", DEFAULT_DB))
    result = sync_once(store, client, initial_days=int(os.environ.get("CLINLOOP_FHIR_INITIAL_DAYS", "365")))
    print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
