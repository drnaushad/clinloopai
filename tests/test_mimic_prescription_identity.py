"""Synthetic immutable MIMIC rows: order identity must not collapse drug/dose components."""
import csv
import re
from pathlib import Path

from src.clinloop_engine.mimic_ingest import load
from src.clinloop_engine.browser_analyse import analyse_bundle

ROW = {'subject_id':'SYN-MIMIC','hadm_id':'SYN-STAY','pharmacy_id':'SYN-ORDER',
       'poe_id':'SYN-POE','poe_seq':'1','drug':'Warfarin','prod_strength':'5mg',
       'starttime':'2026-01-01 09:00:00','stoptime':'2026-01-02 09:00:00',
       'dose_val_rx':'5','dose_unit_rx':'mg','route':'PO'}


def read(root, rows, reverse_columns=False):
    hosp=root/'hosp';hosp.mkdir(parents=True,exist_ok=True)
    fields=list(ROW)
    if reverse_columns:fields.reverse()
    with (hosp/'prescriptions.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    with (hosp/'patients.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['subject_id','gender','anchor_year','anchor_age'])
        writer.writeheader();writer.writerow({'subject_id':'SYN-MIMIC','gender':'F','anchor_year':'2026','anchor_age':'65'})
    return load(str(root),['SYN-MIMIC'])['SYN-MIMIC']


def meds(rows):
    return [r for r in rows if r['resourceType']=='MedicationRequest']


def test_order_components_and_doses_are_distinct_and_can_build_a_graph(tmp_path):
    rows=read(tmp_path,[ROW,{**ROW,'drug':'Heparin'},{**ROW,'dose_val_rx':'7.5'}])
    prescriptions=meds(rows)
    assert len(prescriptions)==len({r['id'] for r in prescriptions})==3
    assert all(re.fullmatch(r'[A-Za-z0-9.-]{1,64}',r['id']) for r in prescriptions)
    result=analyse_bundle({'resourceType':'Bundle','entry':[{'resource':r} for r in rows]},'2026-02-01')
    assert result['patients']==1 and result['events']>=3
    assert any(d['rule_id']=='R007' and d['status']!='closed' for d in result['detections'])


def test_row_and_column_order_do_not_change_source_bound_ids(tmp_path):
    rows=[ROW,{**ROW,'dose_val_rx':'7.5'}]
    first={r['id']:r for r in meds(read(tmp_path/'a',rows))}
    second={r['id']:r for r in meds(read(tmp_path/'b',list(reversed(rows)),True))}
    assert first==second


def test_identical_source_rows_deduplicate_without_losing_a_distinct_component(tmp_path):
    prescriptions=meds(read(tmp_path,[ROW,ROW,{**ROW,'drug':'Heparin'}]))
    assert len(prescriptions)==2
    assert all(any(i['system']=='urn:mimic:pharmacy_id' and i['value']=='SYN-ORDER'
                   for i in r['identifier']) for r in prescriptions)
