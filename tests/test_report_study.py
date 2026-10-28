"""Run offline study-integrity checks; no real records, models or network."""
import pathlib
import shutil
import subprocess
import unittest


class ReportStudyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for offline study checks')
    def test_study_integrity(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/test_report_study.cjs'], cwd=root,
            capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
