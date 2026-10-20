"""Publish allowlisted aggregate evidence only; never copy records or reviewer sheets."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def count(value) -> int:
    if type(value) is not int or value < 0:
        raise ValueError('Aggregate count must be a nonnegative integer')
    return value


def report_check(source: dict, full_openi: dict, inventory: dict) -> dict:
    """Accept counts only, excluding all report text and case-level disagreement data."""
    fields = ['reports', 'exact_matches', 'true_positive_obligations',
              'false_positive_obligations', 'false_negative_obligations',
              'negative_reports', 'true_negative_reports', 'deadline_eligible_reports',
              'deadlines_within_strict_reference_window', 'exact_mismatches',
              'mismatches_with_harness_group_equivalence']
    p = full_openi['processing']['rules']
    return {
        'synthetic_rules': {k: count(source['counts'][k]) for k in fields},
        'scope': 'Previously used synthetic fixtures; rules engine only; not LLM or clinical accuracy',
        'deadline_scope': 'Strict reference bounds, only reports with an exact matching rule; missed obligations excluded',
        'openi_all_distinct': {k: count(p[k]) for k in ['records', 'available', 'flagged']},
        'folders_checked': count(inventory['folders_checked']),
        'reference_reviews_complete': sum(count(v['completed_labels']) for k,v in source['reference_review_counts'].items() if k in ['reviewer_1.csv','reviewer_2.csv']),
        'clinical_accuracy': 'not established; independent clinician labels and approved external test data required',
    }


def build(synthea: dict, openi: dict, hapi: dict, smart: dict, epic: dict, audit: dict, mimic: dict = None) -> dict:
    rows=[]
    for name in ['rules','medgemma:27b','medgemma:4b','exaone3.5:7.8b']:
        p=openi['processing'][name]
        rows.append({'system':name,'processed':count(p['records']),
                     'usable':count(p['available']),'flagged':count(p['flagged'])})
    return {
        'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'clinical_accuracy':'not established; clinician reference reviews pending',
        'hapi':{'round_trip_passed':hapi.get('ok') is True,'synthetic_patients':count(hapi.get('patients',0)),
                'resources_read':count(hapi.get('resources_read',0)),'events':count(hapi.get('events',0))},
        'smart':{'authentication_and_search_passed':smart.get('ok') is True,
                 'readable_resource_types':count(smart.get('readable_types',0))},
        'epic':{'authentication_and_capability_passed':epic.get('authentication_ok') is True,
                'bulk_export_passed':epic.get('ok') is True and epic.get('patients',0)>0 and epic.get('events',0)>0,
                'patients_processed':count(epic.get('patients',0)),'events':count(epic.get('events',0))},
        'synthea':{'patients':count(synthea['patients']),'resources':count(synthea['resources']),
                   'events':count(synthea['events']),'mapping_warnings':count(synthea['mapping_warnings']),
                   'warnings_audited':count(audit.get('total_warnings',0)),
                   'warnings_missing_lab_metadata':count(audit.get('warning_categories',{}).get('lab_metadata_missing',0))},
        'openi':{'sample':count(openi['records']),'systems':rows,'reference_status':'two independent clinician reviews required',
                 'scope':'Exploratory report-text pilot; previously used for development; patient independence not established'},
        'mimic_demo':{'patients':count((mimic or {}).get('patients',0)),
                      'review_cases':count((mimic or {}).get('review_cases',0)),
                      'reference_status':'independent clinician reviews pending'},
        'credentialed_data':'Only the open 100-patient MIMIC-IV demo was found in the checked data folders; full MIMIC, RadGraph and n2c2 access not confirmed',
        'public_model_connection':'Eight installed models selectable on synthetic report text; temporary HTTPS tunnel',
        'limitations':['Successful connections and processing do not establish clinical accuracy.',
                       'Synthetic EHRs do not validate real patient outcomes.',
                       'Unusable model answers are abstentions, not normal results.',
                       'Patient-independent expert-labelled testing and longitudinal outcome validation remain pending.']}


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--synthea',type=Path,required=True);p.add_argument('--openi',type=Path,required=True)
    p.add_argument('--hapi',type=Path,required=True);p.add_argument('--smart',type=Path,required=True)
    p.add_argument('--epic',type=Path,required=True);p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--mimic-patients-file',type=Path)
    p.add_argument('--mimic-review-sheet',type=Path)
    p.add_argument('--report-audit',type=Path)
    p.add_argument('--full-openi',type=Path)
    p.add_argument('--inventory',type=Path)
    p.add_argument('--out',type=Path,default=Path('data/validation_status.json'))
    args=p.parse_args()
    load=lambda path:json.loads(path.read_text())
    mimic={}
    if args.mimic_patients_file:
        with args.mimic_patients_file.open() as f:mimic['patients']=sum(1 for line in f if line.strip())
    if args.mimic_review_sheet:
        with args.mimic_review_sheet.open() as f:mimic['review_cases']=sum(1 for _ in csv.DictReader(f))
    result=build(*(load(getattr(args,k)) for k in ['synthea','openi','hapi','smart','epic','audit']),mimic=mimic)
    extras = [args.report_audit, args.full_openi, args.inventory]
    if any(extras):
        if not all(extras):
            p.error('--report-audit, --full-openi and --inventory must be supplied together')
        result['report_accuracy_check'] = report_check(*(load(path) for path in extras))
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print('Aggregate validation status written; no patient records included.')


if __name__=='__main__':main()
