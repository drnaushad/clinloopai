"""
test_phase1_production.py — Production-readiness items: report versions, access records,
rule-set version, patient message opt-out, pinned dependencies

Synthetic data only.
"""

import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# The same tokens as test_clinical_api (the token table is read once per process)
TOKENS = {
    "admin": "test-admin-token-0123456789",
    "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234",
    "viewer": "test-viewer-token-0123456789",
}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

from src.clinloop_engine.fhir_ingest import bundle_to_events, superseded_reports
from src.clinloop_engine.governance import ruleset_version
from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.loop_store import REPORT_REVISED_STEP, LoopStore, WorkflowError

EVAL = "2026-06-01T00:00:00"
PATIENT = {"resourceType": "Patient", "id": "p1", "birthDate": "1960-01-01", "gender": "male"}


def _report(rid, status, text, issued, accession="ACC-1"):
    return {"resourceType": "DiagnosticReport", "id": rid, "status": status, "subject": {"reference": "Patient/p1"},
            "identifier": [{"type": {"coding": [{"code": "ACSN"}]}, "value": accession}] if accession else [],
            "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": "CT chest"},
            "effectiveDateTime": "2026-01-10T09:00:00Z", "issued": issued, "conclusion": text}


PE_NODULE = "Acute pulmonary embolism. 12 mm solid nodule right upper lobe."
PRELIM = _report("pre1", "preliminary", PE_NODULE, "2026-01-10T09:30:00Z")
FINAL = _report("fin1", "final", PE_NODULE, "2026-01-10T11:00:00Z")


def _ingest(store, resources):
    events, _ = bundle_to_events(resources)
    for pid, evs in events.items():
        store.upsert_detections(ClinLoopDetector(evaluation_time=EVAL).process_patient("t", pid, evs))
    return store.supersede_sources(superseded_reports(resources))


def _loops(store, inactive=True):
    return {(l["rule_id"], l["loop_key"].split("|")[2].split(":")[0]): l
            for l in store.worklist(include_inactive=inactive)}


class TestReportVersions(unittest.TestCase):

    def test_final_report_replaces_its_preliminary(self):
        self.assertEqual(superseded_reports([PATIENT, PRELIM, FINAL]),
                         {"DiagnosticReport/pre1": "DiagnosticReport/fin1"})
        events, _ = bundle_to_events([PATIENT, PRELIM, FINAL])
        self.assertFalse(any(e["source"] == "DiagnosticReport/pre1" for e in events["p1"]))

    def test_acknowledged_loop_moves_to_the_final_report_once(self):
        store = LoopStore()
        _ingest(store, [PATIENT, PRELIM])
        pe = _loops(store)[("R035", "DiagnosticReport/pre1")]
        store.acknowledge(pe["loop_key"], "dr.kim")
        self.assertEqual(_ingest(store, [PATIENT, PRELIM, FINAL]), 2)
        loops = _loops(store)
        self.assertEqual(loops[("R035", "DiagnosticReport/pre1")]["workflow_state"], "superseded")
        new = loops[("R035", "DiagnosticReport/fin1")]
        self.assertEqual((new["workflow_state"], new["owner"]), ("acknowledged", "dr.kim"))
        self.assertEqual([l["rule_id"] for l in store.worklist()].count("R035"), 1)   # one loop, not two
        self.assertEqual(_ingest(store, [PATIENT, PRELIM, FINAL]), 0)                 # idempotent
        self.assertIn("loop_superseded", [a["action"] for a in store.audit_trail(pe["loop_key"])])
        self.assertTrue(store.verify_audit_chain())

    def test_finding_dropped_by_the_final_report_waits_for_a_clinician(self):
        store = LoopStore()
        _ingest(store, [PATIENT, PRELIM])
        no_pe = _report("fin2", "final", "No pulmonary embolism. 12 mm solid nodule right upper lobe.",
                        "2026-01-10T11:00:00Z")
        _ingest(store, [PATIENT, PRELIM, no_pe])
        pe = _loops(store)[("R035", "DiagnosticReport/pre1")]
        self.assertEqual(pe["workflow_state"], "new")             # still on the worklist
        self.assertEqual(pe["missing_step"], REPORT_REVISED_STEP)
        self.assertEqual(pe["engine_status"], "needs_human_review")
        _ingest(store, [PATIENT, PRELIM, no_pe])
        self.assertEqual([a["action"] for a in store.audit_trail(pe["loop_key"])].count("report_revised"), 1)

    def test_other_studies_and_released_versions_are_left_alone(self):
        other = _report("fin3", "final", PE_NODULE, "2026-01-11T11:00:00Z", accession="ACC-2")
        self.assertEqual(superseded_reports([PATIENT, PRELIM, other]), {})
        addendum = _report("add1", "amended", "ADDENDUM: no change.", "2026-01-12T11:00:00Z")
        self.assertEqual(superseded_reports([PATIENT, FINAL, addendum]), {})     # released never replaces released
        self.assertEqual(superseded_reports([PATIENT, _report("x", "preliminary", PE_NODULE, "t", None), FINAL]), {})


