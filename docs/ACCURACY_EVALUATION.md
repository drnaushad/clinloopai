# How accurately does ClinLoop read reports? A blind evaluation

**Question:** given a radiology or pathology report, does ClinLoop open the follow-up obligations a careful
specialist would, with the right deadline, and stay quiet when nothing is needed? When follow-up
happens, does it close the right obligation, and only that one?

**Short answer.** The best guides are the first-pass scores on sets nobody had looked at.

- **Short impressions** (clean, one-paragraph): **97%** of reports handled correctly.
- **Full, real-style reports** (sections, addenda, Korean-English shorthand, scanned-text noise):
  - **80%** on the first such set;
  - **87.5%** on a second, untouched set after a round of fixes;
  - no false alarms on 96% of normal reports.
- **Follow-up tracking** over patient timelines:
  - about **85%** of findings got the correct status (done, done late, pending, missed);
  - after the fixes, **0 false closures**. A follow-up is never shown as done when it was not.

Every defect found was fixed and is covered by a test. All 450 cases and 60 timelines now pass, but
those are no longer unbiased numbers. The steady gap between first-pass scores and after-fix scores
is the honest message: real report wording has a long tail. These are synthetic reports, so this is
software verification, not clinical validation (see "Limits" below).

## Method

1. **Blind cases.** Three independent case writers, acting as radiologists and pathologists, wrote:
   - 270 short report impressions;
   - 180 full real-style reports;
   - 60 patient timelines.

   Each case has its expected rules and deadline windows. The writers saw only the rule catalogue
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

To reproduce (the command scores the current code, so it can differ from the table below after
later fixes to the report readers):
```
python tests/report_eval/run_eval.py tests/report_eval/cases.json confirm --show
```

## Results

### Reports: does the right obligation open?

| Set (each scored once, before it was used for fixing) | Cases | Equivalent | ≥1 correct obligation | No alert when none needed | Deadline in window |
|---|---|---|---|---|---|
| Development, baseline | 85 | n/a | 81.1% | 96.9% | 97.7% |
| Held-out (clean impressions) | 85 | 82.4% | 81.5% | 80.6% | 97.7% |
| Confirmation (clean impressions) | 100 | **97.0%** | **96.8%** | **100%** | **96.7%** |
| Real-style full reports (new writer) | 100 | **80.0%** | 81.0% | 81.1% | 98.0% |
| Real-style confirmation (third writer) | 80 | **87.5%** | 83.0% | 96.3% | 86.4% |
| All 450 after every fix (not unbiased) | 450 | 99.8% | 97.5% | 100% | 98.6% |

**Why the real-style sets matter.** Every rise in score came from fixing what one set revealed, and the
next untouched set always found new wording. Clean impressions are not what hospitals send. Full
reports carry:
- findings in the FINDINGS section only;
- addenda that change or withdraw advice;
- Korean endings (권함, 요망) and Korean-English shorthand;
- quoted guideline thresholds and prior sizes;
- scanning errors ("1O rnm s0lid").

### Follow-up: does the right event close the right obligation?

Patient timelines: a first report, then later events (imaging of some modality and body part,
referrals, specialist visits, biopsies, later reports), and the expected status at an evaluation date.
Score them with:
```
python tests/report_eval/run_timelines.py tests/report_eval/timelines.json --show
```

| Set (first pass) | Timelines | Findings with the right status | False closures (not done, shown done) |
|---|---|---|---|
| Timelines, first set | 40 | 83.8% | **3** |
| Timelines, confirmation set | 20 | 85.0% | **0** |
| All 60 after fixes | 60 | 93.0% | **0** (enforced in CI) |

**The 3 false closures**, now fixed:
- a cardiology referral closed a Lung-RADS 4B work-up;
- a nephrology referral closed a suspicious-kidney-mass referral;
- a liver biopsy closed a pancreatic-cyst work-up.

**The fix.** Work-up rules now need a referral to a service that can carry out the work-up, and a
biopsy that names its site must be of the right organ.

**A design question, not a defect.** R009 (abnormal pathology) needs both a patient notification and
a specialist referral. Both blind writers counted a referral alone as done, so these 4 obligations
stay "missed" until a notification is recorded. Whether a referral should be enough is the hospital's
decision.

