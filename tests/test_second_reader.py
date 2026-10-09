"""
test_second_reader.py — The model-based second reader (R058): only verified, untracked items reach a person.

A fake model stands in for the hospital's on-premise LLM. Synthetic reports only.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import second_reader as sr  # noqa: E402
from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.loop_store import LoopStore  # noqa: E402

NOW = datetime(2026, 3, 2, 9, 0)
PATIENT = {"resourceType": "Patient", "id": "P", "gender": "female", "birthDate": "1970-01-01",
           "name": [{"family": "Kim", "given": ["Minji"], "text": "Kim Minji"}]}


def report(text, rid="r1", when="2026-03-01T09:00:00Z", category="RAD", title="Pelvis US"):
    return {"resourceType": "DiagnosticReport", "id": rid, "status": "final", "category": [{"coding": [{"code": category}]}],
            "code": {"text": title}, "subject": {"reference": "Patient/P"}, "effectiveDateTime": when, "conclusion": text}


class FakeModel:
    def __init__(self, items, error=None):
        self.items, self.error, self.prompts = items, error, []

    def __call__(self, prompt, system):
        self.prompts.append(prompt)
        if self.error:
            return {"error": self.error, "text": ""}
        return {"text": "```json\n" + json.dumps({"items": self.items}) + "\n```", "model": "fake-7b"}


UNUSUAL = ("IMPRESSION: 4.8 cm complex right adnexal cyst with thick septations. Please obtain a dedicated pelvic "
           "MRI at the earliest convenience.")


def loops(resources, when=NOW):
    events, _ = bundle_to_events(resources)
    return {d.rule_id: d for d in ClinLoopDetector(evaluation_time=when).process_patient("t", "P", events.get("P", []))}


class TestReadReport(unittest.TestCase):

    def test_only_exact_quotes_in_the_fixed_categories_survive(self):
        model = FakeModel([
            {"category": "imaging_followup", "quote": "Please obtain a dedicated pelvic MRI", "reason": "MRI advised"},
            {"category": "imaging_followup", "quote": "obtain a dedicated pelvic MRI", "reason": "duplicate"},
            {"category": "biopsy_or_workup", "quote": "biopsy of the left ovary is recommended", "reason": "invented"},
            {"category": "diagnosis", "quote": "complex right adnexal cyst", "reason": "not a category"},
        ])
        out = sr.read_report(UNUSUAL, model)
        self.assertTrue(out["available"])
        self.assertEqual([i["category"] for i in out["items"]], ["imaging_followup"])
        self.assertEqual(out["dropped"], 2)

    def test_identifiers_are_removed_before_the_model_sees_the_report(self):
        model = FakeModel([])
        sr.read_report("Patient Kim Minji, 등록번호 12345678. " + UNUSUAL, model, names=["Kim Minji", "Kim"])
        self.assertNotIn("Minji", model.prompts[0])
        self.assertNotIn("12345678", model.prompts[0])

    def test_unreadable_answer_is_not_a_clean_read(self):
        out = sr.read_report(UNUSUAL, lambda p, s: {"text": "I think the patient is fine.", "model": "fake"})
        self.assertFalse(out["available"])


class TestSecondReadPatient(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()

    def test_untracked_item_opens_a_review_that_follow_up_closes(self):
        rep = report(UNUSUAL)
        self.assertNotIn("R031", loops([PATIENT, rep]))           # the rules do not read "please obtain"
        model = FakeModel([{"category": "imaging_followup", "quote": "Please obtain a dedicated pelvic MRI",
                            "reason": "MRI recommended"}])
        flags = sr.second_read_patient(self.store, "P", [PATIENT, rep], model=model, now=NOW)
        self.assertEqual(len(flags), 1)
        got = loops([PATIENT, rep] + flags)
        d = got["R058"]
        self.assertEqual(d.loop_status, "needs_human_review")
        self.assertTrue(any("Please obtain a dedicated pelvic MRI" in line for line in d.evidence_chain))
        self.assertAlmostEqual((datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).days, 7)
        mri = {"resourceType": "ImagingStudy", "id": "s1", "status": "available", "subject": {"reference": "Patient/P"},
               "started": "2026-03-05T10:00:00Z", "modality": [{"code": "MR"}],
               "series": [{"uid": "1", "modality": {"code": "MR"}, "bodySite": {"display": "PELVIS"}}]}
        self.assertEqual(loops([PATIENT, rep, mri] + flags, NOW + timedelta(days=20))["R058"].loop_status, "closed")
        order = {"resourceType": "ServiceRequest", "id": "o1", "status": "active", "intent": "order",
                 "subject": {"reference": "Patient/P"}, "code": {"text": "MRI pelvis with contrast"},
                 "category": [{"text": "Imaging"}], "authoredOn": "2026-03-03T10:00:00Z"}
        self.assertEqual(loops([PATIENT, rep, order] + flags, NOW + timedelta(days=20))["R058"].loop_status, "closed")
        # A biopsy is not the imaging the flag asks for
        bx = {"resourceType": "Procedure", "id": "b1", "status": "completed", "subject": {"reference": "Patient/P"},
              "code": {"text": "Skin biopsy"}, "performedDateTime": "2026-03-03T10:00:00Z"}
        self.assertNotEqual(loops([PATIENT, rep, bx] + flags, NOW + timedelta(days=20))["R058"].loop_status, "closed")

    def test_items_the_rules_already_track_raise_nothing(self):
        rep = report("IMPRESSION: 9 mm solid RUL nodule. Recommend follow-up chest CT in 3 months.", title="CT chest")
        model = FakeModel([{"category": "imaging_followup", "quote": "Recommend follow-up chest CT in 3 months"}])
        self.assertEqual(sr.second_read_patient(self.store, "P", [PATIENT, rep], model=model, now=NOW), [])
        self.assertEqual(self.store.second_read("P|r1")["items"], 1)

    def test_a_report_is_read_once_unless_its_text_changes(self):
        model = FakeModel([])
        sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL)], model=model, now=NOW)
        sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL)], model=model, now=NOW)
        self.assertEqual(len(model.prompts), 1)
        sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL + " Addendum: MRI booked.")], model=model, now=NOW)
        self.assertEqual(len(model.prompts), 2)

    def test_old_reports_and_the_budget_are_respected(self):
        model = FakeModel([])
        old = report(UNUSUAL, rid="old", when="2025-01-01T09:00:00Z")
        sr.second_read_patient(self.store, "P", [PATIENT, old], model=model, now=NOW)
        self.assertEqual(model.prompts, [])
        budget = {"left": 1}
        sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL, "a"), report(UNUSUAL, "b")],
                               model=model, budget=budget, now=NOW)
        self.assertEqual(len(model.prompts), 1)

    def test_model_failure_is_recorded_and_files_nothing(self):
        flags = sr.second_read_patient(self.store, "P", [PATIENT, report(UNUSUAL)], model=FakeModel([], error="timeout"), now=NOW)
        self.assertEqual(flags, [])
        self.assertEqual(self.store.second_read("P|r1")["status"], "failed")

    def test_critical_and_pathology_review_deadlines(self):
        rep = report("Findings: small left frontal extra-axial blood collection, new compared with yesterday.", title="CT head")
        model = FakeModel([{"category": "critical_finding", "quote": "small left frontal extra-axial blood collection"}])
        flags = sr.second_read_patient(self.store, "P", [PATIENT, rep], model=model, now=NOW)
        d = loops([PATIENT, rep] + flags)["R058"]
        self.assertAlmostEqual((datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).total_seconds() / 86400, 1)

    def test_model_server_must_be_on_premise(self):
        with mock.patch("src.clinloop_engine.imaging_ai._on_premise", return_value=False):
            self.assertIsNone(sr.local_model())

    def test_sync_runs_it_only_when_enabled_and_survives_its_failure(self):
        from src.clinloop_engine import fhir_sync

        class Client:
            def changed_patients(self, since):
                return {"P"}, "2026-03-01T10:00:00Z"

            def patient_history(self, pid):
                return [PATIENT, report(UNUSUAL)]
        calls = []
        with mock.patch.object(sr, "second_read_patient", side_effect=lambda *a, **k: calls.append(1) or []):
            fhir_sync.sync_once(self.store, Client(), now=NOW)
            self.assertEqual(calls, [])                          # off by default
            with mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": "1"}):
                fhir_sync.sync_once(self.store, Client(), now=NOW)
        self.assertEqual(calls, [1])
        with mock.patch.dict(os.environ, {"CLINLOOP_SECOND_READER": "1"}), \
                mock.patch.object(sr, "second_read_patient", side_effect=RuntimeError("model down")):
            self.assertTrue(fhir_sync.sync_once(self.store, Client(), now=NOW)["ok"])


class TestStoredEvaluation(unittest.TestCase):
    """The stored stand-in model answers (docs/SECOND_READER.md) still reach the clinician through today's code."""

    def test_rule_misses_still_reach_a_person(self):
        import subprocess
        base = os.path.join(ROOT, "tests", "report_eval")
        caught = 0
        for name in ("real", "confirm2"):
            out = subprocess.run([sys.executable, os.path.join(base, "run_second_reader_eval.py"),
                                  os.path.join(base, "second_reader", f"cases_{name}.json"),
                                  os.path.join(base, "second_reader", f"rules_first_{name}.json")]
                                 + [os.path.join(base, "second_reader", f"output_{i}.json") for i in range(3)],
                                 capture_output=True, text=True, check=True).stdout
            caught += int(out.split("second reader: ")[1].split("/")[0])
        self.assertGreaterEqual(caught, 16)


if __name__ == "__main__":
    unittest.main()
