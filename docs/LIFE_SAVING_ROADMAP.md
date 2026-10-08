# ClinLoop AI — Life-Saving Roadmap

> From a synthetic-data prototype to a system proven to save lives.

The great patient-safety advances were not clever technology. Pronovost's ICU checklist cut
catheter-related bloodstream infections by about two-thirds across Michigan (NEJM 2006). The WHO
Surgical Safety Checklist roughly halved surgical deaths across eight countries (NEJM 2009). Each
took a failure everyone knew about, made it **measurable**, made it **closable**, **proved** the
benefit in a trial, and then **spread**.

ClinLoop belongs in that lineage. Its job is to make sure that once medicine has found something
dangerous, the patient is not lost on the way to treatment. This document sets out how we get there.

---

## 0. Where we stand

| Strength | Gap |
| --- | --- |
| Deterministic, guideline-cited rules with a full evidence chain for every alert | Runs on synthetic data only; no real-world accuracy has been measured |
| Formal temporal semantics (`□(trigger → ◇≤T follow-up)`) | 46 rules; sign-off workflow built, none yet signed off by a specialist |
| FHIR R4 ingestion, loop registry, clinician worklist, escalation, audit | Not yet connected to a hospital system or SSO |
| 131 tests, including patient-safety regression tests | The comparison baselines are simulations, not real systems |
| Read-only design: never orders, never auto-closes | Counterfactual survival figures are hand-written illustrations |
| Stage 1 chart-review toolkit ready | No IRB approval or real-data validation yet |

**Prior art we must build on and beat.** Singh, Murphy and colleagues at the VA showed that
electronic "e-triggers" can find missed follow-up of cancer red flags, and tested them in a cluster
randomized trial (Murphy et al., JCO 2015). ClinLoop must say clearly what it adds:

1. one engine across many clinical domains, not one trigger per disease;
2. a formal, versioned obligation language;
3. harm-aware ranking under an alert budget;
4. patients as co-owners of their loops;
5. closure evidence that crosses institutions.

---

## 1. North star

> **Every actionable finding reaches its follow-up within its guideline window, for every
> patient, regardless of who they are or where they are seen next.**

We judge ourselves on two numbers:

- **Open-loop rate**: actionable findings not closed within their guideline window, per 1,000
  actionable findings (definition in §3.2).
- **Estimated deaths averted**: once trial evidence lets us attribute closures to ClinLoop (§10).

Everything else (AUROC, alert counts, uptime) serves these two.

---

## 2. Where patients actually die: clinical scope

We prioritise domains by **harm of delay × how often the loop breaks × how clear the next action
is × burden in Korea**.

### Wave 1: highest yield, fully deterministic (build first)

| Domain | Trigger → obligation | Why delay kills |
| --- | --- | --- |
| **Positive cancer screening** | FIT+ → colonoscopy; LDCT Lung-RADS 4 → per-category workup; mammography BI-RADS 4/5 → biopsy; Pap HSIL → colposcopy *(exists: R005)* | Longer FIT+-to-colonoscopy intervals are associated with more advanced-stage colorectal cancer (Corley et al., JAMA 2017). Korea's National Cancer Screening Program uses FIT from age 50, so this one rule reaches millions. |
| **Incidental imaging findings**, especially at ED discharge | Lung nodule *(exists: R003, now size-aware)*, adrenal, renal or pancreatic lesion, AAA, thyroid nodule → recommended imaging or referral | ED patients leave after the emergency is treated; the incidental finding has no owner. |
| **Results pending at discharge** | Any result finalised after discharge → reviewed and acted on | Many inpatients leave with results pending, some actionable, often unknown to their physicians (Roy et al., Ann Intern Med 2005). |
| **Critical values** | Panic K⁺, Na⁺, glucose, troponin, positive blood culture → documented action within hours | Death within hours to days. |
| **Post-discharge positive cultures** | → callback and antibiotic review *(exists: R006, R015)* | Untreated bacteraemia and sepsis. |

### Wave 2: high harm, still deterministic

