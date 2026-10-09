"""
Would the model-based second reader have sent the rules' first-pass misses to a person?

Inputs: a case set; the rules' FIRST-PASS output per case (from the code as it was when the set was first
scored); the second reader's raw answers per case (a stand-in model given only the prompt and the report).
Each answer goes through the real verification (second_reader.read_report: exact quote, fixed categories) and
the real coverage check (second_reader.uncovered: only items no rule tracked).

Reports:
  caught      a finding the rules missed, flagged by the second reader in the matching category
  flag rate   reports needing nothing that the second reader flags anyway (clinician workload)
Usage: run_second_reader_eval.py cases.json rules_first.json answers.json [answers2.json …]
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))
from run_eval import REPORT_RULES  # noqa: E402
from src.clinloop_engine.second_reader import read_report, uncovered  # noqa: E402

GROUP = {"imaging": {"R003", "R019", "R034", "R030", "R031", "R032", "R033", "R037", "R040", "R041", "R043", "R044"},
         "workup": {"R036", "R039", "R018", "R020", "R046", "R038", "R042", "R045"},
         "critical": {"R035"}, "pathology": {"R009"}}
CATEGORY_GROUP = {"imaging_followup": {"imaging"}, "biopsy_or_workup": {"workup", "pathology"},
                  "specialist_referral": {"workup", "pathology"}, "critical_finding": {"critical"},
                  "abnormal_pathology": {"pathology", "workup"}}


def groups(rules):
    return {g for g, rs in GROUP.items() if set(rules) & rs}


def main():
    cases = json.load(open(sys.argv[1], encoding="utf-8"))
    first = json.load(open(sys.argv[2]))
    answers = {}
    for path in [a for a in sys.argv[3:] if not a.startswith("--")]:
        answers.update(json.load(open(path, encoding="utf-8")))
    missed = caught = negatives = flagged_neg = flags_total = dropped = items_total = no_answer = 0
    rows = []
    for c in cases:
        exp = set(c["expected_rules"]) & REPORT_RULES
        got = set(first.get(c["id"], []))
        raw = answers.get(c["id"])
        if raw is None:
            no_answer += 1
            continue
        text = raw if isinstance(raw, str) else json.dumps(raw)
        out = read_report(c["text"], lambda p, s, t=text: {"text": t, "model": "stand-in"})
        items = out["items"] if out["available"] else []
        dropped += out.get("dropped", 0)
        items_total += len(items)
        flags = uncovered(items, got)
        flags_total += len(flags)
        flag_groups = set().union(*[CATEGORY_GROUP[f["category"]] for f in flags]) if flags else set()
        for g in groups(exp) - groups(got):          # a finding the rules missed
            missed += 1
            hit = g in flag_groups
            caught += hit
            rows.append((c["id"], g, "caught" if hit else "MISSED", [f["quote"][:70] for f in flags]))
        if not exp:
            negatives += 1
            flagged_neg += bool(flags)
            if flags:
                rows.append((c["id"], "-", "FLAG ON NORMAL", [f["quote"][:70] for f in flags]))
    print(f"cases={len(cases)} answered={len(cases) - no_answer}")
    print(f"rule misses caught by the second reader: {caught}/{missed} = {caught / max(1, missed):.0%}")
    print(f"normal reports flagged anyway: {flagged_neg}/{negatives} = {flagged_neg / max(1, negatives):.0%}")
    print(f"flags raised: {flags_total}; items verified: {items_total}; items dropped (no exact quote or bad category): {dropped}")
    if "--show" in sys.argv:
        for r in rows:
            print(" ", *r)


if __name__ == "__main__":
    main()
