# Regulatory assessment: device status of the core profile

**Status: draft position for a regulatory specialist. It is not legal advice and has not been
discussed with any regulator.** Version 0.1, October 2026.

This file sets out why the core profile is designed as clinical decision support that is not a
medical device, feature by feature, and where that position is weakest. It assumes the
[intended use statement](INTENDED_USE.md).

## 1. Jurisdictions and sources to check

| Market | Law and guidance to confirm against (current editions) |
| --- | --- |
| Korea (first market) | Medical Devices Act and its enforcement rules; Digital Medical Products Act (in force from January 2025); MFDS guidance on whether software is a medical device, on medical device software approval and review, and on AI-based medical devices; Personal Information Protection Act; Medical Service Act (electronic medical records) |
| United States (design test) | FD&C Act §520(o)(1)(E) (21st Century Cures Act); FDA guidance *Clinical Decision Support Software* (September 2022) |
| European Union (not targeted) | MDR 2017/745 Annex VIII rule 11; MDCG 2019-11. Rule 11 classifies most decision-support software as at least class IIa, so the non-device argument below would **not** carry over |

The specialist should confirm in particular how MFDS treats software that only reminds staff of
guideline-based follow-up from record data, and whether it would consider the time-limited rules in
§4 a different case.

## 2. The test applied

The FDA's four criteria for non-device CDS are used as a structured design test, because they are
explicit and widely used; MFDS guidance asks related questions (does the software analyse images or
signals, does it diagnose or decide treatment, can the professional check its basis). A feature
passes only if all four hold:

1. It does not acquire, process or analyse a medical image, a signal from an in-vitro diagnostic
   device, or a pattern or signal from a signal acquisition system.
2. It displays, analyses or prints medical information about a patient or other medical information
   (such as guidelines).
3. It supports or provides recommendations to a health care professional about prevention, diagnosis
   or treatment, and does not replace their judgement or direct a time-critical decision.
4. It lets the professional independently review the basis of the recommendation, so they do not
   rely primarily on it.

## 3. Feature by feature

| Feature (core profile) | 1 No image or signal | 2 Medical information | 3 Supports a professional | 4 Basis reviewable | Position |
| --- | --- | --- | --- | --- | --- |
| Follow-up rules on lab values, orders, referrals, appointments, medications (R001–R046, R048–R056, R059–R065 except §4) | Yes: values and codes as recorded | Yes | Yes: "this step is not yet recorded", not what to do clinically | Yes: rule text, quoted value, guideline link, deadline arithmetic | Non-device CDS (proposed) |
| Reading follow-up recommendations from radiology and pathology report text (`radiology.py`, `guideline_reports.py`) | Yes: the radiologist's text, not the image | Yes | Yes | Yes: the quoted sentence is shown | Non-device (proposed). Text extraction errors are a risk to control (risk file H-03), not a device trigger |
| ECG items: AF on the ECG report (R054), QTc ≥ 500 ms (R059) (`ecg.py`) | Yes in the core profile: uses the interpretation text and the QTc number the ECG machine or reader reported. The waveform is never read | Yes | Yes | Yes: quoted text or value | Non-device (proposed). **Weak point:** a regulator may see a machine-measured QTc as signal-derived. The QTc is already in the record as a result, like a potassium value; the specialist should confirm |
| Clinical-note plan reading (rules only, `note_reader.py`) | Yes | Yes | Yes | Yes: source sentence shown before filing | Non-device (proposed) |
| Worklist actions, outreach drafts with clinician approval, opt-out, audit and access logs | n/a | Yes | Workflow, not a clinical recommendation | Yes | Not a device function (administrative and communication software) |
| Patient graph (timeline of the record) | Yes | Yes | Display only | Yes | Not a device function |

## 4. The time-critical rules: the main open question

Three rules have a one-hour window:

| Rule | What it checks | Core profile |
| --- | --- | --- |
| R022 | A critical lab value has a documented clinician notification within 1 hour | **Next-day documentation audit** |
| R035 | A critical imaging finding has a documented communication within 1 hour | **Next-day documentation audit** |
| R057 | A critical imaging-AI finding on an unread study is read within 60 minutes | **Off** (needs imaging AI) |

FDA guidance treats software that drives a time-critical decision as failing criterion 3, because
the professional has no time to review the basis. The argument for keeping R022 and R035:

- they do not ask for a clinical decision. They check, after the fact, that the hospital's existing
  critical-result call was documented. The decision (what to do about the result) was already made
  by the people on the call;
- the hospital's critical-result process remains the primary control (intended use §6), and the
  instructions for use say so;
- removing them would remove a back-up for a known failure mode (undocumented or failed critical
  calls).

The argument against: an overdue R022 or R035 item, shown within an hour, is read by staff as an
urgent alert. If the specialist judges that this brings the product into device territory, the
options were (a) keep them, labelled as a documentation audit shown only to the quality team the
next day, or (b) turn them off in the core profile.

**Decision (clinical lead, October 2026): option (a).** In the core profile (`profile.audit_rules()`):

- the engine still evaluates R022 and R035 and records each loop, its rule-set version and its audit
  trail;
- their loops are kept off the worklist and the EHR cards and never escalate
  (`governance.live_rule_ids`);
- the Quality page lists every critical result more than 24 hours old as documented within the
  hour, documented late, not documented, or closed by staff with evidence
  (`GET /api/v1/quality/documentation-audit`, navigators and above, access recorded).

The output is then a retrospective audit of a documentation process, not an alert that directs a
time-critical decision. The regulatory specialist still has to confirm this position.

## 5. Outside the core profile

These are locked off by `CLINLOOP_PROFILE=core` (`profile.py`, tested in `tests/test_profile.py`):

| Feature | Fails criterion | Likely route if ever used clinically |
| --- | --- | --- |
| Chest X-ray model, vision-language model, plug-in image models, CT organ measurement, automatic PACS image scan (`imaging_ai.py`, `ct_organs.py`, `imaging_scanner.py`) | 1 (analyses images) | Software as a medical device; MFDS approval as image-analysis software |
| Imaging-AI result comparison (R047) and triage of unread studies (R057) (`ai_review.py`, `/imaging/ai-results`) | 1 (derived from image analysis), 3 (R057 is time-critical triage) | Computer-aided triage; device |
| Model-based second reader of reports (R058, `second_reader.py`) | 4 (language-model output the user cannot fully check) | Device assessment needed; probably device |
| Language-model note suggestions; free-text language-model assistant including "differential diagnosis" (`note_reader.llm_suggestions`, `/local-llm/generate`, `/agent/*`) | 3 and 4 (diagnostic suggestions from a model) | Device; not planned |
| Demonstration cockpit and illustrative survival curves (`/api/v1/cases/*`) | Synthetic cases only | Not for patient use; keep out of hospital deployments |

## 6. Consequences for the product

- Market and describe only the core profile. Claims must stay inside the intended use: "tracks
  follow-up", never "detects disease", "prevents missed cancer" or "AI diagnosis".
- Ship hospital installations with `CLINLOOP_PROFILE=core` and `CLINLOOP_ENFORCE_SIGNOFF=1`.
- Any change that adds an input type, a time-critical rule or a model output to the core profile
  triggers a new assessment (software lifecycle §6, change control).
- Even as non-device software, the hospital needs the risk management, validation and
  post-market measures in this folder: the duty of care does not depend on device status.

## 7. Sign-off

| Role | Name | Conclusion | Date |
| --- | --- | --- | --- |
| Regulatory specialist (Korea) | | | |
| Clinical lead | | | |
