# From one patient's loop to a hospital that does not forget: graph-AI brainstorm

This builds on [`LIFE_SAVING_ROADMAP.md`](LIFE_SAVING_ROADMAP.md) and does not repeat it. The roadmap
already covers harm-aware attention, delay–harm curves, the open-loop rate, the obligation language
and equity. This document adds the graph-engineering view, with ideas ranked by lives at stake and by
how soon they can be built safely.

**Premise.** A diagnostic error is rarely one wrong decision; it is a broken chain.

- **The chain:** a result → a plan → an order → an appointment → a test → a decision.
- **What ClinLoop is:** a typed temporal hypergraph of these chains, where each obligation is a
  hyperedge with a deadline.
- **Every idea below** asks what else that graph can see that no single clinician can.

---

## Tier 1: build next (deterministic, specialist-reviewable)

### 1. Incomplete diagnostic motifs ("the work-up that never finished")
Some patterns are dangerous only in combination: no single event in them is alarming.

**The idea:** write them as small graph patterns (motifs) over the patient graph and look for the
missing node.

| Motif (all within a time window) | Missing node | Why it matters |
|---|---|---|
| Iron-deficiency anaemia, age ≥ 50 | No colonoscopy or GI referral | Colorectal cancer presents this way |
| Unintentional weight loss + new anaemia or raised ALP | No imaging or no diagnosis recorded | Occult malignancy |
| Haematuria (≥ 2 tests), age ≥ 35 | No urology referral or cystoscopy | Bladder cancer |
| Rising PSA across two results | No urology decision | Prostate cancer |
| New atrial fibrillation diagnosis | No anticoagulation decision documented | Stroke |
| Rising creatinine across three results | No nephrology review or medication change | AKI or CKD progression |

**How it fits ClinLoop:**
- Each motif is a rule with explicit evidence and a specialist sign-off, like R001–R051.
- The graph already holds every node type these motifs need: labs with analytes, diagnoses,
  referrals with specialty, imaging with region, and medications.

**What is new is the query.** It looks for *a pattern plus an absence* across many events, where today's
rules look for one trigger and one follow-up.

### 2. Lesion identity across studies (the nodule that grows silently)
Each report describes "a 7 mm nodule in the right upper lobe". When the next CT says "8 mm RUL
nodule", is that the same lesion, now 14% larger?

**The idea:** a *lesion node* that links mentions across reports, matched on the same organ, segment
or side, a compatible size, and the same time window. Once lesions are linked:

- the nodule's growth rate (volume-doubling time) can be computed;
- R046 (growing nodule) can be triggered from actual measurements, not only the radiologist's
  wording;
- "stable for 2 years", which ends Fleischner follow-up, can be verified from the lesion's history.

**Measurement:** CT organ measurement (TotalSegmentator) already gives the pixel side. The lung-nodule
model and the radiologist's report give the lesion side.

**Safety:** a lesion link proposed by the system is shown as "probably the same lesion" and is
confirmed by a radiologist. It never closes a loop by itself.

### 3. Guideline provenance graph with update alerts
Every rule cites its source (Fleischner 2017, ACR white papers, ACC/AHA).

**The idea:** model rule → guideline version → recommendation as a graph.
- **When a guideline is revised,** every rule and every open loop derived from the old version is
  flagged for specialist re-sign-off. Governance already fingerprints rules; this adds the source
  side.
- **For audits and court records,** the graph answers "which version of which guideline put this
  patient on this clock?"

### 4. Model-checking the rule set
The rules are written as LTL formulas (`ltl_formula` on every rule).

**The idea:** before each release, check the rule set for:
- **conflicts:** two rules demanding incompatible deadlines for the same trigger;
- **dead rules:** a rule that can never fire;
- **unclosable loops:** a required follow-up type no mapper ever produces.

Rule-set errors are then caught by proof, not by patients.

---

## Tier 2: the hospital as a graph (system safety, not just patient safety)

### 5. Hospital-scale obligation graph and process mining
Merge all patients' graphs into one graph of *where obligations break*. Nodes are departments, order
types, clinicians, clinics and weekdays; edges are hand-offs.

- **Bottlenecks:** edge-level failure rates show where loops break. For example, "cardiology referrals
  from the ED fail 3× more often than from clinics".
- **Process mining** (Petri-net discovery from event logs) shows the actual path an obligation takes,
  next to the path the hospital thinks it takes.
- **The output is a fix to the system, not an alert to a person.** One booking-process change can
  close thousands of future loops.
- **Fairness:** every bottleneck is stratified by age, sex, language and insurance, so a fix does not
  help only some patients.

### 6. Learning from closures without letting the machine change the rules
Every closure records a reason, such as "not clinically indicated", "patient declined" or "done
elsewhere".

**The idea:** mine the closure reasons per rule.
- **Example:** when 40% of R030 loops close as "done elsewhere", the hospital needs the outside-records
  feed (national HIE, 진료정보교류), not more alerts.
- **When a rule is mostly overridden as "not indicated",** it goes back to its specialist for review.
- **The system proposes; a named specialist decides.** It never edits a rule itself.

### 7. Who should act? Graph-based routing
An open loop has a responsible person: the ordering clinician, the PCP, the specialist or the
navigator.

**The idea:** the care-team graph (who ordered what, who saw the patient last, who is covering)
routes each loop to the person most likely to close it.

**The aim** is one owner per loop, never "everyone was alerted, so no one acted".

