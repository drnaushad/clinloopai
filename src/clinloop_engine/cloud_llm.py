"""
cloud_llm.py — Optional cloud language models (Claude, GPT, Gemini) for research use only

ClinLoop's default is on-premise models (Ollama): no patient text leaves the hospital. This module adds
cloud models as an opt-in research option, with every one of these conditions enforced in code:

  * research profile only: the clinical (core) profile never sends anything to a cloud model
    (profile.RESEARCH_FEATURES["cloud_llm"]);
  * off unless an administrator lists the provider in CLINLOOP_CLOUD_LLM (e.g. "anthropic,openai")
    and sets its API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY);
  * a model must be named for OpenAI and Gemini (CLINLOOP_OPENAI_MODEL, CLINLOOP_GEMINI_MODEL);
    Claude defaults to claude-opus-5-5 (CLINLOOP_ANTHROPIC_MODEL overrides);
  * identifiers are removed before sending (document_reader.scrub_identifiers), and every call is
    logged with provider, model and character counts only, never the text;
  * outputs are labelled as cloud output and pass through the same checks as local ones (the second
    reader's exact-quote check; a clinician approves every message). A cloud model never decides
    follow-up.

Use synthetic or de-identified research data. Sending real patient data to a cloud provider needs the
institution's approval and a data-processing agreement with that provider.

A model is chosen with the prefix "cloud:", e.g. CLINLOOP_SECOND_READER_MODEL=cloud:anthropic, or
model="cloud:openai" on POST /api/v1/local-llm/generate (task "custom").
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("clinloop.cloud_llm")

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "anthropic": {"label": "Anthropic Claude", "key": "ANTHROPIC_API_KEY", "model_setting": "CLINLOOP_ANTHROPIC_MODEL",
                  "default_model": "claude-opus-5-5", "package": "anthropic"},
    "openai": {"label": "OpenAI GPT", "key": "OPENAI_API_KEY", "model_setting": "CLINLOOP_OPENAI_MODEL",
               "default_model": None, "package": "openai"},
    "gemini": {"label": "Google Gemini", "key": "GEMINI_API_KEY", "model_setting": "CLINLOOP_GEMINI_MODEL",
               "default_model": None, "package": "google.genai"},
}
PREFIX = "cloud:"


def is_cloud(model: Optional[str]) -> bool:
    return bool(model) and model.startswith(PREFIX)


def model_for(provider: str) -> Optional[str]:
    p = PROVIDERS[provider]
    return os.environ.get(p["model_setting"]) or p["default_model"]


def _listed() -> List[str]:
    return [x.strip().lower() for x in os.environ.get("CLINLOOP_CLOUD_LLM", "").split(",") if x.strip()]


def status(provider: str) -> str:
    """'available', or why not (no secrets in the answer)."""
    from .profile import allows
    if provider not in PROVIDERS:
        return "unknown provider"
    if not allows("cloud_llm"):
        return "off: the clinical (core) profile uses on-premise models only"
    if provider not in _listed():
        return "off: not enabled in CLINLOOP_CLOUD_LLM"
    if not os.environ.get(PROVIDERS[provider]["key"]):
        return f"off: {PROVIDERS[provider]['key']} is not set"
    if not model_for(provider):
        return f"off: set {PROVIDERS[provider]['model_setting']} to the model to use"
    try:
        __import__(PROVIDERS[provider]["package"])
    except ImportError:
        return f"off: the {PROVIDERS[provider]['package']} package is not installed"
    return "available"


def describe() -> List[Dict[str, Any]]:
    return [{"provider": name, "label": p["label"], "model": model_for(name), "use_as": PREFIX + name,
             "status": status(name), "research_only": True} for name, p in PROVIDERS.items()]


def _anthropic(model: str, prompt: str, system: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic()
    # Server-side fallback on a policy refusal (fallbacks="default" routes by refusal category)
    response = client.beta.messages.create(
        model=model, max_tokens=max(max_tokens, 2000), system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the model declined this request")
    return "".join(b.text for b in response.content if b.type == "text")


def _openai(model: str, prompt: str, system: str, max_tokens: int) -> str:
    import openai
    client = openai.OpenAI()
    response = client.responses.create(model=model, instructions=system, input=prompt)
    return response.output_text or ""


def _gemini(model: str, prompt: str, system: str, max_tokens: int) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client()
    response = client.models.generate_content(model=model, contents=prompt,
                                              config=types.GenerateContentConfig(system_instruction=system))
    return response.text or ""


_CALL = {"anthropic": _anthropic, "openai": _openai, "gemini": _gemini}


def generate(model: str, prompt: str, system: str, max_tokens: int = 600) -> Dict[str, Any]:
    """Generate with a cloud model named "cloud:<provider>". Same result shape as the local engine."""
    from .document_reader import scrub_identifiers
    provider = model[len(PREFIX):] if is_cloud(model) else model
    base = {"text": "", "provider": provider, "on_premise": False, "cloud": True,
            "phi_egress": "de-identified text sent to " + PROVIDERS.get(provider, {}).get("label", provider)}
    state = status(provider)
    if state != "available":
        return dict(base, error=f"Cloud model not available ({state})", model=model)
    name = model_for(provider)
    clean_prompt, clean_system = scrub_identifiers(prompt), scrub_identifiers(system or "")
    t0 = time.perf_counter()
    try:
        text = _CALL[provider](name, clean_prompt, clean_system, max_tokens)
    except Exception as e:      # provider errors never break the caller; details stay in the server log
        logger.warning("Cloud LLM %s/%s failed: %s", provider, name, type(e).__name__)
        return dict(base, error="The cloud model did not answer", model=f"{provider}:{name}")
    ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info("Cloud LLM call: provider=%s model=%s chars_in=%d chars_out=%d ms=%s",
                provider, name, len(clean_prompt), len(text), ms)
    return dict(base, text=text, model=f"{provider}:{name}", latency_ms=ms)