class TestRulesetVersion(unittest.TestCase):

    def test_loops_and_their_audit_carry_the_ruleset_version(self):
        store = LoopStore()
        _ingest(store, [PATIENT, FINAL])
        version = ruleset_version()
        self.assertRegex(version, r"^rs-[0-9a-f]{12}$")
        loop = store.worklist()[0]
        self.assertEqual(loop["ruleset_version"], version)
        opened = store.audit_trail(loop["loop_key"])[0]
        self.assertEqual((opened["action"], opened["detail"]["ruleset"]), ("loop_opened", version))

    def test_older_database_gains_the_column(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "old.db")
            store = LoopStore(path)
            store._db.execute("ALTER TABLE loops DROP COLUMN ruleset_version")
            store._db.commit()
            store._db.close()
            reopened = LoopStore(path)
            cols = {r["name"] for r in reopened._db.execute("PRAGMA table_info(loops)")}
            reopened._db.close()
            self.assertIn("ruleset_version", cols)


class TestAccessLog(unittest.TestCase):

    def test_records_are_chained_and_repeats_collapse(self):
        store = LoopStore()
        t0 = datetime(2026, 10, 1, 9, 0)
        self.assertTrue(store.record_access("dr.kim", "clinician", "view_worklist", ["p2", "p1"], "10.0.0.5", now=t0))
        self.assertFalse(store.record_access("dr.kim", "clinician", "view_worklist", ["p1", "p2"], "10.0.0.5",
                                             now=t0 + timedelta(seconds=30)))         # auto-refresh
        self.assertTrue(store.record_access("dr.kim", "clinician", "view_worklist", ["p1", "p2"], "10.0.0.5",
                                            now=t0 + timedelta(minutes=11)))
        self.assertTrue(store.record_access("dr.kim", "clinician", "view_loop", ["p1"], "10.0.0.5", now=t0))
        # Alternating views (each loop's messages on every refresh) are each recorded once per window
        for patient in ("p3", "p4", "p3", "p4"):
            store.record_access("dr.kim", "clinician", "view_messages", [patient], "10.0.0.5", now=t0)
        self.assertEqual(len(store.access_log(actor="dr.kim")), 5)
        self.assertEqual(len(store.access_log(patient_id="p1")), 3)
        self.assertEqual(len(store.access_log(patient_id="p2")), 2)
        self.assertEqual(store.access_log()[0]["patients"], ["p4"])
        self.assertTrue(store.verify_access_chain())
        store._db.execute("UPDATE access_log SET actor='someone' WHERE id=1")
        self.assertFalse(store.verify_access_chain())


