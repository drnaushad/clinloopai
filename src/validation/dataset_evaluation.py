"""Local, blinded report pilot: prepare-openi, predict, and score after adjudication.

Report-level triage comparison only, not entity extraction or longitudinal care
completion. Real records and predictions belong outside the repository. No HTTP
service or public demo route is used. Console output contains counts only.
"""
import argparse
import csv
import hashlib
import json
import logging
import os
import random
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .report_validation import _parse_rules, predict_details

MODELS = ('medgemma:27b', 'medgemma:4b', 'exaone3.5:7.8b')
FIELDS = ['report_id', 'study', 'conclusion', 'report_date', 'age', 'sex', 'smoking', 'cancer',
          'label_status', 'expected_rules', 'min_deadline_days', 'max_deadline_days',
          'reviewer_id', 'reviewer_role', 'notes']
REPORT_RULES = {'R003', 'R009', 'R018', 'R019', 'R020', 'R030', 'R031', 'R032', 'R033', 'R034', 'R035',
                'R036', 'R037', 'R038', 'R039', 'R040', 'R041', 'R042', 'R043', 'R044', 'R045', 'R046'}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def private_json(path: Path, value) -> None:
    with path.open('w') as f:
        os.chmod(path, 0o600)
        json.dump(value, f, ensure_ascii=False, indent=2)


def write_sheet(path: Path, records: List[Dict]) -> None:
    with path.open('w', newline='') as f:
        os.chmod(path, 0o600)
        writer = csv.DictWriter(f, FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)


def prepare_openi(root: Path, out: Path, sample: int = 100, seed: int = 42) -> Dict:
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output exists; choose a new private study directory')
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    records, seen, counts, corpus = [], set(), Counter(), hashlib.sha256()
    for path in sorted(root.rglob('*.xml')):
        counts['source_files'] += 1
        raw = path.read_bytes()
        corpus.update(hashlib.sha256(raw).digest())
        try:
            tree = ET.fromstring(raw)
        except ET.ParseError:
            counts['malformed_files'] += 1
            continue
        sections = []
        for section in tree.iter('AbstractText'):
            label = (section.get('Label') or '').upper()
            if label in {'FINDINGS', 'IMPRESSION'}:
                text = ''.join(section.itertext()).strip()
                if text:
                    sections.append(label + ': ' + text)
        text = '\n'.join(sections)
        if not text:
            counts['empty_reports'] += 1
            continue
        counts['nonempty_reports'] += 1
        report_hash = digest(' '.join(text.lower().split()))
        if report_hash in seen:
            counts['exact_duplicate_reports'] += 1
            continue
        seen.add(report_hash)
        records.append({'report_id': 'OI-' + report_hash[:20], 'report_hash': report_hash,
                        'source_file': path.name, 'study': 'Chest radiograph', 'conclusion': text,
                        # No dates, demographics, patient identity or outcomes are invented.
                        'report_date': '', 'age': '', 'sex': '', 'smoking': '', 'cancer': '',
                        'patient_group': None})
    if sample <= 0 or sample > len(records):
        raise ValueError('Requested sample must fit the eligible distinct report pool')
    chosen = random.Random(seed).sample(records, sample)
    private_json(out / 'records.json', chosen)
    # Separate blank copies. None of these sheets contains predictions or AI review labels.
    for name in ('reviewer_1.csv', 'reviewer_2.csv', 'adjudication.csv'):
        write_sheet(out / name, chosen)
    manifest = {'dataset': 'IU OpenI', 'source': 'https://openi.nlm.nih.gov/faq',
                'corpus_sha256': corpus.hexdigest(), 'records_sha256': digest((out/'records.json').read_text()),
                'seed': seed, 'sample': sample, 'counts': dict(counts), 'distinct_reports': len(records),
                'sampling_unit': 'report', 'patient_independence_established': False,
                'previous_rule_development_exposure': True,
                'purpose': 'Exploratory pilot; not an untouched external test set',
                'labels': 'pending two independent clinician reviews; existing AI labels are not gold',
                'timing_scope': 'relative deadlines only; actual dates and follow-up outcomes unavailable',
                'accuracy': 'not measured'}
    private_json(out/'manifest.json', manifest)
    return manifest