**One configuration difference.** The example critical-findings list includes acute appendicitis (ACR
category 2, report within 6 hours). One writer did not consider it critical. Each hospital edits that
list.

### Round 8 (October 2026): Korean hospital style, hard English reports, then a confirmation set

Same method. Three new writers saw only the rule catalogue. Each set was scored once against the code
as it stood, before anything was changed for it:

| Set (first pass, code untouched for it) | Cases | Equivalent | No alert when none needed | Deadline in window |
|---|---|---|---|---|
| Korean hospital-style full reports | 80 | 87.5% | 78.6% | 100% |
| Hard English reports (addenda, corrections, multi-finding, OCR) | 80 | 82.5% | 60.7% | 100% |
| **Confirmation, written after the fixes (40 Korean, 40 English)** | 80 | **91.2%** | **93.1%** | 97.6% |
| All 690 after every fix (not unbiased) | 690 | 99.7% | 99.6% | 99.3% |

**The confirmation set is the honest number for this round.** It improves on the earlier untouched
real-style sets (80% and 87.5%), but the long tail is still there. Korean-language reports remain
weaker than English ones on first pass (87.5% against 95.0% in the confirmation set).

**What the round found**, all fixed with a test:
- **Missed critical finding:** acute PE written "pulmonary thromboembolism", "PTE" or "폐동맥 혈전색전";
  "[CRITICAL]" as a tag.
- **Missed follow-up:**
  - BI-RADS 0 recall;
  - pathology "atypical cells; malignancy cannot be excluded", "suspicious for carcinoma";
  - thyroid Bethesda III–VI;
  - Korean "6주 뒤 Chest PA … 요망";
  - focal FDG uptake in the thyroid far from the word 결절;
  - a "*** CORRECTED REPORT ***" in mid-report that raises the Lung-RADS category.
- **A pre-existing gap, found while testing a fix:** "postoperative free air with contrast leak" was
  never critical, because "postoperative" marked the air as expected. A described leak or perforation
  now always makes free air critical.
- **False alarms:**
  - a thyroid or adrenal nodule after "Rt."/"Lt." (or "adrenal에") read as a lung nodule;
  - guideline thresholds read as sizes ("6 mm 미만", "the 2.5 cm FNA threshold");
  - one nodule described in FINDINGS and again in IMPRESSION counted as two, which changed the
    Fleischner branch;
  - "No new nodules" setting "multiple";
  - the radiologist's "no further follow-up / 추가 검사 불필요" ignored;
  - an addendum or correction that re-categorises or withdraws advice ignored;
  - history and comparison lines read as current findings;
  - expected post-operative free air;
  - a Korean list of negated trauma findings ("기흉, 혈흉 없음").
- **A documented call missed:** "Called to and acknowledged by Dr X".

**Two of the fixes first introduced misses, caught before commit by their own tests and by the timelines:**
- The Korean list negation hid a measured nodule ("8 mm 결절, 흉수 없음"). A measured finding is now
  always present.
- Skipping history lines skipped a growing nodule on a line that read "COMPARISON: … FINDINGS: …".
  A history line now ends at the next section heading.

These two are the reason every fix is checked in both directions: the false alarm it removes, and
the real finding it must not hide.

**Not defects:**
- When a report both recommends a study and matches a guideline rule for the same finding, the
  radiologist's recommendation is tracked (one alert per finding; the same follow-up closes it).
- A critical finding whose call is documented in the report opens and closes at once.
- A BI-RADS 4 biopsy described only in an addendum keeps the loop visible until the biopsy is in the
  record, by design (fail toward a person).

### Round 9 (October 2026): one more untouched set

A new writer wrote 63 reports (10 Korean, 20 needing no follow-up) from the rule catalogue only, without
reading the code: CT, CTA, MRI, ultrasound, radiographs, mammography, LDCT screening, PET/CT and pathology,
with negations, addenda, stable and benign findings, OCR noise and multi-finding reports. Scored once:

