"""
test_notes.py — Plans in clinicians' notes become tracked follow-ups (R048–R051). Synthetic notes only.
"""

import base64
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from test_imaging import HAVE_API, _h  # noqa: E402

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector  # noqa: E402
from src.clinloop_engine.note_reader import find_plans, interval_days, llm_suggestions, plan_label  # noqa: E402

P = {"resourceType": "Patient", "id": "N", "birthDate": "1958-02-01", "gender": "female",
     "name": [{"family": "Hong", "given": ["Gildong"], "text": "Hong Gildong"}],
     "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "MRN-5501"}]}

NOTE_EN = """HPI: 66F with CKD 3. Was told to repeat CT last year but did not.
Exam: unremarkable.
Assessment and Plan:
1. Hyperkalemia (K 5.9): hold lisinopril. Repeat potassium in 1 week.
2. Incidental 7 mm lung nodule on CXR: CT chest in 3 months.
3. Systolic murmur: refer to cardiology.
4. If fever recurs, repeat CBC.
5. No need to repeat echo.
6. HbA1c was rechecked last month.
7. Follow-up in clinic in 6 weeks."""

NOTE_KO = """현병력: 3개월 후 CT 권유받았으나 시행하지 않음.
계획:
- 2주 후 칼륨 재검
- 3개월 후 흉부 CT 추적
- 심장내과 협진 의뢰
- 필요시 복부 초음파 고려
- 6주 후 외래 재방문"""


def doc(text, rid="note1", when="2026-06-01T09:00:00Z", ctype="text/plain"):
    return {"resourceType": "DocumentReference", "id": rid, "status": "current", "docStatus": "final",
            "subject": {"reference": "Patient/N"}, "date": when, "type": {"text": "Progress note"},
            "content": [{"attachment": {"contentType": ctype, "data": base64.b64encode(text.encode()).decode()}}]}


def lab(rid, loinc, name, when, value=4.5):
    return {"resourceType": "Observation", "id": rid, "status": "final", "subject": {"reference": "Patient/N"},
            "category": [{"coding": [{"code": "laboratory"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc}], "text": name},
            "effectiveDateTime": when, "valueQuantity": {"value": value, "unit": "x"}}


def study(rid, modality, body, when, desc=""):
    return {"resourceType": "ImagingStudy", "id": rid, "status": "available", "subject": {"reference": "Patient/N"},
            "started": when, "modality": [{"code": modality}], "description": desc,
            "series": [{"modality": {"code": modality}, "bodySite": {"display": body}}]}


def loops(resources, when=datetime(2026, 10, 8)):
    events, warnings = bundle_to_events(resources)
    assert warnings == [], warnings
    out = {}
    for d in ClinLoopDetector(evaluation_time=when).process_patient("t", "N", events.get("N", [])):
        out.setdefault(d.rule_id, []).append(d.loop_status)
    return {k: v[0] if len(v) == 1 else sorted(v) for k, v in out.items()}


class TestNoteReader(unittest.TestCase):

    def plans(self, text):
        return {(p["kind"], p["target"], p["tracked"]): p for p in find_plans(text)["plans"]}

    def test_english_plan_section(self):
        r = find_plans(NOTE_EN)
        self.assertEqual(r["source"], "plan section")
        got = {(p["kind"], p["target"]): p for p in r["plans"]}
        self.assertEqual(got[("lab", "potassium")]["interval_days"], 7.0)
        self.assertTrue(got[("lab", "potassium")]["tracked"])
        self.assertEqual(got[("imaging", "ct")]["regions"], ["chest"])
        self.assertTrue(got[("referral", "cardiology")]["tracked"])
        self.assertEqual(got[("visit", None)]["interval_days"], 42.0)
        self.assertEqual(got[("lab", "cbc")]["reason"], "conditional: only if something happens")
        self.assertEqual(got[("imaging", "echo")]["reason"], "negated or cancelled")
        self.assertEqual(got[("lab", "hba1c")]["reason"], "already done (past tense)")
        self.assertEqual(r["tracked"], 4)

    def test_korean_plans_and_history_is_not_a_plan(self):
        r = find_plans(NOTE_KO)
        tracked = {(p["kind"], p["target"]) for p in r["plans"] if p["tracked"]}
        self.assertEqual(tracked, {("lab", "potassium"), ("imaging", "ct"), ("referral", "cardiology"), ("visit", None)})
        us = next(p for p in r["plans"] if p["target"] == "ultrasound")
        self.assertFalse(us["tracked"])
        ct = next(p for p in r["plans"] if p["target"] == "ct")
        self.assertIn("흉부", ct["evidence"])                # from the plan, not the history line

    def test_note_without_plan_heading_skips_history(self):
        text = ("History: CT chest was planned in 2024.\nCT chest to be repeated, per old notes.\n\n"
                "Today stable. Recheck labs in 4-6 weeks and RTC 3 months.")
        got = {(p["kind"], p["target"]): p for p in find_plans(text)["plans"]}
        self.assertNotIn(("imaging", "ct"), got)
        self.assertEqual(got[("lab", None)]["interval_days"], 42.0)      # upper bound of 4-6 weeks
        self.assertAlmostEqual(got[("visit", None)]["interval_days"], 91.3, places=1)

    def test_intervals(self):
        self.assertEqual(interval_days("in 2 weeks")[0], 14.0)
        self.assertEqual(interval_days("3개월 후")[0], 91.3)
        self.assertEqual(interval_days("next week")[0], 7.0)
        self.assertEqual(interval_days("in two months")[0], 60.9)
        self.assertIsNone(interval_days("soon")[0])

    def test_unspecified_interval_uses_conservative_default(self):
        p = find_plans("Plan: refer to nephrology.")["plans"][0]
        self.assertFalse(p["interval_stated"])
        self.assertEqual(p["interval_days"], 30.0)
        self.assertEqual(plan_label(p), "Referral to nephrology (no interval stated)")


class TestNotePlanLoops(unittest.TestCase):

    def test_matching_follow_ups_close_their_plans_only(self):
        res = [P, doc(NOTE_EN),
               lab("k2", "2823-3", "Potassium", "2026-06-06T08:00:00Z"),          # closes R048 (potassium)
               lab("t1", "3016-3", "TSH", "2026-06-05T08:00:00Z"),                 # unrelated test
               study("x1", "DX", "CHEST", "2026-07-01T09:00:00Z", "Chest X-ray")]   # not a CT
        statuses = loops(res)
        self.assertEqual(statuses["R048"], "closed")
        self.assertEqual(statuses["R049"], "open")
        self.assertEqual(statuses["R050"], "open")
        self.assertEqual(statuses["R051"], "open")

    def test_wrong_test_does_not_close(self):
        self.assertEqual(loops([P, doc("Plan: repeat potassium in 1 week."),
                                lab("t1", "3016-3", "TSH", "2026-06-05T08:00:00Z")])["R048"], "open")

    def test_ct_must_cover_the_region(self):
        note = doc("Plan: CT chest in 3 months.")
        head = study("c1", "CT", "HEAD", "2026-08-20T09:00:00Z", "CT head")
        chest = study("c2", "CT", "CHEST", "2026-08-25T09:00:00Z", "CT chest")
        self.assertEqual(loops([P, note, head])["R049"], "open")
        self.assertEqual(loops([P, note, chest])["R049"], "closed")

    def test_referral_to_same_specialty(self):
        note = doc("Plan: refer to cardiology.")
        derm = {"resourceType": "ServiceRequest", "id": "s1", "status": "active", "intent": "order",
                "subject": {"reference": "Patient/N"}, "authoredOn": "2026-06-03",
                "code": {"text": "Referral to dermatology"}}
        cardio = {**derm, "id": "s2", "code": {"text": "Referral to cardiology"}}
        self.assertEqual(loops([P, note, derm])["R050"], "open")
        self.assertEqual(loops([P, note, cardio])["R050"], "closed")

    def test_untracked_plans_open_nothing_and_html_notes_are_read(self):
        html = "<p><b>Plan:</b></p><ul><li>If fever recurs, repeat CBC.</li><li>No need to repeat echo.</li></ul>"
        self.assertEqual(loops([P, doc(html, ctype="text/html")]), {})
        events, _ = bundle_to_events([P, doc(html, ctype="text/html")])
        self.assertEqual(len(events["N"]), 2)                 # shown on the graph, not tracked

    def test_preliminary_note_is_ignored(self):
        d = doc("Plan: repeat potassium in 1 week.")
        d["docStatus"] = "preliminary"
        self.assertEqual(loops([P, d]), {})

    def test_several_plans_have_stable_distinct_ids(self):
        e1, _ = bundle_to_events([P, doc(NOTE_EN)])
        e2, _ = bundle_to_events([P, doc(NOTE_EN)])
        ids = [e["event_id"] for e in e1["N"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [e["event_id"] for e in e2["N"]])


class TestLLMSuggestions(unittest.TestCase):

    def test_suggestions_must_quote_the_note_and_are_never_tracked(self):
        answer = ('{"plans": [{"kind": "lab", "target": "magnesium", "interval": "1 week", "quote": "check Mg next week"},'
                  ' {"kind": "imaging", "target": "MRI brain", "quote": "MRI brain to be arranged"},'
                  ' {"kind": "lab", "target": "potassium", "quote": "Repeat potassium in 1 week"}]}')
        note = "Plan: Repeat potassium in 1 week. Also check Mg next week."
        with mock.patch("src.clinloop_engine.local_llm_engine.generate_clinical_text",
                        return_value={"text": answer, "model": "local"}):
            out = llm_suggestions(note, find_plans(note)["plans"])
        self.assertTrue(out["available"])
        quotes = [s["quote"] for s in out["suggestions"]]
        self.assertEqual(quotes, ["check Mg next week"])        # invented MRI dropped; potassium already found

    def test_unavailable_llm_is_reported(self):
        with mock.patch("src.clinloop_engine.local_llm_engine.generate_clinical_text",
                        return_value={"error": "No local LLM available", "text": ""}):
            self.assertFalse(llm_suggestions("Plan: x", [])["available"])


@unittest.skipUnless(HAVE_API, "API dependencies not installed")
class TestClinicalNoteAPI(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from src.clinloop_engine import clinical_api
        from src.clinloop_engine.api import app
        from src.clinloop_engine.loop_store import LoopStore
        clinical_api.set_store(LoopStore())
        self.client = TestClient(app)
        r = self.client.post("/api/v1/fhir/ingest?evaluation_time=2026-06-01T00:00:00",
                             json={"resourceType": "Bundle", "entry": [{"resource": P}]}, headers=_h("admin"))
        self.assertEqual(r.status_code, 200, r.text)

    def test_extract_then_file(self):
        body = {"patient_id": "N", "text": "Patient Hong Gildong, MRN-5501.\n" + NOTE_EN, "date": "2026-06-01"}
        self.assertEqual(self.client.post("/api/v1/documents/clinical-note/extract", json=body,
                                          headers=_h("viewer")).status_code, 403)
        ex = self.client.post("/api/v1/documents/clinical-note/extract", json=body, headers=_h("navigator")).json()
        self.assertEqual(ex["tracked"], 4)
        self.assertIn("label", ex["plans"][0])
        r = self.client.post("/api/v1/documents/clinical-note", json=body, headers=_h("navigator"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue({"R048", "R049", "R050", "R051"} <= {a["rule_id"] for a in r.json()["active"]})
        docs = self.client.get("/api/v1/patients/N/documents", headers=_h("viewer")).json()["documents"]
        self.assertEqual([d["kind"] for d in docs], ["clinical-note"])
        stored = get_note(self)
        self.assertNotIn("Gildong", stored)                  # the patient's name is removed before storage
        self.assertIn("Repeat potassium in 1 week", stored)
        g = self.client.get("/api/v1/patients/N/graph?evaluation_time=2026-06-02T00:00:00", headers=_h("viewer")).json()
        self.assertTrue(any(n["lane"] == "notes" for n in g["nodes"]))

    def test_needs_text_and_valid_date(self):
        self.assertEqual(self.client.post("/api/v1/documents/clinical-note", json={"patient_id": "N"},
                                          headers=_h("navigator")).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/documents/clinical-note", json={"patient_id": "N", "text": "x",
                                          "date": "01/06/2026"}, headers=_h("navigator")).status_code, 422)


def get_note(test) -> str:
    from src.clinloop_engine import clinical_api
    r = next(x for x in clinical_api.get_store().external_resources("N") if x["resourceType"] == "DocumentReference")
    return base64.b64decode(r["content"][0]["attachment"]["data"]).decode()


if __name__ == "__main__":
    unittest.main()
