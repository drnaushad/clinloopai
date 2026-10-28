#!/usr/bin/env node
'use strict';
// Offline coordination and scoring only: no inference, network or clinical authorization.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {TYPES,validText,validate}=require('../js/report-review.js');
const {score,aggregate}=require('./evaluate_report_review.cjs');
const ROOT=path.resolve(__dirname,'..'),MAX_BYTES=16000000;
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const canonical=x=>JSON.stringify(x);
const same=(a,b)=>canonical(a)===canonical(b);
const fail=()=>{throw new Error('Study validation failed. No metrics released.');};
const object=x=>x&&typeof x==='object'&&!Array.isArray(x);
const hex=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const ref=x=>typeof x==='string'&&/^[A-Za-z][A-Za-z0-9_-]{2,63}$/.test(x);
function keys(x,names){if(!object(x)||Object.keys(x).sort().join()!==names.slice().sort().join())fail();}
function toolHash(){return hash(['report_study.cjs','evaluate_report_review.cjs','../js/report-review.js'].map(f=>hash(fs.readFileSync(path.resolve(__dirname,f)))).join(''));}
function read(file){const stat=fs.lstatSync(file);if(!stat.isFile()||stat.size>MAX_BYTES)fail();return JSON.parse(fs.readFileSync(file,'utf8'));}
function outsideRepo(file){
  let resolved=fs.realpathSync(fs.existsSync(file)?file:path.dirname(path.resolve(file)));
  if(resolved===ROOT||resolved.startsWith(ROOT+path.sep))fail();
  // Also protect a different checkout reached through a symlink or the original workspace.
  for(let parent=resolved;;parent=path.dirname(parent)){
    const git=path.join(parent,'.git');
    if(fs.existsSync(git)&&(fs.lstatSync(git).isFile()||fs.existsSync(path.join(git,'HEAD'))))fail();
    if(parent===path.dirname(parent))break;
  }
}
function write(file,value){outsideRepo(file);fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});}
function inputStudy(input){
  keys(input,['schema_version','data_kind','governance','provenance','cases']);
  if(input.schema_version!==1||!['synthetic','approved-deidentified-research'].includes(input.data_kind))fail();
  keys(input.governance,['institution_ref','protocol_ref','ethics_ref','data_permission_ref','clinical_lead_ref','permission_attested']);
  if(!Object.entries(input.governance).every(([k,v])=>k==='permission_attested'?v===true:ref(v)))fail();
  keys(input.provenance,['software_commit','prompt_sha256','schema_sha256','model_id','model_revision','inference_config_sha256']);
  const p=input.provenance;
  if(!/^[a-f0-9]{40}$/.test(p.software_commit)||!['prompt_sha256','schema_sha256','inference_config_sha256'].every(k=>hex(p[k]))||
    !['model_id','model_revision'].every(k=>typeof p[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:+-]{0,159}$/.test(p[k])&&!/^(?:sk-|AIza)/i.test(p[k])))fail();
  if(!Array.isArray(input.cases)||!input.cases.length||input.cases.length>1000)fail();
  const ids=new Set(),texts=new Set(),groups=new Map();
  for(const c of input.cases){
    keys(c,['case_id','patient_group','partition','report_type','language','text','prediction']);
    if(!/^C[0-9]{4,8}$/.test(c.case_id)||ids.has(c.case_id)||!/^G[0-9]{4,8}$/.test(c.patient_group)||
      !['development','evaluation'].includes(c.partition)||typeof c.language!=='string'||!/^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$/.test(c.language))fail();
    ids.add(c.case_id);validText(c.text,c.report_type);
    const textHash=hash(c.text.normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim());
    if(texts.has(textHash)||(groups.has(c.patient_group)&&groups.get(c.patient_group)!==c.partition))fail();
    texts.add(textHash);groups.set(c.patient_group,c.partition);
    if(!object(c.prediction))fail();
    if(c.prediction.status==='accepted'){
      keys(c.prediction,['status','review']);validate(c.prediction.review,c.text);
    }else{keys(c.prediction,['status']);if(!['rejected','unrun'].includes(c.prediction.status))fail();}
  }
  if(!input.cases.some(c=>c.partition==='evaluation'))fail();
  return input;
}
function prepare(inputFile,out){
  outsideRepo(out);const input=inputStudy(read(inputFile));
  // Real-data classification is an operator declaration, never automated de-identification.
  if(input.data_kind!=='synthetic')outsideRepo(inputFile);
  if(fs.existsSync(out))fail();fs.mkdirSync(out,{mode:0o700});
  const sealed={...input,tool_sha256:toolHash()},studyHash=hash(canonical(sealed));
  write(path.join(out,'sealed.json'),sealed);
  write(path.join(out,'manifest.json'),{schema_version:1,study_sha256:studyHash,tool_sha256:toolHash(),seed:42});
  const rows=input.cases.filter(c=>c.partition==='evaluation').map(c=>({case_id:c.case_id,source_sha256:hash(c.text),
    report_type:c.report_type,language:c.language,text:c.text,complete:false,findings:null}));
  for(const [i,name]of ['reviewer_1','reviewer_2','adjudication'].entries()){
    const records=rows.slice().sort((a,b)=>hash('42:'+i+':'+a.case_id).localeCompare(hash('42:'+i+':'+b.case_id)));
    write(path.join(out,name+'.json'),{schema_version:1,study_sha256:studyHash,
      reviewer:{reviewer_ref:'',role:'',verification_ref:'',origin:'human',independent_of_development:false,personally_reviewed:false},records});
  }
  return {prepared_reports:rows.length,reference_status:'pending',metrics:null,network_calls:0};
}
function referenceSheet(file,sealed,studyHash){
  const s=read(file);keys(s,['schema_version','study_sha256','reviewer','records']);
  if(s.schema_version!==1||s.study_sha256!==studyHash||!Array.isArray(s.records))fail();
  keys(s.reviewer,['reviewer_ref','role','verification_ref','origin','independent_of_development','personally_reviewed']);
  const cases=sealed.cases.filter(c=>c.partition==='evaluation'),byId=new Map(cases.map(c=>[c.case_id,c]));
  const seen=new Set();if(s.records.length!==cases.length)fail();
  for(const r of s.records){
    keys(r,['case_id','source_sha256','report_type','language','text','complete','findings']);
    const c=byId.get(r.case_id);
    if(!c||seen.has(r.case_id)||r.source_sha256!==hash(c.text)||r.text!==c.text||r.report_type!==c.report_type||r.language!==c.language||typeof r.complete!=='boolean')fail();
    seen.add(r.case_id);
    if(r.complete){
      const reviewer=s.reviewer;
      if(!ref(reviewer.reviewer_ref)||!ref(reviewer.verification_ref)||!['clinician','clinical-specialist'].includes(reviewer.role)||
        !['human','ai-assisted-human'].includes(reviewer.origin)||reviewer.independent_of_development!==true||reviewer.personally_reviewed!==true)fail();
      validate({findings:r.findings,missing_context:[]},c.text);
      if(new Set(findingSet(r.findings)).size!==r.findings.length)fail();
    }else if(r.findings!==null)fail();
  }
  return s;
}
function findingSet(findings){return findings.map(f=>canonical([f.quote,f.assertion,f.follow_up_quote,f.deadline_quote])).sort();}
function metrics(rows,planned){
  const m=aggregate(rows,planned);
  return Object.fromEntries(['planned_cases','attempted_cases','rejected_cases','unrun_cases','accepted_case_coverage','expected_findings',
    'matched_findings','extra_findings','missed_findings','unrun_expected_findings','precision_on_accepted_output','recall_on_attempted_cases',
    'f1_on_attempted_cases','exact_cases'].map(k=>[k,m[k]]));
}
function scoreStudy(folder){
  outsideRepo(folder);const sealed=read(path.join(folder,'sealed.json')),manifest=read(path.join(folder,'manifest.json'));
  const {tool_sha256,...input}=sealed;inputStudy(input);
  const studyHash=hash(canonical(sealed));
  keys(manifest,['schema_version','study_sha256','tool_sha256','seed']);
  if(manifest.schema_version!==1||manifest.seed!==42||manifest.study_sha256!==studyHash||tool_sha256!==toolHash()||manifest.tool_sha256!==toolHash())fail();
  const sheets=['reviewer_1','reviewer_2','adjudication'].map(n=>referenceSheet(path.join(folder,n+'.json'),sealed,studyHash));
  const maps=sheets.map(s=>new Map(s.records.map(r=>[r.case_id,r]))),planned=[],rows=[];
  let pending=0,disagreements=0;
  for(const c of input.cases.filter(c=>c.partition==='evaluation')){
    const [a,b,z]=maps.map(m=>m.get(c.case_id));let expected;
    if(!a.complete||!b.complete){pending++;continue;}
    const identity=sheets.slice(0,2).map(s=>s.reviewer.reviewer_ref.toLowerCase());
    if(identity[0]===identity[1])fail();
    if(!same(findingSet(a.findings),findingSet(b.findings))){
      disagreements++;
      if(!z.complete){pending++;continue;}
      if(identity.includes(sheets[2].reviewer.reviewer_ref.toLowerCase()))fail();expected=z.findings;
    }else expected=a.findings;
    planned.push({id:c.case_id,expected,report_type:c.report_type,language:c.language});
    if(c.prediction.status==='unrun')continue;
    rows.push(c.prediction.status==='accepted'?{id:c.case_id,accepted:true,...score(validate(c.prediction.review,c.text),expected)}:{id:c.case_id,accepted:false});
  }
  const result={schema_version:1,data_kind:input.data_kind,reports_planned:maps[0].size,pending_references:pending,disagreements,
    clinical_accuracy_established:false,reference_identity_authenticated:false,network_calls:0,
    definition:'Exact verbatim extraction-tuple agreement with coordinator-declared human references. Not diagnostic accuracy, clinical validation or approval for patient care.',
    limitations:['Reviewer identity, qualifications, independence and institutional permission require external verification.',
      'No report-level sensitivity/specificity, confidence intervals or generalization claim. Reports from the same patient may be correlated.',
      'Grouping/partition checks use declared pseudonyms; patient independence and absence of development exposure are not established.',
      'Imported predictions and model/prompt/configuration provenance are coordinator declarations, not attestation of a live model.'],
    study_sha256:studyHash,tool_sha256:toolHash(),metrics:null,by_report_type:{},by_language:{}};
  if(!pending){
    result.metrics=metrics(rows,planned);
    for(const [key,target]of [['report_type','by_report_type'],['language','by_language']])
      for(const value of new Set(planned.map(c=>c[key]))){const group=planned.filter(c=>c[key]===value),ids=new Set(group.map(c=>c.id));result[target][value]=metrics(rows.filter(c=>ids.has(c.id)),group);}
  }
  return result;
}
function example(){
  const fixtures=read(path.resolve(__dirname,'../tests/fixtures/report_review_synthetic.json'));
  const cases=TYPES.map((type,i)=>{const c=fixtures.cases.find(c=>c.report_type===type);return{case_id:'C'+String(i+1).padStart(4,'0'),patient_group:'G'+String(i+1).padStart(4,'0'),
    partition:'evaluation',report_type:type,language:c.language||'en',text:c.text,prediction:{status:'accepted',review:{findings:c.expected,missing_context:[]}}};});
  return {schema_version:1,data_kind:'synthetic',governance:{institution_ref:'SYNTHETIC_SITE',protocol_ref:'SYNTHETIC_PROTOCOL',ethics_ref:'NOT_APPLICABLE',data_permission_ref:'SYNTHETIC_ONLY',clinical_lead_ref:'UNASSIGNED',permission_attested:true},
    provenance:{software_commit:'0'.repeat(40),prompt_sha256:hash(require('../js/report-review.js').SYSTEM),schema_sha256:hash(fs.readFileSync(path.resolve(__dirname,'../data/report_review_schema.json'))),model_id:'synthetic-fixture-replay',model_revision:'developer-authored',inference_config_sha256:hash('no inference')},cases};
}
function main(args){
  const flags={};for(let i=0;i<args.length;i+=2){if(!['--input','--out','--study','--action'].includes(args[i])||!args[i+1]||flags[args[i]])fail();flags[args[i]]=args[i+1];}
  let result;
  if(flags['--action']==='example'&&same(Object.keys(flags).sort(),['--action','--out'])){write(flags['--out'],example());result={synthetic_example_written:true,network_calls:0};}
  else if(flags['--action']==='prepare'&&same(Object.keys(flags).sort(),['--action','--input','--out']))result=prepare(flags['--input'],flags['--out']);
  else if(flags['--action']==='score'&&same(Object.keys(flags).sort(),['--action','--out','--study'])){result=scoreStudy(flags['--study']);write(flags['--out'],result);}
  else fail();console.log(JSON.stringify(result));
}
if(require.main===module){try{main(process.argv.slice(2));}catch(_){console.error('Study operation failed validation or file access. No metrics released. Check the local study instructions.');process.exitCode=1;}}
module.exports={inputStudy,prepare,scoreStudy,example,toolHash};
