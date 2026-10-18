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
