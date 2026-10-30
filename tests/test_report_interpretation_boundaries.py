"""Synthetic development challenges for source assertion and lesion identity.

These are contract regressions, not independent clinical accuracy estimates.
No clinical thresholds or evaluation labels are changed by this suite.
"""
import math

import pytest

from src.clinloop_engine.document_reader import parse_report, outside_report_resource
from src.clinloop_engine.ai_review import _mentions, apply_ai_review
from src.clinloop_engine.ecg import SCP_SYSTEM, af_in_text, map_ecg, qtc_ms, scp_statements
from src.clinloop_engine.guideline_reports import _result_sign, classify_lab
from src.clinloop_engine.imaging_ai import ImagingError, _when
from src.clinloop_engine.radiology import map_radiology_report, _critical_findings


@pytest.mark.parametrize("flag,codes", [("ABNORMAL", ["A"]), ("HIGH", ["H"]), ("CRITICAL", ["AA"])])
def test_abnormal_is_not_positive_detection(flag, codes):
    for test in ("HIV Ag/Ab screen", "HBsAg", "QuantiFERON-TB"):
        result = classify_lab([], test, "", flag, None, None, codes)
        assert result["condition"] is None
        assert result.get("review_note")


@pytest.mark.parametrize("text,codes", [("", ["E"]), ("Positive; Negative", []),
                                        ("", ["POS", "NEG"]), ("Negative", ["POS"])])
def test_equivocal_or_conflicting_detection_requires_review(text, codes):
    assert _result_sign(text, None, codes) == "unclear"


def test_detection_does_not_confuse_normal_with_negative_and_preserves_reference_context():
    assert _result_sign("", None, ["N"]) is None
    assert _result_sign("Non-reactive", None, ["NEG"]) == "negative"
    assert _result_sign("Positive (previous: negative); ref: negative", "HIGH", ["POS"]) == "positive"
    assert _result_sign("not positive", None, []) == "negative"


@pytest.mark.parametrize("text", ["Atrial fibrillation is not identified.", "심방세동 없음.",
                                  "Atrial fibrillation?", "Atrial fibrillation cannot be excluded."])
def test_ecg_nonaffirmed_af_does_not_become_diagnosis(text):
    assert not af_in_text(text)
    assert len(map_ecg({}, "2026-01-01", text)) == 1


def test_af_history_and_current_after_negation_remain_detectable():
    assert af_in_text("History of paroxysmal atrial fibrillation.")
    assert af_in_text("No atrial fibrillation on the old ECG. Atrial fibrillation present today.")


@pytest.mark.parametrize("value", [True, "bad", float("nan"), float("inf"), -1, 101])
def test_invalid_scp_likelihood_never_asserts_or_crashes(value):
    resource = {"component": [{"code": {"coding": [{"system": SCP_SYSTEM, "code": "AFIB"}]},
                               "valueQuantity": {"value": value}}]}
    assert scp_statements(resource) == []
    assert len(map_ecg(resource, "2026-01-01", "")) == 1


def test_scp_legacy_unknown_and_explicit_likelihood_semantics_preserved():
    for value, expected in [(0, ["AFIB"]), (15, []), (100, ["AFIB"])]:
        resource = {"component": [{"code": {"coding": [{"system": SCP_SYSTEM, "code": "AFIB"}]},
                                   "valueQuantity": {"value": value}}]}
        assert scp_statements(resource) == expected


@pytest.mark.parametrize("text,expected", [("QTc 5120 ms", 5120), ("QTc 512.25 ms", 512.25),
                                           ("QTc 0.5123 s", 512.3), ("QT/QTc 400/512.25 ms", 512.25),
                                           ("QTc 512 microseconds", None)])
def test_qtc_reads_the_whole_numeric_token_and_declared_unit(text, expected):
    actual = qtc_ms({}, text)
    assert actual is None if expected is None else math.isclose(actual, expected)


def test_same_size_opposite_sides_are_distinct_nodules():
    rad = map_radiology_report("2026-01-01", "CT chest", "6 mm right lung nodule. 6 mm left lung nodule.", {})[0][2]["radiology"]
    assert len(rad["lung_nodules"]) == 2
    assert {n["side"] for n in rad["lung_nodules"]} == {"left", "right"}
    assert all(n["multiple"] for n in rad["lung_nodules"])


def test_location_specific_amendment_preserves_other_same_size_lesion():
    text = "12 mm RUL nodule. 12 mm LLL nodule.\nADDENDUM: The 12 mm LLL nodule is calcified."
    rad = map_radiology_report("2026-01-01", "CT chest", text, {})[0][2]["radiology"]
    assert len(rad["lung_nodules"]) == 2
    assert not next(n for n in rad["lung_nodules"] if n["lobe"] == "RUL")["benign"]
    assert next(n for n in rad["lung_nodules"] if n["lobe"] == "LLL")["benign"]


