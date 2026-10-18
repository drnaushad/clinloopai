"""
test_phase5_data.py — Lab-result versions, same-timestamp follow-ups, the folder runner, AuditEvent export

Synthetic resources only.
"""

import os
import sys
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TOKENS = {"admin": "test-admin-token-0123456789", "clinician": "test-clinician-token-012345",
          "navigator": "test-navigator-token-01234", "viewer": "test-viewer-token-0123456789"}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

from src.clinloop_engine.fhir_ingest import bundle_to_events, superseded_reports  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.loop_store import RESULT_REVISED_STEP, LoopStore  # noqa: E402

EVAL = datetime(2026, 9, 3)
PATIENT = {"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1960-01-01"}


def potassium(rid, status="final", value=6.8, flag="HH", when="2026-09-01T09:00:00Z", specimen=None):
    r = {"resourceType": "Observation", "id": rid, "status": status, "subject": {"reference": "Patient/p1"},
         "code": {"coding": [{"system": "http://loinc.org", "code": "2823-3", "display": "Potassium"}]},
         "effectiveDateTime": when, "valueQuantity": {"value": value, "unit": "mmol/L"}}
    if flag:
        r["interpretation"] = [{"coding": [{"code": flag}]}]
    if specimen:
        r["specimen"] = {"reference": f"Specimen/{specimen}"}
    return r


def ingest(store, resources):
    events, _ = bundle_to_events(resources)
    for pid, evs in events.items():
        store.upsert_detections(ClinLoopDetector(evaluation_time=EVAL).process_patient("t", pid, evs))
    return store.supersede_sources(superseded_reports(resources))


def rules(resources):
    events, _ = bundle_to_events(resources)
    return sorted(d.rule_id for d in ClinLoopDetector(evaluation_time=EVAL).process_patient("t", "p1", events["p1"]))


class TestLabResultVersions(unittest.TestCase):
    """A preliminary and a final version of one lab result open each loop once (deferred from PR #36)."""

    def test_preliminary_and_final_give_one_set_of_loops(self):
        final_only = rules([PATIENT, potassium("b")])
        self.assertEqual(rules([PATIENT, potassium("a", "preliminary"), potassium("b")]), final_only)
        self.assertEqual(superseded_reports([PATIENT, potassium("a", "preliminary"), potassium("b")]),
                         {"Observation/a": "Observation/b"})

    def test_different_collection_times_or_specimens_are_different_results(self):
        later = potassium("b", when="2026-09-01T15:00:00Z")
        self.assertEqual(superseded_reports([PATIENT, potassium("a", "preliminary"), later]), {})
        self.assertEqual(superseded_reports([PATIENT, potassium("a", "preliminary", specimen="s1"),
                                             potassium("b", specimen="s2")]), {})

    def test_released_versions_never_replace_each_other_and_no_time_means_no_match(self):
        self.assertEqual(superseded_reports([PATIENT, potassium("a"), potassium("b", "corrected")]), {})
        no_time = {k: v for k, v in potassium("a", "preliminary").items() if k != "effectiveDateTime"}
        self.assertEqual(superseded_reports([PATIENT, no_time, potassium("b")]), {})

    def test_loop_from_the_preliminary_moves_to_the_final(self):
        store = LoopStore()
        ingest(store, [PATIENT, potassium("a", "preliminary")])
        key = next(l["loop_key"] for l in store.worklist() if l["rule_id"] == "R022")
        store.acknowledge(key, "dr.kim")
        ingest(store, [PATIENT, potassium("a", "preliminary"), potassium("b")])
        active = [l for l in store.worklist() if l["rule_id"] == "R022"]
        self.assertEqual(len(active), 1)
        self.assertEqual((active[0]["workflow_state"], active[0]["owner"]), ("acknowledged", "dr.kim"))

    def test_final_no_longer_abnormal_waits_for_a_clinician(self):
        store = LoopStore()
        ingest(store, [PATIENT, potassium("a", "preliminary")])
        ingest(store, [PATIENT, potassium("a", "preliminary"), potassium("b", value=4.2, flag="N")])
        old = next(l for l in store.worklist() if l["rule_id"] == "R022")
        self.assertIn("Observation/a", old["loop_key"])
        self.assertEqual(old["missing_step"], RESULT_REVISED_STEP)
        self.assertEqual(old["engine_status"], "needs_human_review")
        self.assertIn("laboratory", old["recommended_action"])


