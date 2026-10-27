(function () {
  'use strict';
  const $=id=>document.getElementById(id), api=window.ClinLoopReportReview;
  const local=new window.ClinLoopPrivate.Workspace(window.fetch.bind(window));
  const research=new api.Research(window.fetch.bind(window));
  let connected=false,busy=false,loading=false,epoch=0,sourceVersion=0,lastActivity=Date.now(),schema=null;
  function status(text){$('status').textContent=text;}
  function sync(){
    const locked=busy||loading;
    $('local-options').hidden=$('mode').value!=='local';$('research-options').hidden=$('mode').value!=='research';
    const label=api.PROVIDERS[$('provider').value];
    $('provider-destination').textContent=label;$('provider-consent').textContent=label;
    $('connect').disabled=locked||connected;
    for(const id of ['report','report-file','model'])$(id).disabled=!connected||locked;
    $('report-type').disabled=locked;$('complete-confirm').disabled=!connected||locked;
    for(const id of ['local-address','research-address','gateway-code','local-confirm','research-confirm'])$(id).disabled=connected||locked;
    $('sample').disabled=!connected||locked;
    const bytes=new TextEncoder().encode($('report').value).length;
    $('report-budget').textContent=bytes+' / 6000 UTF-8 bytes';
    let valid=false;
    try{api.validText($('report').value,$('report-type').value);valid=true;}catch(_){}
    $('analyze').disabled=!connected||locked||!valid||!$('complete-confirm').checked;
    $('review-readiness').textContent=!connected?'Connect a model in step 1 to enable source entry.':
      loading?'Loading source. Wait for the complete file.':busy?'Review in progress. Wait for source checks.':
      bytes>6000?'Report exceeds 6000 UTF-8 bytes. Use a complete report within the limit; do not remove clinical context to fit.':
      !valid?'Add a complete synthetic report in step 2.':!$('complete-confirm').checked?
      'Check the complete report and confirm it above to enable Review report.':
      'Ready to review. Compare every returned suggestion with the original report.';
  }
  function clear(disconnect=true){
    epoch++;sourceVersion++;local.clear(disconnect);research.clear();busy=false;loading=false;
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
    if(busy||loading||connected)return;
    const current=epoch,mode=$('mode').value,provider=$('provider').value;let setupLoaded=false;busy=true;status('Checking selected connection…');sync();
    try {
      const r=await fetch('data/report_review_schema.json',{cache:'no-store',credentials:'omit',redirect:'error'});
      if(current!==epoch)return;
      if(!r.ok)throw new Error('Review schema unavailable.');const contract=await r.json();
      if(current!==epoch)return;
      let models;
      setupLoaded=true;
      if(mode==='local')models=await local.connect($('local-address').value,$('local-confirm').checked);
      else models=[await research.connect($('research-address').value,$('gateway-code').value,$('research-confirm').checked,provider)];
      if(current!==epoch)return;schema=contract;connected=true;
      $('gateway-code').value='';$('model').replaceChildren(...models.map(m=>new Option(m,m)));
      status($('mode').value==='local'?'Connected to your local model. No cloud fallback.':'Research gateway connected. Synthetic text is sent to '+api.PROVIDERS[research.provider]+' only when you select Review report.');
    }catch(_){if(current===epoch){
      local.clear(true);research.clear();connected=false;$('gateway-code').value='';
      const message=!setupLoaded?'Report review setup could not be loaded. Refresh this page and check your connection.':
        mode==='local'?'Could not connect to local Ollama. Confirm the local-model checkbox, that Ollama is running on this browser’s device, and that https://clinloopai.app is an allowed origin. Allow local-network access if your browser prompts; an embedded browser may block it. See Local connection instructions.':
        api.PROVIDERS[provider]+' research gateway connection failed. Check your local gateway, the selected provider configuration and the gateway access code. Add or update your provider key in Personal API setup on your computer; no key belongs on this public page.';
      status(message+' No report sent.');
    }}
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
      const context=document.createElement('p');context.className='source-context';
      context.textContent='Surrounding source (first match): '+item.source_context;
      const matches=document.createElement('p');matches.textContent=item.source_occurrences>1?
        'This quote occurs '+item.source_occurrences+' times. Review every occurrence in the original report; the first match is shown here.':
        'One exact occurrence found. Verify surrounding negation, dates, units and laterality in the original.';
      section.append(h,q,context,matches,follow,deadline);box.append(section);}
    if (review.unlinked_source_sentences && review.unlinked_source_sentences.length) {
      const title=document.createElement('h3');title.textContent='Source sentences needing follow-up review';box.append(title);
      const warning=document.createElement('p');warning.textContent='These sentences were not linked by the model. They may be conditional or negated. Check the original; no action or deadline has been inferred.';box.append(warning);
      for (const sentence of review.unlinked_source_sentences) {const q=document.createElement('blockquote');q.textContent=sentence;box.append(q);}
    }
    const heading=document.createElement('h3');heading.textContent='Model-noted missing context — verify manually';box.append(heading);
    for(const text of review.missing_context){const p=document.createElement('p');p.textContent=text;box.append(p);}
    if(!review.missing_context.length){const p=document.createElement('p');p.textContent='No missing context listed by the model. This is not a completeness check.';box.append(p);}
  }
  $('analyze').addEventListener('click',async()=>{
    if(!connected||busy||loading)return;
    const current=epoch,version=sourceVersion;const text=$('report').value,type=$('report-type').value,model=$('model').value;
    $('result').replaceChildren();
    try {
      api.validText(text,type);if(!$('complete-confirm').checked)throw new Error('Check the complete synthetic report before reviewing.');
      busy=true;status('Reviewing. No result is accepted until its source quotes are checked.');sync();
      let review;
      if($('mode').value==='local'){
        const raw=await local.run(model,text,{schema,system:api.SYSTEM+' Report category: '+type+'.'});
        review=api.validate(JSON.parse(raw),text);
      }else review=await research.run(text,type,$('research-confirm').checked);
      if(current===epoch&&(version!==sourceVersion||text!==$('report').value||type!==$('report-type').value||model!==$('model').value)){status('Source or model changed. Review again.');return;}
      if(current===epoch){render(review);status('Source matching passed. Clinical interpretation still requires human review.');}
    }catch(error){if(current===epoch){$('result').textContent='No analysis accepted. Review the original report with a clinician.';status(error.message || 'Review failed.');}}
    finally{if(current===epoch){busy=false;sync();}}
  });
  $('report-file').addEventListener('change',async()=>{
    const current=epoch,version=++sourceVersion,file=$('report-file').files[0];$('complete-confirm').checked=false;
    if(!file)return;
    loading=true;$('report').value='';$('result').textContent='Loading new source. No review yet.';status('Loading new source. Analysis is paused.');sync();
    try {api.validateFile(file.name,file.size);const buffer=await file.arrayBuffer();const text=new TextDecoder('utf-8',{fatal:true}).decode(buffer);
      api.validText(text,$('report-type').value);if(current===epoch&&version===sourceVersion){$('report').value=text;$('result').textContent='New source loaded. No review yet.';status('New source loaded. Check completeness before reviewing.');}}
    catch(_){if(current===epoch&&version===sourceVersion){$('report').value='';$('result').textContent='No review yet.';status('File not accepted. Use a complete UTF-8 .txt report up to 6000 bytes; no partial report was loaded.');}}
    finally{if(current===epoch&&version===sourceVersion){loading=false;sync();}}
  });
  function sourceChanged(){sourceVersion++;$('complete-confirm').checked=false;$('result').textContent='Source changed. Review again.';status('Source or model changed. Review again.');sync();}
  $('complete-confirm').addEventListener('change',sync);
  $('report').addEventListener('input',sourceChanged);$('report-type').addEventListener('change',sourceChanged);$('model').addEventListener('change',sourceChanged);
  $('sample').addEventListener('click',()=>{
    sourceVersion++;$('report-type').value='radiology-text';$('complete-confirm').checked=false;$('result').textContent='No review yet.';
    $('report').value='SYNTHETIC REPORT — fictional adult. CT chest: A 6 mm pulmonary nodule is present. No pleural effusion. Recommend comparison with prior imaging. No comparison study is supplied. No follow-up interval is specified.';
    status('Synthetic example loaded. Check completeness before reviewing.');sync();
  });
  for(const name of ['pointerdown','keydown','input'])document.addEventListener(name,()=>{lastActivity=Date.now();},{passive:true});
  setInterval(()=>{if(Date.now()-lastActivity>=600000){clear(true);lastActivity=Date.now();}},10000);
  window.addEventListener('pagehide',()=>clear(true));window.addEventListener('pageshow',event=>{if(event.persisted)clear(true);});
  clear(true);
})();
