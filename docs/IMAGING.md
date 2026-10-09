# Imaging in ClinLoop: PACS, imaging AI, outside reports, DICOM and CT analysis

ClinLoop tracks follow-up. It does not diagnose. Images matter for follow-up in the ways below, and
ClinLoop covers each of them.

| Capability | What it answers | How |
|---|---|---|
| **PACS study labels** | "Was the follow-up adrenal CT actually done?" | Reads study labels (modality, body part, description, date, status) from the PACS over DICOMweb QIDO-RS. Never reads pixels. |
| **Automatic scanning** | "Every new chest X-ray and head CT is read by our approved AI, without anyone uploading it." | Off by default. Finds new PACS studies, sends those an approved product applies to, and files the findings (section 4a). |
| **Imaging AI as second reader** | "The AI saw a nodule. Did the radiologist address it?" | Compares each positive AI finding with the report for the same study. If the report never mentions it, a radiologist-review loop opens (R047). |
| **Outside reports** | "The patient brought a CT report from another hospital." | Reads PDF text, or runs OCR (Tesseract, Korean and English) on scans and photos. A person checks and corrects the text. The report then goes through the same report-reading logic. |
| **DICOM analysis** | "Is this image safe to file, and does an imaging model flag anything?" | Header safety checks, a study record, and the hospital's imaging models. Any finding is only a request for a second look. |
| **CT organ measurement** | "The aorta measures 3.4 cm, but the report never mentions it." | A whole CT series is segmented by TotalSegmentator. ClinLoop measures the aorta and the spleen against cited limits (section 5). |
| **Vision-language model** | "Describe this image, and say which findings from the list it shows." | MedGemma or a similar model on the hospital's own server: findings from a fixed list only (section 6). |
| **Patient knowledge graph** | "What has happened to this patient, and what is still missing?" | Every event the engine read, and every obligation between them, on one time axis (section 7). |

All four become standard FHIR R4 resources, and so share ingestion, rules, governance, audit and
the worklist:
- a study becomes an `ImagingStudy`;
- an AI output becomes an `Observation` with the product as `device`;
- an outside report becomes a `DiagnosticReport`.

## 1. PACS study labels (no diagnostic approval needed)

```
CLINLOOP_PACS_DICOMWEB=https://pacs.hospital.local/dicom-web   # QIDO-RS base URL
CLINLOOP_PACS_TOKEN=…                                          # optional bearer token
CLINLOOP_PACS_ID_SYSTEM=…   # FHIR Patient.identifier system holding the PACS PatientID (default: the MR identifier)
CLINLOOP_PACS_MATCH_FHIR_ID=1 # only if the PACS uses FHIR ids as PatientID (otherwise patients without an MRN are not looked up)
CLINLOOP_LOCAL_TZ=Asia/Seoul  # DICOM times are local (default Asia/Seoul; "UTC" if the PACS stores UTC)
```

**Patient check.** Every study the PACS returns must carry the PatientID that was queried;
otherwise it is skipped. IDs containing DICOM wildcards (`*`, `?`) are never queried.

**What is read.** For every patient evaluated, ClinLoop queries `/studies?PatientID=…` and
`/studies/{uid}/series`. It reads Study/Series Description, Modalities in Study, Body Part
Examined, Study Date/Time and Accession.
- Patient names returned by the PACS are discarded.
- A follow-up study closes a loop only if its body region covers the region the follow-up was for.
  For example, an `ABDOMEN` CT covers the adrenals, while a `HEAD` CT does not.
- A study that is only `registered` (booked) is not counted.

**If the PACS is unreachable.** This is recorded as a warning. Follow-ups may then look missing,
which means more alerts, never fewer.

**Works with:** Orthanc, dcm4chee, Sectra, Infinitt and Google Cloud Healthcare, plus any FHIR
server that exposes `ImagingStudy`.

## 2. Imaging AI as a second reader (R047)

An approved product's results arrive in one of two ways. The hospital's integration engine can POST
them to `/api/v1/imaging/ai-results` as a FHIR Bundle of `Observation`s or as the product's DICOM
SR. Alternatively, ClinLoop's own model runner produces them (section 4). Then:

