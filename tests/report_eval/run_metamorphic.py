"""Frozen synthetic metamorphic checks of the actual report ingestion/graph pipeline.

Relations check identity/order/time representation, not new medical truth labels.
Source text and existing reference labels are never changed or used as predictions.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

RELATIONS = {
    'resource_order': 'Reverse FHIR resource list order; output obligations/status/relative deadline must be identical.',
    'identity_rename': 'Rename every resource ID and exact resource reference consistently; clinical output must be identical.',
    'equivalent_timezone': 'Represent each explicit timezone-qualified FHIR timestamp at UTC+09:00 preserving its instant; output must be identical.',
    'unrelated_patient': 'Append another synthetic patient with a normal report; original patient output must be identical.'}


def definition():
    return {'schema_version': 1, 'data_kind': 'synthetic_development_metamorphic_challenge',
            'clinical_reference': 'No independent clinical truth; invariant expected outputs frozen before candidate comparison',
            'relations': RELATIONS, 'seed': 42,
            'signature': ['rule_id','loop_status','deadline-minus-trigger seconds','should_abstain'],
            'selection': 'All exposed synthetic report fixtures; no reference label used to determine expected transformed output'}


def run(root):
    root=root.resolve();sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests/report_eval'))
    def fingerprint():
        return hashlib.sha256(b''.join(str(p.relative_to(root)).encode()+hashlib.sha256(p.read_bytes()).digest() for p in sorted((root/'src/clinloop_engine').glob('*.py')))).hexdigest()
    initial_hash = fingerprint()
    fixture_bytes = (root/'tests/report_eval/cases.json').read_bytes()
    import run_eval as engine
    loaded=[engine]+[m for n,m in sys.modules.items() if n.startswith('src.clinloop_engine') and getattr(m,'__file__',None)]
    if any(not Path(m.__file__).resolve().is_relative_to(root) for m in loaded):
        raise ValueError('Metamorphic source was imported from another checkout; use a fresh interpreter')
    cases=json.loads(fixture_bytes)
    def infer(pid,date,resources):
        events,_=engine.bundle_to_events(resources)
        detections=engine.ClinLoopDetector(evaluation_time=date+timedelta(days=1)).process_patient('metamorphic',pid,events.get(pid,[]))
        return sorted((d.rule_id,d.loop_status,
                       (datetime.fromisoformat(d.deadline)-datetime.fromisoformat(d.trigger_time)).total_seconds(),bool(d.should_abstain))
                      for d in detections if d.rule_id in engine.REPORT_RULES)
    def rewrite(value,refs):
        if isinstance(value,dict):return {k:rewrite(v,refs) for k,v in value.items()}
        if isinstance(value,list):return [rewrite(v,refs) for v in value]
        if isinstance(value,str):return refs.get(value,value)
        return value
    def offset(value):
        if isinstance(value,dict):return {k:offset(v) for k,v in value.items()}
        if isinstance(value,list):return [offset(v) for v in value]
        if isinstance(value,str) and 'T' in value:
            try:
                parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
                if parsed.tzinfo:return parsed.astimezone(timezone(timedelta(hours=9))).isoformat()
            except ValueError:pass
        return value
    counts={k:{'attempted':0,'matched':0,'mismatch':0,'unavailable':0} for k in RELATIONS}
    for case in cases:
        pid,date,resources=engine.resources(case)
        try:baseline=infer(pid,date,resources)
        except Exception:
            for row in counts.values():row['unavailable']+=1
            continue
        refs={r['id']:'renamed-'+r['id'] for r in resources}
        refs.update({r['resourceType']+'/'+r['id']:r['resourceType']+'/renamed-'+r['id'] for r in resources})
        unrelated=[{'resourceType':'Patient','id':'SYNTHETIC-OTHER'},
                   {'resourceType':'DiagnosticReport','id':'SYNTHETIC-OTHER-REPORT','status':'final',
                    'subject':{'reference':'Patient/SYNTHETIC-OTHER'},'category':[{'coding':[{'code':'RAD'}]}],
                    'effectiveDateTime':case['date'][:10]+'T09:00:00Z','conclusion':'No acute cardiopulmonary abnormality.'}]
        variants={'resource_order':(pid,list(reversed(resources))),
                  'identity_rename':(refs[pid],rewrite(resources,refs)),
                  'equivalent_timezone':(pid,offset(resources)),
                  'unrelated_patient':(pid,resources+unrelated)}
        for name,(new_pid,variant) in variants.items():
            counts[name]['attempted']+=1
            try:got=infer(new_pid,date,variant)
            except Exception:
                counts[name]['unavailable']+=1
                continue
            counts[name]['matched' if baseline==got else 'mismatch']+=1
    final_hash=fingerprint()
    stable=initial_hash==final_hash and fixture_bytes==(root/'tests/report_eval/cases.json').read_bytes()
    return {**definition(),'definition_sha256':hashlib.sha256(json.dumps(definition(),sort_keys=True).encode()).hexdigest(),
            'source_commit':subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,check=True).stdout.strip(),
            'source_sha256':initial_hash,'final_source_sha256':final_hash,'source_snapshot_stable':stable,
            'fixture_sha256':hashlib.sha256(fixture_bytes).hexdigest(),
            'planned_cases':len(cases),'results':counts if stable else None,'clinical_accuracy_established':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--freeze-definition',action='store_true');a=p.parse_args()
    result=definition() if a.freeze_definition else run(a.source_root)
    with os.fdopen(os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result.get('results',{'definition_frozen':True})))

if __name__=='__main__':main()
