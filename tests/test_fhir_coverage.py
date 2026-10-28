"""Coverage counters must not turn export success into report-analysis claims."""
import copy
import json
import sqlite3
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.clinloop_engine.fhir_coverage import empty_coverage, report_coverage, safe_coverage
from src.clinloop_engine.fhir_sync import sync_once
from src.clinloop_engine.loop_store import LoopStore


def test_report_field_presence_is_partitioned_without_fetching_or_guessing():
    records = [
        {'resourceType': 'DiagnosticReport', 'conclusion': 'SYNTHETIC'},
        {'resourceType': 'DiagnosticReport', 'conclusionCode': [{'text': 'SYNTHETIC code'}]},
        {'resourceType': 'DiagnosticReport', 'presentedForm': [{'url': 'Binary/synthetic'}]},
        {'resourceType': 'DiagnosticReport', 'result': [{'reference': 'Observation/synthetic'}]},
        {'resourceType': 'DiagnosticReport'},
        {'resourceType': 'DocumentReference', 'content': [{'attachment': {'contentType': 'text/html', 'data': 'ZmFrZQ=='}}]},
        {'resourceType': 'DocumentReference', 'content': [{'attachment': {'url': 'Binary/synthetic'}}]},
    ]
    original = copy.deepcopy(records)
    result = report_coverage(records)
    assert result['diagnostic_reports'] == 5
    assert result['reports_with_attachments'] == 1
    for key in ('with_conclusion', 'with_coded_conclusion_only', 'attachment_only',
                'linked_results_only', 'without_summary_or_attachment',
                'document_reference_inline_text', 'document_reference_linked_only'):
        assert result[key] == 1
    assert records == original
    assert 'SYNTHETIC' not in json.dumps(result)


def test_warning_categories_count_messages_not_affected_records():
    result = report_coverage([], ['17 mapped resources have missing or unrecognised status',
                                  'FHIR resource: no timestamp; skipped', 'some future warning'])
    assert result['mapping_warning_messages'] == 3
    assert result['warning_categories']['unknown_status'] == 1
    assert result['warning_categories']['missing_timestamp'] == 1
    assert result['warning_categories']['other_mapping_warning'] == 1


def test_coverage_persists_and_is_audited_without_arbitrary_strings(tmp_path):
    path = str(tmp_path / 'local.sqlite')
    store = LoopStore(path)
    coverage = report_coverage([{'resourceType': 'DiagnosticReport'}])
    store.record_ingest('synthetic', 'it', True, patients=1, coverage=coverage)
    assert store.feed_status()['recent_runs'][0]['coverage'] == coverage
    assert store.verify_audit_chain()
    store._db.close()
    reopened = LoopStore(path)
    assert reopened.feed_status()['recent_runs'][0]['coverage'] == coverage
    coverage['source_text'] = 'must not persist'
    with pytest.raises(ValueError):
        reopened.record_ingest('synthetic', 'it', True, coverage=coverage)
    assert 'must not persist' not in json.dumps(reopened.feed_status())


def test_old_ingest_database_migrates_without_losing_runs(tmp_path):
    path = str(tmp_path / 'old.sqlite')
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE ingest_runs (id INTEGER PRIMARY KEY, ts TEXT, source TEXT, actor TEXT, ok INTEGER, patients INTEGER, events INTEGER, warnings INTEGER, error TEXT)')
    db.execute("INSERT INTO ingest_runs VALUES (1,'2026-10-28T00:00:00','old','it',1,7,1,0,NULL)")
    db.commit(); db.close()
    store = LoopStore(path)
    result = store.feed_status(now=datetime(2026, 10, 28, 1))
    assert result['status'] == 'OK'
    assert result['recent_runs'][0]['patients'] == 7
    assert result['recent_runs'][0]['coverage'] is None


def test_sync_records_coverage_but_never_attaches_unfetched_text():
    store = LoopStore()
    client = Mock(spec=['changed_patients', 'patient_history'])
    client.changed_patients.return_value = ({'synthetic'}, '2026-10-28T00:00:00Z')
    history = [{'resourceType': 'Patient', 'id': 'synthetic'},
               {'resourceType': 'DiagnosticReport', 'id': 'synthetic-report', 'status': 'final',
                'subject': {'reference': 'Patient/synthetic'}, 'issued': '2026-10-27T00:00:00Z',
                'presentedForm': [{'contentType': 'application/pdf', 'url': 'Binary/synthetic'}]}]
    client.patient_history.return_value = history
    with patch('src.clinloop_engine.second_reader.running', return_value=False):
        result = sync_once(store, client)
    assert result['ok'] and result['coverage']['attachment_only'] == 1
    assert store.feed_status()['recent_runs'][0]['coverage'] == result['coverage']
    assert 'conclusion' not in history[1]


def test_sync_errors_never_return_or_store_request_urls_or_source_text():
    import requests
    client = Mock(spec=['changed_patients'])
    client.changed_patients.side_effect = requests.ConnectionError('https://secret/?patient=SYNTHETIC_PRIVATE')
    store = LoopStore()
    with patch('src.clinloop_engine.fhir_sync.logger') as log:
        result = sync_once(store, client)
    assert not result['ok']
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(result) + json.dumps(store.feed_status())
    assert 'SYNTHETIC_PRIVATE' not in str(log.mock_calls)


@pytest.mark.parametrize('bad', [-1, True, 1.5, 'source text'])
def test_invalid_counter_values_rejected(bad):
    counters = empty_coverage(); counters['diagnostic_reports'] = bad
    with pytest.raises(ValueError): safe_coverage(counters)


def test_malformed_optional_fields_cannot_break_coverage_reporting():
    result = report_coverage([None, 'unexpected', {'resourceType': 'DiagnosticReport',
                              'conclusionCode': 'wrong', 'presentedForm': None},
                             {'resourceType': 'DocumentReference', 'content': [{'attachment': None},
                              {'attachment': {'contentType': None, 'url': 'Binary/synthetic'}}]}])
    assert result['without_summary_or_attachment'] == 1
    assert result['document_reference_linked_only'] == 1
