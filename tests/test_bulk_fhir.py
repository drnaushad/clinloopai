"""
test_bulk_fhir.py — Reading a FHIR server through Bulk FHIR export ($export)

A stub server implements the Bulk Data Access flow: Group-level kick-off, 202 polling with
Retry-After, a manifest of NDJSON files, _since for later runs and DELETE to clean up.
Synthetic data only.
"""

import copy
import json
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.bulk_fhir import BulkFHIRClient
from src.clinloop_engine.fhir_sync import check_connection, client_from_env, patient_record, sync_once
from src.clinloop_engine.loop_store import LoopStore

TOKEN = "stub-bulk-token-0123456789"
NOW = datetime(2026, 9, 1)


def _resources():
    with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    out = []
    for e in bundle["entry"]:
        r = copy.deepcopy(e["resource"])
        r["meta"] = {"lastUpdated": "2026-08-30T00:00:00Z"}
        out.append(r)
    return out


class StubBulk:
    def __init__(self, polls_before_ready=2, presigned=False, kickoff_status=202):
        self.resources = _resources()
        self.polls_before_ready = polls_before_ready
        self.presigned = presigned
        self.kickoff_status = kickoff_status
        self.jobs = {}
        self.kickoffs = []
        self.deleted = []
        self.file_auth = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=None, headers=None, raw=None, ctype="application/json"):
                data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorized(self):
                return self.headers.get("Authorization") == f"Bearer {TOKEN}"

            def do_DELETE(self):
                stub.deleted.append(urlparse(self.path).path)
                self._send(202)

            def do_GET(self):
                url = urlparse(self.path)
                path = url.path
                if path == "/metadata":
                    return self._send(200, {"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1",
                                            "rest": [{"mode": "server", "resource": [
                                                {"type": "Group", "operation": [{"name": "export"}]}]}]})
                if path.startswith("/files/"):
                    stub.file_auth.append(self.headers.get("Authorization"))
                    if not stub.presigned and not self._authorized():
                        return self._send(401, {})
                    job, rtype = path.split("/")[2], path.split("/")[3].replace(".ndjson", "")
                    lines = [json.dumps(r) for r in stub.jobs[job]["resources"] if r["resourceType"] == rtype]
                    return self._send(200, raw=("\n".join(lines) + "\n").encode(), ctype="application/fhir+ndjson")
                if not self._authorized():
                    return self._send(401, {})
                if path == "/Group/monitored/$export":
                    q = {k: v[0] for k, v in parse_qs(url.query).items()}
                    stub.kickoffs.append(q)
                    if self.headers.get("Prefer") != "respond-async":
                        return self._send(400, {})
                    if stub.kickoff_status != 202:
                        return self._send(stub.kickoff_status, {"resourceType": "OperationOutcome"})
                    types = set(q["_type"].split(","))
                    hits = [r for r in stub.resources if r["resourceType"] in types
                            and ("_since" not in q or r["meta"]["lastUpdated"] > q["_since"])]
                    job = str(len(stub.jobs) + 1)
                    stub.jobs[job] = {"resources": hits, "polls": 0}
                    return self._send(202, headers={"Content-Location": f"/status/{job}"})
                if path.startswith("/status/"):
                    job = stub.jobs[path.split("/")[2]]
                    job["polls"] += 1
                    if job["polls"] <= stub.polls_before_ready:
                        return self._send(202, headers={"Retry-After": "2", "X-Progress": "in progress"})
                    jid = path.split("/")[2]
                    types = sorted({r["resourceType"] for r in job["resources"]})
                    return self._send(200, {"transactionTime": f"2026-08-31T0{len(stub.jobs)}:00:00Z",
                                            "request": "…", "requiresAccessToken": not stub.presigned,
                                            "output": [{"type": t, "url": f"{stub.base}/files/{jid}/{t}.ndjson"} for t in types],
                                            "error": []})
                self._send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


