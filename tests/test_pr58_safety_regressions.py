"""Adversarial synthetic checks for PR58; never call a model or use patient records."""
import json
from datetime import timedelta, timezone
from unittest import mock

import pytest

from test_second_reader import NOW, PATIENT, UNUSUAL, FakeModel, report
from src.clinloop_engine import second_reader as sr
from src.clinloop_engine.fhir_ingest import _status
from src.clinloop_engine.loop_store import LoopStore
from src.validation import dataset_evaluation as evaluation


@pytest.mark.parametrize('subject', [{'reference': 'Patient/OTHER'}, {'reference': 'Group/P'}, {}, None])
def test_reader_never_sends_a_foreign_or_unresolved_subject_to_model(subject):
    resource = report(UNUSUAL)
    resource['subject'] = subject
    model, store = FakeModel([]), LoopStore()
    assert sr.second_read_patient(store, 'P', [PATIENT, resource], model=model, now=NOW, silent=True) == []
    assert model.prompts == []
    assert store.second_read_counts()['reports_read'] == 0


def test_future_reports_are_not_read_and_aware_evaluation_time_is_supported():
    model, store = FakeModel([]), LoopStore()
    resource = report(UNUSUAL, when=(NOW + timedelta(days=1)).isoformat()+'Z')
    sr.second_read_patient(store, 'P', [PATIENT, resource], model=model,
                           now=NOW.replace(tzinfo=timezone.utc), silent=True)
    assert model.prompts == []


def test_rejected_source_items_cannot_be_cached_as_a_clean_read():
    model, store = FakeModel([{'category': 'imaging_followup', 'quote': 'INVENTED QUOTE'}]), LoopStore()
    for _ in range(2):
        sr.second_read_patient(store, 'P', [PATIENT, report(UNUSUAL)], model=model, now=NOW, silent=True)
    assert len(model.prompts) == 2
    assert store.second_read('P|r1')['status'] == 'failed'
    assert 'INVENTED' not in store.second_read('P|r1')['detail']


def test_silent_mode_read_cannot_suppress_later_research_flags():
    item = {'category': 'imaging_followup', 'quote': 'Please obtain a dedicated pelvic MRI'}
    model, store = FakeModel([item]), LoopStore()
    with mock.patch('src.clinloop_engine.profile.allows', return_value=True):
        sr.second_read_patient(store, 'P', [PATIENT, report(UNUSUAL)], model=model, now=NOW, silent=True)
        flags = sr.second_read_patient(store, 'P', [PATIENT, report(UNUSUAL)], model=model, now=NOW, silent=False)
    assert len(flags) == 1
    assert len(model.prompts) == 2


@pytest.mark.parametrize('intent', ['proposal', 'plan', 'option', None, 'unknown'])
@pytest.mark.parametrize('status', ['active', 'completed'])
def test_service_request_without_order_intent_is_not_completion_evidence(intent, status):
    resource = {'resourceType': 'ServiceRequest', 'status': status, 'intent': intent}
    assert _status(resource) not in {'ordered', 'completed'}


@pytest.fixture
def study():
    from test_dataset_evaluation import TestDatasetEvaluation
    fixture = TestDatasetEvaluation()
    fixture.setUp()
    fixture.complete_reviews()
    yield fixture
    fixture.doCleanups()


def test_failed_rescore_cannot_leave_a_stale_accuracy_file(study):
    evaluation.score_study(study.out)
    path = study.out/'reviewer_1.csv'
    rows = list(evaluation.read_sheet(path).values())
    rows[0]['label_status'] = ''
    evaluation.write_sheet(path, rows)
    with pytest.raises(ValueError):
        evaluation.score_study(study.out)
    assert not (study.out/'accuracy.json').exists()


def test_unavailable_rule_prediction_cannot_count_as_a_correct_deadline(study):
    for name in ['reviewer_1.csv', 'reviewer_2.csv']:
        path = study.out/name
        rows = list(evaluation.read_sheet(path).values())
        rows[0].update(min_deadline_days='1', max_deadline_days='10')
        evaluation.write_sheet(path, rows)
    path = study.out/'predictions.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0].update(available=False, action=None, deadline_days={'R003': 5})
    path.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
    result = evaluation.score_study(study.out)
    assert result['rules_deadline_accuracy'] == 0


def test_benchmark_rejects_duplicate_scenario_keys_before_prediction():
    from src.clinloop_engine.benchmark import BenchmarkSuite
    from src.clinloop_engine.data_generator import generate_all_scenarios
    rows = [s.to_dict() for s in generate_all_scenarios(30)]
    rows[1]['scenario_id'] = rows[0]['scenario_id']
    with pytest.raises(ValueError, match='unique'):
        BenchmarkSuite(rows).run()


def test_equivalent_numeric_predictors_stay_in_the_same_holdout_group():
    from src.validation.learned_baselines import grouped_split
    rows = [{'patient_id': str(i)} for i in range(4)]
    features = [{'x': 1}, {'x': 1.0, 'explicit_zero': 0.0}] + [{'x': i} for i in range(2, 4)]
    train, test, _ = grouped_split(rows, features)
    assert ({0, 1} <= set(train)) or ({0, 1} <= set(test))


