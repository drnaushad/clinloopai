# The model-based second reader (R058)

The rule-based report reader is transparent and fast, but it reads only what it has been taught.
Blind evaluations ([`ACCURACY_EVALUATION.md`](ACCURACY_EVALUATION.md)) showed a long tail: every new
writer of realistic reports found wording it did not know. The second reader is a safety net for that
tail.

## What it does

For each recent radiology or pathology report, the hospital's **own** language model reads the report
and lists every actionable item. Each item has one of five categories, and a quote:

| Category | Rules that already cover it | Review due | Closed by |
|---|---|---|---|
| Follow-up imaging | R003, R019, R030–R034, R037, R040, R041, R043, R044 | 7 days | an imaging order, or a study of any modality |
| Biopsy or work-up | R018, R020, R036, R038, R039, R042, R045, R046, R009 | 7 days | a biopsy, a referral, PET/CT or EUS |
| Specialist referral | (same as work-up) | 7 days | a referral or a specialist visit |
| Critical finding | R035 | 1 day | documented communication |
| Abnormal pathology | R009 | 3 days | a referral, a visit, or patient notification |

**What becomes a flag:**
- An item becomes a flag only if its quote appears **word for word** in the report and **no rule
  already tracks that category** for the report.
- Each flag opens **R058**, marked *needs human review*, with the quote as evidence.

**Closing a flag:** a clinician reads the report and either acts (the follow-up closes the flag) or
closes it as not needed. The model never opens or closes a real clinical obligation, and never reaches
the patient.

## Modes: silent in the clinical edition

| `CLINLOOP_SECOND_READER` | Clinical edition (core profile, default) | Research profile |
| --- | --- | --- |
| unset / `off` | Off | Off |
| `silent` | Silent | Silent |
| `1` / `on` | **Silent** (held there: model output never reaches care) | Live (R058 review loops) |

**Silent mode** reads the same reports with the same safeguards, but each suggestion goes to a separate
log that only the quality team sees (Quality page, "Model second reader"). Nothing enters the patient
record: no R058 loop, nothing on the worklist, EHR cards, escalation or patient graph. A clinician on
the team judges each suggestion:

- **Real miss:** follow-up was needed, no rule tracked it, and nobody had handled it.
- **Already handled:** for example, ordered in clinic.
- **Not needed.**
- **Wrong quote.**

An urgent real miss cannot be saved without a safety referral (who on the treating team was told, and
how), so the log is never where an urgent finding is seen and left. Suggestions and judgements are
in the hash-chained audit log, and every read of the quoted suggestions is recorded in the access log.

The totals per category, with precision and its 95% interval, are the evidence for the gate in
[`regulatory/CLINICAL_EVALUATION_PLAN.md`](regulatory/CLINICAL_EVALUATION_PLAN.md) §4. That gate
decides whether suggestions may ever be shown to clinicians, and then only for a person to confirm.
API endpoints:

- `GET /api/v1/quality/second-reader`: counts only, any role.
- `GET /api/v1/quality/second-reader/suggestions`: the quality team; access is recorded.
- `POST /api/v1/quality/second-reader/suggestions/{id}/review`: clinicians on the team.

## Safeguards

- **Off by default:** `CLINLOOP_SECOND_READER=silent` runs it for measurement; `=1` is live only in the
  research profile.
- **On-premise model only:** the server at `CLINLOOP_OLLAMA_URL` must resolve to a private address, or
  nothing is sent.
- **De-identified:** identifiers, and the patient's own names, are removed from the report before the
  model sees it.
- **Verified:** quotes are checked against the report and the categories are fixed. An answer that is
  not the expected JSON counts as a failure, never as "nothing found".
- **Bounded:** a report is read once, and again only if its text changes. Only recent reports are read
  (`CLINLOOP_SECOND_READER_LOOKBACK_DAYS`, default 30), with at most `CLINLOOP_SECOND_READER_MAX` per
  sync run (default 20).
- **Which model:** `CLINLOOP_SECOND_READER_MODEL` (default `medgemma:27b`, which reads English
  radiology/pathology reports) when it is installed on the Ollama server, otherwise the general best
  model (EXAONE first, for Korean patient messages). Install with `ollama pull medgemma:27b` (~17 GB at
  Q4, ~20 GB GPU/RAM). MedGemma is a Google research model under the Health AI Developer Foundations
  terms, not cleared as a medical device; its flags remain suggestions for a person to review, and in
  the core profile the reader stays silent.