def predict_study(out: Path, selected: List[str]) -> Dict:
    from ..clinloop_engine import local_llm_engine as engine
    from ..clinloop_engine.second_reader import PROMPT, SYSTEM_PROMPT, read_report
    # A credentialed report must never be sent through the public tunnel or a cloud model.
    if urlparse(engine.OLLAMA_BASE_URL).hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('This runner requires Ollama on loopback on the approved local machine')
    if any(model not in MODELS for model in selected) or len(set(selected)) != len(selected):
        raise ValueError('Choose distinct supported study models')
    records = json.loads((out/'records.json').read_text())
    manifest = json.loads((out/'manifest.json').read_text())
    if digest((out/'records.json').read_text()) != manifest['records_sha256']:
        raise ValueError('Study input has changed')
    with engine.requests.get(engine.OLLAMA_BASE_URL+'/api/tags', timeout=10) as response:
        response.raise_for_status()
        available = {m['name']: m for m in response.json()['models']}
    if any(name not in available for name in selected):
        raise ValueError('A requested study model is not installed; no fallback is allowed')
    # Freeze inputs, executable decision code and prompt; model digest prevents silent replacement.
    source = Path(__file__).resolve().parents[1]/'clinloop_engine'
    fingerprint = digest(''.join(str(p.relative_to(source))+digest(p.read_text()) for p in sorted(source.rglob('*.py'))) + digest(Path(__file__).read_text()) + digest(Path(__file__).with_name('report_validation.py').read_text()))
    frozen = {'records_sha256': manifest['records_sha256'], 'source_sha256': fingerprint,
              'prompt_sha256': digest(SYSTEM_PROMPT+PROMPT),
              'models': {m: available[m]['digest'] for m in selected}}
    provenance = out/'prediction_provenance.json'
    if provenance.exists() and json.loads(provenance.read_text()) != frozen:
        raise ValueError('Code, prompt or model changed; use a new study output directory')
    private_json(provenance, frozen)
    path = out/'predictions.jsonl'
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            done.add((row['report_id'], row['system']))
    with path.open('a') as output:
        os.chmod(path, 0o600)
        for system in ['rules']+selected:
            completed, failed = 0, 0
            for record in records:
                key = record['report_id'], system
                if key in done:
                    continue
                result = {'report_id': record['report_id'], 'system': system}
                start = time.monotonic()
                try:
                    if system == 'rules':
                        prediction = predict_details(record)
                        rules = prediction['rules'] & REPORT_RULES
                        result.update(available=True, action=bool(rules), rules=sorted(rules),
                                      deadline_days={k:v for k,v in prediction['deadline_days'].items() if k in rules})
                    else:
                        model_text = 'Study: ' + record['study'] + '\n' + record['conclusion']
                        if len(model_text) > 6000:
                            raise ValueError('Input would be truncated')
                        def model(prompt, instruction, name=system):
                            return engine.generate_clinical_text(prompt, model=name, temperature=0.0,
                                                                 max_tokens=600, system_prompt=instruction)
                        prediction = read_report(model_text, model)
                        result.update(available=prediction['available'],
                                      action=bool(prediction['items']) if prediction['available'] else None,
                                      items=prediction['items'], dropped=prediction.get('dropped', 0))
                except Exception:
                    # No exception text, source identifier, patient values or report text in logs.
                    result.update(available=False, action=None, failure='processing_failed')
                result['seconds'] = round(time.monotonic()-start, 3)
                failed += not result['available']
                completed += 1
                output.write(json.dumps(result, ensure_ascii=False)+'\n')
                output.flush()
                if completed % 10 == 0:
                    print(json.dumps({'system': system, 'completed': completed, 'unavailable': failed}), flush=True)
            print(json.dumps({'system': system, 'new_completed': completed, 'unavailable': failed}), flush=True)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    summary = {'records': len(records), 'accuracy': 'NOT MEASURED: clinician reference labels pending',
               'processing': {s: {'records': sum(r['system']==s for r in rows),
                                  'available': sum(r['system']==s and r['available'] for r in rows),
                                  'flagged': sum(r['system']==s and r.get('action') is True for r in rows)}
                              for s in ['rules']+selected}}
    private_json(out/'processing_summary.json', summary)
    return summary


