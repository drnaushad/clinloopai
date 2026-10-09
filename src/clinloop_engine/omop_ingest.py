"""
omop_ingest.py — Read an OMOP Common Data Model database (CSV export) into ClinLoop

Many hospitals and research networks keep their records in the OHDSI OMOP CDM: FEEDER-NET's Korean
hospitals, MIMIC-IV's OMOP release, most observational-research databases. This module turns each
person's OMOP rows into the FHIR R4 resources the rest of ClinLoop already reads, so every rule,
pattern and the worklist work unchanged:

    person            → Patient (sex, birth year, death from `death`)
    visit_occurrence  → Encounter (inpatient / emergency / outpatient, start and end)
    measurement       → Observation (LOINC code from the vocabulary, value, unit, reference range)
    condition_occurrence → Condition        drug_exposure → MedicationRequest
    procedure_occurrence → Procedure        note          → DiagnosticReport (radiology) or DocumentReference
    observation       → not mapped (social and administrative facts), except smoking status

Names and codes come from the CONCEPT table (the OMOP vocabulary). A site's database normally holds
the full vocabulary; extra vocabulary folders can be given. Without a concept the source value is used.

Nothing leaves the machine: the module reads local files and returns Python objects.

CLI (prints a per-person summary; never prints record contents):
    python -m src.clinloop_engine.omop_ingest <cdm folder> [--vocab <folder> …] [--limit N]
"""

import argparse
import base64
import csv
import glob
import os
from collections import defaultdict
from typing import Dict, Iterable, Iterator, List, Optional

from .fhir_ingest import icd_label

# OMOP standard concept ids used directly (stable across vocabulary releases)
GENDER = {"8507": "male", "8532": "female"}
VISIT_CLASS = {
    "9201": "IMP", "262": "IMP", "8717": "IMP", "32037": "IMP",   # inpatient, ER+inpatient, inpatient hospital, ICU
    "9203": "EMER", "8870": "EMER",                                 # emergency room
    "581385": "OBSENC",                                             # observation room
    "9202": "AMB", "38004207": "AMB", "8883": "AMB", "581477": "AMB", "5083": "AMB",  # outpatient, clinic, telehealth
}
SMOKING_CONCEPTS = {"4005823": "current", "4310250": "former", "4144272": "never", "903650": "former", "903651": "never"}
_SYSTEMS = {"LOINC": "http://loinc.org", "SNOMED": "http://snomed.info/sct", "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
            "ICD9CM": "http://hl7.org/fhir/sid/icd-9-cm", "ICD10": "http://hl7.org/fhir/sid/icd-10",
            "RxNorm": "http://www.nlm.nih.gov/research/umls/rxnorm", "CPT4": "http://www.ama-assn.org/go/cpt",
            "KCD7": "urn:oid:1.2.410.200052.1.1", "EDI": "urn:oid:1.2.410.200052.1.2"}


def _table_path(folder: str, name: str) -> Optional[str]:
    for path in glob.glob(os.path.join(folder, "*")):
        base = os.path.basename(path).lower()
        if base in (f"{name}.csv", f"{name}.csv.gz", f"{name}.txt"):
            return path
    return None


def _rows(folder: str, name: str) -> Iterator[Dict[str, str]]:
    path = _table_path(folder, name)
    if not path:
        return
    import gzip
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        for row in csv.DictReader(f, delimiter=delimiter):
            yield {k.lower(): (v or "").strip() for k, v in row.items() if k}


class Vocabulary:
    """concept_id → (name, vocabulary, code), from the CDM's CONCEPT table and any extra vocabulary folders."""

    def __init__(self, folders: Iterable[str]):
        self.concepts: Dict[str, tuple] = {}
        for folder in folders:
            for r in _rows(folder, "concept"):
                if r.get("concept_id") and r["concept_id"] not in self.concepts:
                    self.concepts[r["concept_id"]] = (r.get("concept_name", ""), r.get("vocabulary_id", ""),
                                                      r.get("concept_code", ""))

    def coding(self, *concept_ids: str) -> List[Dict[str, str]]:
        out = []
        for cid in concept_ids:
            c = self.concepts.get(cid or "")
            if c and cid != "0":
                name, vocab, code = c
                out.append({"system": _SYSTEMS.get(vocab, f"urn:omop:{vocab}"), "code": code, "display": name})
        return out

    def name(self, *concept_ids: str) -> str:
        for cid in concept_ids:
            c = self.concepts.get(cid or "")
            if c and cid != "0" and c[0]:
                return c[0]
        return ""


def _when(r: Dict[str, str], prefix: str) -> Optional[str]:
    value = r.get(f"{prefix}_datetime") or r.get(f"{prefix}_date")
    return value.replace(" ", "T") if value else None


