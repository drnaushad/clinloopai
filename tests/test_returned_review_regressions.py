"""Synthetic regressions for returned review findings; no clinical sign-off or model calls."""
import json
from datetime import datetime
from unittest import mock

import pytest

from src.clinloop_engine import clinical_ontology as ontology
from src.clinloop_engine import fhir_ingest as ingest
from src.clinloop_engine import second_reader as reader
from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine.temporal_hypergraph import DynamicTemporalHypergraph
from src.validation import dataset_evaluation as study

NOW = datetime(2026, 6, 15)
PATIENT = {'resourceType': 'Patient', 'id': 'synthetic-P', 'birthDate': '1960-01-01', 'gender': 'male'}


def event(kind='specialist_referral', status='completed', when='2026-05-01T00:00:00', ident='synthetic-e', **details):
    return dict(event_id=ident, patient_id=PATIENT['id'], event_type=kind, status=status,
                timestamp=when, details=details)


def radiology(text, when='2026-07-01T00:00:00Z', title='CT chest', status='final'):
    return {'resourceType': 'DiagnosticReport', 'id': 'synthetic-r', 'status': status,
            'subject': {'reference': 'Patient/'+PATIENT['id']}, 'effectiveDateTime': when,
            'category': [{'coding': [{'code': 'RAD'}]}], 'code': {'text': title}, 'conclusion': text}


def report_rules(resource):
    events, warnings = ingest.bundle_to_events([PATIENT, resource], evaluation_time=datetime(2027, 1, 1))
    rows = ClinLoopDetector(evaluation_time=datetime(2027, 1, 1)).process_patient('synthetic', PATIENT['id'], events[PATIENT['id']])
    return {r.rule_id: r for r in rows}


class FakeModel:
    def __init__(self, items): self.items, self.calls = items, 0
    def __call__(self, prompt, system):
        self.calls += 1
        return {'text': json.dumps({'items': self.items}), 'model': 'synthetic-only'}


@pytest.mark.parametrize('intent', [None, '', 'proposal', 'plan', 'option', 'not-an-intent'])
@pytest.mark.parametrize('status', ['active', 'completed'])
def test_medication_plan_is_not_an_issued_order(intent, status):
    assert ingest._status({'resourceType': 'MedicationRequest', 'intent': intent, 'status': status}) == 'unknown'


@pytest.mark.parametrize('intent', ['order', 'original-order', 'reflex-order', 'filler-order', 'instance-order'])
def test_medication_issued_intents_are_preserved(intent):
    assert ingest._status({'resourceType': 'MedicationRequest', 'intent': intent, 'status': 'active'}) == 'completed'


@pytest.mark.parametrize('status', ['planned', 'in-progress', 'cancelled', 'unknown', 'finished'])
def test_estimated_encounter_end_is_not_discharge(status):
    encounter = {'resourceType': 'Encounter', 'status': status, 'class': {'code': 'IMP'},
                 'period': {'start': '2026-05-01T00:00:00Z', 'end': '2026-05-03T00:00:00Z'}}
    assert bool(ingest._map_encounter(encounter)) == (status == 'finished')


def test_unknown_discharge_does_not_suppress_an_abnormal_lab():
    rows = [event('discharge', 'unknown', when='2026-05-03T00:00:00', arrived_at='2026-05-01T00:00:00'),
            event('lab_result', ident='synthetic-lab', when='2026-05-02T00:00:00', test='potassium', value=6.0, flag='HIGH')]
    ingest._derive_context(rows)
    assert not rows[1]['details'].get('in_stay')


@pytest.mark.parametrize('name', ['Pancreatic FNA', 'EUS-FNA', 'Endoscopic ultrasound biopsy'])
def test_sampling_requests_agree_but_are_not_performed_eus(name):
    row = ingest._map_service_request({'code': {'text': name}, 'status': 'active', 'intent': 'order'})[0]
    assert row[0] == 'biopsy_order'
    assert row[0] != 'endoscopic_ultrasound'


@pytest.mark.parametrize('kind,status,expected', [
    (None, 'final', False), ('lab_result', 'finished', False), ('biopsy_order', 'fulfilled', False),
    ('discharge', 'finished', True), ('referral_visit', 'fulfilled', True),
    ('breast_biopsy', 'final', False), ('imaging_ct', 'final', True),
    ('echocardiogram', 'corrected', True), ('liver_imaging', 'appended', True)])
def test_completion_statuses_are_bound_to_event_kind(kind, status, expected):
    assert ontology.is_fulfilling_status(status, kind) is expected


