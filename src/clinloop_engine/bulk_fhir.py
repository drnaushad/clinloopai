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
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode, urljoin

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
                 store=None, max_wait_seconds: float = 3600.0, sleep: Callable[[float], None] = time.sleep):
        super().__init__(base_url, token=token, timeout=timeout, session=session, auth=auth)
        self.group_id = group_id
        self.store = store
        self.max_wait_seconds = max_wait_seconds
        self.sleep = sleep
        self.last_export: Dict = {}

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
        for attempt in (0, 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kw)
            except SMARTAuthError as e:
                raise FHIRSyncError(f"FHIR login failed: {e}") from None
            invalidate = getattr(self.session.auth, "invalidate", None)
            if resp.status_code == 401 and invalidate and attempt == 0:
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
        params = {"_type": ",".join(EXPORT_TYPES), "_outputFormat": "application/fhir+ndjson"}
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
            logger.info("Bulk export in progress (%s); checking again in %ss",
                        (resp.headers.get("X-Progress") or "no progress reported")[:60], int(delay))
            self.sleep(delay)
            waited += delay

    def cancel(self, status_url: str) -> None:
        try:
            self._request("DELETE", status_url)
        except (FHIRSyncError, requests.RequestException):
            pass                                  # cleaning up is a courtesy; the server expires files anyway

    def download(self, manifest: Dict) -> Iterable[Dict]:
        """Every resource in the manifest's output files. Files hosted elsewhere (pre-signed storage
        links, requiresAccessToken false) are fetched without ClinLoop's token."""
        with_token = bool(manifest.get("requiresAccessToken", True))
        for item in manifest.get("output", []):
            url = item.get("url")
            if not url:
                continue
            headers = {"Accept": "application/fhir+ndjson"}
            try:
                resp = (self._request("GET", url, headers=headers, stream=True) if with_token
                        else requests.get(url, headers=headers, timeout=self.timeout, stream=True))
            except requests.RequestException as e:
                raise FHIRSyncError(f"Bulk export file unreachable ({type(e).__name__})") from None
            if resp.status_code != 200:
                raise FHIRSyncError(f"Bulk export file for {item.get('type', '?')}: HTTP {resp.status_code}")
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.strip():
                    continue
                try:
                    resource = json.loads(line)
                except ValueError:
                    raise FHIRSyncError(f"Bulk export file for {item.get('type', '?')} holds a line that is not JSON") from None
                if isinstance(resource, dict) and resource.get("resourceType") and resource.get("id"):
                    yield resource

    # ── the sync's interface ──────────────────────────────────────────────────
    def changed_patients(self, since: str) -> Tuple[Set[str], Optional[str]]:
        """Run one export (everything on the first run, then changes since `since`), keep the resources
        in the local copy, and return the patients they belong to and the export's transactionTime."""
        if self.store is None:
            raise FHIRSyncError("Bulk export client is not bound to a loop store")
        full = self.store.mirror_size() == 0
        status_url = self.kick_off(None if full else since)
        manifest = self.wait(status_url)
        patients: Set[str] = set()
        batch: List[Tuple[str, Optional[str], str, Dict]] = []
        count = 0
        for r in self.download(manifest):
            rtype = r["resourceType"]
            pid = r["id"] if rtype == "Patient" else _patient_id(r)
            if pid:
                patients.add(pid)
            batch.append((rtype, pid, r["id"], r))
            if len(batch) >= 500:
                count += self.store.mirror_upsert(batch)
                batch = []
        count += self.store.mirror_upsert(batch)
        self.cancel(status_url)                  # done with the files: let the server delete them
        errors = len(manifest.get("error") or [])
        self.last_export = {"full": full, "resources": count, "patients": len(patients),
                            "server_errors": errors, "transaction_time": manifest.get("transactionTime")}
        logger.info("Bulk export: %s", self.last_export)
        if errors:
            logger.warning("Bulk export reported %d error file(s) (OperationOutcome); those resources are missing", errors)
        return patients, manifest.get("transactionTime")

    def patient_history(self, patient_id: str) -> List[Dict]:
        if self.store is None:
            raise FHIRSyncError("Bulk export client is not bound to a loop store")
        return self.store.mirror_history(patient_id)


def bulk_client_from_env(base: str, token: Optional[str], auth) -> BulkFHIRClient:
    minutes = float(os.environ.get("CLINLOOP_FHIR_BULK_TIMEOUT_MINUTES", "60"))
    return BulkFHIRClient(base, token=token, auth=auth, group_id=os.environ.get("CLINLOOP_FHIR_GROUP_ID") or None,
                          max_wait_seconds=minutes * 60)
