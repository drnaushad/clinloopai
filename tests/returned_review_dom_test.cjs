const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('js/app.js', 'utf8');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
  append(...children) { this.children.push(...children); }
  set innerHTML(value) { throw new Error('Untrusted values must not enter innerHTML'); }
}
const context = vm.createContext({
  document: {addEventListener() {}, createElement: tag => new Element(tag)},
  window: {}, location: {hostname:'clinloopai.app'}, console
});
vm.runInContext(source + '\nglobalThis.AppUnderTest = ClinLoopApp;', context);
const app = Object.create(context.AppUnderTest.prototype);
const attack = '<img src=x onerror="alert(1)">';
for (const language of ['en', 'ko']) {
  app.currentLang = language;
  const node = app.renderCounterfactualStep({state:attack,stage:attack,desc:attack,time:attack},true);
  const texts = [];
  const walk = item => { texts.push(item.textContent); item.children.forEach(walk); };
  walk(node);
  assert.equal(texts.filter(text => text === attack).length, 4);
}
// Exercise the shipped IP rule: a literal backspace previously disabled matching.
const rules = source.match(/const PHI_RULES = (\[[\s\S]*?\n    \]);/);
assert.ok(rules);
const ip = vm.runInNewContext(rules[1]).find(rule => rule.name === 'IP 주소');
assert.equal('endpoint 192.168.1.12'.replace(ip.regex, '[IP]'), 'endpoint [IP]');
assert.equal('creatinine 1.2 mg/dL'.replace(ip.regex, '[IP]'), 'creatinine 1.2 mg/dL');
console.log('Dashboard source values remain text; IP regression passed.');