def _num(v: str) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _source_coding(source_value: str, source_concept: str, vocab: Vocabulary) -> List[Dict[str, str]]:
    coding = vocab.coding(source_concept)
    if not coding and source_value:
        coding = [{"system": "urn:omop:source", "code": source_value.strip()}]
    return coding


def load_cdm(folder: str, vocab_folders: Iterable[str] = (), persons: Optional[Iterable[str]] = None
             ) -> Dict[str, List[Dict]]:
    """FHIR resources per person_id from an OMOP CDM folder of CSV tables."""
    vocab = Vocabulary([folder, *vocab_folders])
    wanted = set(persons) if persons is not None else None
    out: Dict[str, List[Dict]] = defaultdict(list)

    def keep(pid: str) -> bool:
        return bool(pid) and (wanted is None or pid in wanted)

    def ref(pid: str) -> Dict[str, str]:
        return {"reference": f"Patient/{pid}"}

    deaths = {r["person_id"]: _when(r, "death") for r in _rows(folder, "death") if r.get("person_id")}
    for r in _rows(folder, "person"):
        pid = r.get("person_id", "")
        if not keep(pid):
            continue
        patient = {"resourceType": "Patient", "id": pid, "gender": GENDER.get(r.get("gender_concept_id", ""), "unknown")}
        if r.get("year_of_birth"):
            patient["birthDate"] = (r.get("birth_datetime") or "")[:10] or (
                f"{r['year_of_birth']}-{int(r.get('month_of_birth') or 1):02d}-{int(r.get('day_of_birth') or 1):02d}")
        if deaths.get(pid):
            patient["deceasedDateTime"] = deaths[pid]
        out[pid].append(patient)

    for r in _rows(folder, "visit_occurrence"):
        pid = r.get("person_id", "")
        if not keep(pid):
            continue
        cls = VISIT_CLASS.get(r.get("visit_concept_id", ""), "AMB")
        enc = {"resourceType": "Encounter", "id": f"v{r['visit_occurrence_id']}", "status": "finished",
               "class": {"code": cls}, "subject": ref(pid),
               "period": {"start": _when(r, "visit_start"), "end": _when(r, "visit_end")},
               "type": [{"text": vocab.name(r.get("visit_concept_id", "")) or cls}]}
        if vocab.name(r.get("care_site_id", "")):
            enc["serviceType"] = {"text": vocab.name(r["care_site_id"])}
        out[pid].append(enc)

    # Diagnoses of a stay become the stay's discharge diagnoses (reason), as hospital feeds send them
    dx_by_visit: Dict[str, List[str]] = defaultdict(list)
    for r in _rows(folder, "condition_occurrence"):
        pid = r.get("person_id", "")
        if not keep(pid):
            continue
        name = vocab.name(r.get("condition_concept_id", ""), r.get("condition_source_concept_id", ""))
        coding = vocab.coding(r.get("condition_concept_id", "")) + _source_coding(
            r.get("condition_source_value", ""), r.get("condition_source_concept_id", ""), vocab)
        out[pid].append({"resourceType": "Condition", "id": f"c{r['condition_occurrence_id']}", "subject": ref(pid),
                         "clinicalStatus": {"coding": [{"code": "active"}]},
                         "code": {"text": name or r.get("condition_source_value", ""), "coding": coding},
                         "onsetDateTime": _when(r, "condition_start")})
        label = name or icd_label([c["code"] for c in coding])
        if r.get("visit_occurrence_id") and label:
            dx_by_visit[r["visit_occurrence_id"]].append(label)
    for pid, resources in out.items():
        for res in resources:
            if res["resourceType"] == "Encounter" and dx_by_visit.get(res["id"][1:]):
                res["reasonCode"] = [{"text": t} for t in dx_by_visit[res["id"][1:]][:3]]

    for r in _rows(folder, "measurement"):
        pid = r.get("person_id", "")
        if not keep(pid):
            continue
        name = vocab.name(r.get("measurement_concept_id", ""), r.get("measurement_source_concept_id", ""))
        obs = {"resourceType": "Observation", "id": f"m{r['measurement_id']}", "status": "final", "subject": ref(pid),
               "category": [{"coding": [{"code": "laboratory"}]}],
               "code": {"text": name or r.get("measurement_source_value", ""),
                        "coding": vocab.coding(r.get("measurement_concept_id", ""))},
               "effectiveDateTime": _when(r, "measurement")}
        value = _num(r.get("value_as_number", ""))
        unit = r.get("unit_source_value") or vocab.name(r.get("unit_concept_id", ""))
        if value is not None:
            obs["valueQuantity"] = {"value": value, "unit": unit}
        elif vocab.name(r.get("value_as_concept_id", "")) or r.get("value_source_value"):
            obs["valueString"] = vocab.name(r.get("value_as_concept_id", "")) or r["value_source_value"]
        low, high = _num(r.get("range_low", "")), _num(r.get("range_high", ""))
        if low is not None or high is not None:
            obs["referenceRange"] = [{**({"low": {"value": low}} if low is not None else {}),
                                      **({"high": {"value": high}} if high is not None else {})}]
        out[pid].append(obs)

    for r in _rows(folder, "observation"):
        pid = r.get("person_id", "")
        status = SMOKING_CONCEPTS.get(r.get("observation_concept_id", "")) or SMOKING_CONCEPTS.get(r.get("value_as_concept_id", ""))
        if keep(pid) and status:
            out[pid].append({"resourceType": "Observation", "id": f"o{r['observation_id']}", "status": "final",
                             "subject": ref(pid), "code": {"text": "Tobacco smoking status"},
                             "valueCodeableConcept": {"text": status}, "effectiveDateTime": _when(r, "observation")})

    for r in _rows(folder, "drug_exposure"):
        pid = r.get("person_id", "")
        if not keep(pid):
            continue
        name = (vocab.name(r.get("drug_concept_id", ""), r.get("drug_source_concept_id", ""))
                or r.get("drug_source_value", ""))
        med = {"resourceType": "MedicationRequest", "id": f"d{r['drug_exposure_id']}", "status": "completed",
               "intent": "order", "subject": ref(pid), "authoredOn": _when(r, "drug_exposure_start"),
               "medicationCodeableConcept": {"text": name, "coding": vocab.coding(r.get("drug_concept_id", ""))}}
        dose = " ".join(x for x in (r.get("quantity"), r.get("dose_unit_source_value"), r.get("sig"),
                                    r.get("route_source_value")) if x)
        if dose:
            med["dosageInstruction"] = [{"text": dose}]
        out[pid].append(med)

    for r in _rows(folder, "procedure_occurrence"):
        pid = r.get("person_id", "")
        if not keep(pid):
            continue
        name = vocab.name(r.get("procedure_concept_id", ""), r.get("procedure_source_concept_id", ""))
        out[pid].append({"resourceType": "Procedure", "id": f"p{r['procedure_occurrence_id']}", "status": "completed",
                         "subject": ref(pid), "performedDateTime": _when(r, "procedure"),
                         "code": {"text": name or r.get("procedure_source_value", ""),
                                  "coding": vocab.coding(r.get("procedure_concept_id", ""))}})

    for r in _rows(folder, "note"):
        pid = r.get("person_id", "")
        text = r.get("note_text", "")
        if not keep(pid) or not text:
            continue
        kind = " ".join([r.get("note_title", ""), vocab.name(r.get("note_class_concept_id", ""), r.get("note_type_concept_id", ""))])
        when = _when(r, "note")
        if "radiolog" in kind.lower() or "imaging" in kind.lower():
            out[pid].append({"resourceType": "DiagnosticReport", "id": f"n{r['note_id']}", "status": "final",
                             "category": [{"coding": [{"code": "RAD"}]}], "subject": ref(pid),
                             "code": {"text": r.get("note_title") or "Radiology report"},
                             "effectiveDateTime": when, "conclusion": text})
        else:
            out[pid].append({"resourceType": "DocumentReference", "id": f"n{r['note_id']}", "status": "current",
                             "subject": ref(pid), "date": when, "type": {"text": kind.strip() or "Clinical note"},
                             "content": [{"attachment": {"contentType": "text/plain",
                                                         "data": base64.b64encode(text.encode()).decode()}}]})
    return dict(out)


def record_end(resources: List[Dict]) -> Optional[str]:
    """The last date in a person's record: OMOP research copies shift dates, so 'now' is per person."""
    stamps = [r.get("effectiveDateTime") or r.get("authoredOn") or r.get("performedDateTime") or r.get("onsetDateTime")
              or ((r.get("period") or {}).get("end")) or "" for r in resources]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


def main(argv: Optional[List[str]] = None) -> None:
    from .fhir_ingest import bundle_to_events
    from .loop_detector import ClinLoopDetector, lapse_after_death
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--vocab", action="append", default=[], help="extra folder with a CONCEPT table")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    people = load_cdm(args.folder, args.vocab)
    rules: Dict[str, int] = defaultdict(int)
    for i, (pid, resources) in enumerate(sorted(people.items())):
        if args.limit and i >= args.limit:
            break
        events, _ = bundle_to_events(resources)
        found = ClinLoopDetector(evaluation_time=record_end(resources)).process_patient("omop", pid, events.get(pid, []))
        for d in lapse_after_death(found, resources):
            rules[f"{d.rule_id} {d.loop_status}"] += 1
    print(f"persons: {len(people)}")
    for k in sorted(rules):
        print(f"  {k}: {rules[k]}")


if __name__ == "__main__":
    main()
