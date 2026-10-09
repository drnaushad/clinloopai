"""
test_image_scan.py — Automatic image scanning: new PACS studies → approved imaging AI → review loops.

A fake PACS and FHIR server hold synthetic studies (numpy images in DICOM). Synthetic; no real patient data.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from src.clinloop_engine.imaging_ai import ImagingError  # noqa: E402
from src.clinloop_engine.imaging_scanner import (  # noqa: E402
    MAX_ATTEMPTS, ScanConfig, eligible_models, resolve_patient, scan_once,
)
from src.clinloop_engine.loop_store import LoopStore  # noqa: E402
from src.clinloop_engine.pacs_client import DICOMwebClient, PACSError  # noqa: E402
from test_imaging import HAVE_DICOM, P, StubModel, make_dicom, phantom, rad  # noqa: E402

NOW = datetime(2026, 1, 10, 12, 0, 0)          # local and UTC alike in these tests
MRN = "urn:oid:1.2.410.99999.1"                 # the hospital's MRN system (CLINLOOP_PACS_ID_SYSTEM)
PS = {**P, "identifier": [{"system": MRN, "type": {"coding": [{"code": "MR"}]}, "value": "MRN-0042"}]}


class FakePACS:
    """Studies in memory, shaped like DICOMwebClient's results."""

    def __init__(self):
        self.by_uid, self.files, self.retrieved, self.queries = {}, {}, [], []
        self.headers, self.headers_read = {}, []

    def add(self, study_uid, pacs_pid, modality, body, files, series_uid="1.2.3.1", desc="Chest PA",
            date="20260110", time="080000", series_desc="PA", count=False):
        st = self.by_uid.setdefault(study_uid, {
            "study_uid": study_uid, "pacs_patient_id": pacs_pid, "study_date": date, "study_time": time,
            "description": desc, "modalities": [modality], "accession": None, "n_series": 1,
            "n_instances": None, "series": []})
        if count:                                  # the PACS reports how many images the study has
            st["n_instances"] = (st["n_instances"] or 0) + len(files)
        st["series"].append({"uid": series_uid, "modality": modality, "body_part": body, "description": series_desc})
        for i, f in enumerate(files):
            self.files[(study_uid, series_uid, f"{series_uid}.{i + 1}")] = f

    def new_studies(self, date_from, date_to, modalities, **_):
        self.queries.append((date_from, date_to, tuple(modalities)))
        return [{**s, "series": []} for s in self.by_uid.values() if date_from <= s["study_date"] <= date_to]

    def series(self, study_uid):
        return self.by_uid[study_uid]["series"]

    def studies(self, pacs_patient_id):          # the per-patient study list (DICOMwebClient.studies)
        return [s for s in self.by_uid.values() if s["pacs_patient_id"] == pacs_patient_id]

    def instances(self, study_uid, series_uid):
        return [{"uid": k[2], "number": int(k[2].rsplit(".", 1)[1])}
                for k in sorted(self.files) if k[0] == study_uid and k[1] == series_uid]

    def instance_header(self, study_uid, series_uid, instance_uid):
        self.headers_read.append(instance_uid)
        return self.headers[(study_uid, series_uid)]

    def retrieve_instance(self, study_uid, series_uid, instance_uid, **_):
        self.retrieved.append(instance_uid)
        return self.files[(study_uid, series_uid, instance_uid)]


class FakeFHIR:
    def __init__(self, patients, history=()):
        self.patients, self.history = patients, list(history)

    def search(self, rtype, params):
        assert rtype == "Patient"
        value = params["identifier"].split("|")[-1]
        return [p for p in self.patients if any(i.get("value") == value for i in p.get("identifier", []))]

    def patient_history(self, pid):
        return [p for p in self.patients if p["id"] == pid] + [r for r in self.history
                                                               if r["subject"]["reference"] == f"Patient/{pid}"]


class SeriesStub(StubModel):
    """An approved whole-series product (e.g. head CT haemorrhage triage)."""
    name, input, modalities, body_regions = "Stub CT series", "series", ["CT"], ["head"]

    def __init__(self, scores):
        super().__init__(scores)
        self.calls = []

    def applies(self, summary):
        return None if summary["modality"] == "CT" and "head" in summary["regions"] else "head CT only"

    def predict_series(self, contents):
        self.calls.append(len(contents))
        return [{"label": k, "score": v} for k, v in self.scores.items()]


