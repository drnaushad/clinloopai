"""Synthetic unusable measurements cannot close a clinical follow-up."""
from datetime import datetime

import pytest

from src.clinloop_engine.fhir_ingest import bundle_to_events
from src.clinloop_engine.loop_detector import ClinLoopDetector


def observation(identifier, when, value, flag=None):
    result = {"resourceType": "Observation", "id": identifier, "status": "final",
              "subject": {"reference": "Patient/SYNTHETIC-Q"},
              "code": {"coding": [{"system": "http://loinc.org", "code": "3016-3"}], "text": "TSH"},
              "effectiveDateTime": when, "valueQuantity": {"value": value, "unit": "mIU/L"}}
    if flag:
        result["interpretation"] = [{"coding": [{"code": flag}]}]
    return result


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, False, None, "2.0"])
def test_unusable_final_lab_does_not_close_followup(invalid):
    resources = [{"resourceType": "Patient", "id": "SYNTHETIC-Q"},
                 observation("initial", "2026-01-01T00:00:00Z", 10.0, "H"),
                 observation("repeat", "2026-01-10T00:00:00Z", invalid)]
    patients, warnings = bundle_to_events(resources)
    detections = ClinLoopDetector(evaluation_time=datetime(2026, 1, 11)).process_patient(
        "synthetic", "SYNTHETIC-Q", patients["SYNTHETIC-Q"])
    assert [d.loop_status for d in detections if d.rule_id == "R012"] == ["needs_human_review"]
    assert warnings and all("SYNTHETIC-Q" not in w for w in warnings)


def test_valid_finite_repeat_still_closes_followup():
    resources = [{"resourceType": "Patient", "id": "SYNTHETIC-Q"},
                 observation("initial", "2026-01-01T00:00:00Z", 10.0, "H"),
                 observation("repeat", "2026-01-10T00:00:00Z", 2.0)]
    patients, warnings = bundle_to_events(resources)
    detections = ClinLoopDetector(evaluation_time=datetime(2026, 1, 11)).process_patient(
        "synthetic", "SYNTHETIC-Q", patients["SYNTHETIC-Q"])
    assert [d.loop_status for d in detections if d.rule_id == "R012"] == ["closed"]
    assert not warnings


def test_malformed_blood_pressure_component_is_not_completion_evidence():
    resource = {"resourceType": "Observation", "id": "synthetic-bp", "status": "final",
                "subject": {"reference": "Patient/SYNTHETIC-Q"},
                "code": {"coding": [{"code": "85354-9"}]},
                "effectiveDateTime": "2026-01-10T00:00:00Z",
                "component": [{"valueQuantity": {"value": float("nan"), "unit": "mmHg"}}]}
    patients, warnings = bundle_to_events([resource])
    assert not patients.get("SYNTHETIC-Q")
    assert warnings
