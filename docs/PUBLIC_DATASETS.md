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

Each reader turns the records into FHIR R4 resources, so all 65 rules run on them unchanged.
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
| **MIMIC-IV + MIMIC-IV-Note** | 2.3M radiology reports for the report reader; discharge summaries for the note reader; labs with ranges and abnormal flags; admissions and ED stays | Reader ready; needs credentialed access, to be run locally. Study plan: [`STUDY_PROTOCOL_STAGE1A.md`](STUDY_PROTOCOL_STAGE1A.md) |
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

## Reproducible local report pilot (20 October 2026)

The machine-readable access/task register is [`data/evaluation_sources.json`](../data/evaluation_sources.json).
It records official sources and access gates; it does not claim that credentialed datasets have been obtained.
RadGraph's human-labelled train/dev/test files differ from its automatically generated graphs. n2c2 labels
are task-specific. Neither is automatically a reference for completed follow-up care.

`src/validation/dataset_evaluation.py` prepares an independent, blinded sample from local OpenI XML:

```bash
python -m src.validation.dataset_evaluation prepare-openi \
  --xml /home/alam/clinloop-data/openi/ecgen-radiology \
  --out /home/alam/clinloop-data/evaluation/new-study --sample 100 --seed 42
python -m src.validation.dataset_evaluation predict \
  --out /home/alam/clinloop-data/evaluation/new-study
python -m src.validation.dataset_evaluation score \
  --out /home/alam/clinloop-data/evaluation/new-study
```

The outputs stay outside the repository. Separate `reviewer_1.csv` and `reviewer_2.csv` contain no
predictions. Two distinct clinicians fill `reviewer_id`, `reviewer_role=clinician`, `label_status=complete`,
and `expected_rules` (rule IDs or explicit `NONE`). They judge **any follow-up within the report-reader's
prespecified rule scope**, not whether the patient actually received care. Conflicting rule sets or
single-rule deadline intervals need a third clinician's completed row in `adjudication.csv`. Blank or
unresolved reviews block scoring; do not turn uncertainty into `NONE`. Roles are declared by reviewers;
the study coordinator must verify qualifications and independence.

The runner evaluates rules, MedGemma 27B, MedGemma 4B and EXAONE on the same reports. The scorer compares
report-level triage for each model alone and each rules-plus-model combination. This coarse comparison
is not finding-level extraction accuracy. It reports precision, recall, F1, false alerts per 100 reports,
missed positive reports, coverage and conservative recall including model abstentions as misses.
Missing model answers never silently count as normal. Rules-only deadline accuracy is available for
single-rule references with explicit bounds; the existing model schema has no structured deadlines,
so model deadline accuracy is explicitly unscored.

The CLI requires local-loopback Ollama, exact installed models, frozen model digests, prompt/code hashes,
and unchanged sampled inputs. It can resume matching runs without repeating completed calls. It emits
counts only. Existing `report_validation` sheets now also require `label_status=complete` and explicit
`NONE` for negatives; untouched templates are not accuracy labels.

**Limits of this pilot:** OpenI was already used during rule development. Patient grouping is not
established by these report XML files. Exact text deduplication changes the sampled prevalence; this
is a distinct-text exploratory pilot, not a population estimate or an untouched patient-independent
external validation. Confidence intervals requiring independent patients are not computed. Prior AI
OpenI labels are excluded from the reference process. Model pretraining overlap also requires review,
especially for MIMIC-derived benchmarks. RadGraph/n2c2, credentialed MIMIC, multimodal localization,
Korean patient-message quality and longitudinal outcome validation remain separate tasks with their
own reference labels and access requirements. Dataset access does not itself establish whether a local
IRB determination or institutional approval is required.

The longitudinal `chart_review` output now explicitly labels its sampling frame as **conditional on
engine-detected obligations**, exposes sampled/retained stratum counts and fully excluded strata,
and sets `end_to_end_sensitivity` to null. Its existing loop-bootstrap intervals are not patient-clustered.
An independent review of eligible records, including records with no engine alert, is necessary to find
obligations the engine never opened. Conditional status performance must not be advertised as overall
follow-up detection sensitivity.

The OpenI pilot input is specifically **FINDINGS + IMPRESSION**, plus the known study type, not the full
medical record. Comparison/history sections and demographics are not inferred. Both reviewers see the
same available text; insufficient context must remain unresolved. The study cannot establish performance
when full longitudinal context or patient-specific risk is required.

### Observed pilot processing results (not accuracy)

Seed 42 selected 100 distinct texts from 3,955 XML files: 3,927 nonempty reports, 770 exact duplicates
excluded, 3,157 distinct eligible texts. Source, prompt and model hashes are preserved locally.

| System | Processed | Usable output | Reports flagged |
|---|---:|---:|---:|
| Rules | 100 | 100 | 5 |
| MedGemma 27B | 100 | 100 | 22 |
| MedGemma 4B | 100 | 100 | 89 |
| EXAONE 3.5 7.8B | 100 | 95 | 3 |

These are workload/robustness counts, not sensitivity, specificity or false-positive rates. The large
flag-count disagreement requires blinded adjudication; it is not evidence that the model with more
flags is better. Five unusable EXAONE responses remain abstentions. No clinician accuracy results
have been computed, and no prior AI-generated OpenI labels were used as reference labels.

### Extended local check and public evidence (20 October 2026)

The rules engine processed all 3,157 distinct eligible OpenI texts without an unavailable output;
95 reports were flagged. This is a processing/workload result, not an accuracy score. The three-model
comparison remains the 100-report pilot above. Both independent review sheets still have zero
completed clinician labels (0 of 200 required reviews); real-report scoring remains blocked.

On the 753 previously used synthetic report cases in `tests/report_eval/cases.json`, exact report-level
rule agreement was 635/753 (84.3%). Exact-rule sensitivity was 466/582 (80.1%) and precision was 466/503
(92.6%). Strict deadline agreement was 363/456 (79.6%) among cases with bounds and at least one exactly
matching rule. Missed obligations are excluded from that timing denominator. The harness now labels
its widened timing tolerance separately and no longer calls broad action-group agreement clinical
equivalence. These are development regression results, not independent clinical or LLM validation.

The [public evidence page](https://clinloopai.app/validation) publishes allowlisted aggregate counts
from `data/validation_status.json`. All eight requested dataset families have explicit tested/pending
status. A bounded filename scan checked 1,206 local folders without finding the additional dataset
copies; the user confirmed that access approval has not yet been obtained. No restricted dataset was
downloaded for this check. File absence in this scan is not a claim about every filesystem on the server.

HAPI's isolated synthetic round trip passed with 7 patients, 20 resources and 16 events. SMART Health IT
signed-key authentication and searches passed for 12 resource types. Epic authentication and capability
checks passed, but its isolated bulk export timed out: completed Epic ingestion remains unconfirmed.
Sandbox interoperability, processing success and clinical validity are separate claims.
