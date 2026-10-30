"""Synthetic privacy attack probes; a regex match is never external-release approval."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from src.clinloop_engine.phi_deidentifier import PHIDeidentifier, PseudonymLedger


def test_unknown_free_text_name_can_never_be_certified_cloud_safe():
    safe, log = PHIDeidentifier().deidentify_patient({'patient_id': 'SYNTHETIC-1',
                         'clinical_context': 'Fictional visitor Alice Example has an 8.5 mm nodule.'})
    assert log['safe_to_send_cloud'] is False
    assert log['human_review_required'] is True
    assert '8.5 mm' in safe['clinical']['clinical_context']
    assert 'HIPAA Safe Harbor Active' not in PHIDeidentifier().build_llm_prompt(safe, 'Review')
    assert 'zero raw PHI' not in json.dumps(PHIDeidentifier().audit_summary())


def test_identical_names_with_different_mrns_never_merge_and_same_mrn_stays_linked():
    engine = PHIDeidentifier()
    a, _ = engine.deidentify_patient({'name': 'Synthetic Same', 'mrn': 'SYN-001'})
    b, _ = engine.deidentify_patient({'name': 'Synthetic Same', 'mrn': 'SYN-002'})
    c, _ = engine.deidentify_patient({'name': 'Synthetic Changed', 'mrn': 'SYN-001'})
    assert a['patient_ref'] != b['patient_ref']
    assert a['patient_ref'] == c['patient_ref'] and a['case_ref'] == c['case_ref']


def test_missing_identity_must_not_collapse_unrelated_records_to_unknown():
    engine = PHIDeidentifier()
    first, log = engine.deidentify_patient({'finding': 'SYNTHETIC first'})
    second, _ = engine.deidentify_patient({'finding': 'SYNTHETIC second'})
    assert first['patient_ref'] != second['patient_ref']
    assert log['stable_identity_available'] is False


def test_pseudonym_namespaces_and_concurrent_calls_remain_consistent():
    ledger = PseudonymLedger()
    name = ledger.pseudonymize('SYNTHETIC-IDENTIFIER', 'PT')
    mrn = ledger.pseudonymize('SYNTHETIC-IDENTIFIER', 'MRN')
    assert name != mrn and mrn.startswith('MRN-')
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: ledger.pseudonymize('SYNTHETIC-IDENTIFIER', 'PT'), range(100)))
    assert values == [name] * 100
    assert 'SYNTHETIC-IDENTIFIER' not in json.dumps(values)


@pytest.mark.parametrize('text,removed', [
    ('주민번호 900101 - 1234567; Nodule 8.5 mm.', '900101'),
    ('MRN: abcd1234; Nodule 8.5 mm.', 'abcd1234'),
    ('주소: 서울특별시 강남구 테헤란로 123; Nodule 8.5 mm.', '테헤란로'),
    ('Call +82 10 1234 5678; Nodule 8.5 mm.', '1234'),
    ('Seen 2026-03-05; Nodule 8.5 mm.', '03-05'),
])
def test_korean_english_patterns_keep_measurements(text, removed):
    output, _ = PHIDeidentifier()._scrub_text(text)
    assert removed not in output and '8.5 mm' in output


def test_short_name_and_vital_signs_are_not_mistaken_for_identifiers():
    output, _ = PHIDeidentifier()._scrub_text('Lipid 4.2 mmol/L; BP 120 80; pulse 98. Li needs review.', {'Li': 'PT-SYNTHETIC'})
    assert 'Lipid 4.2 mmol/L' in output and 'BP 120 80; pulse 98' in output
    assert 'PT-SYNTHETIC needs review' in output
    numeric, _ = PHIDeidentifier()._scrub_text('Measurements: 120 80 98; 8.5 mm.')
    assert '120 80 98' in numeric


def test_fhir_bundle_is_rejected_instead_of_silently_treated_as_one_unknown_patient():
    bundle = {'resourceType': 'Bundle', 'entry': [
        {'resource': {'resourceType': 'Patient', 'id': 'SYNTHETIC-1'}},
        {'resource': {'resourceType': 'Observation', 'subject': {'reference': 'Patient/SYNTHETIC-1'}}},
    ]}
    with pytest.raises(ValueError, match='FHIR'):
        PHIDeidentifier().deidentify_patient(bundle)


@pytest.mark.parametrize('text,removed',[
    ('주소 서울특별시 강남구 테헤란로 123; Nodule 8.5 mm.', ['서울특별시','강남구','테헤란로']),
    ('Visit 2026/3/5; Nodule 8.5 mm.', ['2026/3/5']),
    ('Visit 03/05/2026; Nodule 8.5 mm.', ['03/05/2026']),
    ('Call 010.1234.5678; Nodule 8.5 mm.', ['010.1234.5678']),
])
def test_additional_address_date_and_phone_formats(text,removed):
    result,_=PHIDeidentifier()._scrub_text(text)
    assert all(value not in result for value in removed)
    assert '8.5 mm' in result


def test_known_korean_name_with_honorific_is_removed_without_changing_findings():
    result,_=PHIDeidentifier()._scrub_text('김민수님은 CT에서 8.5 mm 결절이 있습니다.',{'김민수':'PT-SYNTHETIC'})
    assert '김민수' not in result and '8.5 mm' in result
