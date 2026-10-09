"""
test_ai_triage.py — R057: a critical imaging-AI finding on a study not yet reported → read the study now.

Synthetic resources only.
"""

import os
import sys
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from src.clinloop_engine.imaging_fhir import ai_observation_resource, imaging_study_resource  # noqa: E402
from test_imaging import P, loops, rad  # noqa: E402


class TestCriticalFindingOnUnreadStudy(unittest.TestCase):

    def setUp(self):
        self.study = imaging_study_resource({"study_uid": "7.7", "modalities": ["CT"], "body_part": "HEAD",
                                             "description": "CT head without contrast",
                                             "study_date": "20260110", "study_time": "080000"}, "P", "pacs-scan")
        self.ref = "ImagingStudy/" + self.study["id"]

    def ai(self, label="Intracranial hemorrhage", score=0.96, when="2026-01-10T08:05:00",
           regulatory="MFDS approved (Class III)", product="Vendor ICH"):
        return ai_observation_resource("P", label, score, True, product, "2.0", regulatory, self.ref, when)

    def report(self, text, when="2026-01-10T08:40:00Z", rid="r1"):
        return rad(rid, when, "CT head without contrast", text, self.ref)

    def run_at(self, resources, when):
        statuses, dets = loops([P, self.study] + resources, when)
        return statuses, {d.rule_id: d for d in dets}

    def test_unreported_study_must_be_read_within_an_hour(self):
        statuses, dets = self.run_at([self.ai()], datetime(2026, 1, 10, 8, 20))
        self.assertEqual(statuses, {"R057": "open"})
        d = dets["R057"]
        due = (datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds() / 60
        self.assertAlmostEqual(due, 60, delta=1)
        self.assertTrue(any("no radiology report yet" in line for line in d.evidence_chain))
        later, _ = self.run_at([self.ai()], datetime(2026, 1, 10, 10, 0))
        self.assertIn(later["R057"], ("overdue", "open"))
        self.assertNotIn("R047", later)                     # nothing to compare until a report exists

    def test_report_that_addresses_it_closes_everything(self):
        statuses, _ = self.run_at([self.ai(), self.report("Acute 1.5 cm right parietal intraparenchymal hemorrhage.")],
                                  datetime(2026, 1, 10, 12, 0))
        self.assertEqual(statuses["R057"], "closed")
        self.assertNotIn("R047", statuses)                  # the report addressed the finding
        self.assertIn("R035", statuses)                     # the report's own critical result must still be communicated

    def test_report_that_misses_it_closes_the_read_but_opens_the_second_look(self):
        statuses, _ = self.run_at([self.ai(), self.report("No acute intracranial abnormality.")], datetime(2026, 1, 10, 12, 0))
        self.assertEqual(statuses["R057"], "closed")
        self.assertEqual(statuses["R047"], "open")

    def test_study_already_reported_raises_no_urgent_read(self):
        statuses, _ = self.run_at([self.report("Small acute subdural hematoma.", when="2026-01-10T08:30:00Z"),
                                   self.ai(when="2026-01-10T09:00:00")], datetime(2026, 1, 10, 12, 0))
        self.assertNotIn("R057", statuses)

    def test_non_critical_findings_wait_for_the_report(self):
        study = imaging_study_resource({"study_uid": "7.8", "modalities": ["DX"], "body_part": "CHEST",
                                        "study_date": "20260110", "study_time": "080000"}, "P", "pacs-scan")
        nodule = ai_observation_resource("P", "Nodule", 0.9, True, "Vendor CXR", "3", "MFDS approved",
                                         "ImagingStudy/" + study["id"], "2026-01-10T08:05:00")
        statuses, _ = loops([P, study, nodule], datetime(2026, 1, 10, 12, 0))
        self.assertEqual(statuses, {})

    def test_research_products_raise_nothing_unless_allowed(self):
        statuses, _ = self.run_at([self.ai(regulatory="Research use only")], datetime(2026, 1, 10, 12, 0))
        self.assertEqual(statuses, {})

    def test_one_urgent_read_per_study(self):
        statuses, dets = self.run_at([self.ai(), self.ai(label="Pneumothorax", product="Vendor ICH")],
                                     datetime(2026, 1, 10, 8, 20))
        self.assertEqual(statuses, {"R057": "open"})

    def test_hospital_sets_the_read_time(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_AI_CRITICAL_READ_MINUTES": "30"}):
            _, dets = self.run_at([self.ai()], datetime(2026, 1, 10, 8, 20))
        d = dets["R057"]
        self.assertAlmostEqual((datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds() / 60,
                               30, delta=1)


if __name__ == "__main__":
    unittest.main()
