'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {checkFixtures,score,evaluate}=require('../scripts/evaluate_report_review.cjs');
const cases=require('./fixtures/report_review_synthetic.json').cases;
const MODEL='synthetic-fixture:1b';
const ok=x=>({status:200,json:async()=>x});
test('twelve fixed synthetic cases cover all six text report categories',()=>{
 assert.equal(checkFixtures(),12);assert.equal(new Set(cases.map(c=>c.report_type)).size,6);
});
test('a quote fragment hiding negation cannot satisfy the synthetic reference expectation',()=>{
 const expected=[{quote:'No pleural effusion is identified.',assertion:'negated',follow_up_quote:'',deadline_quote:''}];
 assert.equal(score({findings:[{quote:'pleural effusion',assertion:'present',follow_up_quote:'',deadline_quote:''}]},expected).matched,0);
});
test('evaluation uses the application transport and names software agreement without a clinical accuracy claim',async()=>{
 const calls=[];
 const result=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:async(url,options)=>{
   calls.push({url,options});const body=options.body&&JSON.parse(options.body);
   if(url.endsWith('/api/tags'))return ok({models:[{name:MODEL}]});
   if(url.endsWith('/api/show'))return ok({details:{family:'synthetic'},model_info:{'synthetic.context_length':16384},capabilities:['completion']});
   const fixture=cases.find(c=>c.text===body.prompt);assert(fixture);return ok({model:MODEL,done:true,done_reason:'stop',response:JSON.stringify({findings:fixture.expected,missing_context:[]})});
 }});
 assert.equal(result.cases_run,12);assert.equal(result.accepted,12);assert.equal(result.expectations_matched,12);assert.equal(result.clinical_accuracy_established,false);
 assert.equal(result.cases_not_run,0);assert(calls.every(c=>new URL(c.url).origin==='http://localhost:18133'));
});
test('failed generation stops the evaluation without counting remaining reports as clean',async()=>{
 const result=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:async(url)=>ok(url.endsWith('/api/tags')?{models:[{name:MODEL}]}:url.endsWith('/api/show')?{details:{},model_info:{'synthetic.context_length':16384},capabilities:['completion']}:{model:MODEL,done:false,response:'partial'})});
 assert.equal(result.cases_run,1);assert.equal(result.cases_not_run,11);assert.equal(result.accepted,0);
});
