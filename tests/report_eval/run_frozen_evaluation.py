"""Counts-only rerun of exposed synthetic report/timeline regression fixtures.

--source-root can point at a preserved candidate. No labels are altered; no model,
network, protected records or clinical service is accessed. Output must be new.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location('accuracy_harness', HERE.parents[2]/'src/validation/accuracy_harness.py')
harness = importlib.util.module_from_spec(spec); spec.loader.exec_module(harness)


def source_fingerprint(root):
    return hashlib.sha256(b''.join(str(p.relative_to(root)).encode()+hashlib.sha256(p.read_bytes()).digest()
                                  for p in sorted((root/'src/clinloop_engine').glob('*.py')))).hexdigest()


def run(source_root, reps=500):
    source_root = source_root.resolve()
    initial_source_hash = source_fingerprint(source_root)
    fixture_dir = source_root/'tests/report_eval'
    frozen_bytes = {name: (fixture_dir/name).read_bytes() for name in ('cases.json','timelines.json','run_eval.py','run_timelines.py')}
    sys.path.insert(0, str(source_root))
    sys.path.insert(0, str(source_root/'tests/report_eval'))
    import run_eval as reports
    import run_timelines as timelines
    loaded = [reports, timelines] + [m for n,m in sys.modules.items() if n.startswith('src.clinloop_engine') and getattr(m,'__file__',None)]
    if any(not Path(m.__file__).resolve().is_relative_to(source_root) for m in loaded):
        raise ValueError('Evaluation source was already imported from another checkout; use a fresh interpreter')
    report_cases = json.loads(frozen_bytes['cases.json'])
    timeline_cases = json.loads(frozen_bytes['timelines.json'])
    report_rows, autonomous_rows, timeline_rows, aware_timeline_rows = [], [], [], []
    strict_window_n = strict_window_ok = 0
    failures_by_rule = {}
    for c in report_cases:
        expected = c.get('expected_rules')
        if not isinstance(expected, list) or set(expected)-reports.REPORT_RULES:
            raise ValueError('Unknown/missing reference report rules')
        try:
            pid, date, resources = reports.resources(c)
            events, warnings = reports.bundle_to_events(resources)
            detections = reports.ClinLoopDetector(evaluation_time=date + reports.timedelta(days=1)).process_patient('eval',pid,events.get(pid,[]))
            got = {d.rule_id for d in detections if d.rule_id in reports.REPORT_RULES}
            days = {d.rule_id: round((reports.datetime.fromisoformat(d.deadline)-reports.datetime.fromisoformat(d.trigger_time)).total_seconds()/86400,1)
                    for d in detections if d.rule_id in reports.REPORT_RULES}
            needs_review = any(d.should_abstain or d.loop_status == 'needs_human_review' for d in detections)
            status = 'accepted'
        except Exception:
            got, days, status, needs_review = set(), {}, 'unavailable', False
        if set(got)-reports.REPORT_RULES:
            raise ValueError('Unknown predicted report rules')
        window = c.get('expected_window_days')
        if window and set(expected) & got:
            rule = sorted(set(expected) & got)[0]
            strict_window_n += 1
            strict_window_ok += window[0] <= days.get(rule, -1) <= window[1]
        report_rows.append({'id': c['id'],
                            'report_type': c.get('report_type', 'radiology'), 'language': c.get('language','unspecified'),
                            'expected_rules': expected, 'prediction': {'status': status, 'rules': sorted(got)}})
        autonomous_rows.append({**report_rows[-1], 'prediction': {
            'status': 'review_required' if needs_review else status, 'rules': [] if needs_review else sorted(got)}})
    for c in timeline_cases:
        expected = c.get('expected')
        if not isinstance(expected, dict) or set(expected)-timelines.REPORT_RULES:
            raise ValueError('Unknown/missing timeline reference')
        try:
            pid, first_report, resources = timelines.resources(c)
            events, _ = timelines.bundle_to_events(resources)
            when = timelines.datetime.fromisoformat(c['evaluation_date'][:10]) + timelines.timedelta(hours=23,minutes=59)
            detections = timelines.ClinLoopDetector(evaluation_time=when).process_patient('eval',pid,events.get(pid,[]))
            got, aware_got = {}, {}
            for d in detections:
                if d.rule_id not in timelines.REPORT_RULES or (f'/{first_report}:' not in str(d.trigger_event_id)):
                    continue
                legacy_status = ('done' if d.loop_status == 'closed' else 'done_late' if d.loop_status == 'delayed'
                                 else 'pending' if timelines.datetime.fromisoformat(d.deadline) > when else 'missed')
                got[d.rule_id] = legacy_status
                aware_got[d.rule_id] = 'review_required' if d.should_abstain or d.loop_status == 'needs_human_review' else legacy_status
            status = 'accepted'
        except Exception:
            got, aware_got, status = {}, {}, 'unavailable'
        timeline_rows.append({'id': c['id'],
                              'report_type': 'longitudinal', 'language': c.get('language','unspecified'),
                              'expected_rules': sorted(expected), 'expected_statuses': expected,
                              'prediction': {'status': status, 'rules': sorted(got), 'loop_statuses': got}})
        aware_timeline_rows.append({**timeline_rows[-1], 'prediction': {'status': status, 'rules': sorted(aware_got), 'loop_statuses': aware_got}})
    result = {'source_root': str(source_root), 'data_kind': 'exposed_synthetic_regression',
              'source_commit': subprocess.run(['git','rev-parse','HEAD'],cwd=source_root,capture_output=True,text=True,check=True).stdout.strip(),
              'source_dirty': bool(subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=source_root,capture_output=True,text=True,check=True).stdout.strip()),
              'reference': 'Developer/AI authored, reused for development; not independent clinical truth',
              'fixture_sha256': {name: hashlib.sha256(frozen_bytes[name]).hexdigest() for name in ('cases.json','timelines.json')},
              'inference_runner_sha256': {name: hashlib.sha256(frozen_bytes[name]).hexdigest() for name in ('run_eval.py','run_timelines.py')},
              'scoring_source_sha256': hashlib.sha256(HERE.read_bytes() + (HERE.parents[2]/'src/validation/accuracy_harness.py').read_bytes()).hexdigest(),
              'engine_source_sha256': initial_source_hash,
              'no_patient_data': True, 'no_model_calls': True,
              'historical_triage_scope': 'Report rules count review/abstention alerts as detected obligations. Separate autonomous result conservatively abstains the entire case if any detection requires review.',
              'timeline_scope': 'Historical timelines map nonclosed statuses to pending/missed. Separate timelines_review_aware preserves review_required, including should_abstain outputs.',
              'patient_groups': 'Authentic patient grouping unavailable. Fixture IDs are not substituted for patient identities; patient-cluster confidence intervals withheld.'}
    for label,rows,catalog in [('reports',report_rows,reports.REPORT_RULES),('reports_autonomous',autonomous_rows,reports.REPORT_RULES),('timelines',timeline_rows,timelines.REPORT_RULES),('timelines_review_aware',aware_timeline_rows,timelines.REPORT_RULES)]:
        result[label] = harness.evaluate_cohort(rows,[r['id'] for r in rows],catalog,
                        reference_scope=result['reference'],reps=reps)
    result['reports']['legacy_conditional_deadlines'] = {'within_strict_bounds': strict_window_ok, 'denominator': strict_window_n,
        'scope': 'One lexically first matching rule per report. Excludes missed obligations; preserved only for historical comparison.'}
    result['timelines']['strict_status_agreement'] = sum(x['count'] for x in result['timelines']['metrics']['status_confusion'] if x['expected']==x['predicted'])
    result['timelines']['status_comparisons'] = sum(x['count'] for x in result['timelines']['metrics']['status_confusion'])
    result['timelines']['exact_status_cases'] = sum(r['prediction']['status']=='accepted' and r['expected_statuses']==r['prediction']['loop_statuses'] for r in timeline_rows)
    result['final_engine_source_sha256'] = source_fingerprint(source_root)
    result['fixtures_and_runner_stable'] = all((fixture_dir/name).read_bytes() == raw for name,raw in frozen_bytes.items())
    result['source_snapshot_stable'] = initial_source_hash == result['final_engine_source_sha256'] and result['fixtures_and_runner_stable']
    if not result['source_snapshot_stable']:
        for key in ('reports','reports_autonomous','timelines','timelines_review_aware'):
            result[key] = None
        result['invalidated_reason'] = 'Decision source changed during evaluation; comparison metrics withheld'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reps',type=int,default=500)
    args=p.parse_args(); result=run(args.source_root,args.reps)
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    if not result['source_snapshot_stable']:
        print(json.dumps({'source_snapshot_stable':False,'metrics_withheld':True}));return
    print(json.dumps({'reports':{k:result['reports']['metrics'][k] for k in ('eligible_cases','exact_cases','matched_obligations','extra_obligations','missed_obligations_including_abstention')},
                      'timelines':{k:result['timelines'][k] for k in ('exact_status_cases','strict_status_agreement','status_comparisons')}}))

if __name__=='__main__':main()
