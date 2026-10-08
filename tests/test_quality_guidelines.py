"""
test_quality_guidelines.py — Hospital-wide follow-up breakdowns, and guideline-version tracking for rules.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from test_imaging import HAVE_API, _h  # noqa: E402

from src.clinloop_engine import governance  # noqa: E402
from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events, patient_strata  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore  # noqa: E402
from src.clinloop_engine.motifs import cha2ds2_vasc  # noqa: E402

RULE = {r.rule_id: r for r in OBLIGATION_RULES}


def loaded_store():
    with open(os.path.join(ROOT, "data", "radiology_test_bundle.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    events, _ = bundle_to_events(bundle)
    det = ClinLoopDetector(evaluation_time=datetime(2026, 10, 8))
    store = LoopStore()
    store.upsert_detections([d for p, e in events.items() for d in det.process_patient("t", p, e)],
                            strata=patient_strata(bundle))
    return store


class TestBreakdowns(unittest.TestCase):

    def test_rule_owner_and_strata_views(self):
        store = loaded_store()
        r = store.breakdowns(datetime(2026, 10, 8))
        self.assertEqual(r["loops"], sum(g["total"] for g in r["rules"]))
        self.assertTrue(r["bottlenecks"])
        top = r["bottlenecks"][0]
        self.assertGreater(top["overdue"], 0)
        self.assertNotIn("within", top["top_missing"])           # the step, not each loop's own deadline
        for g in r["rules"]:
            self.assertLessEqual(g["active"] + g["closed_on_time"] + g["closed_late"] + g["closed_by_clinician"]
                                 + g["deferred"], g["total"])
            self.assertLessEqual(g["overdue"], g["active"])
            if g["on_time_rate"] is not None:
                self.assertTrue(0 <= g["on_time_rate"] <= 1)
        self.assertIn("sex", r["strata"])
        self.assertEqual(sum(o["active"] for o in r["owners"]), sum(g["active"] for g in r["rules"]))

    def test_closing_a_loop_moves_it(self):
        store = loaded_store()
        before = store.breakdowns(datetime(2026, 10, 8))
        loop = store.worklist()[0]
        store.close(loop["loop_key"], "dr.kim", "Done at outside hospital (report scanned)")
        after = store.breakdowns(datetime(2026, 10, 8))
        b = next(g for g in before["rules"] if g["rule_id"] == loop["rule_id"])
        a = next(g for g in after["rules"] if g["rule_id"] == loop["rule_id"])
        self.assertEqual(a["active"], b["active"] - 1)
        self.assertEqual(a["closed_by_clinician"], b["closed_by_clinician"] + 1)


class TestGuidelineVersions(unittest.TestCase):

    def test_outdated_editions_are_flagged(self):
        flagged = {r.rule_id for r in OBLIGATION_RULES if any(not a["accepted"] for a in governance.guideline_alerts(r))}
        self.assertEqual(flagged, {"R013", "R025", "R054"})
        a = governance.guideline_alerts(RULE["R054"])[0]
        self.assertEqual((a["cited"], a["current"]), (2020, 2024))
        self.assertIn("CHA2DS2-VA", a["change"])

    def test_a_new_edition_flags_the_rules_and_acceptance_clears_it(self):
        reg = governance.load_guidelines()
        for g in reg["guidelines"]:
            if g["id"] == "fleischner":
                g["current"] = "2027"
            if g["id"] == "esc-af":
                g["accepted"] = {"R054": "Cardiology 2026-10-08: CHA2DS2-VASc kept (ACC/AHA 2023)"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(reg, f)
        try:
            with mock.patch.dict(os.environ, {"CLINLOOP_GUIDELINES": f.name}):
                fleischner = {r.rule_id for r in OBLIGATION_RULES
                              if any(a["guideline"] == "fleischner" for a in governance.guideline_alerts(r))}
                self.assertIn("R003", fleischner)
                af = governance.guideline_alerts(RULE["R054"])[0]
                self.assertTrue(af["accepted"])
        finally:
            os.unlink(f.name)

    def test_cha2ds2_va_variant(self):
        events = [{"event_type": "diagnosis", "timestamp": "2026-01-01T00:00:00",
                   "details": {"diagnosis": "Hypertension", "codes": ["I10"]}}]
        ctx = {"birth_date": datetime(1958, 1, 1), "sex": "female"}
        self.assertEqual(cha2ds2_vasc(events, ctx, datetime(2026, 6, 1))["score"], 3)
        with mock.patch.dict(os.environ, {"CLINLOOP_AF_SCORE": "cha2ds2_va"}):
            self.assertEqual(cha2ds2_vasc(events, ctx, datetime(2026, 6, 1))["score"], 2)


@unittest.skipUnless(HAVE_API, "API dependencies not installed")
class TestEndpoints(unittest.TestCase):

    def test_breakdowns_and_governance_payloads(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine import clinical_api
        from src.clinloop_engine.api import app
        clinical_api.set_store(loaded_store())
        c = TestClient(app)
        self.assertEqual(c.get("/api/v1/metrics/breakdowns").status_code, 401)
        r = c.get("/api/v1/metrics/breakdowns", headers=_h("viewer"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("bottlenecks", r.json())
        self.assertEqual(c.get("/api/v1/governance/summary").json()["guideline_updates"], ["R013", "R025", "R054"])
        rules = {x["rule_id"]: x for x in c.get("/api/v1/governance/rules").json()["rules"]}
        self.assertTrue(rules["R054"]["guideline_alerts"])
        self.assertEqual(c.get("/api/v1/governance/rule-check").json()["errors"], 0)


if __name__ == "__main__":
    unittest.main()
