"""
test_rule_check.py — The rule set itself: every rule can fire on hospital data and every loop can close.
"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine import clinical_ontology as co  # noqa: E402
from src.clinloop_engine import rule_check  # noqa: E402


class TestRuleCheck(unittest.TestCase):

    def test_current_rule_set_has_no_errors(self):
        r = rule_check.check_rules()
        errors = [i for i in r["issues"] if i["level"] == "error"]
        self.assertEqual(errors, [], errors)
        self.assertEqual(r["rules"], len(co.OBLIGATION_RULES))

    def test_a_broken_rule_is_caught(self):
        bad = co.ObligationRule(rule_id="R999", name="x", description="x", trigger_event=co.EventType.LAB_RESULT,
                                trigger_condition="zzz_never_produced",
                                required_followups=[co.EventType.SEPSIS_BUNDLE_COMPLETION],
                                deadline_days=1.0, severity=co.Severity.LOW, clinical_domain="x", ltl_formula="")
        with mock.patch.object(rule_check, "OBLIGATION_RULES", co.OBLIGATION_RULES + [bad]):
            issues = [i for i in rule_check.check_rules()["issues"] if i["rule_id"] == "R999"]
        messages = " ".join(i["message"] for i in issues if i["level"] == "error")
        self.assertIn("never fires", messages)
        self.assertIn("stay open", messages)
        self.assertTrue(any("Korean" in i["message"] for i in issues))

    def test_runtime_built_conditions_count(self):
        self.assertTrue(rule_check._produces_condition('d["condition"] = f"note_plan_{p[\'kind\']}"', "note_plan_lab"))
        self.assertFalse(rule_check._produces_condition('x = "note_plan"', "note_plan_lab"))


if __name__ == "__main__":
    unittest.main()
