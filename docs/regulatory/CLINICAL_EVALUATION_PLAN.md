# Clinical evaluation plan

**Status: draft for the clinical lead, the ethics board and the regulatory specialist.** Version 0.1,
October 2026. This plan sets out what evidence is needed for the core profile, and how. The study
procedures themselves are in the [study protocol](../STUDY_PROTOCOL.md) and the
[silent-run runbook](../PILOT_RUNBOOK.md); this plan does not repeat them.

## 1. Claims to be supported

Only these claims will be made, and each needs the evidence named:

| Claim | Evidence | Stage |
| --- | --- | --- |
| C1. ClinLoop identifies follow-up obligations in the hospital record accurately | Sensitivity ≥ 85 % and PPV ≥ 70 % per rule family against blinded dual chart review | 1 |
| C2. It does not show a loop as done when it is not | Zero unexplained false closures; each one reviewed as a safety event | 1 |
| C3. On live data it finds clinically important open loops that usual care misses, at a workload clinicians accept | ≥ 1 true important open loop beyond usual care per 1,000 patients per month; ≤ 5 alerts per clinician per day accepted by clinical leads; feed uptime ≥ 99 % | 2 |
| C4. Used in care, it shortens time to follow-up without harm | Stepped-wedge trial: primary outcome time to completion of overdue follow-up; safety monitoring | 3 |

Claims that will **not** be made: that ClinLoop detects disease, prevents cancer deaths, or replaces
any part of the hospital's result-management process.

## 1a. Where ClinLoop stands on the evidence ladder

Clinical AI earns trust in order: each level rests on the one below, and a claim may go only as high as
the evidence beneath it. ClinLoop's position, October 2026:

| Level | Question | What answers it | Status |
| --- | --- | --- | --- |
| 1. Technical | Does the software do what it was designed to do? | Automated tests, deterministic rules, tamper-evident audit, traceability from each risk control to code and tests | **Done** for the core (tests in CI, `TRACEABILITY.md`) |
| 2. External validity | Is it right on real records it has never seen? | Stage 1: blinded dual chart review (1A on MIMIC, [`STUDY_PROTOCOL_STAGE1A.md`](../STUDY_PROTOCOL_STAGE1A.md); 1B in a Korean hospital) | **Not started.** Tools ready; needs data access, reviewers, ethics |
| 3. Decision impact | On live data, are its alerts true, wanted and manageable? | Stage 2 silent run: PPV, burden, what usual care misses ([`PILOT_RUNBOOK.md`](../PILOT_RUNBOOK.md)) | **Not started.** Tools ready |
| 4. Clinical impact | Do patients get their follow-up sooner, without harm? | Stage 3 stepped-wedge trial, primary outcome time to completion of overdue follow-up, measured from the audit log (`outcomes.py`) | **Not started** |
| 5. Real-world performance | Does it keep working across sites and over time, fairly? | Post-market surveillance: rule monitor, outcome measures, equity breakdowns, yearly re-review ([`POST_MARKET_SURVEILLANCE.md`](POST_MARKET_SURVEILLANCE.md)) | Monitoring built; nothing deployed |

The aim the whole ladder serves is fewer patients harmed by follow-up that never happened. Accuracy
(levels 2 and 3) is necessary for that but is not the aim: a tool that detects every gap and closes
none helps no one. So from Stage 2 on, every loop is followed to its end: whether anyone acted on it,
how long until it closed, whether it closed after the deadline, whether it was dismissed and why, and
which overdue loops nobody touched (`GET /api/v1/quality/outcomes`, Quality page). These are the
measures Stage 3 compares between units with and without ClinLoop.

**Safeguards that do not rest on the clinician alone.** "A person decides" is necessary but cannot be
the only control: it moves the burden of catching the software's errors onto busy staff. ClinLoop
therefore also carries system-level controls: the plain-language basis on every loop, so the reason can
be checked in seconds (`basis.py`); dismissal as easy as acceptance, with every reason counted and acted
on per rule (`rule_monitor.py`); loops nobody acted on surfaced, not buried (`outcomes.py`, escalation);
specialist sign-off before a rule reaches staff; and the core profile, which keeps unverifiable model
output out of clinical use. Clinicians who will use the worklist should co-design it during Stage 2.

