"""Draft imaging safeguards: identity before inference, verified probabilities/statuses/units."""
import os
import unittest
from unittest.mock import Mock, patch
import numpy as np
from src.clinloop_engine import imaging_ai
from src.clinloop_engine.ecg import qtc_ms


def summary():
    return {"modality": "DX", "modality_kind": "xray", "body_part": "CHEST", "study_description": "Synthetic chest",
            "series_description": "", "regions": ["chest"], "study_uid": "1.2.3", "series_uid": "1.2.3.4",
            "accession": "", "study_date": "20260101", "study_time": "090000", "tz_offset": "+0900",
            "image_type": ["ORIGINAL"], "burned_in_annotation": False, "has_pixels": True}


class TestImagingIdentityBeforeInference(unittest.TestCase):
    def test_identity_refusals_never_decode_preview_or_discover_models(self):
        for expected, actual in [([], "synthetic-P"), ([None], "synthetic-P"), ([""], "synthetic-P"),
                                 ("synthetic-P", "synthetic-P"), (["synthetic-P"], "synthetic-other"),
                                 (["synthetic-P"], None)]:
            ds = Mock(PatientID=actual, SOPClassUID="1.2.3")
            with self.subTest(expected=expected, actual=actual), \
                 patch.object(imaging_ai, "read_dicom", return_value=ds), \
                 patch.object(imaging_ai, "dicom_summary", return_value=summary()), \
                 patch.object(imaging_ai, "pixel_image") as pixels, \
                 patch.object(imaging_ai, "registered_models") as models, \
                 patch.object(imaging_ai, "_safe_preview") as preview:
                result = imaging_ai.analyze_dicom(b"synthetic-dicom", "synthetic-P", expected)
            self.assertFalse(result["filed"])
            self.assertEqual(result["resources"], [])
            self.assertIsNone(result["preview"])
            pixels.assert_not_called(); models.assert_not_called(); preview.assert_not_called()

    def test_series_with_no_patient_identity_never_calls_vendor(self):
        model = Mock()
        with patch.object(imaging_ai, "read_dicom", return_value=Mock(PatientID="synthetic-P", SOPClassUID="1.2.3")), \
             patch.object(imaging_ai, "dicom_summary", return_value=summary()):
            result = imaging_ai.analyze_series([b"synthetic-dicom"], "synthetic-P", [], [model])
        self.assertFalse(result["filed"])
        model.predict_series.assert_not_called()
        model.available.assert_not_called()


class TestControlledModelFailures(unittest.TestCase):
    def model(self, raw):
        model = Mock(spec=imaging_ai.ImagingModel)
        model.name = "Synthetic model"; model.version = "1"; model.regulatory = "Research use only"
        model.threshold = 0.5; model.needs_pixels = False; model.input = "instance"
        model.describe.return_value = {"name": model.name}
        model.available.return_value = None; model.applies.return_value = None
        model.predict.return_value = raw
        return model

    def test_bad_findings_are_unavailable_without_losing_valid_study(self):
        bad = [None, {}, ["private"], [{"label": []}]]
        bad +=  [[{"label": "Synthetic nodule", "score": value}] for value in
                         (float("nan"), float("inf"), -1, 2, True, "SYNTHETIC_PRIVATE", {})]
        bad += [[{"label": "Synthetic nodule", "positive": value}] for value in ("uncertain", [], 1)]
        for raw in bad:
            model = self.model(raw)
            with self.subTest(raw=raw), patch.object(imaging_ai, "read_dicom", return_value=Mock(PatientID="synthetic-P", SOPClassUID="1.2.3")), \
                 patch.object(imaging_ai, "dicom_summary", return_value=summary()), \
                 patch.object(imaging_ai, "pixel_image", return_value=np.zeros((2, 2))), \
                 patch.object(imaging_ai, "logger") as logger:
                result = imaging_ai.analyze_dicom(b"synthetic-dicom", "synthetic-P", ["synthetic-P"], models=[model], with_preview=False)
            self.assertTrue(result["filed"])
            self.assertEqual([r["resourceType"] for r in result["resources"]], ["ImagingStudy"])
            self.assertFalse(result["models"][0]["ran"])
            self.assertNotIn("SYNTHETIC_PRIVATE", str(logger.mock_calls))
            self.assertNotIn("SYNTHETIC_PRIVATE", str(result))

    def test_series_validation_error_is_a_controlled_model_failure(self):
        model = self.model([])
        model.predict_series = Mock(return_value=[{"label": "Synthetic nodule", "score": float("nan")}])
        with patch.object(imaging_ai, "read_dicom", return_value=Mock(PatientID="synthetic-P", SOPClassUID="1.2.3")), \
             patch.object(imaging_ai, "dicom_summary", return_value=summary()):
            result = imaging_ai.analyze_series([b"synthetic-dicom"], "synthetic-P", ["synthetic-P"], [model])
        self.assertTrue(result["filed"])
        self.assertFalse(result["models"][0]["ran"])
        self.assertEqual([r["resourceType"] for r in result["resources"]], ["ImagingStudy"])


class TestQTcDeclaredUnits(unittest.TestCase):
    def test_explicit_units_override_magnitude_for_value_and_component(self):
        code = {"coding": [{"system": "http://loinc.org", "code": "8636-3"}]}
        for value, unit, expected in [(0.51, "ms", .51), (.51, "s", 510), (510, "ms", 510), (510, "unknown", None),
                                      (float("nan"), "ms", None), (True, "s", None)]:
            quantity = {"value": value, "unit": unit}
            for resource in ({"code": code, "valueQuantity": quantity},
                             {"component": [{"code": code, "valueQuantity": quantity}]}):
                with self.subTest(value=value, unit=unit, resource=resource):
                    self.assertEqual(qtc_ms(resource, ""), expected)
        self.assertEqual(qtc_ms({}, "QTc 0.51 ms"), .51)
        self.assertEqual(qtc_ms({}, "QTc 0.51 s"), 510)


class TestAIReportVerification(unittest.TestCase):
    @patch.dict(os.environ, {"CLINLOOP_PROFILE": "research"})
    def test_unknown_or_void_report_cannot_suppress_urgent_unread_loop(self):
        from src.clinloop_engine.fhir_ingest import bundle_to_events
        from src.clinloop_engine.loop_detector import ClinLoopDetector
        from src.clinloop_engine.imaging_fhir import ai_observation_resource
        from datetime import datetime
        ai = ai_observation_resource("synthetic-P", "Intracranial hemorrhage", .9, True, "Synthetic product", "1",
                                     "MFDS approved", "ImagingStudy/synthetic-study", "2026-01-01T00:00:00Z")
        for status in (None, "unknown", "cancelled", "preliminary", "draft"):
            report = {"resourceType": "DiagnosticReport", "id": "synthetic-report", "status": status,
                      "subject": {"reference": "Patient/synthetic-P"}, "category": [{"coding": [{"code": "RAD"}]}],
                      "code": {"text": "CT head"}, "effectiveDateTime": "2026-01-01T00:00:00Z",
                      "imagingStudy": [{"reference": "ImagingStudy/synthetic-study"}], "conclusion": "No acute abnormality."}
            events, _ = bundle_to_events([ai, report])
            found = ClinLoopDetector(evaluation_time=datetime(2026, 1, 1, 2)).process_patient("test", "synthetic-P", events["synthetic-P"])
            with self.subTest(status=status):
                self.assertTrue(any(d.rule_id == "R057" and d.loop_status == "open" for d in found))
