"""
test_fhir_sync.py — Live FHIR sync and fail-loud feed monitoring

Runs against a stub FHIR R4 server (real HTTP, Bundle paging, bearer auth)
serving the synthetic example bundle.
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

from src.clinloop_engine.fhir_ingest import _patient_id
from src.clinloop_engine.fhir_sync import FHIRClient, sync_once
from src.clinloop_engine.loop_store import LoopStore

TOKEN = "stub-fhir-token"
NOW = datetime(2026, 9, 1)


class StubFHIR:
    """In-memory FHIR server: _lastUpdated=gt, patient=, _id=, paging of 2 per page."""

    def __init__(self, resources):
        self.resources = resources
        self.down = False
        self.requests = 0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                stub.requests += 1
                if stub.down:
                    return self._send(503, {"resourceType": "OperationOutcome"})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._send(401, {"resourceType": "OperationOutcome"})
                url = urlparse(self.path)
                rtype = url.path.strip("/").split("/")[-1]
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                hits = [r for r in stub.resources if r["resourceType"] == rtype]
                if "_lastUpdated" in q:
                    since = q["_lastUpdated"][2:]
                    hits = [r for r in hits if r["meta"]["lastUpdated"] > since]
                if "patient" in q:
                    pid = q["patient"].split("/")[-1]
                    hits = [r for r in hits if _patient_id(r) == pid]
                if "_id" in q:
                    hits = [r for r in hits if r["id"] == q["_id"]]
                page, size = int(q.get("_page", 0)), 2
                bundle = {"resourceType": "Bundle", "type": "searchset",
                          "entry": [{"resource": r} for r in hits[page * size:(page + 1) * size]], "link": []}
                if (page + 1) * size < len(hits):
                    nxt = dict(q, _page=str(page + 1))
                    query = "&".join(f"{k}={v}" for k, v in nxt.items())
                    bundle["link"].append({"relation": "next", "url": f"{stub.base}/{rtype}?{query}"})
                self._send(200, bundle)

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/fhir+json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def _resources():
    with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    out = []
    for e in bundle["entry"]:
        r = copy.deepcopy(e["resource"])
        r["meta"] = {"lastUpdated": "2026-08-30T00:00:00Z"}
        out.append(r)
    return out


class TestFHIRSync(unittest.TestCase):

    def setUp(self):
        self.stub = StubFHIR(_resources())
        self.client = FHIRClient(self.stub.base, token=TOKEN)
        self.store = LoopStore()

    def tearDown(self):
        self.stub.close()

    def test_first_sync_pulls_everything_through_paging(self):
        result = sync_once(self.store, self.client, now=NOW)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["patients"], 7)
        rules = {l["rule_id"] for l in self.store.worklist()}
        self.assertTrue({"R017", "R003", "R009", "R006"} <= rules)
        self.assertEqual(self.store.feed_status(now=NOW)["status"], "OK")

    def test_second_sync_only_fetches_changed_patients(self):
        sync_once(self.store, self.client, now=NOW)
        # A colonoscopy is recorded for SYN-001 → its FIT loop must resolve
        self.stub.resources.append({
            "resourceType": "Procedure", "id": "col-1", "status": "completed",
            "subject": {"reference": "Patient/SYN-001"}, "performedDateTime": "2026-08-31T09:00:00Z",
            "code": {"text": "Colonoscopy"}, "meta": {"lastUpdated": "2026-08-31T10:00:00Z"}})
        result = sync_once(self.store, self.client, now=NOW + timedelta(hours=1))
        self.assertEqual(result["patients"], 1)
        self.assertEqual(result["loops"]["resolved_by_engine"], 1)
        self.assertNotIn("R017", {l["rule_id"] for l in self.store.worklist()})

    def test_unchanged_server_means_no_work(self):
        sync_once(self.store, self.client, now=NOW)
        result = sync_once(self.store, self.client, now=NOW + timedelta(hours=1))
        self.assertEqual(result["patients"], 0)

    def test_bad_token_is_recorded_as_failure(self):
        result = sync_once(self.store, FHIRClient(self.stub.base, token="wrong"), now=NOW)
        self.assertFalse(result["ok"])
        self.assertIn("401", result["error"])

    def test_outage_turns_feed_failing_and_raises_one_alarm(self):
        sync_once(self.store, self.client, now=NOW)
        self.stub.down = True
        for h in (1, 2, 3):
            self.assertFalse(sync_once(self.store, self.client, now=NOW + timedelta(hours=h))["ok"])
        self.assertEqual(self.store.feed_status(now=NOW + timedelta(hours=3))["status"], "FAILING")
        self.assertIsNotNone(self.store.check_feed(now=NOW + timedelta(hours=3)))
        self.assertIsNone(self.store.check_feed(now=NOW + timedelta(hours=4)))  # not repeated within window
        self.assertTrue(self.store.verify_audit_chain())


class TestFeedStatus(unittest.TestCase):

    def test_never_then_ok_then_stale(self):
        store = LoopStore()
        self.assertEqual(store.feed_status(now=NOW)["status"], "NEVER")
        store.record_ingest("manual", "it", ok=True, now=NOW)
        self.assertEqual(store.feed_status(now=NOW + timedelta(hours=2))["status"], "OK")
        stale = store.feed_status(max_silence_hours=24, now=NOW + timedelta(hours=30))
        self.assertEqual(stale["status"], "STALE")
        self.assertEqual(store.check_feed(now=NOW + timedelta(hours=30))["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