## 2. Evidence available now

| Source | What it shows | Limits |
| --- | --- | --- |
| Synthetic trajectory benchmark (`python src/run_benchmark.py`) | The rules behave as designed against known ground truth; comparison with inbox-alert and naive model baselines | Synthetic data written from the same rules: it cannot show real-world accuracy |
| Report-level validation sets (`src/validation/report_validation.py`) | Text reading on written and public example reports | Small, not from the target hospital |
| Hospital-style data test ([`HOSPITAL_DATA_TEST.md`](../HOSPITAL_DATA_TEST.md)) | Robustness to messy feeds (missing flags, odd codes) | Synthetic |
| Literature on missed follow-up of results and incidental findings | That the problem exists and is common | Not about ClinLoop |
| Clinical review of design decisions ([`CLINICAL_REVIEW.md`](../CLINICAL_REVIEW.md)) | Clinician reasoning about specific behaviours | AI-assisted draft; sign-off by a licensed clinician pending |

None of this supports C1–C4. Real-data evidence starts with Stage 1.

## 3. What is measured, on which version

- **Locked logic.** Each stage records the rule-set version (`governance.ruleset_version()`) and the
  profile. Every loop carries the version that raised it; the pilot export has it on every row. If the
  logic changes during a stage, results are reported per version, and a change to a rule family
  under study restarts its count.
- **Rule families.** Results, imaging findings, transitions of care, referrals, drug monitoring
  (protocol §4). A family that fails a criterion is left out of the next stage or fixed and retested
  (protocol §7); it is not used.
- **Core profile only.** `CLINLOOP_PROFILE=core` in every stage. Research features are not evaluated.
- **Equity.** Results by age group, sex and language (protocol §4); a family that performs clearly
  worse in a subgroup is reviewed before use.

## 4. Stage gates

| Gate | Decision by | Inputs |
| --- | --- | --- |
| Start Stage 1 | Ethics board | Protocol, data-protection review |
| Stage 1 → 2 | Clinical lead, patient safety officer | Stage 1 report; [risk file](RISK_MANAGEMENT.md) re-estimated |
| Stage 2 → 3 | Clinical leads, data-safety group, regulatory specialist | Pilot metrics (Pilot review page, export), safety referrals, [regulatory assessment](REGULATORY_ASSESSMENT.md) confirmed |
| Routine use after Stage 3 | Hospital governance | Trial result; [post-market plan](POST_MARKET_SURVEILLANCE.md) staffed |

No live patient-facing use (alerts to clinicians, messages to patients) before the Stage 2 → 3 gate.

**Model second reader: silent → suggestions shown to clinicians.** A separate gate; the criteria are
proposals for the clinical lead to set before the measurement starts, not after:

| Criterion | Proposed threshold | Source |
| --- | --- | --- |
| Suggestions judged by the quality team | ≥ 300, across radiology and pathology | Quality page, second-reader table |
| Real misses found (needed follow-up that no rule tracked and nobody had handled) | ≥ 10, enough to matter clinically | Same |
| Precision (real misses ÷ judged) | Lower 95 % bound ≥ 20 % (at most about four reviews per real miss) | Same, Wilson interval |
| Wrong quotes | ≤ 1 % of judged suggestions | Same |
| Urgent real misses | Each one reviewed by the patient safety officer, with its safety referral | Audit log |
| Regulatory | Regulatory assessment §5 repeated; MFDS pre-consultation held | Assessment sign-off |

If it passes, suggestions appear as a separate, clearly marked list for confirmation by a clinician:
a suggestion becomes a loop only when a person confirms it, and the model never closes one.

## 5. After release: clinical follow-up

Clinical performance keeps being measured in routine use through the [post-market surveillance
plan](POST_MARKET_SURVEILLANCE.md): dismissal rate and volume per rule (rule monitor), a yearly
sample re-review of closed and open loops by the Stage 1 method, and incident reports. A sustained
drop below the Stage 1 criteria for a family is handled as a problem report (lifecycle §5).

## 6. Sign-off

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Clinical lead | | | |
| Principal investigator | | | |
| Regulatory specialist | | | |
