import unittest
import json
from unittest.mock import patch
from src.clinloop_engine.counterfactual_engine import get_counterfactual_analysis
from src.clinloop_engine.patient_outreach_agent import OutreachRequest, generate_dynamic_outreach
from src.clinloop_engine.biomcp_server import handle_call_tool

class TestNobleEngine(unittest.TestCase):
    def test_counterfactual_engine(self):
        cf = get_counterfactual_analysis("SC-0004")
        self.assertEqual(cf.delta_5yr_survival, 0.75)
        self.assertEqual(cf.qaly_gain, 11.2)
        self.assertEqual(cf.malpractice_cost_avoidance_krw, 350000000)
        self.assertTrue(len(cf.neglected_path) >= 4)
        self.assertTrue(len(cf.intervened_path) >= 4)

    def test_patient_outreach_agent(self):
        request = OutreachRequest(
            patient_id="SYNTHETIC-001",
            obligation_id="OBL-001",
            message_category="follow_up",
            approved_facts={"finding": "abnormal result", "timeframe": "30 days"},
            preferred_language="ko",
            health_literacy_mode="plain",
            permitted_channel="none",
            scheduling_link=None,
            urgency_level="CRITICAL",
            prohibited_topics=["diagnosis", "prognosis"],
        )
        with patch(
            "src.clinloop_engine.patient_outreach_agent.generate_kakao_message",
            return_value={"kakao_message_text": "합성 안내문 초안"},
        ) as generate_message:
            draft = generate_dynamic_outreach(request)

        self.assertEqual(draft.message_text, "합성 안내문 초안")
        self.assertEqual(draft.language, "ko")
        self.assertTrue(draft.requires_human_review)
        self.assertEqual(set(draft.facts_used), {"finding", "timeframe"})
        generate_message.assert_called_once()

    def test_biomcp_server(self):
        res = handle_call_tool("biomcp_query_guidelines", {
            "finding_category": "cervical_cytology",
            "finding_value": "HSIL"
        })
        self.assertEqual(res["status"], "grounded")
        self.assertEqual(res["derived_t_crit"], 30)
        self.assertEqual(res["pmid"], "32243307")

    def test_cases_json_grounding(self):
        with open("demo/data/cases.json", "r", encoding="utf-8") as f:
            cases = json.load(f)
        self.assertEqual(len(cases), 5)
        for c in cases:
            self.assertIn("omop_cdm", c)
            self.assertIn("fhir_r4", c)
            self.assertIn("counterfactual", c)
            self.assertIn("patient_outreach", c)
            self.assertIn("concept_id", c["omop_cdm"])
            self.assertIn("resourceType", c["fhir_r4"])
            self.assertIn("delta_5yr_survival", c["counterfactual"])

if __name__ == "__main__":
    unittest.main()