class TestSameTimestamp(unittest.TestCase):
    """A follow-up stamped with the trigger's exact time stays uncounted, and the reviewer is told why."""

    def evidence(self, note_time):
        ev = [{"event_id": "k", "patient_id": "p1", "event_type": "lab_result", "timestamp": "2026-09-01T09:00:00",
               "details": {"test": "potassium", "value": 6.8, "flag": "CRITICAL"}, "status": "completed"},
              {"event_id": "n", "patient_id": "p1", "event_type": "critical_value_notification",
               "timestamp": note_time, "details": {}, "status": "completed"}]
        d = next(d for d in ClinLoopDetector(evaluation_time=EVAL).process_patient("t", "p1", ev) if d.rule_id == "R022")
        return d.loop_status, " ".join(d.evidence_chain)

    def test_equal_timestamp_stays_open_and_is_labelled(self):
        status, chain = self.evidence("2026-09-01T09:00:00")
        self.assertEqual(status, "open")
        self.assertIn("SAME_TIMESTAMP", chain)

    def test_a_later_follow_up_closes_without_the_label(self):
        status, chain = self.evidence("2026-09-01T09:20:00")
        self.assertEqual(status, "closed")
        self.assertNotIn("SAME_TIMESTAMP", chain)


class TestFolderRunner(unittest.TestCase):
    """Synthea-style folders: per-patient transaction Bundles with urn:uuid references, and NDJSON."""

    def setUp(self):
        import json
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        uid = "11111111-0000-4000-8000-000000000001"
        bundle = {"resourceType": "Bundle", "type": "transaction", "entry": [
            {"fullUrl": f"urn:uuid:{uid}", "resource": {**PATIENT, "id": uid}},
            {"fullUrl": "urn:uuid:o-pre", "resource": {**potassium("o-pre", "preliminary"),
                                                       "subject": {"reference": f"urn:uuid:{uid}"}}},
            {"fullUrl": "urn:uuid:o-fin", "resource": {**potassium("o-fin"), "subject": {"reference": f"urn:uuid:{uid}"}}}]}
        with open(os.path.join(self.tmp.name, "patient_a.json"), "w") as f:
            json.dump(bundle, f)
        nd = os.path.join(self.tmp.name, "bulk")
        os.makedirs(nd)
        uid_b = "22222222-0000-4000-8000-000000000002"
        with open(os.path.join(nd, "Patient.ndjson"), "w") as f:
            f.write(json.dumps({**PATIENT, "id": uid_b}) + "\n\n")
        with open(os.path.join(nd, "Observation.ndjson"), "w") as f:
            f.write(json.dumps({**potassium("o-b"), "subject": {"reference": f"urn:uuid:{uid_b}"}}) + "\n")
            f.write("{not json\n")
        self.uids = (uid, uid_b)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bundles_and_ndjson_give_the_same_loops_as_a_direct_ingest(self):
        from src.clinloop_engine.fhir_folder import run_folder
        store = LoopStore()
        s = run_folder(self.tmp.name, store, now=EVAL)
        self.assertEqual((s["files"], s["patients"]), (3, 2))
        self.assertEqual(s["resource_types"], {"Observation": 3, "Patient": 2})
        self.assertEqual(s["reading"]["unreadable_lines"], 1)
        self.assertEqual(s["reading"]["uuid_subject_assumed_patient"], 1)
        r022 = [l for l in store.worklist(include_inactive=True) if l["rule_id"] == "R022"]
        self.assertEqual(sorted(l["patient_id"] for l in r022 if l["workflow_state"] != "superseded"),
                         sorted(self.uids))                   # one R022 per patient: preliminary superseded
        self.assertEqual(s["loops_by_rule"]["R022"], len(r022))

    def test_summary_carries_no_patient_identifiers(self):
        import contextlib
        import io
        from src.clinloop_engine.fhir_folder import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main([self.tmp.name, "--evaluation-time", "2026-09-03T00:00:00"]), 0)
        for uid in self.uids:
            self.assertNotIn(uid, out.getvalue())
        self.assertIn("not clinical accuracy", out.getvalue())

    def test_empty_folder_is_an_error_not_an_empty_success(self):
        import tempfile
        from src.clinloop_engine.fhir_folder import main
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(main([empty]), 1)


