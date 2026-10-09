"""
test_hospital_data.py — Behaviour found by running a full hospital-style EHR export (Synthea FHIR bulk data)

Each test reproduces one problem a real hospital feed showed, with small synthetic resources:
renewals counted as medication changes, known heart failure counted as new, AKI warnings on
dialysis, decades-old obligations on today's worklist, and labs with ranges but no flags.
"""

import os
import sys
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.fhir_ingest import bundle_to_events  # noqa: E402
from src.clinloop_engine.loop_detector import ClinLoopDetector, hospital_detector  # noqa: E402

P = {"resourceType": "Patient", "id": "P", "gender": "male", "birthDate": "1950-01-01"}
NOW = datetime(2023, 4, 1)


def rules(resources, when=NOW, detector=None):
    events, warnings = bundle_to_events([P] + resources)
    det = detector or ClinLoopDetector(evaluation_time=when)
    return [d for d in det.process_patient("t", "P", events.get("P", []))], warnings


def med(rid, when, text="lisinopril 10 MG Oral Tablet", dose=None):
    r = {"resourceType": "MedicationRequest", "id": rid, "status": "active", "intent": "order",
         "subject": {"reference": "Patient/P"}, "authoredOn": when, "medicationCodeableConcept": {"text": text}}
    if dose:
        r["dosageInstruction"] = [{"text": dose}]
    return r


def lab(rid, when, loinc, text, value, unit="mg/dL", **extra):
    return {"resourceType": "Observation", "id": rid, "status": "final", "subject": {"reference": "Patient/P"},
            "category": [{"coding": [{"code": "laboratory"}]}], "effectiveDateTime": when,
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc}], "text": text},
            "valueQuantity": {"value": value, "unit": unit}, **extra}


def encounter(rid, cls, start, end, reason):
    return {"resourceType": "Encounter", "id": rid, "status": "finished", "class": {"code": cls},
            "subject": {"reference": "Patient/P"}, "period": {"start": start, "end": end},
            "reasonCode": [{"text": reason}]}


