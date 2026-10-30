"""Render shared navigation before first paint; no clinical content or session data is read.

Run after editing appnav.js labels: python scripts/build_workspace_shell.py.
Use --check in CI to reject a stale or inconsistent generated header.
"""
from __future__ import annotations

import argparse
import html
import json
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_VERSION = json.loads((ROOT / 'version.json').read_text())['version']
VERSION = re.sub(r'[^A-Za-z0-9_]', '_', APP_VERSION)
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Spans(HTMLParser):
    """Locate original elements without reserializing forms, scripts or report examples."""
    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.lines = [0] + [m.end() for m in re.finditer('\n', text)]
        self.nodes: list[dict] = []
        self.stack: list[dict] = []
        self.feed(text)

    def position(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        node = dict(tag=tag, attrs=dict(attrs), start=start,
                    opening=start + len(self.get_starttag_text()), end=start + len(self.get_starttag_text()))
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                self.stack[index]['closing'] = self.position()
                self.stack[index]['end'] = self.text.index('>', self.position()) + 1
                del self.stack[index:]
                break

    def find(self, *, cls=None, ident=None, tag=None, within=None):
        for node in self.nodes:
            if within and not (within['start'] <= node['start'] < within['end']):
                continue
            attrs = node['attrs']
            if cls and cls not in attrs.get('class', '').split():
                continue
            if ident and attrs.get('id') != ident:
                continue
            if tag and node['tag'] != tag:
                continue
            return node
        return None

    def raw(self, node) -> str:
        assert node is not None
        return self.text[node['start']:node['end']]


def pages() -> list[dict]:
    source = (ROOT / 'js/appnav.js').read_text()
    entries = re.findall(r"\{ page: '([^']+)', href: '([^']+)', en: '([^']+)', ko: '([^']+)' \}", source)
    assert len(entries) == 13, 'Expected all thirteen menu destinations.'
    return [dict(zip(('page', 'href', 'en', 'ko'), entry)) for entry in entries]


def appearance() -> str:
    return ('<div class="appearance-controls" role="group" aria-label="Appearance">'
            '<button type="button" aria-pressed="true"><span data-nav-language="en">Light</span><span data-nav-language="ko">라이트</span></button>'
            '<button type="button" aria-pressed="false"><span data-nav-language="en">Dark</span><span data-nav-language="ko">다크</span></button></div>')


def languages() -> str:
    return ('<div class="prominent-lang-pill" role="group" aria-label="Language">'
            '<button type="button" id="lang-opt-en" data-language="en" aria-pressed="true">English</button>'
            '<button type="button" id="lang-opt-ko" data-language="ko" aria-pressed="false">한국어</button></div>')


def shell(text: str, name: str, entries: list[dict]) -> str:
    parser = Spans(text)
    if name == 'index':
        brand = parser.raw(parser.find(cls='brand-section'))
        controls = (parser.raw(parser.find(cls='theme-segmented-control'))
                    + '<div class="prominent-lang-pill" role="group" aria-label="Language">'
                    + parser.raw(parser.find(ident='lang-opt-en'))
                    + parser.raw(parser.find(ident='lang-opt-ko')) + '</div>')
    else:
        brand = '<a class="clinloop-shell-brand" href="./"><img src="icons/logo.svg" alt="" width="32" height="32"><span>ClinLoop AI</span></a>'
        button = parser.find(ident='btn-lang')
        controls = appearance()
        if button:
            legacy = re.sub(r'<button\b', '<button hidden data-legacy-language="true"', parser.raw(button), count=1)
            # Re-rendering must not accumulate duplicate presentation attributes.
            legacy = re.sub(r'(?: hidden data-legacy-language="true"){2,}', ' hidden data-legacy-language="true"', legacy)
            controls = '<div role="group" data-shell-account="">' + controls + legacy + languages() + '</div>'
        else:
            controls += languages()
    links = [[], [], []]
    groups = [[], [], []]
    for index, entry in enumerate(entries):
        route = '/' if entry['page'] == 'index' else '/' + entry['page']
        current = ' aria-current="page"' if entry['page'] == name else ''
        en, ko = html.escape(entry['en']), html.escape(entry['ko'])
        group = 0 if index < 8 else 1 if index < 11 else 2
        links[group].append(f'<a class="app-nav-link" href="{entry["href"]}" data-label-en="{en}" data-label-ko="{ko}"{current}>'
                     f'<span data-nav-language="en">{en}</span><span data-nav-language="ko">{ko}</span></a>')
        selected = ' selected' if entry['page'] == name else ''
        groups[group].append(f'<option value="{route}"{selected}>{en}</option>')
    grouped = ''.join(f'<optgroup label="{label}">{"".join(options)}</optgroup>' for label, options in zip(
        ['Clinical workspace', 'Research', 'Evidence and setup'], groups))
    desktop = ''.join(
        f'<div class="clinloop-nav-group" role="group" aria-labelledby="nav-group-{i}">'
        f'<span class="clinloop-nav-group-label" id="nav-group-{i}">'
        f'<span data-nav-language="en">{en}</span><span data-nav-language="ko">{ko}</span></span>'
        f'<div class="clinloop-nav-group-links">{"".join(items)}</div></div>'
        for i, (en, ko, items) in enumerate(zip(
            ['Clinical workspace', 'Research', 'Evidence and setup'],
            ['진료 작업 공간', '연구', '검증 및 설정'], links)))
    workflows = [
        ('review', 'Review report text', '보고서 텍스트 검토',
         'Load TXT in your browser or import PDF, scans, photos and DICOM through your personal gateway. Check the complete source before model review (6000 UTF-8 bytes).',
         'TXT는 브라우저에서, PDF·스캔·사진·DICOM은 개인 게이트웨이에서 불러옵니다. 모델 검토(UTF-8 6000바이트) 전에 전체 원문을 확인하세요.'),
        ('analyse', 'Try follow-up detection', '후속 조치 탐지 체험',
         'Start with a synthetic example, a FHIR .json bundle or radiology/pathology report text. The browser demo needs no model connection.',
         '합성 예제, FHIR .json 번들 또는 영상·병리 보고서 텍스트로 시작하세요. 브라우저 데모는 모델 연결이 필요 없습니다.'),
        ('imaging', 'Explore document and imaging workflows', '문서 및 영상 작업 흐름 살펴보기',
         'DICOM image pixels, medical images and waveforms need a separate validated imaging workflow. The public Imaging page shows local-installation demonstrations.',
         'DICOM 화소, 의료영상 및 파형에는 별도로 검증된 영상 작업 흐름이 필요합니다. 공개 영상 화면은 로컬 설치 기능을 시연합니다.'),
        ('validation', 'Check evidence and limitations', '검증 근거 및 한계 확인',
         'See measured results, supported tasks and pending reviews before choosing a workflow or comparing models. Universal clinical accuracy is not established.',
         '작업 흐름 선택이나 모델 비교 전에 측정 결과, 지원 작업 및 검토 현황을 확인하세요. 모든 임상 작업에 대한 정확도는 입증되지 않았습니다.'),
    ]
    guide = ('<details class="clinloop-workflow-guide"><summary>'
             '<span data-nav-language="en">Choose a workflow</span><span data-nav-language="ko">작업 흐름 선택</span>'
             '</summary><div class="clinloop-workflow-grid">' + ''.join(
                 f'<div><a href="{href}"><span data-nav-language="en">{en}</span><span data-nav-language="ko">{ko}</span></a>'
                 f'<p><span data-nav-language="en">{desc}</span><span data-nav-language="ko">{translation}</span></p></div>'
                 for href, en, ko, desc, translation in workflows) + '</div></details>')
    nav = 'workspace-nav' if name in {'private', 'review', 'smart-launch', 'smart-callback'} else 'app-nav'
    if name.startswith('smart-'):
        grouped = '<option value="" selected>Test EMR connection</option>' + grouped
    return ('<!-- clinloop-shell:start -->\n<header class="clinloop-shell" data-static-shell="true" data-release-version="' + APP_VERSION + '">'
            '<div class="clinloop-shell-top">' + brand + '<div class="clinloop-shell-controls" role="group" aria-label="Display and account">' + controls + '</div></div>'
            f'<nav class="{nav} clinloop-shell-links" aria-label="ClinLoop pages">' + desktop + '</nav>'
            '<div class="clinloop-shell-mobile"><label for="clinloop-page-picker">Go to page</label>'
            '<select id="clinloop-page-picker">' + grouped + '</select></div>' + guide +
            '<aside class="research-release-notice" role="note">'
            '<span data-nav-language="en">Research preview · synthetic data only. Independent review and clinical validation pending. '
            '<a href="validation#engineering-release">Review status</a></span>'
            '<span data-nav-language="ko">연구 미리보기 · 합성 데이터 전용. 독립 검토 및 임상 검증 대기 중. '
            '<a href="validation#engineering-release">검토 현황</a></span>'
            '<small class="release-version">' + APP_VERSION + '</small>'
            '</aside></header>\n<!-- clinloop-shell:end -->')


def render(text: str, name: str, entries: list[dict]) -> str:
    markup = shell(text, name, entries)
    if '<!-- clinloop-shell:start -->' in text:
        return re.sub(r'<!-- clinloop-shell:start -->.*?<!-- clinloop-shell:end -->', lambda _: markup, text, count=1, flags=re.S)
    parser = Spans(text)
    edits = []
    if name == 'index':
        header = parser.find(cls='app-header--pro')
        actions = parser.find(cls='header-actions', within=header)
        tools = parser.raw(actions)
        for cls in ['theme-segmented-control', 'prominent-lang-pill']:
            tools = tools.replace(parser.raw(parser.find(cls=cls, within=header)), '')
        edits.append((header['start'], header['end'], markup + '\n<div class="app-header--pro cockpit-tools">' + tools + '</div>'))
    elif name in {'private', 'review'}:
        header = parser.find(cls='workspace-header')
        edits.append((header['start'], header['end'], markup))
    else:
        nav = parser.find(cls='app-nav')
        edits.append((nav['start'], nav['end'], ''))
        button = parser.find(ident='btn-lang')
        if button:
            owner = next(node for node in parser.nodes if node['tag'] == 'nav' and node['start'] < button['start'] < node['end'])
            edits.append((owner['start'], owner['end'], ''))
        body = parser.find(tag='body')
        edits.append((body['opening'], body['opening'], '\n' + markup))
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    text = re.sub(r'<body([^>]*)>', lambda m: '<body' + (
        re.sub(r'class="([^"]*)"', lambda c: 'class="clinloop-page ' + c[1] + '"', m[1])
        if 'class=' in m[1] else ' class="clinloop-page"' + m[1]) + '>', text, count=1)
    attributes = f' data-workspace="{name}" data-language-options="en ko"'
    if name in {'private', 'review'}:
        attributes += ' data-isolated-session="true"'
    text = re.sub(r'<html([^>]*)>', lambda m: '<html' + m[1] + attributes + '>', text, count=1)
    text = text.replace('<head>', '<head>\n<script src="js/display-start.js?v=' + VERSION + '"></script>', 1)
    text = re.sub(r'<link\b[^>]*href="https://fonts\.(?:googleapis|gstatic)\.com[^>]*>\s*', '', text)
    text = text.replace('20261026_menus1', VERSION).replace('js/appearance-controls.js?v=20261023_1', 'js/appearance-controls.js?v=' + VERSION)
    text = text.replace('js/appnav.js?v=2026-10-26.menus1', 'js/appnav.js?v=' + APP_VERSION)
    # The page title already names its workspace; its brand is now in the common header.
    text = text.replace('</a>ClinLoop <span data-i18n="title">', '</a><span data-i18n="title">')
    if name in {'deployment', 'validation'}:
        boundary = text.index('<!-- clinloop-shell:end -->') + len('<!-- clinloop-shell:end -->')
        text = text[:boundary] + '\n<main class="clinloop-content" id="clinloop-workspace" tabindex="-1">' + text[boundary:]
        text = text.replace('</body>', '</main>\n</body>', 1)
    if 'class="skip-link' not in text:
        target = 'clinloop-workspace'
        if name == 'index':
            text = text.replace('<main class="cockpit-workspace"', '<main id="clinloop-workspace" class="cockpit-workspace"', 1)
            if 'id="clinloop-workspace"' not in text:
                text = text.replace('class="cockpit-workspace"', 'id="clinloop-workspace" tabindex="-1" class="cockpit-workspace"', 1)
        elif name not in {'deployment', 'validation'}:
            text = text.replace('<div class="wrap">', '<div class="wrap" id="clinloop-workspace" role="main" tabindex="-1">', 1)
            if 'id="clinloop-workspace"' not in text:
                text = text.replace('<main>', '<main id="clinloop-workspace" tabindex="-1">', 1)
        text = re.sub(r'(<body[^>]*>)', r'\1<a class="skip-link shell-skip" href="#' + target + '">Skip to workspace</a>', text, count=1)
    return text


def release_assets(text: str, name: str, prefix: str = '') -> str:
    """Keep every public entry point on one release without rewriting source content."""
    titles = {entry['page']: entry['en'] + ' — ClinLoop AI' for entry in pages()}
    titles.update({'index': 'ClinLoop AI | Closed-Loop Follow-up of Clinical Results',
                   'smart/launch': 'Test EMR connections — ClinLoop AI',
                   'smart/callback': 'SMART sandbox reports — ClinLoop AI'})
    text = re.sub(r'<title\b[^>]*>.*?</title>',
                  '<title data-ui-copy>' + html.escape(titles[name]) + '</title>', text, count=1, flags=re.S)
    text = re.sub(r'((?:src|href)="(?:\.\./)?(?:js|css)/[^"?]+)(?:\?v=[^" ]+)?"',
                  lambda m: m[1] + '?v=' + VERSION + '"', text)
    if name.startswith('smart/'):
        text = re.sub(r'(href="sandbox\.css)(?:\?v=[^"]+)?"',
                      lambda m: m[1] + '?v=' + VERSION + '"', text)
    parser = Spans(text)
    additions = []
    if not any(n['attrs'].get('http-equiv', '').lower() == 'cache-control' for n in parser.nodes):
        additions.append('<meta http-equiv="Cache-Control" content="no-cache">')
    for rel, href, extra in [('icon', 'icons/logo.svg', ' type="image/svg+xml"'),
                             ('manifest', 'manifest.json', ''),
                             ('apple-touch-icon', 'icons/icon-192.png', '')]:
        if not any(n['tag'] == 'link' and n['attrs'].get('rel') == rel for n in parser.nodes):
            additions.append(f'<link rel="{rel}" href="{prefix}{href}"{extra}>')
    if not any(n['attrs'].get('name') == 'theme-color' for n in parser.nodes):
        additions.append('<meta name="theme-color" content="#0e7490">')
    if not any(n['tag'] == 'link' and n['attrs'].get('rel') == 'canonical' for n in parser.nodes):
        route = '' if name == 'index' else name + ('.html' if name.startswith('smart/') else '')
        additions.append(f'<link rel="canonical" href="https://clinloopai.app/{route}">')
    if additions:
        text = text.replace('</head>', '\n' + '\n'.join(additions) + '\n</head>', 1)
    return text


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('--check', action='store_true')
    args = command.parse_args()
    changed = []
    entries = pages()
    for entry in entries:
        path = ROOT / (entry['page'] + '.html')
        old = path.read_text()
        new = release_assets(render(old, entry['page'], entries), entry['page'])
        if new != old:
            changed.append(path.name)
            if not args.check:
                path.write_text(new)
    for name in ('launch', 'callback'):
        path = ROOT / 'smart' / (name + '.html')
        old = path.read_text()
        markup = shell(old, 'smart-' + name, entries)
        # Nested sandbox pages share presentation without loading appnav/session code.
        markup = re.sub(r'href="(?:\./)?([^"?#]*)',
                        lambda m: 'href="/' + m[1], markup)
        markup = markup.replace('src="icons/', 'src="../icons/')
        new = re.sub(r'<!-- clinloop-shell:start -->.*?<!-- clinloop-shell:end -->',
                     lambda _: markup, old, count=1, flags=re.S)
        new = release_assets(new, 'smart/' + name, prefix='../')
        if new != old:
            changed.append('smart/' + path.name)
            if not args.check:
                path.write_text(new)
    if args.check and changed:
        print('Shared headers need regeneration: ' + ', '.join(changed))
        return 1
    print('Checked' if args.check else 'Rendered', len(entries) + 2, 'shared headers and release assets.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
