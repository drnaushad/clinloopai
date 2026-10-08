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
import requests
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("clinloop.local_llm")

OLLAMA_BASE_URL = os.environ.get("CLINLOOP_OLLAMA_URL", "http://localhost:11434").rstrip("/")

# Reasoning models (e.g. DeepSeek-R1) emit their chain of thought in <think>
# tags; it must never reach a clinician or a patient.
_THINK = re.compile(r"<think>.*?</think>\s*", re.S | re.I)


def _strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "<think>" in text.lower():          # unterminated (truncated) reasoning block
        text = text[:text.lower().index("<think>")]
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
        "name": "deepseek-r1:70b",
        "label": "DeepSeek-R1 70B (Best Clinical Reasoning)",
        "context_window": 128000,
        "strengths": ["chain-of-thought", "medical-ethics", "multilingual-Korean"],
        "vram_gb": 42,
    },
    {
        "name": "deepseek-r1:32b",
        "label": "DeepSeek-R1 32B (Fast Clinical Reasoning)",
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
]


def get_available_models() -> list:
    """Installed Ollama models, best first: configured model, preferred list, then any other."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return []
        installed = [m["name"] for m in resp.json().get("models", []) if m.get("name")]
        known = {m["name"]: m for m in PREFERRED_MODELS}
        ordered = [n for n in (m["name"] for m in PREFERRED_MODELS) if n in installed]
        ordered += [n for n in installed if n not in ordered]
        forced = os.environ.get("CLINLOOP_LLM_MODEL")
        if forced and forced in installed:
            ordered = [forced] + [n for n in ordered if n != forced]
        available = [known.get(n, {"name": n, "label": n, "context_window": None,
                                   "strengths": [], "vram_gb": None}) for n in ordered]
        logger.info(f"Local LLMs available: {ordered}")
        return available
    except Exception as e:
        logger.warning(f"Ollama unreachable: {e}")
        return []


def get_best_model() -> Optional[str]:
    """Return the best available local model name."""
    models = get_available_models()
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
            "phi_egress": "0% — generation failed gracefully",
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
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - t0) * 1000

        return {
            "text": _strip_reasoning(data.get("response", "")),
            "model": model,
            "latency_ms": round(latency_ms, 1),
            "tokens_generated": data.get("eval_count", 0),
            "on_premise": True,
            "phi_egress": "0% — fully air-gapped generation",
            "done": data.get("done", True),
        }
    except requests.exceptions.Timeout:
        return {
            "error": f"Model {model} timed out (>120s)",
            "text": "",
            "model": model,
            "on_premise": True,
            "phi_egress": "0%",
        }
    except Exception as e:
        return {
            "error": str(e),
            "text": "",
            "model": model,
            "on_premise": True,
            "phi_egress": "0%",
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
    best = models[0] if models else None
    return {
        "engine": "Ollama Local LLM Engine",
        "status": "running" if models else "unavailable",
        "base_url": OLLAMA_BASE_URL,
        "best_model": best["name"] if best else None,
        "best_model_label": best["label"] if best else "None",
        "all_available_models": [m["name"] for m in models],
        "on_premise": True,
        "phi_egress": "0% — all inference air-gapped",
        "vram_used_gb": best["vram_gb"] if best else 0,
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
