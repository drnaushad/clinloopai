"""
pilot.py — The silent run (Stage 2 of docs/STUDY_PROTOCOL.md) and its weekly review

During the silent run ClinLoop reads the live record and keeps its loops, but nothing reaches
clinical care: no worklist loops, no EHR cards, no escalation, no patient messages, and the rule
monitor only reports. Usual care is unchanged. A review team, blinded to each other's answers,
checks a random sample of the loops ClinLoop marked overdue each week and answers the protocol's
three questions:

  (a) was the loop truly open?             yes / no / unclear
  (b) would usual care have caught it?     yes / no / unknown
  (c) is it clinically important?          yes / no / unclear

A truly open loop that is urgent cannot be filed without a safety referral: who in the treating team
was told, when and how (the site's normal safety-reporting route). Patients are not left at risk for
the sake of the study.

The metrics are the protocol's: PPV of "overdue", true clinically important open loops per 1,000
patients per month beyond usual care, alerts per clinician per day, delay in usual care and feed
uptime, set against the Stage 2 → 3 go / no-go criteria. A de-identified export (no patient ids,
no free text, reviewer names hashed) goes to the statistician.

Configuration (environment):
  CLINLOOP_SILENT_RUN=1            turn the silent run on
  CLINLOOP_PILOT_REVIEWERS         user names on the review team (comma separated); empty: any
                                   clinician or administrator
  CLINLOOP_PILOT_REVIEWS_PER_LOOP  reviewers per sampled loop (default 2, for agreement)
  CLINLOOP_PILOT_CLINICIANS        clinicians who would receive the alerts (for the burden measure)
"""

import csv
import hashlib
import io
import math
import os
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .auth import ROLE_RANK, User, require_role
from .clinical_ontology import OBLIGATION_RULES
from .loop_store import ACTIVE_ENGINE_STATUSES, WorkflowError
from .safety_clock import utc_now

SEED = 42
ANSWERS_OPEN = ("yes", "no", "unclear")
ANSWERS_USUAL = ("yes", "no", "unknown")
# Stage 2 → 3 criteria (docs/STUDY_PROTOCOL.md §7)
MIN_TRUE_IMPORTANT_PER_1000_PER_MONTH = 1.0
MAX_ALERTS_PER_CLINICIAN_PER_DAY = 5.0
MIN_FEED_UPTIME = 0.99
MIN_REVIEWED_FOR_DECISION = 30
MIN_OBSERVATION_DAYS = 28        # rates per month and per day need at least four weeks of the run


def silent_run() -> bool:
    return os.environ.get("CLINLOOP_SILENT_RUN", "").strip().lower() in ("1", "true", "yes", "on")


def reviewers() -> List[str]:
    return [x.strip() for x in os.environ.get("CLINLOOP_PILOT_REVIEWERS", "").split(",") if x.strip()]


def is_reviewer(user: User) -> bool:
    if user.role == "admin":
        return True
    named = reviewers()
    return (user.name in named) if named else ROLE_RANK[user.role] >= ROLE_RANK["clinician"]


def may_see_loops(user: User) -> bool:
    """During the silent run only the review team (and administrators) see ClinLoop's loops."""
    return not silent_run() or is_reviewer(user)


def reviews_per_loop() -> int:
    try:
        return max(1, int(os.environ.get("CLINLOOP_PILOT_REVIEWS_PER_LOOP", "2")))
    except ValueError:
        return 2


