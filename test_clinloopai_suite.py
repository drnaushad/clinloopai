"""Real ClinLoop regression entry point; synthetic fixtures only.

Run from this repository with its core/API test dependencies installed:
    python test_clinloopai_suite.py -v
    python -m pytest test_clinloopai_suite.py -v

The imported TestCase classes reuse maintained API, completion-evidence and
report-version tests. No dummy authentication, detector or scrubber is used.
API dependencies are required: this entry point fails rather than silently
passing with its API checks skipped. It changes test-process configuration only;
do not import it into a running application server.

This is a focused regression suite, not clinical validation or a privacy
certification. Full FHIR Bundle de-identification is not implemented by the
flat-record helper. For the additional JWT, concurrency, feed and browser-expiry
probes, run the repository's complete tests/ suite.
"""

import json
import unittest

# Import API fixtures first: they configure synthetic bearer tokens before auth
# reads its process-local configuration. These classes are discovered by both
# unittest and pytest; keep their implementations in their existing test files.
from tests.test_clinical_api import HAVE_API, TestClinicalAPI
from tests.test_completion_evidence import TestAffirmativeCompletion
from tests.test_phase1_production import TestReportVersions
from src.clinloop_engine.phi_deidentifier import PHIDeidentifier


class TestRealPrivacyBoundary(unittest.TestCase):
    """Exercise the public flat-record helper across structured and text fields."""

    def test_embedded_identifiers_removed_while_clinical_text_survives(self) -> None:
        safe, audit = PHIDeidentifier().deidentify_patient({
            "patient_id": "SYNTHETIC-99912",
            "clinical_context": (
                "주민번호: 850101-1234567; 전화: 010-1234-5678; MRN: 98765432. "
                "L5-S1 HNP 소견 보임. Follow-up CT; nodule 8.5 mm."
            ),
        })
        serialized = json.dumps(safe, ensure_ascii=False)
        for identifier in ("SYNTHETIC-99912", "850101-1234567", "010-1234-5678", "98765432"):
            self.assertNotIn(identifier, serialized)
        context = safe["clinical"]["clinical_context"]
        self.assertIn("L5-S1 HNP 소견 보임.", context)
        self.assertIn("nodule 8.5 mm", context)
        self.assertFalse(audit["safe_to_send_cloud"])
        self.assertTrue(audit["human_review_required"])

    def test_linkage_is_consistent_within_one_context_and_input_is_unchanged(self) -> None:
        engine = PHIDeidentifier()
        records = [
            {"patient_id": "SYNTHETIC-99912", "finding": finding}
            for finding in ("Synthetic first event", "Synthetic second event")
        ]
        before = json.dumps(records, sort_keys=True)
        outputs = [engine.deidentify_patient(record)[0] for record in records]
        self.assertEqual(outputs[0]["patient_ref"], outputs[1]["patient_ref"])
        self.assertEqual(outputs[0]["case_ref"], outputs[1]["case_ref"])
        self.assertNotIn("SYNTHETIC-99912", json.dumps(outputs))
        self.assertEqual(json.dumps(records, sort_keys=True), before)
        separate, _ = PHIDeidentifier().deidentify_patient(records[0])
        self.assertNotEqual(outputs[0]["patient_ref"], separate["patient_ref"])

    def test_fhir_is_explicitly_unsupported_and_input_is_not_partly_rewritten(self) -> None:
        bundle = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "SYNTHETIC-1"}},
            {"resource": {"resourceType": "Observation",
                          "subject": {"reference": "Patient/SYNTHETIC-1"}}},
        ]}
        before = json.dumps(bundle, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "FHIR"):
            PHIDeidentifier().deidentify_patient(bundle)
        self.assertEqual(json.dumps(bundle, sort_keys=True), before)


class TestRequiredDependencies(unittest.TestCase):
    def test_api_checks_are_available(self) -> None:
        self.assertTrue(HAVE_API, "Install the repository core/API test dependencies; API checks must run.")


if __name__ == "__main__":
    unittest.main()