- **The report mentions the finding**, confirming or refuting it ("no nodule"): nothing happens,
  because the radiologist decided.
- **The report does not mention it**: R047 opens, asking a radiologist to review. The review is due
  within 1 day for pneumothorax, free air or intracranial haemorrhage, and within 7 days otherwise.
- **A later addendum addresses it**: the loop closes. A clinician can also close it with evidence.
- **No report yet**: the comparison runs once the report arrives. The exception is a **critical**
  finding (intracranial haemorrhage, pneumothorax, free air): the unreported study must be read now
  (**R057**, within 60 minutes by default; `CLINLOOP_AI_CRITICAL_READ_MINUTES`). This is worklist
  triage, the purpose of approved triage products. The first report of the study closes R057, and
  R047 then checks that the report addressed the finding. A study already reported when the AI
  result arrived raises no R057, and there is one R057 per study however many critical findings it
  has.
- **One loop per finding**: reviewing one finding never closes another.

**Positive or not:**
- The vendor's own positive/negative flag (its operating point) is used when present.
- Otherwise ClinLoop uses `CLINLOOP_AI_THRESHOLD_<FINDING>`, else `CLINLOOP_AI_THRESHOLD`, else 0.5.

**Which report is the study's report:**
- Matched by DICOM StudyInstanceUID, or by the same ImagingStudy reference, even when the hospital
  uses its own ImagingStudy ids or absolute URLs.
- If neither side names its study, the first report *after* the study whose body region covers the
  finding is used. A report written before the study never counts.
- A finding with no study link and no body region (e.g. a fracture AI result without a body part)
  is not compared, because ClinLoop cannot tell which report it belongs to.

**Counted as "addressed" only with specific wording.** None of these addresses the AI finding:
- "no osseous lesion" for a lung nodule;
- "pericardial effusion" for a pleural effusion;
- "vertebral collapse" for atelectasis;
- "scalp hematoma" for an intracranial haemorrhage.

**Duplicates:** the same finding on the same study, from two sources (vendor feed and upload) or a
re-analysis, is reviewed once.

**Research-use models, or no stated approval:** findings from products marked research-use, or
with no stated regulatory status, open no loops unless `CLINLOOP_IMAGING_RESEARCH_AI=1`.

## 3. Outside reports (PDF and OCR)

`imaging.html` → *Report from another hospital*. Filing is a two-step flow:

1. **Extract.** Text comes from the PDF's text layer, or from OCR (Tesseract `kor+eng`) for scans
   and photos. ClinLoop finds the study title, the report date (birth dates are skipped) and the
   impression section. Nothing is stored at this step.
2. **Check and file.** A person compares the title, date and impression with the original and
   corrects them, then ticks "checked against the original" and files.
   - Text a person confirms is trusted.
   - Unconfirmed text keeps a "verify against the original" flag on every loop it creates.

**Stored:**
- the impression, with identifiers removed: resident numbers, phone numbers, MRNs, labelled names
  and birth dates, and the patient's own name from their record. Dates, sizes and clinical words
  are never changed;
- the title, reduced to its clinical words ("CT Chest - Hong Gil-dong" → "CT Chest");
- the date and the file's SHA-256.

The file itself is never kept.

**Report date:**
- A date labelled as the exam date wins; otherwise the latest date in the document is used
  (comparison dates are earlier).
- Birth dates are excluded, including in table layouts.
- An ambiguous date like 05/06/2026 is never guessed.

**OCR limits (tested):**
- Clean English text read at 95% confidence.
- Korean read at 91–92%. Latin units inside Korean lines can still be misread ("2.4 cm" →
  "2.4 07").
- Units that OCR turns into look-alike digits are never guessed. This is why the human check
  exists.

## 4. DICOM analysis

`imaging.html` → *DICOM image analysis*, or `POST /api/v1/imaging/analyze`, takes one DICOM file.

**Header safety checks (no AI):**
- **Unknown patient (refused).** The patient must exist in ClinLoop's record, and the id must be a
  valid FHIR id.
