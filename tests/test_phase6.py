"""
test_phase6.py — Basis a clinician can check, and loop outcome measures

Synthetic data only.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {"admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
          "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore  # noqa: E402

EVAL = datetime(2026, 9, 1)


def example_detections():
    with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
        events, _ = bundle_to_events(json.load(f))
    out = {}
    for pid, evs in events.items():
        for d in ClinLoopDetector(evaluation_time=EVAL).process_patient("t", pid, evs):
            out.setdefault(d.rule_id, d)
    return out


class TestBasis(unittest.TestCase):
    """Criterion 4 of non-device CDS: the clinician can rebuild the reason from the record and the rule."""

    @classmethod
    def setUpClass(cls):
        cls.d = example_detections()

    def test_report_finding_is_quoted_with_the_rule_deadline_and_reasoning(self):
        basis = self.d["R003"].basis
        self.assertTrue(basis[0].startswith("Finding: radiology report"))
        self.assertTrue(any("12 mm solid nodule" in b and b.startswith("The record says") for b in basis))
        self.assertTrue(any(b.startswith("Rule R003") and "follow-up CT" in b and "by 2026-" in b for b in basis))
        self.assertTrue(any("Fleischner" in b for b in basis if b.startswith("How this was worked out")))
        self.assertIn("Found in the record: no matching follow-up yet.", basis)
        self.assertTrue(basis[-1].startswith("Reference: Fleischner"))

    def test_lab_value_and_what_was_found(self):
        basis = self.d["R022"].basis
        self.assertTrue(basis[0].startswith("Finding: potassium 6.6 mmol/L (flagged critical)"))
        self.assertTrue(any(b.startswith("Found in the record: documented call") for b in basis))

    def test_no_raw_data_or_routing_notes(self):
        for d in self.d.values():
            text = " ".join(d.basis)
            self.assertNotIn("{'", text, d.rule_id)                      # no dict dumps
            self.assertNotIn("Observation→", text, d.rule_id)
            self.assertNotIn("code/text", text, d.rule_id)
            self.assertNotRegex(text, r"\b[a-z]+_[a-z_]+\b", d.rule_id)  # no internal codes like followup_ct

    def test_review_reason_is_stated(self):
        abstained = [d for d in self.d.values() if d.should_abstain]
        self.assertTrue(abstained)
        for d in abstained:
            self.assertTrue(d.basis[-1].startswith("Needs a person's review:"), d.rule_id)

    def test_quotes_are_whole_sentences_never_cut_words(self):
        """Clinical review: a character window cut 'Negative for high-grade dysplasia' to 'grade dysplasia',
        which reads as the opposite. The basis quotes whole sentences."""
        r009 = next(b for b in self.d["R009"].basis if b.startswith("The record says"))
        self.assertIn("Negative for high-grade dysplasia", r009)
        self.assertIn("Still missing: specialist referral.", self.d["R009"].basis)   # 'and' rule, part done

    def test_long_deadlines_show_a_date_and_review_reason_is_clinical(self):
        r003 = next(b for b in self.d["R003"].basis if b.startswith("Rule R003"))
        self.assertRegex(r003, r"by \d{4}-\d{2}-\d{2} \(")                    # no false clock time
        r022 = next(b for b in self.d["R022"].basis if b.startswith("Rule R022"))
        self.assertRegex(r022, r"by \d{4}-\d{2}-\d{2} \d{2}:\d{2} \(1 hour\)")   # a one-hour window keeps the time
        for d in self.d.values():
            self.assertNotIn("threshold", " ".join(d.basis), d.rule_id)

    def test_stored_and_served_with_the_loop(self):
        store = LoopStore()
        store.upsert_detections(list(self.d.values()))
        loop = next(l for l in store.worklist(include_inactive=True) if l["rule_id"] == "R003")
        self.assertEqual(loop["basis"], self.d["R003"].basis)
        from src.clinloop_engine.cds_hooks import _card
        card = _card(loop, "https://clinloop.local", EVAL)
        self.assertIn("- The record says:", card["detail"])
        self.assertNotIn("From:", card["detail"])


def fit(pid, closed_on=None):
    """A positive FIT (R017: colonoscopy within 90 days); optionally the colonoscopy."""
    ev = [{"event_id": f"fit-{pid}", "patient_id": pid, "event_type": "lab_result", "timestamp": "2026-03-01T09:00:00",
           "details": {"test": "FIT", "result": "positive"}, "status": "completed"}]
    if closed_on:
        ev.append({"event_id": f"col-{pid}", "patient_id": pid, "event_type": "colonoscopy",
                   "timestamp": closed_on, "details": {}, "status": "completed"})
    return ev


class TestOutcomes(unittest.TestCase):
    """Closed-loop accountability, checked by hand on three loops."""

    def test_acted_on_closed_late_dismissed_and_untouched(self):
        from unittest import mock
        from src.clinloop_engine import outcomes
        store = LoopStore()
        opened = datetime(2026, 7, 1, 8, 0)
        with mock.patch("src.clinloop_engine.loop_store.utc_now", return_value=opened):
            for pid in ("A", "B", "C"):
                store.upsert_detections(ClinLoopDetector(evaluation_time=opened).process_patient("t", pid, fit(pid)))
        key = {l["patient_id"]: l["loop_key"] for l in store.worklist() if l["rule_id"] == "R017"}
        with mock.patch("src.clinloop_engine.loop_store.utc_now", return_value=opened + timedelta(hours=6)):
            store.acknowledge(key["A"], "dr.kim")                                   # A: acted on after 6 h
        with mock.patch("src.clinloop_engine.loop_store.utc_now", return_value=opened + timedelta(hours=30)):
            store.defer(key["B"], "dr.lee", "duplicate", "same FIT as last week")    # B: dismissed
        later = datetime(2026, 7, 11, 8, 0)
        with mock.patch("src.clinloop_engine.loop_store.utc_now", return_value=later):   # A: colonoscopy recorded
            store.upsert_detections(ClinLoopDetector(evaluation_time=later).process_patient(
                "t", "A", fit("A", closed_on="2026-07-10T09:00:00")))
        m = outcomes.loop_outcomes(store, now=datetime(2026, 7, 20))
        r = m["rules"]["R017"]
        self.assertEqual(r["opened"], 3)
        self.assertEqual((r["acted_on"], r["median_hours_to_first_action"]), (2, 18.0))      # 6 h and 30 h
        self.assertEqual((r["closed_by_record"], r["closed_by_staff"]), (1, 0))
        self.assertEqual(r["median_days_to_closure"], 10.0)                               # 1 → 11 July
        self.assertEqual(r["closed_late"], 1)                                             # deadline was 30 May
        self.assertEqual((r["dismissed"], r["defer_reasons"]), (1, {"duplicate": 1}))
        self.assertEqual((r["open_past_deadline"], r["open_past_deadline_never_acted_on"]), (1, 1))  # C
        self.assertNotIn("A", json.dumps(m["overall"]))

    def test_endpoint_returns_counts_only(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine import clinical_api
        from src.clinloop_engine.api import app
        store = LoopStore()
        store.upsert_detections(list(example_detections().values()))
        clinical_api.set_store(store)
        body = TestClient(app).get("/api/v1/quality/outcomes",
                                   headers={"Authorization": f"Bearer {TOKENS['viewer']}"}).json()
        self.assertGreater(body["overall"]["opened"], 0)
        self.assertNotIn("SYN-", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
