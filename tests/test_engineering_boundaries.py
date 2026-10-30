"""Synthetic malformed-input and resource-budget probes; no external services."""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

from PIL import Image
import pytest

from src.clinloop_engine import document_reader as documents
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine.smart_auth import SMARTBackendAuth, SMARTAuthError
from src.clinloop_engine.fhir_sync import FHIRClient, sync_once
from datetime import datetime
from types import SimpleNamespace
from src.clinloop_engine import biomcp_client
from src.clinloop_engine.bulk_fhir import BulkFHIRClient


@pytest.mark.parametrize('table,column', [
    ('audit_log', 'detail'), ('access_log', 'detail'), ('access_log', 'patients'),
])
def test_malformed_audit_json_is_failed_verification_not_an_exception(table, column):
    store = LoopStore()
    try:
        store.record_audit('synthetic-review', 'admin', 'synthetic-check', None, {})
        store.record_access('synthetic-review', 'admin', 'synthetic-check', ['SYNTHETIC-1'])
        store._db.execute(f'UPDATE {table} SET {column}=?', ('{not-json',))
        store._db.commit()
        verify = store.verify_audit_chain if table == 'audit_log' else store.verify_access_chain
        assert verify() is False
    finally:
        store._db.close()


def auth_with_response(body):
    response = Mock(status_code=200)
    response.json.return_value = body
    session = Mock()
    session.post.return_value = response
    auth = SMARTBackendAuth('https://synthetic.example/fhir', 'synthetic-client',
                           client_secret='synthetic-secret', scope='system/Patient.read',
                           token_url='https://synthetic.example/token', session=session)
    return auth, response


@pytest.mark.parametrize('body', [
    [], None, {'access_token': None}, {'access_token': {}}, {'access_token': ''},
    {'access_token': 'synthetic\r\nInjected: header'}, {'access_token': '합성'},
    {'access_token': 'synthetic-token', 'expires_in': 'nan'},
    {'access_token': 'synthetic-token', 'expires_in': float('inf')},
    {'access_token': 'synthetic-token', 'expires_in': True},
    {'access_token': 'synthetic-token', 'expires_in': -1},
    {'access_token': 'synthetic-token', 'token_type': 'unsupported'},
])
def test_bad_token_response_never_becomes_a_cached_credential(body):
    auth, response = auth_with_response(body)
    with pytest.raises(SMARTAuthError):
        auth.token()
    assert auth._token is None and auth._expires_at == 0
    response.close.assert_called_once()


def test_token_logs_do_not_echo_untrusted_scope_or_expiry(caplog):
    auth, response = auth_with_response({'access_token': 'synthetic-token', 'expires_in': 3600,
                                        'scope': 'SYNTHETIC-PRIVATE-SERVER-CONTENT'})
    with caplog.at_level('INFO', logger='clinloop.smart_auth'):
        assert auth.token() == 'synthetic-token'
    assert 'SYNTHETIC-PRIVATE-SERVER-CONTENT' not in caplog.text
    assert 'synthetic-token' not in caplog.text
    response.close.assert_called_once()


