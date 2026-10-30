"""Synthetic malformed responses cannot masquerade as a healthy FHIR feed."""
import unittest
import json
from unittest.mock import Mock, patch
from src.clinloop_engine.fhir_sync import FHIRClient, FHIRSyncError, check_connection, search_bundle
from src.clinloop_engine.bulk_fhir import BulkFHIRClient


class TestFHIRResponseSafety(unittest.TestCase):
    def test_error_payload_at_http_200_is_rejected(self):
        for body in [{}, {'resourceType':'OperationOutcome'}, {'resourceType':'Bundle','type':'collection'}]:
            with self.assertRaises(FHIRSyncError):search_bundle(body,'Patient')
        with self.assertRaises(FHIRSyncError):
            search_bundle({'resourceType':'Bundle','type':'searchset','entry':[{'resource':{'resourceType':'OperationOutcome','issue':[{'severity':'error'}]}}]},'Patient')

    def test_warning_outcome_is_not_emitted_as_patient_data(self):
        body={'resourceType':'Bundle','type':'searchset','entry':[{'resource':{'resourceType':'OperationOutcome','issue':[{'severity':'warning'}]}}]}
        c=FHIRClient('https://example.org/fhir');r=Mock(status_code=200);r.json.return_value=body;r.iter_content.return_value=[json.dumps(body).encode()]
        with patch.object(c,'_get',return_value=r):self.assertEqual(list(c.search('Patient',{})),[])

    def test_paging_cannot_send_token_to_another_origin(self):
        c=FHIRClient('https://example.org/fhir',token='synthetic-token')
        r=Mock(status_code=200);r.json.return_value={'resourceType':'Bundle','type':'searchset','link':[{'relation':'next','url':'https://elsewhere.example/steal'}]}
        r.iter_content.return_value=[json.dumps(r.json.return_value).encode()]
        with patch.object(c,'_get',return_value=r) as get:
            with self.assertRaises(FHIRSyncError):list(c.search('Patient',{}))
            self.assertEqual(get.call_count,1)

    def test_epic_group_export_name_is_recognized_only_at_group_scope(self):
        meta=Mock(status_code=200);meta.json.return_value={'resourceType':'CapabilityStatement','fhirVersion':'4.0.1','rest':[{'resource':[{'type':'Group','operation':[{'name':'group-export'}]}]}]}
        with patch('src.clinloop_engine.fhir_sync.requests.get',return_value=meta):
            self.assertTrue(check_connection(BulkFHIRClient('https://example.org/fhir',group_id='synthetic'))['ok'])
            self.assertFalse(check_connection(BulkFHIRClient('https://example.org/fhir'))['ok'])

    def test_metadata_and_http_success_do_not_hide_error_search_body(self):
        meta=Mock(status_code=200);meta.json.return_value={'resourceType':'CapabilityStatement','fhirVersion':'4.0.1','rest':[]}
        response=Mock(status_code=200);response.json.return_value={'resourceType':'OperationOutcome'}
        c=FHIRClient('https://example.org/fhir')
        with patch('src.clinloop_engine.fhir_sync.requests.get',return_value=meta),patch.object(c,'_get',return_value=response):
            result=check_connection(c)
        self.assertFalse(result['ok'])
        self.assertFalse(result['types']['Patient']['readable'])


class TestFHIRTokenRefresh(unittest.TestCase):
    def test_search_refresh_closes_rejected_response(self):
        session = Mock(headers={}, auth=Mock())
        rejected, success = Mock(status_code=401), Mock(status_code=200)
        session.get.side_effect = [rejected, success]
        client = FHIRClient('https://example.org/fhir', session=session)
        self.assertIs(client._get('https://example.org/fhir/Patient'), success)
        rejected.close.assert_called_once()
        session.auth.invalidate.assert_called_once()
        self.assertEqual(session.get.call_count, 2)

    def test_bulk_refresh_closes_rejected_response_and_retries_only_once(self):
        session = Mock(headers={}, auth=Mock())
        rejected, still_rejected = Mock(status_code=401), Mock(status_code=401)
        session.request.side_effect = [rejected, still_rejected]
        client = BulkFHIRClient('https://example.org/fhir', session=session)
        self.assertIs(client._request('GET', 'https://example.org/status/synthetic'), still_rejected)
        rejected.close.assert_called_once()
        session.auth.invalidate.assert_called_once()
        self.assertEqual(session.request.call_count, 2)


class TestOAuthErrorPrivacy(unittest.TestCase):
    def test_untrusted_oauth_error_field_is_never_echoed(self):
        from src.clinloop_engine.smart_auth import SMARTBackendAuth, SMARTAuthError
        for error in ('SYNTHETIC_PRIVATE_TEXT', {'patient': 'SYNTHETIC_PRIVATE'}, None):
            session = Mock()
            response = Mock(status_code=400)
            response.json.return_value = {'error': error, 'error_description': 'SYNTHETIC_PRIVATE'}
            session.post.return_value = response
            auth = SMARTBackendAuth('https://example.org/fhir', 'synthetic-client',
                                    client_secret='synthetic-secret', token_url='https://example.org/token',
                                    scope='system/Patient.read', session=session)
            with self.assertRaises(SMARTAuthError) as raised:
                auth.token()
            self.assertIn('HTTP 400', str(raised.exception))
            self.assertNotIn('SYNTHETIC_PRIVATE', str(raised.exception))
