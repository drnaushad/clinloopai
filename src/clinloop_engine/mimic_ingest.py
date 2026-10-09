"""
mimic_ingest.py — Read MIMIC-IV, MIMIC-IV-Note and MIMIC-CXR into ClinLoop, locally

MIMIC is credentialed data: its data use agreement forbids sharing it or sending it to outside
services, including online AI. This module only reads local files and writes local files. Run it on
the approved machine; nothing here needs a network.

Reads (any that are present; .csv or .csv.gz):
    <mimic-iv>/hosp/patients, admissions, labevents + d_labitems, prescriptions,
                    diagnoses_icd + d_icd_diagnoses, procedures_icd + d_icd_procedures, microbiologyevents
    <mimic-iv>/ed/edstays                      emergency visits
    <mimic-iv-note>/note/radiology, discharge  radiology reports, discharge summaries
    <mimic-cxr>/mimic-cxr-2.0.0-metadata + files/pXX/pNNNNNNNN/sNNNNNNNN.txt   chest X-ray reports

and turns each subject's rows into FHIR R4 resources, so every ClinLoop rule runs unchanged:
labs with their reference range and MIMIC's abnormal flag, prescriptions, admissions and ED stays
(with their diagnoses), procedures, positive cultures, radiology reports (the report reader) and
discharge summaries (the note reader: "follow up with cardiology in 2 weeks").

labevents is large (>100 million rows): it is streamed once and only the chosen subjects are kept.

CLI:
    python -m src.clinloop_engine.mimic_ingest --mimic <dir> [--note <dir>] [--cxr <dir>]
        (--subjects ids.txt | --sample N) --out <folder>
writes <folder>/<Type>.ndjson (FHIR bulk format) for tests/hospital_eval/run_bulk.py and the
chart-review tools (src/validation/chart_review.py), and prints only counts.
"""

import argparse
import base64
import csv
import gzip
import json
import os
import random
from collections import defaultdict
from typing import Dict, Iterable, Iterator, List, Optional, Set

from .fhir_ingest import icd_label

ICD_SYSTEM = {"9": "http://hl7.org/fhir/sid/icd-9-cm", "10": "http://hl7.org/fhir/sid/icd-10-cm"}


def _open(path: str):
    for p in (path + ".csv.gz", path + ".csv"):
        if os.path.exists(p):
            return (gzip.open if p.endswith(".gz") else open)(p, "rt", encoding="utf-8", errors="replace", newline="")
    return None


def _rows(root: Optional[str], *parts: str) -> Iterator[Dict[str, str]]:
    if not root:
        return
    f = _open(os.path.join(root, *parts))
    if f is None:
        return
    with f:
        for row in csv.DictReader(f):
            yield row


