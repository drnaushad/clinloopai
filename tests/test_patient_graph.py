"""
test_patient_graph.py — Patient knowledge graph from the temporal hypergraph (synthetic patients)
"""

import json
import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from test_imaging import HAVE_API, P, _h, rad  # noqa: E402

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.imaging_fhir import ai_observation_resource, imaging_study_resource  # noqa: E402
from src.clinloop_engine.patient_graph import build_patient_graph, node_label  # noqa: E402

LAB = {"resourceType": "Observation", "id": "k1", "status": "final", "subject": {"reference": "Patient/P"},
       "category": [{"coding": [{"code": "laboratory"}]}],
       "code": {"coding": [{"system": "http://loinc.org", "code": "2823-3"}], "text": "Potassium"},
       "effectiveDateTime": "2026-01-02T08:00:00Z", "valueQuantity": {"value": 6.9, "unit": "mmol/L"},
       "interpretation": [{"coding": [{"code": "HH"}]}]}
DX = {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/P"},
      "clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"text": "Type 2 diabetes mellitus"},
      "recordedDate": "2025-06-01"}


def graph(resources, when=datetime(2026, 10, 8)):
    events, _ = bundle_to_events(resources)
    return build_patient_graph("P", events.get("P", []), when)


class TestPatientGraph(unittest.TestCase):

    def test_events_are_placed_in_clinical_lanes(self):
        g = graph([P, LAB, DX, rad("r1", "2026-01-05T01:00:00Z", "CT abdomen and pelvis",
                                   "Indeterminate 2.2 cm right adrenal nodule. Recommend adrenal protocol CT in 3 months.")])
        lanes = {n["lane"] for n in g["nodes"]}
        self.assertTrue({"labs", "diagnoses", "reports", "imaging"} <= lanes, lanes)
        lab = next(n for n in g["nodes"] if n["lane"] == "labs")
        self.assertIn("6.9", lab["label"])
        self.assertEqual(lab["source"], "Observation/k1")

    def test_open_obligation_points_to_the_missing_follow_up(self):
        g = graph([P, rad("r1", "2026-01-05T01:00:00Z", "CT abdomen and pelvis",
                          "Indeterminate 2.2 cm right adrenal nodule. Recommend adrenal protocol CT in 3 months.")])
        h = next(h for h in g["hyperedges"] if h["rule_id"] == "R030")
        self.assertEqual(h["status"], "open")
        self.assertTrue(h["overdue"])
        self.assertEqual(h["followups"], [])
        self.assertEqual(h["expected"][0]["lane"], "imaging")
        self.assertIn("adrenal", h["expected"][0]["label"])
        self.assertTrue(any("Rule:" in line for line in h["evidence"]))

    def test_closed_obligation_links_trigger_to_follow_up(self):
        study = imaging_study_resource({"study_uid": "5.5", "modalities": ["CT"], "body_part": "ABDOMEN",
                                        "description": "CT ADRENAL PROTOCOL", "study_date": "20260325",
                                        "study_time": "090000"}, "P", "pacs")
        g = graph([P, study, rad("r1", "2026-01-05T01:00:00Z", "CT abdomen and pelvis",
                                 "Indeterminate 2.2 cm right adrenal nodule. Recommend adrenal protocol CT in 3 months.")])
        h = next(h for h in g["hyperedges"] if h["rule_id"] == "R030")
        self.assertEqual(h["status"], "closed")
        self.assertEqual(h["expected"], [])
        self.assertIn(f"ImagingStudy/{study['id']}:imaging_ct", h["followups"])

    def test_study_report_and_ai_finding_are_linked(self):
        study = imaging_study_resource({"study_uid": "9.9", "modalities": ["DX"], "body_part": "CHEST",
                                        "study_date": "20260110", "study_time": "080000"}, "P", "pacs")
        ref = "ImagingStudy/" + study["id"]
        ai = ai_observation_resource("P", "Nodule", 0.9, True, "Vendor CXR", "3.1", "MFDS approved", ref,
                                     "2026-01-10T08:05:00", study_uid="9.9")
        g = graph([P, study, ai, rad("r1", "2026-01-10T10:00:00Z", "Chest radiograph PA", "No acute abnormality.", ref)])
        kinds = {e["kind"] for e in g["edges"]}
        self.assertIn("same_study", kinds)
        self.assertIn("derived_from", kinds)              # the R047 review event comes from the AI finding
        linked = {x for e in g["edges"] if e["kind"] == "same_study" for x in (e["source"], e["target"])}
        self.assertTrue(any(x.startswith("Observation/") for x in linked))
        self.assertTrue(any(x.startswith("DiagnosticReport/") for x in linked))
        self.assertEqual([h["rule_id"] for h in g["hyperedges"]], ["R047"])

    def test_labels(self):
        self.assertEqual(node_label("imaging_ct", {"body_regions": ["abdomen", "adrenal", "kidney", "pelvis"]}),
                         "CT · abdomen, pelvis")
        self.assertEqual(node_label("diagnosis", {"diagnosis": "Hepatitis C"}), "Hepatitis C")

    def test_whole_test_bundle_builds(self):
        with open(os.path.join(ROOT, "data", "radiology_test_bundle.json"), encoding="utf-8") as f:
            events, _ = bundle_to_events(json.load(f))
        for pid, evs in events.items():
            g = build_patient_graph(pid, evs, datetime(2026, 10, 8))
            ids = {n["id"] for n in g["nodes"]}
            for h in g["hyperedges"]:
                self.assertIn(h["trigger"], ids)
                self.assertTrue(set(h["followups"]) <= ids)
            json.dumps(g)


@unittest.skipUnless(HAVE_API, "API dependencies not installed")
class TestPatientGraphAPI(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine import clinical_api
        from src.clinloop_engine.api import app
        from src.clinloop_engine.loop_store import LoopStore
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        bundle = {"resourceType": "Bundle", "entry": [{"resource": r} for r in [
            P, LAB, rad("r1", "2026-01-05T01:00:00Z", "CT abdomen and pelvis",
                        "Indeterminate 2.2 cm right adrenal nodule. Recommend adrenal protocol CT in 3 months.")]]}
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-10-08T00:00:00", json=bundle, headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)

    def test_graph_with_worklist_state(self):
        self.assertEqual(self.client.get("/api/v1/patients/P/graph").status_code, 401)
        r = self.client.get("/api/v1/patients/P/graph?evaluation_time=2026-10-08T00:00:00", headers=_h("viewer"))
        self.assertEqual(r.status_code, 200, r.text)
        g = r.json()
        h = next(h for h in g["hyperedges"] if h["rule_id"] == "R030")
        self.assertIsNotNone(h["worklist"])
        self.assertEqual(h["worklist"]["state"], "new")

    def test_unknown_or_invalid_patient(self):
        self.assertEqual(self.client.get("/api/v1/patients/NOPE/graph", headers=_h("viewer")).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/patients/a%20b/graph", headers=_h("viewer")).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/patients/P/graph?evaluation_time=yesterday",
                                         headers=_h("viewer")).status_code, 422)


if __name__ == "__main__":
    unittest.main()
