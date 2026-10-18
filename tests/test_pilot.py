"""
test_pilot.py — The silent run (Stage 2 shadow pilot) and its weekly review

Synthetic data only: the example FHIR bundle evaluated on 1 September 2026.
"""

import csv
import io
import json
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {"admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
          "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

from src.clinloop_engine import pilot
from src.clinloop_engine.loop_store import LoopStore, WorkflowError

try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False

NOW = datetime(2026, 9, 1, 12, 0)


def _h(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestSilentRun(unittest.TestCase):

    def setUp(self):
        self.saved = {k: os.environ.pop(k, None) for k in ("CLINLOOP_SILENT_RUN", "CLINLOOP_PILOT_REVIEWERS",
                                                          "CLINLOOP_PILOT_REVIEWS_PER_LOOP", "CLINLOOP_PILOT_CLINICIANS")}
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.client = TestClient(app)
        with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
            r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00", json=json.load(f),
                                 headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)
        self.key = self.store.worklist()[0]["loop_key"]
        os.environ["CLINLOOP_SILENT_RUN"] = "1"

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def test_nothing_reaches_clinical_care(self):
        wl = self.client.get("/api/v1/worklist", headers=_h("clinician")).json()
        self.assertTrue(wl["silent_run"])
        self.assertEqual(wl["loops"], [])
        self.assertGreater(wl["shadow_count"], 0)                         # the engine still runs
        self.assertEqual(self.client.get(f"/api/v1/loops/{self.key}", headers=_h("viewer")).status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/loops/{self.key}", headers=_h("clinician")).status_code, 200)
        for path, body in ((f"/api/v1/loops/{self.key}/acknowledge", None),
                           (f"/api/v1/loops/{self.key}/outreach", {"language": "ko"}),
                           ("/api/v1/watchdog/escalate", None)):
            r = self.client.post(path, json=body, headers=_h("admin"))
            self.assertEqual(r.status_code, 409, path)
            self.assertIn("Silent run", r.json()["detail"])
        from src.clinloop_engine import rule_monitor
        self.assertFalse(rule_monitor.acting())
        self.assertGreater(self.store.monitored_patient_count(), 0)

    def test_named_review_team(self):
        os.environ["CLINLOOP_PILOT_REVIEWERS"] = "someone.else"
        self.assertEqual(self.client.get(f"/api/v1/loops/{self.key}", headers=_h("clinician")).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/pilot/queue", headers=_h("clinician")).status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/loops/{self.key}", headers=_h("admin")).status_code, 200)

    def test_weekly_sample_review_and_blinding(self):
        self.assertEqual(self.client.post("/api/v1/pilot/sample", json={"size": 2}, headers=_h("clinician")).status_code, 403)
        first = self.client.post("/api/v1/pilot/sample", json={"size": 2}, headers=_h("admin")).json()
        self.assertEqual(first["sampled"], 2)
        self.assertGreaterEqual(first["candidates"], 2)
        rest = self.client.post("/api/v1/pilot/sample", json={"size": None}, headers=_h("admin")).json()
        self.assertEqual(rest["sampled"], first["candidates"] - 2)               # no loop sampled twice
        queue = self.client.get("/api/v1/pilot/queue", headers=_h("clinician")).json()["items"]
        key = queue[0]["loop"]["loop_key"]
        answer = {"loop_key": key, "truly_open": "yes", "usual_care": "no", "important": "yes"}
        r = self.client.post("/api/v1/pilot/reviews", json={**answer, "urgent": True}, headers=_h("clinician"))
        self.assertEqual(r.status_code, 409)                                  # urgent needs a safety referral
        self.assertIn("safety referral", r.json()["detail"])
        r = self.client.post("/api/v1/pilot/reviews", json={**answer, "urgent": True,
                             "safety_referral": "Told Dr Park (ward 7) by phone 14:20, safety report 2291"},
                             headers=_h("clinician"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.post("/api/v1/pilot/reviews", json=answer, headers=_h("clinician")).status_code, 409)
        mine = {i["loop"]["loop_key"] for i in self.client.get("/api/v1/pilot/queue", headers=_h("clinician")).json()["items"]}
        self.assertNotIn(key, mine)
        other = [i for i in self.client.get("/api/v1/pilot/queue", headers=_h("admin")).json()["items"]
                 if i["loop"]["loop_key"] == key][0]
        self.assertEqual(other["reviews_so_far"], 1)
        self.assertNotIn("truly_open", json.dumps(other))                     # blinded to the first answer
        refs = self.client.get("/api/v1/pilot/safety-referrals", headers=_h("admin")).json()["referrals"]
        self.assertEqual(len(refs), 1)
        self.assertIn("safety_referral", [a["action"] for a in self.store.audit_trail(key)])

    def test_metrics_agreement_and_deidentified_export(self):
        os.environ["CLINLOOP_PILOT_CLINICIANS"] = "4"
        self.client.post("/api/v1/pilot/sample", json={"size": None}, headers=_h("admin"))
        keys = [s["loop_key"] for s in self.store.pilot_samples()]
        for i, key in enumerate(keys):
            for role in ("clinician", "admin"):
                truly = "yes" if i % 2 == 0 or (role == "admin" and i == 1) else "no"
                self.client.post("/api/v1/pilot/reviews", headers=_h(role), json={
                    "loop_key": key, "truly_open": truly, "usual_care": "no", "important": "yes",
                    "note": "free text that must not leave"})
        m = self.client.get("/api/v1/pilot/metrics", headers=_h("clinician")).json()
        self.assertEqual(m["reviewed"], len(keys))
        self.assertEqual(m["discordant"], 1)                                  # loop 1: the reviewers disagreed
        self.assertEqual(m["ppv"]["n"], len(keys) - 1)
        self.assertEqual(m["agreement"]["pairs"], len(keys))
        self.assertLess(m["agreement"]["observed"], 1.0)
        self.assertIsNone(m["alerts_per_clinician_per_day"])                  # under 4 weeks: no rate yet
        self.assertIsNone(m["true_important_beyond_usual_care_per_1000_per_month"])
        self.assertTrue(all(c["result"] in ("insufficient data", "decided by the clinical leads") for c in m["go_no_go"]))
        export = self.client.get("/api/v1/pilot/export.csv", headers=_h("admin")).text
        self.assertNotIn("SYN-", export)
        self.assertNotIn("free text", export)
        self.assertNotIn("clinician.user", export)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(export)))), 2 * len(keys))
        self.assertEqual(self.client.get("/api/v1/pilot/export.csv", headers=_h("clinician")).status_code, 403)


