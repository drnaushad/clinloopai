# Production readiness: what is in place, what is not

ClinLoop is a research candidate (core profile by default), not yet validated at a hospital. This page lists what a hospital pilot needs, what the code already
does about each need, the design decisions behind it, and what is still missing. It is a working
document for the team, the hospital's IT and privacy officers and its regulatory adviser. It is not
legal or regulatory advice.

## 2026-10-27 local research candidate and review provenance

Version `2026-10-27.research1` was prepared and uploaded to a separate preview branch; publication to main and the live website was not completed. The corrected research2 candidate includes the subsequent engineering and review-provenance corrections. Independent source review is deferred, with zero human approvals. The 22-file engine/ML/release packet now also covers the review-tool provenance correction, for 23 pending source files. Candidate pages display research-preview status; this does not describe a newly deployed public release. Offline learned comparators do not become clinical prediction services. No shared backend, GPU, model service or hospital integration was restarted or enabled.

The supplied Gemini conversation duplicates the returned source review and is AI-generated review input, not evidence of an identifiable human's approval. Review schema v2 requires a human or AI-assisted-human origin, explicit personal-review and independence attestations, and a reference to identity/qualification verification held by the responsible team. The checker validates field presence and source binding; it does not authenticate a person or verify a licence. AI findings remain useful engineering input outside the human approval record. All new review records default to pending.

The [GMLP evidence and gap tracker](reviews/gmlp-gap-assessment-20261027.json) maps the candidate to all ten 2025 IMDRF principles linked by FDA. Its statuses are engineering assessments, not certification or a regulatory determination. Representative clinical evaluation, reference adjudication, clinician workflow testing and operational monitoring evidence remain incomplete.

Historical checks below retain their original dates and scope. The GPU mismatch note below is a historical finding, not a current hardware diagnosis. See the current release section on the Validation evidence page for research results and unresolved disagreements.

## 2026-10-26 integrated completion candidate — historical local state

The previously tested clinical corrections and research comparators are combined with the
published shared-header interface in a separate checkout. The existing shared server, production
registry, website and GPU configuration are unchanged. This is software integration, not clinical
approval. No clinician signatures, validation labels or hospital approvals have been invented.

- Structured trajectories: compare the deterministic engine with fitted logistic regression,
  gradient-boosted trees and a small `(32, 16)` neural network on the same seed-42 group holdout.
  Training preprocessing sees training records only; no model weights or patient risk service are served.
- Unstructured text: the existing application-transport evaluator now uses 24 developer-authored
  English/Korean synthetic fixtures across six text categories. It measures strict source-sentence,
  assertion, follow-up and timing agreement; duplicate/extra findings count against precision, and
  rejected/unrun cases stay in the recall denominator. Breakdowns do not imply specialty validation.
- Checkpoint identity: the evaluator requires an installed checkpoint digest before inference and
  checks it again at the end. Changed identity withholds comparison metrics. This cannot attest a
  malicious server or detect every intervening replacement that is reverted before the final check.
- Reference review: the local dataset scorer rejects modified source context, malformed prediction
  types/foreign keys, mismatched input provenance and non-finite deadline bounds. Reviewer names are
  normalized to prevent trivial duplicate identities; identity strings are not licence verification.
- Clinical changes retain the review requirements below. Images, OCR, waveforms, new languages,
  fine-tuning and graph neural networks need separate datasets and evaluations. The small event
  neural network is not an image model, LLM or graph neural network.

**Local runtime finding (2026-10-26):** the current GPU query returned an NVIDIA driver/NVML
version mismatch. Ollama answered its metadata endpoints. The initial tags entries listed completion only, but
the detailed `/api/show` check declared completion and vision for both installed MedGemma
checkpoints; EXAONE declared completion. No inference, GPU repair, driver install, reboot or
shared-service restart was attempted. Declared capability is not measured image accuracy.

To finish the clinical release, the responsible clinicians must review the exact clinical diff,
validate hospital status mappings and source deadlines, then approve new rule fingerprints.
Before real-patient use, establish independently annotated report and longitudinal test cohorts,
pre-specified performance/uncertainty targets and subgroup analysis, hospital privacy/security
and applicable regulatory assessment, then a supervised silent pilot. Restricted datasets still
require approved access. Synthetic fixtures and FHIR sandbox connectivity cannot substitute.

