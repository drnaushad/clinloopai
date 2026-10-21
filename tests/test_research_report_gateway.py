"""Synthetic contract and isolation checks; never call a paid API."""
import copy
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from src.research_report_gateway import create_app, verify_review, response_review, ERROR

TOKEN = 'synthetic_gateway_code_' + 'x' * 32
ORIGIN = 'https://clinloopai.app'
TEXT = 'SYNTHETIC: No pleural effusion. A 6 mm lung nodule is present. Recommend CT in 6 months.'
REVIEW = {'findings': [{'quote': 'A 6 mm lung nodule is present.', 'assertion': 'present',
                       'follow_up_quote': 'Recommend CT in 6 months.', 'deadline_quote': '6 months'}],
          'missing_context': ['Comparison imaging not supplied.']}


def response(value=REVIEW, **changes):
    return {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': json.dumps(value)}]}], **changes}


class FakeResponse:
    status_code = 200
    def __init__(self, value=None): self.value = value or response()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, _size): yield json.dumps(self.value).encode()


def client(**changes):
    settings = {'token': TOKEN, 'api_key': 'synthetic-api-key-never-sent', 'model': 'synthetic-test-model', 'origin': ORIGIN, **changes}
    transport = Mock(); transport.post.return_value = FakeResponse()
    app = create_app(settings, transport)
    return TestClient(app, base_url='http://127.0.0.1:18127',
                      headers={'Origin': ORIGIN, 'Authorization': 'Bearer ' + TOKEN}), transport


def payload(**changes):
    return {'text': TEXT, 'report_type': 'radiology-text', 'synthetic_only': True, 'external_api_allowed': True, **changes}


def test_exact_source_contract():
    assert verify_review(REVIEW, TEXT) == REVIEW
    for change in [{'quote': 'Invented cancer.'}, {'follow_up_quote': 'Recommend surgery.'},
                   {'deadline_quote': '6 mm'}, {'assertion': 'diagnosed'}, {'extra': 'not allowed'}]:
        value = copy.deepcopy(REVIEW); value['findings'][0].update(change)
        with pytest.raises(Exception): verify_review(value, TEXT)


def test_empty_review_still_requires_human_review():
    c, transport = client();transport.post.return_value=FakeResponse(response({'findings': [], 'missing_context': []}))
    r=c.post('/review/analyze',json=payload())
    assert r.status_code == 200 and r.json()['human_review_required'] is True


def test_refusal_incomplete_tools_and_malformed_output_rejected():
    for value in [response(status='incomplete'), response(error={'message':'synthetic private marker'}),
                  {'status':'completed','output':[{'type':'function_call'}]},
                  {'status':'completed','output':[{'type':'message','role':'assistant','status':'completed',
                    'content':[{'type':'refusal','refusal':'no'}]}]}, response({'findings': []})]:
        with pytest.raises(Exception): response_review(value, TEXT)


def test_authorized_status_never_contains_api_key():
    c, transport=client();r=c.get('/review/status')
    assert r.status_code==200 and r.json()['configured'] is True
    assert 'synthetic-api-key' not in r.text and 'Bearer' not in r.text
    transport.post.assert_not_called()


@pytest.mark.parametrize('headers',[{'Origin':'https://evil.test'},{'Origin':''},{'Host':'evil.test:18127'},
                                     {'Authorization':'Bearer invalid'},{'Authorization':''}])
def test_wrong_origin_host_or_access_code_no_network(headers):
    c,transport=client();r=c.post('/review/analyze',headers=headers,json=payload())
    assert r.status_code in (401,403);transport.post.assert_not_called()


@pytest.mark.parametrize('changes',[{'synthetic_only':False},{'external_api_allowed':False},
                                    {'synthetic_only':'true'},{'report_type':'dicom'}, {'text':''},
                                    {'text':'한'*2500},{'api_key':'must-not-be-accepted'}, {'text':123}])
def test_input_rejected_without_cloud_call(changes):
    c,transport=client();r=c.post('/review/analyze',json=payload(**changes))
    assert r.status_code in (403,422,413);transport.post.assert_not_called()
    assert 'must-not-be-accepted' not in r.text


def test_oversized_chunked_body_rejected_before_parse():
    c,transport=client();r=c.post('/review/analyze',content=iter([b'x'*9000,b'y'*9000]))
    assert r.status_code==413;transport.post.assert_not_called()


def test_key_and_model_must_be_configured_without_leaking_settings():
    c,transport=client(api_key='');r=c.post('/review/analyze',json=payload())
    assert r.status_code==503;transport.post.assert_not_called()


def test_fixed_cloud_destination_schema_store_false_no_tools_no_redirects():
    c,transport=client();r=c.post('/review/analyze',json=payload())
    assert r.status_code==200 and r.json()['review']==REVIEW
    args,kwargs=transport.post.call_args
    assert args==('https://api.openai.com/v1/responses',)
    assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
    body=kwargs['json'];assert body['store'] is False and body['stream'] is False
    assert body['truncation']=='disabled' and body['text']['format']['strict'] is True
    assert 'tools' not in body and 'previous_response_id' not in body
    assert 'api_key' not in json.dumps(body)
    assert r.headers['cache-control']=='no-store'


def test_errors_do_not_reflect_provider_content_or_secrets():
    c,transport=client();transport.post.side_effect=RuntimeError('synthetic API key and report private marker')
    r=c.post('/review/analyze',json=payload())
    assert r.status_code==502 and r.json()['detail']==ERROR
    assert 'private marker' not in r.text


def test_invalid_evidence_does_not_return_partial_analysis():
    c,transport=client();value=copy.deepcopy(REVIEW);value['findings'][0]['deadline_quote']='tomorrow'
    transport.post.return_value=FakeResponse(response(value))
    r=c.post('/review/analyze',json=payload());assert r.status_code==502 and 'review' not in r.json()


def test_rate_limit_does_not_make_a_thirteenth_paid_call():
    c,transport=client()
    for _ in range(12):assert c.post('/review/analyze',json=payload()).status_code==200
    assert c.post('/review/analyze',json=payload()).status_code==429
    assert transport.post.call_count==12


def test_cors_exact_origin_without_cookies():
    c,_=client();r=c.options('/review/analyze',headers={'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
    assert r.status_code==200 and r.headers['access-control-allow-origin']==ORIGIN
    assert 'access-control-allow-credentials' not in r.headers


def test_no_wildcards_nonloopback_preview_or_weak_gateway_codes():
    for settings in [{'token':'short'}, {'token':TOKEN,'origin':'*'}, {'token':TOKEN,'origin':'https://evil.test'},
                     {'token':TOKEN,'model':'model\r\nheader'}]:
        with pytest.raises(ValueError):create_app(settings)
