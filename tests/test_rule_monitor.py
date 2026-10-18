"""
test_rule_monitor.py — Watching live rules, with a safe automatic stop

The audit log is filled with synthetic loop openings and decisions at chosen times, then the monitor
is run "now". Synthetic data only.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in {
    "admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}.items())

from src.clinloop_engine import governance, rule_monitor
from src.clinloop_engine.loop_store import LoopStore, WorkflowError

NOW = datetime(2026, 10, 1, 12, 0)
HIGH, CRITICAL = "R017", "R035"


def _opened(store, rule, n, days_ago, tag="x"):
    with store._writing():
        for i in range(n):
            at = NOW - timedelta(days=days_ago, minutes=i)
            store._audit("engine", "system", "loop_opened", f"P{tag}{days_ago}-{i}|{rule}|Obs/{tag}{i}:lab_result",
                         {"rule_id": rule}, at=at)


def _decided(store, rule, dismissed, kept, days_ago=3):
    with store._writing():
        for i in range(dismissed + kept):
            reason = "not_clinically_indicated" if i < dismissed else "completed_elsewhere"
            store._audit("dr.kim", "clinician", "defer", f"Q{i}|{rule}|Obs/q{i}:lab_result",
                         {"reason": reason}, at=NOW - timedelta(days=days_ago, minutes=i))


def _usual(store, rule, per_week=2):
    for week in range(1, 6):                          # five weeks of ordinary history
        _opened(store, rule, per_week, days_ago=7 * week + 1, tag=f"h{week}")


class TestRuleMonitor(unittest.TestCase):

    def setUp(self):
        self.saved = os.environ.pop("CLINLOOP_MONITOR", None)
        self.store = LoopStore()

    def tearDown(self):
        os.environ.pop("CLINLOOP_MONITOR", None)
        if self.saved is not None:
            os.environ["CLINLOOP_MONITOR"] = self.saved

    def test_go_live_burst_pauses_nothing(self):
        _opened(self.store, HIGH, 200, days_ago=1)     # the first sync's back-fill
        report = rule_monitor.run(self.store, NOW)
        self.assertEqual(report["changes"], [])
        self.assertFalse(report["rules"][HIGH]["history_weeks_enough"])

    def test_volume_spike_alone_only_flags_a_rule(self):
        # A surge can be real (a screening campaign, a new clinic): it never hides a rule by itself
        _usual(self.store, HIGH)
        _opened(self.store, HIGH, 20, days_ago=2)
        report = rule_monitor.run(self.store, NOW)
        self.assertEqual([c["state"] for c in report["changes"]], ["flagged"])
        self.assertEqual(self.store.paused_rules(), set())
        self.assertIsNone(governance.live_rule_ids(self.store))            # still alerting

    def test_dismissals_after_a_flag_pause_the_rule_and_take_new_loops_off_the_worklist(self):
        _usual(self.store, HIGH)
        _opened(self.store, HIGH, 20, days_ago=2)
        rule_monitor.run(self.store, NOW)
        _decided(self.store, HIGH, dismissed=9, kept=3)
        report = rule_monitor.run(self.store, NOW + timedelta(minutes=5))
        self.assertEqual([c["state"] for c in report["changes"]], ["paused"])
        self.assertNotIn(HIGH, governance.live_rule_ids(self.store))
        self.assertIn("rule_paused", [a["action"] for a in self.store.audit_trail(limit=5)])
        self.assertTrue(self.store.verify_audit_chain())

    def test_paused_rule_keeps_work_in_progress_visible(self):
        self.store.set_monitor_state(HIGH, "paused", "test", {}, "rule-monitor")
        loops = [{"rule_id": HIGH, "workflow_state": "new"}, {"rule_id": HIGH, "workflow_state": "acknowledged"},
                 {"rule_id": HIGH, "workflow_state": "deferred"}, {"rule_id": CRITICAL, "workflow_state": "new"}]
        shown, held = governance.visible_loops(self.store, loops)
        self.assertEqual(held, 1)
        self.assertEqual([l["workflow_state"] for l in shown if l["rule_id"] == HIGH], ["acknowledged", "deferred"])

    def test_critical_rule_is_flagged_never_paused(self):
        _usual(self.store, CRITICAL)
        _opened(self.store, CRITICAL, 30, days_ago=2)
        report = rule_monitor.run(self.store, NOW)
        self.assertEqual([c["state"] for c in report["changes"]], ["flagged"])
        self.assertEqual(self.store.paused_rules(), set())
        self.assertIn(CRITICAL, governance.summary(self.store)["flagged_rules"])

    def test_mostly_dismissed_alerts_pause_the_rule(self):
        _decided(self.store, HIGH, dismissed=8, kept=4)
        self.assertEqual(rule_monitor.run(self.store, NOW)["changes"][0]["state"], "paused")
        other = LoopStore()
        _decided(other, HIGH, dismissed=3, kept=9)       # a few dismissals are normal
        self.assertEqual(rule_monitor.run(other, NOW)["changes"], [])

    def test_resume_needs_a_note_and_holds_for_the_cooldown(self):
        _usual(self.store, HIGH)
        _opened(self.store, HIGH, 20, days_ago=2)
        _decided(self.store, HIGH, dismissed=9, kept=3)
        rule_monitor.run(self.store, NOW)
        self.assertEqual(self.store.paused_rules(), {HIGH})
        with self.assertRaises(WorkflowError):
            rule_monitor.resume(self.store, HIGH, "it.admin", "admin", "ok", now=NOW)
        rule_monitor.resume(self.store, HIGH, "it.admin", "admin", "Lab code change found and mapping fixed", now=NOW)
        self.assertEqual(self.store.paused_rules(), set())
        self.assertEqual(rule_monitor.run(self.store, NOW + timedelta(hours=1))["changes"], [])   # cool-down
        # After the cool-down the same dismissals (still within 4 weeks) pause it again
        later = rule_monitor.run(self.store, NOW + timedelta(days=8))
        self.assertEqual([c["state"] for c in later["changes"]], ["paused"])
        with self.assertRaises(WorkflowError):
            rule_monitor.resume(self.store, "R003", "it.admin", "admin", "nothing to resume", now=NOW)

    def test_report_only_mode_changes_nothing(self):
        os.environ["CLINLOOP_MONITOR"] = "0"
        _usual(self.store, HIGH)
        _opened(self.store, HIGH, 20, days_ago=2)
        report = rule_monitor.run(self.store, NOW)
        self.assertFalse(report["acting"])
        self.assertEqual(len(report["changes"]), 1)
        self.assertEqual(self.store.monitor_state(), {})


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


def _h(role):
    return {"Authorization": "Bearer " + {"admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
                                          "viewer": "test-viewer-token-0123456789"}[role]}


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestRuleMonitorAPI(unittest.TestCase):

    def setUp(self):
        self.saved = os.environ.pop("CLINLOOP_ENFORCE_SIGNOFF", None)
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.client = TestClient(app)
        with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
            self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00", json=json.load(f), headers=_h("admin"))

    def tearDown(self):
        if self.saved is not None:
            os.environ["CLINLOOP_ENFORCE_SIGNOFF"] = self.saved

    def test_paused_rule_leaves_the_worklist_until_resumed(self):
        before = {l["rule_id"] for l in self.client.get("/api/v1/worklist", headers=_h("viewer")).json()["loops"]}
        self.assertIn(HIGH, before)
        self.store.set_monitor_state(HIGH, "paused", "test", {}, "rule-monitor")
        wl = self.client.get("/api/v1/worklist", headers=_h("viewer")).json()
        self.assertNotIn(HIGH, {l["rule_id"] for l in wl["loops"]})
        self.assertEqual(wl["governance"]["paused_rules"], [HIGH])
        self.assertGreater(wl["shadow_count"], 0)
        self.assertEqual(self.client.post(f"/api/v1/governance/rules/{HIGH}/resume", json={"note": "checked"},
                                          headers=_h("clinician")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/v1/governance/rules/{HIGH}/resume", json={"note": "no"},
                                          headers=_h("admin")).status_code, 409)
        r = self.client.post(f"/api/v1/governance/rules/{HIGH}/resume", json={"note": "Reviewed with the lab"},
                             headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(HIGH, {l["rule_id"] for l in self.client.get("/api/v1/worklist", headers=_h("viewer")).json()["loops"]})

    def test_monitor_report_is_readable_and_runnable(self):
        r = self.client.get("/api/v1/governance/monitor", headers=_h("viewer"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(HIGH, r.json()["rules"])
        self.assertNotIn("SYN-", json.dumps(r.json()))                    # counts only, no patient data
        self.assertEqual(self.client.post("/api/v1/governance/monitor/run", headers=_h("viewer")).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/governance/monitor/run", headers=_h("admin")).json()["changes"], [])


if __name__ == "__main__":
    unittest.main()
