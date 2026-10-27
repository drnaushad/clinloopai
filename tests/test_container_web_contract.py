"""Keep menu destinations and their startup resources available in the shipped web root."""
from pathlib import Path
import json
import re
import shlex
import shutil

ROOT = Path(__file__).resolve().parents[1]


def test_container_web_payload_contains_every_menu_page_and_its_setup(tmp_path):
    """Stage the explicit Docker COPY payload; source-only tests missed an absent review page."""
    web = tmp_path / 'web'
    for line in (ROOT / 'Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '):
            continue
        *sources, target = shlex.split(line)[1:]
        if not target.startswith('./web'):
            continue
        destination = tmp_path / target
        destination.mkdir(parents=True, exist_ok=True)
        for name in sources:
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination / source.name)
    pages = re.findall(r"\{ page: '([^']+)', href:", (ROOT / 'js/appnav.js').read_text())
    assert len(pages) == 13
    for page in pages:
        document = (web / (page + '.html')).read_text()
        assert 'data-static-shell="true"' in document, page
        # Local startup resources must exist; a root page alone can hide a broken feature.
        for asset in re.findall(r'(?:src|href)="((?:js|css|icons)/[^"?#]+)', document):
            assert (web / asset).is_file(), (page, asset)
    assert json.loads((web / 'data/report_review_schema.json').read_text())['type'] == 'object'
    assert json.loads((web / 'data/research_release_status.json').read_text())['clinical_use_authorized'] is False
    assert (web / 'smart/launch.html').is_file()
    assert (web / 'smart/callback.html').is_file()
    assert (web / 'docs/reviews/gmlp-gap-assessment-20261027.json').is_file()
    assert not (web / 'docs/reviews/clinical-ml-20261026.json').exists()
    assert not (web / 'src').exists()
