# Stage 1A: retrospective validation on MIMIC (protocol addendum)

**Status: draft for the clinical lead and the principal investigator.** Version 0.1, October 2026.
An addendum to [`STUDY_PROTOCOL.md`](STUDY_PROTOCOL.md) §4 (Stage 1). It does not replace Stage 1 in a
Korean hospital (Stage 1B); it answers the part of Stage 1 that public credentialed data can answer.

## 1. Question and limits

**Question:** on real clinical records, does ClinLoop correctly identify the follow-up obligations a
record creates, and, for the few obligations whose follow-up is also recorded in hospital, does it
correctly tell open from closed?

**What Stage 1A can show:** accuracy of **obligation detection** in radiology reports (Part A) and of
**loop status** for three in-hospital monitoring rules (Part B), on English-language records from one
US academic centre.

**What it cannot show,** because MIMIC-IV holds intensive-care and emergency stays and little care after
discharge: whether outpatient follow-up happened (clinic visits, outpatient imaging, referrals, patient
notification), whether critical results were communicated (no call documentation), performance on
Korean or mixed Korean–English reports, or anything about clinical benefit. These stay with Stage 1B and
later stages. Results must be reported with this limitation stated.

## 2. Data and access

| Source | Used for | Access |
| --- | --- | --- |
| MIMIC-IV (`hosp/`, `ed/`) | Patients, admissions, labs, prescriptions, cultures | PhysioNet credentialed access, CITI "Data or Specimens Only Research" training, signed data use agreement |
| MIMIC-IV-Note (`note/radiology`) | Radiology reports (Part A) | Same, separate data use agreement |
| MIMIC-CXR (report text only) | Chest X-ray reports (Part A) | Same, separate data use agreement |

**Every person who sees MIMIC data needs their own credential**: the study coordinator and each
reviewer. Ethics: MIMIC is de-identified under a data use agreement; whether this analysis also needs
an ethics board's review or exemption depends on the institution. The principal investigator obtains
that decision in writing before starting.

## 3. Data handling (binding)

1. MIMIC data stays on the approved machine. It is never uploaded, emailed, pasted into a chat or an
   issue tracker, or given to an online AI service (including AI coding assistants). This is a condition
   of the data use agreement.
2. ClinLoop's tools run locally and print counts only. Review sheets and packets stay on the approved
   machine; reviewers work there.
3. Only aggregate results leave: the `score` and `analyze` summaries (rates, intervals, counts per
   rule). Before sharing, the coordinator checks that no table identifies a single stay (no free text,
   no identifiers, no dates).
4. Analysis files are deleted at the end of the study as the data use agreement requires.

## 4. Part A (primary): obligations in radiology reports

| Item | Definition |
| --- | --- |
| Rules | The 21 radiology-report rules: R003, R018–R020, R030–R046 (lung nodules, BI-RADS 4/5, Lung-RADS, radiologist-recommended imaging and biopsy, incidental adrenal, renal, pancreatic and thyroid findings, aortic aneurysm, critical findings). R035 is scored for *detecting* a critical finding only; its communication cannot be judged in MIMIC |
| Unit | One radiology report, read on its own (`report_validation.py`: earlier reports are not used, so stepped Fleischner intervals are not exercised) |
| Sample | Reports of randomly drawn subjects (`mimic_ingest --sample`), then a random sample of reports (`--sample` on the template), seed 42 |
| Reference standard | A radiologist, blind to ClinLoop, lists the obligations each report creates (`expected_rules`; explicit `NONE` = no obligation; blank or incomplete labels remain unreviewed) under the guideline each rule cites, using the report and the context columns (age, sex; smoking and cancer history where documented). For a feasibility pilot a second radiologist labels a prespecified random 20 % independently; before a confirmatory accuracy claim, require independent double review and third-person adjudication of all reference disagreements as specified in the 29 October evidence plan |
| Primary endpoints | Sensitivity and PPV over all report × rule obligations pooled (`score`: `overall`), with Wilson 95 % intervals; per rule, the same figures and every disagreement listed for adjudication |
| Targets | Sensitivity ≥ 85 % and PPV ≥ 70 % for the imaging-findings family (protocol §7); per-rule results are descriptive |
| Agreement | Cohen's κ between the two radiologists on the double-labelled subset (any obligation yes / no); κ ≥ 0.6 required (protocol §7) |
| Sample size | About 140 reference obligations give a ± 5 % interval at 90 % sensitivity. Label a first batch of 200 reports to see how many obligations a report carries, then size the rest: if one report in five carries one, about 700 reports in total. Reports from one patient are correlated; draw many patients with few reports each rather than the reverse |

## 5. Part B (secondary): loops closed in hospital