@pytest.mark.parametrize('pid', ['', ' ', None, 42])
def test_invalid_patient_identity_is_rejected(pid):
    row = event(); row['patient_id'] = pid
    with pytest.raises(ValueError, match='identity'):
        ClinLoopDetector(evaluation_time=NOW).process_patient('synthetic', pid, [row])


@pytest.mark.parametrize('status', ['unknown', 'draft', 'pending', 'planned', 'stopped', 'scheduled'])
def test_unissued_referral_does_not_trigger_a_visit_obligation(status):
    assert ClinLoopDetector(evaluation_time=NOW).process_patient('synthetic', PATIENT['id'], [event(status=status)]) == []


def test_future_trigger_and_future_noncompletion_evidence_are_excluded():
    detector = ClinLoopDetector(evaluation_time=NOW)
    assert detector.process_patient('synthetic', PATIENT['id'], [event(when='2026-07-01T00:00:00')]) == []
    rows = [event(), event('referral_visit', 'cancelled', when='2026-07-01T00:00:00', ident='synthetic-later')]
    result = detector.process_patient('synthetic', PATIENT['id'], rows)[0]
    assert '2026-07-01' not in ' '.join(result.evidence_chain)


@pytest.mark.parametrize('statuses', [('pending', 'completed'), ('completed', 'pending'), ('completed', 'cancelled')])
def test_conflicting_duplicate_followup_does_not_silently_close(statuses):
    rows = [event()] + [event('referral_visit', status, when='2026-05-02T00:00:00', ident='same-source') for status in statuses]
    graph = DynamicTemporalHypergraph(evaluation_time=NOW); graph.build_from_patient_trajectory(rows)
    loop = next(x for x in graph.get_all_loops() if x.obligation_rule.rule_id == 'R008')
    assert loop.status == 'open'
    assert graph.nodes['same-source'].status == 'unknown'
    assert graph.nodes['same-source'].details['duplicate_status_conflict']


def test_abstention_does_not_turn_completed_late_task_into_open_review():
    detector = ClinLoopDetector(evaluation_time=NOW); score = detector.risk_scorer.score
    def uncertain(**kwargs):
        result = score(**kwargs); result.should_abstain = True; return result
    rows = [event(), event('referral_visit', when='2026-06-10T00:00:00', ident='synthetic-followup')]
    with mock.patch.object(detector.risk_scorer, 'score', side_effect=uncertain):
        result = detector.process_patient('synthetic', PATIENT['id'], rows)[0]
    assert result.loop_status == 'delayed'


@pytest.mark.parametrize('rule_id,months', [('R019', 3), ('R034', 6), ('R037', 12), ('R041', 12)])
def test_fallback_deadlines_use_actual_calendar_anchor(rule_id, months):
    from src.clinloop_engine.radiology import _calendar_due
    rule = ontology.get_rule_by_id(rule_id); anchor = datetime(2024, 2, 29)
    assert ontology.get_deadline_days(rule, {}, anchor=anchor) == (_calendar_due(anchor, months)-anchor).total_seconds()/86400
    assert '+grace' not in rule.ltl_formula and '+ grace' not in rule.evidence_note


@pytest.mark.parametrize('text,title,rule_id,days', [
    ('Lung-RADS 3.', 'Screening LDCT', 'R034', 184),
    ('Lung-RADS 4A.', 'Screening LDCT', 'R019', 92),
    ('1.2 cm solid hypoechoic nodule in the left lobe, TI-RADS TR4.', 'US thyroid', 'R032', 365),
    ('Incidental 12 mm solid nodule in the right lower lobe. Recommend CT chest in 3 months.', 'CT chest', 'R003', 92),
    ('Incidental 12 mm solid nodule in the right lower lobe. Recommend CT chest in 12 weeks or biopsy.', 'CT chest', 'R003', 84)])
def test_radiology_calendar_and_alternative_paths(text, title, rule_id, days):
    resource = radiology(text, title=title); rows = report_rules(resource)
    result = rows[rule_id]
    assert (datetime.fromisoformat(result.deadline)-datetime(2026,7,1)).total_seconds()/86400 == days
    if 'or biopsy' in text:
        assert 'R030' not in rows and 'R036' not in rows
        assert 'same three-month' not in ' '.join(result.basis)


@pytest.mark.parametrize('when,text,expected', [
    ('2026-01-31T00:00:00Z','Plan: CT chest in 1 month.',28),
    ('2026-02-01T00:00:00Z','Plan: Repeat potassium in 1 month.',28),
    ('2024-02-29T00:00:00Z','Plan: CT chest in 1 year.',365),
    ('2026-01-31T00:00:00Z','Plan: CT chest in 2-3 months.',89)])
