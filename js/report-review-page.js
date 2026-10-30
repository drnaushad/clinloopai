(function () {
  'use strict';
  const ui=(typeof window !== 'undefined' && window.ClinLoopUI)||{set:(e,v)=>{e.textContent=v;},source:(e,v)=>{e.textContent=v;},reset:()=>{}};
  const placeholder=()=>{const option=new Option('Connect first','');ui.set(option,'Connect first');return option;};
  const $=id=>document.getElementById(id), api=window.ClinLoopReportReview;
  const local=new window.ClinLoopPrivate.Workspace(window.fetch.bind(window));
  const research=new api.Research(window.fetch.bind(window));
  const fileImporter=window.ClinLoopFileImport?new window.ClinLoopFileImport.Importer(window.fetch.bind(window)):null;
  let importedDocument=null;
  let connected=false,busy=false,loading=false,epoch=0,sourceVersion=0,lastActivity=Date.now(),schema=null;
  function status(text){ui.set($('status'), text);}
  function syncChoices(){
    const selected=$('mode').value==='local'?'local':$('provider').value;
    for(const choice of ['local','openai','anthropic','gemini']){
      const button=$('choose-'+choice);
      if(button)button.setAttribute('aria-pressed',String(choice===selected));
    }
    const summary=$('connection-summary');
    if(summary)ui.set(summary, selected==='local'?
      'Local LLM selected. Connect your Ollama; no provider API key is needed.':
      api.PROVIDERS[selected]+' selected. Add its API key in Personal API setup, then connect your gateway.');
    const link=$('personal-setup-link');
    if(link)link.href='http://127.0.0.1:18127/setup?provider='+$('provider').value+'&lang='+(document.documentElement.lang==='ko'?'ko':'en');
  }
  function sync(){
    syncChoices();
    const locked=busy||loading;
    $('local-options').hidden=$('mode').value!=='local';$('research-options').hidden=$('mode').value!=='research';
    const label=api.PROVIDERS[$('provider').value];
    ui.set($('provider-destination'), label);ui.set($('provider-consent'), label);
    $('connect').disabled=locked||connected;
    for(const id of ['report','report-file'])$(id).disabled=locked;
    $('model').disabled=!connected||locked;
    $('report-type').disabled=locked;$('complete-confirm').disabled=locked||!$('report').value.trim()||(importedDocument&&!importedDocument.text_review_allowed);
    for(const id of ['local-address','research-address','gateway-code','local-confirm','research-confirm'])$(id).disabled=connected||locked;
    $('sample').disabled=locked;
    for(const id of ['file-address','file-code','file-confirm','ocr-language'])if($(id))$(id).disabled=locked;
    const bytes=new TextEncoder().encode($('report').value).length;
    ui.set($('report-budget'), bytes+' / 6000 UTF-8 bytes');
    let valid=false;
    try{api.validText($('report').value,$('report-type').value);valid=true;}catch(_){}
    const blocked=importedDocument&&!importedDocument.text_review_allowed;
    $('analyze').disabled=!connected||locked||!valid||!$('complete-confirm').checked||blocked;
    if($('check-source'))$('check-source').disabled=locked;
    if($('load-file'))$('load-file').disabled=locked;
    ui.set($('review-readiness'), loading?'Loading source. Wait for the complete file.':busy?'Review in progress. Wait for source checks.':
      blocked?'DICOM preview only. Non-text or incomplete content cannot enter text analysis.':
      bytes>6000?'Report exceeds 6000 UTF-8 bytes. Use a complete report within the limit; do not remove clinical context to fit.':
      !connected?'You can load and check a report now. Connect a model before selecting Review report.':
      !valid?'Add a complete synthetic report in step 2.':!$('complete-confirm').checked?
      'Check the complete report and confirm it above to enable Review report.':
      'Ready to review. Compare every returned suggestion with the original report.');
  }
  function clear(disconnect=true){
    epoch++;sourceVersion++;local.clear(disconnect);research.clear();if(fileImporter)fileImporter.clear();busy=false;loading=false;importedDocument=null;
    // Research clear removes its bearer code: reconnect is required in that pathway.
    if(disconnect||$('mode').value==='research')connected=false;
    $('report').value='';$('report-file').value='';$('result').replaceChildren();ui.set($('result'), 'No review yet.');
    $('gateway-code').value='';$('complete-confirm').checked=false;
    if($('file-code'))$('file-code').value='';if($('file-confirm'))$('file-confirm').checked=false;
    if($('file-preview'))$('file-preview').replaceChildren();
    if(!connected){$('model').replaceChildren(placeholder());$('local-confirm').checked=false;$('research-confirm').checked=false;}
    status(connected?'Report cleared. Local model connection retained.':'Disconnected. Session cleared.');sync();
  }
  $('mode').addEventListener('change',()=>clear(true));
  $('provider').addEventListener('change',()=>clear(true));
  for(const choice of ['local','openai','anthropic','gemini']){
    const button=$('choose-'+choice);
    if(button)button.addEventListener('click',()=>{
      const mode=choice==='local'?'local':'research';
      if($('mode').value===mode&&(mode==='local'||$('provider').value===choice))return;
      $('mode').value=mode;if(mode==='research')$('provider').value=choice;
      clear(true); // An explicit provider change invalidates consent, source and pending results.
    });
  }
  if(window.MutationObserver)new window.MutationObserver(syncChoices).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  $('disconnect').addEventListener('click',()=>clear(true));$('clear').addEventListener('click',()=>clear(false));
  $('connect').addEventListener('click',async()=>{
    if(expireIfIdle())return;
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
    const box=$('result');ui.reset(box);box.replaceChildren();
    const notice=document.createElement('p');ui.set(notice, 'Unverified model extraction — clinician review required. No diagnosis, treatment decision or follow-up closure was made.');box.append(notice);
    if(!review.findings.length){const p=document.createElement('p');ui.set(p, 'No source-backed findings returned. This does not establish a normal report; review the original.');box.append(p);}
    for(const item of review.findings){const section=document.createElement('article');
      const h=document.createElement('h3');ui.set(h, 'Model assertion: '+item.assertion+' — verify against context');
      const q=document.createElement('blockquote');q.textContent=item.quote;
      const follow=document.createElement('p');if(item.follow_up_quote){const label=document.createElement('span');ui.set(label,'Quoted follow-up: ');follow.append(label,document.createTextNode(item.follow_up_quote));}else ui.set(follow,'No explicit follow-up quoted; this does not exclude a required follow-up.');
      const deadline=document.createElement('p');if(item.deadline_quote){const label=document.createElement('span');ui.set(label,'Quoted timing: ');deadline.append(label,document.createTextNode(item.deadline_quote));}else ui.set(deadline,'No source timing quoted. No deadline calculated.');
      const context=document.createElement('p');context.className='source-context';
      const prefix=document.createElement('span');ui.set(prefix,'Surrounding source (first match): ');context.append(prefix,document.createTextNode(item.source_context));
      const matches=document.createElement('p');ui.set(matches, item.source_occurrences>1?
        'This quote occurs '+item.source_occurrences+' times. Review every occurrence in the original report; the first match is shown here.':
        'One exact occurrence found. Verify surrounding negation, dates, units and laterality in the original.');
      section.append(h,q,context,matches,follow,deadline);box.append(section);}
    if (review.unlinked_source_sentences && review.unlinked_source_sentences.length) {
      const title=document.createElement('h3');ui.set(title, 'Source sentences needing follow-up review');box.append(title);
      const warning=document.createElement('p');ui.set(warning, 'These sentences were not linked by the model. They may be conditional or negated. Check the original; no action or deadline has been inferred.');box.append(warning);
      for (const sentence of review.unlinked_source_sentences) {const q=document.createElement('blockquote');q.textContent=sentence;box.append(q);}
    }
    const heading=document.createElement('h3');ui.set(heading, 'Model-noted missing context — verify manually');box.append(heading);
    for(const text of review.missing_context){const p=document.createElement('p');p.textContent=text;box.append(p);}
    if(!review.missing_context.length){const p=document.createElement('p');ui.set(p, 'No missing context listed by the model. This is not a completeness check.');box.append(p);}
  }
  $('analyze').addEventListener('click',async()=>{
    if(expireIfIdle())return;
    if(!connected||busy||loading)return;
    const current=epoch,version=sourceVersion;const text=$('report').value,type=$('report-type').value,model=$('model').value;
    $('result').replaceChildren();
    try {
      api.validText(text,type);if((importedDocument&&!importedDocument.text_review_allowed)||!$('complete-confirm').checked)throw new Error('Check the complete synthetic report before reviewing.');
      busy=true;status('Reviewing. No result is accepted until its source quotes are checked.');sync();
      let review;
      if($('mode').value==='local'){
        const raw=await local.run(model,text,{schema,system:api.SYSTEM+' Report category: '+type+'.'});
        review=api.validate(JSON.parse(raw),text);
      }else review=await research.run(text,type,$('research-confirm').checked);
      if(current===epoch&&(version!==sourceVersion||text!==$('report').value||type!==$('report-type').value||model!==$('model').value)){status('Source or model changed. Review again.');return;}
      if(current===epoch){render(review);status('Source matching passed. Clinical interpretation still requires human review.');}
    }catch(error){if(current===epoch){ui.set($('result'), 'No analysis accepted. Review the original report with a clinician.');status(error.message || 'Review failed.');}}
    finally{if(current===epoch){busy=false;sync();}}
  });
  async function loadSelectedFile(){
    if(expireIfIdle())return;
    if(busy||loading)return;
    const current=epoch,version=++sourceVersion,file=$('report-file').files[0];$('complete-confirm').checked=false;
    if(!file)return;importedDocument=null;if($('file-preview'))$('file-preview').replaceChildren();
    loading=true;$('report').value='';ui.set($('result'), 'Loading new source. No review yet.');status('Loading new source. Analysis is paused.');sync();
    try {
      const ext=window.ClinLoopFileImport?window.ClinLoopFileImport.kind(file.name,file.size):'txt';let text;
      if(ext==='txt'){
        api.validateFile(file.name,file.size);const buffer=await file.arrayBuffer();text=new TextDecoder('utf-8',{fatal:true}).decode(buffer);api.validText(text,$('report-type').value);
      }else{
        if($('file-options'))$('file-options').open=true;
        if(!fileImporter)throw Error('Local file tools unavailable.');
        const data=await fileImporter.run(file,$('file-address').value,$('file-code').value,$('file-confirm').checked,$('ocr-language').value);
        if(current!==epoch||version!==sourceVersion)return;
        importedDocument=data;text=data.text;
        const box=$('file-preview');box.replaceChildren();
        const heading=document.createElement('p');ui.set(heading,'Imported locally. Check every page, number, unit and date against the original. No model was called.');box.append(heading);
        const meta=document.createElement('p');meta.textContent=data.kind+' · '+data.page_count+' · SHA-256 '+data.sha256;box.append(meta);
        if(data.kind.startsWith('dicom-')){
          const notice=document.createElement('p');ui.set(notice,data.kind==='dicom-image'?
            'DICOM image imported for inspection only. Pixel interpretation is not supported by text models.':
            !data.text_review_allowed?'DICOM report is incomplete or contains non-text content. Preview only; text analysis is blocked.':
            'DICOM report text extracted. Check all values, units and context against the original. No pixels were analyzed.');box.append(notice);
        }
        for(const page of data.pages){const detail=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');ui.set(summary,'Source page '+page.number+' · '+page.method);pre.textContent=page.text;detail.append(summary,pre);box.append(detail);}
      }
      if(current===epoch&&version===sourceVersion){$('report').value=text;ui.set($('result'), 'New source loaded. No review yet.');status(importedDocument&&!importedDocument.text_review_allowed?'DICOM preview only. Non-text or incomplete content cannot enter text analysis.':'New source loaded. Check completeness before reviewing.');}
    }
    catch(_){if(current===epoch&&version===sourceVersion){$('report').value='';importedDocument=null;ui.set($('result'), 'No review yet.');status('File import failed. TXT loads in this browser. For PDF, image or DICOM, start your updated personal gateway with --setup, check its access code and confirm local processing. No partial source was loaded.');}}
    finally{if(current===epoch&&version===sourceVersion){loading=false;sync();}}
  }
  $('report-file').addEventListener('change',loadSelectedFile);
  if($('load-file'))$('load-file').addEventListener('click',loadSelectedFile);
  function sourceChanged(){sourceVersion++;$('complete-confirm').checked=false;ui.set($('result'), 'Source changed. Review again.');status('Source or model changed. Review again.');sync();}
  $('complete-confirm').addEventListener('change',sync);
  $('report').addEventListener('input',sourceChanged);$('report-type').addEventListener('change',sourceChanged);$('model').addEventListener('change',sourceChanged);
  $('sample').addEventListener('click',()=>{
    sourceVersion++;importedDocument=null;if($('file-preview'))$('file-preview').replaceChildren();$('report-type').value='radiology-text';$('complete-confirm').checked=false;ui.set($('result'), 'No review yet.');
    $('report').value='SYNTHETIC REPORT — fictional adult. CT chest: A 6 mm pulmonary nodule is present. No pleural effusion. Recommend comparison with prior imaging. No comparison study is supplied. No follow-up interval is specified.';
    status('Synthetic example loaded. Check completeness before reviewing.');sync();
  });
  if($('check-source'))$('check-source').addEventListener('click',()=>{
    try{api.validText($('report').value,$('report-type').value);if(importedDocument&&!importedDocument.text_review_allowed)throw Error('blocked');
      status('Input size and format check passed. This does not verify extraction, completeness or medical accuracy. Check the original before confirming.');
    }catch(_){status('Input check did not pass. Use complete readable text within 6000 UTF-8 bytes; DICOM image or incomplete SR needs its own workflow. Nothing was sent.');}sync();
  });
  function expireIfIdle(){
    if(Date.now()-lastActivity<600000)return false;
    clear(true);lastActivity=Date.now();return true;
  }
  for(const name of ['pointerdown','keydown','input'])document.addEventListener(name,()=>{expireIfIdle();lastActivity=Date.now();},{passive:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)expireIfIdle();});
  setInterval(expireIfIdle,10000);
  window.addEventListener('pagehide',()=>clear(true));window.addEventListener('pageshow',event=>{if(event.persisted)clear(true);else expireIfIdle();});
  // Non-secret link hints only; never accept credentials, report text or arbitrary endpoints.
  if(window.URLSearchParams){
    const requested=new window.URLSearchParams(window.location.search).get('provider');
    if(Object.prototype.hasOwnProperty.call(api.PROVIDERS,requested)){
      $('mode').value='research';$('provider').value=requested;
    }
  }
  clear(true);
})();