- **Wrong patient, or no PatientID (refused).** If the image's PatientID is missing or does not
  match the patient's FHIR id or MRN, nothing is filed and the attempt is audited.
- **Not a DICOM file (refused).**
- **Secondary capture or derived image**, for example a screenshot.
- **Identifiers burned into the pixels.**
- **Missing body part or date.**
- **Modality differs** from the one expected.

**Study record:** the image's study closes follow-ups exactly as a PACS study would. This is useful
for sites without DICOMweb.

**Imaging models:**
- **Selection:** `CLINLOOP_IMAGING_MODELS=txrv` turns on the built-in model, and
  `CLINLOOP_IMAGING_MODELS_CONFIG` adds vendor models.
- **Built-in research model `txrv`:** TorchXRayVision DenseNet-121, "all" weights (Cohen et al.,
  MIDL 2022).
  - Frontal chest radiographs only, with 18 findings. Research use only; not a medical device.
  - It uses the authors' own DICOM preprocessing, so it sees what it was trained on.
  - Install: build the image with `--build-arg WITH_IMAGING_AI=1`, which bakes the weights in so no
    internet is needed. Or run `pip install torch torchxrayvision` and point `CLINLOOP_MODEL_DIR` at
    the weights.
- **Vendor models, any modality (CT, MRI, ultrasound, mammography):**
  - Add the product's on-premise inference endpoint to a JSON file named by
    `CLINLOOP_IMAGING_MODELS_CONFIG`.
  - ClinLoop POSTs the DICOM file and reads `{"findings": [{"label", "score", "positive"?}]}`.
  - Example entry:

    ```json
    [{"name": "Vendor CXR AI", "version": "3.1", "url": "http://ai-gateway.hospital.local/cxr/analyze",
      "token_env": "VENDOR_TOKEN", "modalities": ["CR", "DX"], "body_regions": ["chest"],
      "regulatory": "MFDS approved (Class II), certificate no. …", "threshold": 0.15,
      "label_map": {"nodule": "Nodule"}}]
    ```

**Storage:** pixel data is never stored. A preview is returned to the reviewer only.

Approved vendor products: see [`VENDOR_IMAGING_AI.md`](VENDOR_IMAGING_AI.md) and the placeholder
template [`imaging_models.example.json`](imaging_models.example.json).

## 4a. Automatic scanning of new PACS studies (off by default)

When the hospital turns it on, ClinLoop finds new studies in the PACS and sends each one to the
approved imaging-AI products that apply to it. Nobody uploads anything. Findings go through the same
second-reader comparison as before: when the radiologist's report arrives and does not address a
finding, a radiologist-review loop opens (R047, 1 day for critical findings, 7 days otherwise).

```
CLINLOOP_IMAGE_SCAN=1                       # turn it on (needs CLINLOOP_PACS_DICOMWEB)
CLINLOOP_IMAGING_MODELS_CONFIG=/config/imaging_models.json   # the approved products
CLINLOOP_FHIR_BASE=…                        # to match each study's PatientID to one patient
CLINLOOP_PACS_ID_SYSTEM=…                   # REQUIRED: FHIR identifier system of the PACS PatientID
CLINLOOP_LOCAL_TZ=Asia/Seoul                # the hospital's time zone (DICOM dates and times are local)
CLINLOOP_IMAGE_SCAN_MINUTES=10              # interval
CLINLOOP_IMAGE_SCAN_LOOKBACK_DAYS=2         # how far back to look for new studies
CLINLOOP_IMAGE_SCAN_MODALITIES=CR,DX,MG,CT,MR,US
CLINLOOP_IMAGE_SCAN_MAX_STUDIES=50          # studies analysed per run; the rest wait for the next run
CLINLOOP_IMAGE_SCAN_SETTLE_MINUTES=5        # minimum age of a study before it is read
CLINLOOP_IMAGE_SCAN_MAX_IMAGES=4            # images per series sent to a single-image product
CLINLOOP_IMAGE_SCAN_MAX_SERIES_MB=600       # largest series sent to a whole-series product
CLINLOOP_IMAGE_SCAN_RESEARCH=1              # also run research models, in shadow mode (default off)
```

