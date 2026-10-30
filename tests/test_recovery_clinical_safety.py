"""Draft regressions for preserved outside-report content and controlled refusals."""
import base64
import unittest
from datetime import datetime
from unittest.mock import patch
from src.clinloop_engine import document_reader as reader

class TestPreservedSections(unittest.TestCase):
    def test_repeated_impressions_and_recommendations_are_not_silently_lost(self):
        text = ('IMPRESSION:\nSynthetic first impression.\n'
                'IMPRESSION:\nSynthetic amended impression.\n'
                'RECOMMENDATIONS:\nCompare prior imaging.\n'
                'RECOMMENDATIONS:\nSynthetic specialist review requested.')
        out = reader.parse_report(text)
        for marker in ['first impression', 'amended impression', 'Compare prior imaging', 'specialist review']:
            self.assertIn(marker, out['conclusion'])
        self.assertTrue(out['requires_section_review'])

    def test_findings_are_preserved_even_when_impression_is_short(self):
        out = reader.parse_report('FINDINGS:\nSynthetic lesion needs correlation with prior scans.\nIMPRESSION:\nNo acute change.')
        self.assertIn('lesion needs correlation', out['conclusion'])
        self.assertTrue(out['conclusion'].startswith('No acute change.'))

    def test_unusually_long_document_is_refused_instead_of_truncated(self):
        with self.assertRaises(reader.DocumentError):
            reader.parse_report('IMPRESSION:\n' + 'x' * 200001)

    def test_duplicate_sections_cannot_be_marked_confirmed_without_retaining_review_warning(self):
        parsed = reader.parse_report('IMPRESSION:\nSynthetic original.\nIMPRESSION:\nSynthetic correction.')
        report = reader.outside_report_resource('synthetic-P', b'synthetic', {'method': 'pdf-text'}, parsed,
                                               confirmed_by='synthetic.clinician')
        tags = {tag['code'] for tag in report['meta']['tag']}
        self.assertNotIn('human-confirmed', tags)

    def test_leap_day_does_not_crash_date_finding(self):
        class LeapDay(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2024, 2, 29, 12, tzinfo=tz)
        with patch.object(reader, 'datetime', LeapDay):
            out = reader.parse_report('Exam date: 2024-02-29\nIMPRESSION:\nSynthetic normal report.')
        self.assertEqual(out['date'], '2024-02-29')


class TestDocumentAPIRefusals(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine.api import app
        self.client = TestClient(app)

    def request(self, route, extra=None):
        from src.clinloop_engine.auth import User
        payload = {'patient_id': 'synthetic-P', 'content_base64': base64.b64encode(b'synthetic').decode(), **(extra or {})}
        with patch('src.clinloop_engine.auth.authenticate', return_value=User('synthetic', 'clinician')), \
             patch('src.clinloop_engine.imaging_api._patient_resource', return_value={'id': 'synthetic-P'}), \
             patch('src.clinloop_engine.clinical_api.get_store') as store, \
             patch('src.clinloop_engine.imaging_api.get_store', return_value=store.return_value), \
             patch('src.clinloop_engine.imaging_api.evaluate_patient', return_value={'active': []}):
            response = self.client.post(route, json=payload, headers={'Authorization': 'Bearer synthetic'})
        return response, store.return_value

    def test_parser_refusals_are_controlled_422_responses_without_patient_text(self):
        for route in ['/api/v1/documents/outside-report/extract', '/api/v1/documents/outside-report']:
            with self.subTest(route=route), patch.object(reader, 'extract_text', return_value={'text': 'x' * 200001, 'method': 'pdf-text', 'pages': 1, 'confidence': None}):
                response, store = self.request(route)
            self.assertEqual(response.status_code, 422)
            store.add_external_resource.assert_not_called()
            self.assertNotIn('xxx', response.text)

    def test_calendar_invalid_report_date_is_rejected_before_storing(self):
        for date in ['2026-02-30', '2026-13-01', '0000-01-01']:
            with self.subTest(date=date), patch.object(reader, 'extract_text', return_value={'text': 'IMPRESSION:\nSynthetic normal report.', 'method': 'pdf-text', 'pages': 1, 'confidence': None}):
                response, store = self.request('/api/v1/documents/outside-report', {'date': date})
            self.assertEqual(response.status_code, 422)
            store.add_external_resource.assert_not_called()

    def test_calendar_invalid_note_date_is_rejected_before_storing(self):
        response, store = self.request('/api/v1/documents/clinical-note', {'text': 'Synthetic note: repeat lab next month.', 'date': '2026-02-30'})
        self.assertEqual(response.status_code, 422)
        store.add_external_resource.assert_not_called()


class TestApprovalInputProvenance(unittest.TestCase):
    def test_document_parser_change_invalidates_existing_rule_approval(self):
        from src.clinloop_engine import governance
        from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES
        rule = next(r for r in OBLIGATION_RULES if r.rule_id == "R003")
        original = governance._cached
        fingerprint = governance.rule_fingerprint(rule)
        def changed(kind, path, load):
            return "changed-document-parser" if path.endswith("document_reader.py") else original(kind, path, load)
        with patch.object(governance, "_cached", side_effect=changed):
            self.assertNotEqual(fingerprint, governance.rule_fingerprint(rule))