| Item | Definition |
| --- | --- |
| Rules (proposed; the clinical lead confirms) | R007 warfarin dose change → INR recheck (7 days); R010 medication change → follow-up labs (14 days); R015 positive blood culture → repeat culture (48 hours). Both the trigger and the follow-up are recorded in MIMIC's structured data during a stay |
| Unit | One loop on one patient's whole record, judged at the end of that patient's own record (`--per-patient-end`: MIMIC shifts dates per patient) |
| Sample | `chart_review.py sample --rules R007,R010,R015 --per-stratum 40`: up to 40 loops per rule and predicted class, weighted back to the population |
| Reference standard | Two clinicians, blind to ClinLoop, answer "Was the required follow-up completed within the window?" (yes / no / unclear) from the full record; a third adjudicates disagreements. "Unclear" includes windows that run past discharge; those loops are counted and reported but left out of the primary estimate |
| Endpoints | Weighted sensitivity, specificity, PPV and NPV for "loop not closed in time", stratified-bootstrap 95 % intervals, Cohen's κ (`chart_review.py analyze`) |

## 6. Procedure (on the approved machine)

```
# 0. Record the logic being measured
git rev-parse HEAD
python -c "from src.clinloop_engine.governance import ruleset_version; print(ruleset_version())"

# 1. Extract the cohort to FHIR (counts only are printed)
python -m src.clinloop_engine.mimic_ingest --mimic <mimic-iv> --note <mimic-iv-note> --cxr <mimic-cxr> \
       --sample 2000 --out fhir/

# 2. Part A: blind labelling sheet, then score
python -m src.validation.report_validation template --fhir fhir/ --out sheet.csv --sample 200
#    (radiologists fill expected_rules on the approved machine)
python -m src.validation.report_validation score --sheet sheet.csv --out partA.json

# 3. Part B: blinded packet and separate key, then analyse
python -m src.validation.chart_review sample --fhir fhir/ --out review/ --per-patient-end \
       --rules R007,R010,R015 --per-stratum 40
#    (reviewers fill review/review_packet.csv; the coordinator keeps review/prediction_key.csv apart)
python -m src.validation.chart_review analyze --packet review/review_packet.csv --key review/prediction_key.csv
```

## 7. Locking and over-fitting

- The commit and the rule-set version are recorded before sampling, and the rules are not changed
  while labelling is under way.
- Errors found in Stage 1A will lead to rule fixes. A fixed rule is **not** re-scored on the reports
  that revealed the error: that would measure the fix against the data it was fitted to. Either keep
  a held-out half of the labelled reports untouched until the final run, or label a fresh sample after
  the fix. The report states which.
- Fixes to clinical logic follow AGENTS.md §5 (clinician review, a test per behaviour).

## 8. Reporting

Report following TRIPOD+AI (prediction and classification) and STARD (diagnostic accuracy) where they
apply: data source and version, dates of extraction, rule-set version, sampling, reference standard
and reviewers' qualifications, flow of reports and loops (including "unclear" and excluded), results
with intervals, disagreements by type, the limitations in §1, and the over-fitting control in §7.

## 9. Decision

| Result | Next step |
| --- | --- |
| Part A meets the targets | Evidence for the report-reading component; take the protocol to a Korean hospital for Stage 1B (loop closure, Korean reports) |
| Part A misses a target | Fix, then re-test on fresh or held-out reports (§7); rule families that still fail are left out of later stages |
| Part B | Supporting evidence only; Stage 1B decides loop-closure accuracy |

Passing Stage 1A does not make ClinLoop ready for clinical use (see
[`regulatory/CLINICAL_EVALUATION_PLAN.md`](regulatory/CLINICAL_EVALUATION_PLAN.md)).

## 10. Roles and sign-off

| Role | Name | Credentialed (PhysioNet) | Signed | Date |
| --- | --- | --- | --- | --- |
| Principal investigator | | | | |
| Study coordinator (runs the tools, keeps the key) | | | | |
| Radiologist 1 | | | | |
| Radiologist 2 (20 % double labelling) | | | | |
| Clinician reviewers, Part B (two) and adjudicator | | | | |
| Clinical lead (confirms Part B rules) | | | | |


## 11. Evidence integrity amendment, 29 October 2026

The [candidate evidence plan](reviews/EVIDENCE_REVIEW_20261029.md) specifies the additional confirmatory requirements. Do not treat this protocol's sample-size sketch, targets or unclustered Wilson intervals as an approved statistical analysis plan. A statistician must set sample size, patient-level dependence handling and decision bounds before the untouched test set is opened. The existing chart toolkit scores only obligations the engine identified; an independently enumerated reference cohort is required to measure missed obligations. Existing AI-reviewed and development-exposed Open-i labels cannot serve as independent confirmatory truth. All source/model/rule hashes must describe the exact evaluated candidate. No institutional, ethics or regulatory approvals are created by this amendment.
