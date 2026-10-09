# Public medical datasets: what ClinLoop uses, and how

ClinLoop tracks follow-up: did the obligation that a finding, result or plan created get done? A
dataset helps when it shows the trigger, the later follow-up, or both.

## The data-use rule comes first

**Credentialed data never leaves the approved machine.** MIMIC-IV, MIMIC-IV-Note, MIMIC-CXR,
MIMIC-IV-ECHO, CheXpert Plus, EchoNet and AI-Hub are released under data use agreements. These
agreements forbid sharing the data or sending it to outside services, and that includes online AI
services and chat assistants.

ClinLoop's readers only read and write local files and need no network. Run them on the computer
where your access was approved. Commit only code and aggregate counts, never records.

## Readers in ClinLoop

| Reader | Input | Command |
|---|---|---|
| `omop_ingest.py` | Any OMOP CDM database exported as CSV (FEEDER-NET sites, MIMIC-IV in OMOP, OHDSI Eunomia samples) | `python -m src.clinloop_engine.omop_ingest <cdm folder> [--vocab <folder>]` |
| `mimic_ingest.py` | MIMIC-IV `hosp/` and `ed/`, MIMIC-IV-Note `note/`, MIMIC-CXR reports | `python -m src.clinloop_engine.mimic_ingest --mimic <dir> --note <dir> --cxr <dir> --sample 500 --out fhir/` |
| `ecg.py` | ECGs in FHIR (LOINC 11524-6, 8636-3 QTc …); PTB-XL `ptbxl_database.csv` | `ecg.load_ptbxl(path)` |

Each reader turns the records into FHIR R4 resources, so all 59 rules run on them unchanged.
`mimic_ingest --out` writes FHIR bulk NDJSON. These two tools then work on it directly:
- **`tests/hospital_eval/run_bulk.py`:** runs every rule over each patient's record.
- **The chart-review tools (`src/validation/chart_review.py`):** draw a blinded sample for two clinicians
  to review, and score it.

**Dates are shifted per patient** in MIMIC and other research copies. So each patient is judged at the
end of their own record (`omop_ingest.record_end`), not at today's date.

## Dataset by dataset

| Dataset | Use for ClinLoop | Status |
|---|---|---|
| **MIMIC-IV demo (OMOP)** | Real hospital records of 100 patients; open access (ODbL) | **Tested**: see results below |
| **MIMIC-IV + MIMIC-IV-Note** | 2.3M radiology reports for the report reader; discharge summaries for the note reader; labs with ranges and abnormal flags; admissions and ED stays | Reader ready; needs credentialed access, to be run locally |
| **MIMIC-CXR** | Chest X-ray reports: nodules and follow-up advice; the image second reader | Reader ready (reports); credentialed |
| **CheXpert Plus** | Reports split into sections, from a second hospital (generalisation) | Use the report-validation tool on its report CSV |
| **PTB-XL** | ECG statements: atrial fibrillation (AF) → anticoagulation decision (R054); long QT | Reader ready; open access (CC BY 4.0) |
| **TCIA (e.g. LIDC-IDRI)** | Lung CT with radiologists' nodule marks: size and growth tracking (R056) | Planned |
| **FEEDER-NET** | Stage 1 of [`STUDY_PROTOCOL.md`](STUDY_PROTOCOL.md) across Korean hospitals without moving data (OMOP-CDM) | Reader ready (OMOP); needs an institutional partnership |
| **AI-Hub** | Korean brain-haemorrhage CT for the critical-finding loop (R035) | Application within Korea |
| **MIMIC-IV-ECHO / EchoNet-Dynamic** | Low ejection fraction → heart-failure work-up | Low priority (an image model, not follow-up tracking) |
| **fastMRI** | Raw MRI scanner data for faster scans | Not relevant to follow-up |

## First real-data run: MIMIC-IV demo in OMOP (100 patients)

**Source:** OHDSI Eunomia `MIMIC_5.3`, the MIMIC-IV demo converted to OMOP, ODbL licence:
- 338,550 measurements, 86,779 of them with reference ranges;
- 18,229 drug records;
- 852 visits;
- 15 deaths.

The copy lacks most of the standard OMOP vocabulary, so many drug and diagnosis names are missing. A
hospital's own OMOP database includes the full vocabulary.

**Robustness:** all 100 patients were read and evaluated with no errors. The app takes 72 seconds once
the records are loaded.

