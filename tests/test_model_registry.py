"""
test_model_registry.py — The model registry reports each role's exact model and never a substitute.
Synthetic: the Ollama server is mocked.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import model_registry, second_reader  # noqa: E402


def _server(installed, caps):
    def get(url, timeout=None):
        r = mock.Mock()
        r.raise_for_status = mock.Mock()
        r.json.return_value = {"models": [{"name": n, "digest": "sha256:" + n, "size": 1,
                                           "details": {"family": "gemma3", "parameter_size": "27B"}} for n in installed]}
        return r

    def post(url, json=None, timeout=None):
        r = mock.Mock()
        r.raise_for_status = mock.Mock()
        r.json.return_value = {"capabilities": caps.get(json["model"], ["completion"])}
        return r
    return mock.patch.multiple(model_registry.requests, get=get, post=post)


ENV = {k: "" for k in ("CLINLOOP_LLM_MODEL", "CLINLOOP_SECOND_READER_MODEL", "CLINLOOP_VLM_MODEL")}


class TestRegistry(unittest.TestCase):

    def test_defaults_available(self):
        with mock.patch.dict(os.environ, ENV), \
                _server(["exaone3.5:7.8b", "medgemma:27b", "medgemma:4b"], {"medgemma:4b": ["completion", "vision"]}):
            reg = model_registry.registry("http://127.0.0.1:11434")
        roles = {r["role"]: r for r in reg["roles"]}
        self.assertTrue(reg["all_available"])
        self.assertEqual(roles["second_reader"]["model"], "medgemma:27b")
        self.assertEqual(roles["second_reader"]["digest"], "sha256:medgemma:27b")
        self.assertTrue(roles["second_reader"]["prompt_version"].startswith("sr-"))
        self.assertEqual(roles["vision"]["model"], "medgemma:4b")

    def test_missing_model_is_unavailable_not_substituted(self):
        with mock.patch.dict(os.environ, ENV), _server(["exaone3.5:7.8b", "medgemma:4b"], {"medgemma:4b": ["vision"]}):
            reg = model_registry.registry("http://127.0.0.1:11434")
        sr = next(r for r in reg["roles"] if r["role"] == "second_reader")
        self.assertEqual((sr["model"], sr["status"]), ("medgemma:27b", "not installed"))
        self.assertFalse(reg["all_available"])

    def test_vision_role_needs_vision_capability(self):
        with mock.patch.dict(os.environ, {**ENV, "CLINLOOP_VLM_MODEL": "exaone3.5:7.8b"}), \
                _server(["exaone3.5:7.8b", "medgemma:27b"], {}):
            reg = model_registry.registry("http://127.0.0.1:11434")
        vision = next(r for r in reg["roles"] if r["role"] == "vision")
        self.assertIn("does not declare 'vision'", vision["status"])

    def test_unreachable_server(self):
        def down(*a, **k):
            raise model_registry.requests.ConnectionError()
        with mock.patch.object(model_registry.requests, "get", down):
            reg = model_registry.registry("http://127.0.0.1:1")
        self.assertTrue(all(r["status"] == "model server unreachable" for r in reg["roles"]))

    def test_second_reader_does_not_run_without_its_model(self):
        with mock.patch("src.clinloop_engine.local_llm_engine.get_second_reader_model", return_value=None), \
                mock.patch("src.clinloop_engine.local_llm_engine.OLLAMA_BASE_URL", "http://127.0.0.1:11434"):
            self.assertIsNone(second_reader.local_model())


class TestNotActionableQuotes(unittest.TestCase):
    """A quote that itself says "not needed", "if indicated" or routine screening is not a flag (synthetic)."""

    def _items(self, report, items):
        import json as _json
        answer = _json.dumps({"items": items})
        return second_reader.read_report(report, lambda p, s: {"text": answer, "model": "test"})

    def test_quoted_no_followup_is_dropped(self):
        rep = "Imp) GB polyp 4 mm - f/u 불필요. Thyroid 0.9 cm nodule; no further evaluation needed."
        out = self._items(rep, [{"category": "imaging_followup", "quote": "GB polyp 4 mm - f/u 불필요."},
                                {"category": "biopsy_or_workup", "quote": "no further evaluation needed"}])
        self.assertEqual((out["items"], out["not_actionable"]), ([], 2))

    def test_conditional_and_screening_are_dropped(self):
        rep = "Further radiographs as clinically indicated. Continue annual screening LDCT in 12 months. 필요시 MRI 고려."
        out = self._items(rep, [{"category": "imaging_followup", "quote": "Further radiographs as clinically indicated."},
                                {"category": "imaging_followup", "quote": "Continue annual screening LDCT in 12 months."},
                                {"category": "imaging_followup", "quote": "필요시 MRI 고려."}])
        self.assertEqual(out["items"], [])

    def test_definite_advice_and_critical_findings_stay(self):
        rep = ("No follow-up imaging was performed; recommend CT chest in 3 months. "
               "No midline shift but acute subdural hematoma 9 mm. 3개월 후 f/u CT 권함.")
        out = self._items(rep, [{"category": "imaging_followup", "quote": "No follow-up imaging was performed; recommend CT chest in 3 months."},
                                {"category": "critical_finding", "quote": "No midline shift but acute subdural hematoma 9 mm."}])
        self.assertEqual([i["category"] for i in out["items"]], ["imaging_followup", "critical_finding"])
        out = self._items(rep, [{"category": "imaging_followup", "quote": "3개월 후 f/u CT 권함."}])
        self.assertEqual(len(out["items"]), 1)


if __name__ == "__main__":
    unittest.main()
