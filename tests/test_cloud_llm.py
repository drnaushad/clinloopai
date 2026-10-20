"""
test_cloud_llm.py — Optional cloud models: research profile only, off unless enabled, identifiers removed.
Synthetic text; providers are mocked (no network).
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import cloud_llm, local_llm_engine, second_reader  # noqa: E402

ON = {"CLINLOOP_PROFILE": "research", "CLINLOOP_CLOUD_LLM": "anthropic", "ANTHROPIC_API_KEY": "test-key",
      "CLINLOOP_ANTHROPIC_MODEL": "", "CLINLOOP_SECOND_READER_MODEL": "", "CLINLOOP_LLM_MODEL": ""}


class TestCloudGate(unittest.TestCase):

    def test_core_profile_never_sends(self):
        with mock.patch.dict(os.environ, dict(ON, CLINLOOP_PROFILE="core")):
            self.assertIn("core", cloud_llm.status("anthropic"))
            out = cloud_llm.generate("cloud:anthropic", "Synthetic report.", "system")
        self.assertIn("not available", out["error"])
        self.assertFalse(out["on_premise"])

    def test_off_unless_listed_and_keyed(self):
        with mock.patch.dict(os.environ, dict(ON, CLINLOOP_CLOUD_LLM="")):
            self.assertIn("CLINLOOP_CLOUD_LLM", cloud_llm.status("anthropic"))
        with mock.patch.dict(os.environ, dict(ON, ANTHROPIC_API_KEY="")):
            self.assertIn("ANTHROPIC_API_KEY", cloud_llm.status("anthropic"))

    def test_openai_and_gemini_need_an_explicit_model(self):
        env = dict(ON, CLINLOOP_CLOUD_LLM="openai,gemini", OPENAI_API_KEY="k", GEMINI_API_KEY="k",
                   CLINLOOP_OPENAI_MODEL="", CLINLOOP_GEMINI_MODEL="")
        with mock.patch.dict(os.environ, env):
            self.assertIn("CLINLOOP_OPENAI_MODEL", cloud_llm.status("openai"))
            self.assertIn("CLINLOOP_GEMINI_MODEL", cloud_llm.status("gemini"))

    def test_identifiers_removed_before_sending_and_output_labelled(self):
        seen = {}

        def fake(model, prompt, system, max_tokens):
            seen.update(model=model, prompt=prompt)
            return "Repeat chest CT in 3 months."
        with mock.patch.dict(os.environ, ON), mock.patch.dict(cloud_llm._CALL, {"anthropic": fake}):
            out = cloud_llm.generate("cloud:anthropic", "Patient phone 010-1234-5678. 9 mm nodule.", "system")
        self.assertEqual(seen["model"], "claude-opus-5-5")
        self.assertNotIn("010-1234-5678", seen["prompt"])
        self.assertEqual(out["model"], "anthropic:claude-opus-5-5")
        self.assertTrue(out["cloud"] and not out["on_premise"])

    def test_provider_error_is_generic(self):
        def boom(*a):
            raise RuntimeError("secret detail")
        with mock.patch.dict(os.environ, ON), mock.patch.dict(cloud_llm._CALL, {"anthropic": boom}):
            out = cloud_llm.generate("cloud:anthropic", "x", "y")
        self.assertEqual(out["error"], "The cloud model did not answer")


class TestCloudRouting(unittest.TestCase):

    def test_generate_clinical_text_routes_cloud_models(self):
        with mock.patch.dict(os.environ, ON), \
                mock.patch.dict(cloud_llm._CALL, {"anthropic": lambda *a: "draft"}):
            out = local_llm_engine.generate_clinical_text("Synthetic context", model="cloud:anthropic")
        self.assertEqual((out["text"], out["cloud"]), ("draft", True))

    def test_second_reader_uses_cloud_only_when_available(self):
        with mock.patch.dict(os.environ, dict(ON, CLINLOOP_SECOND_READER_MODEL="cloud:anthropic")):
            self.assertEqual(local_llm_engine.get_second_reader_model(), "cloud:anthropic")
            self.assertIsNotNone(second_reader.local_model())
        with mock.patch.dict(os.environ, dict(ON, CLINLOOP_SECOND_READER_MODEL="cloud:anthropic", CLINLOOP_PROFILE="core")):
            self.assertIsNone(local_llm_engine.get_second_reader_model())     # no substitute either
            self.assertIsNone(second_reader.local_model())


if __name__ == "__main__":
    unittest.main()
