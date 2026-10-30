"""
ClinLoop AI — Local LLM Engine (Ollama Integration)
====================================================
Talks to an Ollama server inside the hospital network. Inference stays on
premise; nothing is sent to a cloud model.

Configuration (environment):
  CLINLOOP_OLLAMA_URL   Ollama address (default http://localhost:11434;
                        http://ollama:11434 in docker-compose)
  CLINLOOP_LLM_MODEL    force a specific installed model (e.g. exaone3.5:7.8b)

Model choice: an explicitly configured model, else the first installed model
from PREFERRED_MODELS (Korean-capable instruction models first, since the
main use is short patient messages), else any installed model.

Callers are responsible for what they put in a prompt: patient outreach
sends only diagnosis-free, approved facts (see outreach.py).
"""

import json
import os
import re
import time
import logging
import ipaddress
import socket
from urllib.parse import urlsplit
import requests
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("clinloop.local_llm")

OLLAMA_BASE_URL = os.environ.get("CLINLOOP_OLLAMA_URL", "http://localhost:11434").rstrip("/")

def _private_base(value: str) -> str:
    """Require a private-network endpoint without credentials or URL-carried data."""
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("Invalid local model endpoint")
    addresses = {item[4][0].split("%")[0] for item in socket.getaddrinfo(url.hostname, url.port)}
    if not addresses or not all((ip := ipaddress.ip_address(a)).is_private and not (
            ip.is_link_local or ip.is_unspecified or ip.is_multicast) for a in addresses):
        raise ValueError("Local model endpoint required")
    return value.rstrip("/")


