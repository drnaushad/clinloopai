# Clinical/ML draft review — 26 October 2026

Status: research-preview candidate with independent source review deferred. The earlier research candidate was uploaded to a separate preview branch; publication to main and the live website was not completed. No clinical approvals have been recorded. This is not a clinical release. The earlier 27 October corrections are recorded in [the PR58 deep review](PR58_DEEP_REVIEW_20261027.md), and the returned-review corrections are recorded in [the engineering disposition](RETURNED_REVIEW_CORRECTIONS_20261027.md). The current packet contains 23 pending source reviews: the previous 22 plus the review-tool provenance correction. See the [GMLP evidence and gap tracker](gmlp-gap-assessment-20261027.json).

This branch carries the remaining clinical safety drafts, source provenance checks, patient/duplicate-separated synthetic ML comparators, dataset evaluation tooling and regression tests. Previously published interface, report-review, Epic and SMART/HAPI changes are preserved.

Before approving clinical behavior for patient-care use:

- Arrange an independent, appropriately qualified clinician to review every changed clinical line and record decisions against the exact source hashes in `clinical-ml-20261026.json`.
- Adjudicate the known synthetic report and timeline disagreements. Engineering tests do not resolve clinical reference disagreements.
- Define the intended use, independently labelled cohort, patient grouping, acceptance criteria and subgroup evaluation.
- Evaluate the chosen model/checkpoint, prompt and schema. Synthetic structured ML comparisons do not establish model superiority or clinical performance.
- Complete the institution's privacy/security review and supervised silent pilot before considering clinical deployment.

The review packet creates no runtime rule sign-offs. Do not mark any reviewer field approved without the named human's completed review. Older local GPU status notes are historical snapshots; this branch neither changes nor restarts GPU or model services.

Regenerate the packet after source edits with:

```sh
python scripts/clinical_review_packet.py --base aadad952cd68715e24735f0412b3034c393ed45b --output /tmp/new-clinical-review.json
```

The checker returns exit status 2 while review is pending. Clinical accuracy and hospital readiness remain unestablished.

## Engineering verification of the 26 October candidate, before the follow-up review

- Offline regression suite: 933 passed, 122 subtests passed, 14 skipped and four existing warnings.
- The 13 Git-dependent review-tool tests passed separately on the host; one pre-existing skip remains.
- `python src/run_benchmark.py` completed with the seeded synthetic ML comparators.
- Shared-header generation and whitespace checks passed.
- All 19 source review records remain pending, with zero approvals and no runtime rule sign-offs.

No patient datasets, attachments, provider keys, private keys, model weights or local service settings are included. These engineering results do not establish clinical accuracy or approve clinical deployment.
