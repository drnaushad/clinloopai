'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {checkFixtures,score,aggregate,evaluate}=require('../scripts/evaluate_report_review.cjs');
const cases=require('./fixtures/report_review_synthetic.json').cases;
const MODEL='synthetic-fixture:1b';
const DIGEST='a'.repeat(64);
const ok=x=>({status:200,json:async()=>x});
test('fixed synthetic cases cover six categories and English/Korean',()=>{
 assert.equal(checkFixtures(),24);assert.equal(new Set(cases.map(c=>c.language)).size,2);assert.equal(new Set(cases.map(c=>c.report_type)).size,6);
});
test('a quote fragment hiding negation cannot satisfy the synthetic reference expectation',()=>{
 const expected=[{quote:'No pleural effusion is identified.',assertion:'negated',follow_up_quote:'',deadline_quote:''}];
 assert.equal(score({findings:[{quote:'pleural effusion',assertion:'present',follow_up_quote:'',deadline_quote:''}]},expected).matched,0);
});
test('evaluation uses the application transport and names software agreement without a clinical accuracy claim',async()=>{
 const calls=[];
 const result=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:async(url,options)=>{
   calls.push({url,options});const body=options.body&&JSON.parse(options.body);
   if(url.endsWith('/api/tags'))return ok({models:[{name:MODEL,digest:DIGEST}]});
   if(url.endsWith('/api/show'))return ok({details:{family:'synthetic'},model_info:{'synthetic.context_length':16384},capabilities:['completion']});
   const fixture=cases.find(c=>c.text===body.prompt);assert(fixture);return ok({model:MODEL,done:true,done_reason:'stop',response:JSON.stringify({findings:fixture.expected,missing_context:[]})});
 }});
 assert.equal(result.cases_run,cases.length);assert.equal(result.accepted,cases.length);assert.equal(result.expectations_matched,cases.reduce((n,c)=>n+c.expected.length,0));assert.equal(result.clinical_accuracy_established,false);
 assert.equal(result.cases_not_run,0);assert(calls.every(c=>new URL(c.url).origin==='http://localhost:18133'));
});
test('failed generation stops the evaluation without counting remaining reports as clean',async()=>{
 const result=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:async(url)=>ok(url.endsWith('/api/tags')?{models:[{name:MODEL,digest:DIGEST}]}:url.endsWith('/api/show')?{details:{},model_info:{'synthetic.context_length':16384},capabilities:['completion']}:{model:MODEL,done:false,response:'partial'})});
 assert.equal(result.cases_run,1);assert.equal(result.cases_not_run,cases.length-1);assert.equal(result.metrics.recall_including_rejected_and_unrun_cases,0);assert.equal(result.accepted,0);
});