def read_sheet(path: Path) -> Dict:
    with path.open(newline='') as f:
        rows = list(csv.DictReader(f))
    if len({r['report_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate review keys')
    return {r['report_id']: r for r in rows}


def completed_reference(row: Dict) -> Optional[Dict]:
    if str(row.get('label_status', '')).strip().lower() != 'complete':
        return None
    if not row.get('reviewer_id') or row.get('reviewer_role', '').strip().lower() != 'clinician':
        raise ValueError('Completed references require a declared clinician reviewer')
    if not row.get('expected_rules', '').strip():
        raise ValueError('Explicit rule IDs or NONE required')
    rules = _parse_rules(row['expected_rules'])
    if rules - REPORT_RULES:
        raise ValueError('Reference contains rules outside this report-level task')
    low, high = row.get('min_deadline_days', ''), row.get('max_deadline_days', '')
    if bool(low) != bool(high):
        raise ValueError('Both deadline bounds are required')
    bounds = (float(low), float(high)) if low else None
    if bounds and not 0 <= bounds[0] <= bounds[1]:
        raise ValueError('Invalid deadline interval')
    return {'rules': rules, 'bounds': bounds, 'reviewer': row['reviewer_id']}


def metrics(pairs: List) -> Dict:
    c = Counter()
    for expected, predicted in pairs:
        c['tp' if expected and predicted else 'fn' if expected else 'fp' if predicted else 'tn'] += 1
    def ratio(a, b):
        return a/b if b else None
    return {**{k:c[k] for k in ('tp','fp','fn','tn')},
            'precision': ratio(c['tp'],c['tp']+c['fp']), 'recall': ratio(c['tp'],c['tp']+c['fn']),
            'f1': ratio(2*c['tp'],2*c['tp']+c['fp']+c['fn']),
            'false_alerts_per_100_reports': ratio(100*c['fp'],len(pairs)),
            'missed_positive_reports': c['fn']}


def score_study(out: Path) -> Dict:
    records = json.loads((out/'records.json').read_text())
    manifest = json.loads((out/'manifest.json').read_text())
    if digest((out/'records.json').read_text()) != manifest['records_sha256']:
        raise ValueError('Study input has changed')
    sheets = [read_sheet(out/name) for name in ('reviewer_1.csv','reviewer_2.csv','adjudication.csv')]
    if any(set(sheet) != {r['report_id'] for r in records} for sheet in sheets):
        raise ValueError('Review sheets do not match the sampled records')
    refs, unresolved = {}, 0
    for record in records:
        rid = record['report_id']
        a, b, adjudication = [completed_reference(sheet.get(rid, {})) for sheet in sheets]
        if a is None or b is None:
            unresolved += 1
            continue
        if a['reviewer'] == b['reviewer']:
            raise ValueError('Two independent reviewer identities required')
        if a['rules'] == b['rules'] and a['bounds'] == b['bounds']:
            refs[rid] = a
        elif adjudication is not None and adjudication['reviewer'] not in {a['reviewer'],b['reviewer']}:
            refs[rid] = adjudication
        else:
            unresolved += 1
    if unresolved:
        raise ValueError('Reference review incomplete: accuracy is not computed')
    predictions = {}
    for line in (out/'predictions.jsonl').read_text().splitlines():
        r = json.loads(line); key = (r['report_id'],r['system'])
        if key in predictions:
            raise ValueError('Duplicate predictions')
        predictions[key] = r
    provenance = json.loads((out/'prediction_provenance.json').read_text())
    systems = ['rules'] + list(provenance['models'])
    if any(s not in systems for _, s in predictions):
        raise ValueError('Unexpected prediction system')
    results = {}
    for name in systems + ['rules+'+m for m in systems if m != 'rules']:
        pairs, missing = [], 0
        for rid, ref in refs.items():
            if name.startswith('rules+'):
                parts = [predictions.get((rid,'rules'),{}), predictions.get((rid,name[6:]),{})]
                valid = any(p.get('available') and p.get('action') for p in parts) or all(p.get('available') for p in parts)
                action = any(p.get('available') and p.get('action') for p in parts)
            else:
                p = predictions.get((rid,name),{}); valid = p.get('available'); action = p.get('action')
            if not valid:
                missing += 1
                continue
            pairs.append((bool(ref['rules']), bool(action)))
        results[name] = {**metrics(pairs), 'eligible':len(refs), 'scored':len(pairs), 'unavailable':missing,
                         'coverage':len(pairs)/len(refs) if refs else None,
                         'recall_including_abstention_as_miss': sum(e and p for e,p in pairs)/sum(bool(r['rules']) for r in refs.values()) if any(r['rules'] for r in refs.values()) else None}
    deadlines = []
    for rid, ref in refs.items():
        if len(ref['rules']) == 1 and ref['bounds']:
            p = predictions.get((rid,'rules'),{}); value = p.get('deadline_days',{}).get(next(iter(ref['rules'])))
            deadlines.append(value is not None and ref['bounds'][0] <= value <= ref['bounds'][1])
    result = {'task':'report-level need for any in-scope follow-up; not finding-level or outcome accuracy',
              'reference':'two declared clinician reviewers, third-person adjudication of disagreements',
              'systems':results, 'rules_deadline_accuracy':sum(deadlines)/len(deadlines) if deadlines else None,
              'deadline_eligible_single_rule_reports':len(deadlines),
              'model_deadline_accuracy':'not scored: existing model output contains no structured deadlines',
              'confidence_intervals':'not computed: patient independence not established',
              'patient_independent_external_validation':False}
    private_json(out/'accuracy.json', result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd',required=True)
    p = sub.add_parser('prepare-openi');p.add_argument('--xml',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--sample',type=int,default=100)
    p.add_argument('--seed',type=int,default=42)
    p = sub.add_parser('predict');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--models',nargs='+',default=list(MODELS))
    p = sub.add_parser('score');p.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        if args.cmd == 'prepare-openi':
            result = prepare_openi(args.xml,args.out,args.sample,args.seed)
            print(json.dumps({k:result[k] for k in ('sample','counts','distinct_reports','accuracy')}))
        elif args.cmd == 'predict':
            print(json.dumps(predict_study(args.out,args.models)))
        else:
            result = score_study(args.out)
            print(json.dumps({'reference_complete':True,'systems':len(result['systems'])}))
    except Exception:
        print(json.dumps({'status':'blocked','reason':'Check local inputs, model availability, or completed reference reviews. No accuracy claim.'}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
