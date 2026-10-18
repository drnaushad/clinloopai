"""
outcomes.py — What happened after each loop opened: closed-loop accountability

Detecting a missed follow-up helps a patient only if the follow-up then happens. These measures follow
every loop from the moment it opened to its end, so a hospital (and the Stage 2 and 3 studies,
STUDY_PROTOCOL.md) can see whether alerts lead to care:

  * acted on: a person acknowledged, assigned, deferred, closed or messaged the patient; time to that
    first action;
  * closed: by a follow-up found in the record, or by staff with written evidence; time from opening;
  * late: closed after the deadline, and by how many days (the Stage 3 primary outcome is time to
    completion of overdue follow-up);
  * dismissed: deferred as not clinically indicated or as a duplicate, with every deferral reason
    counted, so the rules clinicians disagree with are visible (rule_monitor.py acts on the same data);
  * still open past the deadline, and among those, never touched by anyone: the loops most at risk.

Everything is read from the hash-chained audit log, so the figures match the record. Only counts and
durations are returned: no patient identifiers. During the silent run nothing reaches staff, so the
figures then describe usual care alone.
"""

from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Dict, List, Optional

from .rule_monitor import DISMISSAL_REASONS
from .safety_clock import utc_now

STAFF_ACTIONS = ("acknowledge", "assign", "defer", "close", "outreach_drafted")
CLOSING = ("loop_resolved_by_record", "close")
_ACTIONS = ("loop_opened", "loop_reopened") + STAFF_ACTIONS + ("loop_resolved_by_record",)
ACTIVE = ("new", "acknowledged")


def _t(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", ""))


def _med(values: List[float], digits: int = 1) -> Optional[float]:
    return round(median(values), digits) if values else None


def _summary(rows: List[Dict]) -> Dict:
    n = len(rows)
    acted = [r for r in rows if r["first_action_h"] is not None]
    closed = [r for r in rows if r["closed_by"]]
    late = [r for r in closed if r["days_late"] is not None and r["days_late"] > 0]
    reasons = Counter(r["defer_reason"] for r in rows if r["defer_reason"])
    dismissed = sum(v for k, v in reasons.items() if k in DISMISSAL_REASONS)
    open_overdue = [r for r in rows if r["open_overdue"]]
    return {
        "opened": n,
        "acted_on": len(acted), "acted_on_share": round(len(acted) / n, 2) if n else None,
        "median_hours_to_first_action": _med([r["first_action_h"] for r in acted]),
        "closed_by_record": sum(1 for r in closed if r["closed_by"] == "record"),
        "closed_by_staff": sum(1 for r in closed if r["closed_by"] == "staff"),
        "median_days_to_closure": _med([r["days_to_closure"] for r in closed]),
        "closed_late": len(late), "median_days_late": _med([r["days_late"] for r in late]),
        "dismissed": dismissed, "dismissed_share": round(dismissed / n, 2) if n else None,
        "defer_reasons": dict(sorted(reasons.items())),
        "open_past_deadline": len(open_overdue),
        "open_past_deadline_never_acted_on": sum(1 for r in open_overdue if r["first_action_h"] is None),
    }


def loop_outcomes(store, now: Optional[datetime] = None) -> Dict:
    """Outcome of every loop that opened, overall and per rule. Counts and durations only."""
    now = now or utc_now()
    events = defaultdict(list)
    for e in store.loop_audit_events(_ACTIONS):
        events[e["loop_key"]].append(e)
    loops = {l["loop_key"]: l for l in store.worklist(include_inactive=True, now=now)}
    rows = []
    for key, evs in events.items():
        loop = loops.get(key)
        opened = next((e for e in evs if e["action"] == "loop_opened"), None)
        if loop is None or opened is None or loop["workflow_state"] == "superseded":
            continue
        t0 = _t(opened["ts"])
        staff = [e for e in evs if e["action"] in STAFF_ACTIONS and e["role"] != "system"]
        first_action_h = round((_t(staff[0]["ts"]) - t0).total_seconds() / 3600, 1) if staff else None
        closed_by, days_to_closure, days_late = None, None, None
        if loop["workflow_state"] not in ACTIVE and loop["workflow_state"] != "deferred":
            closing = [e for e in evs if e["action"] in CLOSING]
            if closing:
                end = closing[-1]
                closed_by = "record" if end["action"] == "loop_resolved_by_record" else "staff"
                days_to_closure = round((_t(end["ts"]) - t0).total_seconds() / 86400, 1)
                if loop.get("deadline"):
                    days_late = round((_t(end["ts"]) - _t(loop["deadline"])).total_seconds() / 86400, 1)
        defers = [e for e in staff if e["action"] == "defer"]
        open_overdue = (loop["workflow_state"] in ACTIVE and bool(loop.get("deadline"))
                        and _t(loop["deadline"]) < now)
        rows.append({"rule_id": loop["rule_id"], "first_action_h": first_action_h, "closed_by": closed_by,
                     "days_to_closure": days_to_closure, "days_late": days_late,
                     "defer_reason": (defers[-1]["detail"].get("reason") if defers else None),
                     "open_overdue": open_overdue})
    by_rule = defaultdict(list)
    for r in rows:
        by_rule[r["rule_id"]].append(r)
    from .pilot import silent_run
    return {"as_of": now.isoformat(), "silent_run": silent_run(), "overall": _summary(rows),
            "rules": {rid: _summary(rs) for rid, rs in sorted(by_rule.items())},
            "note": ("Counts and durations from the audit log, no patient identifiers. During a silent run "
                     "nothing reaches staff, so these figures describe usual care alone.")}
