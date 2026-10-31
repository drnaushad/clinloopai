'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { target, decorate, mount, localizeNotices, localizeSessionStatus } = require('../js/language-controls.js');
function button(id, text) {
  return { id, textContent: text, attrs: {},
    setAttribute(k,v) { this.attrs[k]=v; }, removeAttribute(k) { delete this.attrs[k]; } };
}
test('a language toggle shows the flag for its destination, independent of current language', () => {
  const b=button('btn-lang','한국어'); decorate(b,'en');
  assert.equal(b.attrs['data-language'],'ko'); assert.equal(b.attrs['aria-label'],'Korean'); assert.equal(b.textContent,'Korean');
  assert.equal(b.attrs.lang,'en'); assert.equal(b.attrs['aria-pressed'],undefined);
  b.textContent='English'; decorate(b,'ko');
  assert.equal(b.attrs['data-language'],'en'); assert.equal(b.attrs['aria-label'],'영어');
});
test('header and dock agree on language and selected state after translation replaces text', () => {
  for (const [id,lang] of [['lang-opt-en','en'],['lang-opt-ko','ko'],['dock-btn-en','en'],['dock-btn-ko','ko']]) {
    const b=button(id,'translation text'); decorate(b,'en');
    assert.equal(target(b),lang); assert.equal(b.attrs['aria-pressed'],String(lang==='en'));
    b.textContent='new translation'; decorate(b,'ko');
    assert.equal(b.attrs['data-language'],lang); assert.equal(b.attrs['aria-pressed'],String(lang==='ko'));
  }
});
test('unrecognized buttons and languages receive no invented flag', () => {
  assert.equal(target(button('btn-lang','Deutsch')),null);
  assert.equal(target(button('patient-action','English')),null);
});
test('mount follows text and html language changes without observing its own attributes', () => {
  const observations=[], observers=[], buttons=[button('lang-opt-en','English'),button('btn-lang','한국어')];
  class Observer { constructor(fn) { this.update=fn; observers.push(this); } observe(el,options) { observations.push({el,options}); } }
  const doc={readyState:'complete',documentElement:{lang:'en'},querySelectorAll:selector=>selector==='[data-demo-copy]'?[]:buttons};
  mount(doc,Observer);
  assert.equal(buttons[0].attrs['aria-pressed'],'true');
  doc.documentElement.lang='ko-KR'; buttons[1].textContent='English'; observers[1].update();
  assert.equal(buttons[0].attrs['aria-pressed'],'false'); assert.equal(buttons[1].attrs['data-language'],'en');
  assert.equal(observations[0].options.attributes,undefined);
  assert.deepEqual(observations.at(-1).options.attributeFilter,['lang']);
});
test('initialization waits for the page and still decorates controls without observer support', () => {
  let start; const b=button('dock-btn-ko','한국어');
  const doc={readyState:'loading',documentElement:{lang:'ko'},querySelectorAll:selector=>selector==='[data-demo-copy]'?[]:[b],addEventListener:(name,fn)=>{assert.equal(name,'DOMContentLoaded');start=fn;}};
  mount(doc,null); assert.deepEqual(b.attrs,{}); start(); assert.equal(b.attrs['aria-pressed'],'true');
});

test('all shared notices switch languages without changing source evidence or link children', () => {
  const keys=['snapshot','unavailable','controls','analyse','serverDemo','loading','loadFailed'];
  const nodes=keys.map(key=>({textContent:'',getAttribute:()=>key}));
  const source={textContent:'합성 원문 보고서 — preserve source exactly'};
  const doc={documentElement:{lang:'en'},querySelectorAll:selector=>{
    assert.equal(selector,'[data-demo-copy]');return nodes;
  }};
  localizeNotices(doc);
  for(const n of nodes){assert(n.textContent.length>0);assert(!/[가-힣]/.test(n.textContent));}
  const english=nodes.map(n=>n.textContent);
  doc.documentElement.lang='ko-KR';localizeNotices(doc);
  for(const n of nodes)assert(/[가-힣]/.test(n.textContent));
  doc.documentElement.lang='en';localizeNotices(doc);
  assert.deepEqual(nodes.map(n=>n.textContent),english);
  assert.equal(source.textContent,'합성 원문 보고서 — preserve source exactly');
});
test('the existing html-language observer updates notices without reloading the page', () => {
  const observers=[], note={textContent:'',getAttribute:()=> 'snapshot'};
  class Observer {constructor(fn){this.update=fn;observers.push(this);}observe(){}}
  const doc={readyState:'complete',documentElement:{lang:'en'},querySelectorAll:s=>s==='[data-demo-copy]'?[note]:[]};
  mount(doc,Observer);assert.match(note.textContent,/Synthetic snapshot/);
  doc.documentElement.lang='ko';observers.at(-1).update();assert.match(note.textContent,/합성 스냅샷/);
  doc.documentElement.lang='en';observers.at(-1).update();assert(!/[가-힣]/.test(note.textContent));
});

