"""Regression checks for selected-language notices and decorative controls."""
import shutil
import subprocess
from pathlib import Path
import pytest

@pytest.mark.skipif(not shutil.which('node'), reason='Node required for language UI checks')
def test_selected_language_notices_and_controls():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/test_language_controls.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
