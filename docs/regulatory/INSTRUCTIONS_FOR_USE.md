# Instructions for use

**Status: draft.** Version 0.1, October 2026. For staff using ClinLoop in the core profile. A Korean
translation must be prepared and checked by a clinician before use.

## 1. What ClinLoop is for

ClinLoop reminds you of follow-up steps that are due from results, reports, orders and referrals
already in the record, and shows why. It is a second check. It does not diagnose, recommend
treatment, read images, or replace your own review of results. Full statement:
[intended use](INTENDED_USE.md).

## 2. Warnings

- **An empty list does not mean nothing is due.** ClinLoop sees only what reaches it through the
  hospital's FHIR interface. Care recorded elsewhere, scanned letters not uploaded, or results from
  another hospital are invisible to it.
- **Critical results:** follow the hospital's critical-result call process. ClinLoop's one-hour
  checks (R022, R035) only check afterwards that the call was documented.
- **Check the source.** Every item quotes the value or sentence it came from. If the quote does not
  support the item, defer it as "not clinically indicated" with a note: this feeds the rule monitor.
- **Feed alarm.** If a page shows that the data feed is failing or silent, new results are not being
  seen. Tell IT; do not rely on the list until it clears.
- **Patient messages** never name a diagnosis or a result. You approve each one; you can edit or
  refuse it. Do not approve a message for a patient you have not checked.

## 3. Reading an item

| Field | Meaning |
| --- | --- |
| Rule and name | The follow-up obligation, e.g. "lung nodule → CT follow-up per Fleischner" |
| Trigger | The event that created it, with the quoted value or sentence |
| Deadline | When the follow-up was due, from the guideline or the radiologist's own interval |
| Missing | Which follow-up has not been recorded |
| Why this alert | Evidence chain, guideline reference, audit trail of everything done on the item |
| Status | Open, overdue, needs human review (ClinLoop could not decide), done late |
| "Final report differs from the preliminary" | The final report dropped a finding the preliminary had. Check whether anything was already done before closing |

## 4. Acting on an item

| Action | When | Recorded |
| --- | --- | --- |
| Acknowledge | You are taking it on | Who and when |
| Assign | Someone else should act | To whom |
| Defer with a reason | Not needed now (coded reason: patient declined, completed elsewhere, not clinically indicated, hospice or comfort care, deceased, duplicate, other; a note is required for "not clinically indicated" and "other") | Reason and note; dismissals are counted per rule |
| Close with evidence | The follow-up happened but ClinLoop cannot see it | Your written evidence (required) |
| Draft a patient message | The patient needs to book or attend | The draft, your approval, sending |

A recorded follow-up in the record closes an item by itself; you do not need to close it by hand.
An unacknowledged overdue item escalates to the next person in the chain.

## 5. Opt-out from messages

If a patient asks not to be contacted by ClinLoop messages, record it from the item on the worklist
(how they asked; ClinLoop records who entered it and when). While it stands, no message can be drafted or approved for them; follow up by
other means.

## 6. For administrators and IT

- Install with `CLINLOOP_PROFILE=core` and `CLINLOOP_ENFORCE_SIGNOFF=1`. The governance page shows
  the profile, the sign-off policy and the rule-set version in use; check them after every update.
- Put ClinLoop behind the hospital's HTTPS reverse proxy, encrypt the database volume and back it
  up ([cybersecurity](CYBERSECURITY.md) §3).
- Connect the FHIR server ([`FHIR_CONNECTION.md`](../FHIR_CONNECTION.md)) and run
  `python -m src.clinloop_engine.fhir_sync --check` before go-live.
- Only rules signed off by a specialist reach staff. A rule whose definition changes needs re-review.
- A paused rule needs an administrator's note to resume, after the clinical lead's review.

## 7. Reporting problems

Report wrong or missing items, wrong closures and any harm or near miss through the hospital's
incident system, naming ClinLoop and the item's rule. The patient safety officer reviews them
([post-market plan](POST_MARKET_SURVEILLANCE.md)).

## 8. Identification

| | |
| --- | --- |
| Product | ClinLoop (core profile) |
| Software version | Image tag; rule-set version shown on the governance page |
| Manufacturer | To be completed |
| Regulatory status | To be completed after the [regulatory assessment](REGULATORY_ASSESSMENT.md) |