## 2026-10-25 safety correction — local clinical draft, not released

The code candidate addresses confirmed technical failures, not every possible medical limitation.
All changed clinical logic must be reviewed line by line under `AGENTS.md` before publication or use.
No patient records, model downloads, shared services or credentials were changed for this correction.

| Confirmed gap | Candidate behavior | Review and operational consequence |
| --- | --- | --- |
| Missing/unmapped follow-up status could close a loop | Affirmative completion allowlist, resource-specific FHIR mapping, unknown-status count warning; unknown direct events remain open | Validate every hospital interface's status vocabulary. Reevaluate prior engine-resolved tasks with uncertain evidence; do not assume a code update alone repairs persisted records. |
| Arrival/check-in counted as a completed visit | Only fulfilled appointments satisfy the tracked visit; orders stay distinct from performed procedures | Validate what the source system means by fulfilled. A fulfilled appointment is not evidence that every downstream result was reviewed. |
| EUS request mapped as a performed endoscopic ultrasound | Request is an imaging order, regardless of active/completed request status | A performed procedure needs its own evidence. Review R042 matching. |
| Scheduling grace silently extended clinical deadlines | No extra grace in report, guideline or clinician-note clocks; whole report calendar months/years and selected calendar-based guideline intervals preserve anniversaries | Some formerly on-time tasks become late. Confirm local scheduling policy separately; it must not alter or conceal the source deadline. Fractional months and note-reader month intervals still use approximate day conversion. |
| Rule approval survived a change in shared matching/ingestion code | Rule fingerprints now bind all shared decision sources | Existing approvals become stale. Re-review and approve the candidate fingerprint; do not copy old approvals. |
| "All follow-ups completed" could imply completed care | Closed output says only the tracked obligation is satisfied; English/Korean basis states the scope | Referral, order, performed study, result review, patient communication and overall care are different milestones. The candidate does not add unvalidated care-pathway rules. |
| HSIL example asserted a universal mandatory biopsy deadline | Risk-assessment context and proposed local 30-day tracking target are explicit | A clinician must determine the correct ASCCP risk-based pathway; no treatment algorithm was added. |

Before any rollout: review the clinical diff, validate source mappings, run a shadow reevaluation against
a backed-up local registry, review newly reopened/late tasks with the responsible clinicians, then
approve the new fingerprints. No automatic production migration or reingestion was executed.

Still required outside this software correction: independently annotated, patient-separated testing
for each intended report type/language/model; a clinician-led silent pilot; hospital privacy/security
and regulatory assessment; approved dataset access; and demonstrated ownership, handover and escalation
in the actual hospital. Sandbox connectivity, synthetic test passes and local LLM availability do not
satisfy those requirements. PDF/OCR, medical images and waveform interpretation need their own validated
workflows. The public site remains synthetic-only.

