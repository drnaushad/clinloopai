# Radiology live-run: read the way a radiologist writes reports

**Date:** 2026-10-08 · **Data:** synthetic patients only (`data/radiology_test_bundle.json`) · **Evaluation time:** 2026-10-08 09:00 KST

Round 1 ran 16 radiology reports through the real FHIR ingestion endpoint
(`POST /api/v1/fhir/ingest`). The reports cover CT, chest radiographs, screening LDCT,
mammography and ultrasound, in English and Korean. They include negative reports and
one patient whose follow-up was done. The wording was chosen to stress the parser:
sizes in centimetres, X-rays, an adrenal nodule, a critical result and hedged phrasing.

## Round 1 result (16 patients)

| # | Study | Report (key sentence) | Before | After |
|---|---|---|---|---|
| RP-01 | CT chest (trauma) | Incidental **1.4 cm** spiculated RUL nodule, suspicious | ❌ **missed** (cm not read) | ✅ R003, 90 days, overdue |
| RP-02 | CT chest | 6 mm solid nodule, CT at 6–12 months | ✅ R003, 180 days | ✅ unchanged |
| RP-03 | **Chest X-ray** | 2.5 cm hilar mass, CT chest for further evaluation | ❌ **missed** (no interval, X-ray) | ✅ R030, 30-day default, overdue |
| RP-04 | Screening LDCT | Lung-RADS 4A, LDCT done 5 days after 3 months, now Lung-RADS 3 | ⚠️ 3 loops: R019 "late", duplicate R003 ×2 | ✅ R019 closed; R034 (6-month LDCT) open |
| RP-05 | CT abdomen | 18 mm **adrenal** nodule, CT in 12 months | ❌ **called a lung nodule**, 90-day alert | ✅ R030, CT in 12 months, not yet due |
| RP-06 | Mammography | BI-RADS 4B, biopsy recommended | ✅ R018 | ✅ unchanged |
| RP-07 | US liver (HBV) | Surveillance US due every 6 months | ✅ R028 overdue | ✅ unchanged |
| RP-08 | US thyroid | 1.6 cm TI-RADS TR4, FNA recommended | ❌ missed | ✅ R036 (biopsy/FNA), overdue |
| RP-09 | CT head | No acute abnormality | ✅ no alert | ✅ no alert |
| RP-10 | CT chest | **No** pulmonary nodule | ✅ no alert | ✅ no alert |
| RP-11 | CT abdomen | 8 mm hepatic lesion, MRI in 3–6 months | ✅ R031 | ✅ unchanged |
| RP-12 | CT chest | 9 mm nodule; follow-up CT **no-show** | ✅ R003 open | ✅ unchanged |
| RP-13 | **Chest X-ray** | Pneumonia, repeat radiograph in 6 weeks | ❌ **missed** | ✅ R033, overdue |
| RP-14 | CT pulmonary angiography | **Acute PE**, RV/LV 1.2, critical result | ❌ **missed** | ✅ R035 critical, top of worklist |
| RP-15 | 흉부 CT (Korean) | 우상엽 12 mm 결절, 3개월 후 추적 CT 권고 | ✅ R003 | ✅ unchanged |
| RP-16 | CT chest | Multiple nodules, largest 11 mm | ✅ R003 | ✅ unchanged |

**Before: 7 / 16 correct. After round 1: 16 / 16.** See round 2 below for 14 more patients.

![Worklist after ingestion](images/radiology_worklist.png)

## What was changed

- **Sizes:** `1.4 cm`, `14 mm`, `1.6 x 1.2 cm`, `12 밀리`. With two diameters, the size is their average (Fleischner 2017).
- **Organ-aware nodules:** the lung-nodule rule (R003) applies only to lung nodules.
  - An adrenal, thyroid, renal or liver nodule is tracked only through the radiologist's recommendation.
  - A nodule with no stated site is still treated as a lung nodule, because a false alert is safer than a miss.
- **Radiographs:** X-ray studies are recognised as completed studies, and a recommended follow-up radiograph becomes **R033**.
- **Recommendation without an interval:** "CT for further evaluation" gets a 30-day default, marked as a default.
  - Hedged wording ("if clinically indicated", "could be considered") is not tracked.
  - Backward-looking wording ("comparison with prior CT") is not tracked.
  - Image guidance ("US-guided biopsy") is not tracked as an imaging follow-up.
- **Screening:** when a Lung-RADS category is present, Lung-RADS governs and R003 does not fire.
  - Lung-RADS 3 → 6-month LDCT (**R034**).
  - Scheduled screening intervals get the same grace period as other radiology intervals, so a 5-day slip is not counted as a miss.
- **Critical findings (R035):** acute PE, aortic dissection, intracranial haemorrhage, pneumothorax, free air, ruptured AAA, torsion and cord compression need documented communication within 1 hour.
  - "Discussed with Dr …" or "담당의에게 전화로 통보함" in the report closes the loop.
  - "No PE", "chronic PE", "pneumothorax has resolved" and "evaluation for PE" do not open one.
