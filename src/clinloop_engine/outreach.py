"""
outreach.py — Patient outreach: draft → clinician approval → send

Rules:
  * Messages never name a diagnosis or result. Lock-screen previews of
    KakaoTalk/SMS are visible to others, so the text only says that a
    follow-up is needed and how to arrange it.
  * Every message is a draft until a clinician approves it (and may edit it).
  * Rules marked patient_outreach=False (e.g. after self-harm, critical
    values) are clinician-handled: no draft can be created.
  * ClinLoop stores no phone numbers. The provider hands the patient ID and
    approved text to the hospital's messaging integration, which resolves
    contact details.
  * Sending a message does not close the loop; only the follow-up does.

Providers (CLINLOOP_OUTREACH_PROVIDER):
  outbox   (default) append to a local JSONL outbox; nothing leaves the
           server until a real integration is configured
  webhook  POST JSON to CLINLOOP_OUTREACH_WEBHOOK_URL (the hospital's
           integration engine / KakaoTalk Alimtalk or SMS gateway adapter)
"""

import json
import os
import uuid
from typing import Dict, Optional

import requests

from .clinical_ontology import get_rule_by_id
from .patient_outreach_agent import OutreachRequest, generate_dynamic_outreach
from .safety.agent_guard import detect_unsupported_clinical_claims, contains_internal_reasoning
from .transport_safety import secure_endpoint, bounded_json

DEFAULT_OUTBOX = os.path.join(os.path.dirname(__file__), "..", "..", "data", "outbox.jsonl")

# Plain-language, diagnosis-free description of the next step
NEXT_STEP = {
    "ko": "담당 의료진이 권고한 후속 진료(검사)",
    "en": "a follow-up visit or test recommended by your care team",
}
TIMEFRAME = {"ko": "가능한 빨리", "en": "as soon as possible"}


class OutreachNotAllowed(ValueError):
    """The loop's rule is clinician-handled, or the text is unsafe."""


def draft_message(loop: Dict, language: str = "ko", scheduling_link: Optional[str] = None) -> Dict:
    """Draft a diagnosis-free message for one loop (local LLM if available, else a safe template)."""
    rule = get_rule_by_id(loop["rule_id"])
    if rule is None or not rule.patient_outreach:
        raise OutreachNotAllowed(
            f"{loop['rule_id']} is clinician-handled: ClinLoop does not draft patient messages for it")
    lang = language if language in NEXT_STEP else "en"
    draft = generate_dynamic_outreach(OutreachRequest(
        patient_id=loop["patient_id"],
        obligation_id=loop["loop_key"],
        message_category="follow_up",
        approved_facts={"finding": NEXT_STEP[lang], "timeframe": TIMEFRAME[lang]},
        preferred_language=lang,
        health_literacy_mode="simple",
        permitted_channel="kakao",
        scheduling_link=scheduling_link,
        urgency_level=loop["severity"].upper(),
        prohibited_topics=["diagnosis", "test_result", "prognosis"],
    ))
    return {"text": draft.message_text, "language": lang, "safety_flags": draft.safety_flags}


def check_text(text: str) -> None:
    if not text or len(text.strip()) < 10:
        raise OutreachNotAllowed("Message text is empty")
    if len(text) > 1000:
        raise OutreachNotAllowed("Message text is too long (max 1000 characters)")
    if contains_internal_reasoning(text):
        raise OutreachNotAllowed("Message contains internal reasoning markers; remove it before review")
    if detect_unsupported_clinical_claims(text):
        raise OutreachNotAllowed("Message contains a definitive clinical claim; remove it before sending")


class OutboxProvider:
    name = "outbox"

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("CLINLOOP_OUTBOX", DEFAULT_OUTBOX)

    def send(self, message: Dict) -> str:
        ref = f"outbox-{uuid.uuid4().hex[:12]}"
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        # New outboxes contain identifiers and need owner-only permissions.
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ref": ref, **message}, ensure_ascii=False) + "\n")
        return ref


class WebhookProvider:
    name = "webhook"

    def __init__(self, url: Optional[str] = None, timeout: float = 10.0):
        self.url = url or os.environ["CLINLOOP_OUTREACH_WEBHOOK_URL"]
        try:
            secure_endpoint(self.url)
        except ValueError:
            raise OutreachNotAllowed("Outreach webhook requires a valid HTTPS endpoint") from None
        self.timeout = timeout

    def send(self, message: Dict) -> str:
        # Patient identity/text must never follow redirects or inherit a proxy.
        with requests.Session() as session:
            session.trust_env = False
            with session.post(self.url, json=message, timeout=self.timeout,
                              allow_redirects=False, stream=True) as resp:
                if resp.status_code not in {200, 201, 202, 204}:
                    raise OutreachNotAllowed(f"Outreach webhook refused delivery: HTTP {resp.status_code}")
                if resp.status_code == 204:
                    return "webhook-204"
                try:
                    body = bounded_json(resp, 16000)
                except (ValueError, UnicodeError):
                    raise OutreachNotAllowed("Outreach webhook returned an invalid acknowledgement") from None
                if not isinstance(body, dict):
                    raise OutreachNotAllowed("Outreach webhook returned an invalid acknowledgement")
                ref = body.get("ref") or body.get("id")
                if ref is not None and (not isinstance(ref, str) or not 1 <= len(ref) <= 200
                                        or any(not (c.isascii() and (c.isalnum() or c in "-_.:")) for c in ref)):
                    raise OutreachNotAllowed("Outreach webhook returned an invalid acknowledgement reference")
                return ref or f"webhook-{resp.status_code}"


def provider_from_env():
    kind = os.environ.get("CLINLOOP_OUTREACH_PROVIDER", "outbox").lower()
    if kind == "webhook":
        return WebhookProvider()
    if kind == "outbox":
        return OutboxProvider()
    raise OutreachNotAllowed("Unknown outreach provider; delivery is disabled")
