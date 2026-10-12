"""
compute.py — What hardware this ClinLoop server really has, and what uses it

ClinLoop's core (reading records, the 59 rules, deadlines, risk scores, the audit trail) is
deterministic Python and runs on an ordinary CPU: a graphics card (GPU) adds nothing to it.

A GPU only speeds up the optional imaging models on a hospital server:
- CT organ segmentation (TotalSegmentator): about 20 s per scan on a CPU with the 3 mm model and
  minutes with the 1.5 mm model; a few seconds on an NVIDIA GPU.
  CLINLOOP_CT_SEG_DEVICE=auto (default) uses the GPU when one is present.
- The chest X-ray model (TorchXRayVision DenseNet-121, 224 px): well under a second on a CPU, so it
  stays there.
- A vision-language model (MedGemma) runs in its own server (Ollama, vLLM), which manages its GPU.

compute_status() reports only what it measured. Nothing is assumed or filled in: no GPU model name,
memory size or speed appears unless the hardware reported it.
"""

import os
import threading
from typing import Any, Dict, Optional

_lock = threading.Lock()
_cached: Optional[Dict[str, Any]] = None


def _probe() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "torch_installed": False,
        "accelerator": "cpu",            # "cuda" (NVIDIA), "mps" (Apple silicon) or "cpu"
        "gpu_name": None,
        "gpu_memory_total_gb": None,
        "torch_version": None,
        "cuda_version": None,
        "cpu_count": os.cpu_count(),
    }
    try:
        import torch
    except ImportError:
        return status
    status["torch_installed"] = True
    status["torch_version"] = torch.__version__.split("+")[0]
    try:
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            status.update(accelerator="cuda", gpu_name=props.name, cuda_version=torch.version.cuda,
                          gpu_memory_total_gb=round(props.total_memory / 1024 ** 3, 1),
                          gpu_count=torch.cuda.device_count())
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            status.update(accelerator="mps", gpu_name="Apple silicon GPU")
    except Exception as e:                      # a broken driver is reported, never hidden
        status["error"] = f"GPU check failed: {type(e).__name__}"
    return status


def hardware(refresh: bool = False) -> Dict[str, Any]:
    """The probe is cached: importing PyTorch takes seconds and the hardware does not change."""
    global _cached
    with _lock:
        if _cached is None or refresh:
            _cached = _probe()
        return dict(_cached)


def ct_segmentation_device() -> str:
    """TotalSegmentator device: CLINLOOP_CT_SEG_DEVICE, or with "auto" the GPU when there is one."""
    chosen = os.environ.get("CLINLOOP_CT_SEG_DEVICE", "auto").strip().lower() or "auto"
    if chosen != "auto":
        return chosen
    acc = hardware()["accelerator"]
    return "gpu" if acc == "cuda" else "mps" if acc == "mps" else "cpu"


def _installed(module: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def compute_status() -> Dict[str, Any]:
    """Hardware plus, for each part of ClinLoop, where it runs on this server."""
    hw = hardware()
    has_gpu = hw["accelerator"] in ("cuda", "mps")
    ct_installed = _installed("totalsegmentator")
    return {
        **hw,
        "gpu_available": has_gpu,
        "summary": (f"GPU: {hw['gpu_name']}" if has_gpu
                    else "CPU only (PyTorch installed, no GPU found)" if hw["torch_installed"]
                    else "CPU only (no imaging models installed)"),
        "uses": {
            "rules_engine": {"runs_on": "cpu", "note": "Deterministic rules; a GPU is not needed"},
            "chest_xray_model": {"installed": _installed("torchxrayvision"), "runs_on": "cpu",
                                 "note": "Under a second per image on a CPU"},
            "ct_organ_segmentation": {"installed": ct_installed,
                                      "runs_on": ct_segmentation_device() if ct_installed else None,
                                      "note": "About 20 s (3 mm model) to minutes (1.5 mm) per scan on a CPU; seconds on a GPU"},
            "vision_language_model": {"runs_on": "its own server (CLINLOOP_VLM_URL)",
                                      "note": "Ollama or vLLM manages that server's GPU"},
        },
    }
