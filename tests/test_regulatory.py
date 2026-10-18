"""
test_regulatory.py — The regulatory file stays true to the code

The documents in docs/regulatory/ make claims about the code: which safety requirement is
implemented where and verified by which test, which dependencies ship, which features the core
profile locks off. These tests fail when a claim stops being true, so the file cannot drift silently.
"""

import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

REG = os.path.join(ROOT, "docs", "regulatory")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def _table_rows(text, first_cell):
    """Cells of the markdown table rows whose first cell matches ``first_cell`` (a regex)."""
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if re.fullmatch(first_cell, cells[0]):
                rows.append(cells)
    return rows


class TestTraceability(unittest.TestCase):

    def setUp(self):
        self.trace = _table_rows(_read(REG, "TRACEABILITY.md"), r"SR-\d+")
        self.risks = _table_rows(_read(REG, "RISK_MANAGEMENT.md"), r"H-\d+")

    def test_every_hazard_has_a_control_and_every_control_a_hazard(self):
        self.assertGreaterEqual(len(self.risks), 10)
        hazards = {r[0] for r in self.risks}
        covered = {h for row in self.trace for h in re.findall(r"H-\d+", row[2])}
        cited = {sr for r in self.risks for sr in re.findall(r"SR-\d+", r[5])}
        self.assertEqual(hazards - covered, set(), "hazards with no safety requirement in TRACEABILITY.md")
        self.assertEqual(covered - hazards, set(), "TRACEABILITY.md names hazards the risk file does not have")
        self.assertEqual({r[0] for r in self.trace} - cited, set(), "requirements no hazard's controls cite")
        self.assertEqual(cited - {r[0] for r in self.trace}, set(), "the risk file cites requirements that do not exist")

    def test_named_code_exists(self):
        for row in self.trace:
            refs = [r.strip() for r in row[3].split("<br>") if r.strip()]
            self.assertTrue(refs, row[0])
            for ref in refs:
                path, symbol = ref.split("::")
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)), f"{row[0]}: {path} does not exist")
                self.assertIn(symbol, _read(ROOT, path), f"{row[0]}: {symbol!r} not found in {path}")

    def test_named_tests_exist(self):
        for row in self.trace:
            refs = [r.strip() for r in row[4].split("<br>") if r.strip()]
            self.assertTrue(refs, f"{row[0]} has no verifying test")
            for ref in refs:
                path, name = ref.split("::")
                self.assertRegex(_read(ROOT, path), rf"def {re.escape(name)}\(", f"{row[0]}: {ref} does not exist")


class TestSBOM(unittest.TestCase):

    def test_sbom_matches_the_lock_file(self):
        from build_sbom import OUT, locked_packages, render
        self.assertEqual(_read(OUT), render(), "SBOM out of date: run python scripts/build_sbom.py")
        self.assertEqual(len(locked_packages()), 
                         sum(1 for line in _read(ROOT, "requirements.lock").splitlines()
                             if "==" in line and not line.lstrip().startswith("#")))


class TestDocumentsMatchTheProfile(unittest.TestCase):

    def test_research_rules_and_features_are_named_in_the_file(self):
        from src.clinloop_engine import profile
        intended, assessment = _read(REG, "INTENDED_USE.md"), _read(REG, "REGULATORY_ASSESSMENT.md")
        for rule in profile.RESEARCH_RULES:
            self.assertIn(rule, intended)
            self.assertIn(rule, assessment)
        self.assertIn("CLINLOOP_PROFILE=core", intended)

    def test_links_between_documents_resolve(self):
        for name in os.listdir(REG):
            if not name.endswith(".md"):
                continue
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", _read(REG, name)):
                if target.startswith("http"):
                    continue
                self.assertTrue(os.path.exists(os.path.normpath(os.path.join(REG, target))), f"{name}: {target}")


if __name__ == "__main__":
    unittest.main()