**What happens to each study**

1. **Found.** The PACS is asked (QIDO-RS) for studies acquired in the look-back window, by modality.
   - Paging runs until an empty page, and stops if the PACS returns the same page again.
   - Each modality has its own cap, so a busy X-ray list can never crowd out CT or MRI.
   - A list cut short is reported.
2. **Complete.** A study is read only once its image count is the same on two runs. A half-arrived
   study is never read. Images that arrive after a study was read (a late series) re-open it.
3. **Matched to one patient.** The study's PatientID must match exactly one patient on the FHIR
   server, by the identifier system in `CLINLOOP_PACS_ID_SYSTEM`.
   - **Required:** without it, another site's MRN with the same digits on a shared FHIR server could
     match, so scanning does not run.
   - No match, or two patients: the study is not analysed and is listed for a person to check. A
     patient is never guessed.
4. **Checked against the products.** Only series that an enabled product applies to (modality and
   body part) are considered. When the PACS does not return the body part in its series list, one
   image header is read (metadata, no pixels). Localizers, dose reports, structured reports and
   screenshots are skipped. If no product applies, no image is retrieved.
5. **Retrieved and checked.** Images are retrieved over WADO-RS, held in memory and never stored.
   - Every image's PatientID must be this patient's MRN in the configured system.
   - One image of another patient stops the whole study: nothing is sent and nothing is filed.
   - Vendor products receive the file as stored, whatever its compression; ClinLoop need not decode
     it.
6. **Analysed.**
   - **Single-image products** (chest X-ray, mammography) get each view, up to the image limit.
   - **Whole-series products** (CT, MRI; `"input": "series"` in the configuration) get every image
     of the series in one `multipart/related` request.
   - A product must answer with a `findings` list in which each finding has a numeric score or a
     positive flag. Any other answer (an asynchronous job id, an error body) is a failure, not "read,
     nothing found".
7. **Filed.** The study (`ImagingStudy`) and each positive finding (`Observation`) are filed, and
   the patient is re-checked. A critical finding on a study with no report yet opens R057 (read it
   now).

**Only approved products run automatically.** A product whose regulatory field is empty or says
research use is not run, unless `CLINLOOP_IMAGE_SCAN_RESEARCH=1` is set for shadow-mode evaluation.
Even then its findings open no loops unless `CLINLOOP_IMAGING_RESEARCH_AI=1`.

**The ledger.** Every study is recorded once, without pixels and without the PACS PatientID:

| Status | Meaning | Retried? |
|---|---|---|
| `pending` | Waiting for all its images to arrive | Yes, next run |
| `scanned` | Analysed by every product that applies; findings filed | Only if more images arrive |
| `no_model` | No enabled product applies | Only if more images arrive |
| `unmatched` | PatientID matched no patient, or more than one | Yes, up to 5 times, then listed |
| `refused` | A safety check failed (wrong patient, mixed series) | No: a person checks it |
| `failed` | A product or the PACS failed; findings from products that did read it are filed | Yes |
| `abandoned` | The study itself failed 5 times (e.g. a corrupt file) | No: raises an alarm |

**Retries:**
- A study no product could read is recorded as `failed`, never as "scanned, nothing found".
- **Outages cost no retries.** If the FHIR server is down, or three studies in a row fail on the PACS
  or a product, the run stops and the studies wait for the next run.
- A study that itself keeps failing is `abandoned`. The monitor then reads **ATTENTION**, as it does
  when the last run's study list was cut short.

**Monitoring.** `GET /api/v1/imaging/scan/status` and the panel on `imaging.html` show whether
scanning is on, the products that may run, the last runs, the counts by status and the studies that
need a person. Admins can run a scan now (`POST /api/v1/imaging/scan/run`). Scan runs are monitored
apart from the FHIR data feed, so a working image scanner can never make a dead record feed look
healthy. A database lease ensures only one scan runs at a time across processes: the API's
background loop, several API workers, or the command line
(`python -m src.clinloop_engine.imaging_scanner --once`).

