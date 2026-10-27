'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const CODE='synthetic_gateway_code_'+'x'.repeat(32), KEY='synthetic-provider-secret-not-real';
function page(fetcher){
 const ids=['provider','code','key','model','confirm','check','save','forget','clear','status','providers','key-link','model-link'];
 const el={},events={},win={},timers=[],intervals=[],calls=[];
 for(const id of ids)el[id]={value:'',checked:false,disabled:false,children:[],addEventListener:(n,f)=>events[id+':'+n]=f,replaceChildren(){this.children=[];},append(x){this.children.push(x);}};
 el.provider.value='openai';
 const context={document:{getElementById:id=>el[id],createElement:()=>({}),addEventListener(){}},window:{addEventListener:(n,f)=>win[n]=f},
  location:{origin:'http://127.0.0.1:18127'},AbortController,Date,
  setTimeout:f=>{timers.push(f);return timers.length;},clearTimeout(){},setInterval:f=>intervals.push(f),
  fetch:async(path,opts)=>{calls.push({path,opts});return fetcher?fetcher(path,opts):{ok:true,json:async()=>({providers:[{id:'openai',configured:true,model:'synthetic-text-model'}]})};}};
 vm.runInNewContext(fs.readFileSync(require.resolve('../src/research_setup/setup.js'),'utf8'),context);
 function fill(){el.code.value=CODE;el.key.value=KEY;el.model.value='synthetic-text-model';el.confirm.checked=true;}
 return {el,events,win,calls,fill,context,timers,intervals};
}
test('key setup only sends credentials to the same-origin personal configuration endpoint',async()=>{
 const p=page();p.fill();await p.events['save:click']();
 assert.equal(p.calls.length,2);assert.equal(p.calls[0].path,'/review/configure');
 assert.equal(JSON.parse(p.calls[0].opts.body).api_key,KEY);
 assert.equal(p.calls[0].opts.headers.Authorization,'Bearer '+CODE);
 for(const {path,opts} of p.calls){assert(path.startsWith('/review/'));assert.equal(opts.credentials,'omit');assert.equal(opts.redirect,'error');assert.equal(opts.cache,'no-store');}
 assert.equal(p.el.key.value,'');assert(!p.el.status.textContent.includes(KEY));assert(!JSON.stringify(p.el.providers.children).includes(KEY));
 assert(p.el.status.textContent.includes('No API call or charge'));
});
test('public or nonloopback origin cannot transmit a key',async()=>{
 const p=page();p.fill();p.context.location.origin='https://clinloopai.app';await p.events['save:click']();
 assert.equal(p.calls.length,0);assert.equal(p.el.key.value,'');
});
test('changing provider discards prior key, model and confirmation',()=>{
 const p=page();p.fill();p.el.provider.value='gemini';p.events['provider:change']();
 assert.equal(p.el.key.value,'');assert.equal(p.el.model.value,'');assert.equal(p.el.confirm.checked,false);
 assert(p.el['key-link'].href.startsWith('https://aistudio.google.com/'));assert.equal(p.calls.length,0);
});
test('missing consent, malformed model, and provider key mistaken for gateway code do not send secrets',async()=>{
 for(const field of ['confirm','model','code']){
  const p=page();p.fill();if(field==='confirm')p.el.confirm.checked=false;else p.el[field].value=field==='code'?'sk-'+'x'.repeat(40):'models/unsafe';
  await p.events['save:click']();assert.equal(p.calls.length,0);assert.equal(p.el.key.value,'');
 }
});
test('a failed setup does not restore or reflect secrets',async()=>{
 const p=page(async()=>{throw Error(KEY);});p.fill();await p.events['save:click']();
 assert.equal(p.el.key.value,'');assert(!p.el.status.textContent.includes(KEY));assert(p.el.status.textContent.includes('may already have completed'));
});
test('page exit and BFCache restore clear all credential fields',()=>{
 const p=page();p.fill();p.win.pagehide();assert.equal(p.el.code.value,'');assert.equal(p.el.key.value,'');
 p.fill();p.win.pageshow({persisted:true});assert.equal(p.el.code.value,'');assert.equal(p.el.key.value,'');
});
test('clearing pending setup prevents stale UI confirmation and aborts the request',async()=>{
 let release;const pending=new Promise(r=>release=r);const p=page(()=>pending);p.fill();
 const task=p.events['save:click']();assert.equal(p.el.key.value,'');p.events['clear:click']();
 assert(p.calls[0].opts.signal.aborted);release({ok:true,json:async()=>({})});await task;
 assert(p.el.status.textContent.includes('Form cleared'));assert.equal(p.calls.length,1);
});
test('old timeout cannot abort a newer setup request after form clearing',async()=>{
 let release;const pending=new Promise(r=>release=r);const p=page(()=>pending);p.fill();const first=p.events['save:click']();
 p.events['clear:click']();p.fill();const second=p.events['save:click']();
 p.timers[0]();assert.equal(p.calls[1].opts.signal.aborted,false);
 p.events['clear:click']();release({ok:true,json:async()=>({})});await Promise.all([first,second]);
});