def test_note_months_are_resolved_at_note_date(when, text, expected):
    note={'resourceType':'DocumentReference','status':'current','date':when,'description':'Progress note',
          'content':[{'attachment':{'contentType':'text/plain','data':__import__('base64').b64encode(text.encode()).decode()}}]}
    plans=ingest._map_document_reference(note)
    assert plans and next(iter(plans[0][2]['rule_deadline_days'].values())) == expected


@pytest.mark.parametrize('reverse', [False, True])
def test_source_matching_prefers_affirmed_advice_over_negated_same_category(reverse):
    items=[{'category':'imaging_followup','quote':'pulmonary nodule'},
           {'category':'imaging_followup','quote':'Please obtain a dedicated pelvic MRI'}]
    result=reader.read_report('No pulmonary nodule. Please obtain a dedicated pelvic MRI.',FakeModel(items[::-1] if reverse else items))
    assert len(result['items']) == 1 and 'pelvic MRI' in result['items'][0]['quote']
    assert not result['items'][0]['context_flagged']


def test_appended_reports_are_read_and_ingestion_uses_same_clock():
    model=FakeModel([]); resource=radiology('No acute findings.',when='2026-06-01T00:00:00Z',status='appended')
    with mock.patch.object(ingest,'bundle_to_events',wraps=ingest.bundle_to_events) as mapper:
        reader.second_read_patient(LoopStore(),PATIENT['id'],[PATIENT,resource],model=model,now=NOW,silent=True)
    assert model.calls == 1 and mapper.call_args.kwargs['evaluation_time'] == NOW


def test_checkpoint_change_invalidates_whole_study_not_just_one_item():
    from test_dataset_evaluation import TestDatasetEvaluation
    from src.clinloop_engine import local_llm_engine as engine, model_registry
    fixture=TestDatasetEvaluation(); fixture.setUp()
    try:
        fixture.out.joinpath('accuracy.json').write_text('{}')
        with mock.patch.object(engine,'OLLAMA_BASE_URL','http://127.0.0.1:11434'), \
             mock.patch.object(model_registry,'checkpoint_identity',return_value={'model':'medgemma:27b','digest':'a'*64}), \
             mock.patch.object(study,'_predict_model',side_effect=study.CheckpointProvenanceError('fixture')):
            with pytest.raises(study.CheckpointProvenanceError):study.predict_study(fixture.out,['medgemma:27b'])
        assert (fixture.out/'study_invalidated.json').exists()
        assert not (fixture.out/'accuracy.json').exists() and not (fixture.out/'prediction_provenance.json').exists()
        with pytest.raises(study.CheckpointProvenanceError):study.score_study(fixture.out)
    finally:fixture.doCleanups()


def test_registry_rejects_duplicate_names_and_prompt_identity_is_shared():
    from src.clinloop_engine import model_registry, local_llm_engine
    with mock.patch.object(local_llm_engine,'_ollama_json',return_value={'models':[{'name':'ambiguous'},{'name':'ambiguous'},{'name':'unique'}]}):
        assert set(model_registry._installed('http://127.0.0.1')) == {'unique'}
    assert model_registry.prompt_version() == 'sr-'+reader.prompt_digest()[:12]


def test_synchronous_ml_events_have_no_invented_direction_and_preserve_status():
    from src.validation.learned_baselines import event_features
    rows=[event('diagnosis'),event('lab_result','ordered',ident='synthetic-lab')]
    a=event_features({'patient_id':PATIENT['id'],'events':rows},NOW)
    b=event_features({'patient_id':PATIENT['id'],'events':rows[::-1]},NOW)
    assert a == b and a['status.ordered.count'] == 1
    assert any(key.startswith('cooccurrence.') for key in a)
    assert not any(key.startswith('transition.') for key in a)


def test_large_simultaneous_ml_batch_preserves_multiplicity_without_expanding_pairs():
    from src.validation.learned_baselines import event_features
    rows=[event('diagnosis',ident='synthetic-'+str(i)) for i in range(20000)]
    rows += [event('lab_result',when='2026-05-03',ident='synthetic-followup')]
    features=event_features({'patient_id':PATIENT['id'],'events':rows},NOW)
    assert features['cooccurrence.diagnosis&diagnosis.count'] == 199990000
    assert features['transition.diagnosis>lab_result.count'] == 20000
    assert features['transition.diagnosis>lab_result.mean_gap_days'] == 2


