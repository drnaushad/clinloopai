"""The public evidence artifact must contain aggregates, never arbitrary source fields."""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('validation_status',Path(__file__).parents[1]/'scripts/build_validation_status.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class TestValidationStatus(unittest.TestCase):
    def test_only_allowlisted_counts_are_published(self):
        source={'records':1,'patient_name':'SYNTHETIC-DO-NOT-PUBLISH','processing':{name:{'records':1,'available':1,'flagged':0,'report_text':'SYNTHETIC-DO-NOT-PUBLISH'} for name in ['rules','medgemma:27b','medgemma:4b','exaone3.5:7.8b']}}
        result=m.build({'patients':1,'resources':2,'events':1,'mapping_warnings':0},source,{}, {}, {}, {})
        import json
        self.assertNotIn('SYNTHETIC-DO-NOT-PUBLISH',json.dumps(result))
        self.assertFalse(result['epic']['bulk_export_passed'])
        self.assertIn('not established',result['clinical_accuracy'])

    def test_a_string_cannot_be_smuggled_as_a_public_count(self):
        with self.assertRaises(ValueError):m.count('SYNTHETIC-DO-NOT-PUBLISH')
        with self.assertRaises(ValueError):m.count(True)

    def test_report_check_drops_case_text_and_arbitrary_fields(self):
        fields = ['reports','exact_matches','true_positive_obligations','false_positive_obligations',
                  'false_negative_obligations','negative_reports','true_negative_reports',
                  'deadline_eligible_reports','deadlines_within_strict_reference_window',
                  'exact_mismatches','mismatches_with_harness_group_equivalence']
        source = {'counts': dict.fromkeys(fields, 1), 'report_text': 'PRIVATE-REPORT',
                  'reference_review_counts': {'reviewer_1.csv': {'completed_labels': 0},
                                             'reviewer_2.csv': {'completed_labels': 0}}}
        result = m.report_check(source, {'processing': {'rules': {'records': 1, 'available': 1, 'flagged': 0, 'text': 'PRIVATE-REPORT'}}}, {'folders_checked': 2})
        import json
        self.assertNotIn('PRIVATE-REPORT', json.dumps(result))
        self.assertEqual(result['reference_reviews_complete'], 0)
        self.assertIn('not established', result['clinical_accuracy'])
