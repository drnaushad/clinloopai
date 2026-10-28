"""Personal setup isolation and credential lifecycle; all provider calls mocked."""
import json
import os
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from src.research_report_gateway import create_app
from tests.test_research_report_gateway import TOKEN, ORIGIN, payload, FakeResponse, vendor_response

LOCAL = 'http://127.0.0.1:18127'
KEY = 'synthetic-only-provider-key-not-a-real-credential'


def setup_client(enabled=True, peer='127.0.0.1'):
    transport = Mock()
    app = create_app({'token': TOKEN, 'origin': ORIGIN, 'local_setup': enabled}, transport)
    return TestClient(app, base_url=LOCAL, client=(peer, 55000),
                      headers={'Origin': LOCAL, 'Authorization': 'Bearer ' + TOKEN}), transport


def config(provider='openai', **changes):
    return {'provider': provider, 'model': 'synthetic-text-model', 'api_key': KEY, **changes}


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'gemini'])
def test_local_setup_selected_provider_isolated_and_can_be_forgotten(provider):
    c, transport = setup_client()
    saved = c.post('/review/configure', json=config(provider))
    assert saved.status_code == 200
    assert saved.json()['credential_checked_with_provider'] is False
    assert KEY not in saved.text
    status = c.get('/review/status').json()
    assert {p['id'] for p in status['providers'] if p['configured']} == {provider}
    assert KEY not in json.dumps(status)
    transport.post.assert_not_called()  # Saving never verifies a key or incurs a charge.
    transport.post.return_value = FakeResponse(vendor_response(provider))
    analyzed = c.post('/review/analyze', headers={'Origin': ORIGIN}, json=payload(provider=provider))
    assert analyzed.status_code == 200
    assert KEY in json.dumps(transport.post.call_args.kwargs['headers'])
    assert KEY not in analyzed.text
    assert c.post('/review/forget', json={'provider': provider}).status_code == 200
    assert c.post('/review/analyze', headers={'Origin': ORIGIN}, json=payload(provider=provider)).status_code == 503
    assert transport.post.call_count == 1


@pytest.mark.parametrize('path,method', [('/setup','GET'),('/setup.js','GET'),('/setup.css','GET'),
                                        ('/review/configure','POST'),('/review/forget','POST')])
def test_setup_not_enabled_by_default(path, method):
    c, transport = setup_client(False)
    assert c.request(method, path, json=config()).status_code == 403
    transport.post.assert_not_called()


@pytest.mark.parametrize('headers', [{'Origin': ORIGIN}, {'Origin': 'https://evil.test'},
                                     {'Origin': ''}, {'Host': 'evil.test:18127'}, {'Host': 'localhost:18127'}])
def test_key_mutation_never_available_to_public_or_wrong_host(headers):
    c, transport = setup_client()
    assert c.post('/review/configure', headers=headers, json=config()).status_code == 403
    transport.post.assert_not_called()


@pytest.mark.parametrize('peer', ['192.168.1.2', '::1', 'testclient'])
def test_remote_peers_cannot_load_setup_or_change_config(peer):
    c, transport = setup_client(peer=peer)
    assert c.get('/setup').status_code == 403
    assert c.post('/review/configure', json=config()).status_code == 403
    transport.post.assert_not_called()


@pytest.mark.parametrize('path', ['/review/configure', '/review/forget'])
def test_configuration_always_requires_separate_access_code(path):
    c, _ = setup_client()
    assert c.post(path, headers={'Authorization': ''}, json=config()).status_code == 401


@pytest.mark.parametrize('change', [{'api_key': 'short'}, {'api_key': KEY+'\r\nX: y'},
                                    {'model': 'models/unsafe'}, {'model': 'sk-credential'},
                                    {'provider': 'unknown'}, {'extra': KEY}])
def test_bad_configuration_never_reflects_secrets_or_contacts_provider(change):
    c, transport = setup_client()
    r = c.post('/review/configure', json=config(**change))
    assert r.status_code == 422 and KEY not in r.text
    assert not any(p['configured'] for p in c.get('/review/status').json()['providers'])
    transport.post.assert_not_called()


def test_setup_assets_allow_direct_navigation_but_no_secrets_or_frame_embedding():
    c, _ = setup_client()
    c.headers.pop('Origin')
    for path in ['/setup', '/setup.js', '/setup.css']:
        r = c.get(path)
        assert r.status_code == 200 and KEY not in r.text and TOKEN not in r.text
        assert r.headers['cache-control'] == 'no-store'
        assert "frame-ancestors 'none'" in r.headers['content-security-policy']
        assert r.headers['x-frame-options'] == 'DENY'
    assert c.get('/review/status').status_code == 200
    assert c.post('/review/configure', json=config()).status_code == 403  # No-Origin mutations refused.


