"""
test_medgemma.py — MedGemma on the on-premise Ollama: model order, second-reader model, VLM default,
compose pull list. Ollama's HTTP API is mocked; no network.
"""

import os
import re
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import local_llm_engine, second_reader  # noqa: E402
from src.clinloop_engine.imaging_ai import VisionLanguageModel  # noqa: E402


def _tags(*names):
    def transport(method, path, payload=None, **kwargs):
        if path == "/api/show":
            return {"capabilities": ["completion"]}
        return {"models": [{"name": n, "digest": "a" * 64} for n in names]}
    return mock.patch.object(local_llm_engine, "_ollama_json", side_effect=transport)


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLINLOOP_LLM_MODEL", "CLINLOOP_SECOND_READER_MODEL", "CLINLOOP_VLM_MODEL")}
    env.update(extra)
    return mock.patch.dict(os.environ, env, clear=True)


class ModelOrder(unittest.TestCase):
    def test_exaone_first_then_medgemma_text_then_vision_last(self):
        with _clean_env(), _tags("medgemma:4b", "medgemma:27b", "exaone3.5:7.8b", "llama3:latest"):
            names = [m["name"] for m in local_llm_engine.get_available_models()]
            self.assertEqual(names, ["exaone3.5:7.8b", "medgemma:27b", "llama3:latest", "medgemma:4b"])
            self.assertEqual(local_llm_engine.get_best_model(), "exaone3.5:7.8b")

    def test_medgemma_labels_and_roles(self):
        known = {m["name"]: m for m in local_llm_engine.PREFERRED_MODELS}
        self.assertEqual(known["medgemma:4b"]["role"], "vision")
        self.assertEqual(known["medgemma:27b"]["role"], "report reader")
        self.assertIn("verify installed capabilities", known["medgemma:27b"]["label"])


class SecondReaderModel(unittest.TestCase):
    def test_medgemma_27b_when_installed(self):
        with _clean_env(), _tags("exaone3.5:7.8b", "medgemma:27b"):
            self.assertEqual(local_llm_engine.get_second_reader_model(), "medgemma:27b")

    def test_no_substitute_without_medgemma(self):
        """The configured reader or nothing: never another model under MedGemma's evaluation."""
        with _clean_env(), _tags("exaone3.5:7.8b", "qwen2.5:7b"):
            self.assertIsNone(local_llm_engine.get_second_reader_model())
        with _clean_env(CLINLOOP_SECOND_READER_MODEL="medgemma:27b-q8"), _tags("medgemma:27b", "exaone3.5:7.8b"):
            self.assertIsNone(local_llm_engine.get_second_reader_model())

    def test_env_override_when_installed(self):
        with _clean_env(CLINLOOP_SECOND_READER_MODEL="qwen2.5:7b"), _tags("exaone3.5:7.8b", "qwen2.5:7b", "medgemma:27b"):
            self.assertEqual(local_llm_engine.get_second_reader_model(), "qwen2.5:7b")

    def test_none_when_no_models(self):
        with _clean_env(), _tags():
            self.assertIsNone(local_llm_engine.get_second_reader_model())

    def test_second_reader_passes_its_model(self):
        with _clean_env(), _tags("exaone3.5:7.8b", "medgemma:27b"), \
                mock.patch.object(local_llm_engine, "OLLAMA_BASE_URL", "http://127.0.0.1:11434"), \
                mock.patch.object(local_llm_engine, "generate_clinical_text", return_value={"text": "{}"}) as gen:
            call = second_reader.local_model()
            self.assertIsNotNone(call)
            call("p", "s")
            self.assertEqual(gen.call_args.kwargs["model"], "medgemma:27b")


class Deployment(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "docker-compose.yml"), encoding="utf-8") as f:
            self.compose = f.read()

    def test_vlm_default_is_medgemma_4b(self):
        with _clean_env():
            self.assertEqual(VisionLanguageModel().model, "medgemma:4b")
        self.assertIn("CLINLOOP_VLM_MODEL: ${CLINLOOP_VLM_MODEL:-medgemma:4b}", self.compose)

    def test_pull_list_includes_both_medgemma_sizes(self):
        m = re.search(r"CLINLOOP_PULL_MODELS: \$\{CLINLOOP_PULL_MODELS:-(.+)\}\s*$", self.compose, re.M)
        self.assertIsNotNone(m)
        for tag in ("exaone3.5:7.8b", "medgemma:4b", "medgemma:27b"):
            self.assertIn(tag, m.group(1))
        self.assertIn("ollama pull", self.compose)
        self.assertIn("$$CLINLOOP_PULL_MODELS", self.compose)


if __name__ == "__main__":
    unittest.main()
