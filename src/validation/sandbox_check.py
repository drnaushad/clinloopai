"""Bounded HAPI sandbox proof with only the repository's synthetic fixture.

An explicit --seed-synthetic uploads one isolated transaction of 20 fake
resources under a fresh namespace, then reads only that seven-patient cohort.
It never merges results into the running app's database or reads a global feed.
"""
import argparse
import copy
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Set

import requests
from ..clinloop_engine.fhir_sync import FHIRClient, FHIRSyncError, check_connection, sync_once
from ..clinloop_engine.fhir_ingest import _patient_id
from ..clinloop_engine.loop_store import LoopStore

BASE='https://hapi.fhir.org/baseR4'


def synthetic_transaction(bundle: Dict, namespace: str) -> Dict:
    resources=[copy.deepcopy(e['resource']) for e in bundle['entry']]
    mapping={r['resourceType']+'/'+r['id']:r['resourceType']+'/'+namespace+'-'+r['id'] for r in resources}
    def rewrite(node):
        if isinstance(node,dict):
            if node.get('reference') in mapping:
                node['reference']=mapping[node['reference']]
            elif 'reference' in node:
                # Do not link a fake clinician/reference to another user's public record.
                node.pop('reference')
                node['display']='Synthetic external reference; not linked'
            for value in node.values():rewrite(value)
        elif isinstance(node,list):
            for value in node:rewrite(value)
    entries=[]
    for r in resources:
        original=r['resourceType']+'/'+r['id']
        rewrite(r);r['id']=mapping[original].split('/')[1]
        r.setdefault('meta',{}).setdefault('tag',[]).append({'system':'https://clinloopai.app/sandbox','code':'synthetic-only'})
        entries.append({'resource':r,'request':{'method':'PUT','url':mapping[original],'ifNoneMatch':'*'}})
    return {'resourceType':'Bundle','type':'transaction','entry':entries}


class CohortClient(FHIRClient):
    def __init__(self, patients: Set[str]):
        super().__init__(BASE,timeout=20)
        self.patients=patients
        self.reads=0
        self.resources=0

    def _get(self,url):
        if urlparse(url).netloc != urlparse(BASE).netloc or not url.startswith(BASE):
            raise FHIRSyncError('Sandbox request left the fixed base')
        self.reads+=1
        if self.reads>120:raise FHIRSyncError('Sandbox request budget exhausted')
        return super()._get(url)

    def changed_patients(self,since):
        return self.patients,None

    def patient_history(self,patient_id):
        if patient_id not in self.patients:raise FHIRSyncError('Patient outside synthetic cohort')
        records=super().patient_history(patient_id)
        for r in records:
            pid=r.get('id') if r['resourceType']=='Patient' else _patient_id(r)
            if pid!=patient_id:raise FHIRSyncError('Server did not respect the patient filter')
        self.resources+=len(records)
        return records


def run(seed: bool=False) -> Dict:
    logging.disable(logging.CRITICAL)
    if not seed:
        report=check_connection(FHIRClient(BASE,timeout=15))
        return {'scope':'readable resource types; no ingestion proof','ok':report['ok'],
                'fhir_version':report['fhir_version'],
                'readable_types':sum(v.get('readable',False) for v in report['types'].values())}
    root=Path(__file__).resolve().parents[2]
    fixture=json.loads((root/'data/fhir_example_bundle.json').read_text())
    transaction=synthetic_transaction(fixture,'clinloop-'+uuid.uuid4().hex[:12])
    response=requests.post(BASE,json=transaction,headers={'Content-Type':'application/fhir+json','Accept':'application/fhir+json'},timeout=60,allow_redirects=False)
    response.raise_for_status();body=response.json()
    if body.get('type')!='transaction-response' or len(body.get('entry',[]))!=len(transaction['entry']):
        raise ValueError('Synthetic transaction was not acknowledged')
    if any(not str(e.get('response',{}).get('status','')).startswith('201') for e in body['entry']):
        raise ValueError('Synthetic transaction did not create exclusively new resources')
    patients={e['resource']['id'] for e in transaction['entry'] if e['resource']['resourceType']=='Patient'}
    client=CohortClient(patients)
    os.environ['CLINLOOP_SECOND_READER']='off'
    os.environ['CLINLOOP_ENFORCE_SIGNOFF']='0'
    result=sync_once(LoopStore(':memory:'),client,source='isolated-hapi-synthetic-check',now=datetime(2026,9,1))
    success=bool(result.get('ok') and result.get('patients')==len(patients) and result.get('events',0)>0 and client.resources>=len(transaction['entry']))
    return {'scope':'isolated synthetic transaction and bounded cohort read through detection pipeline',
            'ok':success,'created_resources':len(transaction['entry']),'patients':result.get('patients',0),
            'resources_read':client.resources,'events':result.get('events',0),'warnings':result.get('warnings',0),
            'http_reads':client.reads,'loops':result.get('loops',{}),'clinical_accuracy':'not measured'}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed-synthetic',action='store_true');args=p.parse_args()
    try:
        result=run(args.seed_synthetic)
    except Exception:
        result={'ok':False,'reason':'Sandbox check failed; no success or accuracy claim'}
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
