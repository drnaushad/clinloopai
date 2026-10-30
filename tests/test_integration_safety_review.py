"""Synthetic identity, privacy, transport and complete-import regression checks."""
import json
import os
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

import pytest
from src.clinloop_engine import oidc, local_llm_engine as llm
from src.clinloop_engine.bulk_fhir import BulkFHIRClient
from src.clinloop_engine.fhir_sync import FHIRClient, FHIRSyncError, FHIRHTTPError, sync_once
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine.outreach import WebhookProvider, OutboxProvider, OutreachNotAllowed, provider_from_env
from src.clinloop_engine.pacs_client import DICOMwebClient, PACSError


def response(body, status=200):
    result = Mock(status_code=status, headers={})
    result.iter_content.return_value = [json.dumps(body).encode()]
    return result


@pytest.mark.parametrize('mapping', [[], ['admin'], None, 'admin', {}, {'x': []}, {'': 'admin'}, {'x': 'unknown'}])
def test_malformed_oidc_role_configuration_fails_closed(mapping):
    with patch.dict(oidc.os.environ, {'CLINLOOP_OIDC_ROLE_MAP': json.dumps(mapping)}):
        with pytest.raises(oidc.OIDCError):
            oidc.role_map()


@pytest.mark.parametrize('body', [[], None, 'SYNTHETIC_PRIVATE', {},
                                {'issuer': 'https://synthetic.example', 'jwks_uri': []},
                                {'issuer': 'https://synthetic.example', 'id_token_signing_alg_values_supported': 7}])
def test_malformed_oidc_discovery_is_generic_authentication_failure(body):
    reply = Mock()
    reply.json.return_value = body
    oidc.reset_cache()
    try:
        with patch.dict(oidc.os.environ, {'CLINLOOP_OIDC_ISSUER': 'https://synthetic.example'}), \
             patch.object(oidc.requests, 'get', return_value=reply):
            with pytest.raises(oidc.OIDCError) as error:
                oidc.discovery()
        assert 'SYNTHETIC_PRIVATE' not in str(error.value)
        assert oidc._discovery['config'] is None
        reply.close.assert_called_once()
    finally:
        oidc.reset_cache()


def test_model_show_cannot_replace_requested_name_before_locality_check():
    details = {'name': 'different:1b', 'capabilities': ['completion'],
               'model_info': {'synthetic.context_length': 16384}}
    with patch.object(llm, '_ollama_json', return_value=details) as model:
        result = llm.generate_clinical_text('SYNTHETIC', model='synthetic:1b')
    assert result.get('error') and result['text'] == ''
    assert all(call.args[1] != '/api/generate' for call in model.call_args_list)


@pytest.mark.parametrize('pid', [None, '', 'SYNTHETIC-OTHER', 7, ['SYNTHETIC']])
def test_pacs_study_without_exact_patient_identity_never_becomes_followup(pid):
    study = {'0020000D': {'Value': ['1.2.3']}}
    if pid is not None:
        study['00100020'] = {'Value': [pid]}
    client = DICOMwebClient('https://pacs.example/dicom-web')
    try:
        with patch.object(client, '_get', return_value=[study]) as query:
            assert client.studies('SYNTHETIC') == []
        assert query.call_count == 1  # Never query series of an unverified patient.
    finally:
        client.session.close()


def test_pacs_matching_identity_is_retained():
    study = {'0020000D': {'Value': ['1.2.3']}, '00100020': {'Value': ['SYNTHETIC']}}
    client = DICOMwebClient('https://pacs.example/dicom-web')
    try:
        with patch.object(client, '_get', side_effect=[[study], []]):
            assert len(client.studies('SYNTHETIC')) == 1
    finally:
        client.session.close()


def test_pacs_rejects_redirect_and_closes_without_reflecting_uid():
    session = Mock()
    reply = response({}, 302)
    session.get.return_value = reply
    client = DICOMwebClient('https://pacs.example/dicom-web', session=session)
    with pytest.raises(PACSError) as error:
        client._get('/studies/SYNTHETIC_PRIVATE_UID/series', {})
    assert 'SYNTHETIC_PRIVATE' not in str(error.value)
    assert session.get.call_args.kwargs['allow_redirects'] is False
    assert session.get.call_args.kwargs['stream'] is True
    reply.close.assert_called_once()


