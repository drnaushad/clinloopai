"""Isolated synthetic API/JWT/race probes. Never contacts an EHR or sends outreach."""
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from unittest.mock import patch

import jwt
import pytest
from tests.test_clinical_api import _h
from tests.test_cds_hooks import _key_pair, EHR, URL
from src.clinloop_engine import clinical_api, cds_hooks
from src.clinloop_engine.api import app
from src.clinloop_engine.loop_store import LoopStore
from fastapi.testclient import TestClient


@pytest.fixture
def api():
    previous = clinical_api.get_store()
    store = LoopStore(); clinical_api.set_store(store)
    with TestClient(app) as client:
        yield client, store
    clinical_api.set_store(previous)
    store._db.close()


@pytest.fixture(scope='module')
def signing():
    return _key_pair()


def token(signing, **claims):
    now = int(time.time())
    lifetime=claims.pop('_lifetime',300)
    return jwt.encode({'iss': EHR, 'aud': URL, 'iat': now, 'exp': now+lifetime,
                       'jti': str(uuid.uuid4()), **claims}, signing[0], algorithm='RS384', headers={'kid': 'ehr-1'})


def call(client, bearer):
    return client.post('/cds-services/clinloop-open-loops',
                       headers={'Authorization': 'Bearer '+bearer},
                       json={'hook':'patient-view','hookInstance':str(uuid.uuid4()),'context':{'patientId':'SYNTHETIC-NONE'}})


@pytest.mark.parametrize('claims', [
    {'exp': str(int(time.time())+300)}, {'iat': str(int(time.time()))},
    {'exp': True}, {'jti': ''}, {'jti': []}, {'jti': {'id':'synthetic'}},
    {'_lifetime':601}, {'iat':int(time.time())-200,'exp':int(time.time())-120},
    {'aud':'https://wrong.example/cds'},
])
def test_malformed_expired_or_wrong_audience_jwt_fails_closed(api, signing, claims):
    with patch.dict('os.environ', {'CLINLOOP_CDS_CLIENTS':json.dumps([{'iss':EHR,'jwks':signing[1]}]),
                                'CLINLOOP_CDS_AUDIENCE':URL}):
        assert call(api[0], token(signing, **claims)).status_code == 401


def test_unsigned_token_cannot_reach_patient_data(api):
    unsigned = jwt.encode({'iss':EHR,'aud':URL,'exp':time.time()+300,'iat':time.time(),'jti':'synthetic'},
                          key='', algorithm='none')
    assert call(api[0], unsigned).status_code == 401


def test_replay_guard_survives_a_separate_store_connection(api, signing, tmp_path):
    # Simulates separate workers/restart sharing the same approved SQLite database.
    path = str(tmp_path/'replay.sqlite')
    first = LoopStore(path); second = LoopStore(path)
    bearer = token(signing)
    with patch.dict('os.environ', {'CLINLOOP_CDS_CLIENTS':json.dumps([{'iss':EHR,'jwks':signing[1]}]),
                                'CLINLOOP_CDS_AUDIENCE':URL}):
        with patch.object(cds_hooks,'get_store',return_value=first):
            assert cds_hooks._check_jwt(bearer,URL) == EHR
        # Erase the old per-process cache as another worker would have none.
        if hasattr(cds_hooks,'_seen_jti'): cds_hooks._seen_jti.clear()
        with patch.object(cds_hooks,'get_store',return_value=second):
            assert cds_hooks._check_jwt(bearer,URL) is None
    first._db.close(); second._db.close()


@pytest.mark.parametrize('role',['viewer','navigator'])
def test_outreach_decision_denied_before_provider_or_database_action(api, role):
    with patch('src.clinloop_engine.outreach.provider_from_env') as provider:
        response=api[0].post('/api/v1/outreach/SYNTHETIC-NOT-A-MESSAGE/decision',json={'approve':True},headers=_h(role))
        assert response.status_code == 403
        provider.assert_not_called()


def ingest(client):
    from pathlib import Path
    bundle=json.loads((Path(__file__).resolve().parents[1]/'data/fhir_example_bundle.json').read_text())
    assert client.post('/api/v1/fhir/ingest?evaluation_time=2026-09-01T00:00:00',json=bundle,headers=_h('admin')).status_code==200


def test_audit_endpoint_detects_out_of_band_tampering(api):
    client, store=api; ingest(client)
    assert client.get('/api/v1/audit/verify',headers=_h('admin')).json()['audit_chain_intact']
    store._db.execute("UPDATE audit_log SET actor='synthetic-tamper' WHERE id=(SELECT MIN(id) FROM audit_log)")
    store._db.commit()
    assert client.get('/api/v1/audit/verify',headers=_h('admin')).json()['audit_chain_intact'] is False


def test_simultaneous_acknowledgements_do_not_overwrite_first_owner(api):
    client, store=api; ingest(client)
    row=client.get('/api/v1/worklist',headers=_h('viewer')).json()['loops'][0]
    path='/api/v1/loops/'+quote(row['loop_key'],safe='')+'/acknowledge'
    barrier=threading.Barrier(2)
    def attempt(role):
        barrier.wait(timeout=5)
        result=client.post(path,headers=_h(role))
        return role,result.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,['navigator','clinician']))
    assert sorted(status for _,status in results)==[200,409]
    winner=next(role for role,status in results if status==200)
    assert store.get(row['loop_key'])['owner']==winner+'.user'
    assert len([a for a in store.audit_trail(row['loop_key']) if a['action']=='acknowledge'])==1
    assert store.verify_audit_chain()


