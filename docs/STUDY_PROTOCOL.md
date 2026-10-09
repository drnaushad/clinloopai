# Clinical validation protocol (draft for a partner hospital and its ethics board)

**Title:** ClinLoop AI: detecting open clinical follow-up loops. A staged study of accuracy, safety
and benefit.

**Status:** draft, version 0.1.
- Not yet reviewed by an ethics board (IRB) or registered.
- A statistician and the site's clinical leads must finalise the sample sizes and endpoints.

## 1. Background

Missed follow-up harms patients. It is common for:
- abnormal results;
- incidental imaging findings;
- referrals;
- monitoring after a new drug.

It is a recognised cause of delayed diagnosis. EHR in-basket alerts are often acknowledged without the
follow-up happening. ClinLoop tracks each follow-up obligation from its trigger to its completion, and
shows the open ones to the responsible clinician with the rule and the evidence. In ClinLoop's terms,
an open obligation is an "open loop".

**Evidence so far** (synthetic data only; see [`ACCURACY_EVALUATION.md`](ACCURACY_EVALUATION.md) and
[`HOSPITAL_DATA_TEST.md`](HOSPITAL_DATA_TEST.md)):
- **Blind report sets:** 80–97% correct on first pass.
- **Whole-record comparison** with a blind reviewer: 71% of obligations found after fixes, and no
  follow-up shown as done when it was not.
- **No real-patient data has been used.** This study is the step that turns these claims into
  measurements.

## 2. Objectives

| Stage | Question | Design |
|---|---|---|
| 1. Retrospective accuracy | Does ClinLoop find the open loops clinicians would find, and only those? | Diagnostic accuracy against chart review, on past records |
| 2. Silent (shadow) run | In live use, how many true open loops does it surface beyond usual care, at what alert burden? | Prospective, no alerts shown to clinicians |
| 3. Effectiveness | Does showing the loops (worklist plus EHR cards) increase timely follow-up without harm? | Stepped-wedge cluster trial across clinical units |

Each stage proceeds only if the previous one meets its go/no-go criteria (section 7).

## 3. Setting and data

- **Sites:** one or two hospitals with a FHIR R4 interface, or an export of their EHR.
- **Integration:**
  - ClinLoop runs on hospital servers (`install.sh` or Docker);
  - it reads data read-only through FHIR sync (`CLINLOOP_FHIR_BASE`);
  - it shows clinicians cards inside the EHR through CDS Hooks (`/cds-services`) in Stage 3 only.
- **Population:** adults with any of the trigger events covered by the rules signed off for the study.
  Examples:
  - abnormal or critical results;
  - incidental lung, adrenal, renal, pancreatic, thyroid or aortic findings;
  - BI-RADS 4/5;
  - positive FIT;
  - elevated PSA;
  - heart-failure or MI discharges;
  - specialist referrals;
  - starts of monitored drugs.
- **Exclusions:** patients in hospice or palliative care, and patients who opted out of data use where
  local law gives that right.
- **Rule governance:** before Stage 2, the site's specialists review each rule in the governance page
  (`governance.html`) and sign it off, approve the critical-finding list and set local thresholds.
  Unsigned rules stay silent.

## 4. Stage 1: retrospective accuracy

**Sample:**
- a stratified random sample of patients with trigger events in a past 12-month window;
- for each, ClinLoop's verdict at the end of the window (open, done late, done on time);
- plus a random sample of patients with no ClinLoop loop, to measure misses.

**Reference standard:**
- **Reviewers:** two clinicians from the relevant specialty, blinded to ClinLoop's output.
- **Question:** each reviewer answers "was a follow-up obligation created, and was it completed in time?"
  using the full chart.
- **Disagreements:** a third clinician adjudicates.
- **Tools:**
  - `python -m src.validation.chart_review sample` draws the sample and the blinded packets;
  - `analyze` computes the results;
  - `src.validation.report_validation` handles report-level rules.

