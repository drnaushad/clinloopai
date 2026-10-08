"""
test_ct_organs.py — CT series reading, organ measurement and the R047 review of abnormal measurements

All volumes are synthetic numpy phantoms; the segmenter is a stub that returns
known organ masks, so the measurements can be checked against the truth.
"""

import base64
import gzip
import io
import os
import random
import sys
import unittest
import zipfile
from datetime import datetime
from unittest import mock

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from test_imaging import HAVE_API, P, TOKENS, _h, loops, rad  # noqa: E402

try:
    import nibabel as nib
    import pydicom  # noqa: F401
    from scipy import ndimage  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

if HAVE_DEPS:
    from src.clinloop_engine import ct_organs
    from src.clinloop_engine.imaging_ai import ImagingError

LABELS = {1: "spleen", 5: "liver", 52: "aorta", 10: "lung_upper_lobe_left", 51: "heart"}
SHAPE = (80, 80, 60)          # 4 mm × 4 mm × 5 mm voxels → 32 × 32 × 30 cm
SPACING = (4.0, 4.0, 5.0)


def phantom_labels(aorta_mm=22.0, spleen_slices=(20, 40), chest_from=45, arch=False):
    """Label volume (i = R→L… as built by the reader, k = inferior→superior)."""
    lab = np.zeros(SHAPE, dtype=np.int16)
    ii, jj = np.mgrid[:SHAPE[0], :SHAPE[1]]
    r_vox = aorta_mm / 2 / SPACING[0]
    for k in range(5, SHAPE[2] - 2):
        lab[:, :, k][(ii - 40) ** 2 + (jj - 48) ** 2 <= r_vox ** 2] = 52
    for k in range(*spleen_slices):
        lab[:, :, k][(ii - 60) ** 2 + (jj - 50) ** 2 <= 16] = 1
    for k in range(10, 40):
        lab[:, :, k][(ii - 20) ** 2 + (jj - 40) ** 2 <= 64] = 5
    for k in range(chest_from, SHAPE[2]):
        lab[:, :, k][(ii - 15) ** 2 + (jj - 20) ** 2 <= 25] = 10
    if arch:   # an oblique, elongated aortic cut (6 cm × 2.4 cm) in a chest slice
        k = SHAPE[2] - 3
        lab[:, :, k][((ii - 40) / 7.5) ** 2 + ((jj - 30) / 3.0) ** 2 <= 1] = 52
    return lab


def stub_segmenter(labels):
    def seg(img):
        assert img.shape == SHAPE
        return nib.Nifti1Image(labels, img.affine), dict(LABELS)
    return seg


