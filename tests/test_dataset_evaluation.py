"""Synthetic evaluation fixtures only; these are not clinician accuracy labels."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.validation import dataset_evaluation as e


class TestDatasetEvaluation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        xml = self.root/'xml'; xml.mkdir()
        for i,text in enumerate(['9 mm lung nodule.', 'No acute findings.', 'No acute findings.', '']):
            (xml/f'{i}.xml').write_text('<root><AbstractText Label="IMPRESSION">'+text+'</AbstractText></root>')
        self.out = self.root/'study'
        self.manifest = e.prepare_openi(xml,self.out,2)
        self.records = json.loads((self.out/'records.json').read_text())

    def complete_reviews(self):
        for filename, reviewer in [('reviewer_1.csv','clinician-a'),('reviewer_2.csv','clinician-b')]:
            rows=[]
            for i,record in enumerate(self.records):
                rows.append(dict(record, reviewer_id=reviewer, reviewer_role='clinician',
                                 label_status='complete', expected_rules='R003' if i==0 else 'NONE'))
            e.write_sheet(self.out/filename,rows)
        e.private_json(self.out/'prediction_provenance.json', {'models':{'medgemma:27b':'synthetic-digest'}})
        rows=[]
        for i,record in enumerate(self.records):
            rows.append({'report_id':record['report_id'],'system':'rules','available':True,'action':i==0})
            rows.append({'report_id':record['report_id'],'system':'medgemma:27b','available':i!=0,'action':False if i else None})
        (self.out/'predictions.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')

    def test_sample_excludes_empty_and_exact_duplicates_and_is_blinded(self):
        self.assertEqual(self.manifest['counts']['empty_reports'],1)
        self.assertEqual(self.manifest['counts']['exact_duplicate_reports'],1)
        self.assertEqual(self.manifest['distinct_reports'],2)
        self.assertFalse(self.manifest['patient_independence_established'])
        self.assertEqual(self.out.stat().st_mode & 0o777,0o700)
        with (self.out/'reviewer_1.csv').open() as f:
            rows=list(csv.DictReader(f))
        self.assertTrue(all(not r['expected_rules'] and not r['label_status'] for r in rows))
        self.assertFalse(any('predicted' in key for key in rows[0]))
        with self.assertRaises(ValueError):
            e.prepare_openi(self.root/'xml',self.out,2)

    def test_blank_reviews_cannot_generate_accuracy(self):
        with self.assertRaises(ValueError):e.score_study(self.out)
        self.assertFalse((self.out/'accuracy.json').exists())

    def test_model_failure_is_abstention_not_negative_and_combined_can_use_rules(self):
        self.complete_reviews()
        result=e.score_study(self.out)
        model=result['systems']['medgemma:27b']
        self.assertEqual(model['unavailable'],1)
        self.assertEqual(model['coverage'],0.5)
        self.assertEqual(model['recall_including_abstention_as_miss'],0)
        self.assertEqual(result['systems']['rules+medgemma:27b']['coverage'],1)
        self.assertEqual(result['systems']['rules+medgemma:27b']['tp'],1)
        self.assertIsNone(result['rules_deadline_accuracy'])

    def test_missing_whole_model_is_reported_not_omitted(self):
        self.complete_reviews()
        p=self.out/'predictions.jsonl'
        rows=[json.loads(line) for line in p.read_text().splitlines()]
        p.write_text('\n'.join(json.dumps(r) for r in rows if r['system']=='rules')+'\n')
        result=e.score_study(self.out)
        self.assertEqual(result['systems']['medgemma:27b']['coverage'],0)
        self.assertIsNone(result['systems']['medgemma:27b']['recall'])

    def test_disagreements_need_third_independent_reviewer(self):
        self.complete_reviews()
        rows=list(e.read_sheet(self.out/'reviewer_2.csv').values());rows[0]['expected_rules']='R019'
        e.write_sheet(self.out/'reviewer_2.csv',rows)
        with self.assertRaises(ValueError):e.score_study(self.out)
        adjudication=[dict(record) for record in self.records]
        adjudication[0].update(label_status='complete',expected_rules='R003',reviewer_id='clinician-c',reviewer_role='clinician')
        e.write_sheet(self.out/'adjudication.csv',adjudication)
        self.assertEqual(e.score_study(self.out)['systems']['rules']['tp'],1)

    def test_same_reviewer_cannot_count_twice(self):
        self.complete_reviews()
        rows=list(e.read_sheet(self.out/'reviewer_2.csv').values())
        for row in rows:row['reviewer_id']='clinician-a'
        e.write_sheet(self.out/'reviewer_2.csv',rows)
        with self.assertRaises(ValueError):e.score_study(self.out)

    def test_changed_input_or_duplicate_prediction_is_rejected(self):
        self.complete_reviews()
        p=self.out/'predictions.jsonl';p.write_text(p.read_text()+p.read_text().splitlines()[0]+'\n')
        with self.assertRaises(ValueError):e.score_study(self.out)
        p=self.out/'records.json';p.write_text(p.read_text()+' ')
        with self.assertRaises(ValueError):e.score_study(self.out)
