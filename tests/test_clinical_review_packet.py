"""Review receipts are source-bound evidence, never medical or runtime approval."""
import copy
import subprocess
import shutil
from datetime import datetime, timedelta, timezone

import pytest
from scripts.clinical_review_packet import build, verify, ReviewError

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="Developer review packet integration requires Git; run on the source checkout")


@pytest.fixture
def draft(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, text=True).strip()
    git('init', '-q')
    git('config', 'user.email', 'synthetic@example.invalid')
    git('config', 'user.name', 'Synthetic test')
    source = tmp_path / 'src/clinloop_engine'
    source.mkdir(parents=True)
    file = source / 'fhir_ingest.py'
    file.write_text('VALUE = 1\n')
    git('add', '.')
    git('commit', '-qm', 'Synthetic base')
    base = git('rev-parse', 'HEAD')
    file.write_text('VALUE = 2\n')
    return tmp_path, base, file


def approved(packet):
    packet = copy.deepcopy(packet)
    for row in packet['files']:
        row.update(reviewer='Synthetic human reviewer', reviewer_role='clinician',
                   reviewed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                   decision='approved', line_by_line_review_complete=True)
    return packet


def test_generated_packet_is_pending_and_never_authorizes_care(draft):
    root, base, _ = draft
    packet = build(root, base)
    result = verify(packet, root, base)
    assert result['status'] == 'PENDING_HUMAN_REVIEW'
    assert result['pending'] == 1
    assert not result['clinical_use_authorized']
    assert packet['files'][0]['requires_clinician']


def test_complete_receipts_do_not_become_clinical_validation(draft):
    root, base, _ = draft
    result = verify(approved(build(root, base)), root, base)
    assert result['status'] == 'REVIEW_RECORDS_COMPLETE_NOT_CLINICAL_VALIDATION'
    assert not result['runtime_rule_signoffs_created']
    assert not result['clinical_use_authorized']


def test_source_changes_invalidate_previously_dated_receipts(draft):
    root, base, source = draft
    packet = approved(build(root, base))
    source.write_text('VALUE = 3\n')
    with pytest.raises(ReviewError, match='stale'):
        verify(packet, root, base)


def test_omitted_new_or_reordered_scope_is_rejected(draft):
    root, base, _ = draft
    packet = build(root, base)
    (root / 'src/clinloop_engine/new_clinical.py').write_text('VALUE = 1\n')
    with pytest.raises(ReviewError):
        verify(packet, root, base)
    assert len(build(root, base)['files']) == 2


def test_staging_new_files_does_not_invalidate_unchanged_review_scope(draft):
    root, base, _ = draft
    added = root / 'src/clinloop_engine/new_clinical.py'
    added.write_text('VALUE = 1\n')
    packet = approved(build(root, base))
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    result = verify(packet, root, base)
    assert result['status'] == 'REVIEW_RECORDS_COMPLETE_NOT_CLINICAL_VALIDATION'
    assert result['clinical_use_authorized'] is False
    added.write_text('VALUE = 2\n')
    with pytest.raises(ReviewError, match='stale'):
        verify(packet, root, base)


@pytest.mark.parametrize('changes', [
    {'reviewer': 'Codex'}, {'reviewer_role': 'ml_researcher'},
    {'reviewed_at': 'invalid'}, {'reviewed_at': '2099-01-01T00:00:00+00:00'},
    {'line_by_line_review_complete': False}, {'sha256': 'forged'},
    {'requires_clinician': False}, {'file': '../private-file'},
])
def test_invalid_human_receipts_and_scope_tampering_fail_closed(draft, changes):
    root, base, _ = draft
    packet = approved(build(root, base))
    packet['files'][0].update(changes)
    with pytest.raises(ReviewError):
        verify(packet, root, base)
