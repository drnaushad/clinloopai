"""
ClinLoop-Bench scorer.

    python benchmark/score.py PREDICTIONS.jsonl [--split test|dev|all] [--data benchmark/data/v1.0]
                              [--bootstrap 1000] [--json]

A prediction line: {"id": "...", "rules": ["R003", ...],
                    "evidence": {"R003": "Recommend follow-up CT in 6-12 months."},          # optional
                    "obligations": {"R003": {"status": "open", "overdue": true}}}           # T2
For T2, "rules" may be omitted (the keys of "obligations" are used). Records without a prediction count
as "nothing predicted". Only rules in a record's gold.scope_rules are scored. Pure stdlib + numpy.
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.join(HERE, "data", "v1.0")
SEED = 42
TOKEN = re.compile(r"[\w가-힣]+", re.UNICODE)


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_gold(data_dir: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(data_dir)):
        if name.endswith(".jsonl"):
            rows.extend(load_jsonl(os.path.join(data_dir, name)))
    return rows


def load_groups(data_dir: str) -> Dict[str, List[List[str]]]:
    path = os.path.join(data_dir, "manifest.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("rule_groups", {})


def _group_key(rule: str, groups: List[List[str]]) -> str:
    for i, g in enumerate(groups):
        if rule in g:
            return f"G{i}"
    return rule


def token_f1(a: str, b: str) -> float:
    ta, tb = TOKEN.findall((a or "").lower()), TOKEN.findall((b or "").lower())
    if not ta or not tb:
        return 0.0
    common = sum(min(ta.count(t), tb.count(t)) for t in set(ta))
    if not common:
        return 0.0
    p, r = common / len(tb), common / len(ta)
    return 2 * p * r / (p + r)


def record_counts(gold: Dict[str, Any], pred: Optional[Dict[str, Any]], groups: List[List[str]]) -> Dict[str, float]:
    """Per-record sufficient statistics; every metric is a ratio of sums of these (so bootstrap is cheap)."""
    pred = pred or {}
    g = gold["gold"]
    scope = set(g.get("scope_rules") or [])
    obligations = pred.get("obligations") or {}
    got_raw = set(pred.get("rules") if pred.get("rules") is not None else obligations.keys())
    # Rules outside the scope are ignored, except non-catalogue labels (e.g. a generic "FOLLOW_UP"),
    # which always count as predictions so a baseline cannot hide them.
    got = {r for r in got_raw if r in scope or not re.fullmatch(r"R\d{3}", str(r))}
    exp = set(g.get("rules") or [])
    c: Dict[str, float] = {"n": 1, "tp": len(exp & got), "fp": len(got - exp), "fn": len(exp - got),
                           "exact": float(exp == got)}
    ge, gg = {_group_key(r, groups) for r in exp}, {_group_key(r, groups) for r in got}
    c.update(gtp=len(ge & gg), gfp=len(gg - ge), gfn=len(ge - gg))
    # Report-level: does the record need any follow-up?
    c.update(btp=float(bool(exp) and bool(got)), bfp=float(not exp and bool(got)),
             bfn=float(bool(exp) and not got), btn=float(not exp and not got))
    # Evidence spans (only where gold spans exist)
    spans = g.get("evidence_spans") or {}
    ev = pred.get("evidence") or {}
    c.update(ev_n=0.0, ev_sum=0.0)
    for rule, span in spans.items():
        texts = span if isinstance(span, list) else [span]
        c["ev_n"] += 1
        c["ev_sum"] += max((token_f1(t, ev.get(rule, "")) for t in texts), default=0.0)
    # Loop status (T2): matched by rule id, else by a predicted rule of the same finding group
    c.update(st_n=0.0, st_ok=0.0, od_n=0.0, od_ok=0.0, false_closure=0.0, review=0.0)
    for rule, o in (g.get("obligations") or {}).items():
        p = obligations.get(rule)
        if p is None:
            key = _group_key(rule, groups)
            p = next((obligations[r] for r in sorted(obligations) if _group_key(r, groups) == key), None)
        c["st_n"] += 1
        if p is not None:
            # An active loop routed to a human ("needs_human_review") is a correct answer for a gold "open"
            # obligation (fail toward a human); it is also counted separately in "review".
            c["st_ok"] += float(p.get("status") == o["status"]
                                or (o["status"] == "open" and p.get("status") == "needs_human_review"))
            c["review"] += float(p.get("status") == "needs_human_review")
            c["false_closure"] += float(o["status"] == "open" and p.get("status") == "closed")
        if o.get("overdue") is not None:
            c["od_n"] += 1
            c["od_ok"] += float(p is not None and p.get("overdue") is not None and bool(p["overdue"]) == o["overdue"])
    return c


def _ratio(num: float, den: float) -> float:
    return num / den if den else float("nan")


def _f1(tp: float, fp: float, fn: float) -> float:
    return _ratio(2 * tp, 2 * tp + fp + fn)


METRICS: Dict[str, Callable[[Dict[str, float]], float]] = {
    "rule_precision": lambda s: _ratio(s["tp"], s["tp"] + s["fp"]),
    "rule_recall": lambda s: _ratio(s["tp"], s["tp"] + s["fn"]),
    "rule_f1": lambda s: _f1(s["tp"], s["fp"], s["fn"]),
    "finding_f1": lambda s: _f1(s["gtp"], s["gfp"], s["gfn"]),
    "needs_followup_precision": lambda s: _ratio(s["btp"], s["btp"] + s["bfp"]),
    "needs_followup_recall": lambda s: _ratio(s["btp"], s["btp"] + s["bfn"]),
    "needs_followup_f1": lambda s: _f1(s["btp"], s["bfp"], s["bfn"]),
    "specificity": lambda s: _ratio(s["btn"], s["btn"] + s["bfp"]),
    "exact_match": lambda s: _ratio(s["exact"], s["n"]),
    "evidence_token_f1": lambda s: _ratio(s["ev_sum"], s["ev_n"]),
    "status_accuracy": lambda s: _ratio(s["st_ok"], s["st_n"]),
    "overdue_accuracy": lambda s: _ratio(s["od_ok"], s["od_n"]),
}
TASK_METRICS = {
    "T1": ["rule_precision", "rule_recall", "rule_f1", "finding_f1", "needs_followup_precision",
           "needs_followup_recall", "needs_followup_f1", "specificity", "exact_match", "evidence_token_f1"],
    "T2": ["rule_precision", "rule_recall", "rule_f1", "status_accuracy", "overdue_accuracy", "exact_match"],
}
TASK_METRICS["T3"] = TASK_METRICS["T1"]


def summarise(counts: List[Dict[str, float]], metrics: List[str], n_boot: int, seed: int = SEED) -> Dict[str, Any]:
    keys = sorted(counts[0]) if counts else []
    mat = np.array([[c[k] for k in keys] for c in counts], dtype=float) if counts else np.zeros((0, 0))
    total = dict(zip(keys, mat.sum(axis=0))) if counts else {}
    out: Dict[str, Any] = {"records": len(counts)}
    rng = np.random.default_rng(seed)
    boots = []
    if counts and n_boot:
        idx = rng.integers(0, len(counts), size=(n_boot, len(counts)))
        sums = np.stack([mat[i].sum(axis=0) for i in idx])
        boots = [dict(zip(keys, row)) for row in sums]
    for m in metrics:
        point = METRICS[m](total) if counts else float("nan")
        vals = np.array([METRICS[m](b) for b in boots], dtype=float)
        vals = vals[~np.isnan(vals)]
        lo, hi = (np.percentile(vals, [2.5, 97.5]) if len(vals) and not np.isnan(point) else (float("nan"),) * 2)
        out[m] = {"value": point, "ci95": [float(lo), float(hi)]}
    for k in ("false_closure", "review"):
        if k in total:
            out[k] = int(total[k])
    return out


def score(gold: List[Dict[str, Any]], preds: Dict[str, Dict[str, Any]], split: str = "test",
          n_boot: int = 1000, groups: Optional[Dict[str, List[List[str]]]] = None) -> Dict[str, Any]:
    groups = groups or {}
    result: Dict[str, Any] = {}
    for task in ("T1", "T2", "T3"):
        rows = [g for g in gold if g["task"] == task and (split == "all" or g["split"] == split)]
        if not rows:
            continue
        counts = [record_counts(g, preds.get(g["id"]), groups.get(task, [])) for g in rows]
        result[task] = summarise(counts, TASK_METRICS[task], n_boot)
        result[task]["predicted_records"] = sum(1 for g in rows if g["id"] in preds)
    return result


def fmt(v: Dict[str, Any]) -> str:
    if v["value"] != v["value"]:
        return "n/a"
    lo, hi = v["ci95"]
    ci = "" if lo != lo else f" [{100 * lo:.1f}-{100 * hi:.1f}]"
    return f"{100 * v['value']:.1f}{ci}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score predictions against ClinLoop-Bench")
    ap.add_argument("predictions")
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    preds = {p["id"]: p for p in load_jsonl(a.predictions)}
    res = score(load_gold(a.data), preds, a.split, a.bootstrap, load_groups(a.data))
    if a.json:
        print(json.dumps(res, indent=1, default=float))
        return 0
    for task, r in res.items():
        print(f"{task} ({a.split}, {r['records']} records, {r['predicted_records']} predicted) — % [95% bootstrap CI]")
        for m in TASK_METRICS[task]:
            print(f"  {m:26s} {fmt(r[m])}")
        if task == "T2":
            print(f"  {'false_closures':26s} {r.get('false_closure', 0)}")
            print(f"  {'needs_human_review':26s} {r.get('review', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