| Domain | Trigger → obligation |
| --- | --- |
| **Liver cancer surveillance** | Chronic HBV or cirrhosis → ultrasound ± AFP every 6 months (KASL/AASLD). HBV-related HCC is a major cause of cancer death in Korea. |
| **Gastric neoplasia** | Biopsy adenoma or dysplasia → endoscopic follow-up or resection; *H. pylori* treated → test of cure. Korea has one of the world's highest gastric cancer incidences. |
| **High-risk medications** | Warfarin → INR *(exists: R007)*; DOAC → renal function; lithium → level *(now 7-day window)*; methotrexate → CBC/LFT; clozapine → ANC; amiodarone → TFT/LFT; teratogens → pregnancy testing |
| **Cardiovascular transitions** | Post-MI → cardiology visit *(exists: R014)*; new HF → echo *(exists: R016)*; HF discharge → 7–14-day visit; TIA → urgent workup |
| **Maternal** | Hypertensive disorder of pregnancy → postpartum BP check within days (ACOG); gestational diabetes → postpartum glucose test |
| **Paediatric** | Abnormal newborn screen → confirmatory testing; neonatal jaundice → post-discharge bilirubin check |

### Wave 3: high harm, needs specialist co-design

| Domain | Trigger → obligation | Note |
| --- | --- | --- |
| **Mental health** | ED visit for self-harm, or psychiatric discharge → follow-up within 7 days | Korea has one of the highest suicide rates in the OECD, and risk peaks just after discharge. Build only with psychiatry, crisis protocols and patient representatives. |
| **Tuberculosis** | Positive smear or culture → treatment start, contact investigation, treatment completion | Korea has long had one of the highest TB incidences among OECD countries. |
| **Hepatitis C** | Antibody+ → RNA test → treatment linkage | A curable disease lost at the second test. |
| **Genetics** | Pathogenic variant (e.g. BRCA) → counselling and cascade testing of relatives | Saves people who are not yet patients. |
| **Amended reports** | Report corrected after sign-off → new result acknowledged | A silent and well-known failure. |

---

## 3. Five contributions that could define the field

### 3.1 Clinical Obligation Language (COL): an open standard

Today every hospital hard-codes its own follow-up logic, or has none. We publish the obligation
rules as an **open, versioned, guideline-cited library**:

- **Semantics**: Metric Temporal Logic, as now: trigger, required follow-ups (all/any), deadline,
  severity, and finding-specific windows (now implemented for nodule size and drug).
- **Interoperability**: compile each rule to HL7 FHIR `PlanDefinition` and CQL (Clinical Quality
  Language), so any FHIR-capable EMR can run it.
- **Governance**: each rule is owned by a named specialist reviewer, cites its guideline version,
  and ships with signed-off positive, negative and edge-case tests.
- **Machine checks**: automatic detection of conflicting, duplicate or unreachable rules, and diffs
  when a guideline is updated.

If specialty societies adopt it, COL becomes infrastructure, as OMOP did for observational research.

### 3.2 The open-loop rate: a new quality measure

- **Numerator**: actionable findings whose required follow-up was not completed within the
  guideline window.
- **Denominator**: all actionable findings in the period (per COL rule, per department).
- **Stratified by**: finding type, department, age, insurance type (including 의료급여), language
  and distance from the hospital.

Our aim is for this to become a nationally reported indicator, through HIRA quality assessment
(적정성 평가) or KOIHA accreditation (의료기관평가인증), the way infection rates are today. A
metric a whole country reports changes behaviour in every hospital, including those that never
buy ClinLoop.

### 3.3 Harm-aware attention allocation: the core AI contribution

Clinician attention is the scarcest resource in the hospital, and alert fatigue has killed many
earlier safety systems. Rank alerts by **expected harm averted**, not by rule severity alone:

```
priority(loop) = P(loop stays open | patient, finding, context)   ← learned survival model
               × harm(delay) for this finding type                ← delay–harm curve (§3.4)
               × actionability (clear, available next step)
subject to:  alerts per clinician per day ≤ budget
```

- `P(stays open)` is a time-to-closure survival model using prior no-shows, distance, age, care
  fragmentation and channel reachability.
- **Equity rule:** social risk factors may only **raise** outreach intensity. They must never lower
  a patient's clinical priority (§8).
- **Evaluation**: decision-curve analysis (net benefit at each alert budget), calibration, and
  harm averted per alert.

This turns ClinLoop from "an alert per rule" into "the most lives saved per minute of clinician
attention". It is a genuinely new, publishable formulation.

### 3.4 Delay–harm curves from real data

The current counterfactual survival paths are hand-written. Replace them with **estimated**
curves:

