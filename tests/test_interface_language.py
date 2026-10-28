"""All menu pages expose the same bilingual controls without translating clinical evidence."""
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
PAGES=['index','worklist','patient','quality','governance','pilot','imaging','analyse','reports','review','private','validation','deployment']
class Controls(HTMLParser):
 def __init__(self,text):
  super().__init__();self.ids={};self.html={};self.feed(text)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='html':self.html=a
  if 'id' in a:self.ids.setdefault(a['id'],[]).append(a)
@pytest.mark.parametrize('page',PAGES)
def test_every_page_has_one_visible_choice_per_language_and_updated_assets(page):
 text=(ROOT/(page+'.html')).read_text();p=Controls(text)
 assert p.html['data-language-options']=='en ko'
 for ident in ['lang-opt-en','lang-opt-ko']:
  assert len(p.ids[ident])==1 and 'hidden' not in p.ids[ident][0]
 assert 'js/interface-copy.js?v=20261028_languages1' in text
 assert 'js/interface-language.js?v=20261028_languages1' in text
 if page in ['review','private']:assert p.html['data-isolated-session']=='true'
@pytest.mark.skipif(not shutil.which('node'),reason='Node required for interface-language checks')
def test_language_runtime_and_source_preservation():
 r=subprocess.run(['node','tests/test_interface_language.cjs'],cwd=ROOT,capture_output=True,text=True,timeout=30)
 assert r.returncode==0,r.stdout+r.stderr
