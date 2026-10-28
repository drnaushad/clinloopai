"""
bulk_fhir.py — Reading a FHIR server through Bulk FHIR export ($export), e.g. Epic

Some servers (Epic among them) do not answer searches across all patients; they provide population
data through the FHIR Bulk Data Access specification instead. This client plugs into the normal sync
(fhir_sync.sync_once) in place of the search-based client:

    1. Kick-off   GET <base>/Group/<id>/$export?_type=…&_since=…   (Prefer: respond-async) → 202 + status URL
    2. Poll       GET <status URL> → 202 (X-Progress, Retry-After) … → 200 + manifest
    3. Download   each NDJSON file in the manifest (with the access token when the manifest asks for it)
    4. Keep       every resource in a local copy of the records (LoopStore.fhir_mirror)
    5. Clean up   DELETE <status URL> (the server may then discard the files)

The first run exports everything for the Group, so each patient's history is complete; later runs
export only what changed since the previous export's transactionTime. A patient's history for the
engine is read from the local copy, exactly as the search-based sync reads it from the server.

The local copy holds patient data: it lives in the same database as the loops, on the hospital's
server, and must be protected and backed up like it.

Configuration (environment):
  CLINLOOP_FHIR_MODE                  bulk (default: search)
  CLINLOOP_FHIR_GROUP_ID              Group to export (recommended: the patients ClinLoop may monitor);
                                      without it, a system-level export (<base>/$export) is requested
  CLINLOOP_FHIR_BULK_TIMEOUT_MINUTES  give up waiting for an export after this long (default 60)
"""

import json
import logging
import os
import time
import tempfile
from contextlib import contextmanager
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode, urljoin, urlsplit

import requests

from .fhir_ingest import _patient_id
from .fhir_sync import CLINICAL_TYPES, OPTIONAL_TYPES, FHIRClient, FHIRSyncError

logger = logging.getLogger("clinloop.bulk_fhir")

EXPORT_TYPES = CLINICAL_TYPES + OPTIONAL_TYPES + ["Patient"]
DEFAULT_RETRY_SECONDS = 10
MAX_RETRY_SECONDS = 300


