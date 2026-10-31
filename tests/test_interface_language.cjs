'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const copy=require('../js/interface-copy.js'),ui=require('../js/interface-language.js');
class El {
 constructor(text=''){this.textContent=text;this.attrs={};this.events={};}
 setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k]??null;}removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,v){this.events[k]=v;}
}
function env({isolated=true,legacy=false}={}){
 const en=new El('English'),ko=new El('한국어'),label=new El('Report review'),source=new El('Report review\n원문 <script>ignored</script>'),input={value:'SYNTHETIC original 6 mm'},code={value:'synthetic-private-code'};
 label.setAttribute('data-ui-copy','');const link=new El();link.setAttribute('href','private');
 const observers=[],assigned=[],saved=[],html={lang:'en',getAttribute:k=>k==='data-isolated-session'?(isolated?'true':null):k==='data-workspace'?'review':null};
 const nodes=[label];
 const old=legacy?{click(){html.lang=html.lang==='en'?'ko':'en';}}:null;
 const doc={readyState:'complete',documentElement:html,getElementById:k=>({'lang-opt-en':en,'lang-opt-ko':ko,'btn-lang':old})[k]||null,
  querySelectorAll:s=>s==='[data-ui-copy]'?nodes.filter(e=>e.getAttribute('data-ui-copy')!==null):s==='[data-ui-placeholder]'?[]:[link]};
 const win={URLSearchParams,location:{search:'?lang=en',pathname:'/review',hash:'#source'},history:{state:null,replaceState:(a,b,c)=>assigned.push(c)},MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}}};
 Object.defineProperty(win,'localStorage',{get(){if(isolated)throw Error('Isolated language accessed storage');return {setItem:(k,v)=>saved.push([k,v])};}});
 for(const k of ['fetch','sessionStorage'])Object.defineProperty(win,k,{get(){throw Error('Language accessed '+k);}});
 ui.mount(doc,win);return {doc,win,en,ko,label,source,input,code,nodes,observers,assigned,saved};
}
test('the complete catalogue contains static labels, statuses and compatibility errors',()=>{
 assert(Object.keys(copy).length>=400);
 for(const text of ['Report review','Personal model workspace','Plan ClinLoop for your setting','No response yet.','Session cleared.'])assert(/[가-힣]/.test(ui.translate(text,'ko')));
 assert.equal(ui.translate('Original SOURCE response 원문','ko'),'Original SOURCE response 원문');
});
test('numeric templates preserve values and model IDs',()=>{
 assert.equal(ui.translate('Saved: medgemma:27b','ko'),'저장된 결과: medgemma:27b');
 assert.equal(ui.translate('25 synthetic patients; 27 resources; 40 events','ko'),'합성 환자 25명; 리소스 27건; 이벤트 40건');
 assert.equal(ui.translate('6000 / 6000 UTF-8 bytes','ko'),'6000 / 6000 UTF-8 바이트');
});
test('isolated switching uses no storage, requests, credentials or source nodes',()=>{
 const e=env();const original=e.source.textContent;e.ko.events.click();
 assert.equal(e.doc.documentElement.lang,'ko');assert.equal(e.label.textContent,'보고서 검토');
 assert.equal(e.source.textContent,original);assert.equal(e.input.value,'SYNTHETIC original 6 mm');assert.equal(e.code.value,'synthetic-private-code');
 assert.equal(e.ko.attrs['aria-pressed'],'true');assert.equal(e.en.attrs['aria-pressed'],'false');
 assert.equal(e.assigned.at(-1),'/review?lang=ko#source');
 e.en.events.click();assert.equal(e.label.textContent,'Report review');assert.equal(e.source.textContent,original);
});
test('late status updates translate now and restore their original text later',()=>{
 const e=env();e.ko.events.click();ui.set(e.label,'Source matching passed. Clinical interpretation still requires human review.');
 assert(/[가-힣]/.test(e.label.textContent));e.en.events.click();assert.equal(e.label.textContent,'Source matching passed. Clinical interpretation still requires human review.');
});
test('source output replaces a marked placeholder without later being translated or overwritten',()=>{
 const e=env();ui.set(e.label,'No response yet.');ui.source(e.label,'No response yet.\n실제 원문');
 e.ko.events.click();assert.equal(e.label.textContent,'No response yet.\n실제 원문');assert.equal(e.label.getAttribute('data-ui-copy'),null);
});
test('a rendering container drops stale empty-state copy before adding results',()=>{
 const e=env();ui.set(e.label,'No review yet.');ui.reset(e.label);e.label.textContent='SYNTHETIC quote 6 mm';
 e.ko.events.click();assert.equal(e.label.textContent,'SYNTHETIC quote 6 mm');
});
test('the legacy translator remains the authority on clinical pages',()=>{
 const e=env({isolated:false,legacy:true});e.ko.events.click();assert.equal(e.doc.documentElement.lang,'ko');assert.deepEqual(e.saved,[]);
 e.en.events.click();assert.equal(e.doc.documentElement.lang,'en');
});
test('navigation only carries validated language to known pages and safe local anchors',()=>{
 assert.equal(ui.navigationHref('private','ko'),'private?lang=ko');
 assert.equal(ui.navigationHref('validation#research-release','ko'),'validation?lang=ko#research-release');
 assert.equal(ui.navigationHref('review?lang=ko','en'),'review?lang=en');
 for(const value of ['https://foreign.example/review','//foreign.example','review?token=secret','../private','review#patient=private',null])assert.equal(ui.navigationHref(value,'ko'),null);
});

