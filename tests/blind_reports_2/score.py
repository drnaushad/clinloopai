"""
score.py — Score ClinLoop on the blind set for R060–R065 (tests/blind_reports_2/cases.json)

The cases were written by an independent author from the guideline definitions alone, without seeing
ClinLoop's code. Each case lists the obligations (rule, deadline, open/closed) the records should open.

    python tests/blind_reports_2/score.py            # metrics
    python tests/blind_reports_2/score.py --misses   # also each disagreement, for review
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402

RULES = ("R060", "R061", "R062", "R063", "R064", "R065")
CASES = os.path.join(os.path.dirname(__file__), "cases.json")


def predict(case: Dict) -> Dict[str, Tuple[str, float]]:
    """{rule: (status, deadline_days)} for R060–R065."""
    events, _ = bundle_to_events(case["resources"])
    out: Dict[str, Tuple[str, float]] = {}
    for pid, evs in events.items():
        for d in ClinLoopDetector(evaluation_time=case["evaluation_time"]).process_patient("blind", pid, evs):
            if d.rule_id not in RULES:
                continue
            days = round((datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds()
                         / 86400)
            status = "closed" if d.loop_status in ("closed", "delayed") else "open"
            out[d.rule_id] = (status, days, d.loop_status == "needs_human_review")
    return out


def wilson(k: int, n: int) -> str:
    if not n:
        return "n/a"
    z, p = 1.96, k / n
    den = 1 + z * z / n
    centre, half = (p + z * z / (2 * n)) / den, z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return f"{100 * p:.1f}% (95% CI {100 * (centre - half):.1f}–{100 * (centre + half):.1f})"


def score(cases: List[Dict], show_misses: bool = False) -> Dict:
    per = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn_cases": 0, "status_ok": 0, "deadline_ok": 0})
    exact_cases, misses, for_review = 0, [], 0
    for case in cases:
        expected = {e["rule"]: (e.get("status", "open"), float(e["deadline_days"])) for e in case["expected"]}
        got = predict(case)
        case_ok = True
        for rule in RULES:
            e, g = expected.get(rule), got.get(rule)
            s = per[rule]
            if g and g[2]:
                for_review += 1
            g = g[:2] if g else g
            if e and g:
                s["tp"] += 1
                s["status_ok"] += e[0] == g[0]
                s["deadline_ok"] += abs(e[1] - g[1]) <= 1
                if e[0] != g[0] or abs(e[1] - g[1]) > 1:
                    case_ok = False
                    misses.append((case["id"], rule, f"expected {e}, got {g}"))
            elif e:
                s["fn"] += 1
                case_ok = False
                misses.append((case["id"], rule, f"missed: expected {e}"))
            elif g:
                s["fp"] += 1
                case_ok = False
                misses.append((case["id"], rule, f"false alarm: got {g}"))
            elif case.get("rule_focus") == rule:
                s["tn_cases"] += 1
        exact_cases += case_ok
    total = {k: sum(s[k] for s in per.values()) for k in ("tp", "fp", "fn", "status_ok", "deadline_ok")}
    report = {"cases": len(cases), "cases_fully_correct": wilson(exact_cases, len(cases)),
              "sensitivity": wilson(total["tp"], total["tp"] + total["fn"]),
              "precision": wilson(total["tp"], total["tp"] + total["fp"]),
              "status_correct_when_found": wilson(total["status_ok"], total["tp"]),
              "deadline_correct_when_found": wilson(total["deadline_ok"], total["tp"]),
              # Open obligations shown as "needs human review": sparse test records (one or two resources)
              "open_shown_for_review": for_review,
              "per_rule": {r: {**per[r], "sensitivity": wilson(per[r]["tp"], per[r]["tp"] + per[r]["fn"]),
                               "precision": wilson(per[r]["tp"], per[r]["tp"] + per[r]["fp"])} for r in RULES}}
    if show_misses:
        report["misses"] = misses
    return report


if __name__ == "__main__":
    with open(CASES, encoding="utf-8") as f:
        data = json.load(f)
    print(json.dumps(score(data, "--misses" in sys.argv), indent=1, ensure_ascii=False))