**Independent review.** A reviewer who had not written the code found 10 defects and reproduced 9;
all are fixed and each has a test:
- a study read while its images were still arriving was closed for good;
- an outage used up every study's retries silently;
- a busy X-ray list could hide CT and MRI, and a PACS ignoring `offset` hung the scanner;
- a product that failed on a study left it "scanned";
- another site's MRN with the same digits could match;
- the container's UTC clock was used instead of the hospital's time zone;
- any HTTP 200 counted as a clean read;
- products were skipped when ClinLoop could not decode the compression;
- a large image used about 11× its size in memory;
- two processes could scan at once.

**Tested against a real DICOMweb server.** Orthanc 1.12 with its DICOMweb plugin, synthetic
studies and a stand-in vendor endpoint were used.
- **Chest X-ray:** one image was sent to the X-ray product with its token.
- **Head CT:** all 6 slices went to the CT product in one request.
- **Other studies:**
  - the unknown patient was held back;
  - the knee MRI was skipped without retrieving images;
  - a study acquired minutes earlier waited for the next run.
- **Result:** both findings were absent from the stand-in reports, so two radiologist-review
  loops opened. A second run re-sent nothing.

This run found two defects that the unit tests had missed; both are fixed and tested:
- Orthanc ignored the comma-separated field list, so no study description came back.
- Orthanc does not return the body part in series queries, so studies would have been skipped as
  "no model applies".

## 5. CT organ measurement (3-D, research use)

`imaging.html` → *CT organ measurement*, or `POST /api/v1/imaging/ct-organs`, takes one CT series:
a `.zip` of its DICOM files, or a NIfTI volume.

**Reading the series:**
- The slices are sorted by position (not by file order) and converted to Hounsfield units.
- A zip with more than one patient's images is refused. If the zip holds several series, the
  largest is used and a note says so.
- A series that is not CT, has fewer than 20 slices, or has duplicate slice positions is refused.
- A NIfTI volume has no PatientID, so its measurements are shown but never filed.

**Segmentation.** TotalSegmentator 2 (Wasserthal J et al., *Radiology: AI* 2023; Apache-2.0)
segments 117 structures.
- It is research use only and not a medical device.
- By default the 3 mm model runs, which takes about 20 s on a CPU. `CLINLOOP_CT_SEG_FAST=0` runs
  the 1.5 mm model, which is more precise but takes minutes.
- Each CT runs in its own short-lived process, with a time limit (`CLINLOOP_CT_SEG_TIMEOUT`,
  default 900 s). nnU-Net's internal multiprocessing hung on the second CT when called inside the
  web server; this was found in the live run and is why.
- TotalSegmentator's default usage statistics, sent to its authors' server, are switched off
  before every run.

**Measurements (explicit, cited limits):**

| Measurement | How | Flagged when |
|---|---|---|
| Aorta | Short-axis diameter of every axial cross-section, from an ellipse fit. Oblique cuts (long axis > 1.6 × short axis, e.g. the arch) are skipped. A slice is thoracic if it contains lung or heart. | Abdominal ≥ 3.0 cm (SVS 2018 definition of AAA); thoracic ≥ 4.0 cm (ACR incidental-findings white paper) |
| Spleen | Craniocaudal length | > 13 cm, and only if the whole spleen is inside the scan |
| Every organ shown | Volume (ml), length, and whether it is fully in the scan | Not flagged |

- A value within one voxel of its limit is marked *borderline*.
- An organ cut off by the edge of the scan is never sized.
- Abdominal and thoracic dilatation on one CT make one finding, so one review.

**What happens to a flagged measurement.** It becomes an imaging-AI Observation with the
measurement as a component (never as a probability), compared with the report of the same CT
(R047).
- These count as addressing it: "AAA", "aneurysm", "ectatic", "normal caliber abdominal aorta",
  "the aorta measures 2.9 cm", "대동맥류".
- "No acute abnormality" does not address it.
- Because TotalSegmentator is research use, R047 opens only with `CLINLOOP_IMAGING_RESEARCH_AI=1`.

**What it deliberately does not do.**
- The organs a CT covers are listed, but a measurement never closes a loop. A chest CT that happens
  to include the adrenals does not close an adrenal follow-up; that stays a radiologist's call.