def test_token_post_does_not_follow_a_redirect_with_credentials():
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            paths.append(self.path)
            if self.path == '/token':
                self.send_response(307)
                self.send_header('Location', '/redirect-target')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            data = json.dumps({'access_token': 'synthetic-token', 'expires_in': 3600}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    auth = SMARTBackendAuth(base, 'synthetic-client', client_secret='synthetic-secret',
                           secret_method='post', scope='system/Patient.read', token_url=base+'/token')
    try:
        with pytest.raises(SMARTAuthError, match='HTTP 307'):
            auth.token()
        assert paths == ['/token']
    finally:
        auth.http.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize('url', [
    'http://synthetic.example/token', 'https://user:secret@synthetic.example/token',
    'https://synthetic.example/token#fragment', 'not-a-url', 123,
])
def test_invalid_token_endpoint_is_refused_before_credentials_are_sent(url):
    auth, _ = auth_with_response({'access_token': 'synthetic-token'})
    auth._token_url = url
    with pytest.raises(SMARTAuthError):
        auth.token()
    auth.http.post.assert_not_called()


def test_tiff_budget_counts_pixels_after_ocr_upscaling():
    stream = io.BytesIO()
    frame = Image.new('RGB', (200, 1000), 'white')
    frame.save(stream, format='TIFF', save_all=True, append_images=[frame] * 6)
    # Input: 1.4M pixels. OCR resizing: 7 * 11.25M = 78.75M > 48M total.
    with patch.object(documents, 'ocr_available', return_value=True), \
         patch.object(documents, '_ocr_image', return_value=('SYNTHETIC readable page', 90)) as ocr:
        with pytest.raises(documents.DocumentError, match='rendering limit'):
            documents.extract_text(stream.getvalue(), 'synthetic.tiff')
    assert ocr.call_count == 4


@pytest.mark.parametrize('field,value', [
    ('issue', None), ('issue', ['SYNTHETIC-PRIVATE-OUTCOME']),
    ('issue', [{'severity': 'not-a-severity'}]),
    ('issue', [{'severity': {'SYNTHETIC-PRIVATE': 'value'}}]),
    ('link', {'relation': 'next'}), ('link', ['SYNTHETIC-PRIVATE-LINK']),
    ('link', [{'relation': 'next', 'url': None}]),
])
def test_malformed_fhir_shapes_record_failed_ingestion_instead_of_crashing_or_success(field, value):
    body = {'resourceType': 'Bundle', 'type': 'searchset'}
    if field == 'issue':
        body['entry'] = [{'resource': {'resourceType': 'OperationOutcome', 'issue': value}}]
    else:
        body['link'] = value
    response = Mock(status_code=200)
    response.json.return_value = body
    response.iter_content.return_value = [json.dumps(body).encode()]
    client = FHIRClient('https://synthetic.example/fhir')
    store = LoopStore()
    try:
        with patch.object(client, '_get', return_value=response):
            result = sync_once(store, client, now=datetime(2026, 10, 29))
        assert result['ok'] is False
        assert 'SYNTHETIC-PRIVATE' not in str(result)
        response.close.assert_called_once()
    finally:
        client.session.close()
        store._db.close()


@pytest.mark.parametrize('body', [[], None, 'SYNTHETIC-PRIVATE-METADATA'])
def test_bad_discovery_documents_do_not_crash_or_send_credentials(body):
    auth, _ = auth_with_response({'access_token': 'synthetic-token'})
    auth._token_url = None
    responses = [Mock(status_code=200), Mock(status_code=200)]
    for response in responses:
        response.json.return_value = body
    auth.http.get.side_effect = responses
    with pytest.raises(SMARTAuthError):
        auth.token()
    auth.http.post.assert_not_called()
    for response in responses:
        response.close.assert_called_once()


@pytest.mark.parametrize('field,value', [
    ('capabilities', 7), ('capabilities', 'permission-v2'),
    ('scopes_supported', {}), ('scopes_supported', [None]),
])
def test_bad_discovery_scope_metadata_is_refused_before_token_post(field, value):
    auth, _ = auth_with_response({'access_token': 'synthetic-token'})
    auth._scope = auth._token_url = None
    response = Mock(status_code=200)
    response.json.return_value = {'token_endpoint': 'https://synthetic.example/token', field: value}
    auth.http.get.return_value = response
    with pytest.raises(SMARTAuthError):
        auth.token()
    auth.http.post.assert_not_called()
    response.close.assert_called_once()


def test_biomedical_transport_error_does_not_expose_source_text():
    async def failure():
        raise RuntimeError('SYNTHETIC-PRIVATE-TRANSPORT-CONTENT')
    with pytest.raises(biomcp_client.BioMCPError) as error:
        biomcp_client._run(failure())
    assert 'SYNTHETIC-PRIVATE' not in str(error.value)


def test_biomedical_tool_error_does_not_echo_the_provider_payload():
    async def error_response(_callback):
        return SimpleNamespace(isError=True, content=[SimpleNamespace(text='SYNTHETIC-PRIVATE-PROVIDER-CONTENT')])
    with patch.object(biomcp_client, 'enabled', return_value=True), \
         patch.object(biomcp_client, '_with_session', new=error_response), \
         patch.object(biomcp_client, '_cache', Mock(get=Mock(return_value=None))):
        with pytest.raises(biomcp_client.BioMCPError) as error:
            biomcp_client.call_tool('article_searcher', {'keywords': ['synthetic']})
    assert 'SYNTHETIC-PRIVATE' not in str(error.value)


def test_refused_biomedical_tool_name_is_not_reflected_into_errors():
    with patch.object(biomcp_client, 'enabled', return_value=True):
        with pytest.raises(biomcp_client.BioMCPError) as error:
            biomcp_client.call_tool('SYNTHETIC-PRIVATE-TOOL-NAME', {})
    assert 'SYNTHETIC-PRIVATE' not in str(error.value)


@pytest.mark.parametrize('field,value', [
    ('deleted', [{'type': 'Bundle', 'url': 'https://synthetic.example/deletions'}]),
    ('deleted', None),
    ('link', [{'relation': 'next', 'url': 'https://synthetic.example/next-manifest'}]),
    ('link', None),
    ('outcome', [{'url': 'https://synthetic.example/outcomes'}]),
    ('outcome', None),
    ('transactionTime', None), ('transactionTime', 'not-a-time'),
    ('transactionTime', '2026-10-29'), ('transactionTime', '2026-10-29T00:00:00'),
])
def test_unsupported_bulk_content_cannot_advance_the_cursor_or_change_the_mirror(field, value):
    store = LoopStore()
    source, cursor = 'synthetic-bulk', '2026-09-01T00:00:00Z'
    store.set_cursor(source, cursor)
    store.mirror_upsert([('Patient', 'SYNTHETIC-1', 'SYNTHETIC-1',
                          {'resourceType': 'Patient', 'id': 'SYNTHETIC-1'})])
    client = BulkFHIRClient('https://synthetic.example/fhir', store=store)
    manifest = {'transactionTime': '2026-10-29T00:00:00Z', 'output': [], 'error': [],
                'requiresAccessToken': True, field: value}
    try:
        with patch.object(client, 'kick_off', return_value='https://synthetic.example/status'), \
             patch.object(client, 'wait', return_value=manifest), \
             patch.object(client, 'download', return_value=iter([])) as download, \
             patch.object(client, 'cancel') as cleanup:
            result = sync_once(store, client, source=source, now=datetime(2026, 10, 29))
        assert result['ok'] is False
        assert store.get_cursor(source) == cursor and store.mirror_size() == 1
        download.assert_not_called()
        cleanup.assert_called_once()
    finally:
        client.session.close()
        store._db.close()
