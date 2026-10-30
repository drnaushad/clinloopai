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
import re
from contextlib import ExitStack
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode, urljoin, urlparse

import requests

from .fhir_ingest import _patient_id, bundle_to_events, patient_strata, superseded_reports
from .loop_detector import ClinLoopDetector, hospital_detector, lapse_after_death
from .loop_store import LoopStore
from .fhir_coverage import empty_coverage, report_coverage, merge_coverage
from .safety_clock import utc_now, normalize_timestamp
from .smart_auth import SMARTAuthError, SMARTBackendAuth, auth_from_env
from .transport_safety import origin, bounded_json

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


class FHIRHTTPError(FHIRSyncError):
    """A resource endpoint HTTP failure, distinguishable from a data-integrity failure."""
    def __init__(self, resource_type: str, status: int):
        self.status = status
        super().__init__(f"GET {resource_type} failed: HTTP {status}")


def _updated(value):
    """Require an unambiguous, zoned FHIR instant before advancing a feed cursor."""
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise FHIRSyncError("FHIR change metadata has no valid update instant")
    from .safety_clock import normalize_timestamp
    try:
        return normalize_timestamp(value)
    except (ValueError, TypeError):
        raise FHIRSyncError("FHIR change metadata has no valid update instant") from None


def search_bundle(body: Dict, resource_type: str) -> Dict:
    """Reject a successful HTTP status carrying an error or a non-search payload."""
    if not isinstance(body, dict) or body.get("resourceType") != "Bundle" or body.get("type") != "searchset":
        raise FHIRSyncError("FHIR search did not return a searchset Bundle")
    if not isinstance(body.get("entry", []), list) or len(body.get("entry", [])) > 10000:
        raise FHIRSyncError("FHIR search entries are malformed")
    links = body.get("link", [])
    if (not isinstance(links, list) or any(not isinstance(link, dict)
            or not isinstance(link.get("relation"), str)
            or not isinstance(link.get("url"), str) or not link["url"].strip() for link in links)):
        raise FHIRSyncError("FHIR search paging links are malformed")
    if sum(link.get("relation") == "next" for link in links) > 1:
        raise FHIRSyncError("FHIR search has ambiguous paging links")
    for entry in body.get("entry", []):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            raise FHIRSyncError("FHIR search entry has no resource")
        if resource.get("resourceType") == "OperationOutcome":
            issues = resource.get("issue")
            if (not isinstance(issues, list) or not issues
                    or any(not isinstance(issue, dict) or not isinstance(issue.get("severity"), str) or issue.get("severity") not in
                           {"fatal", "error", "warning", "information"} for issue in issues)):
                raise FHIRSyncError("FHIR search outcome is malformed")
            if any(i["severity"] in {"error", "fatal"} for i in issues):
                raise FHIRSyncError("FHIR search returned an error outcome")
        elif resource.get("resourceType") != resource_type:
            raise FHIRSyncError("FHIR search returned an unexpected resource type")
        elif not isinstance(resource.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", resource["id"]):
            raise FHIRSyncError("FHIR search returned an invalid resource identifier")
    return body


class FHIRClient:
    """Minimal read-only FHIR R4 REST client with Bundle paging."""

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 30.0,
                 session: Optional[requests.Session] = None, auth=None, max_resources: int = 100000):
        """``auth``: a SMARTBackendAuth (or any requests auth) that supplies and renews the token."""
        self.base = base_url.rstrip("/")
        try:
            origin(self.base)
        except ValueError:
            raise FHIRSyncError("Invalid FHIR endpoint") from None
        if type(max_resources) is not int or max_resources < 1:
            raise FHIRSyncError("Invalid FHIR resource budget")
        self.max_resources = max_resources
        self.timeout = timeout
        self.session = session or requests.Session()
        if session is None:
            self.session.trust_env = False
        # Do not reuse a cached patient history after the change feed advances.
        self.session.headers.update({"Accept": "application/fhir+json", "Cache-Control": "no-cache"})
        if auth is not None:
            self.session.auth = auth
        elif token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, url: str) -> requests.Response:
        try:
            if origin(url) != origin(self.base):
                raise ValueError()
        except ValueError:
            raise FHIRSyncError("FHIR request left the configured origin") from None
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=False, stream=True)
        except SMARTAuthError as e:
            raise FHIRSyncError(f"FHIR login failed: {e}") from None
        invalidate = getattr(self.session.auth, "invalidate", None)
        if resp.status_code == 401 and invalidate:      # token revoked or expired early: log in again, once
            resp.close()
            invalidate()
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=False, stream=True)
            except SMARTAuthError as e:
                raise FHIRSyncError(f"FHIR login failed: {e}") from None
        return resp

    def search(self, resource_type: str, params: Dict[str, str]) -> Iterable[Dict]:
        url = f"{self.base}/{resource_type}?{urlencode({**params, '_count': PAGE_SIZE})}"
        count, seen_pages = 0, set()
        for _ in range(MAX_PAGES):
            if url in seen_pages:
                raise FHIRSyncError("FHIR search paging repeated a page")
            seen_pages.add(url)
            resp = self._get(url)
            try:
                if resp.status_code != 200:
                    raise FHIRHTTPError(resource_type, resp.status_code)
                try:
                    bundle = search_bundle(bounded_json(resp, 16 * 1024 * 1024), resource_type)
                except (ValueError, UnicodeError):
                    raise FHIRSyncError("FHIR search returned unreadable or oversized JSON") from None
            finally:
                resp.close()
            for entry in bundle.get("entry", []):
                if entry.get("resource", {}).get("resourceType") != "OperationOutcome":
                    count += 1
                    if count > self.max_resources:
                        raise FHIRSyncError("FHIR search exceeded the resource-count budget")
                    yield entry["resource"]
            url = next((l["url"] for l in bundle.get("link", []) if l.get("relation") == "next"), None)
            if not url:
                return
            url = urljoin(self.base + "/", url)
            try:
                if origin(url) != origin(self.base):
                    raise ValueError()
            except ValueError:
                raise FHIRSyncError("FHIR paging link left the configured origin")
        raise FHIRSyncError(f"Paging for {resource_type} exceeded {MAX_PAGES} pages")

    def changed_patients(self, since: str) -> Tuple[Set[str], Optional[str]]:
        """Patients with any clinical resource updated after `since`, and the newest lastUpdated seen."""
        patients: Set[str] = set()
        newest: Optional[str] = None
        newest_time, count = _updated(since), 0
        for rtype in CLINICAL_TYPES + OPTIONAL_TYPES + ["Patient"]:
            try:
                for r in self.search(rtype, {"_lastUpdated": f"gt{since}"}):
                    count += 1
                    if count > self.max_resources:
                        raise FHIRSyncError("FHIR change feed exceeded the resource-count budget")
                    try:
                        pid = r.get("id") if rtype == "Patient" else _patient_id(r)
                    except (AttributeError, TypeError):
                        raise FHIRSyncError("FHIR resource patient reference is malformed") from None
                    if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", pid):
                        raise FHIRSyncError("FHIR resource has no verified patient identity")
                    patients.add(pid)
                    meta = r.get("meta", {})
                    if not isinstance(meta, dict):
                        raise FHIRSyncError("FHIR change metadata is malformed")
                    updated = meta.get("lastUpdated")
                    updated_time = _updated(updated)
                    if updated_time > newest_time:
                        newest, newest_time = updated, updated_time
            except FHIRHTTPError as error:
                if rtype in OPTIONAL_TYPES and error.status in {400, 404, 405, 501}:
                    continue
                raise
        return patients, newest

    def patient_history(self, patient_id: str) -> List[Dict]:
        resources: List[Dict] = []
        for rtype in CLINICAL_TYPES + OPTIONAL_TYPES:
            # `patient` is a standard R4 search parameter on every type read here
            try:
                for resource in self.search(rtype, {"patient": f"Patient/{patient_id}"}):
                    try:
                        returned = _patient_id(resource)
                    except (AttributeError, TypeError):
                        raise FHIRSyncError("FHIR resource patient reference is malformed") from None
                    if returned != patient_id:
                        raise FHIRSyncError("FHIR history includes unverified or mismatched patient identity")
                    resources.append(resource)
                    if len(resources) > self.max_resources:
                        raise FHIRSyncError("FHIR patient history exceeded the resource-count budget")
            except FHIRHTTPError as error:
                if rtype not in OPTIONAL_TYPES or error.status not in {400, 404, 405, 501}:
                    raise
        try:
            for resource in self.search("Patient", {"_id": patient_id}):
                if resource.get("id") != patient_id:
                    raise FHIRSyncError("FHIR demographics returned a mismatched patient identity")
                resources.append(resource)
        except FHIRHTTPError as error:
            if error.status not in {404, 405, 501}:
                raise
        return resources