def test_benchmark_reports_autonomous_recall_separately_from_triage():
    from src.clinloop_engine.benchmark import BenchmarkSuite
    from src.clinloop_engine.data_generator import generate_all_scenarios
    suite=BenchmarkSuite(generate_all_scenarios(300)); original=suite.clinloop.process_batch
    def abstain(rows):
        result=original(rows)
        for group in result.values():
            for detection in group:detection.should_abstain=True
        return result
    with mock.patch.object(suite.clinloop,'process_batch',side_effect=abstain), \
         mock.patch('src.clinloop_engine.benchmark.train_and_predict',return_value={}):
        result=suite.run()['overall']['ClinLoop AI']
    assert result['sensitivity_including_abstention_as_miss'] == 0 and result['sensitivity'] > 0


def test_human_followup_labels_cover_both_languages_and_order_scope_is_explicit():
    from src.clinloop_engine import basis
    assert set(basis.FOLLOWUP_NAMES_KO) <= set(basis.FOLLOWUP_NAMES)
    assert basis.FOLLOWUP_NAMES['hbv_dna_test'] == 'HBV DNA test'
    text='same three-month nodule follow-up: earlier report or rule deadline retained'
    assert basis._deadline_note_ko(text) != text


@pytest.mark.parametrize('status,verification', [('cancelled',None),('unknown',None),('completed','provisional'),('completed','unconfirmed')])
def test_unsupported_diagnosis_neither_suppresses_creatinine_nor_adds_af_risk(status, verification):
    from src.clinloop_engine import motifs
    dx=event('diagnosis',status,renal_replacement=True,codes=['I63'],diagnosis='stroke',verification=verification)
    labs=[event('lab_result',when='2026-05-02',ident='creatinine-1',analyte='creatinine',test='Creatinine',value=1.0,unit='mg/dL'),
          event('lab_result',when='2026-05-03',ident='creatinine-2',analyte='creatinine',test='Creatinine',value=2.0,unit='mg/dL')]
    out=[]; motifs.pattern_creatinine([dx]+labs,{},out)
    assert out and out[0]['details']['rule_deadline_days']['R053'] == 3.0
    assert motifs.cha2ds2_vasc([dx],{'birth_date':datetime(1980,1,1),'sex':'male'},NOW)['score'] == 0
    af=event('diagnosis',status,diagnosis='atrial fibrillation',codes=['I48'],verification=verification)
    out=[]; motifs.pattern_af([af],{'birth_date':datetime(1940,1,1),'sex':'male','evaluation_time':NOW},out)
    assert not out


@pytest.mark.parametrize('kind,expected', [('provider_review',True),('referral_visit',False)])
def test_urology_context_must_be_a_relevant_care_event(kind,expected):
    from src.clinloop_engine import motifs
    rows=[event('lab_result',when='2026-01-01',ident='rbc-1',analyte='urine_rbc',value=10,unit='RBC/hpf'),
          event('lab_result',when='2026-02-01',ident='rbc-2',analyte='urine_rbc',value=10,unit='RBC/hpf'),
          event(kind,when='2026-01-15',ident='urology-event',specialty='urology')]
    out=[]; motifs.pattern_haematuria(rows,{'birth_date':datetime(1960,1,1)},out)
    assert bool(out) is expected


@pytest.mark.parametrize('filename',['risk_scorer.py','basis.py'])
def test_shared_decision_code_changes_invalidate_rule_fingerprint(filename):
    from pathlib import Path
    from src.clinloop_engine import governance
    rule=ontology.get_rule_by_id('R017')
    def fingerprint(revision):
        def source_hash(kind,path,loader):
            return revision if Path(path).name == filename else 'unchanged'
        with mock.patch.object(governance,'_cached',side_effect=source_hash):
            return governance.rule_fingerprint(rule)
    assert fingerprint('old') != fingerprint('new')


def test_fhir_sync_ingestion_uses_the_sync_evaluation_clock():
    from test_fhir_sync import TestFHIRSync, NOW as sync_time
    from src.clinloop_engine import fhir_sync
    fixture=TestFHIRSync(); fixture.setUp()
    try:
        with mock.patch.object(fhir_sync,'bundle_to_events',wraps=fhir_sync.bundle_to_events) as mapper:
            assert fhir_sync.sync_once(fixture.store,fixture.client,now=sync_time)['ok']
        assert mapper.call_args_list
        assert all(call.kwargs['evaluation_time'] == sync_time for call in mapper.call_args_list)
    finally:fixture.tearDown()


def test_dashboard_renders_untrusted_steps_as_text():
    import shutil
    import subprocess
    from pathlib import Path
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed for dashboard security regression')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([node,str(root/'tests/returned_review_dom_test.cjs')],cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
