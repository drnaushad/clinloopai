# Silent-run pilot: runbook

This is the practical guide to Stage 2 of [`STUDY_PROTOCOL.md`](STUDY_PROTOCOL.md): ClinLoop runs on
the live record for about three months while a review team checks a weekly sample of the loops it
marks overdue. Nothing reaches clinical care, so usual care is unchanged. Stage 1 (retrospective chart
review, `src/validation/chart_review.py`) comes first; ethics approval comes before either.

## Candidate preparation status (2026-10-26)

Engineering may exercise this workflow with synthetic records and ephemeral authentication in an
isolated test database. That is a software rehearsal, not a prospective hospital pilot. No hospital
partner, named reviewer team, privacy/security acceptance or institutional approval is recorded for
the current candidate. The numerical thresholds and durations below are draft protocol proposals;
the clinical lead and statistician must approve them before use. A real pilot remains blocked until
every prerequisite is documented. Do not change shared service settings just to make this checklist
appear complete. Clinical/ML drafts stay unpublished and no patient outreach is enabled.

## 1. Before starting

| Step | Who | Done when |
| --- | --- | --- |
| Ethics board approval of the protocol, including the safety-referral route | Principal investigator | Approval letter on file |
| Data-protection review: the server, the local copy of records (Bulk FHIR), access log retention | Privacy officer | Signed |
| Clinical review sign-off (`docs/CLINICAL_REVIEW.md`) | Licensed clinician | Signed |
| Review team named: at least two clinicians per rule family to be judged | Clinical lead | Names in `CLINLOOP_PILOT_REVIEWERS` |
| Safety route agreed: whom a reviewer calls about an urgent open loop, and how it is reported | Patient safety officer | Written down and known to every reviewer |
| Connection checked (`python -m src.clinloop_engine.fhir_sync --check`) | Hospital IT | All required types readable |

## 2. Settings

```
CLINLOOP_SILENT_RUN=1                       # nothing reaches clinical care
CLINLOOP_PILOT_REVIEWERS=dr.kim,dr.park     # the review team (user names); others cannot see loops
CLINLOOP_PILOT_REVIEWS_PER_LOOP=2           # two independent reviews per sampled loop
CLINLOOP_PILOT_CLINICIANS=12                # clinicians who would receive the alerts (burden measure)
CLINLOOP_MONITOR=0                          # the rule monitor only reports (it also cannot act in a silent run)
```

During the silent run:
- the worklist shows a "silent run" notice instead of loops; EHR cards are empty;
- escalation, patient messages and every action on a loop (acknowledge, assign, defer, close) are refused;
- only the review team and administrators can open a loop or a patient graph;
- the engine, the data feed, the access log and the audit log all run as normal.

## 3. Each week

1. **Draw the sample** (administrator, Pilot review page): 20 loops is a sensible weekly size; tick
   "All" for 100 % review. The draw is random but reproducible for the week, and a loop is never
   drawn twice. The number of eligible loops is stored with the sample, so results can be weighted.
2. **Review** (each reviewer, Pilot review page): for every loop in "Waiting for my review", look at
   the full chart and answer:
   - (a) Was the follow-up truly still open?
   - (b) Would usual care have caught it anyway?
   - (c) Is it clinically important?

   Other reviewers' answers are hidden until the analysis.
3. **Urgent findings:** if a loop is truly open and the treating team must know now, tick "Urgent",
   contact the team by the agreed route **at once**, and record who was told, when and how. The review
   cannot be saved without it. The patient safety officer reviews the "Safety referrals" list weekly.
4. **Discordant loops** (reviewers disagree on question a): a third clinician adjudicates. Record the
   outcome in the study file; the dashboard counts them separately and leaves them out of the PPV.

## 4. Reading the results

The Pilot review page shows:

| Measure | Meaning |
| --- | --- |
| PPV (95 % CI) | Share of judged sampled loops that were truly open, overall and per rule family |
| True important open loops per 1,000 patients per month beyond usual care | Weighted by each week's sampling fraction; patients = everyone the engine evaluated |
| Truly open loops later closed by usual care | Observed from the record afterwards, alongside the reviewers' judgement (b) |
| Alerts per clinician per day | Loops whose trigger happened during the run, divided by the clinicians who would receive them. The first sync's back-fill of history is excluded |
| Delay in usual care | Median days past the deadline for follow-ups done late |
| Feed uptime | Share of the run covered by successful data-feed runs |
| Agreement | Observed agreement and Cohen's κ (κ reads low when nearly every answer is the same) |

No go / no-go judgement is shown before 30 judged loops **and** 4 weeks of observation. The criteria
are the protocol's (§7):

| Stage 2 → 3 | Threshold |
| --- | --- |
| True clinically important open loops beyond usual care | ≥ 1 per 1,000 patients per month |
| Alert burden | ≤ 5 per clinician per day, and accepted by the clinical leads |
| Feed uptime | ≥ 99 % |

**Export for the statistician:** "De-identified export (CSV)" (administrator). One row per review:
hashed loop and reviewer, rule, family, severity, week, the three answers, whether a safety referral
was made and the rule-set version. No patient ids and no free text.

## 5. Ending the silent run

1. Export the reviews and freeze the analysis.
2. The clinical leads decide on alert burden; the data-safety group reviews the safety referrals.
3. Rule families that fail a criterion are left out or fixed and retested (protocol §7).
4. Turn the silent run off (`CLINLOOP_SILENT_RUN=0`) only for the units starting Stage 3, with the
   rules signed off and shadow mode (`CLINLOOP_ENFORCE_SIGNOFF=1`) on.
