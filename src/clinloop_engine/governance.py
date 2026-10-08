"""
governance.py — Specialist sign-off of rules and hospital approval of the critical-finding list

No rule is fit for patient care until a named specialist has reviewed it.
ClinLoop records that review; it cannot replace it.

  * Each rule has a fingerprint: a hash of its clinical definition (trigger,
    follow-ups, deadline, severity, references) and, for rules decided from
    radiology reports, of the radiology decision code. A sign-off is bound to
    the fingerprint, so any change to the rule makes it "stale" and it must be
    reviewed again.
  * A rule is "approved" once CLINLOOP_SIGNOFF_APPROVALS distinct reviewers
    (default 1) have approved its current fingerprint and nobody's latest
    decision on it is a rejection or a change request.
  * The critical-finding list (config/critical_findings.json, or the file in
    CLINLOOP_CRITICAL_FINDINGS) is approved as a whole, bound to its content hash.
  * Shadow mode: with CLINLOOP_ENFORCE_SIGNOFF=1, loops from rules that are not
    approved are still detected and stored, but kept off the worklist. R035
    (critical findings) additionally needs the approved critical-finding list.

Every review and approval is written to the hash-chained audit log.
"""

import hashlib
import json
import re
import os
from typing import Dict, List, Optional

from .clinical_ontology import OBLIGATION_RULES, EventType, ObligationRule
from .radiology import load_critical_findings

_RADIOLOGY_SOURCE = os.path.join(os.path.dirname(__file__), "radiology.py")
CRITICAL_FINDINGS_KIND = "critical_findings"
CRITICAL_RULE = "R035"


def _radiology_logic_hash() -> str:
    with open(_RADIOLOGY_SOURCE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rule_fingerprint(rule: ObligationRule) -> str:
    """Hash of what a reviewer signs off: the rule's clinical definition (and radiology decision code)."""
    definition = {
        "rule_id": rule.rule_id, "name": rule.name, "description": rule.description,
        "trigger_event": rule.trigger_event.value, "trigger_condition": rule.trigger_condition,
        "required_followups": [f.value for f in rule.required_followups],
        "followup_logic": rule.followup_logic, "deadline_days": rule.deadline_days,
        "severity": rule.severity.value, "ltl_formula": rule.ltl_formula,
        "references": rule.references, "evidence_note": rule.evidence_note,
        "patient_outreach": rule.patient_outreach,
    }
    if rule.trigger_event == EventType.RADIOLOGY_REPORT:
        definition["radiology_logic"] = _radiology_logic_hash()
    return hashlib.sha256(json.dumps(definition, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def approvals_required() -> int:
    try:
        return max(1, int(os.environ.get("CLINLOOP_SIGNOFF_APPROVALS", "1")))
    except ValueError:
        return 1


def enforcement_enabled() -> bool:
    return os.environ.get("CLINLOOP_ENFORCE_SIGNOFF", "").strip().lower() in ("1", "true", "yes", "on")


GUIDELINES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "guidelines.json")


def load_guidelines() -> Dict:
    """The guideline registry (CLINLOOP_GUIDELINES overrides the bundled one)."""
    path = os.environ.get("CLINLOOP_GUIDELINES") or GUIDELINES_PATH
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"guidelines": []}


def _version(text: str) -> Optional[int]:
    """The edition a citation names: its 4-digit year (v2022, 2017, 'Diabetes-2026')."""
    years = [int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text or "")]
    return min(years) if years else None


def guideline_alerts(rule: ObligationRule, registry: Optional[Dict] = None) -> List[Dict]:
    """Citations of an older edition than the registry's current one: the rule needs specialist re-review."""
    registry = registry if registry is not None else load_guidelines()
    alerts = []
    for g in registry.get("guidelines", []):
        current = _version(str(g.get("current")))
        for ref in rule.references:
            if not re.search(g.get("match") or "^$", ref, re.I):
                continue
            cited = _version(ref)
            if cited and current and cited < current:
                accepted = (g.get("accepted") or {}).get(rule.rule_id)
                alerts.append({"guideline": g["id"], "title": g.get("title"), "cited": cited, "current": current,
                               "current_ref": g.get("current_ref"), "change": g.get("change"),
                               "accepted": accepted, "reference": ref})
    return alerts


def rule_status(rule: ObligationRule, reviews: List[Dict]) -> Dict:
    current = rule_fingerprint(rule)
    on_current = [r for r in reviews if r["rule_hash"] == current]
    latest_by_reviewer: Dict[str, Dict] = {}
    for r in on_current:                       # reviews come in id order: the last one wins
        latest_by_reviewer[r["reviewer"]] = r
    decisions = [r["decision"] for r in latest_by_reviewer.values()]
    approvers = sorted(name for name, r in latest_by_reviewer.items() if r["decision"] == "approve")
    if "reject" in decisions:
        status = "rejected"
    elif "request_changes" in decisions:
        status = "changes_requested"
    elif len(approvers) >= approvals_required():
        status = "approved"
    elif any(r["decision"] == "approve" for r in reviews if r["rule_hash"] != current) and not on_current:
        status = "stale"                       # approved before, but the rule has changed since
    else:
        status = "pending"
    return {"rule_id": rule.rule_id, "fingerprint": current, "status": status,
            "guideline_alerts": guideline_alerts(rule),
            "approvals": len(approvers), "approvals_required": approvals_required(), "approvers": approvers,
            "reviews": [{k: r[k] for k in ("decision", "reviewer", "specialty", "note", "decided_at", "rule_hash")}
                        for r in reviews]}


def all_rule_statuses(store) -> Dict[str, Dict]:
    by_rule: Dict[str, List[Dict]] = {}
    for r in store.rule_reviews():
        by_rule.setdefault(r["rule_id"], []).append(r)
    return {rule.rule_id: rule_status(rule, by_rule.get(rule.rule_id, [])) for rule in OBLIGATION_RULES}


def critical_list_status(store) -> Dict:
    active = load_critical_findings()
    approval = store.latest_config_approval(CRITICAL_FINDINGS_KIND)
    if approval is None:
        status = "not_approved"
    elif approval["content_hash"] == active["hash"]:
        status = "approved"
    else:
        status = "changed_since_approval"
    return {"status": status, "content_hash": active["hash"], "source": os.path.basename(active["path"]),
            "custom_list": active["path"] != os.path.join(os.path.dirname(__file__), "config", "critical_findings.json"),
            "name": active["data"].get("name"), "basis": active["data"].get("basis"),
            "findings": active["data"].get("findings", []),
            "approval": ({k: approval[k] for k in ("approver", "title", "note", "decided_at", "content_hash")}
                         if approval else None)}


def summary(store) -> Dict:
    statuses = all_rule_statuses(store)
    counts: Dict[str, int] = {}
    for s in statuses.values():
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    critical = critical_list_status(store)
    return {"rules_total": len(statuses), "rules_approved": counts.get("approved", 0), "by_status": counts,
            "approvals_required": approvals_required(), "enforce_signoff": enforcement_enabled(),
            "critical_findings_list": critical["status"],
            "guideline_updates": sorted(r for r, st in statuses.items()
                                        if any(not a["accepted"] for a in st.get("guideline_alerts") or []))}


def live_rule_ids(store) -> Optional[set]:
    """Rules allowed on the worklist, or None when sign-off is not enforced."""
    if not enforcement_enabled():
        return None
    statuses = all_rule_statuses(store)
    live = {rid for rid, s in statuses.items() if s["status"] == "approved"}
    if critical_list_status(store)["status"] != "approved":
        live.discard(CRITICAL_RULE)
    return live