def condition(rid, onset, text):
    return {"resourceType": "Condition", "id": rid, "subject": {"reference": "Patient/P"}, "onsetDateTime": onset,
            "clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"text": text}}


class TestHospitalExport(unittest.TestCase):

    def test_a_renewal_is_not_a_medication_change(self):
        found, _ = rules([med("m1", "2022-01-10T09:00:00"), med("m2", "2022-07-10T09:00:00"),
                          med("m3", "2023-01-10T09:00:00")])
        self.assertEqual([d.trigger_event_id for d in found if d.rule_id == "R010"],
                         ["MedicationRequest/m1:medication_change"])        # the start only

    def test_a_new_dose_or_a_restart_is_a_change(self):
        found, _ = rules([med("m1", "2021-01-10T09:00:00"), med("m2", "2021-03-10T09:00:00", "lisinopril 20 MG Oral Tablet"),
                          med("m3", "2022-09-10T09:00:00", "lisinopril 20 MG Oral Tablet")])   # 18 months later: restart
        self.assertEqual(sum(d.rule_id == "R010" for d in found), 3)

    def test_warfarin_dose_change_with_the_same_tablet_is_a_change(self):
        tab = "warfarin sodium 5 MG Oral Tablet"
        found, _ = rules([med("w1", "2023-01-02T09:00:00", tab, "5 mg daily"),
                          med("w2", "2023-02-02T09:00:00", tab, "7.5 mg daily"),
                          med("w3", "2023-03-02T09:00:00", tab, "7.5 mg daily")])
        triggers = sorted(d.trigger_event_id for d in found if d.trigger_event == "medication_change")
        self.assertIn("MedicationRequest/w2:medication_change", triggers)
        self.assertNotIn("MedicationRequest/w3:medication_change", triggers)

    def test_known_heart_failure_is_not_a_new_diagnosis(self):
        known = [condition("c1", "2019-05-01", "Chronic congestive heart failure (disorder)"),
                 encounter("e1", "IMP", "2023-02-01T08:00:00", "2023-02-05T10:00:00", "Chronic congestive heart failure")]
        found, _ = rules(known)
        self.assertNotIn("R016", {d.rule_id for d in found})               # no "new HF → echo"
        self.assertIn("R023", {d.rule_id for d in found})                  # but the 7-day visit is still due
        first, _ = rules([encounter("e1", "IMP", "2023-02-01T08:00:00", "2023-02-05T10:00:00", "Heart failure")])
        self.assertIn("R016", {d.rule_id for d in first})

    def test_no_aki_warning_on_dialysis_but_again_after_transplant(self):
        crea = [lab(f"k{i}", f"2022-0{m}-01T08:00:00", "2160-0", "Creatinine", v)
                for i, (m, v) in enumerate([(1, 4.0), (2, 4.1), (3, 8.5)])]
        dialysis = {"resourceType": "Procedure", "id": "d1", "status": "completed", "subject": {"reference": "Patient/P"},
                    "code": {"text": "Renal dialysis (procedure)"}, "performedDateTime": "2022-02-15T08:00:00"}
        self.assertIn("R053", {d.rule_id for d in rules(crea)[0]})
        self.assertNotIn("R053", {d.rule_id for d in rules(crea + [dialysis])[0]})
        later = [lab("t0", "2022-09-15T08:00:00", "2160-0", "Creatinine", 1.0),     # a working transplant
                 lab("t1", "2022-10-01T08:00:00", "2160-0", "Creatinine", 1.0),
                 lab("t2", "2022-10-15T08:00:00", "2160-0", "Creatinine", 1.1),
                 lab("t3", "2022-11-01T08:00:00", "2160-0", "Creatinine", 2.2)]     # months after the last session
        self.assertIn("R053", {d.rule_id for d in rules(crea + [dialysis] + later)[0]})
        esrd = condition("c2", "2021-06-01", "End-stage renal disease (disorder)")
        self.assertNotIn("R053", {d.rule_id for d in rules(crea + [esrd])[0]})

    def test_reference_range_flags_a_result_without_an_interpretation(self):
        rng = {"referenceRange": [{"low": {"value": 3.5}, "high": {"value": 5.1}}]}
        found, _ = rules([lab("p1", "2023-03-30T08:00:00", "2823-3", "Potassium", 6.2, "mmol/L", **rng)])
        self.assertTrue({"R001", "R002"} & {d.rule_id for d in found})
        normal, _ = rules([lab("p1", "2023-03-30T08:00:00", "2823-3", "Potassium", 4.2, "mmol/L", **rng)])
        self.assertFalse({"R001", "R002"} & {d.rule_id for d in normal})
        two = {"referenceRange": [{"low": {"value": 3.5}, "high": {"value": 5.1}},
                                  {"low": {"value": 3.4}, "high": {"value": 4.7}, "appliesTo": [{"text": "neonate"}]}]}
        self.assertTrue({"R001", "R002"} & {d.rule_id for d in rules(
            [lab("p1", "2023-03-30T08:00:00", "2823-3", "Potassium", 6.2, "mmol/L", **two)])[0]})

    def test_referral_recorded_as_a_procedure(self):
        psa = lab("p1", "2023-02-01T08:00:00", "2857-1", "Prostate specific Ag", 6.1, "ng/mL")

        def proc(text):
            return {"resourceType": "Procedure", "id": "r1", "status": "completed", "subject": {"reference": "Patient/P"},
                    "code": {"text": text}, "performedPeriod": {"start": "2023-02-10T09:00:00"}}
        r004 = {d.rule_id: d for d in rules([psa, proc("Referral to urology service (procedure)")])[0]}["R004"]
        self.assertEqual(r004.loop_status, "closed")
        dental = {d.rule_id: d for d in rules([psa, proc("Patient referral for dental care (procedure)")])[0]}["R004"]
        self.assertEqual(dental.loop_status, "open")          # not a urology referral

    def test_psa_needs_urology_or_a_prostate_biopsy(self):
        psa = lab("p1", "2023-02-01T08:00:00", "2857-1", "Prostate specific Ag", 6.1, "ng/mL")

        def proc(rid, text):
            return {"resourceType": "Procedure", "id": rid, "status": "completed", "subject": {"reference": "Patient/P"},
                    "code": {"text": text}, "performedDateTime": "2023-02-10T09:00:00"}
        status = lambda extra: {d.rule_id: d for d in rules([psa, extra])[0]}["R004"].loop_status  # noqa: E731
        self.assertEqual(status(proc("b", "Biopsy of prostate (procedure)")), "closed")
        self.assertEqual(status(proc("b", "Skin biopsy")), "open")
        self.assertEqual(status(proc("r", "Referral to cardiology service (procedure)")), "open")

    def test_referral_opens_a_visit_loop_closed_by_that_specialty(self):
        ref = {"resourceType": "ServiceRequest", "id": "s1", "status": "active", "intent": "order",
               "subject": {"reference": "Patient/P"}, "authoredOn": "2023-01-02T09:00:00",
               "code": {"text": "Referral to cardiology"}, "category": [{"text": "referral"}]}

        def visit(service):
            return {"resourceType": "Encounter", "id": "v1", "status": "finished", "class": {"code": "AMB"},
                    "subject": {"reference": "Patient/P"}, "period": {"start": "2023-01-20T09:00:00", "end": "2023-01-20T09:30:00"},
                    "serviceType": {"text": service}}
        r008 = lambda extra: {d.rule_id: d for d in rules([ref] + extra)[0]}["R008"].loop_status  # noqa: E731
        self.assertEqual(r008([]), "open")
        self.assertEqual(r008([visit("Cardiology clinic")]), "closed")
        self.assertEqual(r008([visit("Dermatology clinic")]), "open")
        self.assertEqual(r008([visit("General practice")]), "open")        # no specialty named: not assumed

    def test_ed_visit_that_ends_in_admission_is_one_stay(self):
        ed = encounter("ed", "EMER", "2023-02-01T08:00:00", "2023-02-01T14:00:00", "Myocardial infarction")
        ward = encounter("w", "IMP", "2023-02-01T14:30:00", "2023-02-05T10:00:00", "Myocardial infarction")
        found = [d for d in rules([ed, ward])[0] if d.rule_id == "R014"]
        self.assertEqual([d.trigger_event_id for d in found], ["Encounter/w:discharge"])

    def test_delivery_after_preeclampsia_needs_a_postpartum_bp_check(self):
        dx = condition("c", "2022-12-20", "Pre-eclampsia (disorder)")
        dx["clinicalStatus"] = {"coding": [{"code": "resolved"}]}           # resolved at delivery, as EHRs record it
        delivery = encounter("d", "IMP", "2023-02-01T08:00:00", "2023-02-03T10:00:00", "Normal pregnancy")
        delivery["type"] = [{"text": "Obstetric emergency hospital admission"}]
        r024 = {d.rule_id: d for d in rules([dx, delivery])[0]}["R024"]
        self.assertEqual((datetime.fromisoformat(r024.deadline) - datetime.fromisoformat(r024.trigger_time)).days, 10)
        severe = {d.rule_id: d for d in rules([condition("c", "2022-12-20", "Eclampsia in pregnancy"), delivery])[0]}["R024"]
        self.assertEqual((datetime.fromisoformat(severe.deadline) - datetime.fromisoformat(severe.trigger_time)).days, 3)

    def test_monitoring_after_a_start_covers_drug_classes_and_any_specimen_code(self):
        start = med("m1", "2023-01-02T09:00:00", "Furosemide 40 MG Oral Tablet")
        k = lab("k", "2023-01-09T09:00:00", "6298-4", "Potassium [Moles/volume] in Blood", 4.1, "mmol/L")
        self.assertEqual({d.rule_id: d for d in rules([start])[0]}["R010"].loop_status, "open")
        self.assertEqual({d.rule_id: d for d in rules([start, k])[0]}["R010"].loop_status, "closed")
        down = rules([med("a", "2023-01-02T09:00:00", "lisinopril 20 MG Oral Tablet"),
                      med("b", "2023-02-02T09:00:00", "lisinopril 10 MG Oral Tablet")])[0]
        self.assertEqual([d.trigger_event_id for d in down if d.rule_id == "R010"],
                         ["MedicationRequest/a:medication_change"])          # a dose reduction needs no new labs
        chemo = rules([med("p", "2023-01-02T09:00:00", "PACLitaxel 100 MG Injection"),
                       med("c", "2023-01-03T09:00:00", "Cisplatin 50 MG Injection")])[0]
        self.assertEqual(sum(d.rule_id == "R010" for d in chemo), 2)       # two drugs, not a reduction of one
        iv = rules([med("o", "2023-01-02T09:00:00", "Furosemide 40 MG Oral Tablet"),
                    med("i", "2023-01-05T09:00:00", "10 ML Furosemide 10 MG/ML Injection")])[0]
        self.assertEqual(sum(d.rule_id == "R010" for d in iv), 2)          # a new route is a new start

    def test_obligations_that_lapse_with_death_leave_the_worklist(self):
        from src.clinloop_engine.loop_detector import lapse_after_death
        dead = dict(P, deceasedDateTime="2023-02-10T00:00:00")
        res = [dead, lab("old", "2022-11-01T08:00:00", "2857-1", "Prostate specific Ag", 6.0, "ng/mL"),
               lab("new", "2023-02-01T08:00:00", "2857-1", "Prostate specific Ag", 7.0, "ng/mL")]
        events, _ = bundle_to_events(res)
        found = ClinLoopDetector(evaluation_time=NOW).process_patient("t", "P", events["P"])
        kept = lapse_after_death(found, res)
        self.assertEqual([d.trigger_event_id for d in kept if d.rule_id == "R004"],
                         ["Observation/old:lab_result"])   # overdue before death: missed; the newer one lapsed

    def test_monitoring_windows_follow_the_drug(self):
        def r010(text):
            d = {d.rule_id: d for d in rules([med("m", "2023-01-02T09:00:00", text)])[0]}.get("R010")
            return d and round((datetime.fromisoformat(d.deadline) - datetime.fromisoformat(d.trigger_time)).days)
        self.assertEqual(r010("Levothyroxine 50 MCG Oral Tablet"), 56)     # TSH at 6–8 weeks
        self.assertEqual(r010("Lithium carbonate 300 MG Oral Capsule"), 7)
        self.assertEqual(r010("lisinopril 10 MG Oral Tablet"), 14)
        self.assertIsNone(r010("Metformin 500 MG Oral Tablet"))             # renal function before, not after

    def test_overlapping_inpatient_encounters_are_one_stay(self):
        a = encounter("a", "IMP", "2023-02-01T08:00:00", "2023-02-03T10:00:00", "Chronic congestive heart failure")
        b = encounter("b", "IMP", "2023-02-02T08:00:00", "2023-02-06T10:00:00", "Chronic congestive heart failure")
        found = [d.trigger_event_id for d in rules([a, b])[0] if d.rule_id == "R023"]
        self.assertEqual(found, ["Encounter/b:discharge"])

    def test_a_feed_without_flags_or_ranges_says_so(self):
        labs = [lab(f"l{i}", "2023-03-01T08:00:00", "2345-7", "Glucose", 90 + i) for i in range(25)]
        _, warnings = rules(labs)
        self.assertTrue(any("no interpretation flag and no reference range" in w for w in warnings))
        _, few = rules(labs[:5])
        self.assertFalse(any("no interpretation flag" in w for w in few))

    def test_hospital_worklist_leaves_out_decades_old_obligations(self):
        psa = [lab("old", "1977-03-26T03:31:03", "2857-1", "Prostate specific Ag", 4.6, "ng/mL"),
               lab("new", "2023-03-01T08:00:00", "2857-1", "Prostate specific Ag", 5.2, "ng/mL")]
        everything, _ = rules(psa)
        self.assertEqual(sum(d.rule_id == "R004" for d in everything), 2)
        with mock.patch.dict(os.environ, {"CLINLOOP_HISTORY_DAYS": "365"}):
            recent, _ = rules(psa, detector=hospital_detector(NOW))
        self.assertEqual([d.trigger_event_id for d in recent if d.rule_id == "R004"], ["Observation/new:lab_result"])
        with mock.patch.dict(os.environ, {"CLINLOOP_HISTORY_DAYS": "0"}):
            self.assertEqual(sum(d.rule_id == "R004" for d in rules(psa, detector=hospital_detector(NOW))[0]), 2)


if __name__ == "__main__":
    unittest.main()
