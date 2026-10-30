"""Synthetic note-model outputs must not silently become complete clinical readings."""
import json
import os
import unittest
from unittest.mock import patch

from src.clinloop_engine.note_reader import llm_suggestions


TEXT = 'Plan: repeat CT chest in 3 months. Obtain CT pelvis in 2 weeks.'
ITEM = {'kind': 'imaging', 'target': 'CT pelvis', 'quote': 'Obtain CT pelvis in 2 weeks', 'interval': '2 weeks'}


@patch.dict(os.environ, {'CLINLOOP_PROFILE': 'research'})
class TestNoteSuggestionSafety(unittest.TestCase):
    def read(self, plans):
        with patch('src.clinloop_engine.local_llm_engine.generate_clinical_text',
                   return_value={'text': json.dumps({'plans': plans}), 'model': 'synthetic'}):
            return llm_suggestions(TEXT, [])

    def test_long_plan_section_is_refused_before_inference(self):
        with patch('src.clinloop_engine.local_llm_engine.generate_clinical_text') as generate:
            out = llm_suggestions('Plan: ' + 'x' * 4001, [])
        generate.assert_not_called()
        self.assertFalse(out['available'])

    def test_structurally_invalid_model_items_are_not_successful_empty_reads(self):
        for item in [[], {'kind': []}, {'kind': {}}, {**ITEM, 'quote': []}, {**ITEM, 'target': {}},
                     {**ITEM, 'interval': {}}, {**ITEM, 'quote': 'not in the synthetic note'}]:
            with self.subTest(item=item):
                out = self.read([item])
                self.assertFalse(out['available'])
                self.assertFalse(out['complete'])

    def test_unparseable_or_missing_plans_array_is_explicitly_unavailable(self):
        for text in ['not JSON', '{}', '{"plans": {}}']:
            with self.subTest(text=text), patch('src.clinloop_engine.local_llm_engine.generate_clinical_text', return_value={'text': text}):
                self.assertFalse(llm_suggestions(TEXT, [])['available'])

    def test_wholly_valid_empty_array_is_distinct_from_rejected_items(self):
        out = self.read([])
        self.assertTrue(out['available'])
        self.assertTrue(out['complete'])

    def test_same_modality_in_another_region_cannot_suppress_a_suggestion(self):
        found = [{'kind': 'imaging', 'target': 'ct', 'evidence': 'repeat CT chest in 3 months.'}]
        with patch('src.clinloop_engine.local_llm_engine.generate_clinical_text',
                   return_value={'text': json.dumps({'plans': [ITEM]})}):
            out = llm_suggestions(TEXT, found)
        self.assertEqual(len(out['suggestions']), 1)

    def test_partial_results_preserve_verified_quotes_and_expose_incompleteness(self):
        out = self.read([ITEM, {'kind': []}, ITEM])
        self.assertTrue(out['available'])
        self.assertFalse(out['complete'])
        self.assertEqual(len(out['suggestions']), 1)
        self.assertEqual(out['dropped'], 1)

    def test_model_failures_are_generic_and_unfinished_answers_abstain(self):
        for result in [None, {'error': 'SYNTHETIC_PRIVATE'}, {'text': '{"plans": []}', 'done': False}]:
            with self.subTest(result=result), patch('src.clinloop_engine.local_llm_engine.generate_clinical_text', return_value=result):
                out = llm_suggestions(TEXT, [])
            self.assertFalse(out['available'])
            self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(out))