**The main lesson: abnormal labs.** Synthetic data carries no abnormal flags, so this problem showed up
only on real data:
- **The volume:** for 100 patients, the first run raised 35,630 "abnormal result → notify the patient"
  obligations and 8,757 "abnormal result after discharge" obligations.
- **Why:**
  - 83% of the abnormal results were taken during a hospital stay, where the team at the bedside acts on
    them;
  - most of the rest were each component of a blood count flagged separately, or the same chronic
    abnormality at every draw.
- **The rules now:**
  - **During a stay:** no "notify the patient" obligation. Critical values still require the documented
    call (R022), wherever the patient is.
  - **One sample:** one obligation per blood draw, listing all its abnormal results.
  - **Known abnormality:** the same test, abnormal in the same direction within 90 days as an outpatient,
    is not new.
- **The result:**

  | Rule | Before | After |
  |---|---|---|
  | R001 (abnormal result → notify the patient) | 35,630 | about 500 |
  | R021 (abnormal result after discharge) | 8,757 | about 100 |

**Diagnoses sent as codes only:** the rules now recognise the ICD-10 and ICD-9 codes for:
- heart failure;
- atrial fibrillation;
- myocardial infarction;
- dialysis or end-stage kidney disease;
- pre-eclampsia;
- cirrhosis;
- hepatitis B.

## Blind clinical review on the real records

**Method:**
- 111 obligations were sampled across 11 rules from the first real-data run.
- An independent reviewer judged each one from the patient's whole record, without seeing the app's
  verdict. For each, they decided:
  - whether the obligation was clinically warranted;
  - if so, its status at the end of the record.

**First pass, before any of the fixes below:**

| Reviewer said | Count |
|---|---|
| Warranted | 33 (30%) |
| Not warranted | 66 |
| Unclear | 12 |

- **Status:** where both the reviewer and the app could judge it, the app's status matched 14 of 17.
- **Honest reading:** on real data, most of what the app raised at first would not survive a
  clinician's review. That is the result that matters most from this test.

**Why the "not warranted" ones were raised, and what changed:**

| Reason (reviewer) | Fix |
|---|---|
| Labs drawn during a stay. In this data, many multi-day stays are labelled "outpatient", and ED labs are drawn just before admission | An encounter lasting more than a day counts as a stay, and so do the 12 hours before an admission. Drug starts and creatinine rises in hospital are not outpatient follow-ups |
| Trivial values: blood-count indices, anion gap, urine microscopy, values just outside the range | Panel indices are shown with their panel, not reviewed on their own. A value within 10% of the reference limit is borderline |
| Creatinine "rises" that stay within the normal range, or start from an impossible baseline of 0.1–0.3 | An AKI warning needs a value above the laboratory's upper limit, and a baseline of at least 0.3 mg/dL |
| R021 (result after discharge) fired on new outpatient draws | Now follows Roy 2005: drawn by discharge and resulted after it. Without a result time, only within 7 days |
| Chronic heart failure coded I50.22 read as new | Chronic and acute-on-chronic ICD codes mean known heart failure. An echo during the same stay answers R016 |

**A false closure the reviewer's data exposed:** a thyroid follow-up (R012) could be closed by any
monitoring lab, for example a potassium check after starting lisinopril. A drug's monitoring lab could
also close another drug's obligation. Each follow-up must now be the right test (repeat TSH or free
T4), or the lab that monitors that drug.

**After the fixes, on the same 111 cases:**

| | Still raised | No longer raised |
|---|---|---|
| Warranted | 27 | 6 |
| Not warranted | 21 | 45 |
| Unclear | 10 | 2 |

- **Of what the app still raises:** 47% is warranted, or 56% leaving out the unclear cases.
- **Status:** matches the reviewer's in 15 of 16 cases where both could judge it.
- **Not an unbiased estimate:** the fixes were designed from this same sample. A fresh sample, ideally
  judged by two clinicians, is the next measurement.
- **What was lost:** of the 6 warranted cases no longer raised, 4 are new outpatient results after
  discharge. These are now judged by the general abnormal-result rules (R001/R002) rather than R021.

**What this data cannot test:**
- **Patient notification and clinic visits** are not recorded here. So "done" can rarely be confirmed
  for R001, R002, R021 and R023.
- **Lab draws:** many lab-only draws are labelled as outpatient visits.
- **Missing records:** there are no notes, and ICD-9-era procedures are missing.

These are properties of this research copy. A hospital's own feed records them.
