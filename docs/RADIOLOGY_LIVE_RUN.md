# Radiology live-run: 16 reports, read the way a radiologist writes them

**Date:** 2026-10-08 · **Data:** synthetic patients only (`data/radiology_test_bundle.json`) · **Evaluation time:** 2026-10-08 09:00 KST

We ran 16 radiology reports through the real FHIR ingestion endpoint
(`POST /api/v1/fhir/ingest`). The reports cover CT, chest radiographs, screening LDCT,
mammography and ultrasound, in English and Korean. They include negative reports and
one patient whose follow-up was done. The wording was chosen to stress the parser:
sizes in centimetres, X-rays, an adrenal nodule, a critical result and hedged phrasing.

## Result

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

**Before: 7 / 16 correct. After: 16 / 16.** 170 automated tests pass, including 17 new ones
built from these cases and from false-positive checks.

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

## Known limitations (radiologist review)

1. **Modality, not body region:** any CT closes a "CT recommended" loop, even a CT of a different body part. Matching by body region needs procedure codes (LOINC/RadLex playbook).
2. **No incidental-findings guidance without a recommendation:**
   - ACR white-paper management of adrenal, renal, pancreatic-cyst, thyroid and AAA findings is not encoded.
   - These findings are tracked only when the radiologist writes a recommendation.
3. **Lung-RADS and Fleischner nuance:**
   - Not encoded: subsolid nodules, the Fleischner low-risk vs high-risk choice, Lung-RADS 4B "PET/CT" alternatives, and stepped follow-up after a stable nodule.
4. **Critical findings use a keyword list.** Each hospital must review the list and the 1-hour window.
   - Communication found in the report text is timestamped at report time + 1 minute; the actual time of the call is not parsed.
5. **Report text only:**
   - Free-text conclusions are read; structured findings from the PACS or RIS are not.
   - Addenda and amended reports need a site-specific feed.
6. **All rules are `pending_specialist_review`.** The reports here are synthetic.
   - Before any clinical use, a radiologist must sign off each rule.
   - Stage-1 chart review on real, de-identified reports is also required (`src/validation/chart_review.py`).

## Reproduce

```bash
export CLINLOOP_API_TOKENS="your-long-admin-token:radiologist:admin"
python3 -m uvicorn src.clinloop_engine.api:app --port 8124 &
curl -X POST "http://localhost:8124/api/v1/fhir/ingest?evaluation_time=2026-10-08T09:00:00%2B09:00" \
     -H "Authorization: Bearer your-long-admin-token" -H "Content-Type: application/json" \
     --data-binary @data/radiology_test_bundle.json
# then open worklist.html, API http://localhost:8124, same token
```
