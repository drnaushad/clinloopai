"""
report_text.py — Small, transparent helpers for reading free-text clinical reports

Negation is read within one sentence:
  * before the finding: "no", "negative for", "without", "no evidence of", …
    A negation carries across a list joined by "or"/"nor" ("no haemorrhage,
    mass effect, or acute infarct") but stops at a comma that starts a new
    statement ("no consolidation, large right pneumothorax").
  * after the finding: "is not identified", "is no longer seen", "has
    resolved", "excluded", "없음", "보이지 않음", …

"No (interval) change / growth in the 7 mm nodule" is not a negation of the nodule.
"""

import re
from typing import Optional

NEGATION_TRIGGER = re.compile(
    r"\b(no|negative for|without|free of|absence of|no evidence of|not)\b",
    re.IGNORECASE,
)
# Negation after the finding: "pneumothorax has resolved", "carcinoma is not identified", "결절 없음"
NEGATION_AFTER = re.compile(
    r"^[^.;]{0,25}?(\b(?:is|are|was|were)\s+(?:not|no\s+longer)\s+(?:seen|identified|present|demonstrated|"
    r"visualized|evident|appreciated)\b|\bno\s+longer\b|\b(?:has|have)\s+resolved\b|\b(?:excluded|ruled out)\b)"
    # Korean negation closes its own clause: "낭성 병변, 주췌관 확장이나 고형 성분 없음" negates the solid part only
    r"|^[^.;,]{0,25}?(?:없|음성|아님|배제|않|안\s*(?:함|됨|보임))",
    re.IGNORECASE,
)
# "No change", "no significant interval change": a statement about change, not absence
_NO_CHANGE = re.compile(r"\bno\s+(?:significant\s+|appreciable\s+|interval\s+)*(?:change|growth|increase|enlargement)\b"
                        r"(?:\s+(?:in|of|since))?", re.IGNORECASE)
_SENTENCE_START = re.compile(r"(?:\.\s|;|\n)")


def not_negated(text: str, start: int) -> bool:
    """True unless a negation earlier in the same sentence applies to the text at ``start``."""
    begin = max((m.end() for m in _SENTENCE_START.finditer(text, 0, start)), default=0)
    window = _NO_CHANGE.sub(lambda m: " " * len(m.group(0)), text[begin:start])
    triggers = list(NEGATION_TRIGGER.finditer(window))
    if not triggers:
        return True
    gap = window[triggers[-1].end():]
    if "," not in gap:
        return len(gap) > 60          # too far away to apply
    last_item = gap.rsplit(",", 1)[1]
    in_list = re.search(r"\b(?:or|nor)\b", last_item) or re.match(r"\s*and\b", last_item)
    return not in_list


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
