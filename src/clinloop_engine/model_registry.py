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
import re
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
    from .second_reader import prompt_digest
    return "sr-" + prompt_digest()[:12]


def _installed(base: str) -> Optional[Dict[str, Dict[str, Any]]]:
    try:
        from .local_llm_engine import _ollama_json
        data = _ollama_json("GET", "/api/tags", timeout=5, base=base)
        if not isinstance(data.get("models"), list):
            return None
        rows = [m for m in data["models"] if isinstance(m, dict) and isinstance(m.get("name"), str)]
        names = [m["name"] for m in rows]
        return {m["name"]: m for m in rows if names.count(m["name"]) == 1}
    except (requests.RequestException, ValueError, OSError):
        return None


def _capabilities(base: str, name: str) -> Optional[List[str]]:
    try:
        from .local_llm_engine import _ollama_json, _local_model
        data = _ollama_json("POST", "/api/show", {"model": name}, timeout=10, base=base)
        if not _local_model({"name": name, **data}):
            return None
        caps = data.get("capabilities")
        return list(caps) if isinstance(caps, list) and all(isinstance(c, str) for c in caps) else None
    except (requests.RequestException, ValueError, OSError):
        return None


def checkpoint_identity(name: str, base: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Fresh local checkpoint identity for cache provenance, never a model fallback.

    Missing, duplicate, malformed or cloud-backed inventory is unavailable.
    The Ollama manifest digest identifies its weights/template/parameters; it
    does not prove a server is truthful or establish clinical performance.
    """
    from .local_llm_engine import OLLAMA_BASE_URL, _local_model, _ollama_json
    try:
        endpoint = base or OLLAMA_BASE_URL
        data = _ollama_json("GET", "/api/tags", timeout=5, base=endpoint)
        rows = data.get("models")
        if not isinstance(rows, list):
            return None
        matches = [row for row in rows if isinstance(row, dict) and row.get("name") == name]
        if len(matches) != 1 or not _local_model(matches[0]):
            return None
        digest = matches[0].get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"(?:sha256:)?[a-fA-F0-9]{64}", digest):
            return None
        caps = _capabilities(endpoint, name)
        if caps is None or "completion" not in caps:
            return None
        return {"model": name, "digest": digest.removeprefix("sha256:").lower()}
    except (requests.RequestException, ValueError, OSError, TypeError):
        return None


def registry(base: Optional[str] = None) -> Dict[str, Any]:
    """Each role with its configured model and its real state on the model server."""
    from .local_llm_engine import OLLAMA_BASE_URL, _local_model
    base = (base or OLLAMA_BASE_URL).rstrip("/")
    installed = _installed(base)
    roles = []
    for role in ROLES:
        name = configured(role)
        entry: Dict[str, Any] = {"role": role["role"], "model": name, "setting": role["setting"],
                                 "default": role["default"], "allowed_use": role["allowed_use"],
                                 "timeout_s": role["timeout_s"], "fallback": "none: the feature does not run",
                                 "backend": "ollama (on-premise)"}
        if installed is None:
            entry.update(status="model server unreachable")
        elif name not in installed:
            entry.update(status="not installed")
        elif not _local_model({"name": name, **installed[name]}):
            entry.update(status="remote or cloud alias refused")
        else:
            m = installed[name]
            d = m.get("details") or {}
            caps = _capabilities(base, name)
            ok = caps is not None and role["needs"] in caps
            entry.update(status="available" if ok else "capability check unavailable" if caps is None else f"installed, but the model does not declare '{role['needs']}'",
                         digest=m.get("digest"), size_bytes=m.get("size"), family=d.get("family"),
                         parameter_size=d.get("parameter_size"), quantization=d.get("quantization_level"),
                         capabilities=caps)
        if role["role"] == "second_reader":
            from .second_reader import reader_contract
            entry["prompt_version"] = prompt_version()
            entry["verification_version"] = reader_contract()
            entry["inference"] = {"temperature": 0.0, "max_tokens": 600}
        roles.append(entry)
    return {"roles": roles, "all_available": all(r["status"] == "available" for r in roles)}
