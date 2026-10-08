"""test_report_validation.py — report-level validation tool (blind labelling sheet → sensitivity / PPV)"""

import csv
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.validation.report_validation import main, score, template_rows, wilson  # noqa: E402


class TestReportValidation(unittest.TestCase):

    def test_synthetic_sheet_scores(self):
        with open(os.path.join(ROOT, "data", "radiology_validation_synthetic.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        result = score(rows)
        self.assertEqual(result["reports"], len(rows))
        self.assertEqual(result["discordant"], [])

    def test_disagreements_are_listed(self):
        rows = [{"report_id": "X1", "study": "CT chest", "report_date": "2026-01-10",
                 "conclusion": "9 mm solid nodule in the right lower lobe.", "expected_rules": ""},
                {"report_id": "X2", "study": "CT chest", "report_date": "2026-01-10",
                 "conclusion": "No nodule.", "expected_rules": "R003"}]
        result = score(rows)
        self.assertEqual(result["per_rule"]["R003"], {**result["per_rule"]["R003"], "tp": 0, "fp": 1, "fn": 1})
        self.assertEqual([d["report_id"] for d in result["discordant"]], ["X1", "X2"])

    def test_unknown_rule_is_an_error(self):
        with self.assertRaises(ValueError):
            score([{"report_id": "X", "study": "CT", "conclusion": "", "expected_rules": "R999"}])

    def test_wilson_interval(self):
        p, lo, hi = wilson(9, 10)
        self.assertEqual(p, 0.9)
        self.assertTrue(0.55 < lo < 0.6 and 0.98 < hi <= 1.0)
        self.assertEqual(wilson(0, 0), (None, None, None))

    def test_template_is_blind_and_deidentified(self):
        bundle = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "P", "birthDate": "1960-05-01", "gender": "male"}},
            {"resource": {"resourceType": "DiagnosticReport", "id": "r", "category": [{"coding": [{"code": "RAD"}]}],
                          "code": {"text": "CT chest"}, "subject": {"reference": "Patient/P"},
                          "effectiveDateTime": "2026-01-10T09:00:00Z",
                          "conclusion": "9 mm nodule. Call 010-1234-5678 with questions."}}]}
        rows = template_rows(bundle)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expected_rules"], "")
        self.assertNotIn("010-1234-5678", rows[0]["conclusion"])
        self.assertEqual(rows[0]["age"], "66")

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            sheet, out = os.path.join(d, "sheet.csv"), os.path.join(d, "result.json")
            main(["template", "--fhir", os.path.join(ROOT, "data", "radiology_test_bundle.json"), "--out", sheet])
            main(["score", "--sheet", sheet, "--out", out])
            with open(out, encoding="utf-8") as f:
                self.assertIn("overall", json.load(f))


if __name__ == "__main__":
    unittest.main()
