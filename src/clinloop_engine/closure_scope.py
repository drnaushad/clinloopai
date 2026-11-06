"""Conservative tissue-follow-up identity checks; clinical-review draft.

These checks can refuse closure. They do not establish diagnosis, prove that a
procedure addressed every lesion, or infer an unrecorded source relationship.
"""
from __future__ import annotations

import re
from typing import Callable, Dict

_SIDE_CODES = {"7771000": "left", "24028007": "right", "51440002": "bilateral"}
_SIDE = {
    "left": re.compile(r"\bleft\s+(?:\w+\s+){0,2}(?:breast|lung|kidney|adrenal|thyroid|lobe|nodule|mass|lesion)\b|\b(?:breast|lung|kidney|lesion)\s*[,:(-]?\s*left\b|좌측|왼쪽|좌[상하]엽", re.I),
    "right": re.compile(r"\bright\s+(?:\w+\s+){0,2}(?:breast|lung|kidney|adrenal|thyroid|lobe|nodule|mass|lesion)\b|\b(?:breast|lung|kidney|lesion)\s*[,:(-]?\s*right\b|우측|오른쪽|우[상중하]엽", re.I),
    "bilateral": re.compile(r"\bbilateral\b|\bboth\s+(?:breasts|lungs|kidneys)\b|양측", re.I),
}


def _objects(value) -> list:
    """FHIR permits single concepts/references and repeated ones by resource."""
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _concept(concept) -> str:
    if not isinstance(concept, dict):
        return ""
    return " ".join([str(concept.get("text") or "")] +
                    [str(c.get("display") or "") for c in _objects(concept.get("coding"))])


def resource_scope(resource: Dict, normalize: Callable[[str], str]) -> Dict:
    """Keep explicit FHIR scope and bounded side wording, without creating IDs.

    Multiple/contradictory side mentions remain ambiguous. No attempt is made to
    decide which finding a side belongs to in a multi-finding narrative.
    """
    sites = _objects(resource.get("bodySite"))
    text = " ".join([_concept(resource.get("code")), str(resource.get("conclusion") or "")] +
                    [_concept(c) for c in sites])
    sides = {side for side, pattern in _SIDE.items() if pattern.search(text)}
    for site in sites:
        for coding in _objects(site.get("coding")):
            if isinstance(coding, dict) and coding.get("system") == "http://snomed.info/sct":
                code = coding.get("code")
                side = _SIDE_CODES.get(code) if isinstance(code, str) else None
                if side:
                    sides.add(side)
    scope = {}
    if sides:
        scope["laterality"] = sorted(sides)
    for source, target, prefix in [("focus", "lesion_refs", "BodyStructure/"),
                                   ("specimen", "specimen_refs", "Specimen/")]:
        refs = _objects(resource.get(source))
        values = {normalize(ref.get("reference")) for ref in refs
                  if isinstance(ref, dict) and isinstance(ref.get("reference"), str)}
        values = {ref for ref in values if isinstance(ref, str) and ref.startswith(prefix)}
        if values:
            scope[target] = sorted(values)
    return scope


def tissue_scope_matches(trigger: Dict, followup: Dict, rule_id: str) -> bool:
    """Refuse wrong/unknown/ambiguous tissue scope; never guess a missing side.

    Explicit lesion/specimen requirements must all be covered. A generic breast
    biopsy is insufficient to close a BI-RADS obligation with unresolved side.
    Bilateral tissue evidence cannot prove which target was actually sampled.
    """
    expected = trigger.get("closure_scope") or {}
    actual = followup.get("closure_scope") or {}
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    linked = False
    for field in ("lesion_refs", "specimen_refs"):
        want, got = expected.get(field), actual.get(field)
        if want:
            if (not isinstance(want, list) or not isinstance(got, list) or
                    any(not isinstance(v, str) or not v for v in want + got) or
                    not set(want).issubset(got)):
                return False
            linked = True
    want = expected.get("laterality")
    got = actual.get("laterality")
    if want:
        if (not isinstance(want, list) or len(want) != 1 or want[0] not in {"left", "right"} or
                not isinstance(got, list) or got != want):
            return False
    elif rule_id == "R018" and not linked:
        return False
    return True