- No diagnosis is made, and nothing is sent to the patient.

**Install:**
- Docker: `docker build --build-arg WITH_CT_SEGMENTATION=1`, which bakes the 3 mm weights into the
  image.
- Or `pip install TotalSegmentator`, with the weights in `TOTALSEG_WEIGHTS_PATH`.
- Then set `CLINLOOP_IMAGING_MODELS=totalseg`.

## 6. Vision-language model (research use)

Add `vlm` to `CLINLOOP_IMAGING_MODELS`. It runs on any modality, one image at a time, on the
*DICOM image analysis* panel.

```
CLINLOOP_VLM_URL=http://ollama:11434        # the hospital's own Ollama, or an OpenAI-compatible server (vLLM, llama.cpp)
CLINLOOP_VLM_MODEL=medgemma-4b-it           # whatever name the server gives the model
CLINLOOP_VLM_API=ollama | openai            # default: ollama for port 11434
CLINLOOP_VLM_REGULATORY=…                   # default "Research use only — not a medical device"
```

**Safeguards against the known failure modes of generative models:**
- **Images stay inside the hospital.** The image goes only to a server whose address is private or
  localhost. A public URL is refused, unless `CLINLOOP_VLM_ALLOW_REMOTE=1`.
- **Fixed vocabulary.** The model must answer with findings from ClinLoop's fixed list. Any other
  label ("lung cancer stage IV") is dropped.
- **Body region must fit.** A finding for another body region, such as a pneumothorax on a head CT,
  is dropped.
- **Bad answers file nothing.** An unreadable answer files no findings. A confidence outside 0–1 is
  ignored.
- **Free text is not filed.** The free-text description is shown to the reviewer, marked as
  unverified AI text, and never stored in the record.
- **Research use.** Findings open review loops only with `CLINLOOP_IMAGING_RESEARCH_AI=1`.

**Not yet run on real weights.** The adapter is tested against a stand-in server that speaks the
Ollama and OpenAI formats. MedGemma's weights could not be downloaded in the build environment
(Hugging Face and ollama.com are blocked there), so the model itself has not been run here.

## 7. Patient knowledge graph

`patient.html?patient=<id>`, or `GET /api/v1/patients/{id}/graph` (viewer role), is reachable from
each worklist loop.

**Nodes:**
- Every clinical event the engine read for the patient, placed in lanes on a time axis: diagnoses
  and risk factors, lab values and pathology, orders and referrals, medications, appointments and
  communication, imaging studies and procedures, radiology reports, and imaging AI.
- Every active Condition is now read as a diagnosis node. Only HCC-risk diagnoses carry an
  obligation of their own (R027).

**Hyperedges (obligations).** Each runs from the event that created the obligation to the
follow-up(s) that fulfilled it.
- When the follow-up is missing, the hyperedge runs to a dashed "missing" node at its deadline,
  in the lane where the follow-up should appear: for example "CT · adrenal" by 2026-04-29.
- Colour shows the status: closed on time, closed late, or open.
- Each hyperedge carries the evidence chain and the loop's worklist state.

**Edges:**
- *same study*: the study, its report and its AI findings;
- *same record*: several facts read from one FHIR resource;
- *derived from*: an R047 review created from an AI finding.

The graph comes from the same temporal hypergraph that opens the loops, so what is drawn is
exactly what the engine decided.

### What ClinLoop does *not* do

- **It does not diagnose.** No model output is shown as a diagnosis, sent to a patient, or used to
  close a loop.
- **No approved CT, MRI or ultrasound model is built in.**
  - CT measurement and the vision-language model are research use.
  - Findings that should open loops in routine care need an approved vendor product (section 4).
  - Building one would need its own validation and MFDS approval.
- **2-D analysis reads one image.** One DICOM file is analysed at a time; for multi-frame files,
  the middle frame. 3-D analysis is CT only (section 5).

## Live run (synthetic patients, 2026-10-08)

