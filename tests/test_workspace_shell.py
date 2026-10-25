"""Shared navigation must preserve isolated research and clinical page controls."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node required for workspace shell checks')
def test_workspace_shell_navigation_and_session_isolation():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/test_workspace_shell.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