def _ollama_json(method: str, path: str, payload=None, timeout=10, base=None) -> Dict[str, Any]:
    """Bounded local transport. Never inherit proxies, follow redirects or log bodies."""
    endpoint = _private_base(base or OLLAMA_BASE_URL)
    with requests.Session() as session:
        session.trust_env = False
        with session.request(method, endpoint + path, json=payload, timeout=timeout,
                             allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ValueError("Local model request failed")
            raw = bytearray()
            for chunk in response.iter_content(8192):
                raw.extend(chunk)
                if len(raw) > 512000:
                    raise ValueError("Local response too large")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("error"):
        raise ValueError("Invalid local response")
    return value


def _local_model(value: Dict[str, Any]) -> bool:
    name = value.get("name")
    details = value.get("details") or {}
    return (isinstance(name, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", name))
            and "cloud" not in name.lower() and not value.get("remote_host") and not value.get("remote_model")
            and isinstance(details, dict) and not details.get("remote_host") and not details.get("remote_model"))


# Reasoning models (e.g. DeepSeek-R1) emit their chain of thought in <think>
# tags; it must never reach a clinician or a patient.
_THINK = re.compile(r"<\s*think\b[^>]*>.*?</\s*think\s*>\s*", re.S | re.I)


def _strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text or "")
    opening = re.search(r"<\s*think\b", text, re.I)
    if opening:                         # truncated/unterminated reasoning block
        text = text[:opening.start()]
    if re.search(r"</\s*think\s*>", text, re.I):
        return ""                       # orphan/nested block: no safe boundary
    return text.strip()


# ── Model priority: Korean-capable instruction models first ──
PREFERRED_MODELS = [
    {
        "name": "exaone3.5:32b",
        "label": "EXAONE 3.5 32B (Korean/English)",
        "context_window": 32768,
        "strengths": ["Korean", "instruction-following"],
        "vram_gb": 20,
    },
    {
        "name": "exaone3.5:7.8b",
        "label": "EXAONE 3.5 7.8B (Korean/English)",
        "context_window": 32768,
        "strengths": ["Korean", "instruction-following"],
        "vram_gb": 5,
    },
    {
        "name": "qwen2.5:7b",
        "label": "Qwen 2.5 7B (multilingual)",
        "context_window": 32768,
        "strengths": ["multilingual", "instruction-following"],
        "vram_gb": 5,
    },
    {
        # Google MedGemma 27B: assigned report-text role; inspect the installed checkpoint for capabilities.
        # Research model (Health AI Developer Foundations terms), not a medical device.
        # Preference order is configuration, not measured clinical or language accuracy.
        "name": "medgemma:27b",
        "label": "MedGemma 27B (medical research; verify installed capabilities)",
        "context_window": 128000,
        "strengths": ["English-medical-text", "report-reading"],
        "vram_gb": 20,
        "role": "report reader",
    },
    {
        "name": "deepseek-r1:70b",
        "label": "DeepSeek-R1 70B (general reasoning; unvalidated for clinical use)",
        "context_window": 128000,
        "strengths": ["chain-of-thought", "medical-ethics", "multilingual-Korean"],
        "vram_gb": 42,
    },
    {
        "name": "deepseek-r1:32b",
        "label": "DeepSeek-R1 32B (general reasoning; unvalidated for clinical use)",
        "context_window": 128000,
        "strengths": ["chain-of-thought", "differential-diagnosis", "Korean"],
        "vram_gb": 19,
    },
    {
        "name": "medllama2:latest",
        "label": "MedLlama2 7B (Clinical Tuned)",
        "context_window": 4096,
        "strengths": ["clinical-jargon", "differential-diagnosis"],
        "vram_gb": 4,
    },
    {
        "name": "llama3.1:latest",
        "label": "Llama 3.1 8B (General Clinical Assistant)",
        "context_window": 128000,
        "strengths": ["general-medicine", "patient-communication"],
        "vram_gb": 5,
    },
    {
        "name": "llama3:latest",
        "label": "Llama 3 8B",
        "context_window": 8192,
        "strengths": ["general-medicine", "patient-communication"],
        "vram_gb": 5,
    },
    {
        # Google MedGemma 4B (image + text, ~3.3 GB): the imaging vision-language model
        # (CLINLOOP_VLM_MODEL). Listed last so it is never picked for text generation
        # ahead of a text model.
        "name": "medgemma:4b",
        "label": "MedGemma 4B (vision-language, imaging)",
        "context_window": 128000,
        "strengths": ["image+text", "radiology-draft"],
        "vram_gb": 8,
        "role": "vision",
    },
]

# The report second reader reads English radiology/pathology reports.
SECOND_READER_DEFAULT = "medgemma:27b"


def get_available_models() -> list:
    """Installed Ollama models, best first: configured model, preferred list, then any other."""
    try:
        tags = _ollama_json("GET", "/api/tags", timeout=5)
        installed = [m["name"] for m in tags.get("models", []) if isinstance(m, dict) and _local_model(m)]
        known = {m["name"]: m for m in PREFERRED_MODELS}
        ordered = [n for n in (m["name"] for m in PREFERRED_MODELS) if n in installed]
        ordered += [n for n in installed if n not in ordered]
        forced = os.environ.get("CLINLOOP_LLM_MODEL")
        if forced and forced in installed:
            ordered = [forced] + [n for n in ordered if n != forced]
        available = [known.get(n, {"name": n, "label": n, "context_window": None,
                                   "strengths": [], "vram_gb": None}) for n in ordered]
        logger.info("Local model inventory: %d eligible models", len(ordered))
        return available
    except Exception as e:
        logger.warning("Local model inventory unavailable (%s)", type(e).__name__)
        return []


def get_second_reader_model() -> Optional[str]:
    """Model for the report second reader: CLINLOOP_SECOND_READER_MODEL (default MedGemma 27B), only
    when installed. No substitute: a reader evaluated as MedGemma must not quietly become another
    model, so without it the second reader does not run (model_registry reports it unavailable)."""
    want = os.environ.get("CLINLOOP_SECOND_READER_MODEL") or SECOND_READER_DEFAULT
    names = [m["name"] for m in get_available_models()]
    return want if want in names else None


def get_best_model() -> Optional[str]:
    """Return the best available local model name."""
    models = get_available_models()
    forced = os.environ.get("CLINLOOP_LLM_MODEL")
    if forced:
        return forced if any(m["name"] == forced for m in models) else None
    return models[0]["name"] if models else None


def generate_clinical_text(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.25,
    max_tokens: int = 400,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run inference on the local Ollama LLM.
    Returns: {text, model, latency_ms, tokens_generated, on_premise, phi_egress}
    """
    if model is None:
        model = get_best_model()
    if model is None:
        return {
            "error": "No local LLM available",
            "text": "",
            "on_premise": True,
            "phi_egress": "not measured; no generation performed",
        }

    sys = system_prompt or (
        "You are ClinLoop AI, an on-premise clinical safety assistant at a Korean hospital. "
        "You receive de-identified clinical context only (no patient names or IDs). "
        "You write empathetic, plain-language, non-alarming patient communications in Korean and English. "
        "You follow Hippocratic non-maleficence: never alarm unnecessarily, always reassure and guide."
    )

    payload = {
        "model": model,
        "system": sys,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }

    t0 = time.perf_counter()
    try:
        if not _local_model({"name": model}) or not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 20000:
            raise ValueError("Invalid local generation input")
        details = _ollama_json("POST", "/api/show", {"model": model}, timeout=10)
        if (details.get("name", model) != model or not _local_model({**details, "name": model})
                or not isinstance(details.get("model_info"), dict)
                or not details["model_info"] or not isinstance(details.get("capabilities"), list)
                or "completion" not in details["capabilities"]):
            raise ValueError("Model locality or capability not verified")
        lengths = [v for k, v in details["model_info"].items()
                   if k.endswith(".context_length") and type(v) is int and v > 0]
        if not lengths or type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ValueError("Model context capacity or output budget not verified")
        context_window = min(16384, *lengths)
        if len((prompt + sys).encode("utf-8")) + max_tokens + 512 > context_window:
            raise ValueError("Complete model input does not fit the verified context")
        payload["options"]["num_ctx"] = context_window
        data = _ollama_json("POST", "/api/generate", payload, timeout=120)
        if (data.get("model") != model or data.get("done") is not True or data.get("done_reason") != "stop"
                or not isinstance(data.get("response"), str) or len(data["response"]) > 30000
                or data["response"].lower().count("<think>") != data["response"].lower().count("</think>")):
            raise ValueError("Incomplete or unexpected local output")
        answer = _strip_reasoning(data["response"])
        if not answer:
            raise ValueError("Empty local output")
        latency_ms = (time.perf_counter() - t0) * 1000

        return {
            "text": answer,
            "model": model,
            "latency_ms": round(latency_ms, 1),
            "tokens_generated": data.get("eval_count", 0),
            "on_premise": True,
            "phi_egress": "not measured; local destination and model metadata checked",
            "done": True,
            "done_reason": "stop",
        }
    except requests.exceptions.Timeout:
        return {
            "error": f"Model {model} timed out (>120s)",
            "text": "",
            "model": model,
            "on_premise": True,
            "phi_egress": "not measured",
        }
    except Exception as e:
        return {
            "error": "Local model request failed or could not be verified.",
            "text": "",
            "model": model,
            "on_premise": True,
            "phi_egress": "not measured",
        }


# ── Clinical Task Presets ──────────────────────────────────────────────────

CLINICAL_PROMPTS = {
    "kakao_message_ko": (
        "Write a 2-3 sentence Korean KakaoTalk message for a patient who has an incidental "
        "finding requiring follow-up. Tone: warm, reassuring, non-alarming. "
        "No jargon. No patient name. Mention the follow-up is protective and important.\n"
        "De-identified clinical context: {context}"
    ),
    "kakao_message_en": (
        "Write a 2-3 sentence plain-English mobile notification for a patient who has an "
        "incidental finding requiring follow-up. Tone: warm, reassuring, non-alarming. "
        "De-identified clinical context: {context}"
    ),
    "discharge_summary_ko": (
        "Write a patient-friendly Korean discharge summary (3-4 sentences). "
        "Explain what was found, what the patient should do, and why it matters. "
        "De-identified clinical context: {context}"
    ),
    "differential_diagnosis": (
        "As a clinical AI, provide a concise differential diagnosis (top 3 conditions) "
        "with brief reasoning for each. Use clinical but clear language. "
        "De-identified case: {context}"
    ),
    "ethics_review": (
        "As a clinical ethics AI aligned with Hippocratic principles, briefly assess "
        "the ethical considerations of the following clinical scenario. "
        "Focus on non-maleficence, patient autonomy, and beneficence. "
        "De-identified context: {context}"
    ),
}


def generate_kakao_message(de_identified_context: str, lang: str = "ko") -> Dict[str, Any]:
    """Generate a KakaoTalk patient outreach message using the best local LLM."""
    task = "kakao_message_ko" if lang == "ko" else "kakao_message_en"
    prompt = CLINICAL_PROMPTS[task].format(context=de_identified_context)
    return generate_clinical_text(prompt, temperature=0.3, max_tokens=200)


def generate_differential_diagnosis(de_identified_context: str) -> Dict[str, Any]:
    """Generate a differential diagnosis using the best local LLM (DeepSeek-R1 chain-of-thought)."""
    prompt = CLINICAL_PROMPTS["differential_diagnosis"].format(context=de_identified_context)
    return generate_clinical_text(prompt, temperature=0.1, max_tokens=350)


def generate_ethics_review(de_identified_context: str) -> Dict[str, Any]:
    """Run a Hippocratic ethics alignment check using the best local LLM."""
    prompt = CLINICAL_PROMPTS["ethics_review"].format(context=de_identified_context)
    return generate_clinical_text(prompt, temperature=0.2, max_tokens=300)


def get_engine_status() -> Dict[str, Any]:
    """Return the status of the local LLM engine for the API telemetry endpoint."""
    models = get_available_models()
    forced = os.environ.get("CLINLOOP_LLM_MODEL")
    best = next((m for m in models if m["name"] == forced), None) if forced else (models[0] if models else None)
    return {
        "engine": "Ollama Local LLM Engine",
        "status": "running" if best else "unavailable",
        "base_url": "configured private-network endpoint",
        "best_model": best["name"] if best else None,
        "best_model_label": best["label"] if best else "None",
        "all_available_models": [m["name"] for m in models],
        "on_premise": True,
        "phi_egress": "not measured; local-only transport required",
        "vram_used_gb": None,
        "estimated_model_vram_gb": best["vram_gb"] if best else None,
    }


if __name__ == "__main__":
    print("=== ClinLoop AI Local LLM Engine Status ===")
    status = get_engine_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))

    if status["best_model"]:
        print(f"\n=== Testing {status['best_model']} on clinical task ===")
        result = generate_kakao_message(
            "Patient: 40대 남성. CT finding: 14mm ground-glass nodule (GGN) in right lower lobe. "
            "Risk: 42.1% malignant progression per Fleischner 2017. Follow-up PET-CT required within 24 days.",
            lang="ko"
        )
        print(f"Latency: {result.get('latency_ms', 'N/A')}ms")
        print(f"Tokens: {result.get('tokens_generated', 'N/A')}")
        print(f"On-premise: {result.get('on_premise', True)}")
        print(f"\nGenerated Message:\n{result.get('text', 'Error: ' + result.get('error',''))}")