def test_pacs_closes_oversized_and_successful_responses():
    session = Mock()
    client = DICOMwebClient('https://pacs.example/dicom-web', session=session)
    for chunks in [[b'x' * (8 * 1024 * 1024 + 1)], [b'[]']]:
        reply = response([])
        reply.iter_content.return_value = chunks
        session.get.return_value = reply
        if chunks[0] == b'[]':
            assert client._get('/studies', {}) == []
        else:
            with pytest.raises(PACSError):
                client._get('/studies', {})
        reply.close.assert_called_once()


@pytest.mark.parametrize('endpoint', ['http://hospital.example/send', 'https://secret:password@hospital.example/send',
                                      'https://hospital.example/send#fragment', 'file:///tmp/outreach'])
def test_outreach_endpoint_must_protect_identifiable_payload(endpoint):
    with pytest.raises(OutreachNotAllowed):
        WebhookProvider(endpoint)


def test_outreach_redirect_never_receives_a_second_identifiable_request():
    session = MagicMock()
    session.__enter__.return_value = session
    reply = MagicMock(status_code=307)
    reply.__enter__.return_value = reply
    session.post.return_value = reply
    with patch('src.clinloop_engine.outreach.requests.Session', return_value=session):
        with pytest.raises(OutreachNotAllowed):
            WebhookProvider('https://hospital.example/send').send({'patient_id': 'SYNTHETIC'})
    assert session.trust_env is False and session.post.call_count == 1
    assert session.post.call_args.kwargs['allow_redirects'] is False


def test_unknown_outreach_provider_does_not_silently_fallback():
    with patch.dict('os.environ', {'CLINLOOP_OUTREACH_PROVIDER': 'webhok'}):
        with pytest.raises(OutreachNotAllowed):
            provider_from_env()


def test_search_rejects_cross_patient_history_and_optional_integrity_failure():
    client = FHIRClient('https://fhir.example/r4')
    try:
        with patch.object(client, 'search', return_value=iter([
                {'resourceType': 'Observation', 'id': 'lab', 'subject': {'reference': 'Patient/OTHER'}}])):
            with pytest.raises(FHIRSyncError):
                client.patient_history('SYNTHETIC')
        def search(kind, params):
            if kind == 'ImagingStudy':
                raise FHIRSyncError('SYNTHETIC malformed optional content')
            return iter([])
        with patch.object(client, 'search', side_effect=search):
            with pytest.raises(FHIRSyncError):
                client.patient_history('SYNTHETIC')
    finally:
        client.session.close()


def test_search_optional_unsupported_endpoint_is_distinguished_from_integrity_failure():
    client = FHIRClient('https://fhir.example/r4')
    def search(kind, params):
        if kind == 'ImagingStudy':
            raise FHIRHTTPError(kind, 404)
        return iter([])
    try:
        with patch.object(client, 'search', side_effect=search):
            assert client.patient_history('SYNTHETIC') == []
    finally:
        client.session.close()


@pytest.mark.parametrize('meta', [None, [], {'lastUpdated': None}, {'lastUpdated': '2026-10-29'},
                                  {'lastUpdated': '2026-02-30T00:00:00Z'}])
def test_malformed_change_metadata_fails_feed_without_advancing_cursor(meta):
    store = LoopStore()
    client = FHIRClient('https://fhir.example/r4')
    item = {'resourceType': 'Patient', 'id': 'SYNTHETIC', 'meta': meta}
    try:
        with patch.object(client, 'search', side_effect=lambda kind, params: iter([item] if kind == 'Patient' else [])):
            result = sync_once(store, client, now=datetime(2026, 10, 29))
        assert result['ok'] is False and store.get_cursor('fhir-sync') is None
    finally:
        client.session.close()
        store._db.close()


def test_change_cursor_compares_absolute_instants_and_does_not_regress():
    client = FHIRClient('https://fhir.example/r4')
    items = [{'resourceType': 'Patient', 'id': 'SYNTHETIC-' + str(i), 'meta': {'lastUpdated': stamp}}
             for i, stamp in enumerate(['2026-10-29T02:00:00+09:00', '2026-10-28T23:00:00Z'])]
    try:
        with patch.object(client, 'search', side_effect=lambda kind, params: iter(items if kind == 'Patient' else [])):
            _, newest = client.changed_patients('2026-10-28T00:00:00Z')
            assert newest == '2026-10-28T23:00:00Z'
            assert client.changed_patients('2026-10-29T00:00:00Z')[1] is None
    finally:
        client.session.close()


