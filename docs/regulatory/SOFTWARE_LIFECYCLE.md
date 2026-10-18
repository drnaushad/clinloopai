# Software lifecycle (IEC 62304 structure)

**Status: draft. Describes how the software is built and changed today and what must be added for a
regulated release.** Version 0.1, October 2026.

## 1. Software safety classification (proposed)

| Class | Meaning (IEC 62304) |
| --- | --- |
| A | No injury possible |
| B | Non-serious injury possible |
| C | Death or serious injury possible |

**Proposed: class B for the core profile, to be confirmed by the risk-management specialist.**

Reasoning: a failure of ClinLoop (H-01, H-02 in the [risk file](RISK_MANAGEMENT.md)) can contribute
to delayed follow-up, and a delayed diagnosis can be serious. IEC 62304 allows the class to take
account of risk controls outside the software. Here the external control is usual care: the ordering
clinician remains responsible for the result, and ClinLoop is a second check. If the specialist does
not accept usual care as an adequate external control (for example for R022 and R035), the
affected items are class C, and the parts of the code that decide them (the "decision sources" listed
in `governance._DECISION_SOURCES`) would need class C activities: detailed design and unit
verification of each unit.

## 2. Development process in place

| Activity | How it is done now | Evidence |
| --- | --- | --- |
| Development planning | Phased roadmap; this folder; `AGENTS.md` (rules for every change) | Repository |
| Requirements | Intended use; rules with guideline references (`clinical_ontology.py`); safety requirements SR-01…SR-20 | [`TRACEABILITY.md`](TRACEABILITY.md) |
| Architecture | Record → events (`fhir_ingest.py`) → temporal graph (`temporal_hypergraph.py`) → detection (`loop_detector.py`) → store and workflow (`loop_store.py`) → API and pages | README, module docstrings |
| Detailed design | Module docstrings state purpose, inputs, safety decisions | Source |
| Unit and integration verification | Automated tests (615 at the time of writing), run in CI on every change and before every image | `tests/`, CI "test" job |
| System verification | Benchmark on synthetic trajectories (`python src/run_benchmark.py`); hospital-style data test; live browser checks with an accessibility scan | `docs/ACCURACY_EVALUATION.md`, `docs/HOSPITAL_DATA_TEST.md` |
| Clinical review of logic | Changes to clinical logic files are drafts until a clinician has reviewed them line by line (AGENTS.md §5); rule sign-off is bound to the rule version | `governance.py`, governance page |
| Release | Pull request → CI green → merge → image built from `main` and published to GHCR | `.github/workflows/docker-publish.yml` |

## 3. SOUP (software of unknown provenance)

Every third-party package and its exact version is in [`sbom.cdx.json`](sbom.cdx.json), generated
from `requirements.lock` (`python scripts/build_sbom.py`; the tests fail when it is out of date). The
runtime is the `python:3.12-slim` image.

SOUP that the core profile's safety depends on, with the requirement on it:

| SOUP | Used for | Requirement and how it is checked |
| --- | --- | --- |
| Python 3.12 standard library (`datetime`, `re`, `sqlite3`, `hashlib`) | Deadlines, text reading, storage, hash chains | Behaviour covered by the test suite on the pinned version |
| FastAPI, Starlette, Pydantic | API, request validation, roles | Request validation and role tests (SR-11) |
| PyJWT, cryptography | Single sign-on tokens, SMART client assertion | Token refusal tests (`tests/test_sso.py`, `tests/test_smart_auth.py`) |
| requests | FHIR reads (`fhir_sync.py`, `bulk_fhir.py`) | FHIR sync tests against stub servers |
| NetworkX | Temporal graph structures | Engine tests |

Image-model and language-model packages are SOUP only for the research profile and are not assessed
here.

## 4. Configuration management

- Source, documents and tests in one git repository; every change through a pull request.
- `requirements.lock` pins dependencies; `sbom.cdx.json` records them.
- **Rule-set version** (`governance.ruleset_version()`): a hash of every rule definition, the guideline
  registry, the critical-finding list, the decision source files and the profile. Stamped on every
  loop and in its audit entries, so any alert can be traced to the exact logic that raised it.
- Deployment configuration is environment variables; the governance page shows the profile, sign-off
  enforcement and rule-set version that are live.

## 5. Problem resolution

| Source | Route |
| --- | --- |
| A clinician dismisses an alert as not indicated or duplicate | Counted per rule; the rule monitor flags or pauses the rule (SR-05) |
| Silent-run reviewer judges a loop not truly open | Pilot metrics per rule family (PPV) |
| Incident or near miss | Hospital incident system → patient safety officer → issue in the repository with severity; risk file updated |
| Defect found in development | Issue → fix with a test that fails before the fix → pull request |

## 6. Change control

| Change | Required before release |
| --- | --- |
| A rule, its deadline or its follow-up list | Clinician review (AGENTS.md §5); new rule fingerprint makes its sign-off "needs re-review" automatically; re-run the rule's tests and the benchmark |
| Text-reading logic (`radiology.py`, `fhir_ingest.py`, `note_reader.py`, `ecg.py`, …) | Clinician review; report-level validation set re-run; rule-set version changes |
| A new input type, a time-critical rule, or a model output in the core profile | New [regulatory assessment](REGULATORY_ASSESSMENT.md) and risk review before release |
| Dependency | Change the range, regenerate the lock and SBOM, full test suite |
| Profile contents (`profile.py`) | Regulatory assessment §5 and intended use §7 updated in the same change (the tests check the rule list) |

## 7. Gaps before a regulated release

- Formal software development plan and software requirements specification documents, signed.
- Release notes per version with known anomalies, and a version number shown in the product that
  matches the release (the rule-set version identifies logic, not the whole software).
- Independent review of the class B (or C) verification evidence.
- A maintenance plan naming who supports a deployed version and for how long.
