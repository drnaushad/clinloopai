#!/usr/bin/env node
'use strict';
// Fixed synthetic fixtures only. No patient-file input, remote API or model downloads.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {Workspace,localAddress}=require('../js/private-workspace.js');
globalThis.ClinLoopPrivate={localAddress};
const {validate,validText,SYSTEM}=require('../js/report-review.js');
const fixturePath=path.join(__dirname,'../tests/fixtures/report_review_synthetic.json');
const fixtures=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
function checkFixtures(){
  if(fixtures.synthetic_only!==true||fixtures.seed!==42||fixtures.cases.length!==12)throw new Error('Synthetic fixture contract invalid.');
  for(const c of fixtures.cases){validText(c.text,c.report_type);validate({findings:c.expected,missing_context:[]},c.text);}
  return fixtures.cases.length;
}
function score(review,expected){
  return {expected:expected.length,matched:expected.filter(e=>review.findings.some(f=>
    f.quote.includes(e.quote)&&f.assertion===e.assertion&&f.follow_up_quote===e.follow_up_quote&&f.deadline_quote===e.deadline_quote)).length};
}
async function evaluate({address,model,fetcher=fetch}){
  checkFixtures();let modelDigest=null;
  const w=new Workspace(async(url,options)=>{
    const r=await fetcher(url,options);
    if(url.endsWith('/api/tags')&&r.status===200){const tags=await r.json();modelDigest=tags.models?.find(m=>m.name===model)?.digest||null;return {status:r.status,json:async()=>tags};}
    return r;
  }),cases=[];
  const schema=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/report_review_schema.json'),'utf8'));
  try{
    await w.connect(localAddress(address),true);
    if(!w.models.includes(model))throw new Error('Requested installed local model unavailable. No fallback.');
    for(const c of fixtures.cases){
      try{
        const raw=await w.run(model,c.text,{schema,system:SYSTEM+' Report category: '+c.report_type+'.'});
        const review=validate(JSON.parse(raw),c.text);cases.push({id:c.id,accepted:true,...score(review,c.expected)});
      }catch(_){cases.push({id:c.id,accepted:false,error:'Model response failed local transport, completeness or source checks.'});break;}
    }
  }finally{w.clear(true);}
  return {synthetic_only:true,clinical_accuracy_established:false,model,
    model_digest:modelDigest,prompt_sha256:crypto.createHash('sha256').update(SYSTEM).digest('hex'),schema_sha256:crypto.createHash('sha256').update(JSON.stringify(schema)).digest('hex'),
    fixture_sha256:crypto.createHash('sha256').update(fs.readFileSync(fixturePath)).digest('hex'),
    cases_planned:fixtures.cases.length,cases_run:cases.length,cases_not_run:fixtures.cases.length-cases.length,
    accepted:cases.filter(c=>c.accepted).length,expectations_matched:cases.reduce((n,c)=>n+(c.matched||0),0),
    expectations_planned:fixtures.cases.reduce((n,c)=>n+c.expected.length,0),cases};
}
async function main(){
  if(process.argv.includes('--check-fixtures')){console.log('Validated '+checkFixtures()+' synthetic fixtures; no model was called.');return;}
  const args=process.argv.slice(2),options={};
  for(let i=0;i<args.length;i+=2){if(!['--model','--address','--output'].includes(args[i])||!args[i+1])throw new Error('Use --model INSTALLED_MODEL --address LOOPBACK_URL --output LOCAL_JSON.');options[args[i].slice(2)]=args[i+1];}
  if(!options.model||!options.address||!options.output)throw new Error('Explicit model, loopback address and local output file required.');
  if(fs.existsSync(options.output))throw new Error('Choose a new output filename before running inference.');
  const report=await evaluate(options);fs.writeFileSync(options.output,JSON.stringify(report,null,2)+'\n',{mode:0o600,flag:'wx'});
  console.log(JSON.stringify({cases_run:report.cases_run,accepted:report.accepted,expectations_matched:report.expectations_matched,clinical_accuracy_established:false}));
  if(report.accepted!==12||report.expectations_matched!==report.expectations_planned)process.exitCode=2;
}
if(require.main===module)main().catch(()=>{console.error('Synthetic evaluation could not complete. Check local model health and configuration. No clinical accuracy established.');process.exitCode=1;});
module.exports={checkFixtures,score,evaluate};
