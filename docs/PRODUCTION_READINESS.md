# Production readiness: what is in place, what is not

ClinLoop is a research prototype. This page lists what a hospital pilot needs, what the code already
does about each need, the design decisions behind it, and what is still missing. It is a working
document for the team, the hospital's IT and privacy officers and its regulatory adviser. It is not
legal or regulatory advice.

## 1. Intended use (draft for review)

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

Recommendation: ship the tracking core on its own, with these features off by default, and decide
about each one separately.

## 3. What is in place

| Need | In place | Where |
| --- | --- | --- |
| Show the basis of every alert | Rule, triggering value or sentence, guideline reference, evidence chain, audit trail per loop | worklist "Why this alert" |
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
| Stop when a rule misbehaves | Hourly rule monitor: mostly dismissed alerts pause a non-critical rule (new alerts held back, work in progress stays visible); a volume jump alone only flags it; critical rules are flagged, never paused; resume needs an administrator's note | `rule_monitor.py`, governance page, `docs/CLINICAL_REVIEW.md` |
| Roles | Bearer tokens with viewer / navigator / clinician / admin | `auth.py` |

## 4. Design decisions

### 4.1 A follow-up at the same moment as its trigger does not close the loop

The engine counts a follow-up only if it is recorded *after* the triggering event
(`temporal_hypergraph.py`). A follow-up stamped with exactly the same time as the trigger is not
counted. The alternative would let the triggering study close its own loop: a CT report and its CT
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
| Vendor sandbox run | SMART login is tested against a stub that follows the specification, not yet a vendor's server | Run `fhir_sync --check`, then a sync, against Medplum or the SMART Health IT launcher with synthetic patients (`docs/FHIR_CONNECTION.md`) |
| Vendor Bulk FHIR run | Bulk export is tested against a stub that follows the Bulk Data specification, not yet Epic | Group-level export from the Epic sandbox with synthetic patients |
| Hospital identity provider run | Single sign-on is tested against a stub provider in a real browser, not yet the hospital's Keycloak / Entra ID / ADFS | Register ClinLoop as a public client (PKCE) with `https://<server>/worklist.html` as its redirect address, map groups to roles, sign in once per role |
| Monitor thresholds | The default volume and dismissal thresholds are reasonable guesses, not tuned on real alert patterns | Run with `CLINLOOP_MONITOR=0` (report only) during the shadow pilot and set thresholds from what is seen |
| Validation on real data | All accuracy figures are on synthetic or public data | Shadow-mode pilot on retrospective de-identified data with full clinician review (`docs/STUDY_PROTOCOL.md`) |
| Regulatory file | No intended-use sign-off, no device determination | §1 and §2 to a regulatory specialist |
| Separate review of clinical-logic changes | One author can change a rule and its tests | Require a clinician reviewer on `clinical_ontology.py`, `radiology.py`, `fhir_ingest.py`, `motifs.py`, `guideline_reports.py`, `note_reader.py` and outreach code (e.g. GitHub CODEOWNERS) |
| Access-log review | Records exist; nobody is prompted to look at them | Periodic review report for the privacy officer |
| Database | SQLite suits one server; no replication | PostgreSQL for multi-server deployments |