test('sign-in status follows the selected language while preserving username, role and timestamp', () => {
  const status={textContent:'Signed in as practice.clinician (clinician). · as of 2026-10-20 12:22',classList:{contains:()=>false}};
  const doc={documentElement:{lang:'ko'},getElementById:id=>id==='status'?status:null};
  localizeSessionStatus(doc);assert.match(status.textContent,/님으로 로그인했습니다/);assert.match(status.textContent,/기준 2026-10-20 12:22/);
  doc.documentElement.lang='en';localizeSessionStatus(doc);
  assert.equal(status.textContent,'Signed in as practice.clinician (clinician). · as of 2026-10-20 12:22');
  status.textContent='연결 오류: source text';localizeSessionStatus(doc);assert.equal(status.textContent,'연결 오류: source text');
});


test('cockpit summary uses the selected language for an unfamiliar synthetic case and treats text as text', () => {
  const vm = require('node:vm');
  const fs = require('node:fs');
  const source = fs.readFileSync('js/app.js', 'utf8');
  const nodes = Object.fromEntries(['summary-patient-name','summary-patient-meta','summary-q1-finding',
    'summary-q2-problem','summary-q3-action','summary-neg-risk'].map(id=>[id,{textContent:''}]));
  for (const node of Object.values(nodes)) Object.defineProperty(node,'innerHTML',{set(){throw Error('Summary text interpreted as markup');}});
  const context={window:{},location:{hostname:"clinloopai.app",protocol:"https:"},document:{addEventListener(){},getElementById:id=>nodes[id]||null}};
  vm.runInNewContext(source+'\nthis.renderSummary = ClinLoopApp.prototype.updateSummaryView;',context);
  const app={currentLang:'en',closedOverrides:new Set(),currentCase:{scenario_id:'SYNTHETIC-UNFAMILIAR',
    patient_id:'SYNTHETIC-P',patient_age:60,patient_sex:'F',scenario_name:'<img src=x onerror=alert(1)>',missing_followup:'Synthetic follow-up'}};
  context.renderSummary.call(app);
  for (const node of Object.values(nodes)) assert(!/[가-힣]/.test(node.textContent));
  assert.equal(nodes['summary-q1-finding'].textContent,'<img src=x onerror=alert(1)>');
  assert.equal(nodes['summary-neg-risk'].textContent,'Not estimated');
  app.currentCase.scenario_id='SC-0062';context.renderSummary.call(app);
  assert.match(nodes['summary-q3-action'].textContent,/risk-based/);
  assert.doesNotMatch(nodes['summary-q3-action'].textContent,/Mandatory/);
});

test('late notices translate in Korean and repeated observer delivery does not rewrite unchanged status',()=>{
 const observers=[],nodes=[];let writes=0,text='Signed in as practice.clinician (clinician).';
 const status={get textContent(){return text;},set textContent(v){writes++;text=v;},classList:{contains:()=>false}};
 const doc={readyState:'complete',body:{},documentElement:{lang:'ko'},getElementById:id=>id==='status'?status:null,querySelectorAll:s=>s==='[data-demo-copy]'?nodes:[]};
 class Observer{constructor(fn){observers.push(fn);}observe(){}}
 mount(doc,Observer);assert.match(text,/의료진/);const note={textContent:'Synthetic snapshot',getAttribute:()=> 'snapshot'};nodes.push(note);
 const target={nodeType:1,closest:()=>true};observers.at(-1)([{target,addedNodes:[]}]);assert.match(note.textContent,/합성 스냅샷/);
 const before=writes;for(let i=0;i<5;i++)observers.at(-1)([{target,addedNodes:[]}]);assert.equal(writes,before);
 doc.documentElement.lang='en';observers[1]();assert.equal(text,'Signed in as practice.clinician (clinician).');
});
test('message-language choice labels do not change its independent selected state',()=>{
 const b=button('btn-lang-en','English');b.attrs['aria-pressed']='false';decorate(b,'ko');
 assert.equal(b.textContent,'영어');assert.equal(b.attrs['aria-pressed'],'false');decorate(b,'en');assert.equal(b.textContent,'English');
});

