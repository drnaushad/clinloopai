"""
build_demo_reports.py — Build data/demo_reports.json for the public demo (synthetic reports only)

Takes a fixed set of synthetic evaluation reports and MedGemma 27B's saved answers to them
(tests/report_eval/second_reader/medgemma27b_*.json, made with the production prompt; see
medgemma27b_manifest.json) and runs each answer through the second reader's real checks (exact quote,
fixed category, not-actionable filter). Nothing is invented: a case whose saved answer yields no
item shows none.

    python scripts/build_demo_reports.py
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.clinloop_engine import demo_reader  # noqa: E402
from src.clinloop_engine.second_reader import read_report  # noqa: E402

SR = os.path.join(ROOT, "tests", "report_eval", "second_reader")
# (case id, claim, what it shows). All synthetic. Each claim is checked against today's rules before
# the file is written, so the page never says something the app does not do:
#   agree        the model's item is also tracked by a rule
#   model_only   the model adds an item no rule tracks (a suggestion for a clinician)
#   model_false  a model-only item on a report that needs nothing: a false flag, shown on purpose
#   model_misses a rule opens an obligation and the model raises nothing
#   nothing      neither raises anything (the check removed a quoted "not needed", if any)
PICKS = [
    ("M005", "agree", "Synthetic colon biopsy: compare the saved MedGemma reading with pathology follow-up rules."),
    ("M016", "nothing", "Synthetic gastric biopsy: the saved reading and rules raise no tracked obligation."),
    ("M029", "agree", "Synthetic breast biopsy: compare pathology follow-up suggestions with the rules."),
    ("N071", "nothing", "Synthetic colon polyp pathology: compare a saved reading on a case with no tracked obligation."),
    ("M008", "agree", "Acute subdural haematoma: the critical-finding rule and MedGemma agree."),
    ("M093", "agree", "Ascending aortic aneurysm with Korean-English advice: rule and MedGemma agree."),
    ("N057", "agree", "Pancreatic cyst with worrisome features: EUS work-up, rule and MedGemma agree."),
    ("M015", "model_only", "MedGemma adds the urology cystoscopy for haematuria, which no rule tracks."),
    ("M065", "model_only", "Korean report: MedGemma adds the gynaecology referral (부인과 진료 권함)."),
    ("M014", "nothing", "Normal report: 'f/u 불필요'. MedGemma quoted it; the check removes it."),
    ("N070", "nothing", "Normal report: simple renal cyst, explicit 'f/u 불필요'."),
    ("N044", "model_false", "A false flag, shown on purpose: MedGemma raises a scalp haematoma on a normal trauma CT."),
    ("M084", "model_misses", "OCR-damaged '1O mm s0lid' nodule: the rule reads it, MedGemma misses it."),
]



def _check(cid, claim, c, items):
    c = dict(c, date=c["date"][:10])
    rules = demo_reader.rules_for(c)
    marked = demo_reader.compare(rules, items)
    only = [i for i in marked if i["agreement"].startswith("model only")]
    actual = ("model_false" if only and not c["expected_rules"] else "model_only" if only else
              "agree" if marked else "model_misses" if rules else "nothing")
    if actual != claim:
        raise SystemExit(f"{cid}: caption claims {claim!r} but today's rules and the saved reading give {actual!r}")


def main() -> None:
    cases = {}
    answers = {}
    for name in ("real", "confirm2"):
        cases.update({c["id"]: c for c in json.load(open(os.path.join(SR, f"cases_{name}.json"), encoding="utf-8"))})
        answers.update(json.load(open(os.path.join(SR, f"medgemma27b_{name}.json"), encoding="utf-8")))
    manifest = json.load(open(os.path.join(SR, "medgemma27b_manifest.json"), encoding="utf-8"))
    out = []
    for cid, claim, teaches in PICKS:
        c = cases[cid]
        raw = answers[cid]
        reading = read_report(c["text"], lambda p, s, t=raw: {"text": t, "model": manifest["model"]["name"]})
        _check(cid, claim, c, reading["items"])
        out.append({"id": cid, "title": c["title"], "date": c["date"][:10], "language": c["language"],
                    "report_type": c.get("report_type", "radiology"), "patient": c.get("patient") or {},
                    "text": c["text"], "teaches": teaches,
                    "saved_reading": {"available": reading["available"], "items": reading["items"],
                                      "dropped": reading.get("dropped", 0),
                                      "not_actionable": reading.get("not_actionable", 0),
                                      "read_at": manifest["date"], "source": "saved MedGemma 27B answer"}})
    doc = {"note": "Synthetic reports written for software testing. Not real patients. Model items are "
                   "suggestions for a clinician, never decisions.",
           "model": {k: manifest["model"][k] for k in ("name", "digest", "quantization")} |
                    {"prompt_version": manifest["prompt_version"], "temperature": 0.0},
           "cases": out}
    path = os.path.join(ROOT, "data", "demo_reports.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"{len(out)} cases → {path}")


if __name__ == "__main__":
    main()