def test_search_resource_limit_and_oversized_json_fail_closed():
    client = FHIRClient('https://fhir.example/r4', max_resources=1)
    body = {'resourceType': 'Bundle', 'type': 'searchset', 'entry': [
        {'resource': {'resourceType': 'Patient', 'id': 'SYNTHETIC-1'}},
        {'resource': {'resourceType': 'Patient', 'id': 'SYNTHETIC-2'}}]}
    try:
        reply = response(body)
        with patch.object(client, '_get', return_value=reply):
            with pytest.raises(FHIRSyncError):
                list(client.search('Patient', {}))
        reply.close.assert_called_once()
        reply = response({})
        reply.iter_content.return_value = [b'x' * (16 * 1024 * 1024 + 1)]
        with patch.object(client, '_get', return_value=reply):
            with pytest.raises(FHIRSyncError):
                list(client.search('Patient', {}))
        reply.close.assert_called_once()
    finally:
        client.session.close()


def test_signed_bulk_files_require_exact_explicit_origin_without_network():
    client = BulkFHIRClient('https://fhir.example/r4')
    try:
        with patch('src.clinloop_engine.bulk_fhir.requests.Session') as session:
            for url in ['https://169.254.169.254/latest', 'https://arbitrary.example/file',
                        'https://fhir.example@arbitrary.example/file']:
                with pytest.raises(FHIRSyncError), client._file_response(url, False):
                    pass
            session.assert_not_called()
    finally:
        client.session.close()


@pytest.mark.parametrize('allowed', [['http://files.example'], ['https://files.example/path'],
                                     ['https://secret:password@files.example'], ['https://files.example?key=secret']])
def test_bulk_download_allowlist_is_origins_only(allowed):
    with pytest.raises(FHIRSyncError):
        BulkFHIRClient('https://fhir.example/r4', download_origins=allowed)


@pytest.mark.parametrize('budget', [{'max_resources': 1}, {'max_bytes': 30}, {'max_line_bytes': 30}])
def test_bulk_import_limits_keep_mirror_and_cursor_unchanged(budget):
    store = LoopStore()
    store.set_cursor('fhir-sync', '2026-10-01T00:00:00Z')
    client = BulkFHIRClient('https://fhir.example/r4', store=store, **budget)
    data = b'\n'.join(json.dumps({'resourceType': 'Patient', 'id': 'SYNTHETIC-' + str(i)}).encode() for i in range(2))
    reply = response({})
    reply.iter_content.return_value = [data]
    @contextmanager
    def file_response(_url, _token):
        yield reply
    manifest = {'transactionTime': '2026-10-29T00:00:00Z', 'output': [{'type': 'Patient', 'url': 'https://fhir.example/file'}]}
    try:
        with patch.object(client, 'kick_off', return_value='https://fhir.example/status'), \
             patch.object(client, 'wait', return_value=manifest), patch.object(client, 'cancel'), \
             patch.object(client, '_file_response', side_effect=file_response):
            result = sync_once(store, client, now=datetime(2026, 10, 29))
        assert result['ok'] is False and store.mirror_size() == 0
        assert store.get_cursor('fhir-sync') == '2026-10-01T00:00:00Z'
    finally:
        client.session.close()
        store._db.close()


def test_mirror_patient_reassignment_is_atomic_and_requires_reconciliation():
    store = LoopStore()
    try:
        original = {'resourceType': 'Observation', 'id': 'lab'}
        store.mirror_upsert([('Observation', 'SYNTHETIC-1', 'lab', original)])
        with pytest.raises(ValueError):
            store.mirror_upsert([('Patient', 'SYNTHETIC-NEW', 'SYNTHETIC-NEW', {'resourceType': 'Patient', 'id': 'SYNTHETIC-NEW'}),
                                 ('Observation', 'SYNTHETIC-2', 'lab', original)])
        assert store.mirror_size() == 1
        assert store.mirror_history('SYNTHETIC-1') == [original]
        assert store.mirror_history('SYNTHETIC-2') == []
    finally:
        store._db.close()