class FailingStub(StubModel):
    def predict(self, ds, img, content):
        raise RuntimeError("vendor endpoint down")


def research_stub():
    m = StubModel({"Nodule": 0.9})
    m.name, m.regulatory = "Research CXR", "Research use only"
    return m


def scan(store, pacs, fhir, models, **cfg):
    return scan_once(store, pacs, fhir, models=models, cfg=ScanConfig(**cfg), now=NOW, local_now=NOW)


@unittest.skipUnless(HAVE_DICOM, "pydicom not installed")
class TestImageScan(unittest.TestCase):

    def setUp(self):
        env = mock.patch.dict(os.environ, {"CLINLOOP_PACS_ID_SYSTEM": MRN})
        env.start()
        self.addCleanup(env.stop)
        self.store = LoopStore()
        self.pacs = FakePACS()
        self.report = rad("r1", "2026-01-10T10:00:00Z", "Chest radiograph PA", "No acute cardiopulmonary abnormality.")
        self.fhir = FakeFHIR([PS], [self.report])

    def cxr(self, uid="9.1", pid="MRN-0042", **kw):
        files = [make_dicom(phantom(), pid=pid, date="20260110",
                            extra={"StudyInstanceUID": uid, "SeriesInstanceUID": "1.2.3.1"})]
        self.pacs.add(uid, pid, "DX", "CHEST", files, **kw)

    def test_new_chest_xray_is_scanned_and_unaddressed_finding_opens_review(self):
        self.cxr()
        result = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9, "Effusion": 0.1})])
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["scanned"], result["findings"]), (1, 1))
        self.assertEqual(self.store.scan_study("9.1")["status"], "scanned")
        kinds = sorted(d["kind"] for d in self.store.external_resource_list("P"))
        self.assertEqual(kinds, ["dicom-study", "imaging-ai"])
        # The radiologist's report does not mention the nodule → R047 radiologist review
        self.assertEqual([r["rule_id"] for r in self.store.worklist()], ["R047"])

    def test_scanned_once_only(self):
        self.cxr()
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.pacs.retrieved.clear()
        again = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual((again["scanned"], again["skipped_done"], self.pacs.retrieved), (0, 1, []))

    def test_wrong_patient_image_is_refused(self):
        files = [make_dicom(phantom(), pid="MRN-9999", extra={"StudyInstanceUID": "9.2", "SeriesInstanceUID": "1.2.3.1"})]
        self.pacs.add("9.2", "MRN-0042", "DX", "CHEST", files)   # PACS index says MRN-0042, the image says otherwise
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        row = self.store.scan_study("9.2")
        self.assertEqual(row["status"], "refused")
        self.assertIn("patient_mismatch", row["detail"])
        self.assertEqual(self.store.external_resource_list("P"), [])

    def test_unknown_or_ambiguous_patient_is_never_guessed(self):
        self.cxr(uid="9.3", pid="MRN-UNKNOWN")
        twin = {**PS, "id": "P2"}
        scan(self.store, self.pacs, FakeFHIR([PS]), [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.scan_study("9.3")["status"], "unmatched")
        self.cxr(uid="9.4")
        scan(self.store, self.pacs, FakeFHIR([PS, twin]), [StubModel({"Nodule": 0.9})])
        row = self.store.scan_study("9.4")
        self.assertEqual(row["status"], "unmatched")
        self.assertIn("2 patients", row["detail"])
        self.assertEqual(self.pacs.retrieved, [])          # no image retrieved for an unmatched study

    def test_no_applicable_model_retrieves_nothing(self):
        files = [make_dicom(phantom(), modality="MR", body="KNEE", extra={"StudyInstanceUID": "9.5"})]
        self.pacs.add("9.5", "MRN-0042", "MR", "KNEE", files, desc="MRI knee")
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.scan_study("9.5")["status"], "no_model")
        self.assertEqual(self.pacs.retrieved, [])

    def test_research_models_do_not_run_automatically(self):
        self.cxr()
        result = scan(self.store, self.pacs, self.fhir, [research_stub()])
        self.assertFalse(result["ok"])
        self.assertIn("research use", result["error"])
        self.assertEqual(self.pacs.retrieved, [])
        shadow = scan(self.store, self.pacs, self.fhir, [research_stub()], allow_research=True)
        self.assertEqual(shadow["scanned"], 1)
        # Shadow mode: the finding is filed but opens no loop (CLINLOOP_IMAGING_RESEARCH_AI is off)
        self.assertEqual(self.store.worklist(), [])

    def test_unstated_approval_counts_as_research(self):
        m = StubModel({"Nodule": 0.9})
        m.regulatory = "not stated"
        self.assertEqual(eligible_models([m], ScanConfig())[0], [])

    def test_recent_study_waits_for_its_images(self):
        self.cxr(time="115800")                            # 2 minutes before NOW
        result = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual((result["waiting"], result["scanned"]), (1, 0))
        self.assertIsNone(self.store.scan_study("9.1"))

    def test_per_run_limit_defers_the_rest(self):
        for i in range(3):
            self.cxr(uid=f"9.{10 + i}", time=f"0{7 + i}0000")
        result = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})], max_studies=2)
        self.assertEqual((result["scanned"], result["deferred"]), (2, 1))
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})], max_studies=2)["scanned"], 1)

    def test_model_failure_is_a_failure_not_a_clean_scan(self):
        self.cxr()
        scan(self.store, self.pacs, self.fhir, [FailingStub({"Nodule": 0.9})])
        row = self.store.scan_study("9.1")
        self.assertEqual(row["status"], "failed")
        self.assertIn("failed", row["detail"])
        # Retried on the next run, and scanned once the product is back
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.scan_study("9.1")["status"], "scanned")

    def test_pacs_down_is_recorded_and_alarmed(self):
        class Down(FakePACS):
            def new_studies(self, *a, **k):
                raise PACSError("QIDO-RS /studies → HTTP 503")
        for _ in range(3):
            self.assertFalse(scan(self.store, Down(), self.fhir, [StubModel({})])["ok"])
        self.assertEqual(self.store.scan_status(now=NOW)["status"], "FAILING")

    def test_scan_runs_never_mask_the_fhir_feed_monitor(self):
        self.cxr()
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.feed_status()["status"], "NEVER")

    def test_whole_series_model_gets_every_image_and_checks_each(self):
        uid, ser = "9.20", "1.2.3.20"
        files = [make_dicom(phantom(), modality="CT", body="HEAD", desc="CT head without contrast",
                            extra={"StudyInstanceUID": uid, "SeriesInstanceUID": ser, "InstanceNumber": i + 1})
                 for i in range(3)]
        self.pacs.add(uid, "MRN-0042", "CT", "HEAD", files, series_uid=ser, desc="CT head without contrast",
                      series_desc="Axial 5mm")
        model = SeriesStub({"Intracranial hemorrhage": 0.95})
        result = scan(self.store, self.pacs, self.fhir, [model])
        self.assertEqual((result["scanned"], model.calls), (1, [3]))
        # One image of the series belongs to someone else: nothing is sent or filed
        uid2, ser2 = "9.21", "1.2.3.21"
        files = [make_dicom(phantom(), modality="CT", body="HEAD", pid=pid,
                            extra={"StudyInstanceUID": uid2, "SeriesInstanceUID": ser2})
                 for pid in ("MRN-0042", "MRN-9999", "MRN-0042")]
        self.pacs.add(uid2, "MRN-0042", "CT", "HEAD", files, series_uid=ser2, desc="CT head")
        model.calls.clear()
        scan(self.store, self.pacs, self.fhir, [model])
        self.assertEqual(self.store.scan_study(uid2)["status"], "refused")
        self.assertEqual(model.calls, [])

    def test_localizers_and_reports_are_not_analysed(self):
        files = [make_dicom(phantom(), extra={"StudyInstanceUID": "9.30"})]
        self.pacs.add("9.30", "MRN-0042", "DX", "CHEST", files, series_desc="Dose report")
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.scan_study("9.30")["status"], "no_model")

    def test_body_part_missing_from_the_series_query_is_read_from_one_header(self):
        # Some PACS (Orthanc) do not return BodyPartExamined in series queries: without the header the
        # study would be skipped as "no model applies" and never scanned
        self.cxr(uid="9.40", desc="")
        self.pacs.by_uid["9.40"]["series"][0]["body_part"] = None
        self.pacs.headers[("9.40", "1.2.3.1")] = {"body_part": "CHEST", "description": "PA",
                                                   "study_description": "Chest PA", "modality": "DX"}
        scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.scan_study("9.40")["status"], "scanned")
        self.assertEqual(len(self.pacs.headers_read), 1)

    def test_one_scan_at_a_time(self):
        from src.clinloop_engine import imaging_scanner
        self.cxr()
        with imaging_scanner._RUNNING:
            busy = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertTrue(busy.get("busy"))
        self.assertEqual(self.pacs.retrieved, [])
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])["scanned"], 1)

    def test_patient_match_needs_the_mrn_identifier(self):
        not_mrn = {**P, "id": "P3", "identifier": [{"system": "urn:insurance", "value": "MRN-0042"}]}
        patient, why = resolve_patient("MRN-0042", FakeFHIR([not_mrn]), self.store)
        self.assertIsNone(patient)
        self.assertIsNone(resolve_patient("MRN-*", FakeFHIR([PS]), self.store)[0])
        self.assertEqual(resolve_patient("MRN-0042", FakeFHIR([PS]), self.store)[0]["id"], "P")

    # ── Defects found by the independent review ──

    def test_scanning_refuses_to_run_without_the_identifier_system(self):
        # Another site's MRN 12345 on a shared FHIR server must never match this hospital's PatientID 12345
        self.cxr()
        with mock.patch.dict(os.environ, {"CLINLOOP_PACS_ID_SYSTEM": ""}):
            r = scan(self.store, self.pacs, FakeFHIR([P]), [StubModel({"Nodule": 0.9})])
        self.assertFalse(r["ok"])
        self.assertIn("CLINLOOP_PACS_ID_SYSTEM", r["error"])
        self.assertEqual(self.pacs.retrieved, [])

    def test_other_site_mrn_with_the_same_digits_is_not_this_patient(self):
        other = {**P, "id": "B", "identifier": [{"system": "urn:other-hospital", "type": {"coding": [{"code": "MR"}]},
                                                 "value": "MRN-0042"}]}
        self.cxr()
        scan(self.store, self.pacs, FakeFHIR([other]), [StubModel({"Nodule": 0.9})])
        self.assertEqual(self.store.scan_study("9.1")["status"], "unmatched")
        self.assertEqual(self.store.external_resource_list("B"), [])

    def test_half_arrived_study_waits_and_new_images_reopen_it(self):
        files = [make_dicom(phantom(), extra={"StudyInstanceUID": "9.50", "SeriesInstanceUID": "1.2.3.1"})]
        self.pacs.add("9.50", "MRN-0042", "DX", "CHEST", files, count=True)
        model = StubModel({"Nodule": 0.9})
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [model])["scanned"], 0)   # count first seen: wait
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [model])["scanned"], 1)   # unchanged: read
        # A late series arrives: the study is read again, not left "scanned" for good
        late = [make_dicom(phantom(), extra={"StudyInstanceUID": "9.50", "SeriesInstanceUID": "1.2.3.2"})]
        self.pacs.add("9.50", "MRN-0042", "DX", "CHEST", late, series_uid="1.2.3.2", count=True)
        r = scan(self.store, self.pacs, self.fhir, [model])
        self.assertEqual(r["reopened"], 1)
        self.assertEqual(self.store.scan_study("9.50")["status"], "pending")
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [model])["scanned"], 1)

    def test_outages_do_not_use_up_retries_and_stop_the_run(self):
        for i in range(4):
            self.cxr(uid=f"9.6{i}", time=f"0{6 + i}0000")
        for _ in range(MAX_ATTEMPTS + 2):
            r = scan(self.store, self.pacs, self.fhir, [FailingStub({"Nodule": 0.9})])
            self.assertFalse(r["ok"])
            self.assertIn("in a row", r["error"])
        # Vendor back: every study is still read
        r = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertEqual(r["scanned"], 4)

    def test_fhir_outage_stops_the_run_without_spending_retries(self):
        class Down(FakeFHIR):
            def search(self, *a):
                raise ConnectionError("FHIR down")
        self.cxr()
        r = scan(self.store, self.pacs, Down([PS]), [StubModel({"Nodule": 0.9})])
        self.assertFalse(r["ok"])
        self.assertIsNone(self.store.scan_study("9.1"))
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])["scanned"], 1)

    def test_a_study_that_keeps_failing_is_abandoned_and_raises_an_alarm(self):
        self.cxr()
        broken = StubModel({"Nodule": 0.9})
        with mock.patch("src.clinloop_engine.imaging_ai.read_dicom", side_effect=ImagingError("corrupt file")):
            for _ in range(MAX_ATTEMPTS):
                scan(self.store, self.pacs, self.fhir, [broken])
        self.assertEqual(self.store.scan_study("9.1")["status"], "abandoned")
        status = self.store.scan_status(now=NOW)
        self.assertEqual(status["status"], "ATTENTION")
        self.assertEqual(status["problems"][0]["status"], "abandoned")

    def test_one_product_failing_keeps_the_study_open_for_it(self):
        self.cxr()
        ok, down = StubModel({"Nodule": 0.9}), FailingStub({"Pneumothorax": 0.9})
        down.name = "Second CXR product"
        scan(self.store, self.pacs, self.fhir, [ok, down])
        row = self.store.scan_study("9.1")
        self.assertEqual(row["status"], "failed")
        self.assertIn("Second CXR product", row["detail"])
        self.assertEqual(len([d for d in self.store.external_resource_list("P") if d["kind"] == "imaging-ai"]), 1)
        scan(self.store, self.pacs, self.fhir, [ok, StubModel({"Pneumothorax": 0.9})])
        self.assertEqual(self.store.scan_study("9.1")["status"], "scanned")

    def test_hospital_time_zone_not_the_container_clock(self):
        from src.clinloop_engine.imaging_scanner import _hospital_now
        with mock.patch.dict(os.environ, {"CLINLOOP_LOCAL_TZ": "Asia/Seoul"}):
            seoul = _hospital_now()
        utc = datetime.utcnow()
        self.assertAlmostEqual((seoul - utc).total_seconds() / 3600, 9, delta=0.1)

    def test_lease_blocks_a_second_process(self):
        self.cxr()
        self.assertTrue(self.store.acquire_lease("image-scan", "other-host:123:x", 60, NOW))
        r = scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])
        self.assertTrue(r.get("busy"))
        self.assertEqual(self.pacs.retrieved, [])
        self.store.release_lease("image-scan", "other-host:123:x")
        self.assertEqual(scan(self.store, self.pacs, self.fhir, [StubModel({"Nodule": 0.9})])["scanned"], 1)


