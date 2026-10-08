"""
test_literature.py — Live PubMed / Europe PMC connections and the status endpoint

Runs against a stub server that speaks the NCBI E-utilities and Europe PMC
REST formats, so the real HTTP clients are exercised without internet access.
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import literature
from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES


class StubLiterature:
    def __init__(self):
        self.down = False
        self.hits = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                stub.hits.append((url.path, q))
                if stub.down:
                    return self._send(503, {})
                if url.path.endswith("/einfo.fcgi"):
                    return self._send(200, {"einforesult": {"dblist": ["pubmed"]}})
                if url.path.endswith("/esearch.fcgi"):
                    return self._send(200, {"esearchresult": {"idlist": ["28240562", "32243307"]}})
                if url.path.endswith("/esummary.fcgi"):
                    return self._send(200, {"result": {
                        "uids": ["28240562", "32243307"],
                        "28240562": {"title": "Guidelines for Management of Incidental Pulmonary Nodules.",
                                     "fulljournalname": "Radiology", "pubdate": "2017 Jul"},
                        "32243307": {"title": "2019 ASCCP Risk-Based Management Consensus Guidelines.",
                                     "fulljournalname": "J Low Genit Tract Dis", "pubdate": "2020 Apr"}}})
                if url.path.endswith("/search"):
                    return self._send(200, {"resultList": {"result": [
                        {"id": "28240562", "source": "MED", "pmid": "28240562", "doi": "10.1148/radiol.2017161659",
                         "title": "Guidelines for Management of Incidental Pulmonary Nodules.",
                         "journalTitle": "Radiology", "pubYear": "2017"}]}})
                self._send(404, {})

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


class TestLiterature(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.stub = StubLiterature()

    @classmethod
    def tearDownClass(cls):
        cls.stub.server.shutdown()

    def setUp(self):
        literature.clear_cache()
        self.stub.down = False
        self.stub.hits.clear()
        os.environ["CLINLOOP_PUBMED_BASE"] = self.stub.base + "/entrez/eutils"
        os.environ["CLINLOOP_EUROPEPMC_BASE"] = self.stub.base + "/europepmc/webservices/rest"

    def tearDown(self):
        for k in ("CLINLOOP_PUBMED_BASE", "CLINLOOP_EUROPEPMC_BASE", "CLINLOOP_LITERATURE"):
            os.environ.pop(k, None)

    def test_every_rule_has_an_evidence_query(self):
        self.assertEqual(set(literature.EVIDENCE_QUERIES), {r.rule_id for r in OBLIGATION_RULES})

    def test_pubmed_search_and_summary(self):
        result = literature.evidence_for_rule("R003", "pubmed")
        first = result["articles"][0]
        self.assertEqual(first["pmid"], "28240562")
        self.assertEqual(first["journal"], "Radiology")
        self.assertEqual(first["year"], "2017")
        self.assertEqual(first["url"], "https://pubmed.ncbi.nlm.nih.gov/28240562/")
        self.assertNotIn(".", first["title"][-1])

    def test_europepmc_search(self):
        result = literature.evidence_for_rule("R003", "europepmc")
        self.assertEqual(result["articles"][0]["doi"], "10.1148/radiol.2017161659")

    def test_only_rule_level_terms_leave_the_server(self):
        literature.evidence_for_rule("R017", "pubmed")
        sent = [q.get("term") for path, q in self.stub.hits if path.endswith("esearch.fcgi")]
        self.assertEqual(sent, [literature.EVIDENCE_QUERIES["R017"]])

    def test_searches_are_cached(self):
        literature.evidence_for_rule("R003", "pubmed")
        n = len(self.stub.hits)
        literature.evidence_for_rule("R003", "pubmed")
        self.assertEqual(len(self.stub.hits), n)

    def test_status_ok_and_unreachable(self):
        self.assertEqual(literature.pubmed_status()["status"], "ok")
        literature.clear_cache()
        self.stub.down = True
        status = literature.europepmc_status()
        self.assertEqual(status["status"], "unreachable")
        self.assertIn("503", status["error"])

    def test_can_be_switched_off(self):
        os.environ["CLINLOOP_LITERATURE"] = "off"
        self.assertEqual(literature.pubmed_status()["status"], "disabled")
        with self.assertRaises(literature.LiteratureError):
            literature.search_pubmed("anything")


try:
    from fastapi.testclient import TestClient
    os.environ.setdefault("CLINLOOP_API_TOKENS", "lit-test-admin-token-0123:t:admin")
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestConnectionsAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.stub = StubLiterature()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.stub.server.shutdown()

    def setUp(self):
        literature.clear_cache()
        os.environ["CLINLOOP_PUBMED_BASE"] = self.stub.base + "/entrez/eutils"
        os.environ["CLINLOOP_EUROPEPMC_BASE"] = self.stub.base + "/europepmc/webservices/rest"

    def tearDown(self):
        os.environ.pop("CLINLOOP_PUBMED_BASE", None)
        os.environ.pop("CLINLOOP_EUROPEPMC_BASE", None)

    def test_status_reports_real_state_without_secrets(self):
        body = self.client.get("/api/v1/connections/status").json()
        self.assertEqual(body["pubmed"]["status"], "ok")
        self.assertEqual(body["europe_pmc"]["status"], "ok")
        self.assertEqual(body["fhir_server"]["status"], "not_configured")
        self.assertEqual(body["omop_cdm"]["status"], "not_connected")
        self.assertEqual(body["cloud_llm"]["status"], "not_used")
        self.assertNotIn(self.stub.base, json.dumps(body))      # no hostnames leaked

    def test_evidence_endpoint(self):
        body = self.client.get("/api/v1/evidence/R003?source=pubmed&limit=2").json()
        self.assertEqual(body["articles"][0]["pmid"], "28240562")
        self.assertEqual(self.client.get("/api/v1/evidence/R999").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/evidence/R003?source=google").status_code, 422)

    def test_evidence_endpoint_reports_outage(self):
        self.stub.down = True
        try:
            r = self.client.get("/api/v1/evidence/R005?source=europepmc")
            self.assertEqual(r.status_code, 502)
        finally:
            self.stub.down = False


if __name__ == "__main__":
    unittest.main()