- **Tissue sampling (R036):** a recommended biopsy or FNA (TI-RADS, renal mass, …) needs a biopsy within 30 days.
  - It does not fire when BI-RADS, Lung-RADS 4B/4X or R003 already covers the finding.
- **R003** is also closed by tissue sampling, which Fleischner lists as a >8 mm option.
- **Negation after the finding:** "is not identified", "has resolved", "없음" are now read as negations.

## Round 2: the five limitations from round 1

Round 1 left five gaps that made ClinLoop unsafe for real patients. All five are now addressed in
code and tests. Two of them can only be finished by people at the hospital.

| Round-1 limitation | What changed |
|---|---|
| **1. Body region not checked**: any CT closed a "CT recommended" loop | Every study gets body regions and organs from its title (an abdominal CT covers the adrenals, kidneys, pancreas and liver). Every recommendation gets the region it names, else the region of its finding, else the region of the study. A follow-up closes the loop only if the regions match. A study of unknown region does not close it, and the evidence chain lists studies "not counted (different or unknown body region)". |
| **2. Incidental findings tracked only with an explicit recommendation** | ACR white-paper management is now encoded for findings with no recommendation: adrenal (R037, R038), renal/Bosniak (R039, R040), pancreatic cyst (R041, R042), thyroid on CT/MRI/PET (R043), and TI-RADS on thyroid US (via R036/R032). Abdominal aortic aneurysm is covered by R044 and R045. Benign features are recognised (adrenal adenoma ≤10 HU, simple cyst, angiomyolipoma, "too small to characterise", pseudocyst). When the radiologist did write a recommendation for that organ, theirs is tracked instead. |
| **3. Fleischner nuance missing** | Covered now: solid, part-solid (with solid-component size) and ground-glass nodules; single and multiple; low and high risk, from smoking status (FHIR LOINC 72166-2), spiculation, upper lobe, emphysema and fibrosis. Unknown risk is managed as high risk. Stepped follow-up of a known nodule uses earlier reports or "stable for N years" in the text: solid stable ≥2 years is done, ground-glass every 2 years to 5 years, part-solid yearly to 5 years. Low-risk optional scans are not tracked. Growth of ≥2 mm, or a persistent solid component ≥6 mm, triggers work-up within 30 days (R046). Age < 35, known cancer or immunocompromise → human review. |
| **4. Critical-finding list was a hard-coded keyword list** | The list is a hospital-editable file with ACR category and a reporting window per finding. A clinical leader approves it on `governance.html`; the approval is bound to the file's hash, so any edit voids it. |
| **5. No specialist sign-off** | Each rule is signed off by a named specialist (approve / reject / request changes, with specialty and note). The sign-off is bound to the rule's fingerprint, and any change makes it "needs re-review". Shadow mode (`CLINLOOP_ENFORCE_SIGNOFF=1`) keeps unsigned rules off the worklist and out of escalation. A report-level validation tool (`src/validation/report_validation.py`) measures sensitivity and PPV per rule on blind radiologist labels. |

### Live run, round 2: 30 patients (14 new)

The test set (`data/radiology_test_bundle.json`) now has 30 synthetic patients, 34 reports, smoking
status and cancer history. New cases, evaluated on 2026-10-08:

| # | Case | ClinLoop |
|---|---|---|
| RP-17 | CT abdomen: 1.5 cm indeterminate adrenal nodule, no recommendation | R037: adrenal CT/MRI within 12 months (+ grace) |
| RP-18 | Adrenal CT recommended in 3 months; the only later study is a **head CT** | R030 **stays open**: head CT not counted (wrong region) |
| RP-19 | 2.4 cm enhancing solid mass, lower pole of the left kidney | R039: urology referral, overdue |
| RP-20 | 2.8 cm pancreatic cyst, no worrisome features | R041: MRI/MRCP at 6 months |
| RP-21 | Pancreatic cyst with mural nodule, main duct 9 mm | R042: EUS / specialist within 30 days, overdue |
| RP-22 | CT neck: 1.8 cm thyroid nodule, age 60 | R043: thyroid ultrasound |
| RP-23 | AAA 4.6 cm | R044: imaging at 6 months, overdue |
| RP-24 | AAA 5.3 cm in a woman, "without rupture" | R045: vascular surgery referral (≥5.0 cm in women) |
| RP-25 | 8 mm ground-glass nodule, never smoker | R003: CT within 12 months (+ grace) |
| RP-26 | 7 mm solid nodule, stable at 11 months, ex-smoker | first loop closed; next CT at 18–24 months tracked (high risk) |
| RP-27 | Nodule 6 mm → 9 mm in 6 months | R046: growth → work-up |
| RP-28 | 9 mm nodule in a patient with breast cancer | R003, flagged for human review (Fleischner does not apply) |
| RP-29 | Acute subdural haematoma, "discussed with Dr Park by telephone" | R035 closed by the documented communication |
| RP-30 | 4 mm solid nodule | no loop (Fleischner: no routine follow-up) |

