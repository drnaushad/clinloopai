"""Check first-paint structure and display-only startup without accessing patient data."""
from pathlib import Path
import shutil
import subprocess
from collections import Counter
from html.parser import HTMLParser
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.skipif(not shutil.which('node'), reason='Node required for startup regression checks')
def test_display_start_and_noninterrupting_updates():
    result = subprocess.run(['node', 'tests/test_display_start.cjs'], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_shared_headers_are_current_and_idempotent():
    result = subprocess.run([__import__('sys').executable, 'scripts/build_workspace_shell.py', '--check'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = Counter()
        self.shells = 0
        self.current = 0
        self.body_class = ''
        self.shell_links = 0
        self.in_shell = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids[a['id']] += 1
        if tag == 'body':
            self.body_class = a.get('class', '')
        if tag == 'header' and 'clinloop-shell' in a.get('class', '').split():
            self.shells += 1
            self.in_shell = True
        if self.in_shell and tag == 'a' and 'app-nav-link' in a.get('class', '').split():
            self.shell_links += 1
            self.current += a.get('aria-current') == 'page'
    def handle_endtag(self, tag):
        if tag == 'header':
            self.in_shell = False


@pytest.mark.parametrize('page', ['index', 'worklist', 'patient', 'quality', 'governance', 'pilot', 'imaging', 'analyse', 'reports', 'review', 'private', 'validation', 'deployment'])
def test_navigation_exists_before_javascript_without_duplicate_controls(page):
    html = (ROOT / (page + '.html')).read_text()
    parsed = Structure()
    parsed.feed(html)
    assert parsed.shells == 1 and parsed.shell_links == 13 and parsed.current == 1
    assert 'clinloop-page' in parsed.body_class.split()
    assert parsed.ids['clinloop-page-picker'] == 1
    for ident in ['btn-lang', 'theme-opt-light', 'theme-opt-dark', 'lang-opt-ko', 'lang-opt-en']:
        assert parsed.ids[ident] <= 1
    assert 'fonts.googleapis.com' not in html and 'fonts.gstatic.com' not in html
    assert html.index('js/display-start.js') < html.index('<body')
    assert html.index('data-static-shell="true"') < html.index('id="clinloop-page-picker"')
    assert parsed.ids['workspace' if page in {'private', 'review'} else 'clinloop-workspace'] == 1


class MenuGroups(HTMLParser):
    def __init__(self):
        super().__init__()
        self.groups = []
        self.options = []
        self.current_group = None
        self.in_option_group = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'clinloop-nav-group' in a.get('class', '').split():
            self.current_group = []
            self.groups.append(self.current_group)
        if tag == 'a' and 'app-nav-link' in a.get('class', '').split():
            self.current_group.append(a['href'])
        if tag == 'optgroup':
            self.options.append([])
            self.in_option_group = True
        if tag == 'option' and self.in_option_group:
            self.options[-1].append(a['value'])
    def handle_endtag(self, tag):
        if tag == 'optgroup':
            self.in_option_group = False


@pytest.mark.parametrize('page', ['index', 'worklist', 'patient', 'quality', 'governance', 'pilot', 'imaging', 'analyse', 'reports', 'review', 'private', 'validation', 'deployment'])
def test_desktop_and_phone_menus_offer_identical_groups_and_destinations(page):
    parsed = MenuGroups()
    parsed.feed((ROOT / (page + '.html')).read_text())
    normalize = lambda href: '/' if href == './' else '/' + href
    assert len(parsed.groups) == len(parsed.options) == 3
    assert [[normalize(href) for href in group] for group in parsed.groups] == parsed.options
    assert [len(group) for group in parsed.groups] == [8, 3, 2]
