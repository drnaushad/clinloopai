'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { target, decorate, mount } = require('../js/language-controls.js');
function button(id, text) {
  return { id, textContent: text, attrs: {},
    setAttribute(k,v) { this.attrs[k]=v; }, removeAttribute(k) { delete this.attrs[k]; } };
}
test('a language toggle shows the flag for its destination, independent of current language', () => {
  const b=button('btn-lang','한국어'); decorate(b,'en');
  assert.equal(b.attrs['data-language'],'ko'); assert.equal(b.attrs['aria-label'],'한국어');
  assert.equal(b.attrs.lang,'ko'); assert.equal(b.attrs['aria-pressed'],undefined);
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
  const doc={readyState:'complete',documentElement:{lang:'en'},querySelectorAll:()=>buttons};
  mount(doc,Observer);
  assert.equal(buttons[0].attrs['aria-pressed'],'true');
  doc.documentElement.lang='ko-KR'; buttons[1].textContent='English'; observers[1].update();
  assert.equal(buttons[0].attrs['aria-pressed'],'false'); assert.equal(buttons[1].attrs['data-language'],'en');
  assert.equal(observations[0].options.attributes,undefined);
  assert.deepEqual(observations.at(-1).options.attributeFilter,['lang']);
});
test('initialization waits for the page and still decorates controls without observer support', () => {
  let start; const b=button('dock-btn-ko','한국어');
  const doc={readyState:'loading',documentElement:{lang:'ko'},querySelectorAll:()=>[b],addEventListener:(name,fn)=>{assert.equal(name,'DOMContentLoaded');start=fn;}};
  mount(doc,null); assert.deepEqual(b.attrs,{}); start(); assert.equal(b.attrs['aria-pressed'],'true');
});
