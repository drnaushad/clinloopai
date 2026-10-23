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
  assert.equal(b.attrs['data-language'],'en'); assert.equal(b.attrs['aria-label'],'English');
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
