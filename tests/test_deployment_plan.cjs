const test = require('node:test');
const assert = require('node:assert/strict');
const {build} = require('../js/deployment-plan.js');
const catalog = require('../data/deployment_modules.json');
const base = {country:'India',language:'en-IN',timeZone:'Asia/Kolkata',dateFormat:'iso8601',modules:['radiology_text']};
test('plans are never clinical authorization or runtime changes',()=>{
  for(const [country,language,timeZone] of [['India','hi','Asia/Kolkata'],['South Korea','ko','Asia/Seoul'],['United States','en-US','America/New_York'],['Egypt','ar','Africa/Cairo'],['Spain','es','Europe/Madrid']]) {
    const p=build({...base,country,language,timeZone,modules:catalog.report_modules.map(m=>m.id)},catalog);
    assert.equal(p.status,'planning_only');assert.equal(p.clinical_authorization,'not_established');
    assert.equal(p.runtime_configuration_changed,false);assert.equal(p.modules.length,5);
    assert(p.modules.every(m=>m.clinical_validation==='not_established'));
  }
});
test('unassessed languages remain explicit evaluation work',()=>{
  assert(build({...base,language:'hi'},catalog).warnings.some(w=>w.includes('new language-specific evaluation')));
});
test('ambiguous source dates require explicit institutional choice',()=>{
  for(const dateFormat of ['', 'auto', '03/04/26'])assert.throws(()=>build({...base,dateFormat},catalog));
});
test('missing and malformed setup cannot be exported as a complete plan',()=>{
  for(const patch of [{country:''},{country:'<script>'},{language:''},{language:'not_a_language'},
    {timeZone:''},{timeZone:'No/SuchZone'},{modules:[]},{modules:['invented']},
    {modules:['radiology_text','radiology_text']}])assert.throws(()=>build({...base,...patch},catalog));
});
test('arbitrary inputs and patient-like fields are not copied into the plan',()=>{
  const p=build({...base,patient_name:'PRIVATE',report_text:'PRIVATE',token:'PRIVATE'},catalog);
  assert(!JSON.stringify(p).includes('PRIVATE'));
});