- **Method**: target trial emulation (Hernán & Robins 2016) on national claims and cohort data
  (NHIS), e.g. "colonoscopy at ≤1, 1–3, 3–6, 6–12 months after FIT+" → risk of advanced-stage
  cancer and death.
- **Output**: for each finding type, how much each extra week of delay raises the risk of harm,
  with confidence intervals.
- **Uses**: setting rule deadlines from evidence, the harm term in §3.3, and the lives-saved
  estimate in §10. Each curve is a standalone publication.

### 3.5 ClinLoop-Bench: an open benchmark

The current synthetic benchmark is a rule-conformance test (see README). The field needs what CASP
was for protein structure:

- de-identified real trajectories, with loop status adjudicated by two blinded clinicians;
- a radiology and pathology report set annotated with follow-up recommendations and evidence spans;
- credentialed access (PhysioNet-style), fixed splits and a public leaderboard;
- **real baselines**: the hospital's existing inbox logic, published e-trigger definitions, and a
  zero-shot LLM actually run on the same records.

---

## 4. The AI that matters: neuro-symbolic done right

The rules decide; the AI reads, predicts and prioritises. Never the reverse.

1. **Obligation extraction from free text.** Most obligations live in radiology and pathology
   narrative ("recommend CT chest in 3 months"). An LLM extracts a structured obligation plus the
   exact evidence span. A deterministic validator checks it against COL. Calibrated confidence
   (e.g. conformal prediction) routes uncertain extractions to a human. Measure extraction accuracy
   on ClinLoop-Bench.
2. **Closure-evidence fusion.** False alarms often happen because the patient completed follow-up
   somewhere else. Fuse orders, results, appointments and, with consent, external records via
   진료정보교류 and 마이헬스웨이 (My Healthway) and NHIS claims. A loop closes on evidence, never
   on a click.
3. **Ownership resolution.** Every open loop needs one accountable owner: ordering clinician, PCP
   or discharging attending. Escalate along a defined chain when the owner is away.
4. **Proactive outreach.** Use the §3.3 survival model to contact high-risk patients *before* the
   deadline, not after.
5. **Process mining.** Mine event logs for *where* loops break (which handoff, clinic or weekday)
   so hospitals fix the system, not just the case. This is Pronovost-style systems science, powered
   by data.
6. **Post-deployment monitoring.** Detect data and performance drift, run federated evaluation
   across sites without moving patient data, and keep a public log of the system's own misses.

---

## 5. Human factors: close the loop, don't just alert

- **Navigator model.** Route most alerts to nurse navigators rather than physicians. Navigator
  programmes are an established way to complete cancer-screening follow-up.
- **One-click actions** inside the EMR workflow: order, message the patient, refer.
- **Defer with reason.** "Patient declined", "done elsewhere", "hospice", "clinically not
  indicated". This captures clinical judgment, documents the decision, cuts repeat alerts, and
  every reason feeds rule refinement.
- **Tiered urgency.** Interrupt only for critical or overdue loops; batch the rest into a daily
  digest; enforce the alert budget.
- **Patients as co-owners.** Plain-language KakaoTalk or SMS messages; teach-back; caregiver proxy
  for elderly patients; Korean, English, Chinese and Vietnamese; one-tap booking. Test message
  framings in randomised message trials instead of assuming which works best.
- **Measure burden**: clinician minutes per closed loop, alerts per day, override rates.

---

## 6. Safety engineering for a safety system

A safety net that fails silently is worse than none, because people stop checking.

- **Fail loud.** Heartbeats on every data feed. If no lab results arrive for N hours, or the
  watchdog stops scanning, page a human.
- **Standards**: ISO 14971 hazard analysis, IEC 62304 software lifecycle, and a written safety case.
- **Hard limits**: never auto-close a loop, never place an order, never contact a patient without an
  approved template or human review.
- **Clinical regression suite.** Every rule ships with specialist-signed test cases. The
  patient-safety regression tests added in this release (partial closure, cancelled follow-up,
  downgraded urgency, wrong guideline window) are the seed.
- **Rule governance board** with a defined process and timeline for guideline updates.

---

## 7. Evidence ladder

