'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const html=fs.readFileSync('analyse.html','utf8');
const coordinator=html.slice(html.indexOf('  function invalidateResults()'),html.indexOf('\n  function applyRole()',html.indexOf('  function invalidateResults()')));
const events=html.slice(html.indexOf("  $('bundle-file').addEventListener('change'"),html.indexOf("  $('connect-form').addEventListener"));
function setup(fetcher=async()=>({ok:true,text:async()=>'{"resourceType":"Bundle"}'})){
 const handlers={},nodes={},calls=[];let status='';
 const node=id=>nodes[id]||(nodes[id]={id,value:'synthetic',textContent:'OLD RESULT',disabled:false,dataset:{example:id},files:[],replaceChildren(){this.textContent='';},addEventListener:(name,fn)=>{handlers[id+':'+name]=fn;}});
 const examples=[node('example-a'),node('example-b')];const controls=[...examples,...['bundle-file','paste-text','paste-kind','paste-title','paste-date','eval-time'].map(node)];
 const c={$:node,document:{querySelectorAll:s=>s==='.example'?examples:controls},MAX_BYTES:5*1024*1024,IN_BROWSER:true,fetch:fetcher,parseBundle:text=>{try{return JSON.parse(text);}catch{throw Error('Invalid JSON');}},pasteBundle:()=>({resourceType:'Bundle'}),setRun:text=>{status=text;},t:()=>({preparing:'Preparing',tooBig:'Too big',notJson:'Invalid JSON',exampleFailed:'Example unavailable',srcExample:'example',srcFile:'file',srcPaste:'paste',sourceChanged:'Source changed',analyseFailed:'Failed'}),applyRole(){},analyseHere:async(bundle,source)=>{calls.push({bundle,source:source()});node('results').textContent='NEW RESULT';},sendToServer:async()=>{throw Error('Unexpected server request');}};
 vm.createContext(c);vm.runInContext('let running=false;let last={draw(){}};'+coordinator+events+'\nthis.inspect=()=>({running,last});',c);
 return {c,node,handlers,controls,calls,get status(){return status;}};
}
test('example loading takes the busy lock before fetch and rejects overlapping selections',async()=>{
 let resolve,fetches=0;const pending=new Promise(r=>{resolve=r;});const s=setup(async()=>{fetches++;return pending;});
 const first=s.handlers['example-a:click']();assert(s.c.inspect().running);assert(s.controls.every(x=>x.disabled));assert.equal(s.node('results').textContent,'');
 await s.handlers['example-b:click']();assert.equal(fetches,1);
 resolve({ok:true,text:async()=>'{"resourceType":"Bundle"}'});await first;assert.equal(s.calls.length,1);assert.equal(s.calls[0].source,'example: OLD RESULT');assert(s.controls.every(x=>!x.disabled));
});
test('a failed replacement file clears old output and last result before reading',async()=>{
 const s=setup();let reject;const pending=new Promise((_r,j)=>{reject=j;});s.node('bundle-file').files=[{size:20,text:()=>pending}];
 const task=s.handlers['bundle-file:change']({target:s.node('bundle-file')});assert.equal(s.node('results').textContent,'');assert.equal(s.c.inspect().last,null);assert(s.c.inspect().running);
 reject(Error('SYNTHETIC SOURCE MUST NOT APPEAR'));await task;assert.equal(s.status,'Invalid JSON');assert.equal(s.node('results').textContent,'');assert.equal(s.calls.length,0);assert(!s.c.inspect().running);
});
test('editing report inputs or evaluation time invalidates all previous output',()=>{
 for(const id of ['eval-time','paste-kind','paste-title','paste-date','paste-text']){const s=setup();s.handlers[id+':input']();assert.equal(s.node('results').textContent,'');assert.equal(s.c.inspect().last,null);assert.equal(s.status,'Source changed');}
});
test('oversize files are rejected without reading, retaining or processing their source',async()=>{
 const s=setup();s.node('bundle-file').files=[{size:6*1024*1024,text:()=>{throw Error('Must not read');}}];await s.handlers['bundle-file:change']({target:s.node('bundle-file')});assert.equal(s.status,'Too big');assert.equal(s.node('results').textContent,'');assert.equal(s.calls.length,0);assert(s.controls.every(x=>!x.disabled));
});