- **Never blocks the sync:** if the model fails, the rules' result stands.
- **Monitored:** `GET /api/v1/reports/second-read/status`.
- **Preview:** `POST /api/v1/reports/second-read/preview` shows what the rules and the model each find
  in one pasted report, side by side, without filing anything.

## How well does it work? (synthetic reports, stand-in model)

**Method:**
- **Model:** the smallest available hosted model, standing in for a hospital's local model. It was
  given only the prompt and each report, with no labels and no code.
- **Scoring:** its answers went through the real quote check and coverage check, combined with the
  rules **as they were when each set was first scored**.

**Results:**

| Real-style report set (scored once) | Rule misses sent to a person | Normal reports flagged anyway |
|---|---|---|
| First set (100 reports) | 9 of 10 | 3 of 37 |
| Confirmation set (80 reports) | 7 of 7 | 2 of 27 |
| **Total** | **16 of 17 (94%)** | **5 of 64 (8%)** |

No item was rejected for an inexact quote.

**What it caught:**
- an acute subdural haemorrhage the critical list missed;
- a persistent part-solid nodule needing work-up;
- Korean recommendations ("f/u CT 권함", "MRI 시행 권함");
- a scanned report ("1O rnm");
- a worrisome IPMN;
- endometrial precancer (EIN).

**What it missed:** an MRI recommendation in a sentence that also named a gynecology referral. It
reported the referral but not the MRI.

**Its false flags:**
- routine statements: "continue annual screening", "routine screening mammography", "correlation with
  cultures";
- a definite liver cancer (LI-RADS 5) sent to tumour board, which arguably deserves a look anyway.

To reproduce:
```
python tests/report_eval/run_second_reader_eval.py tests/report_eval/second_reader/cases_real.json \
    tests/report_eval/second_reader/rules_first_real.json tests/report_eval/second_reader/output_*.json --show
```

**Limits:**
- **Synthetic reports.**
- **The stand-in model is a hosted model,** not the hospital's own. A local 7–30B model may find less
  and invent more. Verified quotes make invented items harmless, but they cannot recover missed ones.
- **Before going live:** run the hospital's model on its own de-identified reports in shadow mode,
  measure both numbers again against two specialists, and set the workload the clinicians accept.

## MedGemma 27B itself (October 2026, synthetic reports)

The figures above came from a stand-in model. This section is the real default reader, `medgemma:27b`
(Q4_K_M, digest `58238ae3…`) on Ollama, with the production prompt (`sr-b042876ec2e5`) at temperature 0
on an RTX A4500. Inputs, raw answers, rules output and hashes are in
`tests/report_eval/second_reader/` (`medgemma27b_*.json`, `medgemma27b_manifest.json`).

**Denominators.** All 243 reports got an answer (about 3 s each). The 180 development reports produced
157 actionable items: 153 verified by exact quote, 4 dropped. "Normal" means the blind label expects no
follow-up.

| Set | Rule misses caught | Normal reports flagged |
|---|---|---|
| Development (100 real-style + 80 confirmation), as answered | 15/17 | 21/64 (33%) |
| Same, with the not-actionable check below (not unbiased: designed from these reports) | 15/17 | 7/64 (11%) |
| Held-out round 9 (63 reports), as answered | 0/1 | 2/20 |
| Held-out round 9, with the check | 0/1 | 1/20 |

**Why normal reports were flagged (21):**
- 7 quoted the report's own "no follow-up needed" ("f/u 불필요");
- 4 quoted conditional advice ("필요시", "as clinically indicated", "could be considered");
- 3 quoted routine annual screening;
- 4 were real clinical actions outside the rule catalogue (colonoscopy, tumour board, culture correlation);
- 3 were findings with no action stated.

The prompt already excludes the first three groups. The model quoted them anyway, so `read_report` now
drops an item whose own exact quote says so, unless the same quote gives definite advice ("recommend
CT …", "권함"). A critical finding is never dropped.

**Misses.** Both development misses were OCR-damaged nodule reports ("1O mm s0lid", "9 rnm s0lid"),
the same text the rules missed. The held-out set had a single rule miss, so it says little about
sensitivity.

**Limits.** These are synthetic reports labelled by their writers. This is software verification, not
clinical validation. The flag rate on a hospital's own reports must be measured in silent mode before
anyone uses live mode.