function stub(changes={}){
 let tagCalls=0,generations=0;
 const fetcher=async(url,options)=>{
  if(url.endsWith('/api/tags')){tagCalls++;return ok({models:[{name:MODEL,digest:changes.noDigest?null:changes.replaceDigest&&tagCalls>1?'b'.repeat(64):DIGEST}]});}
  if(url.endsWith('/api/show'))return ok({details:{family:'synthetic'},model_info:{'synthetic.context_length':16384},capabilities:['completion']});
  generations++;const c=cases.find(c=>c.text===JSON.parse(options.body).prompt);
  return ok({model:MODEL,done:true,done_reason:'stop',response:JSON.stringify(changes.review?changes.review(c,generations):{findings:c.expected,missing_context:[]})});
 };
 return {fetcher,generations:()=>generations};
}
test('duplicate predictions count as extras and cannot satisfy repeated expectations',()=>{
 const e=cases[0].expected[0];const s=score({findings:[e,e]},[e]);
 assert.equal(s.matched,1);assert.equal(s.false_positive_findings,1);assert.equal(s.exact,false);
 assert.equal(score({findings:[e]},[e,e]).matched,1);
});
test('valid JSON with wrong assertion, follow-up or timing fails distinct measurements',()=>{
 const e=cases.find(c=>c.id==='rad-plan').expected[0];
 const s=score({findings:[{...e,assertion:'historical',follow_up_quote:'',deadline_quote:''}]},[e]);
 assert.equal(s.matched,0);assert.equal(s.quote_matches,1);
 assert.equal(s.assertion_errors,1);assert.equal(s.follow_up_errors,1);assert.equal(s.deadline_errors,1);
 assert.equal(s.false_negative_findings,1);assert.equal(s.false_positive_findings,1);
});
test('empty extraction never earns recall credit for a missed source finding',()=>{
 const s=score({findings:[]},cases[0].expected);assert.equal(s.matched,0);assert.equal(s.false_negative_findings,1);
 const a=aggregate([{id:cases[0].id,accepted:true,...s}],[cases[0]]);assert.equal(a.recall_including_rejected_and_unrun_cases,0);
 assert.equal(a.precision_on_accepted_output,null);
});
test('matching a quoted fragment does not satisfy full source-sentence expectation',()=>{
 const e=cases[0].expected[0];assert.equal(score({findings:[{...e,quote:'Potassium 4.2 mmol/L'}]},[e]).matched,0);
});
test('a negative reference with an extra model finding has zero precision',()=>{
 const s=score({findings:cases[0].expected},[]),a=aggregate([{id:'negative',accepted:true,...s}],[{id:'negative',expected:[]}]);
 assert.equal(a.extra_findings,1);assert.equal(a.precision_on_accepted_output,0);assert.equal(a.exact_cases,0);
 assert.equal(a.recall_including_rejected_and_unrun_cases,null);
});
test('changed checkpoint at end invalidates all comparison metrics',async()=>{
 const model=stub({replaceDigest:true}),r=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:model.fetcher});
 assert.equal(r.provenance_valid,false);assert.equal(r.metrics,null);assert.equal(r.expectations_matched,null);
 assert.notEqual(r.model_digest,r.final_model_digest);assert(Object.values(r.by_language).every(x=>x===null));
});
test('missing checkpoint digest is rejected before sending any synthetic text',async()=>{
 const model=stub({noDigest:true});await assert.rejects(evaluate({address:'http://localhost:18133',model:MODEL,fetcher:model.fetcher}));
 assert.equal(model.generations(),0);
});
test('source-valid omission reduces agreement despite accepted transport',async()=>{
 const model=stub({review:()=>({findings:[],missing_context:[]})});
 const r=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:model.fetcher});
 assert.equal(r.accepted,cases.length);assert.equal(r.metrics.missed_findings,r.expectations_planned);
 assert.equal(r.metrics.recall_including_rejected_and_unrun_cases,0);assert.equal(r.clinical_accuracy_established,false);
 assert.equal(r.by_language.ko.planned_cases,6);assert.equal(Object.keys(r.by_report_type).length,6);
});
test('invented evidence rejects the whole case and keeps later cases unrun',async()=>{
 const model=stub({review:()=>({findings:[{...cases[0].expected[0],quote:'Invented non-source finding.'}],missing_context:[]})});
 const r=await evaluate({address:'http://localhost:18133',model:MODEL,fetcher:model.fetcher});
 assert.equal(r.accepted,0);assert.equal(r.cases_run,1);assert.equal(r.metrics.accepted_case_coverage,0);
 assert.equal(r.metrics.missed_findings,cases[0].expected.length);
 assert.equal(r.metrics.unrun_expected_findings,r.expectations_planned-cases[0].expected.length);
 assert(!JSON.stringify(r).includes('Invented non-source'));
});

test('unrun categories have no measured recall or missed findings',()=>{
 const r=aggregate([],cases);
 assert.equal(r.attempted_cases,0);assert.equal(r.unrun_cases,24);
 assert.equal(r.expected_findings,0);assert.equal(r.missed_findings,0);
 assert.equal(r.recall_on_attempted_cases,null);assert.equal(r.f1_on_attempted_cases,null);
 assert.equal(r.unrun_expected_findings,cases.reduce((n,c)=>n+c.expected.length,0));
 assert.equal(r.execution_complete,false);assert.equal(r.all_outputs_accepted,false);
});
test('rejection, accepted omissions and unrun cases have separate denominators',()=>{
 const planned=cases.slice(0,3);
 const r=aggregate([{id:planned[0].id,accepted:true,...score({findings:[]},planned[0].expected)},
  {id:planned[1].id,accepted:false}],planned);
 const attempted=planned[0].expected.length+planned[1].expected.length;
 assert.equal(r.expected_findings,attempted);assert.equal(r.missed_findings,attempted);
 assert.equal(r.rejected_expected_findings,planned[1].expected.length);
 assert.equal(r.unrun_expected_findings,planned[2].expected.length);
 assert.equal(r.attempted_cases,2);assert.equal(r.rejected_cases,1);assert.equal(r.unrun_cases,1);
 assert.equal(r.recall_on_attempted_cases,0);assert.equal(r.execution_complete,false);
});
test('duplicate or foreign cases cannot silently distort coverage',()=>{
 assert.throws(()=>aggregate([{id:cases[0].id},{id:cases[0].id}],cases));
 assert.throws(()=>aggregate([{id:'foreign'}],cases));
 assert.throws(()=>aggregate([],[cases[0],cases[0]]));
});
