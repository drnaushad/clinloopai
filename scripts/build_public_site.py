"""Package only public web assets for GitHub Pages; never publish the repository root."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_engine_manifest import browser_sources

PAGES = ('index', 'worklist', 'governance', 'imaging', 'patient', 'quality', 'pilot',
         'analyse', 'reports', 'review', 'validation', 'deployment', 'private')
ROOT_FILES = tuple(p + '.html' for p in PAGES) + (
    'CNAME', '.nojekyll', 'config.js', 'version.json', 'manifest.json', 'sw.js',
    'favicon.ico', 'robots.txt', 'sitemap.xml', 'public-models.json')
PUBLIC_DATA = ('cases.json', 'fhir_example_bundle.json', 'radiology_test_bundle.json',
               'validation_status.json', 'deployment_modules.json', 'research_release_status.json',
               'report_review_schema.json', 'engineering_release_status.json', 'safety_release_status.json')
PUBLIC_DOCS = ('docs/reviews/RETURNED_REVIEW_CORRECTIONS_20261027.md',
               'docs/reviews/gmlp-gap-assessment-20261027.json',
               'docs/reviews/EVIDENCE_REVIEW_20261029.md', 'docs/releases/20261030.md',
               'docs/releases/20261102.md', 'docs/releases/20261105.md')
PUBLIC_JWKS = ('epic/jwks.json', 'epic/jwks-prod.json')
ASSET_DIRS = {'css': {'.css'}, 'js': {'.js', '.json'},
              'icons': {'.png', '.svg', '.ico'}, 'smart': {'.html', '.css'},
              'demo/api': {'.json'}, 'demo/examples': {'.json'}}


def validate_public_jwks(path: Path) -> None:
    """Only signature-verification material may enter the public artifact."""
    allowed = {'kty', 'kid', 'alg', 'use', 'key_ops', 'n', 'e', 'crv', 'x', 'y'}

    def unique_object(pairs: list) -> dict:
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError()
            result[name] = value
        return result

    try:
        if path.stat().st_size > 16384:
            raise ValueError()
        # The reviewed bytes are copied verbatim. Reject shadowed properties,
        # rather than validating only the last value selected by json.loads.
        body = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
        if not isinstance(body, dict) or set(body) != {'keys'}:
            raise ValueError()
        keys = body['keys']
        if not isinstance(keys, list) or not 1 <= len(keys) <= 8:
            raise ValueError()
        ids = set()
        for key in keys:
            if not isinstance(key, dict) or not set(key) <= allowed:
                raise ValueError()
            if key.get('use') != 'sig' or key.get('key_ops', ['verify']) != ['verify']:
                raise ValueError()
            kid = key.get('kid')
            if not isinstance(kid, str) or not kid or kid in ids:
                raise ValueError()
            ids.add(kid)
            if key.get('kty') == 'RSA' and key.get('alg') == 'RS384':
                fields = ('n', 'e')
                if {'crv', 'x', 'y'} & set(key):
                    raise ValueError()
            elif key.get('kty') == 'EC' and key.get('alg') == 'ES384' and key.get('crv') == 'P-384':
                fields = ('x', 'y')
                if {'n', 'e'} & set(key):
                    raise ValueError()
            else:
                raise ValueError()
            if any(not isinstance(key.get(field), str) or not key[field] or
                   any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in key[field])
                   for field in fields):
                raise ValueError()
    except (ValueError, TypeError, OSError):
        raise ValueError('Public JWKS must contain only supported public verification keys') from None


def build(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Public artifact output must be a new directory')
    selected = set(ROOT_FILES) | {'data/' + p for p in PUBLIC_DATA} | set(PUBLIC_DOCS) | set(PUBLIC_JWKS)
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=source).decode().split('\0'))
    engine = browser_sources(source)
    if not set(engine['files']) <= tracked:
        raise ValueError('Browser engine source must be tracked')
    if not set(PUBLIC_JWKS) <= tracked:
        raise ValueError('Public JWKS must be tracked')
    bundle_name = 'js/engine_sources.json'
    if (source/bundle_name).exists() or (source/bundle_name).is_symlink():
        raise ValueError('Browser engine bundle must be generated from source, not supplied')
    for directory, extensions in ASSET_DIRS.items():
        base = source/directory
        if not base.is_dir() or base.is_symlink():
            raise ValueError('Required public asset directory is missing or unsafe')
        for path in base.rglob('*'):
            if path.is_symlink():
                raise ValueError('Public assets cannot contain symlinks')
            name = path.relative_to(source).as_posix()
            # Demo API answers are freshly generated from repository synthetic
            # seeds. All other assets must already be tracked source files.
            if path.is_file() and path.suffix in extensions and (name in tracked or directory == 'demo/api'):
                selected.add(path.relative_to(source).as_posix())
    for name in selected:
        path = source/name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('Required public asset is missing or unsafe')
    for name in PUBLIC_JWKS:
        validate_public_jwks(source/name)
    # Validate everything before creating the output. No source files are removed.
    output.mkdir(parents=True)
    hashes = {}
    for name in sorted(selected):
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    bundle_path = output/bundle_name
    bundle_path.write_text(json.dumps(engine, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    hashes[bundle_name] = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    return {'public_files': len(hashes), 'sha256': hashes,
            'scope': 'Static synthetic research preview and browser analysis dependency bundle; no server endpoints, tests, secrets, databases or recovery artifacts.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(Path(__file__).resolve().parents[1], args.output)
    print(json.dumps({'public_files': result['public_files'], 'scope': result['scope']}))


if __name__ == '__main__':
    main()
