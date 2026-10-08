# Clinical notes: plans that must not be forgotten

Many missed follow-ups start as a promise in a note that was never ordered:

- "Repeat potassium in 1 week"
- "CT chest in 3 months"
- "Refer to cardiology"
- "6주 후 외래 재방문"

ClinLoop reads the plan part of a clinician's note, in English or Korean. Each concrete plan becomes an
obligation, with the exact sentence it came from.

| Plan in the note | Closes only when | Rule | Default if no interval is written |
|---|---|---|---|
| Repeat or check a lab test | A result of **the same test** (a potassium plan is not closed by a TSH). "Repeat labs" with no named test is closed by any lab result. | R048 | 30 days |
| Imaging | A study of **the same modality** covering **the named region** (a chest X-ray does not close "CT chest"; a head CT does not either) | R049 | 90 days |
| Referral | A referral or visit to **the same specialty** | R050 | 30 days |
| Follow-up visit | A follow-up appointment that took place | R051 | 30 days |

**Deadline.** The stated interval plus a grace period:
- for lab tests, referrals and visits: 15%, at least 3 days;
- for imaging: the radiology grace period, 25% (7–30 days).

For a range ("4–6 weeks"), the upper bound is used.

## What is deliberately not tracked

Each of these plans is still shown on the patient graph, with the reason it is not tracked:

| Kind | Examples | Shown as |
|---|---|---|
| Conditional | "Repeat CBC **if** fever recurs", "**consider** MRI", "**필요시** 초음파" | conditional |
| Cancelled or negated | "**No need** to repeat echo", "ortho consult **declined**", "협진 **불필요**" | negated or cancelled |
| Already done | "HbA1c **was rechecked** last month", "**이미** 시행함" | already done |

**History sections are not read for plans.** This covers HPI, past history, 현병력 and 과거력. When the
note has a Plan / A&P / 계획 section, only that section is read. Otherwise the whole note is read,
minus the history sections; each history section ends at the next heading or blank line.

## Where notes come from

- **FHIR `DocumentReference`** from the EHR, with `text/plain` or `text/html` attachments carried
  inline. Notes with `docStatus` "preliminary" are ignored.
- **`patient.html` → *Read a clinical note*.** Paste a note, or send a PDF or scanned file (read
  with OCR).
  - *Find plans* shows what would be tracked and stores nothing.
  - *File note and track* stores the note, with identifiers removed (the patient's name, resident
    number, phone number, MRN), and re-evaluates the patient.
- **API:** `POST /api/v1/documents/clinical-note/extract` and `POST /api/v1/documents/clinical-note`
  (navigator role).

## Optional: the hospital's local LLM as a second reader

Ticking *ask the local AI* sends the plan part of the note, with identifiers removed, to the
on-premise Ollama model. The model is asked which plans the rules missed.

- A suggestion must **quote the note word for word**. Suggestions that don't are dropped, so the
  model cannot invent plans.
- Suggestions are **shown for review and never tracked automatically**. A person decides.
- **The model has not been run here.** No local LLM was available in the build environment, and the
  page reports this. The parsing and the quote check are tested with recorded answers.

## Limits, honestly

- **Rules, not understanding.** The reader knows 18 lab tests, 7 imaging modalities and 19
  specialties, in English and Korean. Plans outside that vocabulary are not found; this is what the
  LLM suggestions are for.
- **Not yet measured on real notes.** Before clinical use, measure precision and recall on a sample of
  real notes against two clinicians' annotation, with IRB approval. Do this per note type
  (outpatient, discharge, ED), because note styles differ.
- **New rules start unsigned.** R048–R051 start in shadow mode, like every rule, until a specialist
  signs them off on `governance.html`.
