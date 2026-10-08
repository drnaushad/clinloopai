"""
loop_store.py — Persistent loop registry, clinical workflow and audit log

The detection engine is stateless: it re-derives every loop from the record
on each run. Clinical work is not stateless. This module remembers, per
loop, who owns it, what was done about it and why, and escalates loops
nobody is acting on.

Workflow states:
    new → acknowledged → closed_by_clinician
        ↘ deferred (coded reason, optional until-date; resurfaces when it expires)
    any active state → resolved_by_engine (the record now shows the follow-up)

Principles:
  * Closure needs evidence. A clinician closing a loop must say what closed
    it; a click is not closure.
  * Deferral needs a coded reason, so clinical judgment is documented and
    the reasons can refine the rules.
  * Every action is written to an append-only audit log whose entries are
    SHA-256 hash-chained, so tampering with history is detectable.

Uses only the Python standard library (sqlite3).
"""

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .clinical_ontology import LoopStatus
from .safety_clock import utc_now

# Engine statuses that count as a missed loop for the quality measure
ACTIVE_ENGINE_STATUSES = (LoopStatus.OPEN.value, LoopStatus.DELAYED.value, LoopStatus.ABSTAIN.value)
# Engine statuses that need someone to act. A DELAYED loop's follow-up did
# happen, only late: it counts as a miss, but it is not a task any more.
ACTION_NEEDED_STATUSES = (LoopStatus.OPEN.value, LoopStatus.ABSTAIN.value)
FOLLOWUP_FOUND_STATUSES = (LoopStatus.CLOSED.value, LoopStatus.DELAYED.value)
ACTIVE_WORKFLOW_STATES = ("new", "acknowledged")

DEFER_REASONS = {
    "patient_declined": "Patient informed and declined (informed refusal documented)",
    "completed_elsewhere": "Follow-up completed at another institution",
    "not_clinically_indicated": "Clinician judges follow-up not indicated",
    "hospice_or_comfort_care": "Patient in hospice or comfort-focused care",
    "patient_deceased": "Patient deceased",
    "duplicate": "Duplicate of another loop",
    "other": "Other (note required)",
}
REASONS_REQUIRING_NOTE = {"not_clinically_indicated", "other"}

