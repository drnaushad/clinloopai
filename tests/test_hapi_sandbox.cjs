'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {HapiSandbox,records,mount,BASE,COHORT,TAG_SYSTEM}=require('../js/hapi-sandbox.js');
const meta={resourceType:'CapabilityStatement',fhirVersion:'4.0.1'};
const tags=[COHORT.tag,'SYNTHETIC_ONLY'].map(code=>({system:TAG_SYSTEM,code}));
const bundle=rows=>({resourceType:'Bundle',type:'searchset',total:rows.length,entry:rows.map(resource=>({resource}))});
const patient=()=>({resourceType:'Patient',id:COHORT.patients[0],meta:{tag:structuredClone(tags)}});
const report=()=>({resourceType:'DiagnosticReport',id:COHORT.reports[0],meta:{tag:structuredClone(tags)},subject:{reference:'Patient/'+COHORT.patients[0]},status:'final',conclusion:'Synthetic follow-up recommendation.'});
const fixture=()=>[bundle([patient()]),bundle([report()])];
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/fhir+json'}});
function setup(responder){const calls=[];const values=[meta,...fixture()];return {calls,client:new HapiSandbox({fetcher:async(url,options)=>{calls.push({url,options});return responder?responder(calls.length,url,options):json(values[calls.length-1]);}})};}
test('only three fixed read requests are made without credentials, caching or redirects',async()=>{
 const s=setup(),result=await s.client.connect(true);assert.equal(result.patients,1);assert.equal(result.reports.length,1);assert.equal(result.clinical_accuracy_established,false);assert.equal(s.calls.length,3);
 for(const [i,{url,options}]of s.calls.entries()){assert.equal(new URL(url).origin,'https://hapi.fhir.org');assert.equal(options.method,'GET');assert.equal(options.credentials,'omit');assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');assert.equal(options.referrerPolicy,'no-referrer');assert(!options.headers.Authorization);if(i){const q=new URL(url).searchParams;assert.equal(q.get('_tag'),TAG_SYSTEM+'|'+COHORT.tag);assert.equal(q.get('_count'),'20');assert.equal([...q].length,2);}}
 assert.equal(s.calls[0].url,BASE+'/metadata');
});
test('confirmation and closed-client boundaries prevent all network calls',async()=>{for(const v of [false,undefined,'true']){const s=setup();await assert.rejects(s.client.connect(v));assert.equal(s.calls.length,0);}const s=setup();s.client.close();await assert.rejects(s.client.connect(true));assert.equal(s.calls.length,0);assert(Object.isFrozen(COHORT.patients));});
test('non-R4 metadata stops before searching patients',async()=>{for(const bad of [{...meta,fhirVersion:'5.0.0'},{}]){const s=setup(()=>json(bad));await assert.rejects(s.client.connect(true));assert.equal(s.calls.length,1);}});
test('foreign or untagged resources and search outcomes fail closed',()=>{
 for(const mutate of [p=>p.entry[0].resource.id='foreign',p=>p.entry[0].resource.meta.tag=[],p=>p.entry[0].resource.meta.tag={},p=>p.entry[0].resource.resourceType='Observation',p=>p.entry[0].search={mode:'outcome'},p=>p.entry.push(p.entry[0]),p=>p.entry=[{}],p=>p.link=[null],p=>p.entry=[],p=>p.type='collection']){const [p,r]=fixture();mutate(p);assert.throws(()=>records(p,r));}
});
test('report IDs, exact patient references, status and source text are checked',()=>{
 for(const mutate of [r=>r.id='foreign',r=>r.subject.reference='Patient/foreign',r=>r.subject.reference='https://evil.test/Patient/'+COHORT.patients[0],r=>r.subject.reference={},r=>delete r.status,r=>r.status='x'.repeat(81),r=>r.conclusion={},r=>r.conclusion='x'.repeat(12001),r=>r.meta.tag.pop()]){const [p,r]=fixture();mutate(r.entry[0].resource);assert.throws(()=>records(p,r));}
});
test('missing conclusions and empty or partial reports never imply normal findings',()=>{
 const [p,r]=fixture();delete r.entry[0].resource.conclusion;assert.match(records(p,r).reports[0].conclusion,/No plain-text/);assert.equal(records(p,bundle([])).reports.length,0);r.link=[{relation:'next',url:'https://evil.test/track'}];assert.equal(records(p,r).partial,true);r.link=[];r.total=4;assert.equal(records(p,r).partial,true);
});
test('pagination, XHTML and attachment URLs are never fetched or exposed',async()=>{
 const [p,r]=fixture();r.link=[{relation:'next',url:'https://evil.test/page'}];r.entry[0].resource.text={div:'<img src="https://evil.test/track">'};r.entry[0].resource.presentedForm=[{url:'https://evil.test/file'}];const s=setup(n=>json([meta,p,r][n-1]));const value=await s.client.connect(true);assert.equal(s.calls.length,3);assert(!JSON.stringify(value).includes('evil.test'));
});
test('malformed, oversized, non-JSON and failed responses cannot become results',async()=>{
 for(const make of [()=>json({},401),()=>new Response('<html>'),()=>new Response('{',{headers:{'Content-Type':'application/json'}}),()=>new Response('x'.repeat(2*1024*1024+1),{headers:{'Content-Type':'application/json'}})]){const s=setup(make);await assert.rejects(s.client.connect(true));assert.equal(s.calls.length,1);}
});
test('disconnect aborts pending work and concurrent connects are rejected',async()=>{
 let release;const s=setup(()=>new Promise(resolve=>{release=resolve;}));const pending=s.client.connect(true);await assert.rejects(s.client.connect(true));s.client.close();assert(s.calls[0].options.signal.aborted);release(json(meta));await assert.rejects(pending);assert.equal(s.calls.length,1);
});
function page(connect=async()=>({...records(...fixture()),fhir_version:'4.0.1'})){
 const events={},elements={},timers=new Map();let seq=0,closed=0,created=0;
 const element=()=>({textContent:'',checked:false,disabled:false,children:[],append(...xs){this.children.push(...xs);},appendChild(x){this.children.push(x);},replaceChildren(){this.children=[];},addEventListener(name,fn){this[name]=fn;}});
 for(const id of ['hapi-connect','hapi-status','hapi-reports','hapi-synthetic','hapi-disconnect'])elements[id]=element();
 mount({document:{getElementById:id=>elements[id],createElement:element,addEventListener:(n,f)=>events[n]=f},window:{addEventListener:(n,f)=>events[n]=f},createClient:()=>{created++;return {connect,close:()=>closed++};},schedule:f=>{timers.set(++seq,f);return seq;},cancel:n=>timers.delete(n)});
 return {elements,events,timers,get closed(){return closed;},get created(){return created;},start:()=>elements['hapi-connect'].click(),confirm:()=>{elements['hapi-synthetic'].checked=true;}};
}
test('UI requires confirmation, renders plain text, clears and reconnects',async()=>{
 const p=page();await p.start();assert.equal(p.created,0);p.confirm();await p.start();assert.match(p.elements['hapi-status'].textContent,/Connected/);assert.equal(p.elements['hapi-reports'].children.length,2);p.elements['hapi-disconnect'].click();assert.equal(p.elements['hapi-reports'].children.length,0);assert.equal(p.closed,1);assert(!p.elements['hapi-connect'].disabled);await p.start();assert.equal(p.created,2);
});
test('late replies after disconnect cannot repopulate the page',async()=>{let release;const p=page(()=>new Promise(r=>release=r));p.confirm();const pending=p.start();p.elements['hapi-disconnect'].click();release(records(...fixture()));await pending;assert.equal(p.elements['hapi-reports'].children.length,0);assert.match(p.elements['hapi-status'].textContent,/Disconnected/);});
test('page exit, restored pages and idle timeout erase reports',async()=>{for(const action of [p=>p.events.pagehide(),p=>p.events.pageshow({persisted:true}),p=>[...p.timers.values()][0]()]){const p=page();p.confirm();await p.start();action(p);assert.equal(p.closed,1);assert.equal(p.elements['hapi-reports'].children.length,0);assert.equal(p.timers.size,0);}});
test('server error details are not shown in the UI',async()=>{const p=page(async()=>{throw Error('DO_NOT_DISPLAY');});p.confirm();await p.start();assert(!p.elements['hapi-status'].textContent.includes('DO_NOT_DISPLAY'));assert.equal(p.elements['hapi-reports'].children.length,0);});
test('HAPI access is on launch page only; callback retains SMART-only policy',()=>{
 const launch=fs.readFileSync('smart/launch.html','utf8'),callback=fs.readFileSync('smart/callback.html','utf8');assert(launch.includes('connect-src https://launch.smarthealthit.org https://hapi.fhir.org;'));assert(!callback.includes('hapi.fhir.org'));assert(!callback.includes('hapi-sandbox.js'));assert(launch.includes('id="launcher"'));assert(launch.includes('id="hapi-synthetic"'));assert(!/<script[^>]*>\s*[^<\s]/.test(launch));
});
