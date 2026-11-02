"""Tampered or incomplete deployed assets must fail before Python executes."""
from pathlib import Path
import shutil
import subprocess
import pytest

@pytest.mark.skipif(not shutil.which('node'), reason='Node required for browser engine integrity checks')
def test_browser_engine_integrity_loader():
    result=subprocess.run(['node','--test','tests/test_browser_engine_loader.cjs'],cwd=Path(__file__).parents[1],
                          capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
