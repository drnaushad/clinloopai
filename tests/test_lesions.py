"""
test_lesions.py — The same lung nodule linked across reports; growth the reports do not state (R056). Synthetic.
"""

import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.motifs import volume_doubling_days  # noqa: E402
from src.clinloop_engine.radiology import _lung_nodules  # noqa: E402

PT = {"resourceType": "Patient", "id": "L", "gender": "male", "birthDate": "1957-05-01"}


def ct(rid, when, text):
    return {"resourceType": "DiagnosticReport", "id": rid, "status": "final", "category": [{"coding": [{"code": "RAD"}]}],
            "code": {"text": "CT chest without contrast"}, "subject": {"reference": "Patient/L"},
            "effectiveDateTime": when, "conclusion": text}


def run(resources, when=datetime(2026, 10, 8)):
    events, _ = bundle_to_events(resources)
    evs = events.get("L", [])
    dets = ClinLoopDetector(evaluation_time=when).process_patient("t", "L", evs)
    return {d.rule_id: d.loop_status for d in dets}, [e for e in evs if (e["details"] or {}).get("pattern") == "nodule-growth"]


class TestLesionTracking(unittest.TestCase):

    def test_location_is_read_per_nodule(self):
        got = [(n["size_mm"], n["lobe"]) for n in _lung_nodules(
            "6 mm solid nodule in the right upper lobe. 4 mm nodule in the left lower lobe.", "CT chest")]
        self.assertEqual(got, [(6.0, "RUL"), (4.0, "LLL")])

    def test_stable_wording_does_not_hide_measured_growth(self):
        rules, pats = run([PT, ct("c1", "2025-03-01T09:00:00Z", "6 mm solid nodule in the right upper lobe."),
                           ct("c2", "2026-03-01T09:00:00Z", "Stable 8 mm solid nodule in the right upper lobe.")])
        self.assertEqual(rules.get("R056"), "open")
        d = pats[0]["details"]
        self.assertEqual(d["nodule_growth_mm"], 2)
        self.assertIn("calls it stable", d["evidence_span"])
        self.assertEqual(len(d["evidence_events"]), 2)
        self.assertIsNotNone(d["volume_doubling_days"])

    def test_slow_growth_over_three_scans(self):
        rules, pats = run([PT, ct("c1", "2024-03-01T09:00:00Z", "6 mm RUL nodule."),
                           ct("c2", "2025-03-01T09:00:00Z", "7 mm RUL nodule, unchanged."),
                           ct("c3", "2026-03-01T09:00:00Z", "8 mm RUL nodule, unchanged.")])
        self.assertEqual(rules.get("R056"), "open")
        self.assertEqual(pats[0]["details"]["lesion"]["sizes_mm"], [6.0, 7.0, 8.0])

    def test_different_lobes_are_different_lesions(self):
        rules, pats = run([PT, ct("c1", "2025-03-01T09:00:00Z", "6 mm nodule in the right upper lobe."),
                           ct("c2", "2026-03-01T09:00:00Z", "Stable 6 mm right upper lobe nodule. "
                                                            "New 9 mm nodule in the left lower lobe.")])
        self.assertEqual(pats, [])

    def test_report_that_states_growth_is_left_to_r046(self):
        rules, pats = run([PT, ct("c1", "2025-03-01T09:00:00Z", "6 mm RUL nodule."),
                           ct("c2", "2026-03-01T09:00:00Z", "RUL nodule has grown, now 9 mm.")])
        self.assertEqual(pats, [])
        self.assertIn("R046", rules)

    def test_pet_or_referral_closes_it(self):
        pet = {"resourceType": "ImagingStudy", "id": "p1", "status": "available", "subject": {"reference": "Patient/L"},
               "started": "2026-03-20T09:00:00Z", "modality": [{"code": "PT"}],
               "series": [{"modality": {"code": "PT"}, "bodySite": {"display": "CHEST"}}]}
        rules, _ = run([PT, ct("c1", "2025-03-01T09:00:00Z", "6 mm RUL nodule."),
                        ct("c2", "2026-03-01T09:00:00Z", "Stable 8 mm RUL nodule."), pet])
        self.assertEqual(rules.get("R056"), "closed")

    def test_volume_doubling_time(self):
        self.assertAlmostEqual(volume_doubling_days(6, 8, 365), 293, delta=1)
        self.assertIsNone(volume_doubling_days(8, 6, 365))


if __name__ == "__main__":
    unittest.main()