| Stage | Design | Primary questions | Reporting standard |
| --- | --- | --- | --- |
| **0. Conformance** *(now)* | Synthetic scenarios, specialist review of all rules | Does the engine implement its rules exactly? | — |
| **1. Retrospective validation** | One tertiary hospital, IRB-approved; two blinded clinicians adjudicate a stratified chart sample | Sensitivity and PPV against chart review; true baseline open-loop rate; time-to-closure distributions | TRIPOD+AI |
| **2. Silent prospective deployment** | 3–6 months live, alerts logged but not shown | Alert burden; clinician-judged actionability; feed and system reliability | DECIDE-AI |
| **3. Stepped-wedge cluster RCT** | Clinics adopt in randomised order; pre-registered (CRIS) | **Primary:** share of findings closed in window. **Secondary:** time to diagnosis, cancer stage at diagnosis. **Harms:** unnecessary follow-up tests, patient anxiety, clinician burden | SPIRIT-AI / CONSORT-AI |
| **4. Replication and economics** | Multiple sites, more than one country | Generalisability; measured QALYs and costs | CHEERS |

Count harms as carefully as benefits. Over-investigation of benign findings is a real harm, and
reporting it honestly is part of what will make this work trusted.

---

## 8. Equity by design

The patients most likely to be lost are the ones medicine already fails most: elderly people living
alone, 의료급여 recipients, rural residents, migrants, and people with disabilities.

- Report the open-loop rate stratified by these groups (`sdoh_monitor.py` already computes the
  disparity ratio). Publish it.
- **Never encode bias into priority.** "Past no-shows" must trigger *more* outreach, never a lower
  clinical rank. Audit the ranking model for this explicitly.
- Channel diversity: phone calls and community-health-worker visits for patients without
  smartphones.

---

## 9. Regulation and deployment (Korea first)

- **MFDS**: request a pre-consultation on whether and how ClinLoop is classified as software as a
  medical device. Consider innovative medical device designation once Stage 1 data exist.
- **Integration**: read-only FHIR R4 or HL7 v2 feeds; on-premise deployment; no PHI leaves the
  hospital.
- **Privacy**: PIPA-compliant pseudonymisation; human review before any external transmission (the
  regex scrubber cannot catch every name).
- **Business**: B2B SaaS priced on value, since closed loops reduce malpractice exposure. Make that
  claim only once it is measured.

---

## 10. Measuring lives saved: the scoreboard

Once Stage 3 provides an attributable effect:

```
deaths averted ≈ Σ over loops closed because of ClinLoop
                   (delay avoided) × (delay–harm slope for that finding, §3.4)
```

Report it quarterly with confidence intervals, next to the harms. This is the number that justifies
everything else, and the only one we should ever put on a slide about saving lives.

---

## 11. Plan

### Engine safety fixes (2026-10-07)
- [x] Fix the engine bugs that silently dropped patients (partial closure, cancelled follow-ups,
      downgraded critical alerts, "mi" substring, timezone crashes)
- [x] Correct the guideline windows (Fleischner >8 mm nodule → 3 months; levothyroxine; lithium)
- [x] Make the safety-clock watchdog run the real engine
- [x] Remove unsupported outcome, trial and hallucination claims from the API; label illustrative
      figures on the site
- [x] Correct the cockpit narrative for SC-0004 (7.8 mm solid nodule → Fleischner 6–12-month CT)
- [x] Make the public site's local-LLM panel state plainly that the on-premise LLM is unavailable
- [x] Merge to `main` so clinloopai.app serves these changes

### Built for the pilot (2026-10-08)
- [x] Wave 1 rules R017–R022 (FIT+, BI-RADS 4/5, Lung-RADS 4A/4B/4X, post-discharge results,
      critical values), every rule marked `pending_specialist_review`
- [x] FHIR R4 adapter (status-aware, negation-aware extraction with evidence spans)
- [x] Loop registry: owners, coded deferral, evidence-based closure, escalation chain,
      hash-chained audit, open-loop rate stratified by equity groups (§3.2, §8)
- [x] Token authentication with clinical roles; restricted CORS; Docker image
- [x] Clinician worklist (`worklist.html`)
- [x] Stage 1 chart-review toolkit: stratified blinded sampling, weighted metrics, bootstrap CIs,
      Cohen's kappa (§7)
- [x] Wave 2 rules R023–R029 (heart failure, postpartum BP, gestational diabetes, HCV, HCC
      surveillance, self-harm follow-up as a clinician-only rule)
