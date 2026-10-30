"""Keep fixed synthetic extraction scoring and provenance checks in the Python CI suite."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node required for extraction evaluation checks')
def test_report_evaluation_scoring_and_provenance():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '--test-reporter=tap', 'tests/test_report_evaluation.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '# pass 16' in result.stdout
