"""Run the browser planner's semantic tests through the existing Python CI entry point."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TestDeploymentPlanner(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Planner JavaScript tests require Node.js')
    def test_international_plans_preserve_unvalidated_scope(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', '--test', '--test-reporter=tap', str(root / 'tests/test_deployment_plan.cjs')],
            cwd=root, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('# pass 5', result.stdout)