class TestOutreachOptOut(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        events = [{"event_id": "fit-1", "patient_id": "P1", "event_type": "lab_result",
                   "timestamp": "2026-05-01T09:00:00", "details": {"test": "FIT", "result": "positive"},
                   "status": "completed"}]
        self.store.upsert_detections(ClinLoopDetector(evaluation_time=datetime(2026, 6, 1)).process_patient("t", "P1", events))
        self.key = self.store.worklist()[0]["loop_key"]

    def test_opt_out_blocks_drafting_and_withdraws_waiting_drafts(self):
        msg = self.store.add_outreach_draft(self.key, "nurse.park", "navigator", "Please call the clinic.", "ko", "sms", [])
        with self.assertRaises(WorkflowError):
            self.store.set_outreach_preference("P1", True, "nurse.park", "navigator", reason="")   # how? required
        self.store.set_outreach_preference("P1", True, "nurse.park", "navigator", reason="by phone to the navigator")
        self.assertEqual(self.store._outreach(msg["id"])["status"], "withdrawn")
        with self.assertRaises(WorkflowError):
            self.store.add_outreach_draft(self.key, "nurse.park", "navigator", "Please call.", "ko", "sms", [])
        self.store.set_outreach_preference("P1", False, "nurse.park", "navigator")
        self.store.add_outreach_draft(self.key, "nurse.park", "navigator", "Please call.", "ko", "sms", [])
        actions = [a["action"] for a in self.store.audit_trail(limit=50)]
        self.assertIn("outreach_opt_out", actions)
        self.assertIn("outreach_opt_in", actions)

    def test_approval_is_refused_after_opt_out(self):
        msg = self.store.add_outreach_draft(self.key, "nurse.park", "navigator", "Please call the clinic.", "ko", "sms", [])
        self.store._db.execute("INSERT INTO outreach_preferences VALUES ('P1', 1, 'phone', 'x', '2026-10-01')")
        self.store._db.commit()

        class Provider:
            name = "test"
            sent = []

            def send(self, payload):
                self.sent.append(payload)
                return "ref"
        provider = Provider()
        with self.assertRaises(WorkflowError):
            self.store.decide_outreach(msg["id"], "dr.lee", "clinician", True, provider=provider)
        self.assertEqual(provider.sent, [])


class TestPinnedDependencies(unittest.TestCase):

    def test_every_requirement_is_pinned_and_used(self):
        def names(path):
            out = set()
            for line in open(os.path.join(ROOT, path), encoding="utf-8"):
                line = line.split("#")[0].strip()
                if line and not line.startswith("-"):
                    out.add(re.split(r"[<>=!~\[; ]", line)[0].lower().replace("_", "-"))
            return out
        lock = {}
        for line in open(os.path.join(ROOT, "requirements.lock"), encoding="utf-8"):
            m = re.match(r"^([A-Za-z0-9_.\-]+)==(\S+)", line)
            if m:
                lock[m.group(1).lower().replace("_", "-")] = m.group(2)
        for name in names("requirements.txt") | names("requirements-api.txt"):
            self.assertIn(name, lock, f"{name} is not pinned in requirements.lock")
        for path in ("Dockerfile", os.path.join(".github", "workflows", "docker-publish.yml")):
            self.assertIn("-c requirements.lock", open(os.path.join(ROOT, path), encoding="utf-8").read(), path)


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


def _h(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestPhase1API(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.client = TestClient(app)
        with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
            r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00",
                                 json=json.load(f), headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)

    def test_reading_patient_data_leaves_an_access_record(self):
        loops = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()["loops"]
        key = loops[0]["loop_key"]
        self.client.get(f"/api/v1/loops/{key}", headers=_h("viewer"))
        records = self.store.access_log(actor="viewer.user")
        self.assertEqual([r["action"] for r in records], ["view_loop", "view_worklist"])
        self.assertEqual(set(records[1]["patients"]), {l["patient_id"] for l in loops})
        self.assertEqual(records[0]["patients"], [loops[0]["patient_id"]])
        self.assertTrue(records[0]["client"])
        self.assertIn("ingest", [r["action"] for r in self.store.access_log(actor="admin.user")])

    def test_only_admin_reads_the_access_log_and_reading_it_is_recorded(self):
        self.assertEqual(self.client.get("/api/v1/access-log", headers=_h("clinician")).status_code, 403)
        r = self.client.get("/api/v1/access-log?patient_id=SYN-001", headers=_h("admin"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all("SYN-001" in rec["patients"] for rec in r.json()["records"]))
        self.assertEqual(self.store.access_log(actor="admin.user")[0]["action"], "view_access_log")
        self.assertTrue(self.client.get("/api/v1/access-log/verify", headers=_h("admin")).json()["access_log_intact"])

    def test_opt_out_through_the_api(self):
        path = "/api/v1/patients/SYN-001/outreach-preference"
        self.assertEqual(self.client.put(path, json={"opted_out": True, "reason": "phone"},
                                         headers=_h("viewer")).status_code, 403)
        self.assertEqual(self.client.put(path, json={"opted_out": True}, headers=_h("navigator")).status_code, 409)
        r = self.client.put(path, json={"opted_out": True, "reason": "by phone to the navigator"}, headers=_h("navigator"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.client.get(path, headers=_h("viewer")).json()["opted_out"])
        key = next(l["loop_key"] for l in self.store.worklist() if l["patient_id"] == "SYN-001" and l["rule_id"] == "R017")
        draft = self.client.post(f"/api/v1/loops/{key}/outreach", json={"language": "ko"}, headers=_h("navigator"))
        self.assertEqual(draft.status_code, 409)
        self.assertIn("asked not to be messaged", draft.json()["detail"])
        self.assertEqual(self.client.get("/api/v1/patients/bad%20id/outreach-preference",
                                         headers=_h("viewer")).status_code, 422)


if __name__ == "__main__":
    unittest.main()