def _t(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value.replace(" ", "T") if value else None


def _num(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def choose_subjects(mimic: str, sample: int, seed: int = 42) -> List[str]:
    """A reproducible random sample of subject_ids from patients."""
    ids = sorted(r["subject_id"] for r in _rows(mimic, "hosp", "patients"))
    random.Random(seed).shuffle(ids)
    return sorted(ids[:sample])


def load(mimic: str, subjects: Iterable[str], note: Optional[str] = None, cxr: Optional[str] = None
         ) -> Dict[str, List[Dict]]:
    """FHIR resources per subject_id for the chosen subjects."""
    keep: Set[str] = {str(s) for s in subjects}
    out: Dict[str, List[Dict]] = defaultdict(list)

    def ref(sid: str) -> Dict[str, str]:
        return {"reference": f"Patient/{sid}"}

    for r in _rows(mimic, "hosp", "patients"):
        sid = r["subject_id"]
        if sid in keep:
            p = {"resourceType": "Patient", "id": sid, "gender": {"M": "male", "F": "female"}.get(r.get("gender"), "unknown")}
            if r.get("anchor_year") and r.get("anchor_age"):        # MIMIC gives the age in a shifted anchor year
                p["birthDate"] = f"{int(r['anchor_year']) - int(r['anchor_age'])}-01-01"
            if r.get("dod"):
                p["deceasedDateTime"] = _t(r["dod"])
            out[sid].append(p)

    dx_names = {(r["icd_code"], r["icd_version"]): r["long_title"] for r in _rows(mimic, "hosp", "d_icd_diagnoses")}
    dx_by_stay: Dict[str, List[str]] = defaultdict(list)
    for r in _rows(mimic, "hosp", "diagnoses_icd"):
        if r["subject_id"] not in keep:
            continue
        name = dx_names.get((r["icd_code"], r["icd_version"]), "")
        if int(r.get("seq_num") or 99) <= 3:                       # the principal diagnoses of the stay
            dx_by_stay[r["hadm_id"]].append(name or icd_label([r["icd_code"]]) or r["icd_code"])
        out[r["subject_id"]].append({
            "resourceType": "Condition", "id": f"dx-{r['hadm_id']}-{r['seq_num']}", "subject": ref(r["subject_id"]),
            "clinicalStatus": {"coding": [{"code": "active"}]}, "encounter": {"reference": f"Encounter/{r['hadm_id']}"},
            "code": {"text": name or r["icd_code"],
                     "coding": [{"system": ICD_SYSTEM.get(r["icd_version"], ""), "code": r["icd_code"]}]},
            "_hadm": r["hadm_id"]})

    admissions = {}
    for r in _rows(mimic, "hosp", "admissions"):
        if r["subject_id"] in keep:
            admissions[r["hadm_id"]] = r
            enc = {"resourceType": "Encounter", "id": r["hadm_id"], "status": "finished", "class": {"code": "IMP"},
                   "subject": ref(r["subject_id"]), "period": {"start": _t(r["admittime"]), "end": _t(r["dischtime"])},
                   "type": [{"text": r.get("admission_type") or "Hospital admission"}],
                   "reasonCode": [{"text": t} for t in dx_by_stay.get(r["hadm_id"], [])]}
            if r.get("discharge_location"):
                enc["hospitalization"] = {"dischargeDisposition": {"text": r["discharge_location"]}}
            out[r["subject_id"]].append(enc)
    # A diagnosis's date is its admission (MIMIC does not date diagnoses)
    for sid, resources in out.items():
        for res in resources:
            hadm = res.pop("_hadm", None)
            if hadm is not None:
                res["onsetDateTime"] = _t((admissions.get(hadm) or {}).get("admittime", ""))

    for r in _rows(mimic, "ed", "edstays"):
        if r["subject_id"] in keep:
            out[r["subject_id"]].append({
                "resourceType": "Encounter", "id": f"ed-{r['stay_id']}", "status": "finished", "class": {"code": "EMER"},
                "subject": ref(r["subject_id"]), "period": {"start": _t(r["intime"]), "end": _t(r["outtime"])},
                "type": [{"text": "Emergency department visit"}],
                "hospitalization": {"dischargeDisposition": {"text": r.get("disposition", "")}}})

    items = {r["itemid"]: r for r in _rows(mimic, "hosp", "d_labitems")}
    for r in _rows(mimic, "hosp", "labevents"):
        if r["subject_id"] not in keep:
            continue
        item = items.get(r["itemid"], {})
        label = " ".join(x for x in (item.get("label"), f"[{item['fluid']}]" if item.get("fluid") else "") if x)
        obs = {"resourceType": "Observation", "id": f"lab-{r['labevent_id']}", "status": "final",
               "subject": ref(r["subject_id"]), "category": [{"coding": [{"code": "laboratory"}]}],
               "code": {"text": label or r["itemid"], "coding": [{"system": "urn:mimic:itemid", "code": r["itemid"]}]},
               "effectiveDateTime": _t(r["charttime"])}
        value = _num(r.get("valuenum"))
        if value is not None:
            obs["valueQuantity"] = {"value": value, "unit": r.get("valueuom", "")}
        elif r.get("value"):
            obs["valueString"] = r["value"]
        low, high = _num(r.get("ref_range_lower")), _num(r.get("ref_range_upper"))
        if low is not None or high is not None:
            obs["referenceRange"] = [{**({"low": {"value": low}} if low is not None else {}),
                                      **({"high": {"value": high}} if high is not None else {})}]
        if (r.get("flag") or "").lower() == "abnormal":
            obs["interpretation"] = [{"coding": [{"code": "A"}]}]
        out[r["subject_id"]].append(obs)

    for r in _rows(mimic, "hosp", "microbiologyevents"):
        if r["subject_id"] not in keep or not r.get("org_name") or r.get("ab_name"):
            continue                                       # one row per organism, not per antibiotic tested
        out[r["subject_id"]].append({
            "resourceType": "Observation", "id": f"micro-{r['microevent_id']}", "status": "final",
            "subject": ref(r["subject_id"]), "category": [{"coding": [{"code": "microbiology"}]}],
            "code": {"text": f"{r.get('spec_type_desc', '')} culture".strip()},
            "effectiveDateTime": _t(r.get("storetime") or r.get("charttime") or r.get("chartdate")),
            "valueString": f"growth: {r['org_name']}"})

    for r in _rows(mimic, "hosp", "prescriptions"):
        if r["subject_id"] not in keep or not r.get("drug"):
            continue
        dose = " ".join(x for x in (r.get("dose_val_rx"), r.get("dose_unit_rx"), r.get("route")) if x)
        text = " ".join(x for x in (r["drug"], r.get("prod_strength")) if x)
        out[r["subject_id"]].append({
            "resourceType": "MedicationRequest", "id": f"rx-{r.get('pharmacy_id') or r.get('poe_id')}-{r.get('poe_seq', '')}",
            "status": "completed", "intent": "order", "subject": ref(r["subject_id"]), "authoredOn": _t(r["starttime"]),
            "medicationCodeableConcept": {"text": text}, **({"dosageInstruction": [{"text": dose}]} if dose else {})})

    px_names = {(r["icd_code"], r["icd_version"]): r["long_title"] for r in _rows(mimic, "hosp", "d_icd_procedures")}
    for r in _rows(mimic, "hosp", "procedures_icd"):
        if r["subject_id"] in keep:
            out[r["subject_id"]].append({
                "resourceType": "Procedure", "id": f"px-{r['hadm_id']}-{r['seq_num']}", "status": "completed",
                "subject": ref(r["subject_id"]), "performedDateTime": _t(r["chartdate"]),
                "code": {"text": px_names.get((r["icd_code"], r["icd_version"]), r["icd_code"])}})

    for kind in ("radiology", "discharge"):
        for r in _rows(note, "note", kind):
            if r["subject_id"] not in keep or not r.get("text"):
                continue
            if kind == "radiology":
                out[r["subject_id"]].append({
                    "resourceType": "DiagnosticReport", "id": f"note-{r['note_id']}", "status": "final",
                    "category": [{"coding": [{"code": "RAD"}]}], "subject": ref(r["subject_id"]),
                    "code": {"text": "Radiology report"}, "effectiveDateTime": _t(r["charttime"]), "conclusion": r["text"]})
            else:
                out[r["subject_id"]].append({
                    "resourceType": "DocumentReference", "id": f"note-{r['note_id']}", "status": "current",
                    "subject": ref(r["subject_id"]), "date": _t(r["charttime"]), "type": {"text": "Discharge summary"},
                    "content": [{"attachment": {"contentType": "text/plain",
                                                "data": base64.b64encode(r["text"].encode()).decode()}}]})

    for r in _rows(cxr, "mimic-cxr-2.0.0-metadata"):
        sid, study = r.get("subject_id", ""), r.get("study_id", "")
        if sid not in keep or not study:
            continue
        report = os.path.join(cxr, "files", f"p{sid[:2]}", f"p{sid}", f"s{study}.txt")
        rid = f"cxr-{study}"
        if not os.path.exists(report) or any(x.get("id") == rid for x in out[sid]):
            continue
        date = r.get("StudyDate", "")
        when = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else None
        with open(report, encoding="utf-8", errors="replace") as f:
            text = f.read()
        out[sid].append({"resourceType": "DiagnosticReport", "id": rid, "status": "final",
                         "category": [{"coding": [{"code": "RAD"}]}], "subject": ref(sid),
                         "code": {"text": "Chest X-ray"}, "effectiveDateTime": when, "conclusion": text})
    return dict(out)


def write_bulk(people: Dict[str, List[Dict]], folder: str) -> Dict[str, int]:
    """FHIR bulk-data layout: one NDJSON file per resource type."""
    os.makedirs(folder, exist_ok=True)
    counts: Dict[str, int] = defaultdict(int)
    files: Dict[str, object] = {}
    try:
        for resources in people.values():
            for r in resources:
                t = r["resourceType"]
                if t not in files:
                    files[t] = open(os.path.join(folder, f"{t}.000.ndjson"), "w", encoding="utf-8")
                files[t].write(json.dumps(r, ensure_ascii=False) + "\n")
                counts[t] += 1
    finally:
        for f in files.values():
            f.close()
    return dict(counts)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="MIMIC-IV (+Note, +CXR) → FHIR NDJSON for ClinLoop, locally")
    ap.add_argument("--mimic", required=True, help="MIMIC-IV folder (with hosp/, optionally ed/)")
    ap.add_argument("--note", help="MIMIC-IV-Note folder (with note/)")
    ap.add_argument("--cxr", help="MIMIC-CXR folder (metadata CSV and files/)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--subjects", help="file with one subject_id per line")
    group.add_argument("--sample", type=int, help="random sample of N subjects (seed 42)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    subjects = ([s.strip() for s in open(args.subjects) if s.strip()] if args.subjects
                else choose_subjects(args.mimic, args.sample))
    counts = write_bulk(load(args.mimic, subjects, args.note, args.cxr), args.out)
    print(f"subjects: {len(subjects)}")
    for t in sorted(counts):
        print(f"  {t}: {counts[t]}")


if __name__ == "__main__":
    main()
