"""
test_biomcp_and_llm.py — BioMCP (real MCP server) and the on-premise LLM

BioMCP tests use the real `biomcp` server (pip install biomcp-python) over
both MCP transports and are skipped when it is not installed. Its upstream
sources may be unreachable from a sandbox, so tool results may be empty;
the tests check the MCP connection, not internet access.

LLM tests run against a stub server speaking the Ollama HTTP API.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import biomcp_client, literature, local_llm_engine
from src.clinloop_engine.outreach import draft_message
from src.clinloop_engine.patient_outreach_agent import FALLBACK_MESSAGES

HAVE_BIOMCP = shutil.which("biomcp") is not None


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(HAVE_BIOMCP, "BioMCP not installed (pip install biomcp-python)")
class TestBioMCPConnection(unittest.TestCase):

    def setUp(self):
        literature.clear_cache()
        os.environ.pop("CLINLOOP_BIOMCP_URL", None)

    def test_stdio_connection_lists_tools(self):
        s = biomcp_client.status(force=True)
        self.assertEqual(s["status"], "ok", s)
        self.assertEqual(s["transport"], "stdio")
        self.assertIn("BioMCP", s["server"])
        self.assertGreaterEqual(s["tools"], 10)
        self.assertIn("article_searcher", s["allowed_tools"])

    def test_streamable_http_connection(self):
        port = _free_port()
        proc = subprocess.Popen(["biomcp", "run", "--mode", "streamable_http", "--host", "127.0.0.1",
                                 "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                    break
                except OSError:
                    time.sleep(0.5)
            os.environ["CLINLOOP_BIOMCP_URL"] = f"http://127.0.0.1:{port}/mcp"
            s = biomcp_client.status(force=True)
            self.assertEqual((s["status"], s["transport"]), ("ok", "streamable_http"), s)
        finally:
            os.environ.pop("CLINLOOP_BIOMCP_URL", None)
            proc.terminate()
            proc.wait(timeout=10)

    def test_rule_article_search_goes_through_mcp(self):
        r = biomcp_client.rule_articles("R017")
        self.assertEqual(r["tool"], "article_searcher")
        self.assertEqual(r["arguments"], {"keywords": [literature.EVIDENCE_QUERIES["R017"]]})
        # Live results, or an explicit note that upstream sources may be unreachable
        self.assertTrue(r["result"] or "note" in r)


class TestBioMCPGuards(unittest.TestCase):

    def setUp(self):
        literature.clear_cache()

    def test_tools_outside_allowlist_are_refused(self):
        with self.assertRaises(biomcp_client.BioMCPError):
            biomcp_client.call_tool("think", {"thought": "x"})
        with self.assertRaises(biomcp_client.BioMCPError):
            biomcp_client.call_tool("alphagenome_predictor", {})

    def test_missing_server_is_reported(self):
        with patch.dict(os.environ, {"CLINLOOP_BIOMCP_COMMAND": "definitely-not-installed-biomcp run"}):
            os.environ.pop("CLINLOOP_BIOMCP_URL", None)
            s = biomcp_client.status(force=True)
        self.assertEqual(s["status"], "not_installed")


class StubOllama:
    """Speaks /api/tags and /api/generate like Ollama."""

    def __init__(self, models, response):
        self.models, self.response, self.prompts = models, response, []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/api/tags":
                    return self._send({"models": [{"name": m} for m in stub.models]})
                self._send({}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.prompts.append(body)
                self._send({"model": body["model"], "response": stub.response, "done": True, "eval_count": 42})

            def _send(self, body, code=200):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


class TestLocalLLM(unittest.TestCase):

    def _with_ollama(self, models, response):
        stub = StubOllama(models, response)
        self.addCleanup(stub.server.shutdown)
        p = patch.object(local_llm_engine, "OLLAMA_BASE_URL", stub.base)
        p.start()
        self.addCleanup(p.stop)
        return stub

    def test_prefers_korean_instruction_model_and_falls_back_to_any(self):
        self._with_ollama(["llama3.1:latest", "mistral:7b", "exaone3.5:7.8b"], "ok")
        names = [m["name"] for m in local_llm_engine.get_available_models()]
        self.assertEqual(names[0], "exaone3.5:7.8b")
        self.assertIn("mistral:7b", names)          # not on the preferred list, still usable

    def test_configured_model_wins(self):
        self._with_ollama(["exaone3.5:7.8b", "mistral:7b"], "ok")
        with patch.dict(os.environ, {"CLINLOOP_LLM_MODEL": "mistral:7b"}):
            self.assertEqual(local_llm_engine.get_best_model(), "mistral:7b")

    def test_reasoning_is_stripped(self):
        self._with_ollama(["deepseek-r1:32b"], "<think>The patient probably has cancer…</think>\nPlease call the clinic.")
        out = local_llm_engine.generate_clinical_text("x")
        self.assertEqual(out["text"], "Please call the clinic.")
        self.assertEqual(local_llm_engine._strip_reasoning("Hello <think>unfinished"), "Hello")

    def test_outreach_uses_local_llm_text(self):
        stub = self._with_ollama(["exaone3.5:7.8b"],
                                 "안녕하세요. 담당 의료진이 권고한 후속 진료가 있어 연락드립니다. 병원에 전화해 예약해 주세요.")
        loop = {"rule_id": "R017", "patient_id": "P", "loop_key": "k", "severity": "high"}
        draft = draft_message(loop, "ko")
        self.assertTrue(draft["text"].startswith("안녕하세요. 담당 의료진이 권고한"))
        self.assertEqual(draft["safety_flags"], [])
        self.assertEqual(stub.prompts[0]["model"], "exaone3.5:7.8b")
        # The prompt carries no diagnosis: only the approved, generic facts
        prompt = stub.prompts[0]["prompt"]
        for word in ("FIT", "colonoscopy", "대장", "cancer", "암"):
            self.assertNotIn(word, prompt)

    def test_unsafe_llm_output_is_replaced(self):
        self._with_ollama(["exaone3.5:7.8b"], "You have cancer. Book now.")
        loop = {"rule_id": "R017", "patient_id": "P", "loop_key": "k", "severity": "high"}
        draft = draft_message(loop, "en")
        self.assertEqual(draft["text"], FALLBACK_MESSAGES["en"])
        self.assertIn("unsupported_claim_blocked_fallback_used", draft["safety_flags"])


if __name__ == "__main__":
    unittest.main()
