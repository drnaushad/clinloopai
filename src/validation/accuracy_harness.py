"""All-eligible evaluation bookkeeping; never runs models or changes clinical decisions.

Declared reference truth and patient grouping remain external responsibilities. This
module refuses an engine-detected-only frame for estimates of missed obligations.
"""
from collections import Counter, defaultdict
import math
import random

STATUSES = {'accepted', 'review_required', 'unavailable', 'unrun'}
LOOP_STATUSES = {'done', 'done_late', 'pending', 'missed', 'review_required'}


def _ratio(a, b):
    return a / b if b else None


def assert_group_separation(records):
    """Reject declared patient or normalized-text duplicates across partitions."""
    seen = {}
    for r in records:
        partition = r.get('partition')
        if partition not in {'development', 'evaluation'}:
            raise ValueError('Explicit development/evaluation partition required')
        group = r.get('patient_group')
        if not isinstance(group, str) or not group.strip():
            raise ValueError('Declared patient grouping required for partition checks')
        keys = [('patient', group)]
        if r.get('text'):
            keys.append(('text', ' '.join(r['text'].casefold().split())))
        for key in keys:
            if key in seen and seen[key] != partition:
                raise ValueError('Patient or duplicate report crosses study partitions')
            seen[key] = partition


def _counts(rows, rules):
    statuses = Counter(r['prediction']['status'] for r in rows)
    matrix = {truth: {prediction: 0 for prediction in ('positive', 'negative', 'review_required', 'unavailable', 'unrun')}
              for truth in ('positive', 'negative')}
    per_rule = {rule: {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'positive_abstention': 0, 'negative_abstention': 0}
                for rule in sorted(rules)}
    tp = fp = missed = exact = predicted_count = expected_count = false_closure = missed_status = 0
    status_pairs = Counter()
    for row in rows:
        exp = set(row['expected_rules']); p = row['prediction']; accepted = p['status'] == 'accepted'
        got = set(p['rules']) if accepted else set()
        expected_count += len(exp); predicted_count += len(got)
        tp += len(exp & got); fp += len(got - exp); missed += len(exp - got)
        exact += accepted and exp == got
        matrix['positive' if exp else 'negative'][('positive' if got else 'negative') if accepted else p['status']] += 1
        for rule in rules:
            key = ('tp' if rule in got else 'fn') if rule in exp else ('fp' if rule in got else 'tn')
            if accepted:
                per_rule[rule][key] += 1
            else:
                per_rule[rule]['positive_abstention' if rule in exp else 'negative_abstention'] += 1
        for rule in set(row.get('expected_statuses', {})) | set(p.get('loop_statuses', {}) if accepted else {}):
            expected = row.get('expected_statuses', {}).get(rule, 'absent')
            actual = p.get('loop_statuses', {}).get(rule, 'absent') if accepted else p['status']
            status_pairs[(expected, actual)] += 1
            false_closure += expected in {'pending', 'missed', 'review_required'} and actual in {'done', 'done_late'}
            missed_status += expected != 'absent' and actual == 'absent'
    accepted_n = statuses['accepted']
    pos = matrix['positive']; neg = matrix['negative']
    longitudinal = [r for r in rows if 'expected_statuses' in r]
    return {'eligible_cases': len(rows), 'accepted_cases': accepted_n,
            'coverage': _ratio(accepted_n, len(rows)), 'prediction_status_counts': dict(statuses),
            'exact_cases': int(exact), 'exact_rate_all_eligible': _ratio(exact, len(rows)),
            'exact_definition': 'Exact rule-ID sets only; longitudinal statuses have a separate denominator',
            'longitudinal_eligible_cases': len(longitudinal),
            'exact_status_cases': sum(r['prediction']['status']=='accepted' and r['expected_statuses']==r['prediction'].get('loop_statuses',{}) for r in longitudinal) if longitudinal else None,
            'expected_obligations': expected_count, 'predicted_obligations_accepted': predicted_count,
            'matched_obligations': tp, 'extra_obligations': fp, 'missed_obligations_including_abstention': missed,
            'precision_accepted': _ratio(tp, predicted_count), 'recall_all_eligible': _ratio(tp, expected_count),
            'micro_f1_all_eligible': _ratio(2 * tp, expected_count + predicted_count),
            'report_confusion': matrix, 'per_rule': per_rule,
            'report_sensitivity_accepted': _ratio(pos['positive'], pos['positive'] + pos['negative']),
            'report_sensitivity_all_eligible': _ratio(pos['positive'], sum(pos.values())),
            'report_specificity_accepted': _ratio(neg['negative'], neg['positive'] + neg['negative']),
            'false_closures': int(false_closure), 'absent_expected_statuses': missed_status,
            'status_confusion': [{'expected': a, 'predicted': b, 'count': n} for (a,b),n in sorted(status_pairs.items())]}


