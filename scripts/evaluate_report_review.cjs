#!/usr/bin/env node
'use strict';
// Fixed synthetic fixtures only. No patient-file input, cloud API or model downloads.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {Workspace,localAddress}=require('../js/private-workspace.js');
globalThis.ClinLoopPrivate={localAddress};
const {validate,validText,SYSTEM}=require('../js/report-review.js');
const fixturePath=path.join(__dirname,'../tests/fixtures/report_review_synthetic.json');
const fixtures=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
function checkFixtures(){
  if(fixtures.synthetic_only!==true||fixtures.seed!==42||fixtures.cases.length<12)throw new Error('Synthetic fixture contract invalid.');
  const ids=new Set();
  for(const c of fixtures.cases){
    if(typeof c.id!=='string'||ids.has(c.id)||!['en','ko'].includes(c.language||'en'))throw new Error('Invalid synthetic case metadata.');
    ids.add(c.id);validText(c.text,c.report_type);validate({findings:c.expected,missing_context:[]},c.text);
  }
  return fixtures.cases.length;
}
function score(review,expected){
  // Exact tuples, one-to-one: duplicate predictions cannot earn extra credit.
  // Alternate clinically equivalent wording is deliberately not adjudicated here.
  const fields=['quote','assertion','follow_up_quote','deadline_quote'];
  const remaining=review.findings.map(f=>({...f})),unmatched=[];
  let matched=0,quote_matches=0,assertion_errors=0,follow_up_errors=0,deadline_errors=0;
  for(const e of expected){
    const at=remaining.findIndex(f=>fields.every(key=>f[key]===e[key]));
    if(at>=0){remaining.splice(at,1);matched++;quote_matches++;}else unmatched.push(e);
  }
  for(const e of unmatched){
    const at=remaining.findIndex(f=>f.quote===e.quote);
    if(at<0)continue;
    const f=remaining.splice(at,1)[0];quote_matches++;
    assertion_errors+=f.assertion!==e.assertion;
    follow_up_errors+=f.follow_up_quote!==e.follow_up_quote;
    deadline_errors+=f.deadline_quote!==e.deadline_quote;
  }
  return {expected:expected.length,predicted:review.findings.length,matched,quote_matches,
    assertion_errors,follow_up_errors,deadline_errors,
    false_positive_findings:review.findings.length-matched,false_negative_findings:expected.length-matched,
    exact:matched===expected.length&&matched===review.findings.length};
}
function aggregate(cases,planned){
  const plannedById=new Map(planned.map(c=>[c.id,c]));
  if(plannedById.size!==planned.length||planned.some(c=>typeof c.id!=='string')||
    new Set(cases.map(c=>c.id)).size!==cases.length||cases.some(c=>!plannedById.has(c.id)))
    throw new Error('Evaluation case coverage is invalid.');
  const plannedExpected=planned.reduce((n,c)=>n+c.expected.length,0),accepted=cases.filter(c=>c.accepted);
  const expected=cases.reduce((n,c)=>n+plannedById.get(c.id).expected.length,0);
  const acceptedExpected=accepted.reduce((n,c)=>n+plannedById.get(c.id).expected.length,0);
  const sum=key=>accepted.reduce((n,c)=>n+(c[key]||0),0),tp=sum('matched'),predicted=sum('predicted');
  return {metrics_schema_version:2,
    definition:'Exact synthetic tuple agreement. Attempted-case recall includes rejected output as abstention; unrun cases are reported separately. Not clinical correctness.',
    expected_findings:expected,matched_findings:tp,extra_findings:predicted-tp,missed_findings:expected-tp,
    planned_expected_findings:plannedExpected,unrun_expected_findings:plannedExpected-expected,
    rejected_expected_findings:expected-acceptedExpected,
    precision_on_accepted_output:predicted?tp/predicted:null,
    recall_on_attempted_cases:expected?tp/expected:null,
    recall_on_accepted_cases:acceptedExpected?tp/acceptedExpected:null,
    f1_on_attempted_cases:expected+predicted?2*tp/(expected+predicted):null,
    // Legacy fields are conservative plan-coverage bounds, not measured extraction accuracy.
    recall_including_rejected_and_unrun_cases:plannedExpected?tp/plannedExpected:null,
    f1_including_rejected_and_unrun_cases:plannedExpected+predicted?2*tp/(plannedExpected+predicted):null,
    legacy_plan_bound_meaning:'Unrun cases penalize plan coverage only; do not present these bounds as measured model accuracy.',
    attempted_cases:cases.length,rejected_cases:cases.length-accepted.length,
    unrun_cases:planned.length-cases.length,execution_complete:cases.length===planned.length,
    all_outputs_accepted:accepted.length===planned.length,
    attempted_case_coverage:planned.length?cases.length/planned.length:null,
    accepted_case_coverage:planned.length?accepted.length/planned.length:null,
    exact_cases:accepted.filter(c=>c.exact).length,planned_cases:planned.length,
    assertion_errors_on_matched_quotes:sum('assertion_errors'),
    follow_up_errors_on_matched_quotes:sum('follow_up_errors'),deadline_errors_on_matched_quotes:sum('deadline_errors')};
}
async function evaluate({address,model,fetcher=fetch}){
  checkFixtures();let modelDigest=null;
  const w=new Workspace(async(url,options)=>{
    const r=await fetcher(url,options);
    if(url.endsWith('/api/tags')&&r.status===200){const tags=await r.json();modelDigest=tags.models?.find(m=>m.name===model)?.digest||null;return {status:r.status,json:async()=>tags};}
    return r;
  }),cases=[];
  const schemaPath=path.join(__dirname,'../data/report_review_schema.json');
  const schema=JSON.parse(fs.readFileSync(schemaPath,'utf8'));
  let initialDigest,finalDigest,provenanceValid=false;
  try{
    await w.connect(localAddress(address),true);initialDigest=modelDigest;
    if(!w.models.includes(model))throw new Error('Requested installed local model unavailable. No fallback.');
    if(typeof initialDigest!=='string'||!/^[a-f0-9]{64}$/i.test(initialDigest))throw new Error('Checkpoint digest required before inference.');
    for(const c of fixtures.cases){
      try{
        const raw=await w.run(model,c.text,{schema,system:SYSTEM+' Report category: '+c.report_type+'.'});
        const review=validate(JSON.parse(raw),c.text);
        cases.push({id:c.id,report_type:c.report_type,language:c.language||'en',accepted:true,...score(review,c.expected)});
      }catch(_){cases.push({id:c.id,report_type:c.report_type,language:c.language||'en',accepted:false,error:'Model response failed local transport, completeness or source checks.'});break;}
    }
    await w.request('/api/tags',null,w.epoch);finalDigest=modelDigest;
    provenanceValid=initialDigest===finalDigest;
  }finally{w.clear(true);}
  const metrics=provenanceValid?aggregate(cases,fixtures.cases):null;
  const by=(key)=>Object.fromEntries([...new Set(fixtures.cases.map(c=>c[key]||'en'))].map(value=>[value,
    provenanceValid?aggregate(cases.filter(c=>c[key]===value),fixtures.cases.filter(c=>(c[key]||'en')===value)):null]));
  return {synthetic_only:true,clinical_accuracy_established:false,reference:'Developer-authored synthetic expectations, not independent clinician labels',model,
    model_digest:initialDigest,final_model_digest:finalDigest,provenance_valid:provenanceValid,
    provenance_limit:'Boundary checks detect changed checkpoint tags, not a malicious server or an intervening change reverted before completion',
    prompt_sha256:hash(SYSTEM),prompt_template:'SYSTEM + Report category: CASE.report_type + period',
    schema_sha256:hash(fs.readFileSync(schemaPath)),fixture_sha256:hash(fs.readFileSync(fixturePath)),
    executable_sha256:hash([__filename,'../js/private-workspace.js','../js/report-review.js'].map(n=>fs.readFileSync(path.resolve(__dirname,n))).map(b=>hash(b)).join('')),
    cases_planned:fixtures.cases.length,cases_run:cases.length,cases_not_run:fixtures.cases.length-cases.length,
    accepted:cases.filter(c=>c.accepted).length,expectations_matched:metrics?.matched_findings??null,
    expectations_planned:fixtures.cases.reduce((n,c)=>n+c.expected.length,0),metrics,
    by_report_type:by('report_type'),by_language:by('language'),cases};
}
async function main(){
  if(process.argv.includes('--check-fixtures')){console.log('Validated '+checkFixtures()+' synthetic fixtures; no model was called.');return;}
  const args=process.argv.slice(2),options={};
  for(let i=0;i<args.length;i+=2){if(!['--model','--address','--output'].includes(args[i])||!args[i+1])throw new Error('Use --model INSTALLED_MODEL --address LOOPBACK_URL --output LOCAL_JSON.');options[args[i].slice(2)]=args[i+1];}
  if(!options.model||!options.address||!options.output)throw new Error('Explicit model, loopback address and local output file required.');
  if(fs.existsSync(options.output))throw new Error('Choose a new output filename before running inference.');
  const report=await evaluate(options);fs.writeFileSync(options.output,JSON.stringify(report,null,2)+'\n',{mode:0o600,flag:'wx'});
  console.log(JSON.stringify({cases_run:report.cases_run,accepted:report.accepted,expectations_matched:report.expectations_matched,provenance_valid:report.provenance_valid,clinical_accuracy_established:false}));
  if(!report.provenance_valid||report.accepted!==report.cases_planned||report.metrics.exact_cases!==report.cases_planned)process.exitCode=2;
}
if(require.main===module)main().catch(()=>{console.error('Synthetic evaluation could not complete. Check local model health and configuration. No clinical accuracy established.');process.exitCode=1;});
module.exports={checkFixtures,score,aggregate,evaluate};