test('privacy demonstration samples and replacement labels follow language but edited input stays intact',()=>{
 const vm=require('node:vm'),fs=require('node:fs'),nodes={};
 function node(){return {value:'',textContent:'',events:{},addEventListener(k,fn){this.events[k]=fn;},dispatchEvent(e){this.events[e.type]?.();}};}
 for(const id of ['phi-firewall-input','phi-firewall-output','phi-count-badge','firewall-sample-btn'])nodes[id]=node();
 const context={window:{},location:{hostname:'clinloopai.app',protocol:'https:'},document:{addEventListener(){},getElementById:id=>nodes[id]||null},Event,setTimeout:fn=>{fn();return 0;},clearTimeout(){}};
 vm.runInNewContext(fs.readFileSync('js/app.js','utf8')+'\nthis.initPrivacy=ClinLoopApp.prototype.initPrivacyFirewall;',context);
 const app={currentLang:'en'};context.initPrivacy.call(app);nodes['firewall-sample-btn'].events.click();
 assert(!/[가-힣]/.test(nodes['phi-firewall-input'].value));assert.match(nodes['phi-firewall-output'].textContent,/National ID removed/);
 app.currentLang='ko';app.renderPrivacyLocale();assert.match(nodes['phi-firewall-input'].value,/가상환자/);assert.match(nodes['phi-firewall-output'].textContent,/주민번호 삭제/);
 const source='SYNTHETIC edited original 원문 2026-01-01';nodes['phi-firewall-input'].value=source;
 app.currentLang='en';app.renderPrivacyLocale();assert.equal(nodes['phi-firewall-input'].value,source);assert.match(nodes['phi-count-badge'].textContent,/Date/);assert(!/[가-힣]/.test(nodes['phi-count-badge'].textContent));
});
test('graph event titles localize known and unfamiliar types',()=>{
 const vm=require('node:vm'),fs=require('node:fs'),context={};vm.runInNewContext(fs.readFileSync('js/hypergraph.js','utf8')+'\nthis.label=HypergraphVisualizer.prototype._formatEventType;',context);
 for(const type of ['lab_result','radiology_report','missing_obligation','scheduling_action','synthetic_unfamiliar_type']) {
  const labels=context.label(type);assert(/[가-힣]/.test(labels.ko));assert(!/[가-힣]/.test(labels.en));
 }
});

test('local synthetic drafting requests the chosen language and preserves the returned model source',async()=>{
 const vm=require('node:vm'),fs=require('node:fs'),ui=require('../js/interface-language.js');
 for(const lang of ['en','ko']) {
  const nodes=Object.fromEntries(['test-local-llm-btn','local-llm-status-badge','local-llm-test-output'].map(id=>[id,{textContent:'',dataset:{},style:{}}]));
  const requests=[],original='SYNTHETIC model source 원문';
  const context={window:{CLINLOOP_API_BASE:'https://synthetic.invalid',ClinLoopUI:{set:(e,v)=>{e.textContent=ui.translate(v,lang);},source:(e,v)=>{e.textContent=v;}}},location:{hostname:'clinloopai.app',protocol:'https:'},document:{documentElement:{lang},addEventListener(){},getElementById:id=>nodes[id]||null},fetch:async(url,options)=>{
   requests.push({url,options});return {ok:true,json:async()=>url.endsWith('/status')?{best_model:'synthetic'}:{text:original,model:'synthetic',latency_ms:3}};
  }};
  vm.runInNewContext(fs.readFileSync('js/app.js','utf8'),context);await context.testLocalLLM();
  assert.equal(JSON.parse(requests[1].options.body).task,'kakao_message_'+lang);
  assert.equal(nodes['local-llm-test-output'].textContent,original);
  assert.equal(/[가-힣]/.test(nodes['local-llm-status-badge'].textContent),lang==='ko');
  assert.equal(nodes['test-local-llm-btn'].disabled,false);
 }
});