def clustered_intervals(rows, rules, reps=500, seed=42):
    """Percentile intervals resample whole declared patient clusters, retaining all reports."""
    if type(reps) is not int or reps <= 0 or type(seed) is not int:
        raise ValueError('Positive replicate count and integer seed required')
    groups = defaultdict(list)
    for row in rows:
        group = row.get('patient_group')
        if not isinstance(group, str) or not group.strip():
            return {'available': False, 'reason': 'Declared patient grouping absent; report-independent intervals refused'}
        groups[group].append(row)
    if len(groups) < 2:
        return {'available': False, 'reason': 'At least two declared patient groups required'}
    rng = random.Random(seed); clusters = [groups[k] for k in sorted(groups)]; draws = defaultdict(list)
    for _ in range(reps):
        sample = [r for _ in clusters for r in rng.choice(clusters)]
        result = _counts(sample, rules)
        for key in ('exact_rate_all_eligible', 'precision_accepted', 'recall_all_eligible', 'micro_f1_all_eligible', 'report_sensitivity_all_eligible', 'report_specificity_accepted'):
            if result[key] is not None:
                draws[key].append(result[key])
    intervals = {}
    for key, values in draws.items():
        values.sort(); n = len(values)
        intervals[key] = {'low': values[math.floor(.025 * (n-1))], 'high': values[math.ceil(.975 * (n-1))],
                          'defined_replicates': n, 'undefined_replicates': reps-n}
    return {'available': True, 'method': 'patient-cluster percentile bootstrap of declared groups',
            'patient_groups': len(groups), 'seed': seed, 'replicates': reps, 'ci95': intervals,
            'limit': 'Grouping declarations are not identity verification. Synthetic intervals do not establish clinical generalization.'}


def evaluate_cohort(records, eligible_case_ids, rule_catalog, *, sampling_frame='all_eligible', reference_scope,
                    reps=500, seed=42, development_records=None):
    """Score every externally enumerated eligible case; explicit NONE is an empty list.

    All cases require reference labels and a prediction status. Missing references
    stop scoring; unavailable/unrun/review predictions remain in the denominator.
    Caller must enumerate the cohort before viewing model results.
    """
    if sampling_frame != 'all_eligible':
        raise ValueError('Missed-obligation estimates require an independent all-eligible frame; engine-detected-only frames refused')
    if development_records is not None:
        if any(r.get('partition') != 'evaluation' for r in records) or any(r.get('partition') != 'development' for r in development_records):
            raise ValueError('Declared development and evaluation partition provenance required')
        assert_group_separation(list(records) + list(development_records))
    rules = set(rule_catalog)
    if not rules or not isinstance(reference_scope, str) or not reference_scope.strip():
        raise ValueError('Explicit rule catalog and reference scope required')
    ids = list(eligible_case_ids)
    if not ids or any(not isinstance(i, str) or not i.strip() for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('Nonempty independently enumerated eligible case IDs required')
    if len(records) != len(ids) or {r.get('id') for r in records} != set(ids):
        raise ValueError('Every eligible case must occur exactly once')
    for row in records:
        exp = row.get('expected_rules'); p = row.get('prediction', {})
        if not isinstance(exp, list) or any(not isinstance(x,str) for x in exp) or len(exp) != len(set(exp)) or set(exp) - rules:
            raise ValueError('Complete explicit reference rules required; unknown labels refused')
        if p.get('status') not in STATUSES:
            raise ValueError('Explicit accepted, review_required, unavailable or unrun status required')
        got = p.get('rules')
        if not isinstance(got, list) or any(not isinstance(x,str) for x in got) or len(got) != len(set(got)) or set(got) - rules:
            raise ValueError('Distinct known prediction rule IDs required')
        if p['status'] != 'accepted' and got:
            raise ValueError('Abstentions cannot claim autonomous finding predictions')
        for statuses in (row.get('expected_statuses', {}), p.get('loop_statuses', {})):
            if not isinstance(statuses, dict) or set(statuses) - rules or any(v not in LOOP_STATUSES for v in statuses.values()):
                raise ValueError('Unknown longitudinal rule or status')
        if set(row.get('expected_statuses', {})) - set(exp) or set(p.get('loop_statuses', {})) - set(got):
            raise ValueError('Longitudinal statuses require corresponding explicit obligation IDs')
    result = {'schema_version': 1, 'reference_scope': reference_scope, 'sampling_frame': sampling_frame,
              'patient_independence_established': False,
              'split_check_performed': development_records is not None,
              'split_provenance': 'Declared patient groups and normalized duplicate text only; identity, site, template-family and temporal independence require external verification',
              'clinical_accuracy_established': False, 'metrics': _counts(records, rules),
              'intervals': clustered_intervals(records, rules, reps, seed), 'by_report_type': {}, 'by_language': {}}
    for field in ('report_type', 'language'):
        groups = defaultdict(list)
        for row in records:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                value = 'unspecified'
            groups[value].append(row)
        result['by_' + field] = {k: _counts(v, rules) for k,v in sorted(groups.items())}
    return result
