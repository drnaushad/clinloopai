"""
build_sbom.py — Software bill of materials (CycloneDX 1.5 JSON) from requirements.lock

The SBOM lists every third-party Python package the Docker image installs, with its exact version
and package URL, for the regulatory file (docs/regulatory/SOFTWARE_LIFECYCLE.md, SOUP list) and for
the hospital's vulnerability scanning (docs/regulatory/CYBERSECURITY.md). It is generated, not
edited: tests/test_regulatory.py fails when it no longer matches the lock file.

    python scripts/build_sbom.py            # writes docs/regulatory/sbom.cdx.json
    python scripts/build_sbom.py --check    # exit 1 if the file is out of date

The output has no timestamp, so the same lock file always gives the same bytes.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCK = os.path.join(ROOT, "requirements.lock")
OUT = os.path.join(ROOT, "docs", "regulatory", "sbom.cdx.json")
_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)\s*(?:;\s*(.+))?$")


def locked_packages(path: str = LOCK) -> List[Dict[str, str]]:
    """name, version and environment marker of every pinned line, sorted by name."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _LINE.match(line.strip())
            if m:
                out.append({"name": m.group(1).lower(), "version": m.group(2), "marker": (m.group(3) or "").strip()})
    return sorted(out, key=lambda p: (p["name"], p["marker"]))


def build(path: str = LOCK) -> Dict:
    with open(path, "rb") as f:
        lock_sha = hashlib.sha256(f.read()).hexdigest()
    components = []
    for p in locked_packages(path):
        c = {"type": "library", "bom-ref": f"pkg:pypi/{p['name']}@{p['version']}", "name": p["name"],
             "version": p["version"], "purl": f"pkg:pypi/{p['name']}@{p['version']}"}
        if p["marker"]:
            c["properties"] = [{"name": "python:environment-marker", "value": p["marker"]}]
        components.append(c)
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {
            "component": {"type": "application", "bom-ref": "clinloop", "name": "ClinLoop",
                          "description": "Clinical follow-up tracking (see docs/regulatory/INTENDED_USE.md)"},
            "properties": [{"name": "source", "value": "requirements.lock"},
                           {"name": "source:sha256", "value": lock_sha},
                           {"name": "runtime", "value": "python:3.12-slim (Dockerfile)"}],
        },
        "components": components,
        "dependencies": [{"ref": "clinloop", "dependsOn": [c["bom-ref"] for c in components]}],
    }


def render(path: str = LOCK) -> str:
    return json.dumps(build(path), indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--check", action="store_true", help="exit 1 if the SBOM is out of date")
    args = ap.parse_args()
    text = render()
    if args.check:
        try:
            with open(OUT, encoding="utf-8") as f:
                current = f.read()
        except OSError:
            current = ""
        if current != text:
            print("docs/regulatory/sbom.cdx.json is out of date: run python scripts/build_sbom.py", file=sys.stderr)
            return 1
        print("SBOM up to date")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {os.path.relpath(OUT, ROOT)} ({len(build()['components'])} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