| | Cases | Equivalent | No alert when none needed | Deadline in window |
|---|---|---|---|---|
| Round 9, first pass | 63 | **93.7%** | 90.0% | 100% |
| Round 9 after the fixes below (not unbiased) | 63 | 100% | 100% | 100% |
| All 753 after every fix (not unbiased) | 753 | 99.7% | 99.6% | 99.3% |

**What it found**, each fixed with a test:
- **False critical alert:** "CLINICAL HISTORY: Prior pulmonary embolism 2024" before "No pulmonary embolism"
  opened the one-hour critical rule. The history sentence is now skipped for critical findings, but only
  that sentence: in "Clinical history: trauma. Large right pneumothorax." the finding is still read.
- **A retracted finding still tracked:** an addendum saying the "nodule" was the nipple shadow withdrew
  the advice, but the Fleischner rule re-derived it from the nodule. An addendum that says there is no
  nodule now removes it. When the report has several nodules and the addendum does not say which one,
  all stay for a person to review.
- **Missed nodule in scanned text:** OCR's "nodu1e" became "noduie" (a '1' between letters was always
  read as 'i'). Finding words now read '1' as 'l'; "rnonths" and "recornrnended" are repaired.

**Not a defect:** a ruptured aneurysm opens the critical rule and the vascular referral (R045), as
designed; the writer had expected the critical rule only.

## Defects found and fixed (each now has a test in `tests/test_report_accuracy.py`)

### Found by the real-style and timeline sets
- **Follow-up matching:**
  - wrong-specialty referrals and wrong-organ biopsies no longer close work-ups;
  - an imaging recommendation no longer replaces a work-up rule;
  - a recommendation with no interval takes the guideline's interval instead of 30 days.
- **Korean wording:**
  - recommendation endings 권함, 권합니다, 추천, 요망, 시행 권함;
  - "f/u CXR", "f/u CTA", "MRI (dynamic)";
  - "BI-RADS 범주 4";
  - "선생님께 … 구두 보고함" as communication;
  - "변화 없음" (no change) is not absence;
  - "암 병력 없음" (no cancer history) is a negation;
  - bracketed addenda "[추가판독 …]".
- **Addenda:** revised findings replace the report's own; a withdrawn recommendation is no longer
  tracked; a Bosniak class in the addendum re-classifies the kidney lesion.
- **Scanned text:** "1O rnm s0lid", "Fle1schner", and words broken across lines.
- **Numbers that are not measurements:** "(<6 mm)", "below the FNA threshold (1.5 cm)"; exam names
  ("PULMONARY EMBOLISM PROTOCOL") are not findings.