---

## Tier 3: research (needs data, validation and ethics approval)

### 8. Temporal graph neural networks for failure risk
The goal is to predict, at trigger time, which loops will fail.

**Inputs:**
- the patient's history of no-shows and cancellations;
- the route the obligation must travel: departments and hand-offs;
- the time of year;
- language and distance.

**Rules for using it:**
- The prediction **re-orders** the worklist. It never hides or closes a loop.
- It is **calibrated**, **audited for fairness** (a model that learns "this group always fails, so
  deprioritise it" is harmful), and **validated prospectively in shadow mode** before it affects
  anyone.

### 9. Federated learning across hospitals
Loop-failure patterns differ by hospital, but data cannot leave it.

**The idea:** federated training, sharing model updates and not records, across a Korean hospital
network.
- **Privacy:** secure aggregation plus differential privacy on the shared updates.
- **The deliverable is a benchmark** (ClinLoop-Bench, roadmap §3.5), not just a model.

### 10. A patient's graph across institutions
Patients move between hospitals, and loops die at the border.

**The idea:** with consent, merge outside records into one graph:
- outside reports read with OCR (built);
- national HIE documents;
- patient-held records.

**Hard problems:**
- identity resolution;
- de-duplication: "the same CT, reported twice";
- whose obligation it is after transfer.

The obligation graph makes the hand-off *explicit*. The sending hospital's open loop becomes the
receiving hospital's inbound obligation.

### 11. The patient as a node that can act
Show patients their own open loops, in plain Korean or English, through KakaoTalk or SMS, with
clinician approval (outreach is already built).

- **A patient who knows** "your CT is due by 29 April" closes loops that systems miss.
- **To measure:** whether loop closure improves, and whether anxiety rises. Both are outcomes.

---

## How we will know it saves lives

The evidence ladder is in roadmap §7. Graph-specific additions:

1. **Motif validation:** sensitivity and specificity of each diagnostic motif against chart review by
   two specialists before it goes live.
2. **Lesion linking:** agreement with radiologists' own lesion matching (κ), and growth-rate error
   against manual measurement.
3. **Process-mining fixes:** an interrupted time series of the open-loop rate before and after each
   system fix.
4. **Pragmatic trial:** a stepped-wedge cluster trial across clinics, with time-to-diagnosis for
   cancers from the first abnormal signal as the primary outcome, and stage at diagnosis as the
   secondary outcome.

## What we will not do

- Let a model close a loop, edit a rule, or decide what a note means without a quotable source.
- Rank patients lower because of who they are.
- Claim lives saved before the trial shows it.

---

## Built from this brainstorm (2026-10-08)

**Clinical-note plans (R048–R051).** The single largest gap in the graph was clinicians' own
promises.
- "Repeat potassium in 1 week", "CT chest in 3 months" and "심장내과 협진 의뢰" are now nodes with
  deadlines.
- Each closes only on the *matching* event: the same test, the same modality and region, the same
  specialty.
- Conditional, cancelled and already-done plans are visible but not tracked.
- An on-premise LLM may suggest plans the rules missed, but only with an exact quote and only for a
  person to review.

See [`CLINICAL_NOTES.md`](CLINICAL_NOTES.md).

**Diagnostic motifs, first four (R052–R055).** Idea 1 above, built for the patterns with the
clearest guideline basis:
- iron-deficiency anaemia → GI work-up;
- creatinine rise → repeat creatinine;
- AF with high CHA₂DS₂-VASc → anticoagulation decision;
- persistent haematuria → urology.

Each pattern node links to the events it came from. See
[`DIAGNOSTIC_PATTERNS.md`](DIAGNOSTIC_PATTERNS.md).

**Lesion identity across studies (R056).** Idea 2 above. Nodules are linked across reports by lobe
and size. Growth that no single report states is caught, and the volume-doubling time is computed. A
radiologist confirms the match.

**Model-checking the rule set.** Idea 4 above, as a static check (`rule_check.py`, run in CI and shown
on `governance.html`). For every rule it checks whether hospital data can produce the trigger, and
whether hospital data can produce a follow-up that closes it. It also checks the references, the
Korean name and the formal statement. It currently reports 57 rules with 0 errors. The 3 warnings
are the guideline-edition flags described next.
Tests prove it catches a rule that can never fire or never close.

**Guideline provenance (idea 3).** `config/guidelines.json` records the current edition of each
guideline the rules cite. A rule citing an older edition is flagged on `governance.html` for specialist
re-review. On day one it flagged three rules:
- **R054** cites ESC 2020. ESC 2024 moved to CHA₂DS₂-VA, where sex no longer scores.
  - `CLINLOOP_AF_SCORE=cha2ds2_va` switches the rule to the 2024 score.
  - ACC/AHA 2023 still uses CHA₂DS₂-VASc, so the choice belongs to the hospital's cardiologists.
- **R013 and R025** cite the ADA Standards 2024; the current edition is 2026.

A specialist's documented decision to keep an older edition ("accepted") clears the flag.

**Where follow-up breaks (idea 5, first step).** `quality.html` and `GET /api/v1/metrics/breakdowns`
show:
- each rule's active, overdue and on-time rates;
- the follow-up step most often missing, which is the bottleneck a process fix should target;
- missed rates by age group, language and sex, with groups ≥ 10 points above the overall rate marked;
- workload by owner, for sharing work, never for ranking clinicians.
