# Diagnostic patterns: dangerous combinations whose next step never happened

Some dangers are not one abnormal result but a *combination* across the record, plus a missing
step. ClinLoop looks for these as small graph patterns over each patient's events. Each pattern is
evaluated at the moment it became complete, using only the events up to then.

| Rule | Pattern | Missing step (closes the loop) | Deadline | Source |
|---|---|---|---|---|
| **R052** | Low haemoglobin (< 13 g/dL in men, < 12 g/dL in women) and ferritin < 30 µg/L within 90 days, in a man ≥ 18 or a woman ≥ 50 | Colonoscopy, or a gastroenterology referral or visit | 14 days at age ≥ 60; 60 days otherwise | BSG 2021; NICE NG12 |
| **R053** | Creatinine ≥ 1.5 × baseline and ≥ 0.3 mg/dL (26.5 µmol/L) higher | A repeat creatinine | 3 days | KDIGO 2012; NICE NG148 |
| **R054** | Atrial fibrillation with CHA₂DS₂-VASc ≥ 2 (men) or ≥ 3 (women), and no anticoagulant | An anticoagulant prescription, or a clinician closing the loop with a documented reason | 30 days | ESC 2020 |
| **R055** | ≥ 3 RBC/hpf on two urine tests within 12 months, age ≥ 35 | A urology referral or visit, or a CT covering the kidneys or bladder | 90 days | AUA/SUFU 2020 |

## How each pattern is built

- **Evidence is shown on the graph.** The pattern node on the patient graph (*Diagnostic patterns*
  lane) links to every event it was built from, such as the haemoglobin and the ferritin.
- **No pattern when the next step already happened:**
  - R052: a colonoscopy or GI referral in the past year;
  - R054: the patient already on an anticoagulant;
  - R055: a urology contact in the past year.
- **Fires at most once a year** per patient (30 days for creatinine), so a series of low values
  does not flood the worklist.
- **Creatinine baseline** follows the NHS England AKI algorithm:
  - the lowest value in the previous 7 days;
  - otherwise, the median of the previous 8–365 days;
  - same unit only;
  - the stage (1–3) is shown.
- **CHA₂DS₂-VASc** is computed from the problem list (ICD-10 codes or wording, in English or Korean)
  plus age and sex:
  - heart failure +1, hypertension +1, diabetes +1, stroke/TIA +2, vascular disease +1;
  - age 65–74 +1, age ≥ 75 +2;
  - female +1.
- **Only the matching event closes the loop.** A dermatology referral does not close R052, and a
  head CT does not close R055.

## Limits

- **Built from coded data,** so a pattern can only be as good as that data. A haemoglobin with no
  value or unit, or a diagnosis that is missing from the problem list, means no pattern. The
  dangerous error is a missed pattern; the worklist cannot show what it cannot see.
- **Women under 50 are excluded from R052,** because menstrual loss is the usual cause. Clinicians
  may still investigate.
- **R054 cannot read a documented decision not to anticoagulate** unless it is coded. The clinician
  closes the loop with the reason.
- **Each rule starts in shadow mode** until a specialist signs it off on `governance.html`:
  gastroenterology for R052, nephrology for R053, cardiology for R054, urology for R055.
- **Not yet validated.** Before go-live, measure positive predictive value against chart review for
  each pattern.
