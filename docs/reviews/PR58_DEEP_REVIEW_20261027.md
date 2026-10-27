# PR58 engineering safety review — 27 October 2026

Status: clinical changes remain a draft. This engineering review supplies no clinician approval, runtime rule sign-off or clinical accuracy claim. The released website remains on `main`.

## Reproduced defects and corrections

| Defect | Correction and regression evidence |
| --- | --- |
| A caller could assign another patient's event trajectory to its own patient ID. | Reject mixed or unresolved identities before constructing detections; errors contain no source identifiers. |
| The second reader could process a report without checking its subject and could include a future-dated report. | Require a matching patient subject and report ID; bound dates by the normalized evaluation clock before any model call. |
| An active/completed ServiceRequest proposal or plan could count as an issued order/referral. | Require an order-family intent for completion evidence; preserve unresolved requests for human review. |
| A direct procedure event marked with a result-finalization status could close a task. | Check completion status against the event type in the temporal graph and motif paths; retain final results as result evidence. |
| A cached read could survive a silent/live research-mode change or changed rule coverage. | Include the mode and tracked rule set in cache provenance. |
| Dropped model quotes could be cached as a clean read or scored as a clean negative report. | Mark incomplete source verification failed/nonreusable and treat study inference as an abstention. Valid suggestions remain for human review. |
| Study model provenance was captured once, so weights could change during a long run. | Verify local checkpoint identity before and after every model prediction; reject a returned model mismatch. |
| Failed rescoring could leave an earlier accuracy file looking current. | Invalidate the derived accuracy export before validating a rescore; only write a new result after successful validation. |
| An unavailable or negative rule prediction could still receive deadline credit from stale fields. | Count a deadline only when that rule prediction is available and positive. |
| Duplicate scenario IDs could overwrite benchmark predictions. | Reject duplicate or missing scenario keys before fitting or prediction. |
| Equivalent numeric vectors could cross the train/test boundary because JSON distinguished integers, floats and explicit zeros. | Canonicalize finite numeric vectors before patient/duplicate grouping; absent and explicit zero features share a representation. |
| Year-based surveillance intervals bypassed calendar conversion because YEAR and twelve MONTH constants differ. | Convert the existing half-year and whole-year surveillance intervals using the actual calendar anchor, including leap years and month-end clamping. No new clinical interval was introduced. |

The regression additions use synthetic fixtures, fake models and mocked metadata. They do not call a real model or use patient datasets. A valid synthetic referral fixture was corrected to declare its required `intent: order`; missing intent is tested as unresolved.

## Verification

The new regression file contains 41 parameterized synthetic cases. The initial adversarial run reproduced 18 failures in the previously tested draft; subsequent cases cover the additional findings above. Full-suite and seeded benchmark results are recorded with the follow-up commit and PR description. Existing report expectations were not relabelled to raise accuracy.

Final offline suite: **974 tests and 122 subtests passed**, with 14 skips and four existing warnings. The 13 Git-dependent review-tool tests passed separately on the host; one pre-existing skip remains. The seeded four-system ML benchmark completed. Header generation, whitespace checks and the refreshed 20-file source-review gate also passed their engineering checks; the review gate correctly reports `PENDING_HUMAN_REVIEW`, with zero approvals.

The reused report/timeline evaluation remained unchanged: 635/753 exact report rule sets, 466 matched obligations, 37 extra and 116 missed under developer-authored labels; 448/456 conditional deadlines in bounds. Timelines remained 35/60 exact and 53/78 rule-status comparisons matched, with zero false closures in those particular fixtures. These disagreements still require independent adjudication and are not clinical accuracy estimates.

Regenerate and verify `clinical-ml-20261026.json` against the exact base after any source change. All source decisions remain pending, including the newly changed motif code. These records cannot establish reviewer qualifications or authorize clinical use.

## Remaining requirements

Independent clinician review of every changed clinical line is still required, along with adjudicated reference labels, approved patient-separated validation data, intended-use acceptance criteria, subgroup evaluation and a supervised institutional pilot. The previously reported synthetic report/timeline disagreements are not clinically adjudicated. No claim is made that all possible defects have been eliminated.

The FHIR checks follow the R4 distinctions between a request's intent and status, and the requirement to establish a resource's patient subject directly. References: [HL7 ServiceRequest definitions](https://hl7.org/fhir/R4/servicerequest-definitions.html#ServiceRequest.intent), [HL7 resource references](https://hl7.org/fhir/R4/references.html).