@pytest.mark.parametrize('header',[{'omit_kid':True},{'typ':'at+jwt'},{'kid':''}])
def test_missing_key_identifier_or_wrong_type_rejected(api,signing,header):
    now=int(time.time())
    headers={'kid':'ehr-1',**header}
    if headers.pop('omit_kid',False): headers.pop('kid',None)
    bearer=jwt.encode({'iss':EHR,'aud':URL,'exp':now+300,'iat':now,'jti':str(uuid.uuid4())},
                      signing[0],algorithm='RS384',headers=headers)
    with patch.dict('os.environ',{'CLINLOOP_CDS_CLIENTS':json.dumps([{'iss':EHR,'jwks':signing[1]}]),
                                 'CLINLOOP_CDS_AUDIENCE':URL}):
        assert call(api[0],bearer).status_code==401


def test_replay_storage_failure_blocks_call_without_exposing_error(api,signing):
    with patch.dict('os.environ',{'CLINLOOP_CDS_CLIENTS':json.dumps([{'iss':EHR,'jwks':signing[1]}]),
                                 'CLINLOOP_CDS_AUDIENCE':URL}), \
         patch.object(api[1],'claim_cds_token',side_effect=RuntimeError('SYNTHETIC_PRIVATE')):
        result=call(api[0],token(signing))
        assert result.status_code==401 and 'SYNTHETIC_PRIVATE' not in result.text


def test_same_nonce_from_different_trusted_issuers_is_independent(api,signing):
    other=EHR+'/second'
    nonce='synthetic-shared-nonce'
    with patch.dict('os.environ',{'CLINLOOP_CDS_CLIENTS':json.dumps([
        {'iss':EHR,'jwks':signing[1]},{'iss':other,'jwks':signing[1]}]),'CLINLOOP_CDS_AUDIENCE':URL}):
        assert call(api[0],token(signing,jti=nonce)).status_code==200
        assert call(api[0],token(signing,iss=other,jti=nonce)).status_code==200
        assert call(api[0],token(signing,jti=nonce)).status_code==401


@pytest.mark.parametrize('status',['cancelled','scheduled','no_show','noshow'])
def test_noncompletion_status_never_closes_an_obligation(status):
    from tests.test_loop_store import _events,_ingest
    store=LoopStore();_ingest(store,_events(with_colonoscopy=True,colonoscopy_status=status))
    rows=store.worklist()
    assert len(rows)==1 and rows[0]['rule_id']=='R017'
    assert rows[0]['engine_status']!='closed'


def test_feed_api_reports_silence_and_repeated_failure(api):
    from datetime import timedelta
    from src.clinloop_engine.safety_clock import utc_now
    client,store=api
    store.record_ingest('synthetic','test',ok=True,now=utc_now()-timedelta(hours=49))
    assert client.get('/api/v1/feed/status',headers=_h('viewer')).json()['status']=='STALE'
    for _ in range(3):store.record_ingest('synthetic','test',ok=False,error='Synthetic outage')
    assert client.get('/api/v1/feed/status',headers=_h('viewer')).json()['status']=='FAILING'
    store.check_feed()  # A background watcher may already have emitted the throttled alarm.
    assert any(row['action']=='feed_alarm' for row in store.audit_trail(None))


@pytest.mark.parametrize('value',[float('inf'),float('-inf'),float('nan'),2**4096,{},[]])
def test_nonfinite_or_malformed_numeric_dates_never_produce_server_error(api,signing,value):
    with patch.dict('os.environ',{'CLINLOOP_CDS_CLIENTS':json.dumps([{'iss':EHR,'jwks':signing[1]}]),
                                'CLINLOOP_CDS_AUDIENCE':URL}):
        assert call(api[0],token(signing,exp=value)).status_code==401


def test_replay_claim_is_atomic_across_worker_connections(tmp_path):
    path=str(tmp_path/'shared.sqlite');first=LoopStore(path);second=LoopStore(path)
    barrier=threading.Barrier(2);now=time.time()
    def claim(store):
        barrier.wait(timeout=5)
        return store.claim_cds_token(EHR,'synthetic-nonce',now+300,now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(claim,[first,second]))
    assert sorted(results)==[False,True]
    row=first._db.execute('SELECT digest FROM cds_replay_tokens').fetchone()
    assert 'synthetic-nonce' not in row['digest'] and len(row['digest'])==64
    first._db.close();second._db.close()


def test_acknowledgement_race_across_worker_connections(tmp_path):
    from tests.test_loop_store import _events,_ingest
    from src.clinloop_engine.loop_store import WorkflowError
    path=str(tmp_path/'shared-loops.sqlite')
    first=LoopStore(path);_ingest(first,_events());second=LoopStore(path)
    key=first.worklist()[0]['loop_key'];barrier=threading.Barrier(2)
    def acknowledge(args):
        store,actor=args;barrier.wait(timeout=5)
        try:store.acknowledge(key,actor);return actor,True
        except WorkflowError:return actor,False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(acknowledge,[(first,'synthetic-one'),(second,'synthetic-two')]))
    assert sum(success for _,success in results)==1
    winner=next(actor for actor,success in results if success)
    assert first.get(key)['owner']==winner
    assert first.verify_audit_chain()
    first._db.close();second._db.close()


def test_non_ascii_bearer_input_is_rejected_without_server_error():
    from src.clinloop_engine import auth
    with patch.dict(auth._TOKENS,{'synthetic-test-token-012345':auth.User('synthetic','viewer')},clear=True):
        assert auth.authenticate('synthetic-ö-token') is None
