# Datasheet for ClinLoop-Bench v1.0

Following Gebru et al., "Datasheets for Datasets" (2021).

## Motivation

- **For what purpose was the dataset created?** To measure whether a system finds the follow-up
  obligations a clinical report creates (which guideline rule, with what deadline) and whether it can tell,
  at a given time, if an obligation was met. Missed follow-up of abnormal results is a known cause of
  diagnostic delay; there was no open benchmark for this task, especially for Korean reports.
- **Who created it and on behalf of which entity?** The ClinLoop AI team, from the synthetic blind
  evaluation sets of the ClinLoop AI project.
- **Who funded the creation?** Not stated; to be completed by the owner.

## Composition

- **What do the instances represent?** One synthetic clinical report with patient context (T1, T3), or
  one synthetic patient timeline / FHIR record set with an evaluation time (T2).
- **How many instances?** 1,007: T1 416 (English), T2 317 (262 English, 51 mixed, 4 Korean),
  T3 274 (51 Korean, 223 mixed Korean/English). Dev/test: T1 130/286, T2 108/209, T3 78/196.
- **Sample or complete?** All labelled synthetic cases from the repository's blind rounds up to v1.0;
  exclusions are listed in the README.
- **What data does each instance consist of?** Report text or timeline events, patient context (age, sex,
  smoking, known malignancy, immunocompromise), a FHIR R4 Bundle carrying the same information, and an
  evaluation time.
- **Labels?** Obligated rule ids, deadline window, per-obligation status (open/closed) and overdue flag
  (timelines), writer's rationale.
- **Missing information?** No gold evidence spans; `overdue` is not labelled for the FHIR record sets;
  some report cases have no deadline window.
- **Relationships between instances?** None; each record is an independent synthetic patient.
- **Recommended splits?** `dev` (~30%) and `test` (~70%), by a seeded hash of the record id.
- **Errors, noise, redundancy?** Labels are a single writer's reading of the guidelines, not adjudicated.
  Some reports are deliberately ambiguous (hedged advice, negations).
- **Self-contained?** Yes. The rule catalogue is in the repository (`tests/report_eval/rule_catalog.json`).
- **Confidential data?** No. **Data identifying individuals?** No: every person is fictional; identifier
  fields are stripped from FHIR resources and a test checks for name/MRN/phone/resident-number patterns.
- **Sensitive data?** Fictional diagnoses (cancer, HIV, hepatitis B, TB) appear as clinical content only.

## Collection process

- **How was the data acquired?** Written, not collected. Case writers acting as radiologists and
  pathologists saw only the rule catalogue or guideline definitions, never ClinLoop's code, and wrote the
  case with its expected labels and a rationale.
- **Who was involved?** The writers were language-model agents prompted as clinicians (see the README's
  model-written caveat). No patients, no crowdworkers.
- **Over what timeframe?** 2026, in successive evaluation rounds; report dates in the data are fictional.
- **Ethical review?** Not applicable to synthetic data with no human subjects; none was conducted.
- **Consent?** Not applicable.

## Preprocessing / cleaning / labelling

- `scripts/build_benchmark.py` converts each source case to one record: builds the FHIR Bundle with the
  same functions the evaluation harnesses use, removes identifier fields, restricts gold rules to the
  scoped catalogue, maps timeline labels to status + overdue, assigns language by Hangul / Latin character
  share, and assigns the split. The raw sources stay in the repository.

## Uses

- **Intended:** comparing follow-up tracking systems (rules, ML, LLMs) on obligation extraction and loop
  status; regression testing; studying Korean / code-mixed report reading.
- **Should not be used for:** claims of clinical accuracy or safety, regulatory evidence, or training a
  model that is then evaluated on the same test split.
- **Risks:** synthetic, model-written text over-states performance on real reports. The ClinLoop rules were
  fixed against these rounds, so ClinLoop's own scores are optimistic.

## Distribution

- **How?** In this repository under `benchmark/`. A DOI may be added at release.
- **License:** suggested CC BY 4.0 for the data. The repository has no LICENSE file yet; the owner must add
  one before distribution.
- **Export controls / third-party IP?** None known. Guideline names are cited, guideline text is not copied.

## Maintenance

- **Maintainer:** the ClinLoop AI team (repository issues).
- **Updates:** new evaluation rounds are added by re-running the build and bumping the version. Record ids
  and splits are stable across versions; `manifest.json` records source hashes.
- **Errata:** label corrections should be made in the source sets and the benchmark rebuilt, with a version
  note.
- **Contributions:** new synthetic rounds following the same blind protocol (writers see only the rule
  catalogue).