def test_clinical_ingest_rejects_ambiguous_alias_before_replacing_snapshot():
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.auth import User
    from fastapi import HTTPException
    store = LoopStore()
    prior = [{'resourceType': 'Patient', 'id': 'SYNTHETIC-OLD'}]
    store.save_snapshot('SYNTHETIC-OLD', prior)
    body = {'resourceType': 'Bundle', 'type': 'collection', 'entry': [
        {'fullUrl': 'urn:uuid:ambiguous', 'resource': {'resourceType': 'Patient', 'id': 'SYNTHETIC-OLD'}},
        {'fullUrl': 'urn:uuid:ambiguous', 'resource': {'resourceType': 'Patient', 'id': 'SYNTHETIC-OTHER'}}]}
    try:
        with patch.object(clinical_api, 'get_store', return_value=store):
            with pytest.raises(HTTPException) as error:
                clinical_api.ingest_fhir(body, None, User('synthetic', 'admin'), Mock())
        assert error.value.status_code == 422
        assert store.snapshot('SYNTHETIC-OLD') == prior
        assert store.snapshot('SYNTHETIC-OTHER') == []
    finally:
        store._db.close()


def test_provider_exception_cannot_persist_patient_data_in_error_or_audit():
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    store = LoopStore()
    try:
        events = [{'event_id': 'synthetic-fit', 'patient_id': 'SYNTHETIC', 'event_type': 'lab_result',
                   'timestamp': '2026-05-01T09:00:00', 'details': {'test': 'FIT', 'result': 'positive'},
                   'status': 'completed'}]
        store.upsert_detections(ClinLoopDetector(evaluation_time=datetime(2026, 6, 1)).process_patient('test', 'SYNTHETIC', events))
        key = store.worklist()[0]['loop_key']
        draft = store.add_outreach_draft(key, 'synthetic-nurse', 'navigator', 'Please contact the clinic.', 'en', 'sms', [])
        provider = Mock(name='synthetic-provider')
        provider.name = 'synthetic'
        provider.send.side_effect = ValueError('SYNTHETIC_PRIVATE_PATIENT_PAYLOAD')
        result = store.decide_outreach(draft['id'], 'synthetic-doctor', 'clinician', True, provider=provider)
        assert result['status'] == 'failed'
        assert 'SYNTHETIC_PRIVATE' not in json.dumps(result) + json.dumps(store.audit_trail())
        assert store.verify_audit_chain()
    finally:
        store._db.close()


def test_new_outbox_is_owner_only_and_symlink_is_refused(tmp_path):
    path = tmp_path / 'outbox.jsonl'
    previous = os.umask(0o022)
    try:
        OutboxProvider(str(path)).send({'patient_id': 'SYNTHETIC', 'text': 'Please call.'})
    finally:
        os.umask(previous)
    assert path.stat().st_mode & 0o777 == 0o600
    linked = tmp_path / 'linked.jsonl'
    linked.symlink_to(path)
    if hasattr(os, 'O_NOFOLLOW'):
        with pytest.raises(OSError):
            OutboxProvider(str(linked)).send({'patient_id': 'SYNTHETIC'})


def test_static_library_cannot_claim_verified_evidence_or_critical_treatment():
    from src.clinloop_engine.biomcp_server import handle_call_tool
    reference = handle_call_tool('biomcp_query_guidelines', {'finding_value': 'HSIL'})
    assert reference['status'] == 'static_unverified'
    assert reference['source_verified'] is False and reference['clinical_use'] is False
    assert reference['human_review_required']
    assert not {'evidence_grade', 'legal_liability', 'derived_k_factor'} & set(reference)
    critical = handle_call_tool('biomcp_query_clsi_critical_lab', {'specimen': 'blood', 'isolate': 'unknown'})
    assert critical['status'] == 'unavailable' and 'mandated_action' not in critical


def test_ehr_and_pacs_simulators_cannot_claim_delivery_or_clinical_confirmation(caplog):
    from src.clinloop_engine.ehr_mcp_server import handle_call_tool as ehr
    from src.clinloop_engine.pacs_mcp_server import handle_call_tool as pacs
    with caplog.at_level('INFO'):
        result = ehr('ehr_push_fhir_task', {'patient_id': 'SYNTHETIC_PRIVATE', 'task_type': 'order_imaging'})
        image = pacs('pacs_fetch_dicom_metadata', {'study_uid': 'SYNTHETIC_PRIVATE'})
    assert result['simulated'] and result['transmitted'] is False and result['ehr_connected'] is False
    assert image['simulated'] and image['clinical_confirmation'] is False and image['pacs_connected'] is False
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(result) + json.dumps(image) + caplog.text
