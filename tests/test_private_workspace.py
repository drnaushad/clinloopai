"""Exercise isolation and loopback-only transport with synthetic fixtures."""
import shutil
import re
import subprocess
import unittest
from pathlib import Path


class TestPrivateWorkspace(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Private workspace checks require Node.js')
    def test_private_transport_and_page(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/test_private_workspace.cjs'],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        passed = re.search(r'^# pass (\d+)$', result.stdout, re.MULTILINE)
        self.assertIsNotNone(passed, result.stdout)
        self.assertGreaterEqual(int(passed.group(1)), 24)

    @unittest.skipUnless(shutil.which('node'), 'Personal API setup checks require Node.js')
    def test_personal_api_setup(self):
        """Run credential lifecycle, origin and stale-request checks in Python-driven CI."""
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/test_research_setup_ui.cjs'],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Structured report checks require Node.js')
    def test_structured_report_workflow(self):
        """Run source, transport, race and byte-budget regressions in Python-driven CI too."""
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/test_report_review.cjs'],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'File import checks require Node.js')
    def test_local_file_import_transport(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/test_report_file_import.cjs'], cwd=root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
