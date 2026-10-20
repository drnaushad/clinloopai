"""
second_reader_benchmark.py — Run any model as the second reader over the synthetic report sets

Same production prompt and settings as the app (second_reader.PROMPT, temperature 0), so a cloud model
is compared with MedGemma 27B on equal terms. Synthetic reports only; cloud models must be enabled
first (cloud_llm.py: research profile, CLINLOOP_CLOUD_LLM, the provider's API key).

    python scripts/second_reader_benchmark.py medgemma:27b
    python scripts/second_reader_benchmark.py cloud:anthropic
    python tests/report_eval/run_second_reader_eval.py tests/report_eval/second_reader/cases_real.json \\
        tests/report_eval/second_reader/rules_first_real.json <answers file written below>

Writes <output dir>/<model>_<set>.json (raw answers, one per report) and prints counts only.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.clinloop_engine import second_reader  # noqa: E402
from src.clinloop_engine.local_llm_engine import generate_clinical_text  # noqa: E402
from src.clinloop_engine.radiology import clean_report_text  # noqa: E402

SR = os.path.join(ROOT, "tests", "report_eval", "second_reader")
SETS = {"real": "cases_real.json", "confirm2": "cases_confirm2.json", "r9_heldout": "cases_r9_heldout.json"}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    model = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else SR
    tag = re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_")
    for name, fname in SETS.items():
        cases = json.load(open(os.path.join(SR, fname), encoding="utf-8"))
        answers, errors, ok, t0 = {}, 0, 0, time.time()
        for c in cases:
            r = generate_clinical_text(second_reader.PROMPT + clean_report_text(c["text"]), model=model,
                                       temperature=0.0, max_tokens=600, system_prompt=second_reader.SYSTEM_PROMPT)
            if r.get("error"):
                errors += 1
                if errors >= 3 and not ok:        # not configured or unreachable: stop, write nothing
                    print(f"{model}: {r['error']}. Stopped; no file written.")
                    return 1
            else:
                ok += 1
            answers[c["id"]] = r.get("text") or ""
        path = os.path.join(out_dir, f"{tag}_{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False)
        print(f"{name}: {len(answers)} reports, {errors} errors, {time.time() - t0:.0f} s → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
