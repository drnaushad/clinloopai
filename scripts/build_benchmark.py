"""
Build ClinLoop-Bench (benchmark/data/v<VERSION>/) from the repository's synthetic evaluation sets.

Read-only use of the sources: nothing under tests/ or src/ is written. The output is deterministic
(sorted keys, fixed record order, split chosen by a seeded hash), so re-running the script on unchanged
sources reproduces the files byte for byte. Re-run it after every new evaluation round:

    python scripts/build_benchmark.py              # writes benchmark/data/v1.0/
    python scripts/build_benchmark.py --out DIR    # writes elsewhere (used by the tests)

Sources (all synthetic, written for ClinLoop's blind evaluations):
  tests/report_eval/cases.json       report text + expected rules         -> T1 (English) / T3 (Korean, mixed)
  tests/report_eval/timelines.json   patient timelines + expected status  -> T2
  tests/blind_reports_2/cases.json   FHIR records + expected obligations  -> T2
  tests/blind_reports_3/cases.json   FHIR records (Korean/English mixed)  -> T2
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "report_eval"))

import run_eval  # noqa: E402  (FHIR construction used by the blind report evaluation)
import run_timelines  # noqa: E402

VERSION = "1.0"
RANDOM_STATE = 42
DEV_PERCENT = 30          # ~30% dev, ~70% held-out test
SOURCES = {
    "report_eval": "tests/report_eval/cases.json",
    "timelines": "tests/report_eval/timelines.json",
    "blind_reports_2": "tests/blind_reports_2/cases.json",
    "blind_reports_3": "tests/blind_reports_3/cases.json",
}
BLIND_RULES = ["R060", "R061", "R062", "R063", "R064", "R065"]
HANGUL = re.compile(r"[가-힣]")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
# Timeline gold status -> (loop status, overdue)
TIMELINE_STATUS = {"done": ("closed", False), "done_late": ("closed", True),
                   "pending": ("open", False), "missed": ("open", True)}
# Identifying fields a FHIR resource could carry; the sources are synthetic, but the benchmark ships none.
STRIP_FIELDS = ("name", "identifier", "telecom", "address", "photo", "contact")


def split_for(record_id: str) -> str:
    """Deterministic dev/test split: seeded SHA-256 of the record id (random_state=42)."""
    h = int(hashlib.sha256(f"{RANDOM_STATE}:{record_id}".encode("utf-8")).hexdigest(), 16)
    return "dev" if h % 100 < DEV_PERCENT else "test"


def language_of(text: str) -> str:
    """en / ko / mixed. 'mixed' = Hangul text that also carries >=25% Latin words (Konglish reports)."""
    hangul = len(HANGUL.findall(text))
    if not hangul:
        return "en"
    latin = sum(len(w) for w in LATIN_WORD.findall(text))
    return "mixed" if latin / max(1, latin + hangul) >= 0.25 else "ko"


def strip_identifiers(resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in resources:
        r = json.loads(json.dumps(r))
        for f in STRIP_FIELDS:
            r.pop(f, None)
        out.append(r)
    return out


def bundle(resources: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"resourceType": "Bundle", "type": "collection",
            "entry": [{"resource": r} for r in strip_identifiers(resources)]}


def _sha(path: str) -> str:
    with open(os.path.join(ROOT, path), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _load(path: str):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def report_records() -> List[Dict[str, Any]]:
    out = []
    for c in _load(SOURCES["report_eval"]):
        rid = f"report_eval:{c['id']}"
        lang = language_of(c["text"]) if c.get("language") != "en" or HANGUL.search(c["text"]) else "en"
        _, date, res = run_eval.resources(c)
        out.append({
            "id": rid, "version": VERSION, "task": "T1" if lang == "en" else "T3", "language": lang,
            "split": split_for(rid), "synthetic": True,
            "source": {"file": SOURCES["report_eval"], "round": c["set"], "original_id": c["id"]},
            "input": {"text": c["text"], "title": c.get("title") or "", "report_type": c.get("report_type"),
                      "report_date": c["date"][:10], "patient": c.get("patient") or {},
                      "fhir_bundle": bundle(res)},
            "eval_time": (date + timedelta(days=1)).date().isoformat() + "T09:00:00Z",
            "gold": {"rules": sorted(set(c.get("expected_rules") or []) & run_eval.REPORT_RULES),
                     "window_days": c.get("expected_window_days"),
                     "scope_rules": sorted(run_eval.REPORT_RULES),
                     "evidence_spans": None, "obligations": None},
            "rationale": c.get("rationale") or "", "tags": sorted(c.get("tags") or []),
        })
    return out


def timeline_records() -> List[Dict[str, Any]]:
    out = []
    for c in _load(SOURCES["timelines"]):
        rid = f"timelines:{c['id']}"
        _, first_report, res = run_timelines.resources(c)
        text = " ".join(e.get("text") or "" for e in c["events"])
        obligations = {}
        for rule, st in sorted((c.get("expected") or {}).items()):
            if rule in run_timelines.REPORT_RULES:
                status, overdue = TIMELINE_STATUS[st]
                obligations[rule] = {"status": status, "overdue": overdue, "deadline_days": None, "source_label": st}
        out.append({
            "id": rid, "version": VERSION, "task": "T2", "language": language_of(text), "split": split_for(rid),
            "synthetic": True, "source": {"file": SOURCES["timelines"], "round": "timelines", "original_id": c["id"]},
            "input": {"events": c["events"], "patient": c.get("patient") or {}, "index_event_id": first_report,
                      "fhir_bundle": bundle(res)},
            "eval_time": c["evaluation_date"][:10] + "T23:59:00Z",
            "gold": {"rules": sorted(obligations), "window_days": None, "scope_rules": sorted(run_timelines.REPORT_RULES),
                     "evidence_spans": None, "obligations": obligations},
            "rationale": c.get("rationale") or "", "tags": [],
        })
    return out


def blind_records(key: str) -> List[Dict[str, Any]]:
    out = []
    for c in _load(SOURCES[key]):
        rid = f"{key}:{c['id']}"
        text = json.dumps(c["resources"], ensure_ascii=False)
        obligations = {e["rule"]: {"status": e.get("status", "open"), "overdue": None,
                                   "deadline_days": e.get("deadline_days"), "source_label": e.get("status", "open")}
                       for e in c["expected"]}
        out.append({
            "id": rid, "version": VERSION, "task": "T2", "language": language_of(text), "split": split_for(rid),
            "synthetic": True, "source": {"file": SOURCES[key], "round": key, "original_id": c["id"]},
            "input": {"fhir_bundle": bundle(c["resources"]), "rule_focus": c.get("rule_focus")},
            "eval_time": c["evaluation_time"],
            "gold": {"rules": sorted(obligations), "window_days": None, "scope_rules": BLIND_RULES,
                     "evidence_spans": None, "obligations": dict(sorted(obligations.items()))},
            "rationale": c.get("rationale") or "", "tags": [],
        })
    return out


def rule_groups() -> Dict[str, Any]:
    """Finding-level equivalence groups (one alert per finding), copied from the evaluation harnesses."""
    return {"T1": [sorted(g) for g in run_eval.GROUPS], "T3": [sorted(g) for g in run_eval.GROUPS],
            "T2": [sorted(g) for g in run_timelines.GROUPS]}


def build(out_dir: str) -> Dict[str, Any]:
    records = report_records() + timeline_records() + blind_records("blind_reports_2") + blind_records("blind_reports_3")
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate record ids"
    os.makedirs(out_dir, exist_ok=True)
    files = {"T1": "t1_report_obligations.jsonl", "T2": "t2_loop_status.jsonl", "T3": "t3_korean_mixed.jsonl"}
    counts: Dict[str, Any] = {}
    for task, name in files.items():
        rows = sorted((r for r in records if r["task"] == task), key=lambda r: r["id"])
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        c: Dict[str, Dict[str, int]] = {"split": {}, "language": {}}
        for r in rows:
            c["split"][r["split"]] = c["split"].get(r["split"], 0) + 1
            c["language"][r["language"]] = c["language"].get(r["language"], 0) + 1
        counts[task] = {"file": name, "records": len(rows), **{k: dict(sorted(v.items())) for k, v in c.items()}}
    manifest = {"name": "ClinLoop-Bench", "version": VERSION, "random_state": RANDOM_STATE, "dev_percent": DEV_PERCENT,
                "tasks": counts, "rule_groups": rule_groups(),
                "sources": {k: {"path": p, "sha256": _sha(p)} for k, p in sorted(SOURCES.items())}}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "benchmark", "data", f"v{VERSION}"))
    m = build(ap.parse_args().out)
    for task, c in m["tasks"].items():
        print(task, c["records"], "split", c["split"], "language", c["language"])


if __name__ == "__main__":
    main()
