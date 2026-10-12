"""
test_compute.py — The Compute badge reports measured hardware, never assumed hardware

ClinLoop's rules engine needs no GPU. compute.py reports what the server really has, and picks the GPU
for CT organ segmentation only when one is present. PyTorch is replaced by a stand-in here, so the tests
run anywhere (with or without a GPU, with or without PyTorch).
"""

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import compute  # noqa: E402


def fake_torch(cuda: bool):
    t = types.ModuleType("torch")
    t.__version__ = "2.5.1+cu124"
    props = types.SimpleNamespace(name="NVIDIA L4", total_memory=24 * 1024 ** 3)
    t.cuda = types.SimpleNamespace(is_available=lambda: cuda, get_device_properties=lambda i: props,
                                   device_count=lambda: 1)
    t.version = types.SimpleNamespace(cuda="12.4" if cuda else None)
    t.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    return t


class TestCompute(unittest.TestCase):

    def probe(self, torch_module, env=None):
        modules = {"torch": torch_module}
        with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, env or {}, clear=False):
            compute.hardware(refresh=True)
            status = compute.compute_status()
            device = compute.ct_segmentation_device()
        compute.hardware(refresh=True)          # leave the real probe cached for other tests
        return status, device

    def test_no_pytorch_means_cpu_and_no_invented_gpu(self):
        status, device = self.probe(None)       # None in sys.modules makes "import torch" fail
        self.assertFalse(status["torch_installed"])
        self.assertFalse(status["gpu_available"])
        self.assertIsNone(status["gpu_name"])
        self.assertIsNone(status["gpu_memory_total_gb"])
        self.assertEqual(device, "cpu")
        self.assertEqual(status["uses"]["rules_engine"]["runs_on"], "cpu")

    def test_cpu_only_server(self):
        status, device = self.probe(fake_torch(cuda=False))
        self.assertTrue(status["torch_installed"])
        self.assertEqual(status["accelerator"], "cpu")
        self.assertIn("CPU only", status["summary"])
        self.assertEqual(device, "cpu")

    def test_gpu_server_reports_the_real_card_and_ct_uses_it(self):
        status, device = self.probe(fake_torch(cuda=True))
        self.assertEqual((status["gpu_name"], status["gpu_memory_total_gb"], status["cuda_version"]),
                         ("NVIDIA L4", 24.0, "12.4"))
        self.assertEqual(status["summary"], "GPU: NVIDIA L4")
        self.assertEqual(device, "gpu")
        # An explicit choice wins over "auto"
        _, forced = self.probe(fake_torch(cuda=True), {"CLINLOOP_CT_SEG_DEVICE": "cpu"})
        self.assertEqual(forced, "cpu")

    def test_api_endpoints_and_no_hardcoded_claims(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine.api import app
        client = TestClient(app)
        new, old = client.get("/api/v1/compute/status"), client.get("/api/v1/gpu/telemetry")
        self.assertEqual(new.status_code, 200)
        self.assertEqual(new.json(), old.json())
        keys = client.get("/api/v1/config/api-keys").json()
        self.assertNotIn("on_premise_gpu", keys)                  # was a hard-coded "RTX A4500"
        with open(os.path.join(ROOT, "src", "clinloop_engine", "api.py"), encoding="utf-8") as f:
            self.assertNotIn("A4500", f.read())
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            page = f.read()
        for claim in ("A4500", "Zero Cloud Egress", "Zero cloud egress"):
            self.assertNotIn(claim, page)
        self.assertNotIn("phi_zero_leakage_certified", open(os.path.join(ROOT, "src", "clinloop_engine", "compute.py")).read())


if __name__ == "__main__":
    unittest.main()