def iso_week(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


# ── sampling ─────────────────────────────────────────────────────────────────

def overdue_candidates(store, now: datetime) -> List[Dict]:
    """Loops ClinLoop marks overdue: action still needed and the deadline passed."""
    now_iso = now.isoformat()
    return [l for l in store.worklist(include_inactive=True, now=now)
            if l["engine_status"] in ACTIVE_ENGINE_STATUSES and l["engine_status"] != "delayed"
            and l["workflow_state"] != "superseded" and l["deadline"] and l["deadline"] <= now_iso]


def draw_sample(store, size: Optional[int], actor: str, now: Optional[datetime] = None) -> Dict:
    """This week's random sample of overdue loops not sampled before (size None: all of them).
    The draw is reproducible: the same week and pool give the same sample."""
    now = now or utc_now()
    week = iso_week(now)
    already = {s["loop_key"] for s in store.pilot_samples()}
    eligible = sorted((l for l in overdue_candidates(store, now) if l["loop_key"] not in already),
                      key=lambda l: l["loop_key"])
    pool = eligible if size is None or size >= len(eligible) else random.Random(f"{SEED}:{week}").sample(eligible, size)
    rows = [{"loop_key": l["loop_key"], "week": week, "week_candidates": len(eligible), "rule_id": l["rule_id"]}
            for l in pool]
    store.add_pilot_samples(rows, actor)
    return {"week": week, "candidates": len(eligible), "sampled": len(rows)}


# ── review ───────────────────────────────────────────────────────────────────

def review(store, user: User, loop_key: str, truly_open: str, usual_care: str, important: str,
           urgent: bool, safety_referral: str = "", note: str = "") -> Dict:
    from .governance import ruleset_version
    if truly_open not in ANSWERS_OPEN or important not in ANSWERS_OPEN or usual_care not in ANSWERS_USUAL:
        raise WorkflowError("Answer each question with one of the listed options")
    if urgent and truly_open != "yes":
        raise WorkflowError("Only a loop that is truly open can be marked urgent")
    if urgent and len(safety_referral.strip()) < 10:
        raise WorkflowError("An urgent open loop needs a safety referral: who in the treating team was told, "
                            "when and how (at least 10 characters)")
    return store.add_pilot_review({"loop_key": loop_key, "truly_open": truly_open, "usual_care": usual_care,
                                   "important": important, "urgent": urgent, "safety_referral": safety_referral.strip(),
                                   "note": note.strip(), "ruleset_version": ruleset_version()}, user.name, user.role)


def queue(store, user: User) -> List[Dict]:
    """Sampled loops this person has not reviewed and that still need reviewers. Other reviewers'
    answers are not shown (blinding)."""
    need = reviews_per_loop()
    by_loop = defaultdict(list)
    for r in store.pilot_reviews():
        by_loop[r["loop_key"]].append(r["reviewer"])
    out = []
    for s in store.pilot_samples():
        done = by_loop.get(s["loop_key"], [])
        if user.name in done or len(done) >= need:
            continue
        try:
            loop = store.get(s["loop_key"])
        except KeyError:
            continue
        out.append({"sample": s, "reviews_so_far": len(done), "reviews_needed": need, "loop": loop})
    return out


# ── metrics ──────────────────────────────────────────────────────────────────

def _wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(p, 3), round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def _verdicts(store) -> Dict[str, Dict]:
    """Per sampled loop: the agreed answers, or 'discordant' when reviewers disagree on question (a)."""
    by_loop = defaultdict(list)
    for r in store.pilot_reviews():
        by_loop[r["loop_key"]].append(r)
    out = {}
    for key, rows in by_loop.items():
        opens = {r["truly_open"] for r in rows}
        out[key] = {
            "truly_open": opens.pop() if len(opens) == 1 else "discordant",
            "important": "yes" if any(r["important"] == "yes" for r in rows) else
                         ("no" if all(r["important"] == "no" for r in rows) else "unclear"),
            "usual_care": "yes" if any(r["usual_care"] == "yes" for r in rows) else
                          ("no" if all(r["usual_care"] == "no" for r in rows) else "unknown"),
            "reviews": len(rows), "urgent": any(r["urgent"] for r in rows)}
    return out


def _agreement(store) -> Dict[str, Optional[float]]:
    """Agreement between the first two reviewers on question (a): observed share and Cohen's kappa.
    Kappa is low when nearly every answer is the same (the prevalence paradox), so both are shown."""
    by_loop = defaultdict(list)
    for r in store.pilot_reviews():
        by_loop[r["loop_key"]].append(r["truly_open"])
    pairs = [(v[0], v[1]) for v in by_loop.values() if len(v) >= 2]
    if not pairs:
        return {"observed": None, "kappa": None, "pairs": 0}
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in ANSWERS_OPEN)
    kappa = round((po - pe) / (1 - pe), 3) if pe < 1 and n >= 2 else None
    return {"observed": round(po, 3), "kappa": kappa, "pairs": n}


