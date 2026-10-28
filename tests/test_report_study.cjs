'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process');
const {prepare,scoreStudy,example,inputStudy}=require('../scripts/report_study.cjs');
const copy=x=>JSON.parse(JSON.stringify(x));
function fixture(t,mutate=()=>{}){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'clinloop-study-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const input=example();mutate(input);const inputFile=path.join(root,'input.json'),out=path.join(root,'study');
  fs.writeFileSync(inputFile,JSON.stringify(input));prepare(inputFile,out);return{root,out,input};
}
function complete(out,input,{disagree=false,adjudicate=false}={}){
  for(const [i,name]of ['reviewer_1','reviewer_2','adjudication'].entries()){
    const file=path.join(out,name+'.json'),sheet=JSON.parse(fs.readFileSync(file));
    if(i===2&&!adjudicate)continue;
    sheet.reviewer={reviewer_ref:'REVIEWER_'+i,role:'clinician',verification_ref:'EXTERNAL_VERIFICATION_'+i,origin:'human',independent_of_development:true,personally_reviewed:true};
    for(const row of sheet.records){row.complete=true;row.findings=copy(input.cases.find(c=>c.case_id===row.case_id).prediction.review?.findings||[]);}
    if(i===1&&disagree)sheet.records[0].findings=[];
    fs.writeFileSync(file,JSON.stringify(sheet));
  }
}
test('all six text categories prepare blank blinded worksheets and no metrics',t=>{
  const {out,input}=fixture(t);assert.equal(new Set(input.cases.map(c=>c.report_type)).size,6);
  const r=JSON.parse(fs.readFileSync(path.join(out,'reviewer_1.json')));
  for(const row of r.records){assert.equal(row.complete,false);assert.equal(row.findings,null);assert(!('prediction' in row));}
  const result=scoreStudy(out);assert.equal(result.pending_references,6);assert.equal(result.metrics,null);assert.equal(result.network_calls,0);
  assert.equal(result.clinical_accuracy_established,false);assert.equal(result.reference_identity_authenticated,false);
  if(process.platform!=='win32'){assert.equal(fs.statSync(out).mode&0o777,0o700);assert.equal(fs.statSync(path.join(out,'sealed.json')).mode&0o777,0o600);}
});
test('completed declared references permit only extraction agreement and aggregate exports',t=>{
  const {out,input}=fixture(t);complete(out,input);const result=scoreStudy(out);
  assert.equal(result.metrics.exact_cases,6);assert.equal(result.pending_references,0);
  assert.equal(Object.keys(result.by_report_type).length,6);assert.equal(result.clinical_accuracy_established,false);
  const raw=JSON.stringify(result);for(const c of input.cases){assert(!raw.includes(c.text));assert(!raw.includes(c.case_id));assert(!raw.includes(c.patient_group));}
  assert(!raw.includes('REVIEWER_'));assert(!raw.includes(input.provenance.model_id));
});
test('unrun and rejected cases remain explicit and cannot become normal findings',t=>{
  const {out,input}=fixture(t,x=>{x.cases[0].prediction={status:'unrun'};x.cases[1].prediction={status:'rejected'};});
  // Labels are supplied independently of these absent predictions.
  const truth=example();complete(out,truth);const result=scoreStudy(out);
  assert.equal(result.metrics.unrun_cases,1);assert.equal(result.metrics.rejected_cases,1);
  assert.equal(result.metrics.attempted_cases,5);assert.equal(result.metrics.accepted_case_coverage,4/6);
});
test('changed source, model provenance or evaluator hash withholds all metrics',t=>{
  const {out,input}=fixture(t);complete(out,input);const file=path.join(out,'sealed.json'),original=fs.readFileSync(file,'utf8');
  for(const change of [s=>s.cases[0].text+=' changed',s=>s.provenance.model_revision='changed',s=>s.tool_sha256='a'.repeat(64)]){
    const s=JSON.parse(original);change(s);fs.writeFileSync(file,JSON.stringify(s));assert.throws(()=>scoreStudy(out));
  }
});
test('changed source in a reference worksheet and duplicate case rows are rejected',t=>{
  const {out,input}=fixture(t);complete(out,input);const file=path.join(out,'reviewer_1.json'),s=JSON.parse(fs.readFileSync(file));
  const old=s.records[0].text;s.records[0].text='CHANGED';fs.writeFileSync(file,JSON.stringify(s));assert.throws(()=>scoreStudy(out));
  s.records[0].text=old;s.records[1]=s.records[0];fs.writeFileSync(file,JSON.stringify(s));assert.throws(()=>scoreStudy(out));
});
test('AI-only, missing verification and duplicate reviewer identities cannot complete reference records',t=>{
  const {out,input}=fixture(t);complete(out,input);const file=path.join(out,'reviewer_2.json'),original=fs.readFileSync(file,'utf8');
  for(const change of [s=>s.reviewer.origin='ai',s=>s.reviewer.verification_ref='',s=>s.reviewer.personally_reviewed=false,s=>s.reviewer.reviewer_ref='reviewer_0']){
    const s=JSON.parse(original);change(s);fs.writeFileSync(file,JSON.stringify(s));assert.throws(()=>scoreStudy(out));
  }
});
test('disagreement requires a distinct adjudicator and is not silently excluded',t=>{
  const {out,input}=fixture(t);complete(out,input,{disagree:true});const first=scoreStudy(out);assert.equal(first.disagreements,1);assert.equal(first.pending_references,1);assert.equal(first.metrics,null);
  complete(out,input,{disagree:true,adjudicate:true});assert.equal(scoreStudy(out).pending_references,0);
  const file=path.join(out,'adjudication.json'),s=JSON.parse(fs.readFileSync(file));s.reviewer.reviewer_ref='REVIEWER_0';fs.writeFileSync(file,JSON.stringify(s));assert.throws(()=>scoreStudy(out));
});
test('duplicate source reports and patient overlap across development/evaluation are rejected',()=>{
  for(const change of [x=>x.cases[1].text=x.cases[0].text,x=>{x.cases[0].partition='development';x.cases[1].patient_group=x.cases[0].patient_group;},x=>x.cases[1].case_id=x.cases[0].case_id]){
    const input=example();change(input);assert.throws(()=>inputStudy(input));
  }
});
test('approved deidentified data needs explicit governance declarations but does not establish approval',t=>{
  const {out,input}=fixture(t,x=>{x.data_kind='approved-deidentified-research';});assert.equal(scoreStudy(out).metrics,null);
  for(const key of Object.keys(input.governance)){const x=copy(input);x.governance[key]=key==='permission_attested'?false:'';assert.throws(()=>inputStudy(x));}
});
test('image categories, oversized reports, invented evidence and provider-key model IDs are rejected',()=>{
  for(const change of [x=>x.cases[0].report_type='dicom',x=>x.cases[0].text='x'.repeat(6001),x=>x.provenance.model_id='sk-SENSITIVE_SENTINEL',x=>x.cases[0].prediction.review.findings.push({quote:'invented',assertion:'present',follow_up_quote:'',deadline_quote:''})]){
    const x=example();change(x);assert.throws(()=>inputStudy(x));
  }
});
test('study output under a Git checkout, including a symlink alias, is refused',t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'clinloop-study-path-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const repo=path.join(root,'repo');fs.mkdirSync(repo);fs.mkdirSync(path.join(repo,'.git'));fs.writeFileSync(path.join(repo,'.git','HEAD'),'ref: refs/heads/main');
  const input=path.join(root,'input.json');fs.writeFileSync(input,JSON.stringify(example()));assert.throws(()=>prepare(input,path.join(repo,'study')));
  if(process.platform!=='win32'){fs.symlinkSync(repo,path.join(root,'alias'));assert.throws(()=>prepare(input,path.join(root,'alias','study')));}
});
test('CLI refuses overwrite and prints no report text, paths or parser diagnostics on failure',t=>{
  const {root}=fixture(t),file=path.join(root,'SENSITIVE_SENTINEL.json');fs.writeFileSync(file,'{"patient":"SENSITIVE_SENTINEL"');
  const r=cp.spawnSync(process.execPath,[path.resolve(__dirname,'../scripts/report_study.cjs'),'--action','prepare','--input',file,'--out',path.join(root,'bad')],{encoding:'utf8'});
  assert.equal(r.status,1);assert(!r.stderr.includes('SENSITIVE_SENTINEL'));assert(!r.stderr.includes(root));assert.equal(r.stdout,'');
  const again=cp.spawnSync(process.execPath,[path.resolve(__dirname,'../scripts/report_study.cjs'),'--action','example','--out',file],{encoding:'utf8'});
  assert.equal(again.status,1);assert(fs.readFileSync(file,'utf8').includes('SENSITIVE_SENTINEL'));
});