**Primary measures:**
- sensitivity and PPV of open-loop detection, per rule family, with 95% CIs (stratified bootstrap);
- inter-reviewer agreement (Cohen's κ).

**Secondary measures:**
- **False closures:** loops shown as done when not done. Target 0; any one is reviewed as a safety event.
- **Deadline accuracy.**
- **Results by subgroup:** age group, sex, language (equity).

**Sample size:** to estimate a sensitivity of about 90% with a 95% CI half-width of ±5%, about 140 true
obligations are needed per rule family reported. With about 50% of sampled loops truly open, that
means about 300 sampled loops per family, plus 300 patients without a loop for the miss rate. The
families are:
- results;
- imaging findings;
- transitions of care;
- referrals;
- drug monitoring.

## 5. Stage 2: silent run (shadow mode)

- **Duration:** ClinLoop runs live for 3 months.
- **No alerts:** escalation is off and no cards are shown. Usual care is unchanged.
- **Weekly sample review:** a review team checks a random sample of loops ClinLoop marked overdue, and
  records for each one:
  - **(a)** whether it was truly open;
  - **(b)** whether usual care would have caught it anyway (it closed later without intervention);
  - **(c)** whether it was clinically important.
- **Measures:**
  - true open loops per 1,000 patients;
  - PPV;
  - alerts per clinician per day (the expected burden);
  - median delay in usual care;
  - data-feed uptime (`/api/v1/feed/status`).
- **Safety:** a reviewed loop that is truly open and clinically urgent is passed to the treating team
  through the site's normal safety-reporting route. Patients are not left at risk for the sake of the
  study.

## 6. Stage 3: effectiveness (stepped-wedge cluster trial)

**Clusters and design:**
- units or departments start ClinLoop in a random order, one step every 6–8 weeks, until all use it;
- before its step, each unit is a control.

**Intervention:**
- the worklist for the unit's care navigators and clinicians;
- CDS Hooks cards when the patient's chart is opened;
- escalation of overdue loops to the unit lead.

Clinicians decide every action. ClinLoop never orders tests or contacts patients without clinician
approval.

**Primary outcome:** the proportion of trigger events whose required follow-up was completed within
the guideline window. This is measured from the record by the same rules, and checked by blinded chart
review on a random 10% sample.

**Secondary outcomes:**
- time from trigger to follow-up;
- clinically important delayed diagnoses (adjudicated);
- patient notification rates.

**Balancing measures** (harm from the tool itself):
- alerts per clinician per day;
- card override rates and reasons;
- unnecessary tests prompted (follow-ups done but not indicated on review);
- clinician-reported burden (NASA-TLX or similar).

**Equity:** primary-outcome effects by age group, sex and language. The tool must not widen gaps.

**Sample size, illustrative:**
- **Assumption:** usual-care completion around 60% (published adherence to follow-up of incidental
  findings varies widely, often 30–70%).
- **Target:** to detect an improvement to 75% with 80% power at α = 0.05 needs about 150 trigger events
  per arm before cluster adjustment.
- **Cluster adjustment:** the stepped-wedge design effect depends on the number of clusters, the steps
  and the intra-cluster correlation, which is estimated in Stage 2. The statistician finalises the
  numbers from that.

## 7. Go / no-go criteria

| From → to | Proceed only if |
|---|---|
| Stage 1 → 2 | Sensitivity ≥ 85% and PPV ≥ 70% for each rule family to be used, no unexplained false closures, κ between reviewers ≥ 0.6 |
| Stage 2 → 3 | ≥ 1 true clinically important open loop per 1,000 patients per month beyond usual care, alert burden accepted by clinical leads (target ≤ 5 per clinician per day), feed uptime ≥ 99% |
| During Stage 3 | Stop or pause a unit if the data-safety monitoring group sees harm: rising missed urgent loops, unsafe alert fatigue, or a pattern of false closures |

Rule families failing a criterion are left out or fixed and retested, not used.

## 8. Data protection and ethics

- **On-site data:**
  - data stays on hospital servers;
  - ClinLoop sends no patient data to external AI;
  - optional local models run on-premise only.
- **Data handling:**
  - access by role-based tokens;
  - every action is recorded in a hash-chained audit log (`/api/v1/audit/verify`);
  - de-identified extracts for analysis.
- **Approvals:**
  - ethics board (IRB) approval at each site, and compliance with local law (for example Korea's PIPA,
    HIPAA in the US);
  - consent waiver for Stages 1–2 is likely appropriate (minimal risk, usual care unchanged), to be
    decided by the ethics board;
  - Stage 3 as a quality-improvement trial with clinician-level information.
- **Registration and reporting:**
  - register before Stage 3 (ClinicalTrials.gov or CRIS);
  - report Stage 1 under STARD and STARD-AI, and Stage 3 under CONSORT (stepped-wedge extension) with
    CONSORT-AI and the DECIDE-AI guidance for early clinical evaluation of AI;
  - publish all results, including negative ones.
- **Regulatory status:**
  - ClinLoop is a research prototype and not a medical device;
  - the study uses it under the hospital's research governance;
  - any clinical deployment after the study needs the appropriate regulatory route (for example MFDS
    or FDA software as a medical device).

## 9. Team and roles

| Role | Responsibility |
|---|---|
| Principal investigator (site clinician) | Study conduct, safety escalation |
| Specialty leads | Rule sign-off, local thresholds, adjudication |
| Chart reviewers (2 + adjudicator per family) | Blinded reference standard |
| Statistician | Final sample sizes, analysis plan, interim safety analyses |
| Data-safety monitoring group | Independent review of harm signals in Stage 3 |
| ClinLoop technical lead | Installation, feed monitoring, version control (each rule's fingerprint frozen per stage) |
