"""
rule_check.py — Check the rule set itself before it can harm anyone

A rule that can never fire is a silent gap; a rule whose follow-up no data
source ever produces is a loop that can never close (a permanent false alarm).
Neither shows up in a test of the rule; both show up here, by reading what the
real-data pipeline (FHIR mappers, radiology reader, note reader, patterns,
AI review, the hypergraph's condition inference) can actually produce.

  error    the rule cannot work on real data (CI fails)
  warning  it works only through an unusual route (e.g. the explicit FHIR
           event-type extension, or synthetic data only), or documentation
           a specialist needs for sign-off is missing

GET /api/v1/governance/rule-check shows the result; tests/test_rule_check.py
keeps it at zero errors.
"""

import os
import re
from typing import Dict, List

from .clinical_ontology import OBLIGATION_RULES, RULE_NAMES_KO

HERE = os.path.dirname(os.path.abspath(__file__))
# Modules that turn real hospital data into events, and those that set trigger conditions
EVENT_PRODUCERS = ["fhir_ingest.py", "radiology.py", "motifs.py", "ai_review.py"]
CONDITION_PRODUCERS = EVENT_PRODUCERS + ["note_reader.py", "temporal_hypergraph.py"]
SYNTHETIC = ["data_generator.py"]


def _source(files: List[str]) -> str:
    out = []
    for f in files:
        try:
            with open(os.path.join(HERE, f), encoding="utf-8") as fh:
                out.append(fh.read())
        except OSError:
            pass
    return "\n".join(out)


def _produces_condition(src: str, cond: str) -> bool:
    if re.search(r"['\"]" + re.escape(cond) + r"['\"]", src):
        return True
    # Built at run time: f"note_plan_{kind}", f"radiologist_rec_{modality}" …
    parts = cond.split("_")
    for i in range(1, len(parts)):
        prefix = "_".join(parts[:i]) + "_"
        if re.search(r"f['\"]" + re.escape(prefix) + r"\{", src):
            return True
    return False


def _produces_event(src: str, event_value: str, enum_name: str) -> bool:
    return bool(re.search(r"EventType\." + re.escape(enum_name) + r"\b", src)
                or re.search(r"['\"]" + re.escape(event_value) + r"['\"]", src))


def check_rules() -> Dict[str, object]:
    from .governance import guideline_alerts, load_guidelines
    from .literature import EVIDENCE_QUERIES
    registry = load_guidelines()
    real, events_src, synthetic = _source(CONDITION_PRODUCERS), _source(EVENT_PRODUCERS), _source(SYNTHETIC)
    issues: List[Dict[str, str]] = []

    def add(rule_id: str, level: str, msg: str) -> None:
        issues.append({"rule_id": rule_id, "level": level, "message": msg})

    seen = set()
    for r in OBLIGATION_RULES:
        if r.rule_id in seen:
            add(r.rule_id, "error", "duplicate rule id")
        seen.add(r.rule_id)
        cond = r.trigger_condition
        if cond != "any" and not _produces_condition(real, cond):
            if _produces_condition(synthetic, cond):
                add(r.rule_id, "warning", f"trigger '{cond}' is produced only by the synthetic data generator: "
                                          "this rule cannot fire on hospital data")
            else:
                add(r.rule_id, "error", f"trigger '{cond}' is produced by no part of the pipeline: the rule never fires")
        trig = r.trigger_event
        if not _produces_event(events_src, trig.value, trig.name):
            add(r.rule_id, "warning", f"trigger event {trig.value} only via the explicit FHIR event-type extension")
        closable = [f for f in r.required_followups if _produces_event(events_src, f.value, f.name)]
        missing = [f.value for f in r.required_followups if f not in closable]
        if not closable:
            add(r.rule_id, "error", f"no required follow-up ({', '.join(missing)}) is produced from hospital data: "
                                    "every loop would stay open")
        elif missing and r.followup_logic != "any":
            add(r.rule_id, "error", f"needs all of its follow-ups but {', '.join(missing)} is never produced: "
                                    "every loop would stay open")
        elif missing:
            add(r.rule_id, "warning", f"follow-up type(s) {', '.join(missing)} only via the explicit extension "
                                      "(others can close it)")
        if r.deadline_days <= 0:
            add(r.rule_id, "error", "deadline must be positive")
        if not r.references:
            add(r.rule_id, "warning", "no reference: a specialist cannot check the source")
        if not r.ltl_formula:
            add(r.rule_id, "warning", "no formal (LTL) statement")
        if r.rule_id not in RULE_NAMES_KO:
            add(r.rule_id, "warning", "no Korean name for the worklist")
        for a in guideline_alerts(r, registry):
            if not a["accepted"]:
                add(r.rule_id, "warning", f"cites {a['title']} {a['cited']}; the current edition is {a['current']}"
                                          f"{' (' + a['change'] + ')' if a.get('change') else ''}: specialist re-review")
        if r.rule_id not in EVIDENCE_QUERIES:
            add(r.rule_id, "warning", "no literature query for live evidence")
    errors = [i for i in issues if i["level"] == "error"]
    return {"rules": len(OBLIGATION_RULES), "errors": len(errors),
            "warnings": len(issues) - len(errors), "issues": issues}
