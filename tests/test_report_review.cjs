'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {Workspace,localAddress}=require('../js/private-workspace.js');
globalThis.ClinLoopPrivate={localAddress};
const {TYPES,SYSTEM,validText,validate,validateFile,Research}=require('../js/report-review.js');
const TEXT='SYNTHETIC: No effusion. A nodule is present. Recommend CT in 6 months.';
const REVIEW={findings:[{quote:'A nodule is present.',assertion:'present',follow_up_quote:'Recommend CT in 6 months.',deadline_quote:'6 months'}],missing_context:[]};
const CODE='synthetic_gateway_code_'+'x'.repeat(32);
const ok=x=>({ok:true,status:200,json:async()=>x});
test('all six text report categories are accepted without claiming image support',()=>{
  for(const type of TYPES)assert.equal(validText(TEXT,type),TEXT);
  for(const [text,type]of [['','laboratory'],['한'.repeat(2500),'laboratory'],[TEXT,'dicom']])assert.throws(()=>validText(text,type));
});
test('exact evidence includes source character positions and never closes an obligation',()=>{
  const result=validate(REVIEW,TEXT);assert(result.human_review_required);
  const f=result.findings[0];assert.equal(TEXT.slice(f.source_start,f.source_end),f.quote);
  assert(!('closed' in result));
});
test('invented quotes, unrelated dates and non-schema fields fail the whole response',()=>{
  for(const change of [{quote:'Cancer is confirmed.'},{deadline_quote:'No effusion'},{follow_up_quote:'Book surgery.'},{assertion:'normal'},{extra:true}]){
    const r=structuredClone(REVIEW);Object.assign(r.findings[0],change);assert.throws(()=>validate(r,TEXT));
  }
  for(const r of [null,[],{findings:[]},{...REVIEW,missing_context:['x'.repeat(301)]}])assert.throws(()=>validate(r,TEXT));
});
test('negated, uncertain and historical assertions remain visible, not reclassified as present',()=>{
  for(const assertion of ['negated','uncertain','historical']){
    const r=structuredClone(REVIEW);r.findings[0].assertion=assertion;
    assert.equal(validate(r,TEXT).findings[0].assertion,assertion);
  }
});
test('empty findings remain explicitly subject to human review',()=>assert(validate({findings:[],missing_context:[]},TEXT).human_review_required));
test('text uploads reject unsupported files and excessive lengths before reading',()=>{
  validateFile('synthetic.TXT',6000);
  for(const args of [['report.pdf',200],['image.jpg',200],['report.txt',6001],['report.txt',0]])assert.throws(()=>validateFile(...args));
});
function research(handler){const calls=[];const r=new Research(async(url,options)=>{calls.push({url,options});return handler?handler(url,options):ok(url.endsWith('/status')?{mode:'synthetic-research-only',provider:'openai',configured:true,model:'synthetic-test'}:{review:REVIEW,provider:'openai',model:'synthetic-test'});});return {r,calls};}
test('research requires loopback gateway, access code and consent before transmission',async()=>{
  for(const args of [['http://127.0.0.1:18127',CODE,false],['https://api.openai.com',CODE,true],['http://localhost:18127','sk-an-api-key',true],['http://localhost:18127','sk-proj-'+'x'.repeat(100),true]]){
    const {r,calls}=research();await assert.rejects(r.connect(...args));assert.equal(calls.length,0);
  }
});
test('research calls only the selected loopback gateway with no cookies or redirect fallback',async()=>{
  const {r,calls}=research();await r.connect('http://127.0.0.1:18127',CODE,true);await r.run(TEXT,'radiology-text',true);
  assert.equal(calls.length,2);
  for(const c of calls){assert(c.url.startsWith('http://127.0.0.1:18127/'));assert.equal(c.options.credentials,'omit');assert.equal(c.options.redirect,'error');assert.equal(c.options.cache,'no-store');}
  const body=JSON.parse(calls[1].options.body);assert(body.synthetic_only&&body.external_api_allowed);assert(!('api_key' in body));
});
test('research aborts and clears its access code; late output cannot restore a session',async()=>{
  let release;const promise=new Promise(r=>{release=r;});const {r}=research(url=>url.endsWith('/status')?ok({mode:'synthetic-research-only',provider:'openai',configured:true,model:'synthetic'}):promise);
  await r.connect('http://localhost:18127',CODE,true);const run=r.run(TEXT,'radiology-text',true);r.clear();release(ok({review:REVIEW}));
  await assert.rejects(run);assert.equal(r.token,'');assert.equal(r.address,'');
});
test('local structured review sends original text only to an inspected local model',async()=>{
  const calls=[],schema=JSON.parse(fs.readFileSync(require.resolve('../data/report_review_schema.json'),'utf8'));
  const w=new Workspace(async(url,options)=>{calls.push({url,options});const p=new URL(url).pathname;
    return ok(p==='/api/tags'?{models:[{name:'synthetic:1b'}]}:p==='/api/show'?{details:{family:'test'},model_info:{'general.architecture':'test','test.context_length':16384},capabilities:['completion']}:
      {model:'synthetic:1b',done:true,done_reason:'stop',response:JSON.stringify(REVIEW)});});
  await w.connect('http://localhost:11434',true);const raw=await w.run('synthetic:1b',TEXT,{schema,system:SYSTEM});validate(JSON.parse(raw),TEXT);
  assert.equal(calls.length,3);for(const c of calls)assert.equal(new URL(c.url).origin,'http://localhost:11434');
  const body=JSON.parse(calls.at(-1).options.body);assert.deepEqual(body.format,schema);assert.equal(body.prompt,TEXT);assert.equal(body.options.temperature,0);
});
function page({localRun=async()=>JSON.stringify(REVIEW),researchRun=async()=>validate(REVIEW,TEXT),localConnect=async()=>['synthetic'],researchConnect=async()=> 'synthetic-api',schemaFetch=async()=>ok({type:'object'})}={}){
  const ids=['mode','provider','provider-destination','provider-consent','local-options','research-options','connect','disconnect','status','model','report','report-file','analyze','local-address','research-address','gateway-code','local-confirm','research-confirm','report-type','complete-confirm','result','sample','clear'];
  const el={},events={},windowEvents={},calls=[];
  for(const id of ids)el[id]={value:'',checked:false,children:[],files:[],addEventListener:(n,f)=>{events[id+':'+n]=f;},replaceChildren(...xs){this.children=xs;},append(...xs){this.children.push(...xs);}};
  el.mode.value='local';el.provider.value='openai';el['local-address'].value='http://127.0.0.1:11434';el['research-address'].value='http://127.0.0.1:18127';el['report-type'].value='radiology-text';
  const api=require('../js/report-review.js');
  const context={document:{getElementById:id=>el[id],createElement:()=>({children:[],append(...xs){this.children.push(...xs);}}),addEventListener(){}},
    Option:function(text,value){this.text=text;this.value=value;},fetch:schemaFetch,setInterval(){},Date,TextDecoder,
    window:{fetch:async()=>ok({type:'object'}),addEventListener:(n,f)=>{windowEvents[n]=f;},
      ClinLoopPrivate:{Workspace:class{clear(v){calls.push(['localClear',v]);}async connect(){calls.push(['localConnect']);return localConnect();}async run(){calls.push(['localRun']);return localRun();}}},
      ClinLoopReportReview:{...api,Research:class{clear(){calls.push(['researchClear']);}async connect(){calls.push(['researchConnect']);return researchConnect();}async run(){calls.push(['researchRun']);return researchRun();}}}}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../js/report-review-page.js'),'utf8'),context);
  return{el,events,windowEvents,calls};
}
test('default hospital pathway uses local models and does not call research transport',async()=>{
  const p=page();p.el['local-confirm'].checked=true;await p.events['connect:click']();
  p.el.report.value=TEXT;p.el['complete-confirm'].checked=true;await p.events['analyze:click']();
  assert(p.calls.some(x=>x[0]==='localRun'));assert(!p.calls.some(x=>x[0]==='researchRun'||x[0]==='researchConnect'));
});
test('local connection failures explain device and browser requirements without provider credentials',async()=>{
 const p=page({localConnect:async()=>{throw new Error('SENSITIVE_SENTINEL');}});
 p.el['local-confirm'].checked=true;await p.events['connect:click']();
 assert(p.el.status.textContent.includes('local Ollama'));
 assert(p.el.status.textContent.includes('local-network access'));
 assert(p.el.status.textContent.includes('https://clinloopai.app'));
 assert(!/access code|provider configuration|SENSITIVE_SENTINEL/.test(p.el.status.textContent));
 assert.equal(p.el.analyze.disabled,true);assert(!p.calls.some(c=>c[0].endsWith('Run')));
});
test('research connection failures name the selected provider and clear the gateway code',async()=>{
 const p=page({researchConnect:async()=>{throw new Error('SENSITIVE_SENTINEL');}});
 p.el.mode.value='research';p.el.provider.value='anthropic';p.el['gateway-code'].value=CODE;
 await p.events['connect:click']();
 assert(p.el.status.textContent.includes('Anthropic (Claude) research gateway'));
 assert(p.el.status.textContent.includes('gateway access code'));
 assert(!p.el.status.textContent.includes('SENSITIVE_SENTINEL'));assert.equal(p.el['gateway-code'].value,'');
 assert.equal(p.el.analyze.disabled,true);
});
test('missing review schema is reported as setup failure before connecting a model',async()=>{
 const p=page({schemaFetch:async()=>{throw new Error('SENSITIVE_SENTINEL');}});await p.events['connect:click']();
 assert(p.el.status.textContent.includes('setup could not be loaded'));
 assert(!p.calls.some(c=>c[0]==='localConnect'||c[0]==='researchConnect'));
 assert(!p.el.status.textContent.includes('SENSITIVE_SENTINEL'));
});
test('changing pathways clears source, result and gateway code before the new connection',()=>{
  const p=page();p.el.report.value=TEXT;p.el['gateway-code'].value=CODE;p.el.mode.value='research';p.events['mode:change']();
  assert.equal(p.el.report.value,'');assert.equal(p.el['gateway-code'].value,'');assert.equal(p.el.result.textContent,'No review yet.');
  assert.equal(p.el.analyze.disabled,true);
});
test('incomplete report confirmation prevents inference',async()=>{
  const p=page();await p.events['connect:click']();p.el.report.value=TEXT;await p.events['analyze:click']();
  assert(!p.calls.some(x=>x[0].endsWith('Run')));assert(p.el.status.textContent.includes('complete synthetic report'));
});
test('disconnect blocks stale local output from appearing',async()=>{
  let release;const pending=new Promise(r=>{release=r;});const p=page({localRun:()=>pending});await p.events['connect:click']();
  p.el.report.value=TEXT;p.el['complete-confirm'].checked=true;const task=p.events['analyze:click']();p.events['disconnect:click']();release(JSON.stringify(REVIEW));await task;
  assert.equal(p.el.result.textContent,'No review yet.');assert.equal(p.el.report.value,'');
});
test('edited source invalidates prior output and completeness confirmation',()=>{
  const p=page();p.el['complete-confirm'].checked=true;p.events['report:input']();
  assert.equal(p.el['complete-confirm'].checked,false);assert.equal(p.el.result.textContent,'Source changed. Review again.');
});
test('page exit and browser cache restoration clear session data',()=>{
  const p=page();p.el.report.value=TEXT;p.windowEvents.pagehide();assert.equal(p.el.report.value,'');
  p.el.report.value=TEXT;p.windowEvents.pageshow({persisted:true});assert.equal(p.el.report.value,'');
});
test('all three research providers are explicitly selected and sent to the local gateway',async()=>{
  for(const provider of ['openai','anthropic','gemini']){
    const {r,calls}=research(url=>ok(url.endsWith('/status')?{mode:'synthetic-research-only',providers:[{id:provider,configured:true,model:'synthetic-'+provider}]}:{provider,model:'synthetic-'+provider,review:REVIEW}));
    await r.connect('http://localhost:18127',CODE,true,provider);await r.run(TEXT,'radiology-text',true);
    assert.equal(JSON.parse(calls[1].options.body).provider,provider);assert.equal(r.provider,provider);
    for(const c of calls)assert.equal(new URL(c.url).origin,'http://localhost:18127');
  }
});
test('unconfigured providers and unknown selections receive no report; no fallback',async()=>{
  const {r,calls}=research();await assert.rejects(r.connect('http://localhost:18127',CODE,true,'anthropic'));
  assert.equal(calls.length,1);assert.equal(r.token,'');
  await assert.rejects(r.connect('http://localhost:18127',CODE,true,'other'));assert.equal(calls.length,1);
});
test('a response from another provider or model is rejected',async()=>{
  for(const wrong of [{provider:'anthropic',model:'synthetic-test'},{provider:'openai',model:'different-model'}]){
    const {r}=research(url=>ok(url.endsWith('/status')?{mode:'synthetic-research-only',provider:'openai',configured:true,model:'synthetic-test'}:{review:REVIEW,...wrong}));
    await r.connect('http://localhost:18127',CODE,true);await assert.rejects(r.run(TEXT,'radiology-text',true));
  }
});
test('Gemini and Anthropic keys are rejected as mistaken gateway access codes',async()=>{
  for(const key of ['AIza'+'x'.repeat(40),'sk-ant-'+'x'.repeat(80)]){
    const {r,calls}=research();await assert.rejects(r.connect('http://localhost:18127',key,true));assert.equal(calls.length,0);
  }
});
test('changing provider clears report and access code and updates named consent',()=>{
  const p=page();p.el.mode.value='research';p.el.provider.value='anthropic';p.el.report.value=TEXT;p.el['gateway-code'].value=CODE;
  p.el['research-confirm'].checked=true;p.events['provider:change']();
  assert.equal(p.el.report.value,'');assert.equal(p.el['gateway-code'].value,'');assert.equal(p.el['research-confirm'].checked,false);
  assert.equal(p.el['provider-consent'].textContent,'Anthropic (Claude)');assert.equal(p.el['provider-destination'].textContent,'Anthropic (Claude)');
});
test('existing OpenAI-only gateways remain usable without an unknown provider field',async()=>{
  const {r,calls}=research();await r.connect('http://localhost:18127',CODE,true,'openai');await r.run(TEXT,'radiology-text',true);
  assert.equal(r.legacy,true);assert.equal(r.provider,'openai');assert(!('provider' in JSON.parse(calls[1].options.body)));
});

test('disconnect while schema loads cannot reconnect a cleared session',async()=>{
  let release;const pending=new Promise(r=>release=r);const p=page({schemaFetch:()=>pending});
  const task=p.events['connect:click']();p.events['disconnect:click']();release(ok({type:'object'}));await task;
  assert(!p.calls.some(c=>c[0]==='localConnect'||c[0]==='researchConnect'));assert(p.el.analyze.disabled);
});
test('changing pathway while schema loads cannot initiate a different connection',async()=>{
  let release;const p=page({schemaFetch:()=>new Promise(r=>release=r)});
  const task=p.events['connect:click']();p.el.mode.value='research';p.events['mode:change']();release(ok({type:'object'}));await task;
  assert(!p.calls.some(c=>c[0]==='researchConnect'));assert(p.el.analyze.disabled);
});
test('pending file load clears old results and prevents analysis until the complete file is loaded',async()=>{
  let release;const p=page();await p.events['connect:click']();p.el.report.value=TEXT;p.el.result.textContent='OLD RESULT';p.el['complete-confirm'].checked=true;
  p.el['report-file'].files=[{name:'synthetic.txt',size:TEXT.length,arrayBuffer:()=>new Promise(r=>release=r)}];
  const task=p.events['report-file:change']();assert.equal(p.el.report.value,'');assert(p.el.analyze.disabled);assert(!p.el.result.textContent.includes('OLD RESULT'));
  await p.events['analyze:click']();assert(!p.calls.some(c=>c[0]==='localRun'));
  release(new TextEncoder().encode(TEXT).buffer);await task;assert.equal(p.el.report.value,TEXT);assert(!p.el.analyze.disabled);assert.equal(p.el['complete-confirm'].checked,false);
});
test('a source edit during inference cannot display an answer for the earlier report',async()=>{
  let release;const p=page({localRun:()=>new Promise(r=>release=r)});await p.events['connect:click']();p.el.report.value=TEXT;p.el['complete-confirm'].checked=true;
  const task=p.events['analyze:click']();p.el.report.value='SYNTHETIC revised source.';p.events['report:input']();release(JSON.stringify(REVIEW));await task;
  assert.equal(p.el.result.textContent,'Source changed. Review again.');assert(!p.el.status.textContent.includes('matching passed'));
});
test('changing the selected model invalidates the previous result',()=>{
  const p=page();p.el.result.textContent='OLD MODEL RESULT';p.events['model:change']();assert.equal(p.el.result.textContent,'Source changed. Review again.');
});
test('source context exposes nearby negation and repeated-quote ambiguity without reclassifying the model',()=>{
  const text='SYNTHETIC: No pleural effusion. Previously pleural effusion resolved.';
  const r=validate({findings:[{quote:'pleural effusion',assertion:'negated',follow_up_quote:'',deadline_quote:''}],missing_context:[]},text);
  assert(r.findings[0].source_context.includes('No pleural effusion'));
  assert.equal(r.findings[0].source_occurrences,2);assert.equal(r.findings[0].assertion,'negated');
});

test('editing a reviewed report clears the old success status as well as its findings',()=>{
 const p=page();p.el.status.textContent='Source matching passed.';p.events['report:input']();assert(!p.el.status.textContent.includes('matching passed'));assert(p.el.status.textContent.includes('Review again'));
});
test('observed synthetic negation reversal is rejected, not relabelled',()=>{
 const text='No pleural effusion is identified.';
 assert.throws(()=>validate({findings:[{quote:text,assertion:'present',follow_up_quote:'',deadline_quote:''}],missing_context:[]},text),/negation conflict/);
 const result=validate({findings:[{quote:text,assertion:'negated',follow_up_quote:'',deadline_quote:''}],missing_context:[]},text);
 assert.equal(result.findings[0].assertion,'negated');
});
test('unlinked recommendation stays visible without inventing a finding or deadline link',()=>{
 const text='A nodule is present. Repeat chest CT in 6 months.';
 const review=validate({findings:[{quote:'A nodule is present.',assertion:'present',follow_up_quote:'',deadline_quote:''}],missing_context:['Missing prior study','Missing prior study']},text);
 assert.deepEqual(review.unlinked_source_sentences,['Repeat chest CT in 6 months.']);assert.equal(review.findings[0].follow_up_quote,'');assert.equal(review.findings[0].deadline_quote,'');assert.equal(review.missing_context.length,1);
});
test('linked recommendation is not duplicated; negated recommendations remain human-review candidates',()=>{
 assert.deepEqual(validate(REVIEW,TEXT).unlinked_source_sentences,[]);
 const text='No follow-up is needed.';assert.deepEqual(validate({findings:[],missing_context:[]},text).unlinked_source_sentences,[text]);
});
test('a quote that drops the preceding negation is not accepted as present',()=>{
 const text='SYNTHETIC CT: No pleural effusion is identified.';
 assert.throws(()=>validate({findings:[{quote:'pleural effusion',assertion:'present',follow_up_quote:'',deadline_quote:''}],missing_context:[]},text),/negation conflict/);
});
