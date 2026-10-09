"""
build_static_demo.py — A read-only snapshot of the public demo, served as static files

The public website (GitHub Pages, a global CDN) has no ClinLoop server behind it. This script starts
ClinLoop in demo mode (synthetic patients only), asks it everything the read-only pages can show —
worklist, every loop's audit trail and outreach drafts, every patient's graph, quality metrics,
governance, imaging status, rules — and writes each answer to demo/api/<key>.json.

js/demo.js answers the pages' requests from these files when no server is present, so anyone can use
the whole app at clinloopai.app, on any device, in any number, with nothing to overload. Changes
(acknowledge, close, upload) need a real ClinLoop server and say so.

The file name is the FNV-1a hash of the request (decoded path + sorted query), computed the same way
in js/demo.js.

    python scripts/build_static_demo.py            # writes demo/api/
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "demo", "api")


def request_key(path: str, query: Optional[Dict[str, str]] = None) -> str:
    """The same key js/demo.js computes: decoded path, then the query sorted by name."""
    q = "&".join(f"{k}={v}" for k, v in sorted((query or {}).items()) if v not in (None, ""))
    return path + ("?" + q if q else "")


def fnv1a(text: str) -> str:
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def build() -> Dict[str, int]:
    os.environ["CLINLOOP_DEMO"] = "1"
    os.environ["CLINLOOP_API_TOKENS"] = ""
    from fastapi.testclient import TestClient
    from src.clinloop_engine.api import app
    from src.clinloop_engine.demo import DEMO_TOKEN

    headers = {"Authorization": f"Bearer {DEMO_TOKEN}"}
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    written: Dict[str, str] = {}

    with TestClient(app) as client:
        def save(path: str, query: Optional[Dict[str, str]] = None) -> Optional[dict]:
            r = client.get(path + ("?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in query.items())
                                   if query else ""), headers=headers)
            if r.status_code != 200:
                print(f"  skipped {path} {query or ''}: HTTP {r.status_code}", file=sys.stderr)
                return None
            key = request_key(path, {k: str(v) for k, v in (query or {}).items()})
            name = fnv1a(key)
            if name in written and written[name] != key:
                raise SystemExit(f"hash collision: {key} / {written[name]}")
            written[name] = key
            with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(r.json(), f, ensure_ascii=False, separators=(",", ":"))
            return r.json()

        for path in ("/api/v1/me", "/api/v1/rules", "/api/v1/feed/status", "/api/v1/metrics/breakdowns",
                     "/api/v1/metrics/open-loop-rate", "/api/v1/governance/summary", "/api/v1/governance/rules",
                     "/api/v1/governance/critical-findings", "/api/v1/governance/rule-check",
                     "/api/v1/imaging/models", "/api/v1/imaging/scan/status", "/api/v1/reports/second-read/status",
                     "/api/v1/connections/status", "/cds-services"):
            save(path)
        for by in ("rule", "language", "age_group", "sex"):
            save("/api/v1/metrics/open-loop-rate", {"stratify_by": by})
        loops: List[dict] = []
        for inactive in ("false", "true"):
            data = save("/api/v1/worklist", {"include_inactive": inactive}) or {}
            loops += data.get("loops", [])
        keys = sorted({loop["loop_key"] for loop in loops})
        patients = sorted({loop["patient_id"] for loop in loops})
        for key in keys:
            save(f"/api/v1/loops/{key}/audit")
            save(f"/api/v1/loops/{key}/outreach")
        for pid in patients:
            save(f"/api/v1/patients/{pid}/graph")
            save(f"/api/v1/patients/{pid}/documents")

    index = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "patients": patients,
             "loops": len(keys), "files": len(written),
             "note": "Read-only snapshot of the ClinLoop public demo: synthetic patients only."}
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    return {"files": len(written), "patients": len(patients), "loops": len(keys)}


if __name__ == "__main__":
    print(build())
