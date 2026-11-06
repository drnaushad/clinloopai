"""Synthetic serialization/source-integrity regressions; no clinical reference claims."""
import json
from pathlib import Path

import pytest

from src.clinloop_engine.model_json import strict_object
from src.clinloop_engine.second_reader import read_report
from src.research_report_gateway import parse_provider_response, verify_review


@pytest.mark.parametrize('source', [
    '{"items":[{"quote":"synthetic"}],"items":[]}',
    '{"items":[{"category":"critical_finding","category":"imaging_followup"}]}',
    '{"items":[],"item\\u0073":[1]}',
    '{"items":[]} {"items":[1]}',
    'Explanation: {"items":[]}',
    '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}', '{"value":1e999}',
    '[]', 'null', '{"items":[]',
])
def test_ambiguous_model_json_is_not_salvaged_as_a_clean_answer(source):
    with pytest.raises(ValueError):
        strict_object(source, fenced=True)
    model = lambda *args: {'text': source, 'model': 'synthetic-test-model'}
    result = read_report('SYNTHETIC: Review original source.', model)
    assert not result['available'] and result['items'] == []


def test_json_braces_escapes_and_a_single_local_fence_are_preserved():
    value = {'items': [{'quote': 'SYNTHETIC: literal } and { and "quoted" text.'}]}
    source = json.dumps(value)
    assert strict_object(source) == value
    assert strict_object('```json\n'+source+'\n```', fenced=True) == value
    with pytest.raises(ValueError):
        strict_object('```json\n'+source+'\n```')


def test_excessive_second_reader_items_are_unavailable_not_a_partial_read():
    model = lambda *args: {'text': json.dumps({'items': [{'category': 'imaging_followup', 'quote': 'SYNTHETIC'}]*31})}
    result = read_report('SYNTHETIC: Review original source.', model)
    assert not result['available'] and result['items'] == []


@pytest.mark.parametrize('text', [
    'SYNTHETIC: No pleural effusion.',
    'SYNTHETIC: Without pleural effusion.',
    'SYNTHETIC: Negative for pleural effusion.',
    'SYNTHETIC: pleural effusion noted historically. No pleural effusion now.',
])
def test_gateway_does_not_accept_present_when_a_matching_context_is_negated(text):
    finding = {'quote': 'pleural effusion', 'assertion': 'present', 'follow_up_quote': '', 'deadline_quote': ''}
    with pytest.raises(ValueError):
        verify_review({'findings': [finding], 'missing_context': []}, text)
    # Reject, never silently reclassify. The original model assertion is unchanged.
    assert finding['assertion'] == 'present'
    finding['assertion'] = 'negated'
    assert verify_review({'findings': [finding], 'missing_context': []}, text)['findings'][0] == finding


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'gemini'])
def test_every_cloud_parser_rejects_shadowed_findings(provider):
    from tests.test_research_report_gateway import vendor_response
    envelope = vendor_response(provider)
    raw = '{"findings":[{"quote":"SYNTHETIC","assertion":"present","follow_up_quote":"","deadline_quote":""}],"findings":[],"missing_context":[]}'
    if provider == 'openai':
        envelope['output'][0]['content'][0]['text'] = raw
    elif provider == 'anthropic':
        envelope['content'][0]['text'] = raw
    else:
        envelope['candidates'][0]['content']['parts'][0]['text'] = raw
    with pytest.raises(ValueError):
        parse_provider_response(provider, envelope, 'SYNTHETIC: Original report.')


def test_parser_changes_invalidate_reader_cache_and_clinical_signoff(monkeypatch):
    from src.clinloop_engine import second_reader, governance
    from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES
    before = second_reader.reader_contract()
    original = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda path: original(path) + (b' synthetic-change' if path.name == 'model_json.py' else b''))
    assert second_reader.reader_contract() != before
    assert 'model_json.py' in governance._DECISION_SOURCES
    assert governance.rule_fingerprint(OBLIGATION_RULES[0])
