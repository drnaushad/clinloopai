# Regulatory file

The documents a regulatory specialist, ethics board and hospital need before ClinLoop is used in
live patient care. **All are drafts.** Nothing here has been reviewed by a regulator, and none of it is
legal advice. Each document ends with the sign-offs it needs.

| Document | Answers | Sign-off by |
| --- | --- | --- |
| [Intended use](INTENDED_USE.md) | What ClinLoop is for, for whom, with which inputs and outputs, and its limits | Regulatory specialist, clinical lead |
| [Regulatory assessment](REGULATORY_ASSESSMENT.md) | Why the core profile is designed as non-device clinical decision support, feature by feature; the open question on one-hour rules | Regulatory specialist |
| [Risk management](RISK_MANAGEMENT.md) | Hazards, risk controls and residual risk (ISO 14971 structure) | Clinical lead, patient safety officer |
| [Traceability](TRACEABILITY.md) | Each risk control → the code that implements it → the tests that verify it (checked by the tests) | — |
| [Software lifecycle](SOFTWARE_LIFECYCLE.md) | Safety class, development process, SOUP, change control (IEC 62304 structure) | Quality lead |
| [SBOM](sbom.cdx.json) | Every third-party package and version (CycloneDX), generated from `requirements.lock` | — |
| [Cybersecurity](CYBERSECURITY.md) | Controls, what the hospital must provide, threats, vulnerability handling | Information security officer, privacy officer |
| [Clinical evaluation plan](CLINICAL_EVALUATION_PLAN.md) | Which claims, which evidence, stage gates (builds on the [study protocol](../STUDY_PROTOCOL.md)) | Clinical lead, ethics board |
| [Post-market surveillance](POST_MARKET_SURVEILLANCE.md) | Who watches which signal after go-live, and what they do | Patient safety officer |
| [Instructions for use](INSTRUCTIONS_FOR_USE.md) | What staff and IT need to know to use it safely | Clinical lead |

## The core profile

The intended use covers the follow-up tracking core only. `CLINLOOP_PROFILE=core` locks every
research feature off (image models, CT measurement, image scanning, imaging-AI comparison and
triage, the model second reader, language-model features) and never opens R047, R057 or R058
(`src/clinloop_engine/profile.py`). `core` is the default (October 2026): an installation is the
clinical edition unless `CLINLOOP_PROFILE=research` is set on purpose, which must never be done for
patient care.

## Keeping the file true

`tests/test_regulatory.py` fails when:
- a hazard has no risk control, or a control names code or a test that no longer exists;
- the SBOM no longer matches `requirements.lock` (regenerate: `python scripts/build_sbom.py`);
- the profile's research rules are missing from the intended use or the assessment;
- a link between these documents is broken.

## Decisions still open

1. Device status in Korea, confirmed by a regulatory specialist ([assessment §1](REGULATORY_ASSESSMENT.md)).
2. Software safety class B or C ([lifecycle §1](SOFTWARE_LIFECYCLE.md)).
3. Machine-measured QTc as an input ([assessment §3](REGULATORY_ASSESSMENT.md)).

Decided: the one-hour rules R022 and R035 are a next-day documentation audit in the core profile
(clinical lead, October 2026; [assessment §4](REGULATORY_ASSESSMENT.md)); the regulatory specialist
confirms.