The extended run found two more parser misses, which are now fixed and tested:

- In RP-19, "mass in the lower pole of the left kidney" was missed because the organ word was beyond the search window.
- In RP-24, "aneurysm … without rupture" was dropped because the rupture exclusion ignored the negation.

![Rule sign-off](images/governance_signoff.png)

With shadow mode on, the worklist showed nothing until a radiologist signed off R003 and R035 and
approved the critical-finding list. After that, only those loops appeared; the other 18 stayed in
shadow:

![Worklist in shadow mode](images/worklist_shadow_mode.png)

## Independent review

A separate reviewer ran awkward but realistic report wording through the new code. They
confirmed 22 problems, and all of them are fixed. Their 59 inputs are now permanent tests
(`TestIndependentReviewCases`). The most important ones:

- **Missed findings:**
  - A decimal size broke the organ match: "Right kidney 2.5 cm lesion, Bosniak IIF".
  - Sizes were averaged where guidelines use the longest axis: a 5.6 × 5.2 cm AAA fell below the surgical threshold.
  - "Compared to prior, new large pneumothorax" was dropped.
  - "No consolidation, large right pneumothorax" was read as negated.
  - The Korean 기간/6개월간 was read as 간 (liver).
  - "now 9 mm, was 6 mm" was not recognised as growth.
  - "Repeat CT in 3 months" and "Suggest follow-up CT" were not tracked.
- **False alarms:**
  - Korean negation 보이지 않음 was not recognised.
  - "no longer seen" was not read as a negation.
  - A normal head CT ("no haemorrhage, …, or acute infarct") was read as a stroke.
  - Resolving or chronic findings raised critical alerts.
  - Negated growth ("without growth") was counted as growth.
  - Hedged recommendations that had an interval were tracked.
  - "Pancreatic head" or "femoral neck" was read as a body region, so an MRI of the brain could close a pancreatic follow-up.
- **Communication:** "will be called to Dr Lee" and "discussed with the patient" no longer close a critical-finding loop. The communication must be in the past tense and to a clinician.
- **Crashes:** a partial FHIR date ("2026-01") or an absurd interval no longer crashes ingestion.
- **Additions:**
  - K-TIRADS (Korean Thyroid Association 2021) FNA thresholds.
  - Korean study titles without a space ("복부CT").

Still open from the review:
- Pancreatic cyst intervals are not adjusted by age.
- "CT or MRI" recommendations accept only the first modality.
- A recommended PET/CT or endoscopic ultrasound is not tracked as its own modality.
- Very long reports (>50 KB) take a few seconds to read.

## What still needs people, not code

1. **Specialist sign-off of all 46 rules** in `governance.html`, by radiologists and the relevant
   specialists (pulmonology, endocrinology, urology, GI, vascular surgery). Every "proposed" interval
   in the rule notes needs a local decision.
2. **The hospital's critical-finding list**: edit the example list, then approve it.
3. **Validation on real, de-identified reports.** Use `report_validation.py` to label a sample blind
   and measure sensitivity and PPV per rule, then run the chart review (`chart_review.py`). Both need
   IRB approval. The synthetic sheet's 100% agreement is circular: the same team wrote the reports
   and the labels.
4. **Local vocabulary.** Map the hospital's study titles and procedure codes; LOINC/RadLex Playbook
   codes would make body-region matching more precise than title text.

Remaining technical limits:
- The ACR age adjustments for pancreatic cysts are not encoded.
- Adrenal biochemical work-up is not tracked.
- The thoracic aorta is not covered.
- Nodules are matched across reports per patient, not per lobe.
- In-report communication is timestamped at report time + 1 minute.

## Reproduce

```bash
export CLINLOOP_API_TOKENS="your-long-admin-token:radiologist:admin"
python3 -m uvicorn src.clinloop_engine.api:app --port 8124 &
curl -X POST "http://localhost:8124/api/v1/fhir/ingest?evaluation_time=2026-10-08T09:00:00%2B09:00" \
     -H "Authorization: Bearer your-long-admin-token" -H "Content-Type: application/json" \
     --data-binary @data/radiology_test_bundle.json
# then open worklist.html, API http://localhost:8124, same token
# (the worklist's "Load synthetic radiology example" button does the same)
```

To see shadow mode, start the API with `CLINLOOP_ENFORCE_SIGNOFF=1`. Then sign off rules on
`governance.html` with a clinician token (`token:dr.name:clinician`).

Report-level validation on the synthetic sheet:

```bash
python -m src.validation.report_validation score --sheet data/radiology_validation_synthetic.csv
```
