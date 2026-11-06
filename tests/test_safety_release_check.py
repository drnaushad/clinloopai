"""Source provenance is separate from clinical authorization."""
import copy
import subprocess
import shutil
import json
from pathlib import Path
import pytest
from scripts.safety_release_check import build,check,source_digest

pytestmark=pytest.mark.skipif(not shutil.which('git'),reason='Source provenance requires Git')


def test_repository_candidate_provenance_matches_current_software():
    root=Path(__file__).resolve().parents[1]
    check(root,json.loads((root/'data/safety_release_status.json').read_text()))


@pytest.fixture
def source(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'src').mkdir()
    (tmp_path/'src/engine.py').write_text('VALUE=1\n')
    return tmp_path


def test_untracked_and_modified_source_invalidate_status(source):
    status=build(source)
    check(source,status)
    (source/'src/new.py').write_text('VALUE=2\n')
    with pytest.raises(ValueError):check(source,status)
    status=build(source)
    (source/'src/engine.py').write_text('VALUE=3\n')
    with pytest.raises(ValueError):check(source,status)


def test_successful_tests_do_not_remove_external_gates(source):
    xml=source/'result.xml'
    xml.write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>')
    status=build(source,xml,source_digest(source))
    assert status['software_tests']['tests']==2
    assert status['clinical_use_authorized'] is False
    assert sum(f['state']=='external_evidence_required' for f in status['findings'])==3
    with pytest.raises(ValueError):build(source,xml,'old-source')
    forged=copy.deepcopy(status);forged['clinical_use_authorized']=True
    with pytest.raises(ValueError):check(source,forged)


def test_failed_or_empty_tests_cannot_be_recorded_as_passed(source):
    xml=source/'result.xml'
    for attrs in ('tests="0"','tests="2" failures="1"','tests="2" errors="1"'):
        xml.write_text('<testsuite '+attrs+'/>')
        with pytest.raises(ValueError):build(source,xml,source_digest(source))
