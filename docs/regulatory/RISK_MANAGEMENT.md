# Risk management file (ISO 14971 structure)

**Status: draft. The hazard list and the estimates are the development team's first pass; they must
be reviewed by the clinical lead, the patient safety officer and a risk-management specialist, and
re-estimated with the data from the silent run.** Version 0.1, October 2026. Scope: the core profile.

## 1. Method

- Hazards are found from the intended use, the data flow (record → rules → worklist → person), the
  clinical review ([`CLINICAL_REVIEW.md`](../CLINICAL_REVIEW.md)), the deep code review of PR #36
  and the known failure modes of results follow-up in the literature.
- **Severity** (S): 1 negligible, 2 minor (inconvenience, extra work), 3 serious (delayed care
  without lasting harm), 4 critical (delayed diagnosis with lasting harm), 5 catastrophic (death).
- **Probability** (P) that the hazardous situation leads to harm: 1 improbable, 2 remote,
  3 occasional, 4 probable, 5 frequent. Before real-data validation these are estimates.
- **Acceptability**: S × P ≤ 4 acceptable; 5–9 acceptable only after risk controls reduce it as far as
  possible and the benefit outweighs it; ≥ 10 not acceptable.
- Every risk control is a safety requirement (SR) in [`TRACEABILITY.md`](TRACEABILITY.md) with the
  code that implements it and the tests that verify it. `tests/test_regulatory.py` fails if a hazard
  here has no control there, or a control names code or a test that does not exist.

A key point for the estimates: ClinLoop runs **alongside** usual care. The clinician who ordered the
test remains responsible for its result. Most hazards below are "the safety net fails", so the harm
also needs usual care to fail; this is why many residual probabilities are low.

## 2. Hazards, controls and residual risk

| ID | Hazard (hazardous situation) | Possible harm | S | P before | Risk controls | P after | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H-01 | A follow-up obligation in the record is not recognised (rule gap, unmapped code, text phrased unusually) | Delayed diagnosis (e.g. a nodule never re-imaged) | 4 | 3 | SR-01, SR-18, SR-13; Stage 1 sensitivity ≥ 85 % per rule family before use; rule monitor; hospital code mapping review at go-live | 2 | 8: acceptable with benefit (usual care still applies) |
| H-02 | An open loop is closed wrongly (a follow-up of the wrong kind, the trigger study closing its own loop, a cancelled order) | Follow-up never happens, nobody is reminded | 4 | 3 | SR-02, SR-03, SR-08; Stage 1 "no unexplained false closures" | 1 | 4: acceptable |
| H-03 | Report text is misread (negation, a differential read as a diagnosis, history read as new) | False alert (S2) or missed obligation (H-01) | 3 | 3 | SR-18, SR-01 (quoted sentence shown), SR-04 | 2 | 6: acceptable with benefit |
| H-04 | Too many or low-value alerts | Alert fatigue; real alerts ignored | 3 | 4 | SR-04, SR-05, Stage 2 burden ≤ 5 per clinician per day; per-rule dismissal monitoring | 2 | 6: acceptable with benefit |
| H-05 | The data feed stops or lags silently | Results not seen; loops wrongly look open or wrongly look fine | 4 | 3 | SR-06; feed uptime ≥ 99 % in Stage 2; IT on-call for the alarm | 1 | 4: acceptable |
| H-06 | Data attached to the wrong patient | Wrong person contacted or a loop closed by another patient's test | 4 | 2 | SR-07, SR-11 | 1 | 4: acceptable |
| H-07 | A rule or guideline is wrong or out of date | Wrong deadline or wrong follow-up suggested | 3 | 3 | SR-04 (specialist sign-off bound to the rule version), SR-13, guideline-update alerts on the governance page, SR-05 | 1 | 3: acceptable |
| H-08 | Staff rely on the list as complete (automation bias): "not on the list, so nothing to do" | Delayed care from items ClinLoop cannot see | 4 | 3 | Intended use §6 and instructions §2 state it is a safety net; SR-01; training; no "all clear" message: an empty worklist says it covers only the records ClinLoop can see | 2 | 8: acceptable with benefit; re-estimate in Stage 3 |
| H-09 | A patient message is wrong, reveals a diagnosis, or goes to a patient who opted out | Distress, privacy breach, loss of trust | 3 | 2 | SR-12 | 1 | 3: acceptable |
| H-10 | Duplicate loops for one finding (preliminary and final report, two sources) | Extra work; double contact; inflated metrics | 2 | 4 | SR-08 | 2 | 4: acceptable |
| H-11 | Unauthorised access to patient data | Privacy breach | 3 | 2 | SR-11, SR-10, SR-20; [cybersecurity](CYBERSECURITY.md) | 1 | 3: acceptable |
| H-12 | The audit or access record is altered or lost | Actions cannot be reconstructed after an incident | 3 | 2 | SR-09, SR-10, database backup (hospital IT) | 1 | 3: acceptable |
| H-13 | A research feature (image model, language model) is used on patients | Unvalidated output influences care; device used without approval | 4 | 2 | SR-14; installation checklist; governance page shows the profile | 1 | 4: acceptable |
| H-14 | An overdue loop stays unacknowledged | Delay continues unseen | 4 | 3 | SR-15; escalation up the chain; SR-06 | 2 | 8: acceptable with benefit |
| H-15 | Patient data leaves the hospital (to a model, a public service, an export) | Privacy breach | 3 | 2 | SR-16, on-premise only design, outbound network blocked by the hospital, literature queries use rule-level terms only | 1 | 3: acceptable |
| H-16 | A pilot reviewer finds an urgent open loop during the silent run and nothing reaches the team | Harm during the study | 4 | 2 | SR-19 (safety referral required before an urgent review is saved), patient safety officer reviews referrals weekly | 1 | 4: acceptable |
| H-17 | A dependency changes behaviour or carries a vulnerability | Wrong output or compromise | 3 | 2 | SR-17 (pinned lock file, SBOM); vulnerability handling in [cybersecurity](CYBERSECURITY.md) §5 | 1 | 3: acceptable |
| H-18 | A time-critical item (R022, R035) is treated as the primary critical-result alert | Critical result not acted on within the hour | 5 | 2 | SR-21 (core profile: next-day documentation audit, never a live alert); intended use §6; instructions §2; hospital's critical-result process stays primary ([assessment §4](REGULATORY_ASSESSMENT.md)) | 1 | 5: acceptable only with benefit; confirm with the safety officer |

## 3. Overall residual risk

Before real-data validation, the team's view is that the benefit (a second check on follow-up that
published studies show is missed for a substantial share of abnormal results, at rates that vary
widely by test and setting) outweighs the residual risk,
**provided** the controls are in place and Stages 1 and 2 meet their criteria. This judgement must be
repeated by the clinical lead and patient safety officer with the Stage 1 and 2 results, and
recorded below.

| Review point | Reviewer | Conclusion | Date |
| --- | --- | --- | --- |
| Before the silent run | | | |
| After the silent run (Stage 2 → 3) | | | |
| Annual review | | | |

## 4. Production and post-production information

New hazards and changed probabilities come from: the rule monitor, dismissal reasons, the safety
referrals of the silent run, incident reports, user feedback on EHR cards, feed alarms and the
access-log review. The [post-market surveillance plan](POST_MARKET_SURVEILLANCE.md) says who looks at
each and how often; any new hazard is added here with its control.