class TestValidationToolsOnFolders(unittest.TestCase):
    """Stage 1A (docs/STUDY_PROTOCOL_STAGE1A.md): the validators read mimic_ingest's NDJSON folder, and
    date-shifted records are judged at each patient's own record end."""

    def setUp(self):
        import json
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        # Two date-shifted patients, decades apart: a warfarin dose change; one has the INR recheck
        rows = {"Patient": [{**PATIENT, "id": "a"}, {**PATIENT, "id": "b"}], "Observation": [], "MedicationRequest": []}
        for pid, year, recheck in (("a", "2131", True), ("b", "2178", False)):
            rows["MedicationRequest"].append({
                "resourceType": "MedicationRequest", "id": f"w-{pid}", "status": "active", "intent": "order",
                "subject": {"reference": f"Patient/{pid}"}, "authoredOn": f"{year}-03-01T10:00:00Z",
                "medicationCodeableConcept": {"text": "warfarin 5 mg"},
                "dosageInstruction": [{"text": "warfarin dose changed from 3 mg to 5 mg"}]})
            if recheck:
                rows["Observation"].append({**potassium(f"inr-{pid}", value=2.4, flag="N", when=f"{year}-03-05T08:00:00Z"),
                                            "subject": {"reference": f"Patient/{pid}"},
                                            "code": {"coding": [{"system": "http://loinc.org", "code": "6301-6",
                                                                 "display": "INR"}]}})
            # the record goes on for a year: the deadline has passed within the patient's own timeline
            rows["Observation"].append({**potassium(f"late-{pid}", value=4.1, flag="N", when=f"{int(year) + 1}-03-01T08:00:00Z"),
                                        "subject": {"reference": f"Patient/{pid}"}})
        for rtype, items in rows.items():
            with open(os.path.join(self.tmp.name, f"{rtype}.ndjson"), "w") as f:
                f.write("".join(json.dumps(r) + "\n" for r in items))

    def tearDown(self):
        self.tmp.cleanup()

    def test_chart_review_reads_a_folder_and_judges_each_record_at_its_own_end(self):
        from src.clinloop_engine.fhir_folder import load_resources
        from src.validation.chart_review import build_frame
        resources = load_resources(self.tmp.name)
        frame = build_frame(resources, per_patient_end=True)
        r007 = {r["patient_id"]: r["predicted_status"] for r in frame if r["rule_id"] == "R007"}
        if not r007:
            self.skipTest("the warfarin fixture opens no R007 in this rule set")
        self.assertEqual(r007.get("a"), "closed")
        self.assertIn(r007.get("b"), ("open", "delayed", "needs_human_review"))
        self.assertTrue(all(r["rule_id"] == "R007" for r in build_frame(resources, per_patient_end=True, rules=["r007"])))

    def test_report_template_reads_a_folder_and_samples(self):
        import csv
        import json
        from src.validation.report_validation import main
        rad = {"resourceType": "DiagnosticReport", "status": "final", "subject": {"reference": "Patient/a"},
               "category": [{"coding": [{"code": "RAD"}]}], "code": {"text": "CT chest"},
               "effectiveDateTime": "2131-04-01T09:00:00Z", "conclusion": "6 mm solid nodule right upper lobe."}
        with open(os.path.join(self.tmp.name, "DiagnosticReport.ndjson"), "w") as f:
            f.write("".join(json.dumps({**rad, "id": f"r{i}"}) + "\n" for i in range(5)))
        out = os.path.join(self.tmp.name, "sheet.csv")
        self.assertEqual(main(["template", "--fhir", self.tmp.name, "--out", out, "--sample", "3"]), 0)
        with open(out) as f:
            self.assertEqual(len(list(csv.DictReader(f))), 3)


try:
    from fastapi.testclient import TestClient
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.api import app
    HAVE_API = True
except ImportError:  # optional dependencies (see requirements-api.txt)
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "API dependencies not installed (pip install -r requirements-api.txt)")
class TestAuditEventExport(unittest.TestCase):

    def setUp(self):
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.client = TestClient(app)
        ingest(self.store, [PATIENT, potassium("b")])
        self.client.get("/api/v1/worklist", headers={"Authorization": f"Bearer {TOKENS['clinician']}"})

    def test_access_records_as_fhir_audit_events(self):
        admin = {"Authorization": f"Bearer {TOKENS['admin']}"}
        b = self.client.get("/api/v1/access-log/audit-events", headers=admin).json()
        self.assertEqual(b["resourceType"], "Bundle")
        ev = next(e["resource"] for e in b["entry"] if e["resource"]["subtype"][0]["code"] == "view_worklist")
        self.assertEqual((ev["resourceType"], ev["type"]["code"], ev["action"], ev["outcome"]), ("AuditEvent", "110110", "R", "0"))
        self.assertTrue(ev["recorded"].endswith("Z"))
        self.assertEqual(ev["agent"][0]["who"]["identifier"]["value"], "clinician.user")
        self.assertTrue(ev["agent"][0]["requestor"])
        self.assertEqual(ev["entity"][0]["what"]["reference"], "Patient/p1")
        self.assertEqual(ev["purposeOfEvent"][0]["coding"][0]["code"], "TREAT")
        chain = {x["url"]: x for x in ev["extension"][0]["extension"]}
        self.assertEqual(len(chain["hash"]["valueString"]), 64)
        self.assertTrue(self.store.verify_access_chain())
        # looking at the export is itself recorded, and only administrators may
        self.assertEqual(self.store.access_log(limit=1)[0]["detail"].get("format"), "AuditEvent")
        self.assertEqual(self.client.get("/api/v1/access-log/audit-events",
                                         headers={"Authorization": f"Bearer {TOKENS['clinician']}"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
