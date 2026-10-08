# Imaging in ClinLoop: PACS, imaging AI, outside reports and DICOM analysis

ClinLoop tracks follow-up. It does not diagnose. Images matter for follow-up in four ways, and
ClinLoop now covers each of them.

| Capability | What it answers | How |
|---|---|---|
| **PACS study labels** | "Was the follow-up adrenal CT actually done?" | Reads study labels (modality, body part, description, date, status) from the PACS over DICOMweb QIDO-RS. Never reads pixels. |
| **Imaging AI as second reader** | "The AI saw a nodule. Did the radiologist address it?" | Compares each positive AI finding with the report for the same study. If the report never mentions it, a radiologist-review loop opens (R047). |
| **Outside reports** | "The patient brought a CT report from another hospital." | Reads PDF text, or runs OCR (Tesseract, Korean and English) on scans and photos. A person checks and corrects the text. The report then goes through the same report-reading logic. |
| **DICOM analysis** | "Is this image safe to file, and does an imaging model flag anything?" | Header safety checks, a study record, and the hospital's imaging models. Any finding is only a request for a second look. |

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
CLINLOOP_LOCAL_TZ=Asia/Seoul  # DICOM times are local; the default compose file sets Asia/Seoul
```

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
- **No report yet**: nothing happens. The comparison runs once the report arrives.
- **One loop per finding**: reviewing one finding never closes another.

**Positive or not:**
- The vendor's own positive/negative flag (its operating point) is used when present.
- Otherwise ClinLoop uses `CLINLOOP_AI_THRESHOLD_<FINDING>`, else `CLINLOOP_AI_THRESHOLD`, else 0.5.

**Research-use models:** findings from products marked research-use open no loops unless
`CLINLOOP_IMAGING_RESEARCH_AI=1`.

## 3. Outside reports (PDF and OCR)

`imaging.html` → *Report from another hospital*. Filing is a two-step flow:

1. **Extract.** Text comes from the PDF's text layer, or from OCR (Tesseract `kor+eng`) for scans
   and photos. ClinLoop finds the study title, the report date (birth dates are skipped) and the
   impression section. Nothing is stored at this step.
2. **Check and file.** A person compares the title, date and impression with the original and
   corrects them, then ticks "checked against the original" and files.
   - Text a person confirms is trusted.
   - Unconfirmed text keeps a "verify against the original" flag on every loop it creates.

**Stored:** only the impression (identifiers scrubbed), the title, the date and the file's SHA-256.
The file itself is never kept.

**OCR limits (tested):**
- Clean English text read at 95% confidence.
- Korean read at 91–92%. Latin units inside Korean lines can still be misread ("2.4 cm" →
  "2.4 07").
- Units that OCR turns into look-alike digits are never guessed. This is why the human check
  exists.

## 4. DICOM analysis

`imaging.html` → *DICOM image analysis*, or `POST /api/v1/imaging/analyze`, takes one DICOM file.

**Header safety checks (no AI):**
- **Wrong patient (refused).** If the image's PatientID does not match the patient or their MRN,
  nothing is filed and the attempt is audited.
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

### What ClinLoop does *not* do

- **It does not diagnose.** No model output is shown as a diagnosis, sent to a patient, or used to
  close a loop.
- **No built-in model for CT, MRI or ultrasound.** Those need an approved vendor product (section 4,
  vendor models). Building one would need its own validation and MFDS approval.
- **No 3-D volume analysis.** One DICOM file is analysed at a time; for multi-frame files, the
  middle frame.

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

## Before clinical use

1. Connect the PACS read-only and check the body-part vocabulary against your PACS. Some sites
   leave Body Part Examined empty; for those, map study descriptions or procedure codes.
2. Choose the imaging-AI products. Use **approved** products for anything that opens loops, and set
   each product's operating point.
3. Have R047 signed off on `governance.html`.
4. Validate OCR on a sample of real outside reports, with IRB approval. Measure field accuracy
   (date, impression) per document type.