@pytest.mark.parametrize('intent', ['order', 'original-order', 'reflex-order', 'filler-order', 'instance-order'])
def test_authorized_service_request_intents_preserve_issued_order_semantics(intent):
    assert _status({'resourceType': 'ServiceRequest', 'status': 'active', 'intent': intent}) == 'ordered'


@pytest.mark.parametrize('change', ['checkpoint', 'returned_model', 'unavailable_checkpoint'])
def test_study_rejects_model_or_weights_changed_during_inference(change):
    expected = {'model': 'synthetic-model', 'digest': 'a'*64}
    after = {**expected, 'digest': 'b'*64} if change == 'checkpoint' else None if change == 'unavailable_checkpoint' else expected
    prediction = {'available': True, 'model': 'wrong-model' if change == 'returned_model' else expected['model'], 'items': []}
    with mock.patch('src.clinloop_engine.model_registry.checkpoint_identity', side_effect=[expected, after]), \
            mock.patch('src.clinloop_engine.second_reader.read_report', return_value=prediction):
        with pytest.raises(ValueError, match='checkpoint'):
            evaluation._predict_model('Synthetic text', expected['model'], expected['digest'])


def test_partial_source_verification_is_study_abstention_not_negative():
    identity = {'model': 'synthetic-model', 'digest': 'a'*64}
    prediction = {'available': True, 'model': identity['model'], 'items': [],
                  'verification_incomplete': True, 'dropped': 1}
    with mock.patch('src.clinloop_engine.model_registry.checkpoint_identity', return_value=identity), \
            mock.patch('src.clinloop_engine.second_reader.read_report', return_value=prediction):
        result = evaluation._predict_model('Synthetic text', identity['model'], identity['digest'])
    assert result['available'] is False
    assert result['items'] == []


def test_mixed_patient_trajectory_cannot_be_relabelled_by_the_caller():
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    event = {'patient_id': 'SENSITIVE_OTHER_PATIENT', 'event_id': 'synthetic-fit',
             'event_type': 'lab_result', 'timestamp': '2026-01-01T00:00:00',
             'status': 'completed', 'details': {'condition': 'positive_fit'}}
    with pytest.raises(ValueError) as exc:
        ClinLoopDetector(evaluation_time=NOW).process_patient('synthetic', 'P', [event])
    assert 'SENSITIVE' not in str(exc.value)


@pytest.mark.parametrize('status', ['final', 'amended', 'corrected', 'appended'])
def test_result_finalisation_status_cannot_close_a_direct_procedure_event(status):
    from src.clinloop_engine.temporal_hypergraph import DynamicTemporalHypergraph
    from src.clinloop_engine.clinical_ontology import is_fulfilling_status
    trigger = {'patient_id': 'P', 'event_id': 'synthetic-fit', 'event_type': 'lab_result',
               'timestamp': '2026-01-01T00:00:00', 'status': 'completed',
               'details': {'test': 'FIT', 'result': 'positive'}}
    procedure = {'patient_id': 'P', 'event_id': 'synthetic-col', 'event_type': 'colonoscopy',
                 'timestamp': '2026-01-03T00:00:00', 'status': status, 'details': {}}
    graph = DynamicTemporalHypergraph(evaluation_time=NOW)
    graph.build_from_patient_trajectory([trigger, procedure])
    loop = next(e for e in graph.get_all_loops() if e.obligation_rule.rule_id == 'R017')
    assert loop.status == 'open'
    assert is_fulfilling_status(status, 'lab_result')


@pytest.mark.parametrize('years', [0.5, 1, 2, 3, 5])
def test_year_based_surveillance_uses_the_calendar_anchor(years):
    from datetime import datetime
    from src.clinloop_engine.radiology import YEAR, _calendar_due, _nominal_calendar_days
    anchor = datetime(2023, 10, 31, 12, 30)
    expected = (_calendar_due(anchor, int(years*12))-anchor).total_seconds()/86400
    assert _nominal_calendar_days(years*YEAR, anchor) == expected


def test_changed_rule_coverage_invalidates_second_reader_cache():
    from types import SimpleNamespace
    item = {'category': 'imaging_followup', 'quote': 'Please obtain a dedicated pelvic MRI'}
    model, store = FakeModel([item]), LoopStore()
    covered = SimpleNamespace(trigger_event_id='DiagnosticReport/r1:radiology_report', rule_id='R031')
    with mock.patch('src.clinloop_engine.loop_detector.ClinLoopDetector.process_patient', return_value=[covered]):
        sr.second_read_patient(store, 'P', [PATIENT, report(UNUSUAL)], model=model, now=NOW, silent=True)
    with mock.patch('src.clinloop_engine.loop_detector.ClinLoopDetector.process_patient', return_value=[]):
        sr.second_read_patient(store, 'P', [PATIENT, report(UNUSUAL)], model=model, now=NOW, silent=True)
    assert len(model.prompts) == 2
    counts = store.second_reader_suggestion_counts()['imaging_followup']
    assert counts['n'] == 1 and counts['reviewed'] == 0
