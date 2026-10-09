# Connecting an approved imaging-AI product

ClinLoop does not diagnose. An approved imaging-AI product is a second reader: if it flags a finding
that the radiologist's report of the same study never mentions, ClinLoop opens a radiologist-review
loop (R047). Approved products are the only route by which imaging AI opens loops by default.
Research models (TorchXRayVision, TotalSegmentator, vision-language models) need
`CLINLOOP_IMAGING_RESEARCH_AI=1`.

No vendor is endorsed or pre-configured here. `docs/imaging_models.example.json` is a template with
placeholders. Every value in angle brackets comes from the product's own documentation, its
regulatory certificate, and the hospital's integration team.

## Two ways to connect

| | ClinLoop calls the product (pull) | The product sends results (push) |
|---|---|---|
| **When** | A person analyses an image on `imaging.html`, or automatic scanning sends every new PACS study ([`IMAGING.md`](IMAGING.md) §4a) | The hospital's integration engine forwards every result |
| **How** | ClinLoop POSTs the DICOM file to the product's on-premise endpoint | `POST /api/v1/imaging/ai-results` with a FHIR Bundle of `Observation`s or the product's DICOM SR |
| **Set up** | `CLINLOOP_IMAGING_MODELS_CONFIG=/config/imaging_models.json` | An admin API token for the integration engine |
| **Best for** | A pilot, or products with a synchronous API | Production: every study, no manual step |

### Pull: the configuration file

One entry per product (see the template):

| Field | Meaning |
|---|---|
| `name`, `version` | As on the regulatory certificate. Shown on every finding and in the audit log. |
| `url` | The product's on-premise inference endpoint. ClinLoop POSTs `application/dicom` and expects `{"findings": [{"label", "score", "positive"?}]}`. If the product's API differs, put a small adapter in the integration engine. |
| `token_env` | Name of the environment variable that holds the bearer token. Never the token itself. |
| `modalities`, `body_regions` | The product runs only on matching images (intended use). |
| `input` | `"instance"` (default): one DICOM file per request. `"series"`: the whole series in one `multipart/related` request, for CT and MRI products. |

The product receives the DICOM file as stored (any transfer syntax). It must answer with
`{"findings": [...]}`, where every finding has a `label` and a numeric `score` or a `positive` flag.
Anything else (an asynchronous job id, `probability` in place of `score`, an error body) is a
failure that is retried, never a clean read.
| `regulatory` | For example `MFDS approved (Class II), certificate no. …`. If empty, or if it says research use, the product's findings open no loops unless research AI is allowed. |
| `threshold` | The vendor's operating point, used when the product sends a score without a positive/negative flag. Use the value from the product's validation, not 0.5. |
| `label_map` | Vendor label → ClinLoop wording ("Nodule", "Pneumothorax", "Intracranial haemorrhage", …). The finding types ClinLoop compares with reports are listed in `imaging_fhir.AI_FINDINGS`. |

`GET /api/v1/imaging/models` shows each configured product, its regulatory status and whether it is
ready.

### Push: FHIR or DICOM SR

- **FHIR:** an `Observation` per finding, with `device.display` = product and version, `code.text` =
  the finding, `interpretation` POS/NEG (or a probability in `valueQuantity`), `bodySite`, and
  `derivedFrom` → the `ImagingStudy` or its StudyInstanceUID (`urn:oid:…`). Send the regulatory
  status in the request's `regulatory` field.
- **DICOM SR:** ClinLoop reads the findings and their scores from the SR's content tree. The SR's
  PatientID must match the patient.

## Before go-live, for each product

1. **Regulatory status:** check the certificate number against the MFDS medical device database, and
   check that the intended use covers the modality, body part and population.
2. **Label map:** run 20–50 studies from the hospital's PACS through the product and check that every
   label it emits maps to the intended ClinLoop finding. A label that maps to nothing is shown but
   never compared with a report.
3. **Operating point:** use the vendor's validated threshold. Measure how many R047 loops open per 100
   studies in shadow mode before going live.
4. **Sign-off:** R047 is signed off on `governance.html`, like every other rule.