- **Negation:** the middle item of a list ("without septation, mural nodule, calcification or enhancing
  component") is negated, but a measured item in a list ("9 mm nodule") is still taken as present.
- **Findings:**
  - resolved nodules;
  - the organ right before "nodule" wins ("adrenal nodule in a patient with lung cancer");
  - "solid portion", including a comparison in the next sentence;
  - "grown from 6 mm to 10 mm";
  - "MPD 8 mm", and an IPMN with no organ word;
  - thin smooth septa are not suspicious;
  - "annual CT angiography";
  - "acute SDH".
- **Patient context:** a radiologist's "known malignancy" counts.
- **Pathology:**
  - the diagnosis section is read, not the clinical history;
  - "X: not identified" is a negation;
  - EIN (endometrial precancer) is abnormal.

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

CI keeps all 450 cases at or above 97% equivalent and 97% specificity (`TestBlindCaseSets`), and fails on
any false closure among the 60 timelines (`tests/test_followup_matching.py`).

## Guideline reports (R060–R065)

**What is read:**
- **Lab results:** HIV screening tests (R060), hepatitis B surface antigen (R061), TB infection tests (R062).
- **Colonoscopy and polyp pathology reports:** surveillance intervals (R063).
- **Echocardiogram reports:** severe aortic stenosis (R064) and reduced ejection fraction (R065).

The readers are in `src/clinloop_engine/guideline_reports.py`. Each alert carries the words or numbers that
decided it.

**Method:**
- **Two independent authors.** Each wrote a blind set of synthetic FHIR records from the guideline
  definitions alone (CDC, AASLD, ATS/IDSA/CDC, USMSTF 2020, ACC/AHA 2020, AHA/ACC/HFSA 2022). Neither saw
  ClinLoop's code.
- **The sets:**
  - `tests/blind_reports_2`: 157 cases.
  - `tests/blind_reports_3`: 100 cases, written in the style of real hospital documents (mixed Korean and
    English, flattened measurement tables, QuantiFERON panels sent as five results, multi-part pathology,
    records over several years).
- **Scoring:** each set was scored once, before any fix based on it. The second set was scored only after
  the code was frozen.

**Results:**

| Set (first pass) | Cases | Fully correct | Sensitivity | Precision | Deadline correct |
|---|---|---|---|---|---|
| First set (`blind_reports_2`) | 157 | 95.5% (95% CI 91.1–97.8) | 95.0% | 98.0% | 100% |
| **Confirmation set (`blind_reports_3`)** | 100 | **96.0% (95% CI 90.2–98.4)** | **95.0%** | **100%** (no false alarms) | 98.2% |

- **Status:** where an obligation was found, its status (open or done) was correct in 100% of cases on both
  sets.
- **After fixes:** both sets now pass in full. These after-fix scores are not unbiased.

**Defects found by the blind sets and fixed** (each has a test in `tests/test_guideline_reports.py`):
- **"Exposure to HIV" read as a diagnosis:** a needlestick exposure on the problem list was taken as known
  HIV, so a reactive screen was ignored. Exposure, PrEP and screening entries are now excluded.
- **Reference ranges and comments read as the result:**
  - "REACTIVE … ref: Non-reactive" and "양성 … ** 이전(2021) 음성 **" were read as negative.
  - The first result word now decides. Reference ranges and comments are ignored.
- **Size limits read as polyps:** "four adenomas, all < 10 mm" was read as a 10 mm polyp. Sizes after "<",
  "less than" or "under" are limits.
- **Adenoma counts:** counts written as "(x5)", "5 of 5", part ranges ("A-E.") and Korean ("6개: 모두 선종")
  were missed.
- **"Sessile serrated lesion WITH low-grade dysplasia"** was missed because of the hyphenated qualifier.
- **"BBPS 3-3-3":** three segment scores were read as a total of 3, meaning inadequate preparation.
- **Cancer on pathology:**
  - When the pathology of the same colonoscopy shows cancer, the endoscopy report must not open
    surveillance. Cancer follows the pathology pathway (R009).
  - High-grade dysplasia is not cancer and stays on surveillance.
- **Unsited pathology:** a polyp pathology report that names no organ ("Polyps x7: tubular adenomas") is
  read as colonic unless another site (stomach, duodenum) is named.

**What these sets do not show:**
- **Sparse records:** with only one or two records per patient, many open obligations are shown as "needs
  human review" (sparse record) rather than "open". Both still put the obligation on the worklist.
- **No real-data test:** the MIMIC-IV demo used for the real-data test contains none of these tests or
  reports, so their accuracy on real hospital data is still unmeasured.
- **Thresholds:** they follow one reading of each guideline (for example TST ≥ 10 mm; intervals over 3
  years not tracked). A hospital's specialists must review and sign off each rule before clinical use.

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

## The second reader

A model-based second reader (R058, [`SECOND_READER.md`](SECOND_READER.md)) was scored against the rules'
**first-pass** output on both real-style sets:
- 16 of the rules' 17 misses would have reached a clinician;
- 8% of normal reports would have been flagged.

The stand-in model was the smallest hosted model available, not a hospital's local model.

## Limits

- **Synthetic data:** all reports are synthetic. The real-style sets imitate hospital reports, but a
  hospital's own reports are the real test.
- **Each writer has their own habits:** three independent case writers were used. Every new writer
  still found new wording, so a hospital's own reports will too.
- **A rule-based reader has a long tail:** it reads what it has been taught. A practical safety net is
  a second, model-based reader on the hospital's own server that flags reports the rules opened nothing
  for. A person would review each flag; it would never close or open a loop by itself.
- **Before clinical use:**
  - a retrospective chart review on the hospital's own reports, against two specialists, with κ;
  - shadow-mode operation;
  - sign-off of each rule (`governance.html`).