- **PACS.** A stand-in DICOMweb server answered QIDO-RS for patient RP-18: an `ABDOMEN` CT
  "ADRENAL PROTOCOL" on 2026-03-25. ClinLoop closed RP-18's adrenal follow-up, which until then had
  only a head CT, and the evidence chain shows the region match. Active loops dropped from 26 to 25.
- **DICOM and model.** A public research chest radiograph (not committed) was wrapped as DICOM for a
  synthetic patient. The radiologist's report for that patient said "No acute cardiopulmonary
  abnormality".
  - TorchXRayVision flagged nodule/mass (0.70), lung opacity (0.59) and fracture (0.52) above its
    0.5 operating point.
  - With research findings allowed for the demo, three R047 review loops opened, one per finding.
  - Three alerts from one normal-reported image show why research-model findings are **off by
    default**.
- **Korean outside report.** A scanned 판독지 was read at 91.5% OCR confidence; 복부 CT and
  2026-04-03 were found.
  - A person corrected "2.4 07" to "2.4 cm" and confirmed. Filing opened the radiologist's
    "3개월 후 추적 CT 권고" as R030 (adrenal region).

## Live run: CT, vision-language model and graph (synthetic patient CT-DEMO-01, 2026-10-08)

**CT, real model, real code.**
- TotalSegmentator 2.18 (3 mm) on TotalSegmentator's own public sample CT, run on CPU through the
  API:
  - liver 1062 ml, spleen 260 ml, kidneys 99 and 108 ml;
  - abdominal aorta 2.2 cm: no finding.
- The same CT entered as NIfTI and as a DICOM series gave an identical volume and orientation.
- **Aneurysm phantom.** A 4.4 cm aorta was painted into the lower slices of the same CT.
  - It was measured at **3.3 cm**, which is above the 3.0 cm limit and marked borderline. The
    phantom has soft-tissue density, so the model segmented only part of it.
  - This under-measurement is why a measurement only ever asks for a review and never closes or
    rules anything out.
- The patient's report said "No acute intra-abdominal abnormality. Liver unremarkable", so an R047
  review opened.
- Three CTs in a row took 21–24 s each (after the subprocess fix described in section 5).

**Vision-language model (stand-in server).**
- The request reached the local server with the image and the fixed vocabulary.
- An invented label ("brain tumour") was dropped.
- The description was shown and not filed.

**Graph.** The demo patient showed 26 events and 10 obligations on `patient.html`: 5 open (R003
overdue: the follow-up CT was a no-show) and 5 closed. It was checked in Chromium at 1280 px and at
390 px wide, with no horizontal page scroll.

## Independent review

A separate reviewer ran edge cases through the imaging code and confirmed 15 problems; all are
fixed and now tests (`TestIndependentReviewImaging`, `TestImagingAPISafety`):

- **Report matching:**
  - reports linked to the hospital's own ImagingStudy id were never compared;
  - a report from before the study could count;
  - a chest report's "no rib fracture" addressed a wrist fracture finding;
  - unrelated wording counted as "addressed".
- **Duplicates:** the same finding from two sources opened two review loops.
- **PACS:** a study of another PatientID could be filed.
- **Outside reports:**
  - a birth date in a table, or an earlier comparison date, became the report date;
  - a sentence starting with "Comparison" cut the impression short;
  - the old scrubber changed "6개월 후" and image numbers;
  - names in titles were stored.
- **Integrity:**
  - a reused file or vendor id could attach one patient's record to another;
  - injected or unknown patient ids were accepted.
- **Robustness and privacy:**
  - invalid dates, multi-frame colour ultrasound, text scores and non-DICOM files could crash
    analysis or create junk records;
  - DICOM SR scores were given to the wrong finding;
  - a hash of the MRN was returned.

## Before clinical use

1. Connect the PACS read-only and check the body-part vocabulary against your PACS. Some sites
   leave Body Part Examined empty; for those, map study descriptions or procedure codes.
2. Choose the imaging-AI products. Use **approved** products for anything that opens loops, and set
   each product's operating point.
3. Have R047 signed off on `governance.html`.
4. Validate OCR on a sample of real outside reports, with IRB approval. Measure field accuracy
   (date, impression) per document type.
