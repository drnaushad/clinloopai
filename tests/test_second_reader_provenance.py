"""Synthetic checkpoint-change regression checks; never call a real model."""
import copy
import json
from unittest import mock

from test_second_reader import NOW, PATIENT, UNUSUAL, FakeModel, report
from src.clinloop_engine import second_reader as sr, model_registry as registry
from src.clinloop_engine.loop_store import LoopStore


def run(store, model, resource=None):
    return sr.second_read_patient(store, 'P', [PATIENT, resource or report(UNUSUAL)],
                                  model=model, now=NOW, silent=True)


def test_same_name_new_weights_cannot_reuse_prior_read():
    store, model = LoopStore(), FakeModel([])
    run(store, model)
    first = store.second_read('P|r1')['text_hash']
    model.checkpoint_identity = lambda: {'model': 'fake-7b', 'digest': 'b' * 64}
    run(store, model)
    assert len(model.prompts) == 2
    assert store.second_read('P|r1')['text_hash'] != first
    assert json.loads(store.second_read('P|r1')['detail'])['checkpoint']['digest'] == 'b' * 64


def test_source_date_status_and_identity_context_invalidate_cache():
    for key, value in [('issued', '2026-03-02T08:00:00Z'), ('status', 'amended'),
                       ('code', {'text': 'Corrected synthetic study'})]:
        store, model, original = LoopStore(), FakeModel([]), report(UNUSUAL)
        if key == 'issued':
            original.pop('effectiveDateTime')
            original['issued'] = '2026-03-01T08:00:00Z'
        run(store, model, original)
        updated = copy.deepcopy(original)
        updated[key] = value
        run(store, model, updated)
        assert len(model.prompts) == 2


def test_unknown_checkpoint_is_not_a_reusable_clean_read():
    model = FakeModel([])
    model.checkpoint_identity = None
    store = LoopStore()
    run(store, model)
    run(store, model)
    assert len(model.prompts) == 2
    assert not json.loads(store.second_read('P|r1')['detail'])['cache_reuse_allowed']


def test_metadata_failure_does_not_reuse_cache_or_infer():
    store, model = LoopStore(), FakeModel([])
    run(store, model)
    model.checkpoint_identity = lambda: None
    assert run(store, model) == []
    assert len(model.prompts) == 1


def test_weights_changed_during_generation_discard_the_result():
    model = FakeModel([{'category': 'imaging_followup', 'quote': 'Please obtain a dedicated pelvic MRI'}])
    original = model.__call__
    class Changing:
        checkpoint_identity = model.checkpoint_identity
        def __call__(self, prompt, system):
            result = original(prompt, system)
            self.checkpoint_identity = lambda: {'model': 'fake-7b', 'digest': 'c' * 64}
            return result
    store = LoopStore()
    assert run(store, Changing()) == []
    assert store.second_read('P|r1')['status'] == 'failed'
    assert store.second_reader_suggestion_counts() == {}


def test_returned_model_must_match_the_verified_checkpoint():
    class Wrong(FakeModel):
        def __call__(self, prompt, system):
            result = super().__call__(prompt, system)
            result['model'] = 'unrequested-model'
            return result
    store = LoopStore()
    run(store, Wrong([]))
    assert store.second_read('P|r1')['status'] == 'failed'


def test_fresh_inventory_identity_rejects_missing_duplicate_cloud_or_bad_digest():
    good = {'name': 'synthetic-model', 'digest': 'a' * 64}
    for rows in [[], [good, good], [{**good, 'digest': 'not-a-digest'}],
                 [{**good, 'remote_model': 'cloud-model'}]]:
        with mock.patch('src.clinloop_engine.local_llm_engine._ollama_json', return_value={'models': rows}), \
                mock.patch.object(registry, '_capabilities', return_value=['completion']):
            assert registry.checkpoint_identity('synthetic-model') is None
    with mock.patch('src.clinloop_engine.local_llm_engine._ollama_json', return_value={'models': [good]}), \
            mock.patch.object(registry, '_capabilities', return_value=['completion']):
        assert registry.checkpoint_identity('synthetic-model') == {'model': 'synthetic-model', 'digest': 'a' * 64}