FHIR mapping references: [event status](https://hl7.org/fhir/R4/valueset-event-status.html),
[appointment status](https://hl7.org/fhir/R4/valueset-appointmentstatus.html),
[request status](https://hl7.org/fhir/R4/valueset-request-status.html).
Cervical management context: [ASCCP expedited-treatment guidance](https://www.asccp.org/clinical-practice/practice-pearls/tips-for-best-practice-on-role-of-expedited-treatment/).

## 2026-10-25 research ML/neural extension — local draft

The benchmark now fits logistic-regression, gradient-boosted-tree and two-hidden-layer neural comparators and tests
them with the deterministic engine on a shared synthetic patient/duplicate-group holdout. Legacy
reference-label EMR/LLM simulators are excluded from measured comparisons. This adds an offline research
capability, not a clinical prediction service or a new model in the public model selector. It does not
establish diagnostic or report-reading accuracy; the methods solve the small synthetic task easily.

The second reader now preserves source context, marks repeated/negated quotes for review, suppresses
free-text model medical rationales from verified evidence, and invalidates cached reads after prompt,
verifier-code or configured-name changes. These changes require clinician review before any clinical use.
No source-context check proves a model interpretation correct. Same-name checkpoint replacement and
real clinical validation remain separate requirements. No GPU workload or shared service was changed.

## 1. Intended use (draft for review)

The full statement, with users, inputs, outputs and limits, is in
[`regulatory/INTENDED_USE.md`](regulatory/INTENDED_USE.md); the summary:

> ClinLoop tracks clinical follow-up obligations that arise from results, reports, orders and
> referrals already in the hospital record. It shows staff which expected follow-up step has not been
> recorded by its guideline deadline, why (the rule, the source sentence or value, the guideline
> reference), and lets them acknowledge, assign, defer with a reason, or close with evidence.
> It does not diagnose, does not recommend a treatment, and does not act on the record or contact a
> patient without a person's approval.

Everything below assumes this scope. Features that go beyond it are listed in §2.

## 2. Regulatory position (to be confirmed by a regulatory specialist)

The product is aimed at Korean hospitals, so the regulator is the Ministry of Food and Drug Safety
(MFDS), under the Medical Devices Act and the Digital Medical Products Act; personal information
falls under the Personal Information Protection Act (PIPA) and the Medical Service Act. Check the
current texts and MFDS guidance on medical device software and AI before any clinical use.

A useful design test is the US criteria for clinical decision support that is *not* a device
(21st Century Cures Act, section 520(o)(1)(E) of the FD&C Act, and FDA's CDS guidance): the software
does not analyse medical images or signals, it displays or analyses medical information, it supports
a professional's recommendation, and the professional can independently review the basis. The
follow-up tracking core is designed to meet these: every loop shows its rule, evidence and
reference, and a person decides.

These parts of the code do **not** fit that lane and would need their own regulatory route before
clinical use. They are research features today:

| Feature | Why it falls outside |
| --- | --- |
| DICOM image checks with model plug-ins, chest X-ray model, CT organ measurement, vision-language adapter (`imaging_ai.py`, `ct_organs.py`) | Analyses medical images |
| ECG reading from waveform-derived values (`ecg.py`) | Analyses a physiological signal (reading the text of an ECG report is a different matter) |
| Critical-finding alerts (R035) and other hour-scale rules | Time-critical alerts leave little time to review the basis |
| Model-based second reader (R058) | Model output that the user cannot fully check |

`CLINLOOP_PROFILE=core` now locks all of them off in code (`profile.py`), and new installs use it. The
feature-by-feature assessment, including the decision to report the one-hour rules R022 and R035 as a next-day documentation audit in the core profile, is in
[`regulatory/REGULATORY_ASSESSMENT.md`](regulatory/REGULATORY_ASSESSMENT.md).

## 3. What is in place

| Need | In place | Where |
| --- | --- | --- |
| Show the basis of every alert | Plain-language basis first (finding with value or quoted sentence, rule and deadline, reasoning, what was found, guideline), then the technical evidence chain and audit trail; the same basis on EHR cards | `basis.py`, worklist "Why this alert", `cds_hooks.py` |
| Know whether alerts lead to care | Every loop followed to its end: acted on, time to closure, late, dismissed and why, overdue with nobody acting | `outcomes.py`, Quality page |
| A person decides | Acknowledge, assign, defer with a coded reason, close with evidence; patient messages need a clinician's approval | `loop_store.py`, `worklist.html` |
| Specialist sign-off before a rule goes live | Hash-bound sign-off; shadow mode on by default with `install.sh` and docker compose | `governance.py` |
| Tamper-evident record of actions | Hash-chained audit log; `GET /api/v1/audit/verify` | `loop_store.py` |
| Record of who saw which patient | Hash-chained access log (who, when, client address, which patients, what view); `GET /api/v1/access-log` | `loop_store.py`, `clinical_api.py` |
| Know which logic raised a loop | Rule-set version on every loop and in its `loop_opened` audit entry | `governance.ruleset_version()` |
| One loop per finding | Final report replaces its preliminary version (§4.2) | `fhir_ingest.superseded_reports` |
| Patient's wish not to be messaged | Per-patient opt-out; drafting and approval refused; waiting drafts withdrawn | `PUT /api/v1/patients/{id}/outreach-preference` |
| Data stays in the hospital | FHIR, PACS, models and LLM all on premises; no patient data sent to outside services | README "Data protection" |
| Reproducible builds | `requirements.lock` used by CI and the Docker image | `requirements.lock` |
| Standard FHIR login | SMART Backend Services: signed client assertion, read-only scopes, token renewal; connection check | `smart_auth.py`, `docs/FHIR_CONNECTION.md` |
| Population data from Epic and similar | Bulk FHIR export (Group `$export`), local copy of the records, incremental by `transactionTime` | `bulk_fhir.py` |
| Staff sign-in | Hospital single sign-on (OpenID Connect, PKCE): roles from the person's groups; people without a ClinLoop role refused; sign-out ends the hospital session. Hand-issued tokens remain for service accounts | `oidc.py`, `js/appnav.js` |
| Shadow pilot (silent run) | Nothing reaches care; weekly sampled, blinded dual review; safety referral required for urgent open loops; protocol metrics and go / no-go; de-identified export | `pilot.py`, `pilot.html`, `docs/PILOT_RUNBOOK.md` |
| Stop when a rule misbehaves | Hourly rule monitor: mostly dismissed alerts pause a non-critical rule (new alerts held back, work in progress stays visible); a volume jump alone only flags it; critical rules are flagged, never paused; resume needs an administrator's note | `rule_monitor.py`, governance page, `docs/CLINICAL_REVIEW.md` |
| Roles | Bearer tokens with viewer / navigator / clinician / admin | `auth.py` |
| Access records in the standard shape | The access log as FHIR R4 AuditEvent resources, with each entry's chain hashes (`GET /api/v1/access-log/audit-events`, admin) | `audit_events.py` |
| Scale test on synthetic data | Folder runner: Synthea bundles or NDJSON streamed through the normal sync; counts only, no identifiers (1,000 bundles / 7,000 patients in about 25 s, 115 MB) | `fhir_folder.py` |
| Stay inside the intended use | Core profile locks off image analysis and model features; R047, R057, R058 never opened; shown on the governance page and in the rule-set version | `profile.py` |
| Know what ships | SBOM (CycloneDX) generated from the lock file and checked by the tests | `docs/regulatory/sbom.cdx.json` |

## 4. Design decisions

### 4.1 A follow-up at the same moment as its trigger does not close the loop

The engine counts a follow-up only if it is recorded *after* the triggering event
(`temporal_hypergraph.py`). A follow-up stamped with exactly the same time as the trigger is not
counted, and the loop's evidence says so ("SAME_TIMESTAMP"), so a reviewer can close it with
evidence when it really was the follow-up. The alternative would let the triggering study close its own loop: a CT report and its CT
study, or a result and the order it answers, often share a timestamp. Keeping strict "after" can
only produce a false alarm (a loop someone closes with evidence), never a missed follow-up. A
same-time follow-up is rare in practice; if a hospital's feed produces many, the fix is in the
mapping of that feed, not here.

### 4.2 Preliminary and final reports

A hospital may send the preliminary and final versions of a report as two resources. Read
separately, they open the same obligation twice. ClinLoop treats them as one report when they share
the patient, the accession number (or, without one, the same orders in `basedOn`) and the report
code.

- A draft version (`preliminary`, `partial`, `registered`) is replaced by a released version
  (`final`, `amended`, `corrected`, `appended`). Released versions never replace each other: an
  addendum sent as its own resource may contain only the addendum, and the original's findings
  must not be lost.
- When the draft had already opened a loop, the released version's loop for the same rule takes
  over its owner, acknowledgement, deferral and escalation level. The old loop is marked
  `superseded` and its unsent patient messages are withdrawn. Both steps are audited.
- When the released version no longer carries an obligation the draft did (the final read removed
  the finding), the loop is **not** closed. It stays on the worklist marked "Final report differs
  from the preliminary", because treatment or a referral may already have followed the preliminary
  read. A clinician confirms and closes it with evidence.
- Superseded loops are excluded from the open-loop rate and the follow-up breakdowns, so a report is
  counted once.

Lab results follow the same policy (Phase 5): a preliminary and a final Observation with the same
code and collection time (and the same specimen or order, when given) are one result. A final result
that is no longer flagged leaves the preliminary's loop open as "Final result differs from the
preliminary" for a clinician to confirm with the laboratory. A result without a collection time is
never matched.

Without an accession number or order reference the two versions cannot be linked safely, and both
loops remain. Ask the interface team to send the accession number (`DiagnosticReport.identifier`
with type `ACSN`).

### 4.3 Access log

- Every endpoint that returns or processes identifiable patient data records an entry: the
  worklist, a loop, its audit trail and messages, the patient graph, documents, uploads, FHIR
  ingest and the outreach preference. Reading the access log is itself recorded.
- If the entry cannot be written, the request fails. Data is not shown without a record.
- The worklist refreshes itself every 30 seconds. An identical view by the same person from the
  same address is recorded once per 10 minutes (`ACCESS_REPEAT_SECONDS`), with the list of patients
  shown. Any change (another patient on the list, another address) is recorded at once.
- The log is hash-chained like the audit log, and is kept until the hospital deletes it. Retention
  and review of access records must follow the hospital's PIPA obligations.
- The EHR integration (CDS Hooks) already writes its calls to the audit log.

### 4.4 Rule-set version

`ruleset_version()` hashes every rule's signed-off definition, the guideline registry, the
critical-finding list and the source files that decide obligations. A change to any of them gives a
new version. Each loop records the version that last evaluated it, and its `loop_opened`,
`loop_resolved_by_record` and `loop_reopened` audit entries record the version at that moment. This
answers "which logic raised this alert?" months later, and lets a validation study state which
version it measured. The governance summary shows the version that is live.

### 4.5 Outreach opt-out

Using a patient's data for their own care does not usually need separate consent under Korean law,
and ClinLoop trains no models on patient data. The consent question that applies to ClinLoop today
is contact: a patient can ask not to receive messages. The opt-out records how the patient asked,
who recorded it and when. While it stands, no message can be drafted or approved for that patient.
Confirm the hospital's consent and contact policy with its privacy officer.

### 4.6 Pinned dependencies

`requirements.txt` and `requirements-api.txt` give the allowed ranges. `requirements.lock` gives the
exact versions CI tests and the image ships (Python 3.12, all platforms). To change a dependency,
edit the range, regenerate the lock (command at the top of the file), run the tests, and commit both.

## 5. Not yet in place

| Gap | Why it matters | Suggested step |
| --- | --- | --- |
| Sandbox integration | Public SMART browser authorization and read-only HAPI synthetic source preview passed on 2026-10-26. Backend HAPI tests exposed cached history omitting new follow-ups; the no-cache correction is a tested local draft | Review/deploy the transport correction separately, repeat incremental ingestion and validate hospital-specific mapping; browser connectivity does not establish analysis accuracy |
| Vendor Bulk FHIR run | Bulk export is tested against a stub that follows the Bulk Data specification, not yet Epic | Group-level export from the Epic sandbox with synthetic patients |
| Hospital identity provider run | Single sign-on is tested against a stub provider in a real browser, not yet the hospital's Keycloak / Entra ID / ADFS | Register ClinLoop as a public client (PKCE) with `https://<server>/worklist.html` as its redirect address, map groups to roles, sign in once per role |
| Monitor thresholds | The default volume and dismissal thresholds are reasonable guesses, not tuned on real alert patterns | Run with `CLINLOOP_MONITOR=0` (report only) during the shadow pilot and set thresholds from what is seen |
| Validation on real data | All accuracy figures are on synthetic or public data. The tools for Stages 1 and 2 are built; the studies have not been run | Ethics approval, then Stage 1 chart review and the silent run (`docs/PILOT_RUNBOOK.md`) |
| Regulatory file | Drafted ([`regulatory/`](regulatory/README.md)): intended use, device assessment, risk file, lifecycle, SBOM, cybersecurity, evaluation and post-market plans, instructions for use. Nothing signed | Regulatory specialist, clinical lead and security officer review and sign; decide the open questions listed there |
| HTTPS and encryption at rest | The container serves plain HTTP and does not encrypt its database | Hospital reverse proxy with TLS; encrypted, backed-up volume ([`regulatory/CYBERSECURITY.md`](regulatory/CYBERSECURITY.md) §3) |
| Separate review of clinical-logic changes | One author can change a rule and its tests | Require a clinician reviewer on `clinical_ontology.py`, `radiology.py`, `fhir_ingest.py`, `motifs.py`, `guideline_reports.py`, `note_reader.py` and outreach code (e.g. GitHub CODEOWNERS) |
| Access-log review | Records exist; nobody is prompted to look at them | Periodic review report for the privacy officer |
| Database | SQLite suits one server; no replication | PostgreSQL for multi-server deployments |
