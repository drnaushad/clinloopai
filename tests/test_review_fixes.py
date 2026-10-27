"""
test_review_fixes.py — Regression tests for defects found in the full code review

Each test pins one fixed defect: a wrong-patient match, a loop closed by a request rather than an
action, an endpoint reachable without a token, a key leaked into a log line, and so on.
"""

import logging
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import literature
from src.clinloop_engine.clinical_ontology import OBLIGATION_RULES, is_fulfilling_status
from src.clinloop_engine.ecg import qtc_ms
from src.clinloop_engine.fhir_ingest import bundle_to_events
from src.clinloop_engine.guideline_reports import classify_lab
from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.loop_store import LoopStore, WorkflowError
from src.clinloop_engine.pacs_client import dicom_patient_ids
from src.clinloop_engine.safety.agent_guard import detect_unsupported_clinical_claims

EVAL = "2026-06-01T00:00:00"


def _report_loops(text, extra=()):
    """Rule id → loop status for one chest CT report (plus any extra FHIR resources)."""
    res = [{"resourceType": "Patient", "id": "p1", "birthDate": "1960-01-01", "gender": "male"},
           {"resourceType": "DiagnosticReport", "id": "r1", "status": "final", "subject": {"reference": "Patient/p1"},
            "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": "CT chest"},
            "effectiveDateTime": "2026-01-10T09:00:00Z", "conclusion": text}] + list(extra)
    events, _ = bundle_to_events({"resourceType": "Bundle", "entry": [{"resource": r} for r in res]})
    out = {}
    for pid, evs in events.items():
        for d in ClinLoopDetector(evaluation_time=EVAL).process_patient("t", pid, evs):
            out[d.rule_id] = d.loop_status
    return out


class TestRadiologyCriticalFindings(unittest.TestCase):

    def test_lung_rads_version_is_not_read_as_the_category(self):
        # "Lung-RADS 1.1 Category 4X" is category 4X, not category 1
        self.assertIn("R020", _report_loops("Lung-RADS 1.1 Category 4X. Spiculated 18 mm nodule."))
        self.assertIn("R020", _report_loops("Lung-RADS 2022 category 4B: 16 mm solid nodule right upper lobe."))

    def test_finding_on_the_line_after_the_indication_is_still_critical(self):
        self.assertIn("R035", _report_loops("Indication: rule out PE\nPulmonary embolism in the right lower lobe arteries."))

    def test_request_to_communicate_does_not_close_the_critical_loop(self):
        for text in ("Acute pulmonary embolism. This must be discussed with the referring physician.",
                     "Acute pulmonary embolism. Please ensure findings are conveyed to the clinician."):
            self.assertEqual(_report_loops(text).get("R035"), "open", text)
        done = _report_loops("Acute pulmonary embolism. Findings discussed with Dr. Kim at 14:05.")
        self.assertNotEqual(done.get("R035", "closed"), "open")

    def test_negated_or_chronic_finding_opens_nothing(self):
        self.assertNotIn("R035", _report_loops("No pulmonary embolism. Stable chronic changes."))


class TestLabsAndEcg(unittest.TestCase):

    def test_hiv_screen_with_reflex_wording_is_the_screen(self):
        out = classify_lab({"75622-1"}, "HIV-1/2 Ag/Ab screen with reflex to differentiation", "Reactive",
                           None, None, None, [])
        self.assertEqual(out["condition"], "hiv_screen_reactive")
        rna = classify_lab({"20447-9"}, "HIV-1 RNA", "1200 copies/mL", None, 1200, "copies/mL", [])
        self.assertEqual(rna["followup_event"], "hiv_supplemental_test")

    def test_qt_qtc_pair_reads_the_qtc(self):
        self.assertEqual(qtc_ms({}, "QT/QTc 420/510 ms"), 510.0)