def _feed_uptime(store, start: datetime, now: datetime) -> Optional[float]:
    """Share of the period covered by successful data-feed runs: each success covers the time up to
    the next expected run (two sync intervals at most)."""
    interval = timedelta(minutes=float(os.environ.get("CLINLOOP_FHIR_SYNC_MINUTES", "15")))
    with store._lock:
        rows = store._db.execute("SELECT ts FROM ingest_runs WHERE ok=1 AND ts>=? ORDER BY ts",
                                 (start.isoformat(),)).fetchall()
    times = [datetime.fromisoformat(r["ts"]) for r in rows]
    span = (now - start).total_seconds()
    if not times or span <= 0:
        return None
    covered = 0.0
    for i, t in enumerate(times):
        end = times[i + 1] if i + 1 < len(times) else now
        covered += min((end - t).total_seconds(), 2 * interval.total_seconds())
    return round(min(1.0, covered / span), 4)


def metrics(store, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or utc_now()
    samples = store.pilot_samples()
    verdicts = _verdicts(store)
    family = {r.rule_id: r.clinical_domain for r in OBLIGATION_RULES}
    # The observation period is the silent run itself: from the first patient the engine evaluated
    with store._lock:
        first = store._db.execute("SELECT MIN(first_seen) FROM monitored_patients").fetchone()[0]
    start = datetime.fromisoformat(first) if first else None
    days_observed = (now - start).total_seconds() / 86400 if start else 0.0
    long_enough = days_observed >= MIN_OBSERVATION_DAYS
    months = days_observed / 30.4 if long_enough else None

    reviewed = [k for k, v in verdicts.items() if v["reviews"] >= reviews_per_loop()]
    decided = [k for k in reviewed if verdicts[k]["truly_open"] in ("yes", "no")]
    yes = [k for k in decided if verdicts[k]["truly_open"] == "yes"]
    ppv, lo, hi = _wilson(len(yes), len(decided))
    rule_of = {s["loop_key"]: s["rule_id"] for s in samples}
    per_family: Dict[str, Dict] = defaultdict(lambda: {"reviewed": 0, "truly_open": 0})
    for k in decided:
        f = family.get(rule_of.get(k), "other")
        per_family[f]["reviewed"] += 1
        per_family[f]["truly_open"] += int(verdicts[k]["truly_open"] == "yes")
    for f, row in per_family.items():
        row["ppv"], row["ci_low"], row["ci_high"] = _wilson(row["truly_open"], row["reviewed"])

    # Weighted estimate of true, clinically important open loops that usual care would not have caught
    by_week = defaultdict(lambda: {"candidates": 0, "decided": 0, "hits": 0})
    for s in samples:
        w = by_week[s["week"]]
        w["candidates"] = max(w["candidates"], s["week_candidates"])
        v = verdicts.get(s["loop_key"])
        if v and s["loop_key"] in decided:
            w["decided"] += 1
            w["hits"] += int(v["truly_open"] == "yes" and v["important"] == "yes" and v["usual_care"] == "no")
    estimated = sum(w["candidates"] * w["hits"] / w["decided"] for w in by_week.values() if w["decided"])
    patients = store.monitored_patient_count()
    per_1000_month = round(estimated / (patients / 1000) / months, 2) if patients and months else None

    # Usual care, observed: sampled loops the record later shows closed without ClinLoop
    closed_later = 0
    for k in yes:
        try:
            closed_later += int(store.get(k)["workflow_state"] == "resolved_by_engine")
        except KeyError:
            pass

    # Alert burden: loops that would have reached the worklist, per clinician per day. Only loops whose
    # trigger happened during the run count: the first sync's back-fill of history is not daily load.
    clinicians = int(os.environ.get("CLINLOOP_PILOT_CLINICIANS", "0") or 0)
    new_loops = [l for l in store.worklist(include_inactive=True, now=now)
                 if start and l["trigger_time"] and l["trigger_time"] >= start.isoformat()
                 and l["workflow_state"] != "superseded"]
    burden = round(len(new_loops) / days_observed / clinicians, 2) if clinicians and long_enough else None

    # Delay in usual care: loops completed late, days past the deadline (resolution seen at the next sync)
    delays = []
    for a in store.audit_trail(limit=100000):
        if a["action"] == "loop_resolved_by_record" and a["detail"].get("on_time") is False and a["loop_key"]:
            try:
                deadline = store.get(a["loop_key"])["deadline"]
            except KeyError:
                continue
            if deadline:
                delays.append((datetime.fromisoformat(a["ts"]) - datetime.fromisoformat(deadline)).total_seconds() / 86400)
    uptime = _feed_uptime(store, start, now) if start else None

    enough = len(decided) >= MIN_REVIEWED_FOR_DECISION and long_enough

    def verdict(value, ok):
        if value is None or not enough:
            return "insufficient data"
        return "pass" if ok(value) else "fail"
    criteria = [
        {"criterion": f"≥ {MIN_TRUE_IMPORTANT_PER_1000_PER_MONTH:g} true clinically important open loop per 1,000 "
                      "patients per month beyond usual care", "value": per_1000_month,
         "result": verdict(per_1000_month, lambda v: v >= MIN_TRUE_IMPORTANT_PER_1000_PER_MONTH)},
        {"criterion": f"Alert burden ≤ {MAX_ALERTS_PER_CLINICIAN_PER_DAY:g} per clinician per day", "value": burden,
         "result": verdict(burden, lambda v: v <= MAX_ALERTS_PER_CLINICIAN_PER_DAY)},
        {"criterion": f"Data-feed uptime ≥ {MIN_FEED_UPTIME:.0%}", "value": uptime, "unit": "share",
         "result": verdict(uptime, lambda v: v >= MIN_FEED_UPTIME)},
        {"criterion": "Alert burden accepted by the clinical leads", "value": None,
         "result": "decided by the clinical leads"},
    ]
    return {
        "as_of": now.isoformat(), "silent_run": silent_run(), "since": start.isoformat() if start else None,
        "days_observed": round(days_observed, 1), "minimum_days": MIN_OBSERVATION_DAYS,
        "monitored_patients": patients, "sampled": len(samples), "reviewed": len(reviewed),
        "discordant": sum(1 for k in reviewed if verdicts[k]["truly_open"] == "discordant"),
        "ppv": {"value": ppv, "ci_low": lo, "ci_high": hi, "n": len(decided)},
        "ppv_by_family": dict(per_family), "agreement": _agreement(store),
        "true_important_beyond_usual_care_per_1000_per_month": per_1000_month,
        "truly_open_closed_later_by_usual_care": {"count": closed_later, "of": len(yes)},
        "alerts_per_clinician_per_day": burden, "clinicians": clinicians or None,
        "usual_care_delay_days": {"median": round(statistics.median(delays), 1) if delays else None, "n": len(delays)},
        "feed_uptime": uptime, "urgent_safety_referrals": sum(1 for v in verdicts.values() if v["urgent"]),
        "go_no_go": criteria, "minimum_reviewed_for_decision": MIN_REVIEWED_FOR_DECISION,
    }


def export_csv(store) -> str:
    """One row per review, de-identified: no patient ids, no free text; loop keys and reviewer names
    replaced by short hashes (salted with the signing key when one is set)."""
    salt = os.environ.get("CLINLOOP_SIGNING_KEY", "")
    h = lambda v: hashlib.sha256(f"{salt}|{v}".encode()).hexdigest()[:12]
    family = {r.rule_id: (r.clinical_domain, r.severity.value) for r in OBLIGATION_RULES}
    week = {s["loop_key"]: (s["week"], s["rule_id"]) for s in store.pilot_samples()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["loop", "rule_id", "family", "severity", "week", "reviewer", "truly_open", "usual_care",
                "important", "urgent", "safety_referral_made", "ruleset_version", "reviewed_at"])
    for r in store.pilot_reviews():
        wk, rule = week.get(r["loop_key"], ("", ""))
        fam, sev = family.get(rule, ("", ""))
        w.writerow([h(r["loop_key"]), rule, fam, sev, wk, h(r["reviewer"]), r["truly_open"], r["usual_care"],
                    r["important"], r["urgent"], int(bool(r["safety_referral"])), r["ruleset_version"], r["reviewed_at"]])
    return buf.getvalue()


# ── API ──────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/pilot", tags=["Silent run (pilot)"])


def _store():
    from .clinical_api import get_store
    return get_store()


def require_reviewer(user: User = Depends(require_role("viewer"))) -> User:
    if not is_reviewer(user):
        raise HTTPException(403, "Only the pilot review team can do this")
    return user


class SampleRequest(BaseModel):
    size: Optional[int] = Field(20, ge=1, le=5000, description="Loops to sample this week; null for all (100% review)")


class ReviewRequest(BaseModel):
    loop_key: str = Field(..., max_length=500)
    truly_open: str = Field(..., description="yes | no | unclear")
    usual_care: str = Field(..., description="Would usual care have caught it: yes | no | unknown")
    important: str = Field(..., description="Clinically important: yes | no | unclear")
    urgent: bool = False
    safety_referral: str = Field("", max_length=1000)
    note: str = Field("", max_length=2000)


@router.get("/status")
def status(user: User = Depends(require_role("viewer"))):
    store = _store()
    return {"silent_run": silent_run(), "you_review": is_reviewer(user), "reviews_per_loop": reviews_per_loop(),
            "sampled": len(store.pilot_samples()), "monitored_patients": store.monitored_patient_count()}


@router.post("/sample")
def sample(req: SampleRequest, user: User = Depends(require_role("admin"))):
    return draw_sample(_store(), req.size, user.name)


@router.get("/queue")
def my_queue(user: User = Depends(require_reviewer)):
    store = _store()
    items = queue(store, user)
    store.record_access(user.name, user.role, "view_pilot_queue", [i["loop"]["patient_id"] for i in items])
    return {"items": items}


@router.post("/reviews")
def add_review(req: ReviewRequest, user: User = Depends(require_reviewer)):
    try:
        return review(_store(), user, req.loop_key, req.truly_open, req.usual_care, req.important, req.urgent,
                      req.safety_referral, req.note)
    except WorkflowError as e:
        raise HTTPException(409, str(e))


@router.get("/metrics")
def pilot_metrics(user: User = Depends(require_reviewer)):
    return metrics(_store())


@router.get("/safety-referrals")
def safety_referrals(user: User = Depends(require_reviewer)):
    store = _store()
    rows = [r for r in store.pilot_reviews() if r["safety_referral"]]
    store.record_access(user.name, user.role, "view_safety_referrals", [r["loop_key"].split("|")[0] for r in rows])
    return {"referrals": [{k: r[k] for k in ("loop_key", "reviewer", "safety_referral", "reviewed_at")} for r in rows]}


@router.get("/export.csv")
def export(user: User = Depends(require_role("admin"))):
    return Response(export_csv(_store()), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=clinloop_silent_run_reviews.csv"})
