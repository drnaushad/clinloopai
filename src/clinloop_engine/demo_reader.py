"""
demo_reader.py — Public demo: rules and MedGemma 27B side by side on fixed synthetic reports

Only in demo mode (CLINLOOP_DEMO=1). A visitor picks one of the server's synthetic reports
(data/demo_reports.json); free text and uploads are never accepted, so nothing real can be sent.

For each report the page shows:
  * what the rules open (the real pipeline: bundle_to_events → ClinLoopDetector);
  * MedGemma 27B's saved reading, made with the production prompt and labelled with model, digest,
    prompt version and date (scripts/build_demo_reports.py);
  * optionally a live re-read on this server's GPU, bounded so the public can never starve the GPU:
    one job at a time, a short queue (CLINLOOP_DEMO_QUEUE, default 2 waiting), and a per-visitor quota
    (CLINLOOP_DEMO_LIVE_PER_HOUR, default 3). Over the limit the answer is "busy", never a substitute.

Every model item has passed the second reader's own checks (exact quote, fixed category, not-actionable
filter). Model items are suggestions for a clinician, never decisions.
"""
import hashlib
import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CATALOG = os.path.join(_ROOT, "data", "demo_reports.json")
REPORT_RULES = {"R003", "R009", "R018", "R019", "R020", "R030", "R031", "R032", "R033", "R034", "R035", "R036",
                "R037", "R038", "R039", "R040", "R041", "R042", "R043", "R044", "R045", "R046"}

_catalog: Optional[Dict[str, Any]] = None
_slot = threading.Semaphore(1)            # one live model job at a time
_waiting = 0
_lock = threading.Lock()
_recent: Dict[str, deque] = defaultdict(deque)


def catalog() -> Dict[str, Any]:
    global _catalog
    if _catalog is None:
        with open(CATALOG, encoding="utf-8") as f:
            _catalog = json.load(f)
    return _catalog


def case(case_id: str) -> Optional[Dict[str, Any]]:
    return next((c for c in catalog()["cases"] if c["id"] == case_id), None)


_SMOKING = {"current": ("77176002", "Current smoker"), "former": ("8517006", "Former smoker"),
            "never": ("266919005", "Never smoked")}


def _context(pid: str, when: datetime, p: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The case's patient context as FHIR, as the evaluation harness builds it (run_eval.resources):
    smoking status, known cancer and immunocompromise change which guideline applies."""
    out: List[Dict[str, Any]] = []
    sm = _SMOKING.get(p.get("smoking"))
    if sm:
        out.append({"resourceType": "Observation", "id": f"{pid}-smk", "status": "final",
                    "subject": {"reference": f"Patient/{pid}"},
                    "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2"}], "text": "Tobacco smoking status"},
                    "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": sm[0]}], "text": sm[1]},
                    "effectiveDateTime": (when - timedelta(days=30)).date().isoformat()})
    for flag, code, text, suffix in (("known_malignancy", "C50.9", "Malignant neoplasm", "ca"),
                                     ("immunocompromised", "D84.9", "Immunodeficiency", "ic")):
        if p.get(flag):
            out.append({"resourceType": "Condition", "id": f"{pid}-{suffix}", "subject": {"reference": f"Patient/{pid}"},
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code}], "text": text},
                        "recordedDate": (when - timedelta(days=400)).date().isoformat()})
    return out


def rules_for(c: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The rules' obligations for one report, through the real pipeline."""
    from .fhir_ingest import bundle_to_events
    from .loop_detector import ClinLoopDetector
    pid, when = "DEMO-" + c["id"], datetime.fromisoformat(c["date"])
    p = c.get("patient") or {}
    res = [{"resourceType": "Patient", "id": pid, "gender": p.get("sex") or "unknown",
            "birthDate": (when - timedelta(days=int(p.get("age") or 60) * 365.25 + 100)).date().isoformat()},
           {"resourceType": "DiagnosticReport", "id": pid + "-rep", "status": "final",
            "category": [{"coding": [{"code": "RAD" if c.get("report_type", "radiology") == "radiology" else "PAT"}]}],
            "code": {"text": c.get("title") or ""}, "subject": {"reference": f"Patient/{pid}"},
            "effectiveDateTime": c["date"] + "T09:00:00Z", "conclusion": c["text"]}]
    res += _context(pid, when, p)
    events, _ = bundle_to_events(res)
    dets = ClinLoopDetector(evaluation_time=when + timedelta(days=1)).process_patient("demo", pid, events.get(pid, []))
    return [{"rule_id": d.rule_id, "rule": d.rule_name, "deadline_days": round(
                (datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds() / 86400, 1),
             "basis": list(d.basis)[:3], "status": d.loop_status}
            for d in dets if d.rule_id in REPORT_RULES]


def compare(rules: List[Dict[str, Any]], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each model item marked as also tracked by a rule, or model-only (needs a clinician)."""
    from .second_reader import uncovered
    opened = {r["rule_id"] for r in rules}
    only = {id(i) for i in uncovered(items, opened)}
    return [dict(i, agreement="model only: needs clinician review" if id(i) in only else "also tracked by a rule")
            for i in items]


def _visitor(key: str) -> str:
    return hashlib.sha256(("clinloop-demo|" + (key or "")).encode()).hexdigest()[:16]   # no IP is kept


def quota_left(key: str, now: Optional[float] = None) -> int:
    now = now or time.time()
    per_hour = int(os.environ.get("CLINLOOP_DEMO_LIVE_PER_HOUR", "3"))
    q = _recent[_visitor(key)]
    while q and now - q[0] > 3600:
        q.popleft()
    return max(0, per_hour - len(q))


class Busy(Exception):
    pass


def live_read(c: Dict[str, Any], visitor_key: str, model=None) -> Dict[str, Any]:
    """Re-read one catalogue report with the configured second-reader model, within the public limits."""
    global _waiting
    from .local_llm_engine import get_second_reader_model
    from .second_reader import local_model, read_report
    if quota_left(visitor_key) <= 0:
        raise Busy("Live re-read limit reached for now; the saved MedGemma reading is shown instead.")
    with _lock:
        if _waiting >= int(os.environ.get("CLINLOOP_DEMO_QUEUE", "2")):
            raise Busy("The model is busy with other visitors. Please try again in a minute.")
        _waiting += 1
    try:
        if not _slot.acquire(timeout=90):
            raise Busy("The model is busy with other visitors. Please try again in a minute.")
    finally:
        with _lock:
            _waiting -= 1
    try:
        _recent[_visitor(visitor_key)].append(time.time())
        name = None
        if model is None:
            name = get_second_reader_model()
            model = local_model()
        if model is None:
            return {"available": False, "reason": "The configured second-reader model is not available on this server."}
        t0 = time.time()
        out = read_report(c["text"], model)
        out["seconds"] = round(time.time() - t0, 1)
        out["model"] = out.get("model") or name
        out["read_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return out
    finally:
        _slot.release()
