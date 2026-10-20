"""
test_demo_reader.py — Public demo of rules vs the second reader: catalogue only, bounded live use.
Synthetic reports; the model is a stand-in.
"""
import json
import os
import sys
import threading
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from src.clinloop_engine import demo_reader  # noqa: E402
from src.clinloop_engine.api import app  # noqa: E402

DEMO = {"CLINLOOP_DEMO": "1"}


def stand_in(answer):
    return lambda p, s: {"text": json.dumps(answer), "model": "stand-in"}


class TestDemoReader(unittest.TestCase):

    def setUp(self):
        demo_reader._recent.clear()
        self.client = TestClient(app)

    def test_off_outside_demo_mode(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_DEMO": ""}):
            self.assertEqual(self.client.get("/api/v1/demo/reports").status_code, 404)
            self.assertEqual(self.client.post("/api/v1/demo/reports/M008/live").status_code, 404)

    def test_catalogue_and_case(self):
        with mock.patch.dict(os.environ, DEMO):
            cases = self.client.get("/api/v1/demo/reports").json()["cases"]
            self.assertGreaterEqual(len(cases), 5)
            self.assertEqual(self.client.get("/api/v1/demo/reports/not-a-case").status_code, 404)
            c = self.client.get("/api/v1/demo/reports/M008").json()
        self.assertEqual(c["model_reading"]["items"][0]["category"], "critical_finding")
        self.assertTrue(c["model_reading"]["items"][0]["agreement"].startswith("also tracked"))
        for it in c["model_reading"]["items"]:
            self.assertIn(it["quote"].lower(), c["text"].lower())      # every shown quote is in the report

    def test_catalogue_captions_hold_against_todays_rules(self):
        """The page's captions ("rule and MedGemma agree", "MedGemma adds …") are checked, not asserted."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import build_demo_reports as b
        for case_ in demo_reader.catalog()["cases"]:
            claim = next(k for cid, k, _ in b.PICKS if cid == case_["id"])
            b._check(case_["id"], claim, dict(case_, expected_rules=[] if claim in ("model_false", "nothing") else ["x"]),
                     case_["saved_reading"]["items"])

    def test_no_free_text_route(self):
        with mock.patch.dict(os.environ, DEMO):
            r = self.client.post("/api/v1/demo/reports/M008/live", json={"text": "my own report"})
        self.assertNotIn("my own report", r.text)

    def test_live_read_with_quota(self):
        c = demo_reader.case("M008")
        quote = c["text"].split("\n")[0][:40]
        with mock.patch.dict(os.environ, dict(DEMO, CLINLOOP_DEMO_LIVE_PER_HOUR="2")):
            for _ in range(2):
                out = demo_reader.live_read(c, "visitor-a", model=stand_in({"items": [{"category": "imaging_followup", "quote": quote}]}))
                self.assertTrue(out["available"])
            with self.assertRaises(demo_reader.Busy):
                demo_reader.live_read(c, "visitor-a", model=stand_in({"items": []}))
            self.assertTrue(demo_reader.live_read(c, "visitor-b", model=stand_in({"items": []}))["available"])

    def test_queue_full_is_busy_not_substituted(self):
        c = demo_reader.case("M008")
        demo_reader._slot.acquire()                        # another visitor's job is running
        try:
            with mock.patch.dict(os.environ, dict(DEMO, CLINLOOP_DEMO_QUEUE="0")):
                with self.assertRaises(demo_reader.Busy):
                    demo_reader.live_read(c, "visitor-c", model=stand_in({"items": []}))
        finally:
            demo_reader._slot.release()

    def test_missing_model_reports_unavailable(self):
        c = demo_reader.case("M008")
        with mock.patch.dict(os.environ, DEMO), \
                mock.patch("src.clinloop_engine.second_reader.local_model", return_value=None), \
                mock.patch("src.clinloop_engine.local_llm_engine.get_second_reader_model", return_value=None):
            out = demo_reader.live_read(c, "visitor-d")
        self.assertFalse(out["available"])

    def test_visitor_key_is_hashed(self):
        demo_reader.quota_left("203.0.113.9")
        self.assertNotIn("203.0.113.9", "".join(demo_reader._recent.keys()))


if __name__ == "__main__":
    unittest.main()
