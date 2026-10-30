"""The public deployment must exclude runtime/private/recovery and untracked content."""
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('public_site', Path(__file__).parents[1]/'scripts/build_public_site.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='Public package source checks require Git')


@pytest.fixture
def source(tmp_path):
    root = tmp_path/'source'
    root.mkdir()
    for name in [*m.ROOT_FILES, *('data/'+p for p in m.PUBLIC_DATA), *m.PUBLIC_DOCS]:
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic public fixture')
    for directory, extensions in m.ASSET_DIRS.items():
        path = root/directory/('asset'+sorted(extensions)[0])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('public fixture')
    subprocess.run(['git','init','-q'],cwd=root,check=True)
    subprocess.run(['git','add','.'],cwd=root,check=True)
    return root


def test_private_runtime_recovery_and_untracked_assets_are_not_deployed(source, tmp_path):
    for name in ['.env','database.sqlite','src/server.py','tests/private.json','data/patients.json',
                 'recovery/source.zip','js/local-secret.js','css/private.css']:
        path = source/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('SYNTHETIC-PRIVATE-MARKER')
    output = tmp_path/'public'
    result = m.build(source, output)
    assert result['public_files'] > 30
    assert all('SYNTHETIC-PRIVATE-MARKER' not in p.read_text() for p in output.rglob('*') if p.is_file())
    assert not (output/'.git').exists()
    assert (output/'validation.html').is_file()
    assert (output/'data/engineering_release_status.json').is_file()


def test_missing_required_asset_fails_before_creating_output(source, tmp_path):
    (source/'index.html').unlink()
    output = tmp_path/'public'
    with pytest.raises(ValueError, match='missing or unsafe'):
        m.build(source,output)
    assert not output.exists()


def test_existing_output_is_preserved_and_not_merged(source, tmp_path):
    output = tmp_path/'public'
    output.mkdir()
    marker = output/'keep.txt'
    marker.write_text('preserve')
    with pytest.raises(ValueError, match='new directory'):
        m.build(source,output)
    assert marker.read_text() == 'preserve'


def test_asset_symlink_cannot_publish_outside_content(source, tmp_path):
    private = tmp_path/'private.js'
    private.write_text('SYNTHETIC-PRIVATE-MARKER')
    (source/'js/leak.js').symlink_to(private)
    with pytest.raises(ValueError, match='symlinks'):
        m.build(source,tmp_path/'public')


def test_required_file_symlink_is_refused(source, tmp_path):
    target = tmp_path/'private.html'
    target.write_text('SYNTHETIC-PRIVATE-MARKER')
    (source/'index.html').unlink()
    (source/'index.html').symlink_to(target)
    with pytest.raises(ValueError, match='missing or unsafe'):
        m.build(source,tmp_path/'public')
