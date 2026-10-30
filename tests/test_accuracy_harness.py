"""Engineering fixtures, not clinical reference labels."""
from copy import deepcopy
import unittest
from src.validation.accuracy_harness import evaluate_cohort, assert_group_separation


class AccuracyHarnessTests(unittest.TestCase):
    def rows(self):
        return [dict(id='A',patient_group='P1',report_type='radiology',language='en',expected_rules=['R1'],
                     prediction=dict(status='accepted',rules=['R1'])),
                dict(id='B',patient_group='P1',report_type='pathology',language='ko',expected_rules=[],
                     prediction=dict(status='review_required',rules=[])),
                dict(id='C',patient_group='P2',report_type='radiology',language='en',expected_rules=['R1'],
                     prediction=dict(status='unavailable',rules=[])),
                dict(id='D',patient_group='P3',report_type='radiology',language='en',expected_rules=[],
                     prediction=dict(status='accepted',rules=[]))]

    def score(self,rows,**kwargs):
        return evaluate_cohort(rows,['A','B','C','D'],['R1','R2'],reference_scope='synthetic test',reps=100,**kwargs)

    def test_abstention_never_becomes_a_negative_or_disappears(self):
        r=self.score(self.rows());m=r['metrics']
        self.assertEqual(m['eligible_cases'],4);self.assertEqual(m['coverage'],.5)
        self.assertEqual(m['recall_all_eligible'],.5)
        self.assertEqual(m['per_rule']['R1']['tn'],1)
        self.assertEqual(m['per_rule']['R1']['negative_abstention'],1)
        self.assertEqual(m['report_confusion']['negative']['review_required'],1)
        self.assertEqual(r['by_report_type']['pathology']['accepted_cases'],0)

    def test_incomplete_reference_unknown_label_and_duplicate_keys_refused(self):
        for change in (dict(expected_rules=None),dict(expected_rules=['UNKNOWN']),dict(id='B'),
                       dict(prediction=dict(status='accepted',rules=['UNKNOWN'])),
                       dict(prediction=dict(status='unavailable',rules=['R1'])),
                       dict(prediction=dict(status='negative',rules=[]))):
            rows=self.rows();rows[0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.score(rows)
        with self.assertRaises(ValueError):self.score(self.rows()[1:])
        with self.assertRaises(ValueError):self.score(self.rows(),sampling_frame='engine_detected')

    def test_cluster_intervals_retain_all_reports_and_are_deterministic(self):
        a=self.score(self.rows());b=self.score(list(reversed(self.rows())))
        self.assertEqual(a['intervals'],b['intervals'])
        self.assertEqual(a['intervals']['patient_groups'],3)
        self.assertEqual(a['intervals']['seed'],42)
        rows=self.rows()
        for row in rows:row.pop('patient_group')
        self.assertFalse(self.score(rows)['intervals']['available'])

    def test_single_cluster_and_zero_positive_reference_have_no_sensitivity_interval(self):
        rows=self.rows()
        for row in rows:row['patient_group']='ONE_PATIENT'
        self.assertFalse(self.score(rows)['intervals']['available'])
        rows=self.rows()
        for row in rows:
            row['expected_rules']=[]
            row['prediction']=dict(status='accepted',rules=[])
        result=self.score(rows)
        self.assertIsNone(result['metrics']['recall_all_eligible'])
        self.assertNotIn('recall_all_eligible',result['intervals']['ci95'])
        self.assertIsNone(result['metrics']['report_sensitivity_all_eligible'])
        self.assertNotIn('report_sensitivity_all_eligible',result['intervals']['ci95'])

    def test_false_closure_and_unknown_state_are_explicit(self):
        rows=self.rows();rows[0]['expected_statuses']={'R1':'pending'}
        rows[0]['prediction']['loop_statuses']={'R1':'done'}
        self.assertEqual(self.score(rows)['metrics']['false_closures'],1)
        self.assertEqual(self.score(rows)['metrics']['exact_status_cases'],0)
        self.assertEqual(self.score(rows)['metrics']['longitudinal_eligible_cases'],1)
        rows[0]['prediction']['loop_statuses']={'R1':'closed-ish'}
        with self.assertRaises(ValueError):self.score(rows)

    def test_patient_and_duplicate_text_leakage_are_rejected(self):
        records=[dict(partition='development',patient_group='P1',text='No acute disease'),
                 dict(partition='evaluation',patient_group='P2',text=' no  ACUTE disease ')]
        with self.assertRaises(ValueError):assert_group_separation(records)
        records[1]['text']='Different';records[1]['patient_group']='P1'
        with self.assertRaises(ValueError):assert_group_separation(records)
        records[1]['patient_group']='P2';assert_group_separation(records)
        rows=self.rows()
        for row in rows:row['partition']='evaluation'
        with self.assertRaises(ValueError):
            self.score(rows,development_records=[dict(partition='development',patient_group='P1')])
        result=self.score(rows,development_records=[dict(partition='development',patient_group='P99')])
        self.assertTrue(result['split_check_performed'])
        self.assertFalse(result['patient_independence_established'])

    def test_legacy_fixture_references_are_explicit_and_unknown_labels_refused(self):
        import importlib.util
        root=__import__('pathlib').Path(__file__).resolve().parent/'report_eval'
        for name,case in [('run_eval',dict(id='A',expected_rules=[])),('run_timelines',dict(id='A',expected={}))]:
            spec=importlib.util.spec_from_file_location(name,root/(name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.validate_cases([case])
            with self.assertRaises(ValueError):module.validate_cases([])
            with self.assertRaises(ValueError):module.validate_cases([case,case])
            bad=dict(case)
            bad['expected_rules' if name=='run_eval' else 'expected']=['UNKNOWN'] if name=='run_eval' else {'UNKNOWN':'done'}
            with self.assertRaises(ValueError):module.validate_cases([bad])

    def test_empty_cohort_does_not_claim_perfect_accuracy(self):
        with self.assertRaises(ValueError):
            evaluate_cohort([],[],['R1'],reference_scope='synthetic')

if __name__=='__main__':unittest.main()