class BulkFHIRClient(FHIRClient):
    """Bulk FHIR export client with the same interface the sync uses (changed_patients, patient_history)."""

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 60.0,
                 session: Optional[requests.Session] = None, auth=None, group_id: Optional[str] = None,
                 store=None, max_wait_seconds: float = 3600.0, sleep: Callable[[float], None] = time.sleep,
                 resource_types: Optional[List[str]] = None, output_format: Optional[str] = "application/fhir+ndjson"):
        super().__init__(base_url, token=token, timeout=timeout, session=session, auth=auth)
        self.group_id = group_id
        self.store = store
        self.max_wait_seconds = max_wait_seconds
        self.sleep = sleep
        self.last_export: Dict = {}
        self.resource_types = list(EXPORT_TYPES if resource_types is None else resource_types)
        if (not self.resource_types or len(set(self.resource_types)) != len(self.resource_types)
                or "Patient" not in self.resource_types or any(t not in EXPORT_TYPES for t in self.resource_types)):
            raise FHIRSyncError("Invalid bulk resource type profile")
        if output_format not in {None, "application/fhir+ndjson", "application/ndjson", "ndjson"}:
            raise FHIRSyncError("Invalid bulk output format")
        self.output_format = output_format
        self._cleaned_jobs: Set[str] = set()

    def bind(self, store) -> "BulkFHIRClient":
        """The loop store whose local copy of the records this client fills and reads."""
        self.store = store
        return self

    # ── export ────────────────────────────────────────────────────────────────
    @property
    def export_url(self) -> str:
        return f"{self.base}/Group/{self.group_id}/$export" if self.group_id else f"{self.base}/$export"

    def _request(self, method: str, url: str, **kw) -> requests.Response:
        """A request with the session's login, logging in again once on a 401 (as FHIRClient._get)."""
        from .smart_auth import SMARTAuthError
        try:
            target, origin = urlsplit(url), urlsplit(self.base)
            same = (target.scheme, target.hostname, target.port or (443 if target.scheme == "https" else 80)) == (
                origin.scheme, origin.hostname, origin.port or (443 if origin.scheme == "https" else 80))
            if not same or target.scheme not in {"http", "https"} or target.username or target.password or target.fragment:
                raise ValueError()
        except (TypeError, ValueError):
            raise FHIRSyncError("Authenticated bulk request left the configured origin") from None
        kw["allow_redirects"] = False
        for attempt in (0, 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kw)
            except SMARTAuthError as e:
                raise FHIRSyncError(f"FHIR login failed: {e}") from None
            invalidate = getattr(self.session.auth, "invalidate", None)
            if resp.status_code == 401 and invalidate and attempt == 0:
                resp.close()
                invalidate()
                continue
            return resp
        return resp

    @staticmethod
    def _retry_after(resp: requests.Response) -> float:
        try:
            return min(max(float(resp.headers.get("Retry-After", DEFAULT_RETRY_SECONDS)), 1.0), MAX_RETRY_SECONDS)
        except ValueError:                        # an HTTP date instead of seconds: use the default
            return DEFAULT_RETRY_SECONDS

    def kick_off(self, since: Optional[str]) -> str:
        params = {"_type": ",".join(self.resource_types)}
        if self.output_format is not None:
            params["_outputFormat"] = self.output_format
        if since:
            params["_since"] = since
        resp = self._request("GET", f"{self.export_url}?{urlencode(params)}",
                             headers={"Accept": "application/fhir+json", "Prefer": "respond-async"})
        if resp.status_code != 202:
            raise FHIRSyncError(f"Bulk export not started: HTTP {resp.status_code}")
        status_url = resp.headers.get("Content-Location")
        if not status_url:
            raise FHIRSyncError("Bulk export started without a status URL (Content-Location)")
        return urljoin(self.base + "/", status_url)

    def wait(self, status_url: str) -> Dict:
        """Poll the status URL until the manifest is ready (or the wait limit passes)."""
        waited = 0.0
        while True:
            resp = self._request("GET", status_url, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    raise FHIRSyncError("Bulk export finished without a readable manifest") from None
            if resp.status_code not in (202, 429):
                raise FHIRSyncError(f"Bulk export failed: HTTP {resp.status_code}")
            delay = self._retry_after(resp)
            if waited + delay > self.max_wait_seconds:
                self.cancel(status_url)
                raise FHIRSyncError(f"Bulk export not ready after {int(self.max_wait_seconds // 60)} minutes; cancelled")
            logger.info("Bulk export pending; checking again in %ss", int(delay))
            self.sleep(delay)
            waited += delay

    def cancel(self, status_url: str) -> None:
        if status_url in self._cleaned_jobs:
            return
        try:
            response = self._request("DELETE", status_url)
            if response.status_code in {200, 202, 204, 404, 410}:
                self._cleaned_jobs.add(status_url)
                if len(self._cleaned_jobs) > 256:
                    self._cleaned_jobs.pop()
        except (FHIRSyncError, requests.RequestException):
            pass                                  # cleaning up is a courtesy; the server expires files anyway

    @contextmanager
    def _file_response(self, url: str, with_token: bool):
        """A protected file uses only the FHIR origin; a signed file inherits no login."""
        headers = {"Accept": "application/fhir+ndjson"}
        try:
            if with_token:
                response = self._request("GET", url, headers=headers, stream=True)
                try:
                    yield response
                finally:
                    response.close()
            else:
                target, origin = urlsplit(url), urlsplit(self.base)
                local_http = (target.scheme, target.netloc) == (origin.scheme, origin.netloc) and target.scheme == "http"
                if (target.scheme != "https" and not local_http) or not target.hostname or target.username or target.password or target.fragment:
                    raise FHIRSyncError("Anonymous bulk file endpoint is invalid")
                with requests.Session() as anonymous:
                    anonymous.trust_env = False
                    with anonymous.get(url, headers=headers, timeout=self.timeout, stream=True,
                                       allow_redirects=False) as response:
                        yield response
        except requests.RequestException as error:
            raise FHIRSyncError(f"Bulk export file unreachable ({type(error).__name__})") from None

    def download(self, manifest: Dict) -> Iterable[Dict]:
        """Read typed NDJSON; missing or malformed resources abort the whole import."""
        with_token = manifest.get("requiresAccessToken", True)
        for item in manifest.get("output", []):
            with self._file_response(item["url"], with_token) as response:
                if response.status_code != 200:
                    raise FHIRSyncError(f"Bulk export file request failed: HTTP {response.status_code}")
                for line in response.iter_lines(decode_unicode=True):
                    if not line or not line.strip():
                        continue
                    try:
                        resource = json.loads(line)
                    except ValueError:
                        raise FHIRSyncError("Bulk export file holds an unreadable JSON resource") from None
                    if (not isinstance(resource, dict) or resource.get("resourceType") != item.get("type")
                            or not isinstance(resource.get("id"), str) or not resource["id"]):
                        raise FHIRSyncError("Bulk export contains an invalid or unexpected resource")
                    yield resource

    # ── the sync's interface ──────────────────────────────────────────────────
    def changed_patients(self, since: str) -> Tuple[Set[str], Optional[str]]:
        """Run one export (everything on the first run, then changes since `since`), keep the resources
        in the local copy, and return the patients they belong to and the export's transactionTime."""
        if self.store is None:
            raise FHIRSyncError("Bulk export client is not bound to a loop store")
        full = self.store.mirror_size() == 0
        status_url = self.kick_off(None if full else since)
        try:
            manifest = self.wait(status_url)
            if (not isinstance(manifest, dict) or not isinstance(manifest.get("output"), list)
                    or not isinstance(manifest.get("error", []), list)):
                raise FHIRSyncError("Bulk export manifest is malformed")
            if manifest.get("error"):
                raise FHIRSyncError("Bulk export reported missing data; no records imported or cursor advanced")
            if type(manifest.get("requiresAccessToken", True)) is not bool:
                raise FHIRSyncError("Bulk export token requirement is malformed")
            if any(not isinstance(item, dict) or item.get("type") not in self.resource_types or
                   not isinstance(item.get("url"), str) for item in manifest["output"]):
                raise FHIRSyncError("Bulk export file description is malformed")
            patients: Set[str] = set()
            # Validate/download completely before a single atomic mirror write. Larger
            # exports spill into an automatically deleted, owner-only temporary file.
            try:
                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as staged:
                    for resource in self.download(manifest):
                        rtype = resource["resourceType"]
                        pid = resource["id"] if rtype == "Patient" else _patient_id(resource)
                        if pid:
                            patients.add(pid)
                        staged.write(json.dumps(resource, ensure_ascii=False).encode("utf-8") + b"\n")
                    staged.seek(0)

                    def rows():
                        for line in staged:
                            resource = json.loads(line)
                            rtype = resource["resourceType"]
                            pid = resource["id"] if rtype == "Patient" else _patient_id(resource)
                            yield rtype, pid, resource["id"], resource

                    count = self.store.mirror_upsert(rows())
            except OSError:
                raise FHIRSyncError("Bulk export could not be staged safely") from None
            self.last_export = {"full": full, "resources": count, "patients": len(patients),
                                "server_errors": 0, "transaction_time": manifest.get("transactionTime"),
                                "requested_types": list(self.resource_types), "output_format": self.output_format}
            return patients, manifest.get("transactionTime")
        finally:
            self.cancel(status_url)

    def patient_history(self, patient_id: str) -> List[Dict]:
        if self.store is None:
            raise FHIRSyncError("Bulk export client is not bound to a loop store")
        return self.store.mirror_history(patient_id)


def bulk_client_from_env(base: str, token: Optional[str], auth) -> BulkFHIRClient:
    minutes = float(os.environ.get("CLINLOOP_FHIR_BULK_TIMEOUT_MINUTES", "60"))
    return BulkFHIRClient(base, token=token, auth=auth, group_id=os.environ.get("CLINLOOP_FHIR_GROUP_ID") or None,
                          max_wait_seconds=minutes * 60,
                          resource_types=([t.strip() for t in os.environ["CLINLOOP_FHIR_BULK_TYPES"].split(",")]
                                          if "CLINLOOP_FHIR_BULK_TYPES" in os.environ else None),
                          output_format=(None if os.environ.get("CLINLOOP_FHIR_BULK_OUTPUT_FORMAT") == "default"
                                         else os.environ.get("CLINLOOP_FHIR_BULK_OUTPUT_FORMAT", "application/fhir+ndjson")))