test('theme and language follow only known page links without leaking unrelated query values',()=>{
 assert.equal(ui.navigationHref('review?lang=en&theme=light','ko','dark'),'review?lang=ko&theme=dark');
 assert.equal(ui.navigationHref('/validation#engineering-release','en','light'),'/validation?lang=en&theme=light#engineering-release');
 assert.equal(ui.navigationHref('smart/launch.html','ko','dark'),'smart/launch.html?lang=ko&theme=dark');
 for(const href of ['review?lang=en&theme=dark&token=secret','review?theme=dark&patient=SYNTHETIC','/smart/callback.html?code=secret','//foreign.example/review']) assert.equal(ui.navigationHref(href,'ko','dark'),null);
});
test('synthetic connection and evidence notices translate counts without changing report source',()=>{
 for(const text of ['753 synthetic cases; 118 exact rule-set mismatches.','23 mismatches share broad action groups in the old harness; that does not establish clinical equivalence.','Strict reference bounds conditional on a matching rule; missed obligations excluded.','Connected to HAPI FHIR R4. 11 synthetic patients verified; 4 source reports received.','2 synthetic diagnostic reports received.','Connection verification does not measure clinical accuracy.']) {
  const ko=ui.translate(text,'ko');assert(/[가-힣]/.test(ko),text);assert.equal(ui.translate(text,'en'),text);
  assert.deepEqual(ko.match(/\d+/g),text.match(/\d+/g));
 }
});

test('tooltips, accessible labels and placeholders restore originals without changing values',()=>{
 const node=new El('SYNTHETIC source 원문');node.value='UNMODIFIED credential';
 node.setAttribute('data-ui-attributes','title aria-label placeholder value');
 node.setAttribute('title','wrong captured translation');node.setAttribute('data-ui-en-title','Light theme');
 node.setAttribute('aria-label','Case queue');node.setAttribute('placeholder','Use a fictional report without personal identifiers.');
 const doc={documentElement:{lang:'ko'},querySelectorAll:()=>[node]};
 ui.renderAttributes(doc);assert.equal(node.attrs.title,'밝은 테마');assert.equal(node.attrs['aria-label'],'사례 목록');assert(/[가-힣]/.test(node.attrs.placeholder));
 assert.equal(node.textContent,'SYNTHETIC source 원문');assert.equal(node.value,'UNMODIFIED credential');
 doc.documentElement.lang='en';ui.renderAttributes(doc);assert.equal(node.attrs.title,'Light theme');assert.equal(node.attrs['aria-label'],'Case queue');assert(!/[가-힣]/.test(node.attrs.placeholder));
});
test('app-owned catalogue metadata translates separately from the unmodified report text',()=>{
 for(const title of ['췌장 MRI f/u','요추 MRI','뇌 CT']) {
  const en=ui.display(title,'en'),ko=ui.display(title,'ko');assert(!/[가-힣]/.test(en));assert(/[가-힣]/.test(ko));
 }
 const e=env();const report='원문: f/u 불필요. Synthetic <script>sample</script>';ui.source(e.source,report);
 e.ko.events.click();e.en.events.click();assert.equal(e.source.textContent,report);
});
test('fixed panel copy and singular deadlines have Korean translations',()=>{
 for(const text of ['Hypothetical scenario (illustration only)','Data protection: what is built and what is not','Fast-Forward Clinical Time:','Global Health Informatics Standards Grounding','1 day','1 hour','35 Days','unknown','male','female','unassigned','Load fictional sample'])assert(/[가-힣]/.test(ui.translate(text,'ko')),text);
});

test('specific dynamic status templates localize their prose rather than matching a generic separator',()=>{
 for(const text of ['Best model: synthetic · Generating...','Sample patient message preview opened; nothing was sent · Case: SC-01','✅ synthetic · 3ms · On-Premise ✓']) {
  const ko=ui.translate(text,'ko');assert(/[가-힣]/.test(ko),text);assert(ko.includes('synthetic')||ko.includes('SC-01'));
 }
});
