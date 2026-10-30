# Returned review: engineering corrections, 27 October 2026

Status: **local engineering draft; human clinical and software/ML review pending**.

This follow-up starts from candidate `2779baaca90370e83596e832c8e011f9442ec897`. It treats the returned Markdown/JSON review as unverified technical input. The owner could not confirm its authorship. None of its six claimed approvals were imported as human decisions, and no clinician identity or clinical sign-off was created. This work does not update the public website, merge a branch, activate ML, or restart services.

## Finding disposition

“Corrected” below describes a reproducible software behavior with synthetic regression evidence. It is not clinical approval of a rule, threshold, deadline or intended use.

| Finding | Engineering disposition | Evidence / remaining decision |
| --- | --- | --- |
| ONT-01 | Corrected hidden grace defaults and contradictory catalogue notes; anchored known month/year windows at the trigger date. | Month-end/leap-year regressions. R019 formula now states three months. Date-free helper callers retain nominal fallbacks; clinical default choices still need review. |
| FI-01 | Corrected MedicationRequest intent handling, encounter completion/context checks, typed status call, and EUS-FNA request mapping. **Clinical policy remains open.** | Synthetic FHIR regressions. A biopsy request is an issued order, not a performed procedure. Existing order-accepting rules retain their definitions until a clinical lead decides whether the task is ordering, performance, result review, or all stages. Explanations now state that distinction. |
| RAD-01 | Corrected calendar conversion, interval provenance, and loss of lung-nodule biopsy alternatives. **General alternative-action policy remains open.** | CT-or-biopsy lung tracks preserve existing R003 alternatives. Other biopsy alternatives remain visible with a human-review note; this can overtrack actions until the intended OR task is adjudicated. |
| SR-01 | Corrected same-category preference for affirmed/unambiguous evidence; accept appended reports and pass the evaluation clock. | Synthetic model stub; no inference calls. Still one suggestion per category: not comprehensive extraction of all findings. |
| TH-01 | Corrected future/unissued triggers and future incomplete evidence; conflicting duplicates become unknown. | Both input orders tested. Without source revision authority, “completed wins” could hide cancellation or correction, so conflicting copies cannot prove completion. Unknown results remain eligible for explicit human review. |
| DE-01 | Checkpoint provenance violation invalidates the whole study, removes prior scoring artefacts, and blocks scoring. | Mid-run simulated drift regression. Inventory metadata is not independent hardware/checkpoint attestation. |
| BAS-01 | Completed English labels corresponding to the Korean label map, translated the added calendar reason, and disclosed order scope. | Label parity and deadline explanation tests. Original report evidence is preserved. |
| ONT-02 | Restrict final/amended/corrected/appended to typed results, finished/fulfilled to supported encounter types. | Typed and untyped status regressions; incomplete work does not count as completed care. |
| MOT-01 | Reject cancelled/unknown and explicitly uncertain diagnoses as established AKI/AF context; require relevant urology event types. | Synthetic creatinine, AF-risk and haematuria regressions. Clinical motif thresholds remain drafts. |
| NR-01 | Retain month/year metadata and calculate actual elapsed days when a FHIR note supplies its timestamp. | January month end, leap day and range upper bound tests. Date-free text extraction alone cannot establish a calendar due date. |
| BM-01 | Report autonomous recall and non-abstention coverage separately from human-triage recall. | All-abstain test demonstrates zero autonomous recall even when triage recall is positive. |
| APP-01 | Corrected the Korean synthetic example's diagnostic wording to match the English limitation. | Source-based dashboard checks in both languages. |
| APP-02 | Corrected research-preview wording, unsupported example risk/compliance claims, IP boundary expression and unsafe step HTML interpolation. | Node regression renders attack strings as literal text; sample IP matches while a laboratory decimal is retained. This demo scrubber is not certified de-identification. |
| FS-01 | Pass the same evaluation clock through FHIR synchronization and ingestion. | Local synthetic FHIR stub test. |
| GOV-01 | Include risk scoring and basis text sources in decision fingerprints. | Modifying either source digest changes a rule's approval fingerprint. Existing approvals require re-review after such changes. |
| LD-01 | Reject invalid patient identifiers and preserve completed-late status when data quality causes abstention. | Identity and completion-status regressions. |
| MR-01 | Exclude ambiguous duplicate model names and share one canonical prompt digest. | Synthetic inventory/prompt identity tests. |
| LB-01 | Preserve ordered/planned statuses and encode simultaneous events symmetrically. | Permutation-invariance test; directed transitions only cross distinct timestamps. Existing learned weights must be retrained for the changed feature representation. |

The main regression additions are `tests/test_returned_review_regressions.py` and `tests/returned_review_dom_test.cjs`. Five older tests were updated to supply required intent/status or to expect calendar intervals and typed completion. No reference clinical dataset was relabelled to obtain passing scores.

## Evidence and handoff

The accompanying local package contains the final test log, separate Git-tool test log, seeded synthetic benchmark outputs, exact source hashes, changed-line patch and a fresh pending-review packet. The first test run is retained for transparency alongside the corrected final run. Generated synthetic records and model weights are not source-controlled.

- Final offline suite: **1,056 passed and 122 subtests passed**, with 14 skips and four pre-existing warnings. The 13 Git-dependent review-tool tests passed separately on the host; one pre-existing skip remains.
- The shared-header generator check passed for all 13 pages; the browser-engine manifest regenerated without a diff. Dashboard DOM security checks ran within the suite. Device screenshots and live provider connections were not rerun for this draft.
- The seeded 300-trajectory benchmark completed with 207 training / 93 test trajectories. All four systems score 1.0 on this reused synthetic holdout. These easy synthetic cases establish neither generalization nor a benefit from ML/DL.
- The reused 753-report fixture set still has 635 exact rule sets, 466 matched obligations, 37 extra and 116 missed expectations. Calendar-bound checks are 447/456, versus 448/456 on the earlier candidate. Reference-window adjudication is still needed; fixed-day and calendar-month expectations can differ. No labels were changed to improve the score.
- The reused 60 timelines still have 35 exact matches and 53/78 matching rule/status comparisons, with zero false closures in those fixtures only. This is not a clinical false-closure rate.
- The final pending-review checker reports **22 files, zero approvals, 22 pending**, with clinical use and runtime sign-offs both false. Exit status 2 is expected while human review is deferred.

All 22 source reviews remain pending against the current hashes. A later reviewer should inspect the full candidate diff against `aadad952cd68715e24735f0412b3034c393ed45b`, not only this follow-up. Known synthetic report/timeline disagreements still require independent adjudication; no external patient-labelled evaluation or hospital pilot was completed here.

The clinical lead must settle the two task-definition questions above, review every clinical change, and approve local validation criteria before patient-care deployment. A software/ML reviewer must independently check the study invalidation, feature representation, provenance and test evidence. Source review, clinical validation and deployment approval remain separate stages.

FHIR intent and encounter-state interpretation were checked against the official [MedicationRequest intent definition](https://hl7.org/fhir/R4/medicationrequest-definitions.html#MedicationRequest.intent) and [Encounter status definition](https://hl7.org/fhir/R4/encounter-definitions.html#Encounter.status). Engineering tests do not demonstrate conformance with all [FDA/IMDRF good machine learning practice principles](https://www.fda.gov/medical-devices/artificial-intelligence-enabled-medical-devices/good-machine-learning-practice-medical-device-development-guiding-principles).