def patient_record(patient_id: str, store: LoopStore, client: Optional["FHIRClient"] = None,
                   pacs=None, resources: Optional[List[Dict]] = None) -> Tuple[List[Dict], List[str]]:
    """
    Everything ClinLoop knows about one patient: the FHIR history, resources
    added in ClinLoop (outside reports, DICOM uploads, imaging-AI results) and
    the imaging studies in the PACS.
    """
    from .pacs_client import PACSError, imaging_studies_for
    warnings: List[str] = []
    if client is not None and hasattr(client, "bind"):      # Bulk FHIR: history from the local copy
        client.bind(store)
    if resources is None:
        resources = client.patient_history(patient_id) if client else store.snapshot(patient_id)
    resources = resources + store.external_resources(patient_id)
    if pacs is not None:
        patient = next((r for r in resources if r.get("resourceType") == "Patient" and r.get("id") == patient_id), None)
        try:
            resources += imaging_studies_for(pacs, patient_id, patient)
        except (PACSError, requests.RequestException) as e:
            # Without PACS data, follow-up scans can look missing: more alerts, never fewer
            warnings.append(f"PACS unreachable for this patient ({type(e).__name__})")
    return resources, warnings


def sync_once(store: LoopStore, client: FHIRClient, source: str = "fhir-sync",
              now: Optional[datetime] = None, initial_days: int = 365, pacs=None) -> Dict:
    """One sync run. Never raises: failures are recorded for the feed monitor."""
    now = normalize_timestamp(now) if now is not None else utc_now()
    original_cursor = store.get_cursor(source)
    original_state = store.staging_token()
    since = original_cursor or (now - timedelta(days=initial_days)).isoformat() + "Z"
    if hasattr(client, "bind"):
        client.bind(store)
    try:
        with ExitStack() as staging:
            staged_export = None
            guarded_staging = True
            if hasattr(client, "staged_changes"):
                staged_export = staging.enter_context(client.staged_changes(since))
                patients, newest = staged_export.patients, staged_export.newest
            else:
                # The built-in search client is read-only. Legacy/custom clients
                # may mutate the mirror while discovering changes: contain those
                # writes, even though their transaction may include remote work.
                if getattr(type(client), "changed_patients", None) is not FHIRClient.changed_patients:
                    staging.enter_context(store.atomic())
                    guarded_staging = False
                patients, newest = client.changed_patients(since)
            detector = hospital_detector(now)
            prepared = []
            for pid in sorted(patients):
                overlay = staged_export.patient_history(pid) if staged_export is not None else None
                history, record_warnings = patient_record(pid, store, client, pacs, resources=overlay)
                events_by_patient, warnings = bundle_to_events(history, evaluation_time=now)
                if set(events_by_patient) - {pid}:
                    raise ValueError("FHIR patient history contains another patient identity")
                detections = [d for p, events in events_by_patient.items()
                              for d in lapse_after_death(detector.process_patient(source, p, events), history)]
                prepared.append((pid, history, record_warnings, events_by_patient, warnings, detections))
            # Downloads, scoped FHIR/PACS reads, deterministic mapping and initial
            # detection are complete before taking the built-in clients' write lock.
            with store.atomic():
                if store.get_cursor(source) != original_cursor:
                    raise FHIRSyncError("FHIR sync cursor changed during staging; retry required")
                if guarded_staging and store.staging_token() != original_state:
                    raise FHIRSyncError("FHIR local state changed during staging; retry required")
                if staged_export is not None:
                    staged_export.apply(store)
                store.note_patients(patients)
                n_events, n_warnings, counts = 0, 0, {"new": 0, "updated": 0, "resolved_by_engine": 0}
                coverage = empty_coverage()
                from . import second_reader
                budget = {"left": int(os.environ.get("CLINLOOP_SECOND_READER_MAX", "20"))}
                for pid, history, record_warnings, events_by_patient, warnings, detections in prepared:
                    if second_reader.running():
                        try:
                            # Model requests are read-only externally. Its local
                            # cache/suggestions join this transaction; a failed
                            # optional read rolls back its own partial writes.
                            with store.atomic():
                                additions = second_reader.second_read_patient(store, pid, history, budget=budget, now=now)
                                if additions:
                                    enriched_history = history + additions
                                    enriched_events, enriched_warnings = bundle_to_events(enriched_history, evaluation_time=now)
                                    if set(enriched_events) - {pid}:
                                        raise ValueError("Second reader patient identity mismatch")
                                    enriched_detections = [d for p, events in enriched_events.items()
                                                          for d in lapse_after_death(detector.process_patient(source, p, events), enriched_history)]
                            if additions:
                                history, events_by_patient = enriched_history, enriched_events
                                warnings, detections = enriched_warnings, enriched_detections
                        except Exception as e:
                            logger.warning("Second reader failed for a patient: %s", type(e).__name__)
                    warnings = warnings + record_warnings
                    n_warnings += len(warnings)
                    n_events += sum(len(events) for events in events_by_patient.values())
                    merge_coverage(coverage, report_coverage(history, warnings))
                    result = store.upsert_detections(detections, strata=patient_strata(history), actor=source)
                    for key, value in result.items():
                        counts[key] += value
                    store.supersede_sources(superseded_reports(history), actor=source)
                store.record_ingest(source, source, ok=True, patients=len(patients), events=n_events,
                                    warnings=n_warnings, now=now, coverage=coverage)
                if newest:
                    store.set_cursor(source, newest)
                return {"ok": True, "since": since, "patients": len(patients), "events": n_events,
                        "warnings": n_warnings, "coverage": coverage, "loops": counts, "cursor": newest or since}
    except Exception as e:
        import re
        http = re.search(r"\bHTTP (\d{3})\b", str(e)) if isinstance(e, FHIRSyncError) else None
        error = "FHIR sync failed" + (f": HTTP {http.group(1)}" if http else f" ({type(e).__name__})")
        oauth = re.search(r"Token request refused: HTTP (\d{3})(?: (invalid_client|invalid_grant|invalid_scope|invalid_request|unauthorized_client|unsupported_grant_type))?(?:$|\s)", str(e)) if isinstance(e, FHIRSyncError) else None
        if oauth:
            error = f"Token request refused: HTTP {oauth.group(1)}" + (f" {oauth.group(2)}" if oauth.group(2) else "")
        if isinstance(e, FHIRSyncError) and str(e).startswith("Bulk export not ready after "):
            error = "Bulk export not ready; cancelled"
        logger.error("%s", error)
        store.record_ingest(source, source, ok=False, error=error, now=now)
        return {"ok": False, "since": since, "error": error, "local_state_rolled_back": True}


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
            logger.error("FHIR sync crashed; retrying at the next interval")
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
