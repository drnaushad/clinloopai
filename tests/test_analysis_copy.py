"""Run the actual analysis display helper; engine evidence must survive language changes."""
from pathlib import Path
import shutil
import subprocess
import pytest

@pytest.mark.skipif(not shutil.which('node'), reason='Node required for analysis display checks')
def test_analysis_display_translation_and_evidence():
    root=Path(__file__).parents[1]
    result=subprocess.run(['node','--test','tests/test_analysis_copy.cjs'],cwd=root,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
