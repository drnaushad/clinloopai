# How accurately does ClinLoop read reports? A blind evaluation

**Question:** given a radiology or pathology report, does ClinLoop open the follow-up obligations a careful
specialist would, with the right deadline, and stay quiet when nothing is needed?

**Short answer, on synthetic reports:**
- On a final set of 100 cases written blind and scored once before any fix, every report that needed
  follow-up raised at least one correct obligation in 97% of cases.
- No normal or benign report raised an alert.
- Deadlines were inside the specialist's window in 97% of cases.

These are synthetic reports from one writer. This is software verification, not clinical validation (see
"Limits" below).

## Method

1. **Blind cases.** A case writer, acting as radiologist and pathologist, wrote 270 report impressions with
   expected rules and deadline windows. The writer saw only the rule catalogue
   ([`tests/report_eval/rule_catalog.json`](../tests/report_eval/rule_catalog.json)), never the code.
   - **Coverage:** CT, CTA, MRI, X-ray, ultrasound, mammography, LDCT screening, PET/CT and pathology.
   - **Mix:** 30% Korean; 37% need no follow-up.
   - **Hard variations:** abbreviations, numbered lists, a category in the sentence after its finding,
     negations, hedged advice and prior-study comparisons.
2. **Three sets.**
   - **Development (85):** used to find and fix defects.
   - **Held-out (85):** scored once, then used for fixing.
   - **Confirmation (100):** written after the fixes and scored once.
3. **The real pipeline.** Each case becomes FHIR resources (Patient, smoking status, conditions, the
   report), then goes through `bundle_to_events` and `ClinLoopDetector`.
4. **Two scores.**
   - **Strict:** exact rule ids.
   - **Clinically equivalent:** the same finding gets the same kind of follow-up. One alert per finding is
     by design: when the guideline rule and the radiologist's own recommendation ask for the same study,
     one follow-up closes both. Strict scoring counts that as a miss; the equivalent score does not.

To reproduce:
```
python tests/report_eval/run_eval.py tests/report_eval/cases.json confirm --show
```

## Results

| Set (scored before fixing it) | Equivalent | ≥1 correct obligation | No alert when none needed | Deadline in window |
|---|---|---|---|---|
| Development, baseline | n/a | 81.1% | 96.9% | 97.7% |
| Held-out, after development fixes | 82.4% | 81.5% | 80.6% | 97.7% |
| **Confirmation, after held-out fixes** | **97.0%** | **96.8%** | **100%** | **96.7%** |
| All 270, after every fix (not an unbiased number) | 100% | 98.8% | 100% | 98.2% |

**The gap between development and held-out matters.** The development fixes overfitted at first: they
reached 100% on development, but only 82% on new cases. The confirmation set exists to measure honestly
after the second round of fixes.

## Defects found and fixed (each now has a test in `tests/test_report_accuracy.py`)

### Missed critical findings
- "Ruptured 7.5 cm infrarenal **AAA**" did not match.
- **Large-vessel occlusion** missed in three wordings: "acute M1 occlusion", "MCA occlusion", "중대뇌동맥
  급성 폐색".
- Korean **뇌내출혈**, 뇌실내 출혈 and 경막외 혈종 missed.
- Korean "old" or "resolved" wording (이전, 기존, 흡수됨, 호전) still raised a critical alert; it no longer
  does.

### A follow-up silently dropped
- An MRI recommended for a **pancreatic cyst** was taken to cover an **aortic aneurysm's** 3-year
  surveillance, because both organs are in the abdomen.
- Recommendations are now matched to the organ they name.

### Korean wording
- **Kidney:** 우신, 좌신, 콩팥 and "우측 신" are now read as kidney; 신호 (signal) is not.
- **Renal mass:** 조영증강되는 고형 종괴 and 벽재결절 count as suspicious. "신세포암 배제 위해" (to exclude
  RCC) counts as indeterminate, not suspicious.
- **Negation scope:** a negation now ends at a comma: "낭성 병변, … 고형 성분 없음" negates the solid
  component only, not the cyst.
- **Recommendations:**
  - "3개월 후 dynamic liver MRI 권고";
  - "추적 흉부 X선 권고";
  - "… X선 f/u … 확인 바람";
  - "조영증강 CT 권고".
- **Nodule state:** 지속됨 (persistent); 새로 생긴 고형 성분 (new solid component).

### Category and context
- **Category in the next sentence:** "… renal cystic mass. Bosniak III." is now read with its lesion.
- **Prior categories:** a quoted earlier category ("previous Lung-RADS 3, now Lung-RADS 2") is not taken as
  the current one.
- **Differentials:** "hyperdense cyst versus solid mass" lists possibilities. It is indeterminate, not a
  suspicious mass.

### Benign or ended follow-up recognised
- Adrenal contrast washout (absolute ≥ 60% or relative ≥ 40%) is read as an adenoma.
- "More than 2 years of stability", "since 03/2024" and "consistent with a benign etiology" are read for
  lung nodules.
- A pancreatic cyst under 1.5 cm that has been stable for 5 years or more ends surveillance.
- Benign thyroid cytology (Bethesda II) ends the TI-RADS size follow-up.
- "Without suspicious features" is no longer read as suspicious.

### Shorthand
- "RUL nod 7mm … f/u CT 6-12 mo", "MR angiography" and "MRCP" are now read.
- "MRI-targeted biopsy" is a biopsy, not an MRI.
- "(or EUS-FNA)", offered as an alternative to a tracked MRI, is not a second obligation.
- "A new 7 mm solid component" is read as growth.

### Pathology
- High-grade cervical cytology (HSIL, ASC-H, AGC, CIN 2–3) and high-risk breast lesions (ADH, ALH, LCIS) now
  open R009.

A CI test (`TestBlindCaseSets`) keeps the 270 cases at or above 97% equivalent and 97% specificity.

## Images (separate question)

ClinLoop's job is the follow-up loop, not reading images. Image findings come from plug-in models.

**Test:** the open research model TorchXRayVision, run on 77 public chest X-rays (ieee8023
covid-chestxray-dataset: 60 pneumonia, 17 no finding) through the app's own DICOM path.
- **Discrimination (AUC):** pneumonia 0.85, lung opacity 0.77, consolidation 0.78.
- **At its operating point:** sensitivity 90%, specificity 47%.

**What this means:**
- That is too many false positives for clinical use, which is why research models are off by default.
- Disease detection on CT, MRI or ultrasound images is not validated here. It needs approved vendor
  products, see [`VENDOR_IMAGING_AI.md`](VENDOR_IMAGING_AI.md).
- CT organ measurement (aorta, spleen) is measurement, not diagnosis.

## Limits

- **Synthetic data:** all reports are synthetic, from one writer. Real reports are longer, messier and
  more varied, and include addenda, templates, OCR noise and dictation errors.
- **What is scored:** obligation opening only. Loop closure and the timing of real follow-ups are tested
  elsewhere (`tests/`), not here.
- **Same writer for every set:** the confirmation set is independent of the code, but not of the writer's
  style.
- **Before clinical use:**
  - a retrospective chart review on the hospital's own reports, against two specialists, with κ;
  - shadow-mode operation;
  - sign-off of each rule (`governance.html`).
