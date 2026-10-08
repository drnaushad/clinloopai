"""
test_imaging.py — PACS study labels, imaging-AI second reader, outside reports (PDF/OCR), DICOM analysis

All images are synthetic (numpy arrays); no real patient data.
"""

import base64
import io
import json
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {
    "admin": "test-admin-token-0123456789",
    "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234",
    "viewer": "test-viewer-token-0123456789",
}
os.environ.setdefault("CLINLOOP_API_TOKENS", ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items()))

from src.clinloop_engine.document_reader import ocr_available, outside_report_resource, parse_report  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.imaging_fhir import (  # noqa: E402
    ai_finding_key, ai_observation_resource, dicom_regions, imaging_study_resource,
)
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore  # noqa: E402
from src.clinloop_engine.pacs_client import DICOMwebClient, imaging_studies_for, pacs_patient_ids  # noqa: E402

try:
    import pydicom  # noqa: F401
    HAVE_DICOM = True
except ImportError:
    HAVE_DICOM = False
try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:
    HAVE_API = False

P = {"resourceType": "Patient", "id": "P", "birthDate": "1960-01-01", "gender": "male",
     "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "MRN-0042"}]}


def rad(rid, when, title, text, study=None):
    r = {"resourceType": "DiagnosticReport", "id": rid, "status": "final", "category": [{"coding": [{"code": "RAD"}]}],
         "code": {"text": title}, "subject": {"reference": "Patient/P"}, "effectiveDateTime": when, "conclusion": text}
    if study:
        r["imagingStudy"] = [{"reference": study}]
    return r


def loops(resources, when):
    events, warnings = bundle_to_events(resources)
    assert warnings == [], warnings
    dets = ClinLoopDetector(evaluation_time=when).process_patient("f", "P", events["P"])
    out = {}
    for d in dets:
        out.setdefault(d.rule_id, []).append(d.loop_status.replace("needs_human_review", "open"))
    return {k: v[0] if len(v) == 1 else sorted(v) for k, v in out.items()}, dets


def make_dicom(arr, modality="DX", body="CHEST", desc="Chest PA", pid="MRN-0042", date="20260110", view="PA",
               bits=8, extra=None):
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.1.1"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.PatientID, ds.PatientName = pid, "SYNTHETIC^PATIENT"
    ds.Modality, ds.StudyDescription, ds.StudyDate, ds.StudyTime = modality, desc, date, "093000"
    if body:
        ds.BodyPartExamined = body
    ds.ViewPosition = view
    ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
    ds.ImageType = ["ORIGINAL", "PRIMARY"]
    ds.Rows, ds.Columns = arr.shape
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated = 16 if bits > 8 else 8
    ds.BitsStored, ds.HighBit, ds.PixelRepresentation = bits, bits - 1, 0
    for k, v in (extra or {}).items():
        setattr(ds, k, v)
    ds.PixelData = arr.astype(np.uint16 if bits > 8 else np.uint8).tobytes()
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def phantom(n=256):
    y, x = np.mgrid[:n, :n]
    img = 60 + 120 * (((x - n / 2) ** 2 / (n * 0.35) ** 2 + (y - n / 2) ** 2 / (n * 0.45) ** 2) < 1)
    return img.astype(np.uint8)


class StubModel:
    """A deterministic imaging model for tests."""
    name, version, regulatory, threshold = "Stub CXR", "1", "MFDS approved (test stub)", 0.5
    intended_use, modalities, body_regions = "test", ["DX", "CR"], ["chest"]

    def __init__(self, scores):
        self.scores = scores

    def available(self):
        return None

    def applies(self, summary):
        return None if summary["modality"] in self.modalities else "for DX/CR only"

    def predict(self, ds, img, content):
        return [{"label": k, "score": v} for k, v in self.scores.items()]

    def describe(self):
        return {"name": self.name, "version": self.version, "regulatory": self.regulatory, "research_use": False,
                "intended_use": self.intended_use, "modalities": self.modalities, "body_regions": self.body_regions,
                "threshold": self.threshold, "status": "ready"}


# ── PACS study labels ───────────────────────────────────────────────────────

class TestPACSStudies(unittest.TestCase):

    def test_dicom_body_part_vocabulary(self):
        self.assertIn("adrenal", dicom_regions("ABDOMENPELVIS"))
        self.assertIn("chest", dicom_regions("CHESTABDPELVIS"))
        self.assertIn("head", dicom_regions("", "CT BRAIN W/O"))
        self.assertIn("abdominal_aorta", dicom_regions("AORTA"))

    def test_study_closes_followup_only_in_the_right_region(self):
        base = [P, rad("a", "2026-01-10T09:00:00Z", "CT abdomen",
                       "Indeterminate 18 mm left adrenal nodule. Recommend adrenal protocol CT in 3 months.")]
        abd = imaging_study_resource({"study_uid": "1.2.3", "modalities": ["CT"], "body_part": "ABDOMEN",
                                      "study_date": "20260320"}, "P", "pacs")
        head = imaging_study_resource({"study_uid": "1.2.4", "modalities": ["CT"], "body_part": "HEAD",
                                       "study_date": "20260320"}, "P", "pacs")
        self.assertEqual(loops(base + [abd], datetime(2026, 6, 1))[0], {"R030": "closed"})
        self.assertEqual(loops(base + [head], datetime(2026, 6, 1))[0], {"R030": "open"})

    def test_registered_or_cancelled_study_is_not_a_followup(self):
        base = [P, rad("a", "2026-01-10T09:00:00Z", "CT chest", "9 mm solid nodule in the right lower lobe.")]
        booked = imaging_study_resource({"study_uid": "1.2.5", "modalities": ["CT"], "body_part": "CHEST",
                                         "study_date": "20260301", "status": "registered"}, "P", "pacs")
        self.assertEqual(loops(base + [booked], datetime(2026, 6, 1))[0], {"R003": "open"})

    def test_qido_client_maps_studies(self):
        study = {"0020000D": {"vr": "UI", "Value": ["1.2.840.1"]}, "00080020": {"vr": "DA", "Value": ["20260301"]},
                 "00080030": {"vr": "TM", "Value": ["101500"]}, "00081030": {"vr": "LO", "Value": ["CT CHEST LOW DOSE"]},
                 "00080061": {"vr": "CS", "Value": ["CT"]}, "00080050": {"vr": "SH", "Value": ["ACC1"]},
                 "00100010": {"vr": "PN", "Value": [{"Alphabetic": "HONG^GILDONG"}]}}
        series = [{"0020000E": {"vr": "UI", "Value": ["1.2.840.1.1"]}, "00080060": {"vr": "CS", "Value": ["CT"]},
                   "00180015": {"vr": "CS", "Value": ["CHEST"]}}]

        class Resp:
            def __init__(self, body):
                self.status_code, self.body = 200, body

            def json(self):
                return self.body

        session = mock.Mock()
        session.get.side_effect = lambda url, **kw: Resp(series if url.endswith("/series") else [study])
        client = DICOMwebClient("https://pacs.example/dicom-web", session=session)
        resources = imaging_studies_for(client, "P", P)
        self.assertEqual(session.get.call_args_list[0].kwargs["params"]["PatientID"], "MRN-0042")
        self.assertEqual(len(resources), 1)
        r = resources[0]
        self.assertEqual((r["resourceType"], r["started"], r["series"][0]["bodySite"]["display"]),
                         ("ImagingStudy", "2026-03-01T10:15:00+09:00", "CHEST"))   # DICOM local time, Asia/Seoul
        self.assertNotIn("HONG", json.dumps(r))          # no patient name stored

    def test_patient_id_mapping(self):
        self.assertEqual(pacs_patient_ids(P, "P"), ["MRN-0042"])
        self.assertEqual(pacs_patient_ids({"identifier": []}, "P"), [])          # never guess
        with mock.patch.dict(os.environ, {"CLINLOOP_PACS_MATCH_FHIR_ID": "1"}):
            self.assertEqual(pacs_patient_ids({"identifier": []}, "P"), ["P"])
        insurance = {"identifier": [{"system": "urn:nhis", "value": "123"}]}
        self.assertEqual(pacs_patient_ids(insurance, "P"), [])

    def test_study_of_another_patient_is_rejected(self):
        from src.clinloop_engine.pacs_client import PACSError
        other = {"0020000D": {"vr": "UI", "Value": ["1.2.9"]}, "00100020": {"vr": "LO", "Value": ["MRN-9999"]},
                 "00080061": {"vr": "CS", "Value": ["CT"]}}

        class Resp:
            status_code = 200

            def __init__(self, body):
                self.body = body

            def json(self):
                return self.body
        session = mock.Mock()
        session.get.side_effect = lambda url, **kw: Resp([] if url.endswith("/series") else [other])
        client = DICOMwebClient("https://pacs.example/dicom-web", session=session)
        self.assertEqual(client.studies("MRN-0042"), [])
        with self.assertRaises(PACSError):
            client.studies("12*")
        session.get.side_effect = lambda url, **kw: Resp({"error": "bad request"})
        with self.assertRaises(PACSError):
            client.studies("MRN-0042")

    def test_pacs_outage_is_a_warning_not_a_crash(self):
        from src.clinloop_engine.fhir_sync import patient_record
        from src.clinloop_engine.pacs_client import PACSError
        store = LoopStore()
        store.save_snapshot("P", [P])
        pacs = mock.Mock()
        pacs.studies.side_effect = PACSError("HTTP 503")
        resources, warnings = patient_record("P", store, None, pacs)
        self.assertEqual(resources, [P])
        self.assertTrue(any("PACS unreachable" in w for w in warnings))


# ── Imaging AI as second reader ─────────────────────────────────────────────

class TestAIReview(unittest.TestCase):

    def setUp(self):
        self.study = imaging_study_resource({"study_uid": "9.9", "modalities": ["DX"], "body_part": "CHEST",
                                             "study_date": "20260110", "study_time": "080000"}, "P", "pacs")
        self.ref = "ImagingStudy/" + self.study["id"]

    def ai(self, label="Nodule", score=0.87, positive=True, regulatory="MFDS approved (Class II)"):
        return ai_observation_resource("P", label, score, positive, "Vendor CXR", "3.1", regulatory, self.ref,
                                       "2026-01-10T08:05:00")

    def report(self, text, rid="r1", when="2026-01-10T10:00:00Z"):
        return rad(rid, when, "Chest radiograph PA", text, self.ref)

    def test_finding_missing_from_report_opens_review(self):
        statuses, dets = loops([P, self.study, self.ai(), self.report("No acute cardiopulmonary abnormality.")],
                               datetime(2026, 1, 20))
        self.assertEqual(statuses, {"R047": "open"})
        self.assertTrue(any("does not mention it" in line for line in dets[0].evidence_chain))

    def test_report_that_confirms_or_refutes_is_enough(self):
        for text in ("1 cm right upper lobe nodule. Recommend CT chest in 3 months.", "No suspicious pulmonary nodule."):
            statuses, _ = loops([P, self.study, self.ai(), self.report(text)], datetime(2026, 1, 20))
            self.assertNotIn("R047", statuses, text)

    def test_addendum_closes_review(self):
        statuses, _ = loops([P, self.study, self.ai(), self.report("No acute abnormality."),
                             self.report("Addendum: 1 cm right upper lobe nodule on review.", "r2", "2026-01-12T09:00:00Z")],
                            datetime(2026, 1, 20))
        self.assertEqual(statuses["R047"], "closed")

    def test_each_finding_is_reviewed_separately(self):
        ptx = ai_observation_resource("P", "Pneumothorax", 0.9, True, "Vendor CXR", "3.1", "MFDS approved", self.ref,
                                      "2026-01-10T08:05:00")
        statuses, dets = loops([P, self.study, self.ai(), ptx, self.report("No acute abnormality."),
                                self.report("Addendum: small right pneumothorax.", "r2", "2026-01-11T08:00:00Z")],
                               datetime(2026, 1, 20))
        self.assertEqual(sorted(statuses["R047"]), ["closed", "open"])   # pneumothorax reviewed, nodule not
        late, _ = loops([P, self.study, ptx, self.report("No acute abnormality."),
                         self.report("Addendum: small right pneumothorax.", "r2", "2026-01-12T09:00:00Z")],
                        datetime(2026, 1, 20))
        self.assertEqual(late["R047"], "delayed")                         # critical: due within 1 day
        self.assertEqual(late["R035"], "open")    # the addendum's pneumothorax must also be communicated
        ptx_loop = next(d for d in dets if "Pneumothorax" in " ".join(d.evidence_chain))
        self.assertLess((datetime.fromisoformat(ptx_loop.deadline) - datetime.fromisoformat(ptx_loop.trigger_time)).days, 2)

    def test_dicom_local_time_is_compared_in_the_hospital_time_zone(self):
        """A 09:30 KST study read at 11:00+09:00 the same morning: the report comes after the study."""
        with mock.patch.dict(os.environ, {"CLINLOOP_LOCAL_TZ": "Asia/Seoul"}):
            study = imaging_study_resource({"study_uid": "7.7", "modalities": ["DX"], "body_part": "CHEST",
                                            "study_date": "20260301", "study_time": "093000"}, "P", "dicom-upload")
            ref = "ImagingStudy/" + study["id"]
            obs = ai_observation_resource("P", "Nodule", 0.9, True, "Vendor CXR", "3.1", "MFDS approved", ref,
                                          study["started"])
            report = rad("rk", "2026-03-01T11:00:00+09:00", "Chest radiograph PA", "No acute abnormality.")
            self.assertEqual(loops([P, study, obs, report], datetime(2026, 3, 5))[0], {"R047": "open"})

    def test_no_report_yet_means_no_loop(self):
        self.assertEqual(loops([P, self.study, self.ai()], datetime(2026, 1, 20))[0], {})

    def test_negative_or_low_score_is_ignored(self):
        for obs in (self.ai(positive=False), self.ai(score=0.2, positive=None)):
            statuses, _ = loops([P, self.study, obs, self.report("No acute abnormality.")], datetime(2026, 1, 20))
            self.assertEqual(statuses, {})

    def test_research_model_findings_need_opt_in(self):
        obs = self.ai(regulatory="Research use only")
        base = [P, self.study, obs, self.report("No acute abnormality.")]
        self.assertEqual(loops(base, datetime(2026, 1, 20))[0], {})
        with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_RESEARCH_AI": "1"}):
            self.assertEqual(loops(base, datetime(2026, 1, 20))[0], {"R047": "open"})

    def test_vendor_percent_scores_and_labels(self):
        obs = self.ai(score=None, positive=None)
        obs["valueQuantity"] = {"value": 87, "unit": "%"}
        events, _ = bundle_to_events([P, obs])
        d = events["P"][0]["details"]
        self.assertEqual((d["finding_key"], d["score"], d["positive"]), ("lung_nodule", 0.87, True))
        self.assertEqual(ai_finding_key("Lung Opacity"), "consolidation")
        self.assertEqual(ai_finding_key("Malignancy score", ["breast"]), "breast_malignancy")
        self.assertIsNone(ai_finding_key("Malignancy score", ["chest"]))


# ── Outside reports ─────────────────────────────────────────────────────────

class TestOutsideReports(unittest.TestCase):

    EN = ("SEOUL OUTSIDE HOSPITAL\nPatient: Hong Gil-dong DOB: 1960-04-12 Phone: 010-1234-5678\n"
          "Exam: CT Chest without contrast\nExam date: 2026-05-14\nFINDINGS:\nThere is a 1.3 crn solid nodule.\n"
          "IMPRESSION:\n1. 1.3 cm spiculated solid nodule in the right upper lobe, suspicious for malignancy.\n"
          "Electronically signed by Dr. Kim")
    KO = ("외부병원 판독지\n환자명: 홍길동 생년월일: 1958년 3월 2일\n검사명: 복부 CT\n검사일자: 2026년 4월 3일\n"
          "판독소견: 좌측 부신에 2.4 cm 크기의 결절이 있습니다.\n결론: 좌측 부신 결절 2.4 cm. 3개월 후 추적 CT 권고.\n판독의: 이영희")

    def test_parse_english(self):
        p = parse_report(self.EN)
        self.assertEqual((p["title"], p["date"], p["section"]), ("CT Chest without contrast", "2026-05-14", "impression"))
        self.assertIn("1.3 cm spiculated solid nodule", p["conclusion"])
        self.assertNotIn("Electronically", p["conclusion"])

    def test_parse_korean_skips_birth_date(self):
        p = parse_report(self.KO)
        self.assertEqual((p["title"], p["date"]), ("복부 CT", "2026-04-03"))
        self.assertTrue(p["conclusion"].startswith("좌측 부신 결절 2.4 cm"))

    def test_unconfirmed_outside_report_needs_review(self):
        parsed = parse_report(self.EN)
        resource = outside_report_resource("P", b"file", {"method": "ocr", "confidence": 88.0}, parsed)
        self.assertNotIn("010-1234-5678", json.dumps(resource))
        events, _ = bundle_to_events([P, resource])
        dets = ClinLoopDetector(evaluation_time=datetime(2026, 5, 20)).process_patient("f", "P", events["P"])
        self.assertEqual([(d.rule_id, d.loop_status) for d in dets], [("R003", "needs_human_review")])
        self.assertTrue(any("outside report (OCR" in line for line in dets[0].evidence_chain))
        confirmed = outside_report_resource("P", b"file", {"method": "ocr", "confidence": 88.0}, parsed, confirmed_by="rn.park")
        events, _ = bundle_to_events([P, confirmed])
        self.assertNotIn("review_note_all", events["P"][0]["details"])

    def test_pdf_text_layer(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab not installed")
        from src.clinloop_engine.document_reader import extract_text
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 800
        for line in self.EN.splitlines():
            c.drawString(40, y, line)
            y -= 20
        c.save()
        out = extract_text(buf.getvalue(), "report.pdf")
        self.assertEqual(out["method"], "pdf-text")
        self.assertEqual(parse_report(out["text"])["date"], "2026-05-14")

    @unittest.skipUnless(ocr_available(), "Tesseract not installed")
    def test_ocr_of_a_scanned_report(self):
        from PIL import Image, ImageDraw, ImageFont
        from src.clinloop_engine.document_reader import extract_text
        lines = ["Exam: CT Chest without contrast", "Exam date: 2026-05-14", "IMPRESSION:",
                 "1.3 cm spiculated solid nodule in the right upper lobe."]
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 30)
        except OSError:
            font = ImageFont.load_default()
        img = Image.new("L", (1600, 300), 255)
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            d.text((40, 30 + i * 60), line, fill=0, font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = extract_text(buf.getvalue(), "scan.png")
        self.assertEqual(out["method"], "ocr")
        p = parse_report(out["text"])
        self.assertEqual(p["date"], "2026-05-14")
        self.assertIn("nodule", p["conclusion"])


# ── DICOM analysis ──────────────────────────────────────────────────────────

@unittest.skipUnless(HAVE_DICOM, "pydicom not installed")
class TestDicomAnalysis(unittest.TestCase):

    def test_header_study_and_findings(self):
        from src.clinloop_engine.imaging_ai import analyze_dicom
        out = analyze_dicom(make_dicom(phantom()), "P", ["P", "MRN-0042"],
                            models=[StubModel({"Nodule": 0.81, "Mass": 0.66, "Pneumothorax": 0.1, "Emphysema": 0.7})])
        self.assertTrue(out["filed"])
        self.assertEqual(out["qa"], [])
        self.assertEqual(out["summary"]["regions"], ["chest", "lung"])
        self.assertNotIn("SYNTHETIC", json.dumps(out["summary"]))
        kinds = [r["resourceType"] for r in out["resources"]]
        self.assertEqual(kinds, ["ImagingStudy", "Observation", "Observation"])   # nodule+mass merged, PTX negative
        labels = [r["code"]["text"] for r in out["resources"][1:]]
        self.assertIn("Mass / Nodule", labels)
        self.assertTrue(out["preview"].startswith("data:image/png;base64,"))

    def test_wrong_patient_is_refused(self):
        from src.clinloop_engine.imaging_ai import analyze_dicom
        out = analyze_dicom(make_dicom(phantom(), pid="SOMEONE-ELSE"), "P", ["P", "MRN-0042"], models=[])
        self.assertFalse(out["filed"])
        self.assertEqual(out["resources"], [])
        self.assertEqual([c["code"] for c in out["qa"]], ["patient_mismatch"])

    def test_qa_warnings(self):
        from src.clinloop_engine.imaging_ai import analyze_dicom
        out = analyze_dicom(make_dicom(phantom(), body="", desc="", extra={"ImageType": ["DERIVED", "SECONDARY"],
                                                                         "BurnedInAnnotation": "YES"}),
                            "P", ["MRN-0042"], models=[])
        self.assertEqual({c["code"] for c in out["qa"]}, {"not_original", "burned_in_phi", "region_unknown"})
        self.assertTrue(out["filed"])

    def test_ct_windowing_and_model_scope(self):
        from src.clinloop_engine.imaging_ai import analyze_dicom
        ct = (np.random.RandomState(42).rand(128, 128) * 1500).astype(np.uint16)
        out = analyze_dicom(make_dicom(ct, modality="CT", body="ABDOMEN", desc="CT ABD", bits=12,
                                       extra={"RescaleSlope": 1, "RescaleIntercept": -1024,
                                              "WindowCenter": 40, "WindowWidth": 400}),
                            "P", ["MRN-0042"], models=[StubModel({"Nodule": 0.9})])
        self.assertEqual(out["models"][0]["ran"], False)                  # a CXR model does not read CT
        self.assertIn("adrenal", out["summary"]["regions"])

    def test_uploaded_study_closes_followup(self):
        from src.clinloop_engine.imaging_ai import analyze_dicom
        out = analyze_dicom(make_dicom(phantom(), modality="CT", body="CHEST", desc="CT CHEST", date="20260401"),
                            "P", ["MRN-0042"], models=[])
        base = [P, rad("a", "2026-01-10T09:00:00Z", "CT chest", "9 mm solid nodule in the right lower lobe.")]
        self.assertEqual(loops(base + out["resources"], datetime(2026, 6, 1))[0], {"R003": "closed"})

    def test_dicom_sr_findings(self):
        from pydicom.dataset import Dataset
        from src.clinloop_engine.imaging_ai import parse_dicom_sr

        def code(meaning):
            c = Dataset()
            c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = "x", "99TEST", meaning
            return c
        finding = Dataset()
        finding.ValueType, finding.ConceptNameCodeSequence, finding.ConceptCodeSequence = "CODE", [code("Finding")], [code("Nodule")]
        num = Dataset()
        num.ValueType, num.ConceptNameCodeSequence = "NUM", [code("Probability of malignancy")]
        mv = Dataset()
        mv.NumericValue, mv.MeasurementUnitsCodeSequence = "87", [code("%")]
        num.MeasuredValueSequence = [mv]
        def item(meaning_name, value, unit="%"):
            n = Dataset()
            n.ValueType, n.ConceptNameCodeSequence = "NUM", [code(meaning_name)]
            v = Dataset()
            v.NumericValue, v.MeasurementUnitsCodeSequence = str(value), [code(unit)]
            n.MeasuredValueSequence = [v]
            return n

        def finding_of(label):
            f = Dataset()
            f.ValueType, f.ConceptNameCodeSequence, f.ConceptCodeSequence = "CODE", [code("Finding")], [code(label)]
            return f
        effusion = finding_of("Effusion")
        unscored = finding_of("Pneumothorax")
        tenscale = finding_of("Fracture")
        group = Dataset()
        group.ValueType, group.ConceptNameCodeSequence = "CONTAINER", [code("Imaging finding")]
        group.ContentSequence = [finding, num, effusion, item("Probability", 5), unscored, tenscale, item("Score", 7, "{score}")]
        raw = make_dicom(phantom(16), extra={"ContentSequence": [group], "Manufacturer": "VendorX",
                                             "ManufacturerModelName": "CXR AI"})
        out = parse_dicom_sr(raw)
        by = {f["label"]: f for f in out["findings"]}
        self.assertEqual((by["Nodule"]["score"], by["Effusion"]["score"]), (0.87, 0.05))   # each keeps its own score
        self.assertEqual((by["Pneumothorax"]["score"], by["Pneumothorax"]["positive"]), (None, True))
        self.assertEqual((by["Fracture"]["score"], by["Fracture"]["raw_score"]), (None, 7.0))  # unknown scale: not guessed
        self.assertIn("VendorX", out["product"])

    def test_torchxrayvision_if_installed(self):
        from src.clinloop_engine.imaging_ai import TorchXRayVisionModel, analyze_dicom
        model = TorchXRayVisionModel()
        weights = os.path.expanduser("~/.torchxrayvision/models_data")
        if model.available() or not (os.path.isdir(weights) and os.listdir(weights)):
            self.skipTest("torchxrayvision or its weights not available")
        out = analyze_dicom(make_dicom(phantom(320)), "P", ["MRN-0042"], models=[model])
        result = out["models"][0]
        self.assertTrue(result["ran"])
        self.assertTrue(result["research_use"])
        self.assertEqual(len(result["findings"]), 18)


# ── API ─────────────────────────────────────────────────────────────────────

def _h(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


@unittest.skipUnless(HAVE_API and HAVE_DICOM, "API dependencies or pydicom not installed")
class TestImagingAPI(unittest.TestCase):

    def setUp(self):
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        bundle = {"resourceType": "Bundle", "entry": [{"resource": r} for r in [
            P, rad("r1", "2026-01-10T10:00:00Z", "Chest radiograph PA", "No acute cardiopulmonary abnormality.")]]}
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-01-11T00:00:00", json=bundle, headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)

    def test_models_endpoint_is_public(self):
        r = self.client.get("/api/v1/imaging/models")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ocr", r.json())

    def test_analyze_files_study_and_opens_review(self):
        from src.clinloop_engine import imaging_ai
        payload = {"patient_id": "P", "filename": "cxr.dcm",
                   "content_base64": base64.b64encode(make_dicom(phantom(), date="20260110")).decode()}
        with mock.patch.object(imaging_ai, "registered_models", lambda: [StubModel({"Nodule": 0.9})]):
            self.assertEqual(self.client.post("/api/v1/imaging/analyze", json=payload, headers=_h("viewer")).status_code, 403)
            r = self.client.post("/api/v1/imaging/analyze", json=payload, headers=_h("navigator"))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["filed"])
        self.assertIn("R047", [a["rule_id"] for a in body["active"]])
        docs = self.client.get("/api/v1/patients/P/documents", headers=_h("viewer")).json()["documents"]
        self.assertEqual(sorted(d["kind"] for d in docs), ["dicom-study", "imaging-ai"])

    def test_wrong_patient_image_is_not_filed(self):
        payload = {"patient_id": "P", "content_base64": base64.b64encode(make_dicom(phantom(), pid="OTHER")).decode()}
        body = self.client.post("/api/v1/imaging/analyze", json=payload, headers=_h("navigator")).json()
        self.assertFalse(body["filed"])
        self.assertEqual(self.client.get("/api/v1/patients/P/documents", headers=_h("viewer")).json()["documents"], [])

    def test_outside_report_extract_then_file(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab not installed")
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        for i, line in enumerate(TestOutsideReports.EN.splitlines()):
            c.drawString(40, 800 - i * 20, line)
        c.save()
        payload = {"patient_id": "P", "filename": "outside.pdf", "content_base64": base64.b64encode(buf.getvalue()).decode()}
        ex = self.client.post("/api/v1/documents/outside-report/extract", json=payload, headers=_h("navigator")).json()
        self.assertEqual(ex["parsed"]["date"], "2026-05-14")
        self.assertNotIn("010-1234-5678", ex["text"])
        r = self.client.post("/api/v1/documents/outside-report", headers=_h("navigator"),
                             json={**payload, "confirmed": True, "conclusion": ex["parsed"]["conclusion"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("R003", [a["rule_id"] for a in r.json()["active"]])

    def test_ai_results_from_vendor_bundle(self):
        obs = ai_observation_resource("P", "Nodule", 0.91, True, "Vendor CXR", "3.1", "MFDS approved", None,
                                      "2026-01-10T08:00:00")
        r = self.client.post("/api/v1/imaging/ai-results", headers=_h("admin"),
                             json={"patient_id": "P", "bundle": {"resourceType": "Bundle", "entry": [{"resource": obs}]}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("R047", [a["rule_id"] for a in r.json()["active"]])


class TestIndependentReviewImaging(unittest.TestCase):
    """Cases from an independent review of the imaging code that the first version got wrong."""

    def study(self, uid="1.2.3.4", body="CHEST", modality="DX", date="20260110", time="080000", sid=None):
        r = imaging_study_resource({"study_uid": uid, "modalities": [modality], "body_part": body,
                                    "study_date": date, "study_time": time}, "P", "pacs")
        if sid:
            r["id"] = sid
        return r

    def ai(self, label="Nodule", ref=None, uid="1.2.3.4", product="Vendor CXR", body=None):
        return ai_observation_resource("P", label, 0.9, True, product, "3", "MFDS approved", ref,
                                       "2026-01-10T08:05:00+09:00", body_part=body, finding_key=ai_finding_key(label),
                                       study_uid=uid)

    def test_report_linked_to_the_hospitals_own_study_id_is_compared(self):
        hosp = self.study(sid="hosp-555")
        report = rad("r1", "2026-01-10T10:00:00+09:00", "Chest radiograph", "No acute abnormality.",
                     "https://fhir.hospital.local/r4/ImagingStudy/hosp-555")
        self.assertEqual(loops([P, hosp, self.ai(), report], datetime(2026, 1, 20))[0], {"R047": "open"})

    def test_unrelated_wording_does_not_count_as_addressed(self):
        for label, text in (("Nodule", "No acute osseous lesion."),
                            ("Nodule", "Bibasilar opacity, likely atelectasis."),
                            ("Effusion", "Small pericardial effusion."),
                            ("Atelectasis", "No vertebral body collapse."),
                            ("Intracranial hemorrhage", "Small scalp hematoma.")):
            body = "HEAD" if "hemorrhage" in label else "CHEST"
            st = self.study(body=body, modality="CT" if body == "HEAD" else "DX")
            report = rad("r1", "2026-01-10T10:00:00+09:00", "CT head" if body == "HEAD" else "Chest radiograph", text,
                         "ImagingStudy/" + st["id"])
            statuses, _ = loops([P, st, self.ai(label, body=body), report], datetime(2026, 1, 20))
            self.assertEqual(statuses.get("R047"), "open", (label, text))

    def test_fracture_is_compared_with_its_own_studys_report(self):
        wrist = self.study(uid="9.1", body="WRIST", modality="CR")
        chest_report = rad("rc", "2026-01-10T09:00:00+09:00", "CT chest", "No rib fracture.")
        wrist_report = rad("rw", "2026-01-10T11:00:00+09:00", "Wrist radiograph", "Normal alignment.",
                           "ImagingStudy/" + wrist["id"])
        obs = self.ai("Fracture", uid="9.1", body="WRIST")
        self.assertEqual(loops([P, wrist, obs, chest_report, wrist_report], datetime(2026, 1, 20))[0], {"R047": "open"})

    def test_a_report_written_before_the_study_is_not_its_report(self):
        st = self.study(uid=None)
        st.pop("identifier", None)
        old = rad("r0", "2026-01-10T07:30:00+09:00", "Chest radiograph", "Stable 8 mm nodule.")
        new = rad("r1", "2026-01-10T10:00:00+09:00", "Chest radiograph", "No acute abnormality.")
        obs = ai_observation_resource("P", "Nodule", 0.9, True, "Vendor", "3", "MFDS approved", None,
                                      "2026-01-10T08:00:00+09:00", body_part="CHEST")
        statuses, _ = loops([P, st, obs, old, new], datetime(2026, 1, 20))
        self.assertEqual(statuses.get("R047"), "open")

    def test_same_finding_from_two_sources_is_reviewed_once(self):
        st = self.study()
        report = rad("r1", "2026-01-10T10:00:00+09:00", "Chest radiograph", "No acute abnormality.", "ImagingStudy/" + st["id"])
        a = self.ai("Nodule", product="Vendor CXR")
        b = self.ai("Mass / Nodule", product="ClinLoop runner")
        self.assertEqual(loops([P, st, a, b, report], datetime(2026, 1, 20))[0], {"R047": "open"})
        # the same product re-run gives the same record id
        self.assertEqual(self.ai("Nodule")["id"], self.ai("Nodule / Mass")["id"])

    def test_unstated_regulatory_status_is_gated(self):
        st = self.study()
        report = rad("r1", "2026-01-10T10:00:00+09:00", "Chest radiograph", "No acute abnormality.", "ImagingStudy/" + st["id"])
        obs = ai_observation_resource("P", "Nodule", 0.9, True, "Unknown AI", "1", "not stated", None,
                                      "2026-01-10T08:05:00+09:00", study_uid="1.2.3.4")
        self.assertEqual(loops([P, st, obs, report], datetime(2026, 1, 20))[0], {})

    def test_outside_report_dates_and_sections(self):
        self.assertEqual(parse_report("Name DOB Exam Date\nHong 1960-04-12 2026-05-14\nIMPRESSION:\n9 mm nodule.")["date"],
                         "2026-05-14")
        self.assertIsNone(parse_report("DOB:\n1960-04-12\nCT chest\nIMPRESSION: 9 mm nodule.")["date"])
        self.assertEqual(parse_report("CT chest\nCOMPARISON: 2024-01-03\nDate 2026-05-14\nIMPRESSION:\nStable.")["date"],
                         "2026-05-14")
        self.assertEqual(parse_report("CT chest 05/14/2026\nIMPRESSION: x")["date"], "2026-05-14")
        self.assertIsNone(parse_report("CT chest 05/06/2026\nIMPRESSION: x")["date"])         # ambiguous: not guessed
        p = parse_report("IMPRESSION:\n1.2 cm adrenal nodule.\nComparison with outside CT is recommended.\n"
                         "Recommend adrenal CT in 12 months.")
        self.assertIn("Recommend adrenal CT in 12 months", p["conclusion"])

    def test_identifier_removal_keeps_clinical_text(self):
        from src.clinloop_engine.document_reader import clean_title, scrub_identifiers
        text = "추적 관찰로 6개월 후 CT 권고. image 45 46 47 48 49. 2026-05-14 비교."
        self.assertEqual(scrub_identifiers(text), text)
        out = scrub_identifiers("환자명: 홍길동 010-1234-5678 600412-1234567. 홍길동 님 결절.", ["홍길동"])
        self.assertNotIn("홍길동", out)
        self.assertNotIn("1234567", out)
        self.assertEqual(clean_title("CT Chest - Hong Gil-dong"), "CT Chest")

    def test_store_keeps_patients_apart(self):
        store = LoopStore()
        r = {"resourceType": "Observation", "id": "vendor-1", "subject": {"reference": "Patient/P"}}
        store.add_external_resource(r, "imaging-ai", "it", "admin")
        store.add_external_resource({**r, "subject": {"reference": "Patient/Q"}}, "imaging-ai", "it", "admin")
        self.assertEqual(len(store.external_resources("P")), 1)
        self.assertEqual(store.external_resources("Q")[0]["subject"]["reference"], "Patient/Q")
        from src.clinloop_engine.loop_store import WorkflowError
        with self.assertRaises(WorkflowError):
            store.add_external_resource({**r, "subject": {"reference": "Patient/ZZZ/P"}}, "imaging-ai", "it", "admin")

    @unittest.skipUnless(HAVE_DICOM, "pydicom not installed")
    def test_dicom_robustness(self):
        from src.clinloop_engine.imaging_ai import ImagingError, analyze_dicom
        bad_date = analyze_dicom(make_dicom(phantom(), date="20260230"), "P", ["MRN-0042"], models=[])
        self.assertTrue(bad_date["filed"])
        rgb = np.random.RandomState(1).randint(0, 255, (3, 32, 32, 3)).astype(np.uint8)
        from pydicom.uid import ExplicitVRLittleEndian  # noqa: F401
        raw = make_dicom(phantom(32), modality="US", body="ABDOMEN", extra={"NumberOfFrames": 3})
        import pydicom
        ds = pydicom.dcmread(io.BytesIO(raw))
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
        ds.BitsAllocated, ds.BitsStored, ds.HighBit = 8, 8, 7
        ds.PixelData = rgb.tobytes()
        buf = io.BytesIO()
        ds.save_as(buf, enforce_file_format=True)
        out = analyze_dicom(buf.getvalue(), "P", ["MRN-0042"], models=[])
        self.assertTrue(out["filed"])
        self.assertIsNotNone(out["preview"])
        strings = analyze_dicom(make_dicom(phantom()), "P", ["MRN-0042"],
                                models=[StubModel({"Nodule": "0.9", "Effusion": "n/a"})])
        self.assertEqual(len(strings["resources"]), 2)
        with self.assertRaises(ImagingError):
            analyze_dicom(b"%PDF-1.4 not a dicom file at all" * 10, "P", ["P"], models=[])
        no_id = analyze_dicom(make_dicom(phantom(), pid=""), "P", ["MRN-0042"], models=[])
        self.assertFalse(no_id["filed"])
        self.assertNotIn("patient_id_sha256", json.dumps(no_id["summary"]))


@unittest.skipUnless(HAVE_API and HAVE_DICOM, "API dependencies or pydicom not installed")
class TestImagingAPISafety(unittest.TestCase):

    def setUp(self):
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        bundle = {"resourceType": "Bundle", "entry": [{"resource": P}]}
        self.client.post("/api/v1/fhir/ingest", json=bundle, headers=_h("admin"))

    def test_patient_id_is_validated_and_must_exist(self):
        b64 = base64.b64encode(make_dicom(phantom())).decode()
        r = self.client.post("/api/v1/imaging/analyze", json={"patient_id": "ZZZ/P", "content_base64": b64},
                             headers=_h("navigator"))
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/v1/imaging/analyze", json={"patient_id": "NOPE-123", "content_base64": b64},
                             headers=_h("navigator"))
        self.assertEqual(r.status_code, 404)

    def test_ai_results_for_another_patient_are_refused(self):
        obs = ai_observation_resource("Q", "Nodule", 0.9, True, "Vendor", "3", "MFDS approved", None, "2026-01-10T08:00:00")
        r = self.client.post("/api/v1/imaging/ai-results", headers=_h("admin"),
                             json={"patient_id": "P", "bundle": {"resourceType": "Bundle", "entry": [{"resource": obs}]}})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.get("/api/v1/patients/Q/documents", headers=_h("viewer")).json()["documents"], [])


if __name__ == "__main__":
    unittest.main()
