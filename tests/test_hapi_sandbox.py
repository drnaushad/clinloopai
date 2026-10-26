"""Exercise synthetic browser connection boundaries without contacting a server."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node required for HAPI browser checks')
def test_hapi_browser_connection():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/test_hapi_sandbox.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '# fail 0' in result.stdout
