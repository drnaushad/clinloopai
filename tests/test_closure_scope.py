"""Synthetic side/source challenges. These tests do not establish clinical accuracy."""
from datetime import datetime
import pytest
from src.clinloop_engine.browser_analyse import analyse_bundle
from src.clinloop_engine.closure_scope import tissue_scope_matches, resource_scope
from src.clinloop_engine.fhir_ingest import norm_ref


def bundle(side='right', report='Left breast mass, BI-RADS 4. Recommend left breast biopsy.'):
    dr={'resourceType':'DiagnosticReport','id':'mammogram','status':'final',
        'subject':{'reference':'Patient/SYNTHETIC-SCOPE'},'effectiveDateTime':'2026-01-01T09:00:00Z',
        'category':[{'coding':[{'code':'RAD'}]}],'code':{'text':'Mammography'},'conclusion':report}
    biopsy={'resourceType':'Procedure','id':'biopsy','status':'completed',
        'subject':{'reference':'Patient/SYNTHETIC-SCOPE'},'performedDateTime':'2026-01-10T09:00:00Z',
        'code':{'text':f'{side} breast core needle biopsy'},'bodySite':[{'text':f'{side} breast'}]}
    return {'resourceType':'Bundle','type':'collection','entry':[{'resource':r} for r in
        [{'resourceType':'Patient','id':'SYNTHETIC-SCOPE'},dr,biopsy]]}


def r018(data):
    return next(row for row in analyse_bundle(data,'2026-02-01T00:00:00Z')['detections'] if row['rule_id']=='R018')


@pytest.mark.parametrize('side',['right','','bilateral'])
def test_wrong_unknown_or_bilateral_tissue_does_not_close_left_target(side):
    row=r018(bundle(side))
    assert row['status'] not in {'closed','delayed'}
    assert any('linkage' in line or 'laterality' in line for line in row['basis']+row['evidence'])


def test_same_side_completed_tissue_can_satisfy_tracked_step():
    assert r018(bundle('left'))['status']=='closed'


@pytest.mark.parametrize('report',[
    'Breast mass, BI-RADS 4. Recommend biopsy.',
    'Left breast mass and right breast mass, BI-RADS 4. Recommend biopsy.',
    'Bilateral breast masses, BI-RADS 4. Recommend biopsy.',
])
def test_ambiguous_or_missing_target_side_requires_human_reconciliation(report):
    assert r018(bundle('left',report))['status'] not in {'closed','delayed'}


def test_korean_sides_remain_distinct():
    assert r018(bundle('right','좌측 유방 종괴, BI-RADS 4. 조직검사 권고.'))['status'] not in {'closed','delayed'}
    assert r018(bundle('left','좌측 유방 종괴, BI-RADS 4. 조직검사 권고.'))['status']=='closed'


def test_explicit_lesion_identity_cannot_be_replaced_by_another_lesion():
    # Observation.focus is a real R4 field. Do not invent Procedure.focus.
    a=resource_scope({'resourceType':'Observation','focus':[{'reference':'BodyStructure/a'}]},norm_ref)
    b=resource_scope({'resourceType':'Observation','focus':[{'reference':'BodyStructure/b'}]},norm_ref)
    assert not tissue_scope_matches({'closure_scope':a},{'closure_scope':b},'R018')
    assert tissue_scope_matches({'closure_scope':a},{'closure_scope':a},'R018')


def test_supplied_report_specimen_is_not_replaced_by_an_unlinked_procedure():
    data=bundle('left')
    data['entry'][1]['resource']['specimen']=[{'reference':'Specimen/target'}]
    assert r018(data)['status'] not in {'closed','delayed'}


def test_observation_single_body_site_and_optional_null_fields():
    assert resource_scope({'bodySite':{'text':'Left breast'}},norm_ref)['laterality']==['left']
    assert resource_scope({'bodySite':None,'focus':None,'specimen':None},norm_ref)=={}
    assert resource_scope({'bodySite':{'coding':None}},norm_ref)=={}
    assert resource_scope({'bodySite':{'coding':[{'system':'http://snomed.info/sct','code':{}}]}},norm_ref)=={}


def test_missing_scope_or_mismatched_specimen_does_not_invent_linkage():
    expected={'closure_scope':{'lesion_refs':['BodyStructure/a']}}
    assert not tissue_scope_matches(expected,{},'R036')
    assert not tissue_scope_matches({'closure_scope':{'specimen_refs':['Specimen/a']}},
                                    {'closure_scope':{'specimen_refs':['Specimen/b']}},'R036')


def test_structured_side_and_prose_conflict_is_retained_as_ambiguous():
    scope=resource_scope({'code':{'text':'Left breast biopsy'},'bodySite':[{'coding':[
        {'system':'http://snomed.info/sct','code':'24028007'}]}]},norm_ref)
    assert scope['laterality']==['left','right']
    assert not tissue_scope_matches({'closure_scope':scope},{'closure_scope':scope},'R018')
