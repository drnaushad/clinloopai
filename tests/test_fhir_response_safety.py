"""Synthetic malformed responses cannot masquerade as a healthy FHIR feed."""
import unittest
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
        c=FHIRClient('https://example.org/fhir');r=Mock(status_code=200);r.json.return_value=body
        with patch.object(c,'_get',return_value=r):self.assertEqual(list(c.search('Patient',{})),[])

    def test_paging_cannot_send_token_to_another_origin(self):
        c=FHIRClient('https://example.org/fhir',token='synthetic-token')
        r=Mock(status_code=200);r.json.return_value={'resourceType':'Bundle','type':'searchset','link':[{'relation':'next','url':'https://elsewhere.example/steal'}]}
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
