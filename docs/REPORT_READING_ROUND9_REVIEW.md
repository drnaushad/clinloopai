# Clinician sign-off: report reading, branch `report-reading-round9`

`AGENTS.md` requires a clinician to review report-reading changes line by line before they are merged.
Prepared by the development team (an AI assistant and a PhD student; neither is a clinician).
**Status: awaiting clinician review. Not merged.**

| # | Change (file) | What it does | Safety check in the tests | Approve? |
|---|---|---|---|---|
| 1 | History sentence skipped for critical alerts (`radiology.py`) | "CLINICAL HISTORY: Prior PE…" no longer opens a 1-hour critical alert | A finding after the history sentence still alerts | ☐ |
| 2 | An addendum retracting a nodule removes it (`radiology.py`) | No follow-up for a nodule the radiologist withdrew | With several nodules and no way to tell which one, all stay | ☐ |
| 3 | OCR repair: nodu1e, rnonths, recornrnended (`radiology.py`) | Scanned reports no longer lose findings | Only adds detections | ☐ |
| 4 | Negated lists: "clear of", "no evidence of", comma lists (`report_text.py`) | Real chest X-rays: false critical alerts 84 → 18, all 19 true alerts kept | "No consolidation, large right pneumothorax" still alerts | ☐ |
| 5 | Hydropneumothorax on the critical list (`config/critical_findings.json`) | A missed large hydropneumothorax now alerts | Only adds detections; the list must be approved again in governance | ☐ |
| 6 | **Nodule on a radiograph → chest CT within 30 days** (`radiology.py: radiograph_nodule`) | Replaces Fleischner intervals, which cover CT-detected nodules (ACR Appropriateness Criteria). **Is 30 days the right target?** | A calcified nodule, or a solid nodule stable for 2 years or more, needs nothing; growth → work-up | ☐ |
| 7 | "Unchanged … N years ago" read as stable (`radiology.py`) | A nodule stable for 2 years or more opens no follow-up | Under 2 years still opens | ☐ |

Evidence:
- **Tests:** `tests/test_report_accuracy.py` (classes `TestRound9BlindFindings`,
  `TestRealChestRadiographNegation`, `TestRadiographNodules`).
- **Blind cases:** 753 synthetic, 99.7% clinically equivalent, unchanged.
- **Real reports:** 3,927 Open-i chest radiograph reports; the R035 review labels in
  `tests/report_eval/openi/` also need clinician confirmation.

Reviewer: ____________________  Specialty: ____________  Date: ________  Signature: ____________
