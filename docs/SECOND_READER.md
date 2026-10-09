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

## Safeguards

- **Off by default:** `CLINLOOP_SECOND_READER=1` turns it on.
- **On-premise model only:** the server at `CLINLOOP_OLLAMA_URL` must resolve to a private address, or
  nothing is sent.
- **De-identified:** identifiers, and the patient's own names, are removed from the report before the
  model sees it.
- **Verified:** quotes are checked against the report and the categories are fixed. An answer that is
  not the expected JSON counts as a failure, never as "nothing found".
- **Bounded:** a report is read once, and again only if its text changes. Only recent reports are read
  (`CLINLOOP_SECOND_READER_LOOKBACK_DAYS`, default 30), with at most `CLINLOOP_SECOND_READER_MAX` per
  sync run (default 20).
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
