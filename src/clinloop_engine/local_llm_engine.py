"""
ClinLoop AI — Local LLM Engine (Ollama Integration)
====================================================
Wraps the best available local model for clinical text generation.
Priority order: deepseek-r1:70b > deepseek-r1:32b > llama3:latest

All prompts are pre-filtered through PHI De-identifier before generation.
All inference stays 100% on-premise — zero cloud egress.
"""

import json
import time
import logging
import requests
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("clinloop.local_llm")

OLLAMA_BASE_URL = "http://localhost:11434"

# ── Model priority: best clinical reasoning first ──
PREFERRED_MODELS = [
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
    """Query Ollama for installed models and return sorted by preference."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return []
        installed = {m["name"] for m in resp.json().get("models", [])}
        available = [m for m in PREFERRED_MODELS if m["name"] in installed]
        logger.info(f"Local LLMs available: {[m['name'] for m in available]}")
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
            "text": data.get("response", "").strip(),
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