- [x] Radiologist-recommended follow-up (R030–R032): deadline taken from the report, with evidence span
- [x] Radiology report reading hardened after a radiologist live-run (`docs/RADIOLOGY_LIVE_RUN.md`): sizes in cm, organ-aware nodules, radiographs (R033), Lung-RADS 3 (R034), critical findings (R035), biopsy/FNA recommendations (R036)
- [x] Radiology round 2: body-region matching, full Fleischner 2017 (types, risk, stepped follow-up, growth), ACR incidental findings for adrenal, renal, pancreatic cyst, thyroid and aorta (R037–R046), hospital-editable critical-finding list
- [x] Governance: hash-bound specialist sign-off per rule, critical-finding list approval, shadow mode (`governance.html`); report-level validation tool (`src/validation/report_validation.py`)
- [x] Live FHIR server sync (changed patients → full history); fail-loud feed monitoring (§6)
- [x] Patient outreach: diagnosis-free drafts, clinician approval, hospital messaging webhook (§5)
- [x] Korean/English worklist with assignment and "my loops"

### 90 days
- Clinical advisory board: radiology, pathology, oncology, primary care, psychiatry, nursing
  navigation, a patient representative, an ethicist and a medical lawyer
- Specialist sign-off on all 46 rules (in `governance.html`) and approval of the hospital's critical-finding list; report-level validation on real de-identified reports; map the local LOINC and report vocabularies into the FHIR adapter
- Hospital SSO integration for the worklist; EMR in-basket integration
- COL specification v0.1; FHIR PlanDefinition export
- IRB submission for Stage 1; NHIS data access application for delay–harm curves

### 1 year
- Stage 1 and Stage 2 at the first hospital
- ClinLoop-Bench v1 released
- First delay–harm curves (FIT+ → colonoscopy, lung nodules) published

### 3 years
- Stage 3 cluster RCT completed and published
- Open-loop rate proposed as a national quality indicator
- Multi-site, multi-country replication

---

## 12. What we will not do

- Claim an outcome before it is measured.
- Auto-close a loop, auto-order a test, or contact a patient without review.
- Let social disadvantage lower a patient's priority.
- Send identifiable data outside the hospital.
- Hide our misses: the system's failures are published, like its successes.

---

## References

- Callen JL, Westbrook JI, Georgiou A, Li J. Failure to follow-up test results for ambulatory
  patients: a systematic review. *J Gen Intern Med.* 2012;27(10):1334–48. PMID 22183961.
- Roy CL, Poon EG, Karson AS, et al. Patient safety concerns arising from test results that return
  after hospital discharge. *Ann Intern Med.* 2005;143(2):121–8.
- Singh H, Thomas EJ, Mani S, et al. Timely follow-up of abnormal diagnostic imaging test results in
  an outpatient setting. *Arch Intern Med.* 2009;169(17):1578–86.
- Murphy DR, Wu L, Thomas EJ, et al. Electronic trigger-based intervention to reduce delays in
  diagnostic evaluation for cancer: a cluster randomized controlled trial. *J Clin Oncol.*
  2015;33(31):3560–7.
- Corley DA, Jensen CD, Quinn VP, et al. Association between time to colonoscopy after a positive
  fecal test result and risk of colorectal cancer and cancer stage at diagnosis. *JAMA.*
  2017;317(16):1631–41.
- Pronovost P, Needham D, Berenholtz S, et al. An intervention to decrease catheter-related
  bloodstream infections in the ICU. *N Engl J Med.* 2006;355(26):2725–32.
- Haynes AB, Weiser TG, Berry WR, et al. A surgical safety checklist to reduce morbidity and
  mortality in a global population. *N Engl J Med.* 2009;360(5):491–9.
- MacMahon H, Naidich DP, Goo JM, et al. Guidelines for management of incidental pulmonary nodules
  detected on CT images: from the Fleischner Society 2017. *Radiology.* 2017;284(1):228–43.
- Hernán MA, Robins JM. Using big data to emulate a target trial when a randomized trial is not
  available. *Am J Epidemiol.* 2016;183(8):758–64.
- Vickers AJ, Elkin EB. Decision curve analysis: a novel method for evaluating prediction models.
  *Med Decis Making.* 2006;26(6):565–74.
- Collins GS, et al. TRIPOD+AI statement. *BMJ.* 2024. · Vasey B, et al. DECIDE-AI. *Nat Med.* 2022.
  · Rivera SC, et al. SPIRIT-AI; Liu X, et al. CONSORT-AI. *Nat Med.* 2020.
- World Health Organization. *Global Patient Safety Report.* 2024.
