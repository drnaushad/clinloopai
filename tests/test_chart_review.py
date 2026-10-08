"""
test_chart_review.py — Stage 1 chart-review validation toolkit
"""

import csv
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.validation import chart_review as cr

EVAL = "2026-09-01T00:00:00"


def _bundle():
    with open(os.path.join(ROOT, "data", "fhir_example_bundle.json"), encoding="utf-8") as f:
        return json.load(f)


def _key_rows(sample):
    return [{k: str(r[k]) for k in cr.KEY_FIELDS} for r in sample]


def _packet(sample, answer_fn):
    """Simulated reviewers: answer_fn(row) → (reviewer_1, reviewer_2, adjudicator)."""
    rows = []
    for r in sample:
        r1, r2, adj = answer_fn(r)
        rows.append({"review_id": r["review_id"], "reviewer_1": r1, "reviewer_2": r2, "adjudicator": adj})
    return rows


class TestChartReview(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.frame = cr.build_frame(_bundle(), EVAL)
        cls.sample = cr.stratified_sample(cls.frame, per_stratum=1)

    def test_frame_has_both_predicted_classes(self):
        classes = {r["predicted_positive"] for r in self.frame}
        self.assertEqual(classes, {True, False})

    def test_weights_reconstruct_the_population(self):
        self.assertAlmostEqual(sum(r["weight"] for r in self.sample), len(self.frame))

    def test_sampling_is_reproducible(self):
        again = cr.stratified_sample(self.frame, per_stratum=1)
        self.assertEqual([r["trigger_event_id"] for r in again], [r["trigger_event_id"] for r in self.sample])

    def test_packet_is_blinded(self):
        with tempfile.TemporaryDirectory() as d:
            packet, key = cr.export_review_files(self.sample, d, cr._rule_lookup())
            with open(packet, encoding="utf-8") as f:
                header = next(csv.reader(f))
            self.assertFalse({"predicted_status", "predicted_positive", "weight", "stratum"} & set(header))
            self.assertIn("predicted_status", open(key, encoding="utf-8").readline())

    def test_perfect_engine_and_reviewers(self):
        # Reviewers agree with the truth, and the truth equals the prediction
        packet = _packet(self.sample, lambda r: ("no", "no", "") if r["predicted_positive"] else ("yes", "yes", ""))
        result = cr.analyze(packet, _key_rows(self.sample), reps=200)
        self.assertEqual(result["estimates"], {"sensitivity": 1.0, "specificity": 1.0, "ppv": 1.0, "npv": 1.0})
        self.assertAlmostEqual(result["cohens_kappa"], 1.0)

    def test_missed_loop_lowers_sensitivity(self):
        # One loop ClinLoop called closed was actually not done in time
        neg = next(r["review_id"] for r in self.sample if not r["predicted_positive"])
        packet = _packet(self.sample, lambda r: ("no", "no", "") if r["predicted_positive"] or r["review_id"] == neg
                         else ("yes", "yes", ""))
        result = cr.analyze(packet, _key_rows(self.sample), reps=200)
        self.assertLess(result["estimates"]["sensitivity"], 1.0)
        self.assertEqual(result["estimates"]["specificity"], 1.0)

    def test_disagreements_and_unclear_handling(self):
        ids = [r["review_id"] for r in self.sample]
        answers = {ids[0]: ("yes", "no", "no"),      # resolved by adjudicator
                   ids[1]: ("yes", "no", ""),        # unresolved
                   ids[2]: ("unclear", "unclear", "")}
        packet = _packet(self.sample, lambda r: answers.get(r["review_id"], ("no", "no", "")))
        merged, excluded = cr.merge_reviews(packet, _key_rows(self.sample))
        self.assertEqual(excluded["disagreement_unresolved"], 1)
        self.assertEqual(excluded["unclear"], 1)
        self.assertEqual(len(merged), len(self.sample) - 2)
        self.assertLess(cr.analyze(packet, _key_rows(self.sample), reps=50)["cohens_kappa"], 1.0)

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = os.path.join(d, "bundle.json")
            json.dump(_bundle(), open(bundle, "w", encoding="utf-8"))
            self.assertEqual(cr.main(["sample", "--fhir", bundle, "--out", d,
                                      "--per-stratum", "2", "--evaluation-time", EVAL]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "review_packet.csv")))


if __name__ == "__main__":
    unittest.main()
