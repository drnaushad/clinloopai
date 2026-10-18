"""
rule_monitor.py — Watching live rules after go-live, with a safe automatic stop

A rule that was right in validation can go wrong in production: a laboratory changes a code, a
report template changes, a feed starts sending duplicates. Two signals show it:

  * volume: the rule opens far more loops this week than its usual week
    (at least MIN_VOLUME loops, and more than VOLUME_RATIO × the weekly average of the 4 weeks before);
  * dismissals: clinicians mostly dismiss its alerts as not indicated or duplicates
    (at least MIN_DECISIONS decisions in 4 weeks, DISMISS_RATE or more of them dismissals).

What happens then (clinical review, 2026-10: a surge alone can be real, e.g. a screening campaign or
a new clinic, so volume never hides a rule by itself; dismissals by clinicians are the evidence that
a rule is wrong):

  * dismissals: a rule that is not critical is PAUSED: its NEW, unacknowledged loops leave the
    worklist and page nobody, until an administrator resumes it with a note. Loops someone already
    acknowledged or deferred stay visible to them, so work in progress is never hidden;
  * volume only: the rule is FLAGGED for review on the governance page and worklist banner and keeps
    alerting; dismissals that follow can still pause it;
  * a CRITICAL rule is never paused (hiding a critical alert is the larger danger): it is only flagged.

Guards:
  * volume is judged only for rules with at least 5 weeks of history, so go-live and the first sync's
    back-fill (which opens many loops at once) pause nothing;
  * after a resume, the rule is not paused again for COOLDOWN_DAYS;
  * every pause, flag and resume is in the hash-chained audit log.

Settings (environment): CLINLOOP_MONITOR=0 reports without pausing or flagging;
CLINLOOP_MONITOR_VOLUME_RATIO, CLINLOOP_MONITOR_MIN_VOLUME, CLINLOOP_MONITOR_DISMISS_RATE,
CLINLOOP_MONITOR_MIN_DECISIONS override the thresholds.
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .clinical_ontology import OBLIGATION_RULES
from .safety_clock import utc_now

WINDOW_DAYS = 7
BASELINE_DAYS = 28
COOLDOWN_DAYS = 7
DISMISSAL_REASONS = {"not_clinically_indicated", "duplicate"}


def _setting(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def thresholds() -> Dict[str, float]:
    return {"volume_ratio": _setting("CLINLOOP_MONITOR_VOLUME_RATIO", 3.0),
            "min_volume": _setting("CLINLOOP_MONITOR_MIN_VOLUME", 10),
            "dismiss_rate": _setting("CLINLOOP_MONITOR_DISMISS_RATE", 0.5),
            "min_decisions": _setting("CLINLOOP_MONITOR_MIN_DECISIONS", 10)}


def acting() -> bool:
    """False in report-only mode, and always during the silent run (nothing reaches care to pause)."""
    from .pilot import silent_run
    if silent_run():
        return False
    return os.environ.get("CLINLOOP_MONITOR", "1").strip().lower() not in ("0", "false", "no", "off")


def measure(store, now: Optional[datetime] = None) -> Dict[str, Dict]:
    """Per rule: loops opened this week, the usual week, decisions and dismissals over 4 weeks."""
    now = now or utc_now()
    recent_start = now - timedelta(days=WINDOW_DAYS)
    baseline_start = recent_start - timedelta(days=BASELINE_DAYS)
    decisions_start = now - timedelta(days=BASELINE_DAYS)
    first = store.first_loop_opened()
    m: Dict[str, Dict] = defaultdict(lambda: {"opened_this_week": 0, "opened_baseline": 0,
                                              "decisions": 0, "dismissals": 0})
    for e in store.rule_activity(baseline_start.isoformat()):
        ts = datetime.fromisoformat(e["ts"])
        row = m[e["rule_id"]]
        if e["action"] == "loop_opened":
            if ts >= recent_start:
                row["opened_this_week"] += 1
            else:
                row["opened_baseline"] += 1
        elif ts >= decisions_start:
            row["decisions"] += 1
            row["dismissals"] += int(e["action"] == "defer" and e["reason"] in DISMISSAL_REASONS)
    out = {}
    for rid, row in m.items():
        weekly = row["opened_baseline"] / (BASELINE_DAYS / WINDOW_DAYS)
        has_history = rid in first and datetime.fromisoformat(first[rid]) <= baseline_start
        out[rid] = {**row, "usual_week": round(weekly, 1), "history_weeks_enough": has_history,
                    "dismissal_rate": round(row["dismissals"] / row["decisions"], 2) if row["decisions"] else None}
    return out


def tripped(metrics: Dict, limits: Dict[str, float]) -> Dict[str, Optional[str]]:
    """Which signal tripped, in words: {"volume": … or None, "dismissal": … or None}."""
    out: Dict[str, Optional[str]] = {"volume": None, "dismissal": None}
    if (metrics["history_weeks_enough"] and metrics["opened_this_week"] >= limits["min_volume"]
            and metrics["opened_this_week"] > limits["volume_ratio"] * max(metrics["usual_week"], 1.0)):
        out["volume"] = f"{metrics['opened_this_week']} loops this week against a usual {metrics['usual_week']}"
    if metrics["decisions"] >= limits["min_decisions"] and metrics["dismissal_rate"] is not None \
            and metrics["dismissal_rate"] >= limits["dismiss_rate"]:
        out["dismissal"] = (f"{metrics['dismissals']} of {metrics['decisions']} decisions dismissed the alert "
                            f"as not indicated or duplicate")
    return out


def decide(severity: str, signals: Dict[str, Optional[str]], current: Optional[str]) -> Optional[str]:
    """The new state for a rule, or None to leave it. Pause only on dismissals and never a critical rule;
    a flagged rule can still be paused when dismissals follow."""
    if not any(signals.values()) or current == "paused":
        return None
    new = "paused" if signals["dismissal"] and severity != "critical" else "flagged"
    return None if new == current else new


def run(store, now: Optional[datetime] = None, actor: str = "rule-monitor") -> Dict:
    """Measure every rule; pause or flag the ones that tripped (when acting). Returns the report."""
    now = now or utc_now()
    limits = thresholds()
    severity = {r.rule_id: r.severity.value for r in OBLIGATION_RULES}
    metrics = measure(store, now)
    current = store.monitor_state()
    changes = []
    for rid, row in sorted(metrics.items()):
        signals = tripped(row, limits)
        state = current.get(rid, {})
        if state.get("cooldown_until") and state["cooldown_until"] > now.isoformat():
            continue
        new = decide(severity.get(rid, ""), signals, state.get("state"))
        if new is None:
            continue
        reasons = [r for r in signals.values() if r]
        changes.append({"rule_id": rid, "state": new, "reasons": reasons})
        if acting():
            store.set_monitor_state(rid, new, "; ".join(reasons), row, actor)
    return {"as_of": now.isoformat(), "acting": acting(), "thresholds": limits, "rules": metrics, "changes": changes,
            "states": store.monitor_state()}


def resume(store, rule_id: str, actor: str, role: str, note: str, now: Optional[datetime] = None) -> Dict:
    """An administrator puts a paused or flagged rule back in service after review."""
    from .loop_store import WorkflowError
    now = now or utc_now()
    if len(note.strip()) < 5:
        raise WorkflowError("Say what was reviewed before the rule goes back in service (at least 5 characters)")
    state = store.monitor_state().get(rule_id)
    if not state or state["state"] == "ok":
        raise WorkflowError(f"Rule {rule_id} is not paused or flagged")
    return store.set_monitor_state(rule_id, "ok", f"resumed after review (was {state['state']})", state["metrics"],
                                   actor, role=role, cooldown_until=(now + timedelta(days=COOLDOWN_DAYS)).isoformat(),
                                   note=note.strip())
