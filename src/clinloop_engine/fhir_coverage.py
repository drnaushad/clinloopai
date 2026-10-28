"""Aggregate FHIR input coverage, independent of clinical matching or diagnosis.

A successful export is not proof that narrative reports were read. These counts
cover only histories evaluated in this run, including lab reports whose results
may reside in linked Observations. No remote attachments are fetched here.
"""
from typing import Dict, Iterable

COUNTERS = (
    'diagnostic_reports', 'reports_with_attachments', 'with_conclusion', 'with_coded_conclusion_only',
    'attachment_only', 'linked_results_only', 'without_summary_or_attachment',
    'document_references', 'document_reference_inline_text',
    'document_reference_linked_only', 'mapping_warning_messages',
)
WARNING_CATEGORIES = (
    'missing_patient_reference', 'missing_timestamp', 'unreadable_date',
    'unknown_status', 'missing_lab_interpretation_or_range', 'other_mapping_warning',
)


def empty_coverage() -> Dict:
    return {**dict.fromkeys(COUNTERS, 0), 'warning_categories': dict.fromkeys(WARNING_CATEGORIES, 0)}


def _items(value):
    return value if isinstance(value, list) else []


def report_coverage(resources: Iterable[Dict], warnings: Iterable[str] = ()) -> Dict:
    """Counts indicate field presence, not completeness or correctness of content."""
    out = empty_coverage()
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        kind = resource.get('resourceType')
        if kind == 'DiagnosticReport':
            out['diagnostic_reports'] += 1
            attachments = any(isinstance(a, dict) and (a.get('data') or a.get('url'))
                              for a in _items(resource.get('presentedForm')))
            out['reports_with_attachments'] += int(attachments)
            conclusion = resource.get('conclusion')
            if isinstance(conclusion, str) and conclusion.strip():
                out['with_conclusion'] += 1
            elif any(isinstance(code, dict) and (code.get('text') or code.get('coding'))
                     for code in _items(resource.get('conclusionCode'))):
                out['with_coded_conclusion_only'] += 1
            elif attachments:
                out['attachment_only'] += 1
            elif resource.get('result'):
                out['linked_results_only'] += 1
            else:
                out['without_summary_or_attachment'] += 1
        elif kind == 'DocumentReference':
            out['document_references'] += 1
            attachments = [entry.get('attachment') if isinstance(entry.get('attachment'), dict) else {} for entry in _items(resource.get('content'))
                           if isinstance(entry, dict)]
            if any(str(a.get('contentType') or '').split(';')[0].lower() in {'text/plain', 'text/html'}
                   and a.get('data') for a in attachments):
                out['document_reference_inline_text'] += 1
            elif any(a.get('url') for a in attachments):
                out['document_reference_linked_only'] += 1
    for message in warnings:
        text = message.lower()
        category = ('missing_patient_reference' if 'no patient reference' in text else
                    'missing_timestamp' if 'no timestamp' in text else
                    'unreadable_date' if 'unreadable date' in text else
                    'unknown_status' if 'unrecognised status' in text else
                    'missing_lab_interpretation_or_range' if 'no interpretation flag' in text else
                    'other_mapping_warning')
        out['mapping_warning_messages'] += 1
        out['warning_categories'][category] += 1
    return out


def merge_coverage(total: Dict, addition: Dict) -> None:
    for key in COUNTERS:
        total[key] += addition[key]
    for key in WARNING_CATEGORIES:
        total['warning_categories'][key] += addition['warning_categories'][key]


def safe_coverage(value: Dict) -> Dict:
    """Accept fixed count keys only; never persist arbitrary source/error text."""
    if not isinstance(value, dict) or set(value) != set(COUNTERS) | {'warning_categories'}:
        raise ValueError('Invalid coverage counters')
    categories = value['warning_categories']
    if not isinstance(categories, dict) or set(categories) != set(WARNING_CATEGORIES):
        raise ValueError('Invalid coverage categories')
    if any(type(n) is not int or n < 0 for n in
           [*(value[key] for key in COUNTERS), *categories.values()]):
        raise ValueError('Invalid coverage count')
    return {**{key: value[key] for key in COUNTERS}, 'warning_categories': dict(categories)}
