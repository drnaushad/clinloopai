(function () {
  'use strict';
  const $=id=>document.getElementById(id), api=window.ClinLoopReportReview;
  const local=new window.ClinLoopPrivate.Workspace(window.fetch.bind(window));
  const research=new api.Research(window.fetch.bind(window));
  let connected=false,busy=false,epoch=0,sourceVersion=0,lastActivity=Date.now(),schema=null;
  function status(text){$('status').textContent=text;}
  function sync(){
    $('local-options').hidden=$('mode').value!=='local';$('research-options').hidden=$('mode').value!=='research';
    const label=api.PROVIDERS[$('provider').value];
    $('provider-destination').textContent=label;$('provider-consent').textContent=label;
    $('connect').disabled=busy||connected;
    for(const id of ['report','report-file','analyze','model'])$(id).disabled=!connected||busy;
    $('report-type').disabled=busy;$('complete-confirm').disabled=busy;
    for(const id of ['local-address','research-address','gateway-code','local-confirm','research-confirm'])$(id).disabled=connected||busy;
    $('sample').disabled=!connected||busy;
  }
  function clear(disconnect=true){
    epoch++;sourceVersion++;local.clear(disconnect);research.clear();busy=false;
    // Research clear removes its bearer code: reconnect is required in that pathway.
    if(disconnect||$('mode').value==='research')connected=false;
    $('report').value='';$('report-file').value='';$('result').replaceChildren();$('result').textContent='No review yet.';
    $('gateway-code').value='';$('complete-confirm').checked=false;
    if(!connected){$('model').replaceChildren(new Option('Connect first',''));$('local-confirm').checked=false;$('research-confirm').checked=false;}
    status(connected?'Report cleared. Local model connection retained.':'Disconnected. Session cleared.');sync();
  }
  $('mode').addEventListener('change',()=>clear(true));
  $('provider').addEventListener('change',()=>clear(true));
  $('disconnect').addEventListener('click',()=>clear(true));$('clear').addEventListener('click',()=>clear(false));
  $('connect').addEventListener('click',async()=>{
    const current=epoch;busy=true;status('Checking selected connection…');sync();
    try {
      const r=await fetch('data/report_review_schema.json',{cache:'no-store',credentials:'omit',redirect:'error'});
      if(!r.ok)throw new Error('Review schema unavailable.');const contract=await r.json();
      let models;
      if($('mode').value==='local')models=await local.connect($('local-address').value,$('local-confirm').checked);
      else models=[await research.connect($('research-address').value,$('gateway-code').value,$('research-confirm').checked,$('provider').value)];
      if(current!==epoch)return;schema=contract;connected=true;
      $('gateway-code').value='';$('model').replaceChildren(...models.map(m=>new Option(m,m)));
      status($('mode').value==='local'?'Connected to your local model. No cloud fallback.':'Research gateway connected. Synthetic text is sent to '+api.PROVIDERS[research.provider]+' only when you select Review report.');
    }catch(_){if(current===epoch){local.clear(true);research.clear();connected=false;$('gateway-code').value='';status('Connection failed. Check the selected provider configuration, local service, exact allowed website origin and access code. No report sent.');}}
    finally{if(current===epoch){busy=false;sync();}}
  });
  function render(review){
    const box=$('result');box.replaceChildren();
    const notice=document.createElement('p');notice.textContent='Unverified model extraction — clinician review required. No diagnosis, treatment decision or follow-up closure was made.';box.append(notice);
    if(!review.findings.length){const p=document.createElement('p');p.textContent='No source-backed findings returned. This does not establish a normal report; review the original.';box.append(p);}
    for(const item of review.findings){const section=document.createElement('article');
      const h=document.createElement('h3');h.textContent='Model assertion: '+item.assertion+' — verify against context';
      const q=document.createElement('blockquote');q.textContent=item.quote;
      const follow=document.createElement('p');follow.textContent=item.follow_up_quote?'Quoted follow-up: '+item.follow_up_quote:'No explicit follow-up quoted; this does not exclude a required follow-up.';
      const deadline=document.createElement('p');deadline.textContent=item.deadline_quote?'Quoted timing: '+item.deadline_quote:'No source timing quoted. No deadline calculated.';
      section.append(h,q,follow,deadline);box.append(section);}
    const heading=document.createElement('h3');heading.textContent='Model-noted missing context — verify manually';box.append(heading);
    for(const text of review.missing_context){const p=document.createElement('p');p.textContent=text;box.append(p);}
    if(!review.missing_context.length){const p=document.createElement('p');p.textContent='No missing context listed by the model. This is not a completeness check.';box.append(p);}
  }
  $('analyze').addEventListener('click',async()=>{
    if(!connected||busy)return;
    const current=epoch;const text=$('report').value,type=$('report-type').value;
    $('result').replaceChildren();
    try {
      api.validText(text,type);if(!$('complete-confirm').checked)throw new Error('Check the complete synthetic report before reviewing.');
      busy=true;status('Reviewing. No result is accepted until its source quotes are checked.');sync();
      let review;
      if($('mode').value==='local'){
        const raw=await local.run($('model').value,text,{schema,system:api.SYSTEM+' Report category: '+type+'.'});
        review=api.validate(JSON.parse(raw),text);
      }else review=await research.run(text,type,$('research-confirm').checked);
      if(current===epoch){render(review);status('Source matching passed. Clinical interpretation still requires human review.');}
    }catch(error){if(current===epoch){$('result').textContent='No analysis accepted. Review the original report with a clinician.';status(error.message || 'Review failed.');}}
    finally{if(current===epoch){busy=false;sync();}}
  });
  $('report-file').addEventListener('change',async()=>{
    const current=epoch,version=++sourceVersion,file=$('report-file').files[0];$('complete-confirm').checked=false;
    if(!file)return;
    try {api.validateFile(file.name,file.size);const buffer=await file.arrayBuffer();const text=new TextDecoder('utf-8',{fatal:true}).decode(buffer);
      api.validText(text,$('report-type').value);if(current===epoch&&version===sourceVersion){$('report').value=text;$('result').textContent='New source loaded. No review yet.';}}
    catch(_){if(current===epoch&&version===sourceVersion){$('report').value='';$('result').textContent='No review yet.';status('File not accepted. Use a complete UTF-8 .txt report up to 6000 bytes; no partial report was loaded.');}}
  });
  function sourceChanged(){sourceVersion++;$('complete-confirm').checked=false;$('result').textContent='Source changed. Review again.';}
  $('report').addEventListener('input',sourceChanged);$('report-type').addEventListener('change',sourceChanged);
  $('sample').addEventListener('click',()=>{
    sourceVersion++;$('report-type').value='radiology-text';$('complete-confirm').checked=false;$('result').textContent='No review yet.';
    $('report').value='SYNTHETIC REPORT — fictional adult. CT chest: A 6 mm pulmonary nodule is present. No pleural effusion. Recommend comparison with prior imaging. No comparison study is supplied. No follow-up interval is specified.';
  });
  for(const name of ['pointerdown','keydown','input'])document.addEventListener(name,()=>{lastActivity=Date.now();},{passive:true});
  setInterval(()=>{if(Date.now()-lastActivity>=600000){clear(true);lastActivity=Date.now();}},10000);
  window.addEventListener('pagehide',()=>clear(true));window.addEventListener('pageshow',event=>{if(event.persisted)clear(true);});
  clear(true);
})();
