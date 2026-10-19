"""
profile.py — The deployment profile: the intended-use core, or the full research build

The regulatory file (docs/regulatory/) describes one intended use: tracking follow-up obligations
from information already in the record, with a person deciding (INTENDED_USE.md). Some features of
this code base go beyond it, because they analyse images or rely on model output that the user
cannot fully check (REGULATORY_ASSESSMENT.md §3). They are research features.

CLINLOOP_PROFILE=core locks every one of them off, whatever their own setting says, so the
configuration that was assessed cannot be widened by one environment variable:

  * imaging models: chest X-ray model, vision-language model, plug-in models (imaging_ai.py);
  * CT organ measurement (ct_organs.py) and automatic image scanning from PACS (imaging_scanner.py);
  * research-use imaging-AI findings (ai_review.py) and receiving any imaging-AI product's results;
  * the model-based second reader for reports (second_reader.py);
  * language-model suggestions on clinical notes (note_reader.py);
  * the free-text language-model assistant (differential diagnosis, evidence synthesis, ad-hoc patient
    messages: api.py). Loop-based patient messages (outreach.py) stay: they never name a diagnosis and
    a clinician approves each one;
  * the rules that only those features can open: R047 (imaging-AI finding not in the report),
    R057 (critical imaging-AI finding on an unread study), R058 (second-reader flag).

The one-hour critical-result rules R022 and R035 become a next-day DOCUMENTATION AUDIT in the core
profile (decision of the clinical lead, October 2026; REGULATORY_ASSESSMENT.md §4): the engine still
evaluates them, but their loops leave the worklist, the EHR cards and escalation, and appear instead
on the Quality page once a day has passed since the result, for the quality team to review. The
hospital's critical-result call process stays the primary control; ClinLoop only checks afterwards
that the call was documented.

The default profile is "core": ClinLoop is the clinical edition unless research is chosen on purpose
(CLINLOOP_PROFILE=research). An unknown value is also treated as "core": a typo must not widen the scope.
"""

import os
from datetime import timedelta
from typing import Dict, FrozenSet, List

PROFILES = ("core", "research")

# Rules that only device-like features can open (see the module docstring)
RESEARCH_RULES: FrozenSet[str] = frozenset({"R047", "R057", "R058"})

# Time-critical rules shown as a next-day documentation audit instead of a live alert (core profile)
AUDIT_RULES: FrozenSet[str] = frozenset({"R022", "R035"})
AUDIT_DELAY = timedelta(hours=24)

# Feature → the setting that turns it on in the research profile
RESEARCH_FEATURES: Dict[str, str] = {
    "imaging_models": "CLINLOOP_IMAGING_MODELS / CLINLOOP_IMAGING_MODELS_CONFIG",
    "ct_organs": "CLINLOOP_IMAGING_MODELS=totalseg",
    "image_scan": "CLINLOOP_IMAGE_SCAN",
    "imaging_ai_results": "POST /api/v1/imaging/ai-results",
    "research_imaging_ai": "CLINLOOP_IMAGING_RESEARCH_AI",
    "second_reader": "CLINLOOP_SECOND_READER",
    "note_llm_suggestions": "suggest_with_llm on clinical-note extraction",
    "llm_assistant": "POST /api/v1/local-llm/generate, /agent/evidence-synthesis, /agent/patient-outreach/generate",
}


class OutsideIntendedUse(Exception):
    """Raised when a request needs a feature the core profile locks off."""


def name() -> str:
    value = os.environ.get("CLINLOOP_PROFILE", "core").strip().lower() or "core"
    return value if value in PROFILES else "core"


def core() -> bool:
    return name() == "core"


def allows(feature: str) -> bool:
    """False for a research feature under the core profile; the feature's own setting still applies."""
    if feature not in RESEARCH_FEATURES:
        raise KeyError(feature)
    return not core()


def require(feature: str) -> None:
    if not allows(feature):
        raise OutsideIntendedUse(f"Outside the intended use: {feature.replace('_', ' ')} is off in the core profile "
                                 f"(CLINLOOP_PROFILE=core)")


def excluded_rules() -> FrozenSet[str]:
    return RESEARCH_RULES if core() else frozenset()


def audit_rules() -> FrozenSet[str]:
    """Rules reported as a next-day documentation audit, not as live alerts."""
    return AUDIT_RULES if core() else frozenset()


def describe() -> Dict:
    locked: List[str] = sorted(RESEARCH_FEATURES) if core() else []
    return {"profile": name(), "intended_use": "docs/regulatory/INTENDED_USE.md",
            "locked_features": locked, "excluded_rules": sorted(excluded_rules()),
            "documentation_audit_rules": sorted(audit_rules())}
