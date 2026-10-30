"""Shared navigation must preserve isolated research and clinical page controls."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node required for workspace shell checks')
def test_workspace_shell_navigation_and_session_isolation():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/test_workspace_shell.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_public_headers_and_assets_are_current_and_generator_is_repeatable():
    """A regeneration must not restore stale controls or publish mixed asset versions."""
    import json
    import re
    from html.parser import HTMLParser
    root = Path(__file__).resolve().parents[1]
    version = json.loads((root/'version.json').read_text())['version']
    asset_version = re.sub(r'[^A-Za-z0-9_]', '_', version)
    result = subprocess.run([__import__('sys').executable, '-B', 'scripts/build_workspace_shell.py', '--check'],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '15 shared headers' in result.stdout
    class Nodes(HTMLParser):
        def __init__(self, text):
            super().__init__(); self.nodes=[]; self.feed(text)
        def handle_starttag(self, tag, attrs):
            self.nodes.append((tag, dict(attrs)))
    for path in [*root.glob('*.html'), *root.glob('smart/*.html')]:
        text=path.read_text(); nodes=Nodes(text).nodes
        headers=[a for t,a in nodes if t=='header' and a.get('data-static-shell')=='true']
        assert len(headers)==1 and headers[0]['data-release-version']==version, path.name
        ids=[a['id'] for t,a in nodes if 'id' in a]
        assert len(ids)==len(set(ids)), path.name
        assert text.index('id="lang-opt-en"') < text.index('id="lang-opt-ko"'), path.name
        for tag,a in nodes:
            url=a.get('src',a.get('href',''))
            if re.match(r'(?:\.\./)?(?:js|css)/|sandbox\.css',url):
                assert url.endswith('?v='+asset_version), (path.name,url)
        if path.parent.name=='smart':
            assert 'js/appnav.js' not in text and 'data-isolated-session="true"' in text
            assert 'connect-src https://launch.smarthealthit.org' in text
            assert not any(tag=='script' and 'src' not in a for tag,a in nodes)