class FakeResponse:
    def __init__(self, status=200, json_data=None, content=b"", content_type="application/dicom+json"):
        self.status_code, self._json, self.content, self.headers = status, json_data, content, {"Content-Type": content_type}

    def json(self):
        return self._json

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def close(self):
        pass


class TestDICOMwebRetrieval(unittest.TestCase):

    def client(self, responses):
        session = mock.Mock()
        session.get.side_effect = responses
        return DICOMwebClient("http://pacs.local/dicom-web", session=session), session

    def test_new_studies_queries_by_date_and_modality_and_pages(self):
        def study(uid):
            return {"0020000D": {"Value": [uid]}, "00100020": {"Value": ["MRN-1"]}, "00080020": {"Value": ["20260110"]}}
        c, session = self.client([FakeResponse(json_data=[study("1"), study("2")]), FakeResponse(json_data=[study("3")]),
                                  FakeResponse(json_data=[])])
        found = c.new_studies("20260108", "20260110", ["CT"], page=2)
        self.assertEqual([s["study_uid"] for s in found], ["1", "2", "3"])
        params = session.get.call_args_list[0].kwargs["params"]
        self.assertEqual((params["StudyDate"], params["ModalitiesInStudy"]), ("20260108-20260110", "CT"))
        # Requested fields as repeated parameters: Orthanc ignores a comma-separated list
        self.assertIsInstance(params["includefield"], list)
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["offset"], 2)
        self.assertEqual(found[0]["pacs_patient_id"], "MRN-1")

    def test_paging_survives_small_pages_and_ignored_offsets_and_caps_per_modality(self):
        def page(uids):
            return FakeResponse(json_data=[{"0020000D": {"Value": [u]}, "00100020": {"Value": ["M"]}} for u in uids])
        # A PACS whose pages are smaller than requested: keep going until an empty page
        c, _ = self.client([page(["1", "2"]), page(["3"]), page([])])
        self.assertEqual(len(c.new_studies("20260101", "20260102", ["CT"], page=100)), 3)
        # A PACS that ignores offset: the same page again stops the loop
        c, s = self.client([page(["1", "2"])] * 50)
        self.assertEqual(len(c.new_studies("20260101", "20260102", ["CT"], page=2)), 2)
        self.assertLessEqual(s.get.call_count, 2)
        # Each modality has its own cap, and a cut-short list is reported
        c, _ = self.client([page(["1", "2"]), page(["5"]), page([])])
        found = c.new_studies("20260101", "20260102", ["CR", "CT"], page=2, max_per_modality=2)
        self.assertEqual(c.truncated, ["CR"])
        self.assertIn("5", {x["study_uid"] for x in found})        # CT still queried

    def test_retrieve_reads_the_dicom_part_of_a_multipart_response(self):
        body = (b"--XyZ\r\nContent-Type: application/dicom\r\n\r\n" + b"DICM-BYTES" + b"\r\n--XyZ--\r\n")
        c, _ = self.client([FakeResponse(content=body, content_type='multipart/related; type="application/dicom"; boundary=XyZ')])
        self.assertEqual(c.retrieve_instance("1", "2", "3"), b"DICM-BYTES")
        # Binary content containing CRLFs and dashes is returned byte for byte
        payload = bytes(range(256)) * 50 + b"\r\n--Xy" + bytes(range(256))
        body = b"--XyZ\r\nContent-Type: application/dicom\r\n\r\n" + payload + b"\r\n--XyZ--\r\n"
        c, _ = self.client([FakeResponse(content=body, content_type="multipart/related; boundary=XyZ")])
        self.assertEqual(c.retrieve_instance("1", "2", "3"), payload)

    def test_uids_from_the_pacs_are_validated_before_use_in_a_url(self):
        c, session = self.client([])
        for bad in ("../../studies", "1.2/../3", "1.2.3?x=1", "1" * 65):
            with self.assertRaises(PACSError):
                c.retrieve_instance("1.2", "3.4", bad)
        session.get.assert_not_called()

    def test_retrieve_enforces_the_size_limit(self):
        c, _ = self.client([FakeResponse(content=b"x" * 5000, content_type="application/dicom")])
        with self.assertRaises(PACSError):
            c.retrieve_instance("1", "2", "3", max_bytes=1000)


