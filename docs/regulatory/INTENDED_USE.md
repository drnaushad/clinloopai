# Intended use statement

**Status: draft for review by a regulatory specialist and the clinical lead. Not approved.**
Version 0.1, October 2026. Applies to the **core profile** (`CLINLOOP_PROFILE=core`) only.

## 1. Intended use

> ClinLoop is software for hospital staff that tracks clinical follow-up obligations arising from
> results, reports, orders, referrals and medication records already held in the hospital's
> electronic record. For each obligation it shows whether the expected follow-up step has been
> recorded by a deadline taken from a published guideline or the hospital's own policy, and, when it
> has not, the reason: the rule, the triggering value or sentence quoted from the record, and the
> guideline reference. Staff acknowledge, assign, defer with a reason, or close each item with
> evidence.
>
> ClinLoop is a reminder and work-tracking aid. It does not diagnose, does not recommend a treatment,
> does not analyse medical images or physiological signals, and does not change the record, order
> anything or contact a patient without a person's approval. It does not replace the hospital's own
> processes for communicating critical results or for clinical follow-up.

## 2. Users

| User | Use | Training |
| --- | --- | --- |
| Physicians, nurse practitioners | Review items for their patients, decide and record the follow-up | 30-minute introduction (instructions for use §3–5) |
| Care navigators, nurses | Work the list: assign, chase, record evidence of follow-up | Same, plus outreach approval rules |
| Clinical leads, specialists | Sign off rules before they go live; review rule monitoring | Governance page; [`CLINICAL_REVIEW.md`](../CLINICAL_REVIEW.md) |
| Hospital IT, privacy officer | Install, connect, review access logs | [`FHIR_CONNECTION.md`](../FHIR_CONNECTION.md), §8 of the instructions |

Every decision about a patient is made by a licensed professional who can see the full record.

## 3. Patients and setting

- Patients of the hospital whose records reach ClinLoop through the hospital's FHIR interface. Each
  rule states its own age and sex limits; ClinLoop does not decide eligibility for
  a programme a rule does not describe.
- Outpatient and inpatient care in hospitals and their clinics. ClinLoop is not intended for use in
  emergency triage, intensive care monitoring or any setting where a decision is needed within
  minutes (see §6).

## 4. Inputs

Structured and text data already in the record, read through HL7 FHIR R4 (read-only): Patient,
Observation, DiagnosticReport (including report text), ImagingStudy (study labels only, no pixels),
ServiceRequest, Procedure, Encounter, Condition, MedicationRequest, Appointment, Communication and
DocumentReference (`fhir_sync.CLINICAL_TYPES`). ECGs are read from the interpretation text and the QTc
value as reported by the ECG machine or reader, never from the waveform. Staff can add outside reports and clinical notes by upload;
text found there is shown with its source sentence before it is filed.

## 5. Outputs

- A worklist of open follow-up items, each with its rule, deadline, the quoted evidence, the
  guideline reference and its audit trail.
- Read-only cards in the EHR (CDS Hooks) with the same content.
- Draft patient messages that never name a diagnosis or result, which a clinician must approve
  before sending; none while the patient has opted out.
- Reports for governance and quality: rule sign-off status, rule monitoring, feed status, the
  hash-chained audit and access logs.

## 6. Limitations and situations where it must not be relied on

- **It is a safety net, not the primary process.** A missing item on the list does not mean that no
  follow-up is needed. Clinicians keep full responsibility for reviewing their results.
- **Critical results.** Rules R022 and R035 check that the hospital's own critical-result call was
  documented within an hour. In the core profile they are a next-day documentation audit for the
  quality team, not a live alert. The hospital's critical-result call process stays in place and
  must not be replaced by ClinLoop.
- **Data it cannot see.** Care recorded outside the hospital's FHIR interface (paper, another
  hospital, a scanned letter not uploaded) is invisible, so an item can stay open after the follow-up
  happened. ClinLoop leaves such items open for a person rather than closing them.
- **Feed outages.** If the data feed stops, deadlines keep running but new results are not seen. The
  feed alarm shows on every page after the configured silence; IT must act on it.
- **Rules not signed off** by a specialist are held back (shadow mode, `CLINLOOP_ENFORCE_SIGNOFF=1`)
  and must not be shown to clinicians.
- **Validation.** Accuracy has been measured only on synthetic and public data. Clinical performance
  in a hospital is unknown until the studies in the [clinical evaluation plan](CLINICAL_EVALUATION_PLAN.md)
  are complete.

## 7. Not part of the intended use

The code base also contains research features: image analysis models, CT organ measurement,
automatic image scanning, imaging-AI result comparison and triage (R047, R057), a model-based
second reader of report text (R058), language-model suggestions and a free-text language-model
assistant, plus a demonstration cockpit on synthetic cases. They are **outside this intended use**.
The core profile locks all of them off (`src/clinloop_engine/profile.py`), and the governance page
shows the active profile. Using any of them on patients would need its own regulatory assessment.

## 8. Required configuration

| Setting | Value | Why |
| --- | --- | --- |
| `CLINLOOP_PROFILE` | `core` | Only the assessed features run |
| `CLINLOOP_ENFORCE_SIGNOFF` | `1` | Only specialist-approved rules reach staff |
| `CLINLOOP_FHIR_*` | Hospital FHIR server, read-only scopes | Inputs as described in §4 |
| Single sign-on or issued tokens | Every user named; roles from hospital groups | Every action is attributable |
| Critical-result process | Hospital's own, unchanged | §6 |

## 9. Sign-off

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Regulatory specialist | | | |
| Clinical lead | | | |
| Manufacturer's responsible person | | | |