def test_local_setup_bundle_supports_language_and_nonsecret_handoff_without_external_scripts():
    c, transport = setup_client()
    c.headers.pop('Origin')
    html = c.get('/setup?provider=anthropic&lang=ko').text
    script = c.get('/setup.js').text
    assert 'data-isolated-session="true"' in html
    assert 'id="lang-opt-en"' in html and 'id="lang-opt-ko"' in html
    assert 'ClinLoopInterfaceCopy' in script and 'ClinLoopUI' in script
    assert 'private-workspace' not in script  # No model transport or report input in key setup.
    assert 'provider=' in script and 'key=do-not-import' not in script
    assert KEY not in script and TOKEN not in script
    transport.post.assert_not_called()


def test_setup_bundle_and_schema_resolve_in_packaged_web_layout(monkeypatch, tmp_path):
    import shutil
    from src import research_report_gateway as gateway
    root = gateway.ROOT
    for name in ['js/interface-copy.js', 'js/interface-language.js',
                 'js/language-controls.js', 'data/report_review_schema.json']:
        destination = tmp_path / 'web' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
    destination = tmp_path / 'src/research_setup/setup.js'
    destination.parent.mkdir(parents=True)
    shutil.copyfile(root / 'src/research_setup/setup.js', destination)
    monkeypatch.setattr(gateway, 'ROOT', tmp_path)
    assert json.loads(gateway.web_asset('data/report_review_schema.json').read_text()) == gateway.SCHEMA
    c, transport = setup_client()
    response = c.get('/setup.js')
    assert response.status_code == 200 and 'ClinLoopUI' in response.text
    assert KEY not in response.text and TOKEN not in response.text
    transport.post.assert_not_called()


def test_configuration_refused_while_analysis_uses_the_selected_key():
    c, transport = setup_client()
    assert c.post('/review/configure', json=config()).status_code == 200
    def while_running(*args, **kwargs):
        assert c.post('/review/configure', json=config(api_key='different-synthetic-key')).status_code == 429
        assert c.post('/review/forget', json={'provider': 'openai'}).status_code == 429
        return FakeResponse()
    transport.post.side_effect = while_running
    assert c.post('/review/analyze', headers={'Origin': ORIGIN}, json=payload()).status_code == 200
    assert KEY in json.dumps(transport.post.call_args.kwargs['headers'])


def test_two_gateway_instances_never_share_user_credentials():
    first, _ = setup_client()
    second, _ = setup_client()
    first.post('/review/configure', json=config())
    assert not any(p['configured'] for p in second.get('/review/status').json()['providers'])


def test_setup_helper_never_prompts_for_provider_key_and_removes_private_code_file(monkeypatch, tmp_path, capsys):
    from scripts import run_research_review as helper
    seen = {}
    monkeypatch.setattr(helper, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['run_research_review.py', '--setup'])
    monkeypatch.setattr('builtins.input', lambda *_: pytest.fail('Setup must not prompt in terminal'))
    monkeypatch.setattr(helper.getpass, 'getpass', lambda *_: pytest.fail('Setup must not request a terminal key'))
    # Let monkeypatch restore the helper's environment mutations after this test.
    monkeypatch.setenv('CLINLOOP_RESEARCH_GATEWAY_TOKEN', 'temporary-test-placeholder')
    monkeypatch.setenv('CLINLOOP_RESEARCH_LOCAL_SETUP', '0')
    def run():
        paths = list((tmp_path / 'data/secrets/research-review').glob('access-code-*.txt'))
        assert len(paths) == 1 and paths[0].stat().st_mode & 0o777 == 0o600
        seen['code'] = paths[0].read_text().strip()
        assert seen['code'] == os.environ['CLINLOOP_RESEARCH_GATEWAY_TOKEN']
        assert os.environ['CLINLOOP_RESEARCH_LOCAL_SETUP'] == '1'
    monkeypatch.setattr('src.research_report_gateway.main', run)
    helper.main()
    output = capsys.readouterr().out
    assert '/setup' in output and seen['code'] not in output
    assert not list((tmp_path / 'data/secrets/research-review').glob('access-code-*.txt'))
