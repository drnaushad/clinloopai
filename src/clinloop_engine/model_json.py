"""Unambiguous bounded JSON for model evidence; no salvage of partial answers."""
import json
import math
import re
from typing import Any, Dict


def strict_object(text: str, *, fenced: bool = False) -> Dict[str, Any]:
    """Accept one object; reject duplicate fields, nonfinite values and prose.

    An optional single Markdown JSON fence supports local model responses.
    This validates serialization only, never a model's clinical interpretation.
    """
    if not isinstance(text, str) or len(text.encode("utf-8")) > 512000:
        raise ValueError("Invalid model JSON")
    source = text.strip()
    if fenced and source.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', source, re.S | re.I)
        if not match:
            raise ValueError("Invalid model JSON")
        source = match.group(1)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Invalid model JSON")
            result[key] = value
        return result

    def finite(value):
        raise ValueError("Invalid model JSON")

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("Invalid model JSON")
        return parsed

    try:
        value = json.loads(source, object_pairs_hook=unique, parse_constant=finite, parse_float=number)
    except (ValueError, RecursionError):
        raise ValueError("Invalid model JSON") from None
    if not isinstance(value, dict):
        raise ValueError("Invalid model JSON")
    return value
