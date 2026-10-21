"""Exercise isolation and loopback-only transport with synthetic fixtures."""
import shutil
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
        self.assertIn('# pass 16', result.stdout)