class TestPilotUnits(unittest.TestCase):

    def test_sample_is_reproducible_for_a_week(self):
        from src.clinloop_engine.loop_detector import ClinLoopDetector
        a, b = LoopStore(), LoopStore()
        for s in (a, b):
            for i in range(12):
                ev = [{"event_id": f"fit-{i}", "patient_id": f"P{i}", "event_type": "lab_result",
                       "timestamp": "2026-05-01T09:00:00", "details": {"test": "FIT", "result": "positive"},
                       "status": "completed"}]
                s.upsert_detections(ClinLoopDetector(evaluation_time=NOW).process_patient("t", f"P{i}", ev))
        pilot.draw_sample(a, 5, "it", now=NOW)
        pilot.draw_sample(b, 5, "it", now=NOW)
        self.assertEqual([s["loop_key"] for s in a.pilot_samples()], [s["loop_key"] for s in b.pilot_samples()])
        self.assertEqual(a.pilot_samples()[0]["week"], "2026-W36")

    def test_rates_over_a_six_week_run_match_a_hand_calculation(self):
        from datetime import timedelta
        from src.clinloop_engine.auth import User
        store = LoopStore()
        start = NOW - timedelta(days=42)
        with store._writing():
            store._db.executemany("INSERT INTO monitored_patients VALUES (?,?,?)",
                                  [(f"P{i}", start.isoformat(), NOW.isoformat()) for i in range(2000)])
            for i in range(10):              # one week: 40 overdue loops, 10 sampled
                store._db.execute("INSERT INTO pilot_samples VALUES (?,?,?,?,?,?)",
                                  (f"P{i}|R017|t{i}", "2026-W30", 40, "R017", start.isoformat(), "it"))
        os.environ["CLINLOOP_PILOT_REVIEWS_PER_LOOP"] = "1"
        try:
            for i in range(10):              # 4 of 10: truly open, important, usual care would not catch it
                hit = i < 4
                pilot.review(store, User("dr.kim", "clinician"), f"P{i}|R017|t{i}", "yes" if i < 8 else "no",
                             "no" if hit else "yes", "yes", False)
            m = pilot.metrics(store, now=NOW)
        finally:
            os.environ.pop("CLINLOOP_PILOT_REVIEWS_PER_LOOP", None)
        # 40 × 4/10 = 16 estimated loops; 16 / (2000/1000) / (42/30.4) months = 5.79
        self.assertAlmostEqual(m["true_important_beyond_usual_care_per_1000_per_month"], 5.79, places=2)
        self.assertEqual(m["ppv"]["value"], 0.8)
        self.assertEqual(m["days_observed"], 42.0)

    def test_review_rules(self):
        store = LoopStore()
        from src.clinloop_engine.auth import User
        with self.assertRaises(WorkflowError):          # only sampled loops are reviewed
            pilot.review(store, User("dr.kim", "clinician"), "x|R017|y", "yes", "no", "yes", False)
        with self.assertRaises(WorkflowError):          # urgent needs a truly open loop
            pilot.review(store, User("dr.kim", "clinician"), "x|R017|y", "no", "no", "yes", True, "told ward at 10:00")
        with self.assertRaises(WorkflowError):
            pilot.review(store, User("dr.kim", "clinician"), "x|R017|y", "maybe", "no", "yes", False)


if __name__ == "__main__":
    unittest.main()
