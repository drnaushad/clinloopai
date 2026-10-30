"""Invalid synthetic patient input must not be echoed in HTTP errors or logs."""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestRequestErrorPrivacy(unittest.TestCase):
    def setUp(self):
        # Import after collection: older suites provision their synthetic account
        # environment when collected, before auth captures it at import time.
        from src.clinloop_engine.api import app
        from src.clinloop_engine.auth import User
        self.app = app
        self.user = User("synthetic", "clinician")

    def test_invalid_typed_fields_are_not_echoed_in_errors_or_logs(self):
        marker = 'SYNTHETIC_PRIVATE_VALUE'
        payloads = [
            {'patient_id': 'synthetic-P', 'text': {'report': marker}},
            {'patient_id': 'INVALID ' + marker, 'text': 'Synthetic note'},
            {'patient_id': 'synthetic-P', 'text': 'Synthetic note', 'note_type': marker * 10},
        ]
        with patch('src.clinloop_engine.auth.authenticate', return_value=self.user), \
             patch('src.clinloop_engine.api.logger') as logger:
            for payload in payloads:
                with self.subTest(payload=payload):
                    response = TestClient(self.app).post('/api/v1/documents/clinical-note', json=payload,
                                                    headers={'Authorization': 'Bearer synthetic'})
                    self.assertEqual(response.status_code, 422)
                    self.assertNotIn(marker, response.text)
                    self.assertEqual(set(response.json()), {'detail'})
                    self.assertIsInstance(response.json()['detail'], str)
            self.assertNotIn(marker, str(logger.mock_calls))

    def test_malformed_json_does_not_return_parser_context_or_submitted_content(self):
        with patch('src.clinloop_engine.auth.authenticate', return_value=self.user):
            response = TestClient(self.app).post('/api/v1/documents/clinical-note', content='{"text":"SYNTHETIC_PRIVATE_VALUE", invalid}',
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer synthetic'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE', response.text)
        self.assertNotIn('input', json.dumps(response.json()))
