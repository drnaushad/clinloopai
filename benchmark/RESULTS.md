# ClinLoop-Bench v1.0 — baseline results

Split: **test**. Values are %, with seeded (42) 1,000-sample bootstrap 95% CIs over records.
Regenerate with `python benchmark/baselines/run_baselines.py`.

**Caveat:** the rules engine was developed against these blind rounds (each round was scored once before fixes, then defects were fixed), so its scores here are *after-fix* and optimistic. The first-pass blind scores are in `docs/ACCURACY_EVALUATION.md`.

## T1 (English reports) and T3 (Korean / mixed reports): report -> follow-up obligation

| Baseline | Task | n | Rule P | Rule R | Rule F1 | Finding F1 | Needs-follow-up F1 | Specificity | Exact |
|---|---|---|---|---|---|---|---|---|---|
| ClinLoop rules engine | T1 | 315 | 92.5 [88.6-95.8] | 76.0 [72.1-79.7] | 83.4 [79.8-86.6] | 100.0 [100.0-100.0] | 100.0 [100.0-100.0] | 100.0 [100.0-100.0] | 80.6 [76.2-84.8] |
| ClinLoop rules engine | T3 | 221 | 91.6 [87.0-95.6] | 82.0 [77.1-87.2] | 86.5 [82.3-90.7] | 99.7 [99.0-100.0] | 100.0 [100.0-100.0] | 100.0 [100.0-100.0] | 85.1 [80.5-89.6] |
| Keyword (recommend/follow-up/권고/추적) | T1 | 315 | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 70.8 [65.6-75.8] | 57.3 [48.4-66.2] | 21.3 [16.8-26.3] |
| Keyword (recommend/follow-up/권고/추적) | T3 | 221 | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 66.9 [59.4-72.7] | 59.5 [48.4-70.0] | 19.9 [14.9-25.3] |

## T2: patient timeline / FHIR records -> loop status at the evaluation time

| Baseline | n | Rule P | Rule R | Rule F1 | Status acc. | Overdue acc. | False closures | Needs review |
|---|---|---|---|---|---|---|---|---|
| ClinLoop rules engine | 209 | 100.0 [100.0-100.0] | 91.4 [87.7-95.4] | 95.5 [93.4-97.6] | 98.7 [96.6-100.0] | 100.0 [100.0-100.0] | 0 | 71 |
| Keyword (recommend/follow-up/권고/추적) | 209 | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0.0 [0.0-0.0] | 0 | 0 |

Evidence-span overlap is not reported: v1.0 has no gold evidence spans (see README, limitations).
The keyword baseline emits a generic `FOLLOW_UP` label, so its rule-level scores are zero by design; its needs-follow-up F1 is the meaningful comparison.