class TestStatusesAndRules(unittest.TestCase):

    def test_ordered_or_partial_work_does_not_close_a_loop(self):
        for status in ("requested", "ordered", "waitlist", "preliminary", "partial", "in progress",
                       "in_progress", "unknown"):
            self.assertFalse(is_fulfilling_status(status), status)
        self.assertTrue(is_fulfilling_status("completed"))
        self.assertTrue(is_fulfilling_status("final", "lab_result"))
        self.assertTrue(is_fulfilling_status("fulfilled", "followup_appointment"))
        self.assertFalse(is_fulfilling_status("final"))
        self.assertFalse(is_fulfilling_status("fulfilled"))

    def test_r005_accepts_colposcopy_and_r015_needs_a_culture(self):
        rules = {r.rule_id: r for r in OBLIGATION_RULES}
        self.assertIn("colposcopy_visit", [e.value for e in rules["R005"].required_followups])
        self.assertEqual([e.value for e in rules["R015"].required_followups], ["culture_result"])


class TestWrongPatientImaging(unittest.TestCase):

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in ("CLINLOOP_PACS_ID_SYSTEM", "CLINLOOP_PACS_MATCH_FHIR_ID")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_fhir_id_is_not_matched_when_the_patient_has_an_mrn(self):
        patient = {"id": "1234", "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "MRN-77"}]}
        self.assertEqual(dicom_patient_ids(patient), ["MRN-77"])
        self.assertEqual(dicom_patient_ids({"id": "1234"}), ["1234"])


class TestSecretsAndClaims(unittest.TestCase):

    def test_literature_errors_do_not_log_api_keys(self):
        self.assertNotIn("SECRETKEY", literature._redact("https://x/esearch?term=a&api_key=SECRETKEY&tool=b"))
        self.assertNotIn("me@example.org", literature._redact("https://x/?email=me@example.org"))

    def test_definitive_claims_are_caught_in_english_and_korean(self):
        for text in ("It is definitely benign.", "검사 결과 암입니다.", "약을 중단하세요.", "걱정하실 필요 없습니다."):
            self.assertTrue(detect_unsupported_clinical_claims(text), text)
        for text in ("Please book your follow-up visit.", "추적 검사를 예약해 주세요."):
            self.assertFalse(detect_unsupported_clinical_claims(text), text)


class _Provider:
    name = "test"

    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)
        return "ref-1"


class TestLoopStoreReviewFixes(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        events = [{"event_id": "fit-1", "patient_id": "P1", "event_type": "lab_result",
                   "timestamp": "2026-05-01T09:00:00", "details": {"test": "FIT", "result": "positive"},
                   "status": "completed"}]
        dets = ClinLoopDetector(evaluation_time=datetime(2026, 6, 1)).process_patient("t", "P1", events)
        self.store.upsert_detections(dets)
        self.key = self.store.worklist()[0]["loop_key"]

    def test_defer_rejects_unreadable_or_far_future_dates(self):
        for until in ("zzzz", "2099-01-01T00:00:00"):
            with self.assertRaises(WorkflowError):
                self.store.defer(self.key, "dr.lee", reason_code="completed_elsewhere",
                                 note="Done elsewhere", until=until)

    def test_closing_a_loop_withdraws_its_unsent_messages(self):
        msg = self.store.add_outreach_draft(self.key, "nurse.park", "navigator", "Please call the clinic.",
                                            "en", "sms", [])
        self.store.close(self.key, "dr.lee", evidence="Colonoscopy done at partner hospital 2026-05-20")
        self.assertEqual(self.store._outreach(msg["id"])["status"], "withdrawn")
        provider = _Provider()
        with self.assertRaises(WorkflowError):
            self.store.decide_outreach(msg["id"], "dr.lee", "clinician", True, provider=provider)
        self.assertEqual(provider.sent, [])
        self.assertTrue(self.store.verify_audit_chain())


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestApiNeedsToken(unittest.TestCase):

    def test_patient_and_key_endpoints_refuse_anonymous_calls(self):
        client = TestClient(app)
        for method, path in (("get", "/api/v1/cases"), ("get", "/api/v1/config/api-keys"),
                             ("post", "/api/v1/config/api-keys"), ("post", "/api/v1/config/test-api-key")):
            r = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
            self.assertEqual(r.status_code, 401, f"{method.upper()} {path}: {r.status_code}")

    def test_public_status_endpoints_stay_open(self):
        client = TestClient(app)
        self.assertEqual(client.get("/api/v1/health").status_code, 200)
        self.assertEqual(client.get("/api/v1/rules").status_code, 200)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
