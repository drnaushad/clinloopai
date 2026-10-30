"""Synthetic loader checks: missing evidence must never become benchmark truth."""
import json
import tempfile
import unittest
from pathlib import Path
from src.data_loader import ClinicalDataLoader


class TestResearchDataIntegrity(unittest.TestCase):
    def test_missing_or_empty_dataset_never_substitutes_synthetic_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for target in (base / 'missing', base):
                with self.assertRaises(ValueError):
                    ClinicalDataLoader(str(target)).load_all()
                self.assertEqual(list(base.iterdir()), [])

    def test_missing_reference_status_is_never_a_closed_control(self):
        loader = ClinicalDataLoader()
        row = loader.generate(1, save=False)[0].to_dict()
        self.assertEqual(loader._scenario_from_dict(row).ground_truth_status, row['ground_truth_status'])
        for bad in (None, '', 'unknown'):
            with self.subTest(status=bad), self.assertRaises(ValueError):
                loader._scenario_from_dict(dict(row, ground_truth_status=bad))
        row.pop('ground_truth_status')
        with self.assertRaises(ValueError):
            loader._scenario_from_dict(row)
