# Open-i chest radiograph reports: real-report check of the critical-finding rule (R035)

Source: Indiana University chest X-ray collection, distributed by the US National Library of Medicine
(Open-i, `NLMCXR_reports.tgz`, 3,955 de-identified reports, 3,927 with findings or impression).
The reports are not stored in this repository. Download them from https://openi.nlm.nih.gov/faq
and run them through `tests/report_eval/run_eval.py`'s `run_case`, one report per case.

`r035_review_labels.json` labels each report for which `main` (October 2026) opened R035:
- correct: a current, new or worsening emergent finding;
- false_alarm;
- uncertain;
- radiologist_flag: the radiologist's own "critical result" statement, alerted on by design.
The reviewer was an AI assistant, not a clinician; a clinician must confirm these labels.
