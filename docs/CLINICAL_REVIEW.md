# Clinical review of Phase 1 and Phase 2 logic

This records the clinical review of the code added in Phases 1 and 2 that decides which loops
clinicians see and which patients may be contacted. The review was AI-assisted (the project's coding
assistant, acting as clinical reviewer at the project lead's request). **It does not replace review
and sign-off by a licensed clinician**: the sign-off block at the end is for that person.

Scope: `rule_monitor.py` and `governance.visible_loops` (rule monitoring), `fhir_ingest.superseded_reports`
and `LoopStore.supersede_sources` (preliminary and final reports), `LoopStore.set_outreach_preference`
and `_refuse_if_opted_out` (message opt-out). Not in scope: the 65 obligation rules themselves, which
each need specialist sign-off on the governance page.

## 1. Rule monitoring

**Question:** can the monitor hide a true clinical obligation?

| Finding | Risk | Decision |
| --- | --- | --- |
| A jump in alert volume alone paused a rule | A real surge (screening campaign, new clinic, catch-up after an outage) would pause a correct rule and hide true positives, e.g. positive FIT results awaiting colonoscopy | **Changed:** volume alone now only flags the rule for review; it keeps alerting |
| A pause hid every loop of the rule, including ones a clinician had already acknowledged or deferred | Work in progress disappeared from the person responsible for it | **Changed:** a pause holds back only new, unacknowledged loops; acknowledged and deferred loops stay visible |
| A flagged rule could never be paused afterwards | Dismissals arriving after a flag would be ignored | **Changed:** a flagged, non-critical rule is paused when dismissals cross the threshold |
| Critical rules | Hiding a critical alert is the larger danger | **Kept:** critical rules are only ever flagged |
| Go-live back-fill | The first sync opens many loops at once | **Kept:** volume is judged only after 5 weeks of history |
| What counts as a dismissal | Deferrals coded "not clinically indicated" or "duplicate". "Patient declined", "completed elsewhere", hospice and death do not count: there the rule was right | **Kept.** Note: "duplicate" dismissals usually point to the data feed, not the rule; the review step should check both |
| Thresholds (3× usual week; 50 % of at least 10 decisions in 4 weeks) | Not derived from data | **Open:** run with `CLINLOOP_MONITOR=0` (report only) during the shadow pilot and set thresholds from observed rates before letting it act |
| Who learns of a pause | The worklist banner and governance page name the rule; nobody is paged | **Open:** decide who reviews paused and flagged rules, and how quickly (suggested: the patient safety officer, within one working day) |

Tests covering each decision: `tests/test_rule_monitor.py`.

## 2. Preliminary and final reports

**Question:** can a loop opened on a preliminary report be lost?

| Situation | Behaviour | Assessment |
| --- | --- | --- |
| Final report carries the same obligation | The final report's loop takes over owner, acknowledgement, deferral and escalation; the preliminary loop is marked superseded | Correct: one loop, nothing done is lost |
| Final report drops the finding (e.g. pulmonary embolism on the preliminary, not on the final) | The preliminary loop stays on the worklist: "Final report differs from the preliminary", with the action to confirm with radiology and check what was already done | Correct and important: a preliminary–final discrepancy is a known safety event; the loop is never closed silently |
| Final report raises a different obligation | A new loop opens for it; the old one is handled as above | Correct |
| A corrected or amended report after the final | Released versions never replace each other, so both loops stay | Acceptable: possible duplicate, never a lost obligation. An addendum sent as its own resource may hold only the addendum, so replacing would be unsafe |
| No accession number or order reference | The versions cannot be linked; both loops stay | Acceptable; ask the interface team to send the accession number |
| Preliminary loop already deferred, and the final drops the finding | The loop keeps its deferral (the clinician's decision) and is marked as revised | Acceptable |

Tests: `tests/test_phase1_production.py` (report versions).

## 3. Message opt-out

| Situation | Behaviour | Assessment |
| --- | --- | --- |
| Patient asks not to be messaged | Recorded with how they asked; drafting and approval refused; waiting drafts withdrawn | Correct |
| The loop itself | Stays open; staff are told to contact the patient another way | Correct: opting out of messages is not opting out of care |
| Critical results | Critical rules never allow patient messages (clinician contact only), so the opt-out cannot affect them | Correct |
| Opting back in | Allowed, audited; withdrawn drafts are not restored (a new draft is needed) | Acceptable |

Tests: `tests/test_phase1_production.py` (opt-out).

## 3a. Plain-language basis of each alert (Phase 6, October 2026)

Every loop's "Why this alert" text (`basis.py`) was read for 53 rule-and-status combinations from the
synthetic and example records, as a clinician would read it on a ward round. Found and fixed before
merge:

| Finding | Risk | Fix |
| --- | --- | --- |
| Quotes were a character window and could start mid-word: "Negative for high-grade dysplasia" was shown as "…grade dysplasia in fragment A", which reads as the opposite; "18 mm adrenal nodule" lost its size | Misread finding | Whole sentences from the report are quoted |
| A rule needing two steps (R009: patient told *and* referral) listed the step done but not the one outstanding | Loop looks finished | "Still missing: specialist referral" |
| The reason a loop needs review read "Uncertainty (1.00) exceeds threshold (0.7)" | Not actionable | "The record ClinLoop can see holds too little to tell whether this follow-up happened. Check the chart." |
| Deadlines months away showed a clock time ("2027-06-09 07:12") | False precision | Date only, except for windows under two days |
| Some medication findings omitted the drug | Basis not checkable | Drug, organism or specimen named when the record has it |

Each fix has a regression test (`tests/test_phase6.py`). Left as they are, for rule sign-off rather than
wording: R001 for a critical value asks for patient notification within 3 days (the critical call
itself is R022); mapping notes use the rules' own abbreviations ("aaa 46 mm").

## 4. Before clinical use

1. A licensed clinician reviews this document and the code it names, and signs below.
2. Specialists sign off each of the 65 rules on the governance page (none are signed off today).
3. The shadow pilot runs with `CLINLOOP_MONITOR=0`; monitor thresholds are then set from what is seen.
4. The hospital names who reviews paused and flagged rules, and how fast.

## Sign-off

| Reviewer (name, specialty, licence no.) | Date | Decision (approve / changes needed) | Notes |
| --- | --- | --- | --- |
| | | | |
