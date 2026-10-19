"""
Run the ClinLoop-Bench baselines and write benchmark/RESULTS.md.

    python benchmark/baselines/run_baselines.py [--out benchmark/baselines/predictions] [--no-results]

(a) rules    the ClinLoop rules engine, same call path as the blind evaluation harnesses
             (tests/report_eval/run_eval.py, run_timelines.py): FHIR bundle -> bundle_to_events -> ClinLoopDetector
(b) keyword  "recommend|follow-up|권고|추적" anywhere in the report text -> one generic obligation (FOLLOW_UP)
(c) ollama   optional; an on-premise Ollama model (CLINLOOP_OLLAMA_URL, default http://localhost:11434).
             Skipped when no server answers. Never calls an external API.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
ROOT = os.path.dirname(BENCH)
sys.path.insert(0, ROOT)
sys.path.insert(0, BENCH)

import score as scorer  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402

KEYWORD = re.compile(r"recommend|follow[- ]?up|권고|추적", re.IGNORECASE)
SENTENCE = re.compile(r"[^.\n。]+[.\n。]?")
GENERIC = "FOLLOW_UP"


def _when(eval_time: str):
    """Naive datetime for 'Z' times (as the report/timeline harnesses use); offset strings pass through."""
    if eval_time.endswith("Z"):
        return datetime.fromisoformat(eval_time[:19])
    return eval_time


def _overdue(d, when) -> bool:
    if d.loop_status == "delayed":
        return True
    if d.loop_status == "closed":
        return False
    w = when if isinstance(when, datetime) else datetime.fromisoformat(when)
    dl = datetime.fromisoformat(str(d.deadline))
    if (dl.tzinfo is None) != (w.tzinfo is None):
        dl, w = dl.replace(tzinfo=None), w.replace(tzinfo=None)
    return dl < w


def rules_engine(rec: Dict[str, Any]) -> Dict[str, Any]:
    resources = [e["resource"] for e in rec["input"]["fhir_bundle"]["entry"]]
    events, _ = bundle_to_events(resources)
    when = _when(rec["eval_time"])
    scope = set(rec["gold"]["scope_rules"])
    index = rec["input"].get("index_event_id")
    rules, evidence, obligations = set(), {}, {}
    for pid, evs in events.items():
        for d in ClinLoopDetector(evaluation_time=when).process_patient("bench", pid, evs):
            if d.rule_id not in scope or (index and f"/{index}:" not in str(d.trigger_event_id)):
                continue
            rules.add(d.rule_id)
            evidence[d.rule_id] = " ".join(d.basis or [])
            status = {"closed": "closed", "delayed": "closed"}.get(d.loop_status, d.loop_status)
            if status not in ("open", "closed", "needs_human_review"):
                status = "open"
            obligations[d.rule_id] = {"status": status, "overdue": _overdue(d, when)}
    return {"id": rec["id"], "rules": sorted(rules), "evidence": evidence, "obligations": obligations}


def _texts(rec: Dict[str, Any]) -> List[str]:
    inp = rec["input"]
    if inp.get("text"):
        return [inp["text"]]
    out = []
    for e in inp["fhir_bundle"]["entry"]:
        r = e["resource"]
        if r.get("resourceType") == "DiagnosticReport":
            out.append(r.get("conclusion") or "")
            out.extend(f.get("data", "") for f in r.get("presentedForm") or [] if isinstance(f, dict))
    return out


def keyword(rec: Dict[str, Any]) -> Dict[str, Any]:
    for text in _texts(rec):
        for s in SENTENCE.findall(text):
            if KEYWORD.search(s):
                return {"id": rec["id"], "rules": [GENERIC], "evidence": {GENERIC: s.strip()},
                        "obligations": {GENERIC: {"status": "open", "overdue": None}}}
    return {"id": rec["id"], "rules": [], "evidence": {}, "obligations": {}}


def ollama_url() -> str:
    return os.environ.get("CLINLOOP_OLLAMA_URL", "http://localhost:11434").rstrip("/")


def ollama_available(timeout: float = 2.0) -> Optional[List[str]]:
    try:
        with urllib.request.urlopen(ollama_url() + "/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None


def ollama(rec: Dict[str, Any], model: str, catalogue: str) -> Dict[str, Any]:
    """T1/T3 only: ask the local model for rule ids + evidence sentence as JSON."""
    prompt = (f"Rule catalogue:\n{catalogue}\n\nReport:\n{rec['input'].get('text', '')}\n\n"
              'Return JSON {"rules": [rule ids that this report obligates], "evidence": {rule id: sentence}}.')
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json",
                       "options": {"temperature": 0, "seed": 42}}).encode()
    req = urllib.request.Request(ollama_url() + "/api/generate", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(json.load(r).get("response") or "{}")
        return {"id": rec["id"], "rules": sorted(str(x) for x in out.get("rules") or []),
                "evidence": {str(k): str(v) for k, v in (out.get("evidence") or {}).items()}}
    except Exception:
        return {"id": rec["id"], "rules": [], "evidence": {}}


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def results_md(results: Dict[str, Dict[str, Any]], split: str) -> str:
    def f(v):
        return scorer.fmt(v)
    lines = ["# ClinLoop-Bench v1.0 — baseline results", "",
             f"Split: **{split}**. Values are %, with seeded (42) 1,000-sample bootstrap 95% CIs over records.",
             "Regenerate with `python benchmark/baselines/run_baselines.py`.", "",
             "**Caveat:** the rules engine was developed against these blind rounds (each round was scored once "
             "before fixes, then defects were fixed), so its scores here are *after-fix* and optimistic. The "
             "first-pass blind scores are in `docs/ACCURACY_EVALUATION.md`.", "",
             "## T1 (English reports) and T3 (Korean / mixed reports): report -> follow-up obligation", "",
             "| Baseline | Task | n | Rule P | Rule R | Rule F1 | Finding F1 | Needs-follow-up F1 | Specificity | Exact |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, res in results.items():
        for t in ("T1", "T3"):
            r = res.get(t)
            if r:
                lines.append(f"| {name} | {t} | {r['records']} | {f(r['rule_precision'])} | {f(r['rule_recall'])} | "
                             f"{f(r['rule_f1'])} | {f(r['finding_f1'])} | {f(r['needs_followup_f1'])} | "
                             f"{f(r['specificity'])} | {f(r['exact_match'])} |")
    lines += ["", "## T2: patient timeline / FHIR records -> loop status at the evaluation time", "",
              "| Baseline | n | Rule P | Rule R | Rule F1 | Status acc. | Overdue acc. | False closures | Needs review |",
              "|---|---|---|---|---|---|---|---|---|"]
    for name, res in results.items():
        r = res.get("T2")
        if r:
            lines.append(f"| {name} | {r['records']} | {f(r['rule_precision'])} | {f(r['rule_recall'])} | "
                         f"{f(r['rule_f1'])} | {f(r['status_accuracy'])} | {f(r['overdue_accuracy'])} | "
                         f"{r.get('false_closure', 0)} | {r.get('review', 0)} |")
    lines += ["", "Evidence-span overlap is not reported: v1.0 has no gold evidence spans (see README, limitations).",
              "The keyword baseline emits a generic `FOLLOW_UP` label, so its rule-level scores are zero by design; "
              "its needs-follow-up F1 is the meaningful comparison.", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=scorer.DEFAULT_DATA)
    ap.add_argument("--out", default=os.path.join(HERE, "predictions"))
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--no-results", action="store_true", help="do not rewrite benchmark/RESULTS.md")
    ap.add_argument("--ollama-model", default=os.environ.get("CLINLOOP_BENCH_OLLAMA_MODEL"))
    a = ap.parse_args(argv)
    gold = scorer.load_gold(a.data)
    groups = scorer.load_groups(a.data)
    os.makedirs(a.out, exist_ok=True)
    runs = {"ClinLoop rules engine": ("rules", rules_engine), "Keyword (recommend/follow-up/권고/추적)": ("keyword", keyword)}
    models = ollama_available()
    if models is None:
        print("ollama: no server reachable — LLM baseline skipped")
    else:
        model = a.ollama_model or (models[0] if models else None)
        if model:
            with open(os.path.join(ROOT, "tests", "report_eval", "rule_catalog.json"), encoding="utf-8") as fh:
                cat = "\n".join(f"{r['rule_id']}: {r['name']}" for r in json.load(fh))
            runs[f"Ollama {model}"] = ("ollama", lambda rec, m=model, c=cat: ollama(rec, m, c)
                                       if rec["task"] != "T2" else {"id": rec["id"], "rules": []})
    results = {}
    for name, (slug, fn) in runs.items():
        preds = [fn(r) for r in gold]
        write_jsonl(os.path.join(a.out, f"{slug}.jsonl"), preds)
        results[name] = scorer.score(gold, {p["id"]: p for p in preds}, a.split, a.bootstrap, groups)
    md = results_md(results, a.split)
    if not a.no_results:
        with open(os.path.join(BENCH, "RESULTS.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
