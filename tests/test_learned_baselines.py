"""Synthetic-only leakage, temporal-graph and real-fit research regression tests."""
import copy
import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from src.clinloop_engine.benchmark import BenchmarkSuite
from src.clinloop_engine.data_generator import generate_all_scenarios
from src.validation.learned_baselines import event_features, grouped_split, train_and_predict

NOW = datetime(2027, 1, 1)


def sample(pid='synthetic-P'):
    return {'patient_id': pid, 'scenario_id': 'synthetic-S', 'ground_truth_status': 'open',
            'scenario_name': 'LABEL_HINT_SENTINEL', 'missing_followup': 'LABEL_HINT_SENTINEL',
            'events': [{'patient_id': pid, 'event_id': 'IDENTIFIER_SENTINEL', 'event_type': 'lab_result',
                        'timestamp': '2026-05-01T09:00:00', 'status': 'completed',
                        'details': {'condition': 'elevated_psa', 'flag': 'HIGH',
                                    'note': 'REPORT_TEXT_SENTINEL', 'outcome': 'LABEL_HINT_SENTINEL'}}]}


def test_reference_labels_identifiers_and_outcome_annotations_are_not_predictors():
    original = sample()
    expected = event_features(original, NOW)
    changed = copy.deepcopy(original)
    changed.update(ground_truth_status='closed', ground_truth_severity='critical',
                   clinical_narrative='NEW_LABEL_HINT', patient_id='DIFFERENT_IDENTIFIER')
    changed['events'][0].update(patient_id=changed['patient_id'], event_id='NEW_EVENT_IDENTIFIER')
    changed['events'][0]['details'].update(outcome='completed', note='NEW_REPORT_TEXT', status='completed_late')
    assert event_features(changed, NOW) == expected
    assert 'SENTINEL' not in json.dumps(expected)
    assert 'events.total' in expected


def test_future_information_is_excluded_from_temporal_features():
    scenario = sample()
    baseline = event_features(scenario, NOW)
    future = copy.deepcopy(scenario['events'][0])
    future.update(event_type='specialist_referral', timestamp='2027-02-01T09:00:00')
    scenario['events'].append(future)
    assert event_features(scenario, NOW) == baseline
    future['timestamp'] = '2026-05-10T09:00:00'
    observed = event_features(scenario, NOW)
    assert observed['transition.lab_result>specialist_referral.count'] == 1
    assert observed['transition.lab_result>specialist_referral.mean_gap_days'] == 9


def test_mixed_patients_or_invalid_dates_fail_without_echoing_values():
    scenario = sample()
    scenario['events'][0]['patient_id'] = 'SENSITIVE_SENTINEL'
    with pytest.raises(ValueError) as exc:
        event_features(scenario, NOW)
    assert 'SENSITIVE' not in str(exc.value)
    scenario = sample()
    scenario['events'][0]['timestamp'] = 'SENSITIVE_DATE_SENTINEL'
    with pytest.raises(ValueError) as exc:
        event_features(scenario, NOW)
    assert 'SENSITIVE' not in str(exc.value)


def test_patient_and_duplicate_groups_are_transitive_and_disjoint():
    rows = [{'patient_id': p} for p in ['A', 'A', 'B', 'C', 'D', 'E', 'F', 'G']]
    features = [{'x': x} for x in [1, 2, 2, 3, 4, 5, 6, 7]]
    train, test, metadata = grouped_split(rows, features)
    assert not ({rows[i]['patient_id'] for i in train} & {rows[i]['patient_id'] for i in test})
    assert not ({json.dumps(features[i]) for i in train} & {json.dumps(features[i]) for i in test})
    # A's two visits connect B through their duplicate representation.
    assert ({0, 1, 2} <= set(train)) or ({0, 1, 2} <= set(test))
    assert metadata['patient_overlap'] == metadata['exact_predictor_overlap'] == 0
    again = grouped_split(rows, features)
    assert train.tolist() == again[0].tolist() and test.tolist() == again[1].tolist()


def test_missing_groups_and_unsplittable_duplicates_are_rejected():
    with pytest.raises(ValueError):
        grouped_split([{'patient_id': ''}] * 4, [{'x': i} for i in range(4)])
    with pytest.raises(ValueError):
        grouped_split([{'patient_id': str(i)} for i in range(4)], [{'same': 1}] * 4)


def test_preprocessing_fits_training_only_and_neural_model_really_trains():
    features = [{'signal': float(i % 2)} for i in range(24)]
    labels = [bool(i % 2) for i in range(24)]
    test = [{'signal': 0.0, 'HELDOUT_ONLY_FEATURE': 1000.0}, {'signal': 1.0}]
    result = train_and_predict(features, labels, test)
    assert set(result) == {'Logistic regression', 'Gradient-boosted trees', 'Neural network (32,16)'}
    for entry in result.values():
        assert entry['training_only_feature_count'] == 1
        assert entry['iterations'] > 0
        assert entry['can_modify_clinical_state'] is False
        assert len(entry['scores']) == 2 and all(0 <= x <= 1 for x in entry['scores'])
    with pytest.raises(ValueError):
        train_and_predict(features, [True] * len(features), test)


def test_measured_benchmark_excludes_reference_label_simulators():
    scenarios = generate_all_scenarios(90)
    suite = BenchmarkSuite(scenarios, evaluation_time=NOW.replace(tzinfo=timezone.utc))
    original = suite.clinloop.process_batch
    seen = []

    def observed_only(views):
        seen.extend(views)
        assert all(set(v) == {'scenario_id', 'patient_id', 'events'} for v in views)
        return original(views)

    with mock.patch.object(suite.clinloop, 'process_batch', side_effect=observed_only):
        result = suite.run()
    assert seen and len(seen) == result['n_samples']
    assert result['cohort_samples'] == 90
    assert 'LLM Baseline' not in result['overall'] and 'EMR Baseline' not in result['overall']
    assert result['clinical_accuracy_established'] is False
    assert result['preprocessing_fit'] == 'training partition only'
    assert result['split']['patient_overlap'] == result['split']['exact_predictor_overlap'] == 0
    assert 'LLMBaseline' in result['excluded_comparators']
    assert result['model_artifacts_saved'] is False and result['clinical_state_modified'] is False
    json.dumps(result, allow_nan=False)
