"""The public deployment must exclude runtime/private/recovery and untracked content."""
import importlib.util
import hashlib
import json
import shutil
import subprocess
import sys
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
    repo = Path(__file__).parents[1]
    manifest = json.loads((repo/'js/engine_manifest.json').read_text())
    shutil.copyfile(repo/'js/engine_manifest.json', root/'js/engine_manifest.json')
    for name in manifest['files']:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo/name, target)
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


def test_packaged_engine_runs_without_the_source_checkout(source, tmp_path):
    """Exercise the deployed dependency closure, not imports from the repository under test."""
    output = tmp_path/'public'
    result = m.build(source, output)
    manifest = json.loads((output/'js/engine_manifest.json').read_text())
    bundle = json.loads((output/manifest['source_bundle']).read_text())
    assert set(bundle['files']) == set(manifest['files'])
    assert result['sha256'][manifest['source_bundle']]
    runtime = tmp_path/'runtime'
    for name, text in bundle['files'].items():
        assert hashlib.sha256(text.encode()).hexdigest() == manifest['sha256'][name]
        target = runtime/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    assert not (output/'src').exists()
    assert not any('api.py' in name or 'loop_store.py' in name for name in bundle['files'])
    repo = Path(__file__).parents[1]
    examples = [json.loads((repo/'demo/examples'/f'{name}.json').read_text()) for name in
                ('lung-nodule', 'positive-fit', 'warfarin-inr')]
    code = '''import json,sys
sys.path.insert(0,sys.argv[1])
for m in ('fastapi','requests','httpx','pandas','torch','pydicom'):
    sys.modules[m]=None
from src.clinloop_engine.browser_analyse import analyse_bundle
for bundle, expected in zip(json.load(sys.stdin), [('R003','open'),('R017','open'),('R007','closed')]):
    result=analyse_bundle(bundle,'2026-09-01T00:00:00')
    assert expected in [(d['rule_id'],d['status']) for d in result['detections']], expected
print('three packaged browser examples passed')
'''
    done = subprocess.run([sys.executable, '-I', '-c', code, str(runtime)], cwd=runtime,
                          input=json.dumps(examples), text=True, capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize('damage', ['stale_source', 'extra_manifest_file', 'untracked_source',
                                   'supplied_bundle', 'source_symlink'])
def test_engine_packaging_fails_closed_before_writing(source, tmp_path, damage):
    manifest_path = source/'js/engine_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    name = 'src/clinloop_engine/browser_analyse.py'
    if damage == 'stale_source':
        with (source/name).open('a') as f:
            f.write('\n# stale code\n')
    elif damage == 'extra_manifest_file':
        manifest['files'].append('src/clinloop_engine/api.py')
        manifest_path.write_text(json.dumps(manifest))
    elif damage == 'untracked_source':
        subprocess.run(['git','rm','--cached',name], cwd=source, check=True, capture_output=True)
    elif damage == 'supplied_bundle':
        (source/'js/engine_sources.json').write_text('SYNTHETIC-PRIVATE-MARKER')
    else:
        target = tmp_path/'private.py'
        target.write_text((source/name).read_text())
        (source/name).unlink()
        (source/name).symlink_to(target)
    output = tmp_path/'public'
    with pytest.raises(ValueError):
        m.build(source,output)
    assert not output.exists()


def test_bundle_cli_uses_the_container_web_manifest_layout(source):
    scripts = source/'scripts'
    scripts.mkdir()
    shutil.copyfile(Path(__file__).parents[1]/'scripts/build_engine_manifest.py', scripts/'build_engine_manifest.py')
    web = source/'web/js'
    web.mkdir(parents=True)
    shutil.move(source/'js/engine_manifest.json', web/'engine_manifest.json')
    done = subprocess.run([sys.executable, 'scripts/build_engine_manifest.py', '--manifest',
                           'web/js/engine_manifest.json', '--bundle-output', 'web/js/engine_sources.json'],
                          cwd=source, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    manifest = json.loads((web/'engine_manifest.json').read_text())
    sources = json.loads((web/'engine_sources.json').read_text())
    assert set(sources['files']) == set(manifest['files'])