def test_benign_largest_lesion_cannot_hide_smaller_nonbenign_lesion():
    text = "20 mm calcified RUL nodule. 8 mm LLL nodule."
    rad = map_radiology_report("2026-01-01", "CT chest", text, {})[0][2]["radiology"]
    assert rad["lung_nodule"]["size_mm"] == 8
    assert not rad["lung_nodule"]["benign"]


def test_resolved_second_lesion_does_not_erase_first_lesion_on_same_line():
    text = "8 mm RUL nodule. Previous 4 mm LLL nodule has resolved."
    rad = map_radiology_report("2026-01-01", "CT chest", text, {})[0][2]["radiology"]
    assert len(rad["lung_nodules"]) == 1
    assert rad["lung_nodules"][0]["lobe"] == "RUL"


def test_amended_outside_report_keeps_source_order_and_requires_review():
    text = "CT chest\nIMPRESSION: 8 mm lung nodule.\nADDENDUM: Original measurement incorrect; nodule 4 mm."
    parsed = parse_report(text)
    assert parsed["requires_section_review"]
    assert "ADDENDUM:" in parsed["conclusion"]
    resource = outside_report_resource("synthetic", b"synthetic", {"method": "pdf-text"}, parsed,
                                       confirmed_by="synthetic reviewer")
    tags = {t["code"] for t in resource["meta"]["tag"]}
    assert "section-review" in tags and "human-confirmed" not in tags


def test_history_only_imaging_mentions_do_not_prove_finding_was_addressed():
    report = {"details": {"conclusion": "HISTORY: Prior pneumothorax.\nFINDINGS: No effusion."}}
    assert _mentions(report, "pneumothorax") is None
    report["details"]["conclusion"] += "\nIMPRESSION: No pneumothorax."
    assert _mentions(report, "pneumothorax") is not None


def test_exact_study_link_does_not_allow_report_before_study_to_suppress_urgent_review():
    events = [
        {"event_id": "synthetic-ai", "event_type": "ai_finding", "timestamp": "2026-01-02T09:00:00",
         "status": "final", "details": {"finding_key": "pneumothorax", "positive": True,
                                          "study_uid": "synthetic-study", "study_time": "2026-01-02T08:55:00",
                                          "score": .9, "regions": ["chest"]}},
        {"event_id": "synthetic-report", "event_type": "radiology_report", "timestamp": "2026-01-01T09:00:00",
         "status": "final", "details": {"conclusion": "No pneumothorax.",
                                         "imaging_studies": ["synthetic-study"],
                                         "radiology": {"study_regions": ["chest"]}}},
    ]
    apply_ai_review(events)
    assert any("ai_critical_unread" in e["details"].get("extra_conditions", []) for e in events)
    assert not any(e["event_type"] == "ai_finding_reviewed" for e in events)


def test_multiline_history_does_not_become_current_lung_finding_or_ai_review():
    text = "CLINICAL HISTORY:\n8 mm RUL nodule. Prior pneumothorax.\nFINDINGS:\nNo pulmonary nodules."
    rad = map_radiology_report("2026-01-01", "CT chest", text, {})[0][2]["radiology"]
    assert not rad.get("lung_nodules")
    assert _mentions({"details": {"conclusion": text}}, "pneumothorax") is None
    assert not _critical_findings("CLINICAL HISTORY:\nPrior pneumothorax.\nFINDINGS:\nNo effusion.")
    assert _critical_findings("CLINICAL HISTORY:\nPrior pneumothorax.\nFINDINGS:\nNew right pneumothorax.")


@pytest.mark.parametrize("date,time,offset", [("20260230", "090000", "+0900"),
                                              ("20260101", "250000", "+0900"),
                                              ("20260101", "090000", "+9999"),
                                              (None, "invalid", None)])
def test_explicit_invalid_dicom_timing_never_becomes_current_acquisition(date, time, offset):
    with pytest.raises(ImagingError, match="timing"):
        _when({"study_date": date, "study_time": time, "tz_offset": offset})


def test_missing_dicom_date_keeps_inference_bookkeeping_separate_from_valid_acquisition():
    assert _when({"study_date": None, "study_time": None, "tz_offset": None})
    assert _when({"study_date": "20260101", "study_time": "090000.123", "tz_offset": "+0900"}) == "2026-01-01T09:00:00.123000+09:00"
