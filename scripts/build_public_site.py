"""Package only public web assets for GitHub Pages; never publish the repository root."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

PAGES = ('index', 'worklist', 'governance', 'imaging', 'patient', 'quality', 'pilot',
         'analyse', 'reports', 'review', 'validation', 'deployment', 'private')
ROOT_FILES = tuple(p + '.html' for p in PAGES) + (
    'CNAME', '.nojekyll', 'config.js', 'version.json', 'manifest.json', 'sw.js',
    'favicon.ico', 'robots.txt', 'sitemap.xml', 'public-models.json')
PUBLIC_DATA = ('cases.json', 'fhir_example_bundle.json', 'radiology_test_bundle.json',
               'validation_status.json', 'deployment_modules.json', 'research_release_status.json',
               'report_review_schema.json', 'engineering_release_status.json')
PUBLIC_DOCS = ('docs/reviews/RETURNED_REVIEW_CORRECTIONS_20261027.md',
               'docs/reviews/gmlp-gap-assessment-20261027.json',
               'docs/reviews/EVIDENCE_REVIEW_20261029.md', 'docs/releases/20261030.md')
ASSET_DIRS = {'css': {'.css'}, 'js': {'.js', '.json'},
              'icons': {'.png', '.svg', '.ico'}, 'smart': {'.html', '.css'},
              'demo/api': {'.json'}, 'demo/examples': {'.json'}}


def build(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Public artifact output must be a new directory')
    selected = set(ROOT_FILES) | {'data/' + p for p in PUBLIC_DATA} | set(PUBLIC_DOCS)
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=source).decode().split('\0'))
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
    # Validate everything before creating the output. No source files are removed.
    output.mkdir(parents=True)
    hashes = {}
    for name in sorted(selected):
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return {'public_files': len(hashes), 'sha256': hashes,
            'scope': 'Static synthetic research preview; no server code, tests, secrets, databases or recovery artifacts.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(Path(__file__).resolve().parents[1], args.output)
    print(json.dumps({'public_files': result['public_files'], 'scope': result['scope']}))


if __name__ == '__main__':
    main()
