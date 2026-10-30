"""Synthetic timing refusals before model execution or clinical persistence."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.clinloop_engine import ct_organs, imaging_ai


def test_invalid_ct_acquisition_timing_refused_before_segmenter():
    segmenter = Mock()
    summary = {"study_date": "20260230", "study_time": "090000", "tz_offset": "+0900"}
    with patch.object(ct_organs, "read_dicom_series", return_value=(Mock(), Mock(), [])), \
         patch.object(ct_organs, "dicom_summary", return_value=summary), \
         patch.object(ct_organs, "qa_checks", return_value=[]):
        with pytest.raises(imaging_ai.ImagingError, match="timing"):
            ct_organs.analyze_ct_series(b"synthetic", "study.zip", "synthetic", ["synthetic"], segmenter)
    segmenter.assert_not_called()


def test_invalid_dicom_sr_acquisition_timing_refused_before_store_access():
    from fastapi import HTTPException
    from src.clinloop_engine import imaging_api
    source = {"patient_id": "synthetic", "study_uid": "synthetic-study", "study_date": "20260230",
              "study_time": "090000", "product": "synthetic", "findings": []}
    with patch.object(imaging_api, "_require_profile"), \
         patch.object(imaging_api, "_patient_resource", return_value={}), \
         patch.object(imaging_api, "_patient_ids", return_value=["synthetic"]), \
         patch.object(imaging_api, "_decode", return_value=b"synthetic"), \
         patch.object(imaging_ai, "parse_dicom_sr", return_value=source), \
         patch.object(imaging_api, "get_store") as store, \
         patch.object(imaging_api, "evaluate_patient") as evaluate:
        with pytest.raises(HTTPException) as err:
            imaging_api.receive_ai_results(imaging_api.AIResults(patient_id="synthetic", dicom_sr_base64="synthetic"),
                                           SimpleNamespace(name="synthetic", role="admin"))
        assert err.value.status_code == 422
    store.assert_not_called()
    evaluate.assert_not_called()
