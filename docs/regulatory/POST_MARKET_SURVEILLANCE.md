# Post-market surveillance plan

**Status: draft. Names roles, not people; the hospital fills in who.** Version 0.1, October 2026.

After go-live, the question is whether ClinLoop still works as validated, on this hospital's data,
as the data and the guidelines change. Most of the signals are already produced by the software; this
plan says who looks at them and what they do.

## 1. Signals and who reviews them

| Signal | Produced by | Reviewed by | How often | Action threshold |
| --- | --- | --- | --- | --- |
| Rule paused or flagged (volume jump, mostly dismissed) | Rule monitor (`rule_monitor.py`), governance page | Clinical lead for the rule family | When raised; weekly summary | Every pause: review before resuming (a note is required) |
| Dismissal reasons per rule | Defer reasons on the worklist | Clinical lead | Monthly | Dismissal rate above the monitor threshold, or a new pattern in free-text notes |
| Feed alarm and uptime | Feed monitor (`/api/v1/feed/status`) | Hospital IT on-call | Continuous alarm; monthly uptime | Any alarm; uptime below 99 % in a month |
| Overdue loops nobody acknowledged | Escalation (`escalate_overdue`) | Department heads in the escalation chain | Daily | Any loop at the top escalation level |
| Guideline updates | Guideline registry alerts on the governance page | Specialists who signed off the rule | When raised | Re-review the rule; sign-off follows the rule version |
| Access log | Access log (`GET /api/v1/access-log`) | Privacy officer | Monthly sample; on request | Access without a care relationship, unusual volume |
| Audit chain integrity | `GET /api/v1/audit/verify` | Hospital IT | Weekly, automated | Any failure: incident |
| Incidents and near misses involving ClinLoop | Hospital incident system | Patient safety officer | As reported; quarterly summary | Every report is assessed against the [risk file](RISK_MANAGEMENT.md) |
| Clinician feedback on EHR cards | CDS Hooks feedback (audited) | Clinical lead | Monthly | Repeated "not helpful" for one rule |
| Yearly accuracy re-check | Stage 1 method on a fresh sample | Clinical lead and two reviewers | Yearly | Below the Stage 1 criteria for a family |

## 2. Periodic report

Every quarter, the clinical lead and the patient safety officer write a short report: rules paused or
changed and why, incidents, uptime, access-log findings, and whether the [risk file](RISK_MANAGEMENT.md)
needs new hazards or new estimates. The report goes to the hospital's patient-safety committee and is
kept with this file.

## 3. Reporting to the regulator

If ClinLoop is a medical device in the hospital's jurisdiction (see the [regulatory
assessment](REGULATORY_ASSESSMENT.md)), adverse events and recalls must be reported to the regulator
(in Korea, the Ministry of Food and Drug Safety) within the legal time limits; the specialist will add
the exact obligations here. If it is not a device, incidents still follow the hospital's
patient-safety reporting rules.

## 4. Field actions

| Situation | Action |
| --- | --- |
| A rule is found to be wrong | A specialist records "changes requested" on the rule (governance page): with sign-off enforcement on, its loops leave the worklist at once; fix through change control (lifecycle §6); review loops it opened |
| A defect could have closed loops wrongly | Re-run the engine on the affected period after the fix; reopened loops are audited (`loop_reopened`) and reviewed by the clinical lead |
| A security vulnerability | [Cybersecurity](CYBERSECURITY.md) §5 |
| The feed was down | After recovery, check loops whose deadline passed during the outage |
