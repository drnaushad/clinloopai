"""Synthetic import boundaries preserve identity and isolate invalid demographics."""
import copy
import unittest
from src.clinloop_engine.fhir_ingest import bundle_to_events, resolved_resources


def observation(subject="Patient/synthetic-P"):
    return {"resourceType": "Observation", "id": "synthetic-lab", "status": "final",
            "subject": {"reference": subject}, "effectiveDateTime": "2026-10-01T00:00:00Z",
            "code": {"text": "potassium"}, "valueQuantity": {"value": 7.1, "unit": "mmol/L"},
            "interpretation": [{"coding": [{"code": "HH"}]}]}


class TestFHIRInputBoundaries(unittest.TestCase):
    def test_invalid_birth_date_does_not_blind_other_patients(self):
        resources = [{"resourceType": "Patient", "id": "synthetic-P", "birthDate": "2026-02-30"},
                     observation(), observation("Patient/synthetic-Q")]
        events, warnings = bundle_to_events(resources)
        self.assertEqual(set(events), {"synthetic-P", "synthetic-Q"})
        self.assertTrue(any("birth date is invalid" in warning for warning in warnings))
        self.assertFalse(any("2026-02-30" in warning for warning in warnings))

    def test_full_birth_date_suffix_is_not_silently_accepted(self):
        events, warnings = bundle_to_events([
            {"resourceType": "Patient", "id": "synthetic-P", "birthDate": "2000-01-01garbage"}, observation()])
        self.assertIn("synthetic-P", events)
        self.assertTrue(any("birth date is invalid" in warning for warning in warnings))

    def test_generator_matches_list_input_on_all_mapping_passes(self):
        resources = [{"resourceType": "Patient", "id": "synthetic-P", "birthDate": "1970-01-01"}, observation()]
        self.assertEqual(bundle_to_events(iter(copy.deepcopy(resources))), bundle_to_events(copy.deepcopy(resources)))

    def test_ambiguous_alias_cannot_rebind_patient_by_entry_order(self):
        entries = [{"fullUrl": "urn:uuid:synthetic-shared", "resource": {"resourceType": "Patient", "id": pid}}
                   for pid in ("synthetic-P", "synthetic-Q")]
        entries.append({"resource": observation("urn:uuid:synthetic-shared")})
        for ordered in (entries, list(reversed(entries))):
            bundle = {"resourceType": "Bundle", "entry": ordered}
            for read in (bundle_to_events, resolved_resources):
                with self.subTest(read=read.__name__), self.assertRaisesRegex(ValueError, "Conflicting FHIR"):
                    read(bundle)

    def test_resolved_resources_preserve_all_linkages_without_mutating_input(self):
        lab = observation("urn:uuid:synthetic-patient")
        lab["basedOn"] = [{"reference": "https://synthetic.invalid/fhir/order"}]
        request = {"resourceType": "ServiceRequest", "id": "synthetic-order", "status": "active", "intent": "order",
                   "subject": {"reference": "urn:uuid:synthetic-patient"}}
        bundle = {"resourceType": "Bundle", "entry": [
            {"fullUrl": "urn:uuid:synthetic-patient", "resource": {"resourceType": "Patient", "id": "synthetic-P"}},
            {"fullUrl": "https://synthetic.invalid/fhir/order", "resource": request}, {"resource": lab}]}
        original = copy.deepcopy(bundle)
        resources = resolved_resources(bundle)
        self.assertEqual(resources[2]["subject"]["reference"], "Patient/synthetic-P")
        self.assertEqual(resources[2]["basedOn"][0]["reference"], "ServiceRequest/synthetic-order")
        self.assertEqual(bundle, original)
        self.assertEqual(set(bundle_to_events(resources)[0]), {"synthetic-P"})

    def test_unresolved_alias_stays_unresolved(self):
        resources = resolved_resources([observation("urn:uuid:unknown")])
        events, warnings = bundle_to_events(resources)
        self.assertFalse(events)
        self.assertTrue(any("no patient reference" in warning for warning in warnings))

    def test_malformed_resource_containers_are_controlled_refusals(self):
        for bundle in ({"resourceType": "Bundle", "entry": {}}, {"resourceType": "Bundle", "entry": ["private"]},
                       {"resourceType": "Bundle", "entry": [{"resource": []}]}, [None],
                       [{"resourceType": "Observation", "id": "invalid private id"}]):
            with self.subTest(bundle=bundle), self.assertRaises(ValueError) as err:
                resolved_resources(bundle)
            self.assertNotIn("private", str(err.exception))


class TestBrowserBundleIdentity(unittest.TestCase):
    def test_browser_analysis_resolves_aliases_before_dropping_bundle_envelope(self):
        from src.clinloop_engine.browser_analyse import analyse_bundle
        bundle = {"resourceType": "Bundle", "entry": [
            {"fullUrl": "urn:uuid:synthetic-patient", "resource": {"resourceType": "Patient", "id": "synthetic-P"}},
            {"resource": observation("urn:uuid:synthetic-patient")}]}
        result = analyse_bundle(bundle, "2026-10-02T00:00:00Z")
        self.assertEqual(result["patients"], 1)
        self.assertGreater(result["events"], 0)
        self.assertFalse(any("no patient reference" in warning for warning in result["warnings"]))
