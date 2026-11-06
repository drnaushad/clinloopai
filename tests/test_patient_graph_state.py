"""Exercise actual page loader against delayed and failed patient requests."""
from pathlib import Path
import shutil
import subprocess
import pytest


@pytest.mark.skipif(not shutil.which('node'),reason='Node required for page loader regression')
def test_graph_loader_preserves_display_settings_and_never_shows_stale_patient():
    result=subprocess.run(['node','-'],input=r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const html=fs.readFileSync('patient.html','utf8');
const code=html.slice(html.indexOf('  let graphLoadVersion = 0;'),html.indexOf('  function plansHtml('));
const elements={};
for(const id of ['patient','when','stats','graph-wrap','legend','obligations','detail']){
  elements[id]={value:'',hidden:false,handlers:{},addEventListener(t,fn){this.handlers[t]=fn;}};
}
elements.patient.value='SYN-A';
const state={graph:null,sel:null},urls=[],pending=[];
const ctx={state,$:id=>elements[id],lang:'ko',URLSearchParams,
  location:{search:'?lang=ko&theme=dark&extra=preserve'},
  document:{documentElement:{getAttribute:()=> 'dark'}},
  history:{replaceState:(_,__,url)=>urls.push(url)},
  api:path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject})),
  t:()=>({working:'working',empty:'empty'}),signedIn:()=> 'signed',
  setStatus:()=>{},render:()=>{elements['graph-wrap'].hidden=false;}};
vm.createContext(ctx);vm.runInContext(code,ctx);
(async()=>{
  const first=ctx.load();
  assert.equal(elements['graph-wrap'].hidden,true);
  pending.shift().resolve({nodes:[{id:'a'}],warnings:[]});await first;
  assert.equal(state.graph.nodes[0].id,'a');
  const query=new URLSearchParams(urls.at(-1));
  assert.equal(query.get('lang'),'ko');assert.equal(query.get('theme'),'dark');
  assert.equal(query.get('extra'),'preserve');assert.equal(query.get('patient'),'SYN-A');
  elements.patient.value='SYN-B';elements.patient.handlers.input();
  assert.equal(state.graph,null);assert.equal(elements['graph-wrap'].hidden,true);
  const slow=ctx.load();
  elements.patient.value='SYN-C';elements.patient.handlers.change();
  const latest=ctx.load();
  pending[1].resolve({nodes:[{id:'c'}],warnings:[]});await latest;
  pending[0].resolve({nodes:[{id:'b'}],warnings:[]});await slow;
  assert.equal(state.graph.nodes[0].id,'c');assert.equal(urls.length,2);
  pending.length=0;const failed=ctx.load();pending[0].reject(new Error('Unavailable'));await failed;
  assert.equal(state.graph,null);assert.equal(elements['graph-wrap'].hidden,true);
})().catch(e=>{console.error(e);process.exitCode=1;});
''',text=True,capture_output=True,timeout=20,cwd=Path(__file__).resolve().parents[1])
    assert result.returncode==0,result.stdout+result.stderr