class TestBulkFHIR(unittest.TestCase):

    def setUp(self):
        self.stub = StubBulk()
        self.slept = []
        self.client = BulkFHIRClient(self.stub.base, token=TOKEN, group_id="monitored", sleep=self.slept.append)
        self.store = LoopStore()

    def tearDown(self):
        self.stub.close()

    def test_first_run_exports_everything_and_builds_the_worklist(self):
        result = sync_once(self.store, self.client, now=NOW)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["patients"], 7)
        self.assertNotIn("_since", self.stub.kickoffs[0])                 # full export first
        self.assertEqual(self.slept, [2.0, 2.0])                          # honoured Retry-After
        self.assertEqual(self.stub.deleted, ["/status/1"])                # cleaned up
        self.assertTrue({"R017", "R003", "R009", "R006"} <= {l["rule_id"] for l in self.store.worklist()})
        self.assertEqual(result["cursor"], "2026-08-31T01:00:00Z")        # transactionTime

    def test_later_run_exports_changes_and_uses_the_whole_local_history(self):
        sync_once(self.store, self.client, now=NOW)
        self.stub.resources.append({
            "resourceType": "Procedure", "id": "col-1", "status": "completed",
            "subject": {"reference": "Patient/SYN-001"}, "performedDateTime": "2026-08-31T09:00:00Z",
            "code": {"text": "Colonoscopy"}, "meta": {"lastUpdated": "2026-08-31T10:00:00Z"}})
        result = sync_once(self.store, self.client, now=NOW + timedelta(hours=1))
        self.assertEqual(self.stub.kickoffs[1]["_since"], "2026-08-31T01:00:00Z")
        self.assertEqual(result["patients"], 1)
        self.assertEqual(result["loops"]["resolved_by_engine"], 1)      # the FIT from the first export is closed
        history, _ = patient_record("SYN-001", self.store, self.client)
        self.assertIn("col-1", {r["id"] for r in history})

    def test_presigned_files_are_fetched_without_clinloops_token(self):
        stub = StubBulk(polls_before_ready=0, presigned=True)
        try:
            client = BulkFHIRClient(stub.base, token=TOKEN, group_id="monitored", sleep=lambda s: None)
            self.assertTrue(sync_once(LoopStore(), client, now=NOW)["ok"])
            self.assertEqual(set(stub.file_auth), {None})
        finally:
            stub.close()

    def test_export_that_never_finishes_is_cancelled_and_reported(self):
        stub = StubBulk(polls_before_ready=1000)
        try:
            client = BulkFHIRClient(stub.base, token=TOKEN, group_id="monitored", sleep=lambda s: None,
                                    max_wait_seconds=10)
            store = LoopStore()
            result = sync_once(store, client, now=NOW)
            self.assertFalse(result["ok"])
            self.assertIn("not ready", result["error"])
            self.assertEqual(stub.deleted, ["/status/1"])
            self.assertIsNone(store.get_cursor("fhir-sync"))              # nothing is skipped next time
        finally:
            stub.close()

    def test_refused_export_fails_loudly(self):
        stub = StubBulk(kickoff_status=403)
        try:
            client = BulkFHIRClient(stub.base, token=TOKEN, group_id="monitored", sleep=lambda s: None)
            result = sync_once(LoopStore(), client, now=NOW)
            self.assertFalse(result["ok"])
            self.assertIn("HTTP 403", result["error"])
        finally:
            stub.close()

    def test_connection_check_in_bulk_mode(self):
        report = check_connection(self.client)
        self.assertEqual(report["mode"], "bulk export")
        self.assertTrue(report["export"]["declared"])
        self.assertTrue(report["ok"], report)
        self.assertEqual(self.stub.kickoffs, [])                         # the check starts no export

    def test_environment_selects_bulk_mode(self):
        keys = ("CLINLOOP_FHIR_BASE", "CLINLOOP_FHIR_MODE", "CLINLOOP_FHIR_GROUP_ID", "CLINLOOP_FHIR_CLIENT_ID")
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            os.environ.update(CLINLOOP_FHIR_BASE=self.stub.base, CLINLOOP_FHIR_MODE="bulk",
                              CLINLOOP_FHIR_GROUP_ID="monitored")
            client = client_from_env()
            self.assertIsInstance(client, BulkFHIRClient)
            self.assertEqual(client.export_url, f"{self.stub.base}/Group/monitored/$export")
            os.environ["CLINLOOP_FHIR_MODE"] = "nonsense"
            from src.clinloop_engine.fhir_sync import FHIRSyncError
            with self.assertRaises(FHIRSyncError):
                client_from_env()
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
