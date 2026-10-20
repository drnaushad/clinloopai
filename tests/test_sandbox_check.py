"""Only a fresh namespace of known synthetic resources can be seeded."""
import json
import unittest
from pathlib import Path
from src.validation.sandbox_check import synthetic_transaction


class TestSandboxCheck(unittest.TestCase):
    def test_fixture_references_are_rewritten_and_existing_records_protected(self):
        fixture=json.loads((Path(__file__).parents[1]/'data/fhir_example_bundle.json').read_text())
        result=synthetic_transaction(fixture,'clinloop-synthetic-test')
        urls={e['request']['url'] for e in result['entry']}
        self.assertEqual(len(urls),20)
        self.assertTrue(all(e['request']['ifNoneMatch']=='*' for e in result['entry']))
        self.assertTrue(all(e['resource']['id'].startswith('clinloop-synthetic-test-') for e in result['entry']))
        def refs(node):
            if isinstance(node,dict):
                if 'reference' in node:self.assertIn(node['reference'],urls)
                for value in node.values():refs(value)
            elif isinstance(node,list):
                for value in node:refs(value)
        refs(result)