def series_zip(pid="MRN-0042", modality="CT", n=SHAPE[2], shuffle=True, patients=None, study_uid="1.2.3.4"):
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w")
    order = list(range(n))
    if shuffle:
        random.Random(42).shuffle(order)
    series = generate_uid()
    for k in order:
        fm = FileMetaDataset()
        fm.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        fm.MediaStorageSOPInstanceUID = generate_uid()
        fm.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = fm
        ds.SOPClassUID, ds.SOPInstanceUID = fm.MediaStorageSOPClassUID, fm.MediaStorageSOPInstanceUID
        ds.PatientID = (patients or {}).get(k, pid)
        ds.Modality, ds.BodyPartExamined = modality, "ABDOMEN"
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, series
        ds.StudyDate, ds.StudyTime = "20260920", "101500"
        ds.StudyDescription, ds.SeriesDescription = "CT ABDOMEN", "AXIAL"
        ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        ds.ImagePositionPatient = [-160.0, -160.0, -150.0 + 5.0 * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [4.0, 4.0], 5.0
        ds.Rows, ds.Columns = SHAPE[1], SHAPE[0]
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleIntercept, ds.RescaleSlope = -1024, 1
        pix = np.full((SHAPE[1], SHAPE[0]), 1024 + k, dtype=np.int16)
        ds.PixelData = pix.tobytes()
        b = io.BytesIO()
        ds.save_as(b, enforce_file_format=True)
        zf.writestr(f"dir/IM{k:04d}", b.getvalue())
    zf.close()
    return buf.getvalue()


@unittest.skipUnless(HAVE_DEPS, "nibabel, scipy or pydicom not installed")
class TestCTSeries(unittest.TestCase):

    def test_series_is_sorted_by_position_and_converted_to_hounsfield(self):
        img, header, notes = ct_organs.read_dicom_series(series_zip())
        self.assertEqual(img.shape, SHAPE)
        data = np.asarray(img.dataobj)
        self.assertEqual(float(data[0, 0, 0]), 0.0)          # slice 0: 1024 − 1024 HU
        self.assertEqual(float(data[0, 0, 59]), 59.0)        # sorted by position, not by zip order
        self.assertEqual(tuple(round(float(z), 3) for z in img.header.get_zooms()), SPACING)
        self.assertEqual(nib.aff2axcodes(img.affine), ("R", "A", "S"))

    def test_bad_series_are_refused(self):
        with self.assertRaisesRegex(ImagingError, "more than one patient"):
            ct_organs.read_dicom_series(series_zip(patients={7: "SOMEONE-ELSE"}))
        with self.assertRaisesRegex(ImagingError, "needs a CT"):
            ct_organs.read_dicom_series(series_zip(modality="MR"))
        with self.assertRaisesRegex(ImagingError, "slices"):
            ct_organs.read_dicom_series(series_zip(n=5))
        with self.assertRaisesRegex(ImagingError, "zip"):
            ct_organs.read_dicom_series(b"not a zip at all")


@unittest.skipUnless(HAVE_DEPS, "nibabel, scipy or pydicom not installed")
class TestMeasurements(unittest.TestCase):

    def run_ct(self, labels, pid="MRN-0042"):
        return ct_organs.analyze_ct_series(series_zip(), "ct.zip", "P", [pid], segmenter=stub_segmenter(labels))

    def test_aneurysm_and_splenomegaly_are_measured(self):
        r = self.run_ct(phantom_labels(aorta_mm=44.0, spleen_slices=(10, 40)))
        self.assertAlmostEqual(r["measurements"]["aorta"]["abdominal_max_cm"], 4.4, delta=0.25)
        self.assertEqual(r["measurements"]["spleen"]["craniocaudal_cm"], 15.0)
        keys = sorted(f["finding_key"] for f in r["findings"])
        self.assertEqual(keys, ["aortic_aneurysm", "splenomegaly"])
        self.assertTrue(r["filed"])
        obs = [x for x in r["resources"] if x["resourceType"] == "Observation"]
        self.assertEqual(len(obs), 2)
        for o in obs:
            self.assertNotIn("valueQuantity", o)                     # a measurement, never a probability
            self.assertEqual(o["component"][0]["valueQuantity"]["unit"], "cm")
            self.assertIn("Research use", o["extension"][0]["valueString"])

    def test_normal_ct_has_no_findings(self):
        r = self.run_ct(phantom_labels(aorta_mm=20.0, spleen_slices=(20, 40)))
        self.assertEqual(r["findings"], [])
        self.assertAlmostEqual(r["measurements"]["aorta"]["abdominal_max_cm"], 2.0, delta=0.25)
        self.assertEqual([x["resourceType"] for x in r["resources"]], ["ImagingStudy"])

    def test_thoracic_threshold_is_higher(self):
        """A 3.6 cm aorta is an abdominal aneurysm but not a dilated thoracic aorta."""
        lab = phantom_labels(aorta_mm=20.0)
        ii, jj = np.mgrid[:SHAPE[0], :SHAPE[1]]
        for k in range(45, 58):                       # chest slices only
            lab[:, :, k][(ii - 40) ** 2 + (jj - 48) ** 2 <= (36 / 8) ** 2] = 52
        r = self.run_ct(lab)
        self.assertGreater(r["measurements"]["aorta"]["thoracic_max_cm"], 3.3)
        self.assertEqual(r["findings"], [])

    def test_abdominal_and_thoracic_dilatation_is_one_finding(self):
        r = self.run_ct(phantom_labels(aorta_mm=48.0))       # dilated along its whole length
        self.assertEqual(len(r["findings"]), 1)
        self.assertIn("Abdominal aortic aneurysm and Thoracic aortic dilatation", r["findings"][0]["label"])
        self.assertEqual(len([x for x in r["resources"] if x["resourceType"] == "Observation"]), 1)

    def test_oblique_arch_cut_is_not_a_diameter(self):
        r = self.run_ct(phantom_labels(aorta_mm=24.0, arch=True))
        self.assertLess(r["measurements"]["aorta"]["thoracic_max_cm"], 3.0)
        self.assertEqual(r["findings"], [])

    def test_organ_cut_off_by_the_scan_is_not_sized(self):
        r = self.run_ct(phantom_labels(spleen_slices=(0, 30)))        # spleen touches the bottom slice
        self.assertFalse(r["measurements"]["spleen"]["complete"])
        self.assertNotIn("splenomegaly", [f["finding_key"] for f in r["findings"]])
        self.assertIn("spleen_cut_off", [q["code"] for q in r["qa"]])

    def test_wrong_patient_is_not_filed(self):
        r = self.run_ct(phantom_labels(aorta_mm=44.0), pid="SOMEONE-ELSE")
        self.assertFalse(r["filed"])
        self.assertEqual(r["resources"], [])
        self.assertTrue(r["findings"])              # still shown to the person, for the right patient's chart

    def test_nifti_is_shown_never_filed(self):
        img, _, _ = ct_organs.read_dicom_series(series_zip())
        raw = gzip.compress(img.to_bytes())
        r = ct_organs.analyze_ct_series(raw, "ct.nii.gz", "P", ["MRN-0042"],
                                        segmenter=stub_segmenter(phantom_labels(aorta_mm=44.0)))
        self.assertFalse(r["filed"])
        self.assertEqual(r["qa"][0]["code"], "no_patient_id")

    def test_coverage_is_reported_but_closes_nothing(self):
        r = self.run_ct(phantom_labels())
        self.assertIn("spleen", r["covered_regions"])
        study = r["resources"][0]
        self.assertEqual(study["resourceType"], "ImagingStudy")
        self.assertNotIn("spleen", str(study))       # the study record is not widened by the segmentation


@unittest.skipUnless(HAVE_DEPS, "nibabel, scipy or pydicom not installed")
class TestMeasurementReview(unittest.TestCase):
    """An abnormal measurement is compared with the radiologist's report of the same CT (R047)."""

    def resources(self, aorta_mm=44.0):
        r = ct_organs.analyze_ct_series(series_zip(), "ct.zip", "P", ["MRN-0042"],
                                        segmenter=stub_segmenter(phantom_labels(aorta_mm=aorta_mm,
                                                                                spleen_slices=(20, 40))))
        return r["resources"], "ImagingStudy/" + r["resources"][0]["id"]

    def test_unmentioned_aneurysm_opens_review_when_research_ai_allowed(self):
        res, ref = self.resources()
        report = rad("r1", "2026-09-20T03:00:00Z", "CT abdomen", "No acute intra-abdominal abnormality.", ref)
        self.assertEqual(loops([P, *res, report], datetime(2026, 9, 25))[0], {})          # research use: off
        with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_RESEARCH_AI": "1"}):
            statuses, dets = loops([P, *res, report], datetime(2026, 9, 25))
        self.assertEqual(statuses, {"R047": "open"})
        self.assertIn("Aortic aneurysm", " ".join(dets[0].evidence_chain))

    def test_report_that_sizes_the_aorta_is_enough(self):
        res, ref = self.resources()
        for text in ("Infrarenal AAA measuring 4.3 cm.", "Normal caliber abdominal aorta.",
                     "The abdominal aorta measures 2.9 cm.", "복부 대동맥류 4.3 cm."):
            report = rad("r1", "2026-09-20T03:00:00Z", "CT abdomen", text, ref)
            with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_RESEARCH_AI": "1"}):
                statuses, _ = loops([P, *res, report], datetime(2026, 9, 25))
            self.assertNotIn("R047", statuses, text)


@unittest.skipUnless(HAVE_DEPS and HAVE_API, "API dependencies not installed")
class TestCTOrgansAPI(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine import clinical_api
        from src.clinloop_engine.api import app
        from src.clinloop_engine.loop_store import LoopStore
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        bundle = {"resourceType": "Bundle", "entry": [{"resource": P}]}
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-09-21T00:00:00", json=bundle, headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)
        self.payload = {"patient_id": "P", "filename": "ct.zip",
                        "content_base64": base64.b64encode(series_zip()).decode()}

    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_MODELS": ""}):
            r = self.client.post("/api/v1/imaging/ct-organs", json=self.payload, headers=_h("navigator"))
        self.assertEqual(r.status_code, 503)

    def test_measures_and_files(self):
        seg = stub_segmenter(phantom_labels(aorta_mm=44.0))
        with mock.patch.dict(os.environ, {"CLINLOOP_IMAGING_MODELS": "totalseg"}), \
                mock.patch.object(ct_organs, "available", lambda: None), \
                mock.patch.object(ct_organs, "totalsegmentator_segmenter", seg):
            self.assertEqual(self.client.post("/api/v1/imaging/ct-organs", json=self.payload,
                                              headers=_h("viewer")).status_code, 403)
            r = self.client.post("/api/v1/imaging/ct-organs", json=self.payload, headers=_h("navigator"))
            models = self.client.get("/api/v1/imaging/models").json()["models"]
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["filed"])
        self.assertEqual([f["finding_key"] for f in body["findings"]], ["aortic_aneurysm"])
        self.assertIn("TotalSegmentator", [m["name"] for m in models])
        docs = self.client.get("/api/v1/patients/P/documents", headers=_h("viewer")).json()["documents"]
        self.assertEqual(sorted(d["kind"] for d in docs), ["dicom-study", "imaging-ai"])


if __name__ == "__main__":
    unittest.main()
