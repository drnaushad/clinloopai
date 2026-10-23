"""Synthetic source-lifecycle regressions for the browser analyser; no network/model calls."""
from pathlib import Path
import shutil
import subprocess
import pytest

@pytest.mark.skipif(not shutil.which('node'), reason='Node required for UI workflow tests')
def test_analyse_source_lifecycle():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run(['node','tests/test_analyse_workflow.cjs'],cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
