"""
report_text.py — Small, transparent helpers for reading free-text clinical reports

Negation is handled with two short windows inside the same sentence:
  * before the finding: "no", "negative for", "without", "no evidence of", …
  * after the finding:  "is not identified", "has resolved", "excluded", "없음", …

"No (interval) change in the 7 mm nodule" is not a negation of the nodule.
"""

import re
from typing import Optional

NEGATION_BEFORE = re.compile(
    r"\b(no|negative for|without|free of|absence of|no evidence of|not)\b[^.;]{0,40}$",
    re.IGNORECASE,
)
# Negation after the finding: "pneumothorax has resolved", "carcinoma is not identified", "결절 없음"
NEGATION_AFTER = re.compile(
    r"^[^.;]{0,25}?(\b(?:is|are|was|were)\s+not\s+(?:seen|identified|present|demonstrated|visualized)\b"
    r"|\b(?:has|have)\s+resolved\b|\b(?:excluded|ruled out)\b|없|음성|아님|배제)",
    re.IGNORECASE,
)
# "No change", "no significant interval change": a statement about change, not absence
_NO_CHANGE = re.compile(r"\bno\s+(?:significant\s+|appreciable\s+|interval\s+)*change\b(?:\s+(?:in|of|since))?",
                        re.IGNORECASE)


def not_negated(text: str, start: int) -> bool:
    window = _NO_CHANGE.sub(" ", text[max(0, start - 60):start])
    return not NEGATION_BEFORE.search(window)


def affirmed(text: str, match: re.Match) -> bool:
    return not_negated(text, match.start()) and not NEGATION_AFTER.search(text[match.end():])


def first_affirmed(pattern: re.Pattern, text: str) -> Optional[re.Match]:
    """First affirmed match ("negative for X; Y present" finds Y; "X is not identified" is skipped)."""
    for m in pattern.finditer(text):
        if affirmed(text, m):
            return m
    return None


def span(text: str, match: re.Match, pad: int = 40) -> str:
    return text[max(0, match.start() - pad): match.end() + pad].strip()


def sentence(text: str, start: int, end: int) -> str:
    """The sentence around a match ('1.4 cm' is not a sentence break)."""
    left = max(text.rfind(". ", 0, start), text.rfind(";", 0, start), text.rfind("\n", 0, start))
    rights = [i for i in (text.find(". ", end), text.find(";", end), text.find("\n", end)) if i != -1]
    return text[left + 1: min(rights) if rights else len(text)]


def previous_sentence(text: str, start: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind(";", 0, start), text.rfind("\n", 0, start))
    if left <= 0:
        return ""
    return sentence(text, max(0, left - 1), max(0, left - 1))