# Escalation chain. A loop past its deadline that nobody has acknowledged
# climbs one level each time its grace period passes again.
ESCALATION_CHAIN = ["owner", "department_lead", "patient_safety_officer"]
ESCALATION_GRACE = {"critical": timedelta(hours=1), "high": timedelta(hours=24),
                    "moderate": timedelta(hours=72), "low": timedelta(days=7)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS loops (
    loop_key TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_name TEXT,
    severity TEXT,
    trigger_event TEXT,
    trigger_time TEXT,
    deadline TEXT,
    engine_status TEXT,
    workflow_state TEXT NOT NULL DEFAULT 'new',
    risk_score REAL,
    clock_state TEXT,
    missing_step TEXT,
    recommended_action TEXT,
    explanation TEXT,
    evidence_chain TEXT,
    owner TEXT NOT NULL DEFAULT 'unassigned',
    escalation_level INTEGER NOT NULL DEFAULT 0,
    last_escalated_at TEXT,
    defer_reason TEXT,
    defer_note TEXT,
    defer_until TEXT,
    closure_evidence TEXT,
    strata TEXT,
    first_seen TEXT,
    last_seen TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_loops_patient ON loops(patient_id);
CREATE INDEX IF NOT EXISTS idx_loops_owner ON loops(owner);
CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    actor TEXT,
    ok INTEGER NOT NULL,
    patients INTEGER DEFAULT 0,
    events INTEGER DEFAULT 0,
    warnings INTEGER DEFAULT 0,
    error TEXT
);
CREATE TABLE IF NOT EXISTS outreach_messages (
    id TEXT PRIMARY KEY,
    loop_key TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    language TEXT,
    channel TEXT,
    draft_text TEXT,
    final_text TEXT,
    status TEXT NOT NULL,            -- draft | sent | rejected | failed
    safety_flags TEXT,
    drafted_by TEXT,
    drafted_at TEXT,
    decided_by TEXT,
    decided_at TEXT,
    provider TEXT,
    provider_ref TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_outreach_loop ON outreach_messages(loop_key);
CREATE TABLE IF NOT EXISTS sync_state (
    source TEXT PRIMARY KEY,
    cursor TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS rule_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL,
    rule_hash TEXT NOT NULL,          -- fingerprint of the rule definition reviewed
    decision TEXT NOT NULL,           -- approve | reject | request_changes
    reviewer TEXT NOT NULL,
    role TEXT,
    specialty TEXT,
    note TEXT,
    decided_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rule_reviews_rule ON rule_reviews(rule_id);
CREATE TABLE IF NOT EXISTS config_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,               -- e.g. critical_findings
    content_hash TEXT NOT NULL,
    approver TEXT NOT NULL,
    role TEXT,
    title TEXT,
    note TEXT,
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patient_snapshots (
    patient_id TEXT PRIMARY KEY,      -- resources from the last manual FHIR upload (no FHIR server configured)
    resources TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS external_resources (
    id TEXT PRIMARY KEY,              -- FHIR resource id
    patient_id TEXT NOT NULL,
    kind TEXT NOT NULL,               -- outside-report | dicom-study | imaging-ai
    resource TEXT NOT NULL,           -- FHIR JSON (never the uploaded file or pixel data)
    source_sha256 TEXT,               -- hash of the uploaded file, for traceability
    summary TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_external_patient ON external_resources(patient_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT,
    action TEXT NOT NULL,
    loop_key TEXT,
    detail TEXT,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
"""


class WorkflowError(ValueError):
    """Raised when a workflow action is not allowed in the loop's current state."""


def loop_key(patient_id: str, rule_id: str, trigger_event_id: str) -> str:
    return f"{patient_id}|{rule_id}|{trigger_event_id}"


class LoopStore:
    def __init__(self, path: str = ":memory:"):
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # ── audit ────────────────────────────────────────────────────────────────
    def _audit(self, actor: str, role: str, action: str, key: Optional[str], detail: Dict,
               at: Optional[datetime] = None) -> None:
        row = self._db.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "GENESIS"
        ts = (at or utc_now()).isoformat()
        body = json.dumps({"ts": ts, "actor": actor, "role": role, "action": action,
                           "loop_key": key, "detail": detail, "prev": prev},
                          sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self._db.execute(
            "INSERT INTO audit_log (ts, actor, role, action, loop_key, detail, prev_hash, hash) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ts, actor, role, action, key, json.dumps(detail, ensure_ascii=False, default=str), prev, digest))

    def audit_trail(self, key: Optional[str] = None, limit: int = 200) -> List[Dict]:
        with self._lock:
            if key:
                rows = self._db.execute("SELECT * FROM audit_log WHERE loop_key=? ORDER BY id", (key,))
            else:
                rows = self._db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
            return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]

    def verify_audit_chain(self) -> bool:
        """Recompute every hash; False if any entry was altered, removed or reordered."""
        with self._lock:
            prev = "GENESIS"
            for r in self._db.execute("SELECT * FROM audit_log ORDER BY id"):
                body = json.dumps({"ts": r["ts"], "actor": r["actor"], "role": r["role"],
                                   "action": r["action"], "loop_key": r["loop_key"],
                                   "detail": json.loads(r["detail"] or "{}"), "prev": prev},
                                  sort_keys=True, ensure_ascii=False, default=str)
                if r["prev_hash"] != prev or hashlib.sha256(body.encode("utf-8")).hexdigest() != r["hash"]:
                    return False
                prev = r["hash"]
            return True

    # ── governance: rule sign-off and configuration approval ─────────────────
    REVIEW_DECISIONS = ("approve", "reject", "request_changes")

    def add_rule_review(self, rule_id: str, rule_hash: str, decision: str, reviewer: str, role: str,
                        specialty: str, note: str = "") -> Dict:
        if decision not in self.REVIEW_DECISIONS:
            raise WorkflowError(f"decision must be one of {', '.join(self.REVIEW_DECISIONS)}")
        if not specialty.strip():
            raise WorkflowError("The reviewer's specialty is required")
        if decision != "approve" and len(note.strip()) < 5:
            raise WorkflowError("Explain a rejection or change request (at least 5 characters)")
        now = utc_now().isoformat()
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO rule_reviews (rule_id, rule_hash, decision, reviewer, role, specialty, note, decided_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (rule_id, rule_hash, decision, reviewer, role, specialty.strip(), note, now))
            self._audit(reviewer, role, f"rule_review:{decision}", None,
                        {"rule_id": rule_id, "rule_hash": rule_hash, "specialty": specialty.strip(), "note": note})
            self._db.commit()
            return dict(self._db.execute("SELECT * FROM rule_reviews WHERE id=?", (cur.lastrowid,)).fetchone())

    def rule_reviews(self, rule_id: Optional[str] = None) -> List[Dict]:
        with self._lock:
            if rule_id:
                rows = self._db.execute("SELECT * FROM rule_reviews WHERE rule_id=? ORDER BY id", (rule_id,))
            else:
                rows = self._db.execute("SELECT * FROM rule_reviews ORDER BY id")
            return [dict(r) for r in rows]

    def add_config_approval(self, kind: str, content_hash: str, approver: str, role: str,
                            title: str, note: str = "") -> Dict:
        if not title.strip():
            raise WorkflowError("The approver's title (e.g. Chair of Radiology) is required")
        now = utc_now().isoformat()
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO config_approvals (kind, content_hash, approver, role, title, note, decided_at) "
                "VALUES (?,?,?,?,?,?,?)", (kind, content_hash, approver, role, title.strip(), note, now))
            self._audit(approver, role, f"config_approval:{kind}", None,
                        {"content_hash": content_hash, "title": title.strip(), "note": note})
            self._db.commit()
            return dict(self._db.execute("SELECT * FROM config_approvals WHERE id=?", (cur.lastrowid,)).fetchone())

    def latest_config_approval(self, kind: str) -> Optional[Dict]:
        with self._lock:
            r = self._db.execute("SELECT * FROM config_approvals WHERE kind=? ORDER BY id DESC LIMIT 1",
                                 (kind,)).fetchone()
        return dict(r) if r else None

    # ── resources added outside the FHIR feed (uploads, imaging AI) ──────────
    def add_external_resource(self, resource: Dict, kind: str, actor: str, role: str,
                              source_sha256: Optional[str] = None, summary: str = "") -> None:
        ref = str((resource.get("subject") or {}).get("reference", ""))
        if not ref.startswith("Patient/") or ref.count("/") != 1 or not resource.get("id"):
            raise WorkflowError("External resource needs an id and a subject of the form Patient/<id>")
        pid = ref.split("/", 1)[1]
        # Keyed by patient AND resource id: a vendor or file id reused for another patient never
        # overwrites or moves this patient's record
        row_id = f"{pid}|{resource['resourceType']}/{resource['id']}"
        now = utc_now().isoformat()
        with self._lock:
            self._db.execute(
                "INSERT INTO external_resources (id, patient_id, kind, resource, source_sha256, summary, created_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET resource=excluded.resource, "
                "summary=excluded.summary, created_by=excluded.created_by, created_at=excluded.created_at",
                (row_id, pid, kind, json.dumps(resource, ensure_ascii=False), source_sha256, summary, actor, now))
            self._audit(actor, role, f"external_resource:{kind}", None,
                        {"patient_id": pid, "resource": f"{resource.get('resourceType')}/{resource['id']}",
                         "source_sha256": source_sha256, "summary": summary})
            self._db.commit()

    def external_resources(self, patient_id: str) -> List[Dict]:
        with self._lock:
            rows = self._db.execute("SELECT resource FROM external_resources WHERE patient_id=? ORDER BY created_at",
                                    (patient_id,)).fetchall()
        return [json.loads(r["resource"]) for r in rows]

    def external_resource_list(self, patient_id: str) -> List[Dict]:
        with self._lock:
            rows = self._db.execute("SELECT id, patient_id, kind, source_sha256, summary, created_by, created_at "
                                    "FROM external_resources WHERE patient_id=? ORDER BY created_at DESC", (patient_id,))
            return [dict(r) for r in rows]

    def save_snapshot(self, patient_id: str, resources: List[Dict]) -> None:
        with self._lock:
            self._db.execute("INSERT INTO patient_snapshots (patient_id, resources, updated_at) VALUES (?,?,?) "
                             "ON CONFLICT(patient_id) DO UPDATE SET resources=excluded.resources, updated_at=excluded.updated_at",
                             (patient_id, json.dumps(resources, ensure_ascii=False), utc_now().isoformat()))
            self._db.commit()

    def snapshot(self, patient_id: str) -> List[Dict]:
        with self._lock:
            r = self._db.execute("SELECT resources FROM patient_snapshots WHERE patient_id=?", (patient_id,)).fetchone()
        return json.loads(r["resources"]) if r else []

    def external_patients(self) -> List[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT DISTINCT patient_id FROM external_resources")]

    # ── ingest detections ────────────────────────────────────────────────────
    def upsert_detections(self, detections: Iterable[Any],
                          strata: Optional[Dict[str, Dict]] = None, actor: str = "engine",
                          default_owner: str = "unassigned") -> Dict[str, int]:
        """
        Record the engine's view of each loop. A loop's key is
        patient | rule | trigger event, so it is stable across runs.
        `strata` maps patient_id → equity attributes (age group, insurance,
        language) used to stratify the open-loop rate.
        Returns counts of new / updated / resolved loops.
        """
        counts = {"new": 0, "updated": 0, "resolved_by_engine": 0}
        now = utc_now().isoformat()
        strata = strata or {}
        with self._lock:
            for d in detections:
                key = loop_key(d.patient_id, d.rule_id, d.trigger_event_id or d.trigger_time)
                existing = self._db.execute("SELECT * FROM loops WHERE loop_key=?", (key,)).fetchone()
                fields = {
                    "rule_name": d.rule_name, "severity": d.severity, "trigger_event": d.trigger_event,
                    "trigger_time": d.trigger_time, "deadline": d.deadline, "engine_status": d.loop_status,
                    "risk_score": d.risk_score, "clock_state": d.clock_state, "missing_step": d.missing_step,
                    "recommended_action": d.recommended_action,
                    "explanation": json.dumps(d.explanation, ensure_ascii=False),
                    "evidence_chain": json.dumps(d.evidence_chain, ensure_ascii=False),
                    "last_seen": now, "updated_at": now,
                }
                if existing is None:
                    workflow = "new" if d.loop_status in ACTION_NEEDED_STATUSES else "resolved_by_engine"
                    self._db.execute(
                        f"INSERT INTO loops (loop_key, patient_id, rule_id, workflow_state, owner, strata, first_seen, "
                        f"{', '.join(fields)}) VALUES (?,?,?,?,?,?,?,{', '.join('?' * len(fields))})",
                        (key, d.patient_id, d.rule_id, workflow, default_owner,
                         json.dumps(strata.get(d.patient_id, {}), ensure_ascii=False), now, *fields.values()))
                    if workflow == "new":
                        counts["new"] += 1
                        self._audit(actor, "system", "loop_opened", key,
                                    {"rule_id": d.rule_id, "engine_status": d.loop_status, "deadline": d.deadline})
                    continue

                if (d.loop_status in FOLLOWUP_FOUND_STATUSES
                        and existing["workflow_state"] in ACTIVE_WORKFLOW_STATES + ("deferred",)):
                    fields["workflow_state"] = "resolved_by_engine"
                    counts["resolved_by_engine"] += 1
                    self._audit(actor, "system", "loop_resolved_by_record", key,
                                {"evidence": "required follow-up found in the record",
                                 "on_time": d.loop_status == LoopStatus.CLOSED.value})
                elif (d.loop_status in ACTION_NEEDED_STATUSES
                      and existing["workflow_state"] == "resolved_by_engine"):
                    # The record changed (e.g. a follow-up was cancelled): reopen
                    fields["workflow_state"] = "new"
                    self._audit(actor, "system", "loop_reopened", key, {"engine_status": d.loop_status})
                counts["updated"] += 1
                self._db.execute(
                    f"UPDATE loops SET {', '.join(f'{k}=?' for k in fields)} WHERE loop_key=?",
                    (*fields.values(), key))
            self._db.commit()
        return counts

    # ── read ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _row(r: sqlite3.Row) -> Dict:
        d = dict(r)
        for k in ("explanation", "evidence_chain", "strata"):
            d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "strata" else {})
        d["escalated_to"] = ESCALATION_CHAIN[min(d["escalation_level"], len(ESCALATION_CHAIN) - 1)]
        return d

    def get(self, key: str) -> Dict:
        with self._lock:
            r = self._db.execute("SELECT * FROM loops WHERE loop_key=?", (key,)).fetchone()
        if r is None:
            raise KeyError(key)
        return self._row(r)

    def worklist(self, owner: Optional[str] = None, include_inactive: bool = False,
                 now: Optional[datetime] = None) -> List[Dict]:
        """
        Active loops, most dangerous first: severity, then overdue, then risk.
        Deferred loops come back once their until-date passes.
        """
        now_iso = (now or utc_now()).isoformat()
        with self._lock:
            rows = [self._row(r) for r in self._db.execute("SELECT * FROM loops")]
        out = []
        for r in rows:
            expired_deferral = (r["workflow_state"] == "deferred" and r["defer_until"]
                                and r["defer_until"] <= now_iso)
            active = r["workflow_state"] in ACTIVE_WORKFLOW_STATES or expired_deferral
            if not include_inactive and not active:
                continue
            if owner and r["owner"] != owner:
                continue
            r["deferral_expired"] = bool(expired_deferral)
            out.append(r)
        sev_rank = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
        out.sort(key=lambda r: (
            r["workflow_state"] not in ACTIVE_WORKFLOW_STATES and not r["deferral_expired"],
            sev_rank.get(r["severity"], 4),
            r["clock_state"] != "BLACK",
            -(r["risk_score"] or 0),
        ))
        return out

    # ── clinician actions ────────────────────────────────────────────────────
    def _transition(self, key: str, actor: str, role: str, action: str,
                    allowed_from: Iterable[str], updates: Dict, detail: Dict) -> Dict:
        with self._lock:
            loop = self.get(key)
            if loop["workflow_state"] not in allowed_from:
                raise WorkflowError(f"Cannot {action} a loop in state '{loop['workflow_state']}'")
            updates = {**updates, "updated_at": utc_now().isoformat()}
            self._db.execute(f"UPDATE loops SET {', '.join(f'{k}=?' for k in updates)} WHERE loop_key=?",
                             (*updates.values(), key))
            self._audit(actor, role, action, key, detail)
            self._db.commit()
            return self.get(key)

    def acknowledge(self, key: str, actor: str, role: str = "clinician") -> Dict:
        return self._transition(key, actor, role, "acknowledge", ("new", "deferred"),
                                {"workflow_state": "acknowledged"}, {})

    def assign(self, key: str, owner: str, actor: str, role: str = "admin") -> Dict:
        return self._transition(key, actor, role, "assign", ACTIVE_WORKFLOW_STATES + ("deferred",),
                                {"owner": owner, "escalation_level": 0}, {"owner": owner})

    def defer(self, key: str, actor: str, reason_code: str, note: str = "",
              until: Optional[str] = None, role: str = "clinician") -> Dict:
        if reason_code not in DEFER_REASONS:
            raise WorkflowError(f"Unknown reason '{reason_code}'. Use one of: {', '.join(DEFER_REASONS)}")
        if reason_code in REASONS_REQUIRING_NOTE and not note.strip():
            raise WorkflowError(f"A note is required for reason '{reason_code}'")
        return self._transition(key, actor, role, "defer", ACTIVE_WORKFLOW_STATES,
                                {"workflow_state": "deferred", "defer_reason": reason_code,
                                 "defer_note": note, "defer_until": until},
                                {"reason": reason_code, "note": note, "until": until})

    def close(self, key: str, actor: str, evidence: str, role: str = "clinician") -> Dict:
        if not evidence or len(evidence.strip()) < 5:
            raise WorkflowError("Closure requires evidence of the completed follow-up (e.g. order or visit reference)")
        return self._transition(key, actor, role, "close", ACTIVE_WORKFLOW_STATES + ("deferred",),
                                {"workflow_state": "closed_by_clinician", "closure_evidence": evidence},
                                {"evidence": evidence})

    # ── escalation ───────────────────────────────────────────────────────────
    def escalate_overdue(self, now: Optional[datetime] = None, actor: str = "watchdog",
                         rule_ids: Optional[set] = None) -> List[Dict]:
        """
        Climb the escalation chain for loops past their deadline that nobody
        has acknowledged. Each level waits one severity-specific grace period.
        ``rule_ids`` limits escalation to live rules (shadow-mode loops never page anyone).
        """
        now = now or utc_now()
        escalated = []
        with self._lock:
            for loop in self.worklist(now=now):
                if rule_ids is not None and loop["rule_id"] not in rule_ids:
                    continue
                if loop["workflow_state"] != "new" or loop["clock_state"] != "BLACK":
                    continue
                if loop["escalation_level"] >= len(ESCALATION_CHAIN) - 1:
                    continue
                grace = ESCALATION_GRACE.get(loop["severity"], timedelta(hours=24))
                since = loop["last_escalated_at"] or loop["deadline"]
                if since and datetime.fromisoformat(since) + grace > now:
                    continue
                level = loop["escalation_level"] + 1
                self._db.execute("UPDATE loops SET escalation_level=?, last_escalated_at=?, updated_at=? "
                                 "WHERE loop_key=?",
                                 (level, now.isoformat(), now.isoformat(), loop["loop_key"]))
                self._audit(actor, "system", "escalate", loop["loop_key"],
                            {"level": level, "to": ESCALATION_CHAIN[level], "severity": loop["severity"]})
                escalated.append({"loop_key": loop["loop_key"], "level": level, "to": ESCALATION_CHAIN[level]})
            self._db.commit()
        return escalated

    # ── patient outreach (draft → clinician approval → send) ─────────────────
    def outreach_messages(self, key: str) -> List[Dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM outreach_messages WHERE loop_key=? ORDER BY drafted_at", (key,))
            return [{**dict(r), "safety_flags": json.loads(r["safety_flags"] or "[]")} for r in rows]

    def get_outreach(self, msg_id: str) -> Dict:
        with self._lock:
            return self._outreach(msg_id)

    def _outreach(self, msg_id: str) -> Dict:
        r = self._db.execute("SELECT * FROM outreach_messages WHERE id=?", (msg_id,)).fetchone()
        if r is None:
            raise KeyError(msg_id)
        return {**dict(r), "safety_flags": json.loads(r["safety_flags"] or "[]")}

    def add_outreach_draft(self, key: str, actor: str, role: str, text: str, language: str,
                           channel: str, safety_flags: List[str]) -> Dict:
        with self._lock:
            loop = self.get(key)
            if loop["workflow_state"] not in ACTIVE_WORKFLOW_STATES:
                raise WorkflowError(f"Cannot message a patient about a loop in state '{loop['workflow_state']}'")
            msg_id = f"MSG-{hashlib.sha256(f'{key}|{utc_now().isoformat()}'.encode()).hexdigest()[:12]}"
            self._db.execute(
                "INSERT INTO outreach_messages (id, loop_key, patient_id, language, channel, draft_text, status, "
                "safety_flags, drafted_by, drafted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (msg_id, key, loop["patient_id"], language, channel, text, "draft",
                 json.dumps(safety_flags), actor, utc_now().isoformat()))
            self._audit(actor, role, "outreach_drafted", key, {"message_id": msg_id, "language": language})
            self._db.commit()
            return self._outreach(msg_id)

    def decide_outreach(self, msg_id: str, actor: str, role: str, approve: bool,
                        final_text: Optional[str] = None, provider=None, note: str = "") -> Dict:
        """Approve (and send through `provider`) or reject a draft. Exactly one decision per draft."""
        with self._lock:
            msg = self._outreach(msg_id)
            if msg["status"] != "draft":
                raise WorkflowError(f"Message {msg_id} is already '{msg['status']}'")
            now = utc_now().isoformat()
            if not approve:
                self._db.execute("UPDATE outreach_messages SET status='rejected', decided_by=?, decided_at=?, note=? "
                                 "WHERE id=?", (actor, now, note, msg_id))
                self._audit(actor, role, "outreach_rejected", msg["loop_key"], {"message_id": msg_id, "note": note})
                self._db.commit()
                return self._outreach(msg_id)
            text = (final_text or msg["draft_text"]).strip()
            payload = {"message_id": msg_id, "patient_id": msg["patient_id"], "channel": msg["channel"],
                       "language": msg["language"], "text": text}
            try:
                ref, status, err = provider.send(payload), "sent", None
            except Exception as e:  # delivery failure is recorded, never silent
                ref, status, err = None, "failed", f"{type(e).__name__}: {e}"
            self._db.execute(
                "UPDATE outreach_messages SET status=?, final_text=?, decided_by=?, decided_at=?, provider=?, "
                "provider_ref=?, note=? WHERE id=?",
                (status, text, actor, now, getattr(provider, "name", "unknown"), ref, err or note, msg_id))
            self._audit(actor, role, f"outreach_{status}", msg["loop_key"],
                        {"message_id": msg_id, "edited": text != msg["draft_text"].strip(),
                         "provider_ref": ref, "error": err})
            # Contacting the patient means someone is acting on the loop; it is not closure
            loop = self.get(msg["loop_key"])
            if status == "sent" and loop["workflow_state"] == "new":
                self._db.execute("UPDATE loops SET workflow_state='acknowledged', updated_at=? WHERE loop_key=?",
                                 (now, msg["loop_key"]))
            self._db.commit()
            return self._outreach(msg_id)

    # ── data feed: ingest runs, sync cursor, silence alarm ───────────────────
    def record_ingest(self, source: str, actor: str, ok: bool, patients: int = 0, events: int = 0,
                      warnings: int = 0, error: Optional[str] = None, now: Optional[datetime] = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO ingest_runs (ts, source, actor, ok, patients, events, warnings, error) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ((now or utc_now()).isoformat(), source, actor, int(ok), patients, events, warnings, error))
            if not ok:
                self._audit(actor, "system", "ingest_failed", None, {"source": source, "error": error})
            self._db.commit()

    def get_cursor(self, source: str) -> Optional[str]:
        with self._lock:
            r = self._db.execute("SELECT cursor FROM sync_state WHERE source=?", (source,)).fetchone()
        return r["cursor"] if r else None

    def set_cursor(self, source: str, cursor: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO sync_state (source, cursor, updated_at) VALUES (?,?,?) "
                             "ON CONFLICT(source) DO UPDATE SET cursor=excluded.cursor, updated_at=excluded.updated_at",
                             (source, cursor, utc_now().isoformat()))
            self._db.commit()

    def feed_status(self, max_silence_hours: float = 24.0, now: Optional[datetime] = None) -> Dict:
        """
        Is data still arriving? A safety net fed by a dead interface shows an
        empty, reassuring worklist, which is worse than no safety net.
          NEVER    no data has ever been ingested
          FAILING  the last 3 ingest attempts all failed
          STALE    no successful ingest within max_silence_hours
          OK       otherwise
        """
        now = now or utc_now()
        with self._lock:
            last_ok = self._db.execute("SELECT * FROM ingest_runs WHERE ok=1 ORDER BY id DESC LIMIT 1").fetchone()
            recent = [dict(r) for r in self._db.execute("SELECT * FROM ingest_runs ORDER BY id DESC LIMIT 3")]
        hours = None
        if last_ok:
            hours = round((now - datetime.fromisoformat(last_ok["ts"])).total_seconds() / 3600, 2)
        if not recent:
            status = "NEVER"
        elif len(recent) == 3 and not any(r["ok"] for r in recent):
            status = "FAILING"
        elif hours is None or hours > max_silence_hours:
            status = "STALE"
        else:
            status = "OK"
        return {
            "status": status,
            "last_success": last_ok["ts"] if last_ok else None,
            "hours_since_success": hours,
            "max_silence_hours": max_silence_hours,
            "recent_runs": recent,
        }

    def check_feed(self, max_silence_hours: float = 24.0, now: Optional[datetime] = None) -> Optional[Dict]:
        """Raise (audit) a feed alarm when the feed is stale or failing; at most once per silence window."""
        now = now or utc_now()
        status = self.feed_status(max_silence_hours, now)
        if status["status"] not in ("STALE", "FAILING"):
            return None
        with self._lock:
            last = self._db.execute("SELECT ts FROM audit_log WHERE action='feed_alarm' ORDER BY id DESC LIMIT 1").fetchone()
            if last and now - datetime.fromisoformat(last["ts"]) < timedelta(hours=max_silence_hours):
                return None
            detail = {"status": status["status"], "last_success": status["last_success"],
                      "hours_since_success": status["hours_since_success"]}
            self._audit("watchdog", "system", "feed_alarm", None, detail, at=now)
            self._db.commit()
        return detail

    # ── quality measure ──────────────────────────────────────────────────────
    def breakdowns(self, now: Optional[datetime] = None) -> Dict:
        """
        Where follow-up breaks, hospital-wide (process view, not people ranking):
          * per rule: active, overdue, closed on time, closed late, closed by a clinician, deferred,
            on-time rate among loops whose deadline has passed, and the follow-up step most often missing;
          * per owner: active and overdue load, escalations (to balance work, not to blame);
          * per equity stratum (age group, language, sex): overdue rate, so a gap affecting one group shows;
          * bottlenecks: rules ranked by overdue loops weighted by severity.
        """
        now_iso = (now or utc_now()).isoformat()
        sev_w = {"critical": 4, "high": 3, "moderate": 2, "low": 1}
        with self._lock:
            rows = [self._row(r) for r in self._db.execute("SELECT * FROM loops")]
        rules: Dict[str, Dict] = {}
        owners: Dict[str, Dict] = {}
        strata: Dict[str, Dict[str, Dict[str, int]]] = {}
        for r in rows:
            active = r["engine_status"] in ACTIVE_ENGINE_STATUSES and r["workflow_state"] in ACTIVE_WORKFLOW_STATES
            due_passed = bool(r["deadline"]) and r["deadline"] <= now_iso
            overdue = active and due_passed
            g = rules.setdefault(r["rule_id"], {
                "rule_id": r["rule_id"], "rule_name": r["rule_name"], "severity": r["severity"], "total": 0,
                "active": 0, "overdue": 0, "closed_on_time": 0, "closed_late": 0, "closed_by_clinician": 0,
                "deferred": 0, "due_passed": 0, "missing": {}})
            g["total"] += 1
            g["active"] += int(active)
            g["overdue"] += int(overdue)
            if r["workflow_state"] == "closed_by_clinician":
                g["closed_by_clinician"] += 1
            elif r["workflow_state"] == "deferred":
                g["deferred"] += 1
            elif r["engine_status"] == "closed":
                g["closed_on_time"] += 1
            elif r["engine_status"] == "delayed" and not active:
                g["closed_late"] += 1
            if due_passed and r["workflow_state"] != "deferred":
                g["due_passed"] += 1
            if active and r.get("missing_step"):
                step = re.sub(r"\s+within\s+.*$", "", re.sub(r"^Missing:\s*", "", r["missing_step"])).strip()
                g["missing"][step] = g["missing"].get(step, 0) + 1
            if active:
                o = owners.setdefault(r["owner"], {"owner": r["owner"], "active": 0, "overdue": 0, "escalated": 0})
                o["active"] += 1
                o["overdue"] += int(overdue)
                o["escalated"] += int((r.get("escalation_level") or 0) > 0)
            if due_passed and r["workflow_state"] != "deferred":
                for key in ("age_group", "language", "sex"):
                    val = str((r.get("strata") or {}).get(key, "unknown"))
                    cell = strata.setdefault(key, {}).setdefault(val, {"due_passed": 0, "missed": 0})
                    cell["due_passed"] += 1
                    cell["missed"] += int(r["engine_status"] in ACTIVE_ENGINE_STATUSES
                                          and r["workflow_state"] != "closed_by_clinician")
        for g in rules.values():
            missed = g["overdue"] + g["closed_late"]
            g["on_time_rate"] = round(1 - missed / g["due_passed"], 3) if g["due_passed"] else None
            g["top_missing"] = max(g["missing"], key=g["missing"].get) if g["missing"] else None
            g["bottleneck_score"] = g["overdue"] * sev_w.get(g["severity"], 1)
        for groups in strata.values():
            for cell in groups.values():
                cell["missed_rate"] = round(cell["missed"] / cell["due_passed"], 3) if cell["due_passed"] else None
        ranked = sorted(rules.values(), key=lambda g: (-g["bottleneck_score"], -g["active"], g["rule_id"]))
        return {
            "as_of": now_iso, "loops": len(rows),
            "rules": ranked,
            "bottlenecks": [{"rule_id": g["rule_id"], "rule_name": g["rule_name"], "overdue": g["overdue"],
                             "severity": g["severity"], "top_missing": g["top_missing"]}
                            for g in ranked if g["overdue"]][:5],
            "owners": sorted(owners.values(), key=lambda o: (-o["overdue"], -o["active"], o["owner"])),
            "strata": strata,
            "note": "A process view: where follow-up breaks and for whom. Not a ranking of clinicians.",
        }

    def open_loop_rate(self, now: Optional[datetime] = None, stratify_by: Optional[str] = None) -> Dict:
        """
        Open-loop rate (docs/LIFE_SAVING_ROADMAP.md §3.2), per 1,000 loops
        whose deadline has passed:
          numerator   = loops not closed on time (still open, or closed late)
          denominator = all loops whose deadline has passed
        Loops deferred with a documented reason are excluded from both.
        """
        now_iso = (now or utc_now()).isoformat()
        with self._lock:
            rows = [self._row(r) for r in self._db.execute("SELECT * FROM loops")]
        groups: Dict[str, Dict[str, int]] = {}
        for r in rows:
            if not r["deadline"] or r["deadline"] > now_iso or r["workflow_state"] == "deferred":
                continue
            if stratify_by == "rule":
                g = r["rule_id"]
            elif stratify_by:
                g = str(r["strata"].get(stratify_by, "unknown"))
            else:
                g = "all"
            missed = r["engine_status"] in ACTIVE_ENGINE_STATUSES and r["workflow_state"] != "closed_by_clinician"
            groups.setdefault(g, {"eligible": 0, "missed": 0})
            groups[g]["eligible"] += 1
            groups[g]["missed"] += int(missed)
        return {
            "definition": "Loops not closed within their guideline window per 1,000 loops whose deadline has passed",
            "stratified_by": stratify_by,
            "groups": {g: {**v, "rate_per_1000": round(1000 * v["missed"] / v["eligible"], 1)}
                       for g, v in sorted(groups.items())},
        }