class TestSeriesUpload(unittest.TestCase):

    def test_series_product_receives_every_image_in_one_multipart_request(self):
        from src.clinloop_engine.imaging_ai import HTTPImagingModel
        m = HTTPImagingModel({"name": "CT AI", "url": "http://ai.local/ct", "input": "series",
                              "regulatory": "MFDS approved", "modalities": ["CT"]})
        with mock.patch("requests.post") as post:
            post.return_value = mock.Mock(status_code=200, json=lambda: {"findings": [{"label": "ICH", "score": 0.9}]})
            out = m.predict_series([b"A" * 10, b"B" * 10, b"C" * 10])
        body = post.call_args.kwargs["data"]
        self.assertEqual(body.count(b"Content-Type: application/dicom"), 3)
        self.assertIn("multipart/related", post.call_args.kwargs["headers"]["Content-Type"])
        self.assertEqual(out, [{"label": "ICH", "score": 0.9, "positive": None}])
        self.assertEqual(m.describe()["input"], "series")

    def test_a_vendor_reply_without_findings_is_an_error_not_a_clean_read(self):
        from src.clinloop_engine.imaging_ai import HTTPImagingModel, ImagingError
        m = HTTPImagingModel({"name": "CXR AI", "url": "http://ai.local/cxr", "regulatory": "MFDS approved"})
        for body in ({"job_id": "123"}, {"findings": [{"label": "Nodule", "probability": 0.9}]}, ["x"]):
            with mock.patch("requests.post") as post:
                post.return_value = mock.Mock(status_code=200, json=lambda b=body: b)
                with self.assertRaises(ImagingError, msg=str(body)):
                    m.predict(None, None, b"DICM")
        self.assertFalse(m.needs_pixels)        # the product reads the DICOM bytes, any compression


if __name__ == "__main__":
    unittest.main()
