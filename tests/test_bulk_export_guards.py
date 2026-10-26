"""Synthetic export error, provenance-boundary and compatibility regressions."""
import os
from unittest import mock

import pytest
from test_bulk_fhir import StubBulk, NOW, TOKEN
from src.clinloop_engine.bulk_fhir import BulkFHIRClient, bulk_client_from_env
from src.clinloop_engine.fhir_sync import sync_once, FHIRSyncError
from src.clinloop_engine.loop_store import LoopStore


def test_manifest_error_refuses_partial_data_and_preserves_cursor():
    stub = StubBulk(polls_before_ready=0)
    try:
        client = BulkFHIRClient(stub.base, token=TOKEN, group_id='monitored')
        store = LoopStore()
        partial = {'output': [{'type': 'Patient', 'url': stub.base + '/files/1/Patient.ndjson'}],
                   'error': [{'type': 'OperationOutcome', 'url': stub.base + '/errors/1'}]}
        with mock.patch.object(client, 'wait', return_value=partial), mock.patch.object(client, 'download') as download:
            result = sync_once(store, client, now=NOW)
        assert result['ok'] is False
        assert store.mirror_size() == 0 and store.get_cursor('fhir-sync') is None
        assert stub.deleted == ['/status/1']
        download.assert_not_called()
    finally:
        stub.close()


def test_epic_compatible_profile_omits_explicit_format_and_optional_imaging():
    stub = StubBulk(polls_before_ready=0)
    try:
        client = BulkFHIRClient(stub.base, token=TOKEN, group_id='monitored',
                                resource_types=['Patient', 'Observation', 'DiagnosticReport'], output_format=None)
        assert sync_once(LoopStore(), client, now=NOW)['ok']
        assert '_outputFormat' not in stub.kickoffs[0]
        assert 'ImagingStudy' not in stub.kickoffs[0]['_type']
        assert client.last_export['requested_types'] == ['Patient', 'Observation', 'DiagnosticReport']
    finally:
        stub.close()


@pytest.mark.parametrize('url', ['https://foreign.invalid/files', 'http://ehr.invalid/file',
    'https://ehr.invalid:444/file', 'https://user:password@ehr.invalid/file', 'https://ehr.invalid/file#fragment'])
def test_authenticated_job_or_file_cannot_leave_origin(url):
    client = BulkFHIRClient('https://ehr.invalid/FHIR/R4')
    with mock.patch.object(client.session, 'request') as request, pytest.raises(FHIRSyncError):
        client._request('GET', url)
    request.assert_not_called()


def test_authenticated_requests_do_not_follow_redirects():
    client = BulkFHIRClient('https://ehr.invalid/FHIR/R4')
    with mock.patch.object(client.session, 'request', return_value=mock.Mock(status_code=302)) as request:
        assert client._request('GET', 'https://ehr.invalid/status').status_code == 302
    assert request.call_args.kwargs['allow_redirects'] is False


@pytest.mark.parametrize('manifest', [{}, {'output': {}, 'error': []},
    {'output': [], 'error': {}}, {'output': [], 'requiresAccessToken': 'false'},
    {'output': [{'type': 'Unknown', 'url': 'https://ehr.invalid/file'}]}, {'output': [None]}])
def test_malformed_manifest_is_not_a_successful_empty_export(manifest):
    store = LoopStore()
    client = BulkFHIRClient('https://ehr.invalid/FHIR/R4', store=store)
    with mock.patch.object(client, 'kick_off', return_value='https://ehr.invalid/status'), \
            mock.patch.object(client, 'wait', return_value=manifest), mock.patch.object(client, 'cancel') as cancel:
        result = sync_once(store, client, now=NOW)
    assert not result['ok'] and store.mirror_size() == 0
    assert store.get_cursor('fhir-sync') is None
    cancel.assert_called_once()


@pytest.mark.parametrize('types', [[], ['Patient', 'Patient'], ['Patient', 'Unknown'], ['Observation']])
def test_invalid_resource_profiles_are_rejected(types):
    with pytest.raises(FHIRSyncError):
        BulkFHIRClient('https://ehr.invalid', resource_types=types)


def test_environment_selects_explicit_compatible_profile_only_in_new_client():
    with mock.patch.dict(os.environ, {'CLINLOOP_FHIR_BULK_TYPES': 'Patient,Observation,DiagnosticReport',
                                     'CLINLOOP_FHIR_BULK_OUTPUT_FORMAT': 'default'}):
        client = bulk_client_from_env('https://ehr.invalid', None, None)
    assert client.resource_types == ['Patient', 'Observation', 'DiagnosticReport']
    assert client.output_format is None


def test_download_failure_after_a_full_batch_does_not_commit_partial_history():
    store = LoopStore()
    client = BulkFHIRClient('https://ehr.invalid/FHIR/R4', store=store)
    def broken(_):
        for i in range(501):
            yield {'resourceType': 'Patient', 'id': 'synthetic-' + str(i)}
        raise FHIRSyncError('Synthetic download failure')
    with mock.patch.object(client, 'kick_off', return_value='https://ehr.invalid/status'), \
            mock.patch.object(client, 'wait', return_value={'output': [], 'error': []}), \
            mock.patch.object(client, 'download', side_effect=broken), mock.patch.object(client, 'cancel'):
        result = sync_once(store, client, now=NOW)
    assert not result['ok']
    assert store.mirror_size() == 0 and store.get_cursor('fhir-sync') is None


def test_mirror_import_rolls_back_if_a_staged_row_fails():
    store = LoopStore()
    def broken_rows():
        yield 'Patient', 'synthetic', 'synthetic', {'resourceType': 'Patient', 'id': 'synthetic'}
        raise ValueError('Synthetic row failure')
    with pytest.raises(ValueError):
        store.mirror_upsert(broken_rows())
    assert store.mirror_size() == 0
