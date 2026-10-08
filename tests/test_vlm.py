"""
test_vlm.py — Vision-language model adapter (e.g. MedGemma on an on-premise Ollama / OpenAI-compatible server)

A stand-in HTTP server on localhost plays the model, so the real request and
response formats are exercised without downloading model weights. Images are
synthetic.
"""

import json
import os
import sys
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from test_imaging import HAVE_DICOM, P, loops, make_dicom, phantom, rad  # noqa: E402

from src.clinloop_engine.imaging_ai import VisionLanguageModel, _json_object, _on_premise, analyze_dicom  # noqa: E402


class StandInModel(BaseHTTPRequestHandler):
    """Answers like Ollama (/api/chat) or an OpenAI-compatible server (/v1/chat/completions)."""
    answer = "{}"
    requests = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        StandInModel.requests.append((self.path, body))
        if self.path == "/api/chat":
            out = {"message": {"role": "assistant", "content": StandInModel.answer}}
        elif self.path == "/v1/chat/completions":
            out = {"choices": [{"message": {"role": "assistant", "content": StandInModel.answer}}]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@unittest.skipUnless(HAVE_DICOM, "pydicom not installed")
class TestVisionLanguageModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), StandInModel)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        StandInModel.requests = []

    def run_model(self, answer, api="ollama", body="CHEST", modality="DX", desc="Chest PA"):
        StandInModel.answer = answer
        env = {"CLINLOOP_VLM_URL": self.url, "CLINLOOP_VLM_API": api, "CLINLOOP_VLM_MODEL": "medgemma-4b-it"}
        with mock.patch.dict(os.environ, env):
            model = VisionLanguageModel()
            self.assertIsNone(model.available())
            return analyze_dicom(make_dicom(phantom(), modality=modality, body=body, desc=desc), "P",
                                 ["MRN-0042"], models=[model], with_preview=False)

    def test_ollama_answer_becomes_findings_and_a_draft_description(self):
        answer = ('```json\n{"description": "Rounded opacity in the right upper zone.", "findings": ['
                  '{"key": "lung_nodule", "present": true, "confidence": 0.8},'
                  '{"key": "pneumothorax", "present": false, "confidence": 0.1}]}\n```')
        r = self.run_model(answer)
        m = r["models"][0]
        self.assertTrue(m["ran"])
        self.assertEqual(m["description"], "Rounded opacity in the right upper zone.")
        self.assertIn("not stored", m["description_note"])
        self.assertEqual([(f["finding_key"], f["positive"]) for f in m["findings"]],
                         [("lung_nodule", True), ("pneumothorax", False)])
        obs = [x for x in r["resources"] if x["resourceType"] == "Observation"]
        self.assertEqual(len(obs), 1)
        self.assertNotIn("Rounded opacity", json.dumps(r["resources"]))      # free text is never filed
        path, req = StandInModel.requests[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(req["model"], "medgemma-4b-it")
        self.assertTrue(req["messages"][0]["images"][0])                      # a PNG, base64
        self.assertIn("lung_nodule", req["messages"][0]["content"])           # the fixed vocabulary is in the prompt

    def test_openai_compatible_server(self):
        r = self.run_model('{"description": "x", "findings": [{"key": "pleural_effusion", "present": "yes", '
                           '"confidence": 0.7}]}', api="openai")
        path, req = StandInModel.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(req["messages"][0]["content"][1]["type"], "image_url")
        self.assertEqual([f["finding_key"] for f in r["models"][0]["findings"] if f["positive"]], ["pleural_effusion"])

    def test_invented_labels_and_wrong_region_findings_are_dropped(self):
        answer = json.dumps({"description": "x", "findings": [
            {"key": "lung cancer stage IV", "present": True, "confidence": 0.99},
            {"key": "pneumothorax", "present": True, "confidence": 0.9},          # on a head CT
            {"key": "intracranial_hemorrhage", "present": True, "confidence": 1.7}]})  # bad confidence
        r = self.run_model(answer, body="HEAD", modality="CT", desc="CT BRAIN")
        m = r["models"][0]
        self.assertEqual([f["finding_key"] for f in m["findings"]], ["intracranial_hemorrhage"])
        self.assertIsNone(m["findings"][0]["score"])
        self.assertEqual(len(m["dropped"]), 2)

    def test_unparseable_answer_files_no_findings(self):
        r = self.run_model("I think there might be something in the lung.")
        self.assertTrue(r["models"][0]["unparsed"])
        self.assertEqual([x["resourceType"] for x in r["resources"]], ["ImagingStudy"])

    def test_research_use_finding_needs_opt_in_for_review(self):
        r = self.run_model('{"description": "", "findings": [{"key": "lung_nodule", "present": true}]}')
        study = r["resources"][0]
        report = rad("r1", "2026-01-10T10:00:00Z", "Chest radiograph PA", "No acute cardiopulmonary abnormality.",
                     "ImagingStudy/" + study["id"])
        self.assertEqual(loops([P, *r["resources"], report], datetime(2026, 1, 20))[0], {})
        with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_RESEARCH_AI": "1"}):
            self.assertEqual(loops([P, *r["resources"], report], datetime(2026, 1, 20))[0], {"R047": "open"})


class TestVLMSafeguards(unittest.TestCase):

    def test_images_never_leave_the_hospital_network(self):
        self.assertTrue(_on_premise("http://127.0.0.1:11434"))
        self.assertTrue(_on_premise("http://10.2.3.4:8000"))
        self.assertTrue(_on_premise("http://192.168.0.10"))
        self.assertFalse(_on_premise("https://8.8.8.8/v1"))
        with mock.patch.dict(os.environ, {"CLINLOOP_VLM_URL": "https://8.8.8.8/v1"}):
            self.assertIn("refused", VisionLanguageModel().available())
        with mock.patch.dict(os.environ, {"CLINLOOP_VLM_URL": ""}):
            self.assertIn("not configured", VisionLanguageModel().available())

    def test_json_is_found_inside_prose(self):
        self.assertEqual(_json_object('Sure! {"a": {"b": 1}} hope this helps'), {"a": {"b": 1}})
        self.assertEqual(_json_object("no json {here"), {})
        self.assertEqual(_json_object('[1, 2] {"x": 2}'), {"x": 2})


class TestVendorTemplate(unittest.TestCase):
    """docs/imaging_models.example.json loads, and every mapped label reaches a ClinLoop finding type."""

    def test_template_loads_and_maps(self):
        from src.clinloop_engine.imaging_ai import HTTPImagingModel, registered_models
        from src.clinloop_engine.imaging_fhir import ai_finding_key, regulatory_unverified
        path = os.path.join(ROOT, "docs", "imaging_models.example.json")
        with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_MODELS_CONFIG": path, "CLINLOOP_IMAGING_MODELS": ""}):
            models = registered_models()
        self.assertEqual(len(models), 4)
        for m in models:
            self.assertIsInstance(m, HTTPImagingModel)
            self.assertFalse(regulatory_unverified(m.regulatory), m.name)
            for target in m.label_map.values():
                self.assertIsNotNone(ai_finding_key(target, m.body_regions), (m.name, target))


if __name__ == "__main__":
    unittest.main()
