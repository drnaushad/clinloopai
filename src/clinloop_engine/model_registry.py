"""
model_registry.py — The three model roles, what is configured for each, and what is really installed

One place answers "which model does what, is it there, and what may it be used for":

  role            setting                          default          allowed use
  text            CLINLOOP_LLM_MODEL               exaone3.5:7.8b   drafts of patient messages (Korean/English); a clinician approves each
  second_reader   CLINLOOP_SECOND_READER_MODEL     medgemma:27b     re-reads reports; flags go to a person, never open or close a loop
  vision          CLINLOOP_VLM_MODEL               medgemma:4b      research-only image description; never a diagnosis

Availability comes from the Ollama server itself (/api/tags for the digest, /api/show for the
capabilities it declares), so a role is "available" only when its exact model is installed. There is
no substitute: a missing model is reported as unavailable and its feature does not run
(get_second_reader_model returns None; the image reader reports itself not configured).
No addresses, keys or patient data are returned.
"""
import hashlib
import os
from typing import Any, Dict, List, Optional

import requests

ROLES: List[Dict[str, Any]] = [
    {"role": "text", "setting": "CLINLOOP_LLM_MODEL", "default": "exaone3.5:7.8b", "needs": "completion",
     "allowed_use": "Drafts of patient messages in Korean or English from the loop's own facts; a clinician "
                    "approves every message before it is sent. Never decides follow-up.",
     "timeout_s": 120},
    {"role": "second_reader", "setting": "CLINLOOP_SECOND_READER_MODEL", "default": "medgemma:27b", "needs": "completion",
     "allowed_use": "Re-reads radiology and pathology reports for items the rules did not track. Each item must "
                    "quote the report exactly; it goes to a person (R058, or the quality log in silent mode) and "
                    "never opens, closes or changes a follow-up by itself.",
     "timeout_s": 120},
    {"role": "vision", "setting": "CLINLOOP_VLM_MODEL", "default": "medgemma:4b", "needs": "vision",
     "allowed_use": "Research only: describes an image for comparison with its report. Not a medical device; "
                    "locked off in the core profile.",
     "timeout_s": 120},
]


def configured(role: Dict[str, Any]) -> str:
    return os.environ.get(role["setting"]) or role["default"]


def prompt_version() -> str:
    """Short hash of the second reader's prompt, so an evaluation names the exact prompt it measured."""
    from .second_reader import PROMPT, SYSTEM_PROMPT
    return "sr-" + hashlib.sha256((SYSTEM_PROMPT + "\n" + PROMPT).encode("utf-8")).hexdigest()[:12]


def _installed(base: str) -> Optional[Dict[str, Dict[str, Any]]]:
    try:
        r = requests.get(f"{base}/api/tags", timeout=5)
        r.raise_for_status()
        return {m["name"]: m for m in r.json().get("models", []) if m.get("name")}
    except (requests.RequestException, ValueError):
        return None


def _capabilities(base: str, name: str) -> Optional[List[str]]:
    try:
        r = requests.post(f"{base}/api/show", json={"model": name}, timeout=10)
        r.raise_for_status()
        caps = r.json().get("capabilities")
        return list(caps) if isinstance(caps, list) else None
    except (requests.RequestException, ValueError):
        return None


def registry(base: Optional[str] = None) -> Dict[str, Any]:
    """Each role with its configured model and its real state on the model server."""
    from .local_llm_engine import OLLAMA_BASE_URL
    base = (base or OLLAMA_BASE_URL).rstrip("/")
    installed = _installed(base)
    roles = []
    for role in ROLES:
        name = configured(role)
        entry: Dict[str, Any] = {"role": role["role"], "model": name, "setting": role["setting"],
                                 "default": role["default"], "allowed_use": role["allowed_use"],
                                 "timeout_s": role["timeout_s"], "fallback": "none: the feature does not run",
                                 "backend": "ollama (on-premise)"}
        from .cloud_llm import is_cloud, status as cloud_status
        if is_cloud(name):
            entry.update(status=cloud_status(name[6:]), backend="cloud (research only, de-identified)")
        elif installed is None:
            entry.update(status="model server unreachable")
        elif name not in installed:
            entry.update(status="not installed")
        else:
            m = installed[name]
            d = m.get("details") or {}
            caps = _capabilities(base, name)
            ok = caps is None or role["needs"] in caps
            entry.update(status="available" if ok else f"installed, but the model does not declare '{role['needs']}'",
                         digest=m.get("digest"), size_bytes=m.get("size"), family=d.get("family"),
                         parameter_size=d.get("parameter_size"), quantization=d.get("quantization_level"),
                         capabilities=caps)
        if role["role"] == "second_reader":
            entry["prompt_version"] = prompt_version()
            entry["inference"] = {"temperature": 0.0, "max_tokens": 600}
        roles.append(entry)
    from .cloud_llm import describe
    return {"roles": roles, "all_available": all(r["status"] == "available" for r in roles),
            "cloud_options": describe()}
