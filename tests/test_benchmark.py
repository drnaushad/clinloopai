"""ClinLoop-Bench: deterministic build, schema, scorer correctness, synthetic-only content, baselines run.

The benchmark data are exported from the evaluation sets under tests/ by scripts/build_benchmark.py. Those
sets grow with each blind round, so the committed files can lag the sources: test_committed_data_is_current
skips with a "re-run the build" message when the sources changed (set CLINLOOP_BENCH_STRICT=1 to fail
instead, e.g. in a release check). After every evaluation round: python scripts/build_benchmark.py
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "benchmark", "data", "v1.0")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_benchmark  # noqa: E402

# Loaded under its own name: tests/blind_reports_2/score.py is also imported as "score" by other tests.
_spec = importlib.util.spec_from_file_location("clinloop_bench_score", os.path.join(ROOT, "benchmark", "score.py"))
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)

FILES = ("t1_report_obligations.jsonl", "t2_loop_status.jsonl", "t3_korean_mixed.jsonl")


def _read(d):
    return {f: open(os.path.join(d, f), "rb").read() for f in FILES + ("manifest.json",)}


@pytest.fixture(scope="module")
def fresh():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        build_benchmark.build(a)
        build_benchmark.build(b)
        ra, rb = _read(a), _read(b)
        yield ra, rb


@pytest.fixture(scope="module")
def records():
    return score.load_gold(DATA)


def test_build_is_deterministic(fresh):
    ra, rb = fresh
    assert ra == rb


def test_committed_data_is_current(fresh):
    ra, _ = fresh
    committed = _read(DATA)
    if committed != ra:
        msg = "benchmark/data/v1.0 differs from the sources: run python scripts/build_benchmark.py"
        if os.environ.get("CLINLOOP_BENCH_STRICT") == "1":
            pytest.fail(msg)
        pytest.skip(msg)


def test_split_is_seeded_and_stable():
    assert build_benchmark.split_for("report_eval:C001") == build_benchmark.split_for("report_eval:C001")
    splits = [build_benchmark.split_for(f"x:{i}") for i in range(2000)]
    assert 0.25 < splits.count("dev") / len(splits) < 0.35


def test_records_match_schema(records):
    schema = json.load(open(os.path.join(ROOT, "benchmark", "schema.json"), encoding="utf-8"))
    req = set(schema["required"])
    for r in records:
        assert req <= set(r) and set(r) <= set(schema["properties"]), r["id"]
        assert r["task"] in ("T1", "T2", "T3") and r["split"] in ("dev", "test") and r["synthetic"] is True
        assert (r["task"] == "T1") == (r["language"] == "en") or r["task"] == "T2"
        assert r["input"]["fhir_bundle"]["resourceType"] == "Bundle"
        if r["task"] == "T2":
            assert r["gold"]["obligations"] is not None
    jsonschema = pytest.importorskip("jsonschema")
    v = jsonschema.Draft202012Validator(schema)
    for r in records:
        v.validate(r)
    assert len({r["id"] for r in records}) == len(records)


NAME_RE = re.compile(r"\b(MRN|SSN|주민등록번호)\b|\b\d{6}-\d{7}\b|\b\d{3}-\d{3,4}-\d{4}\b")
PII_KEYS = {"name", "identifier", "telecom", "address", "photo", "contact"}


def _walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def test_every_record_is_synthetic_and_carries_no_identifiers(records):
    for r in records:
        assert r["synthetic"] is True
        for e in r["input"]["fhir_bundle"]["entry"]:
            assert not PII_KEYS & set(e["resource"]), r["id"]
        blob = json.dumps(r["input"], ensure_ascii=False)
        assert not NAME_RE.search(blob), r["id"]


def _rec(rid, task, rules, obligations=None, spans=None, scope=("R003", "R030", "R036")):
    return {"id": rid, "task": task, "split": "test",
            "gold": {"rules": rules, "scope_rules": list(scope), "evidence_spans": spans, "obligations": obligations}}


def test_scorer_on_hand_examples():
    groups = {"T1": [["R003", "R030"]], "T2": [["R003", "R030"]]}
    gold = [_rec("a", "T1", ["R003"], spans={"R003": "Recommend CT in 12 months."}),
            _rec("b", "T1", []),
            _rec("c", "T1", ["R036"]),
            _rec("d", "T2", ["R003"], {"R003": {"status": "open", "overdue": True, "deadline_days": None, "source_label": "missed"}}),
            _rec("e", "T2", ["R030"], {"R030": {"status": "closed", "overdue": False, "deadline_days": None, "source_label": "done"}})]
    preds = {"a": {"id": "a", "rules": ["R030"], "evidence": {"R003": "Recommend CT in 12 months."}},
             "b": {"id": "b", "rules": ["R036"]},
             "c": {"id": "c", "rules": ["R036", "R999"]},  # R999 out of scope: ignored
             "d": {"id": "d", "obligations": {"R003": {"status": "closed", "overdue": False}}},
             "e": {"id": "e", "obligations": {"R003": {"status": "closed", "overdue": False}}}}  # same finding group
    res = score.score(gold, preds, "test", n_boot=50, groups=groups)
    t1 = res["T1"]
    # rules: tp=1 (c), fp=2 (a:R030, b:R036), fn=1 (a:R003)
    assert t1["rule_precision"]["value"] == pytest.approx(1 / 3)
    assert t1["rule_recall"]["value"] == pytest.approx(1 / 2)
    assert t1["rule_f1"]["value"] == pytest.approx(0.4)
    assert t1["finding_f1"]["value"] == pytest.approx(2 * 2 / (2 * 2 + 1 + 0))  # a matches by group
    assert t1["specificity"]["value"] == 0.0
    assert t1["needs_followup_recall"]["value"] == 1.0
    assert t1["evidence_token_f1"]["value"] == pytest.approx(1.0)
    lo, hi = t1["rule_f1"]["ci95"]
    assert lo <= hi
    t2 = res["T2"]
    assert t2["status_accuracy"]["value"] == 0.5
    assert t2["overdue_accuracy"]["value"] == 0.5
    assert t2["false_closure"] == 1
    # needs_human_review counts as correct for a gold open loop
    preds["d"]["obligations"]["R003"] = {"status": "needs_human_review", "overdue": True}
    assert score.score(gold, preds, "test", 0, groups)["T2"]["status_accuracy"]["value"] == 1.0


def test_bootstrap_is_seeded():
    gold = [_rec(str(i), "T1", ["R003"] if i % 2 else []) for i in range(30)]
    preds = {str(i): {"id": str(i), "rules": ["R003"] if i % 3 else []} for i in range(30)}
    assert json.dumps(score.score(gold, preds, "test", 200)) == json.dumps(score.score(gold, preds, "test", 200))


def test_token_f1():
    assert score.token_f1("12개월 후 추적 CT 권고", "12개월 후 추적 CT 권고") == 1.0
    assert score.token_f1("a b", "c d") == 0.0


def test_baselines_run(tmp_path):
    out = subprocess.run([sys.executable, os.path.join(ROOT, "benchmark", "baselines", "run_baselines.py"),
                          "--out", str(tmp_path), "--no-results", "--bootstrap", "50"],
                         capture_output=True, text=True, timeout=600, env={**os.environ, "CLINLOOP_OLLAMA_URL": "http://127.0.0.1:9"})
    assert out.returncode == 0, out.stderr[-2000:]
    rules = score.load_jsonl(os.path.join(tmp_path, "rules.jsonl"))
    kw = score.load_jsonl(os.path.join(tmp_path, "keyword.jsonl"))
    assert len(rules) == len(kw) == len(score.load_gold(DATA))
    res = score.score(score.load_gold(DATA), {p["id"]: p for p in rules}, "test", 0, score.load_groups(DATA))
    assert res["T1"]["needs_followup_f1"]["value"] > 0.9
    assert res["T2"]["false_closure"] == 0
