"""Exercise display-only controls and cockpit loading without network/model calls."""
import shutil
import subprocess
from pathlib import Path
import pytest

@pytest.mark.skipif(not shutil.which('node'), reason='Node required for UI checks')
def test_header_controls_and_isolated_preferences():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/test_header_controls.cjs'], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
