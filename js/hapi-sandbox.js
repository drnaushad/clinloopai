/* Read only one known ClinLoop synthetic cohort. No login, writes, storage or inference. */
(function (root) {
  'use strict';
  const BASE='https://hapi.fhir.org/baseR4';
  const TAG_SYSTEM='https://clinloopai.app/testing/synthetic-cohort';
  const COHORT=Object.freeze({"tag": "synthetic-f7959382d7f84e31b693bcbad2fa5c72", "patients": ["clsynt-0a02f6605bc451f484b8fc59101a9715", "clsynt-29200ffcc5ac588c8a2f34aa8a526909", "clsynt-2ed0201ca7285f758f695c7022deb7dc", "clsynt-4ca72f31244d5825bfbaede11f4b19d1", "clsynt-6707b35108505448abdb0ccae9be20e3", "clsynt-88a5599fdc8b5d4f8d97c89d6fb9b54a", "clsynt-94f01690e0a55958a5fa0a60d8af9284", "clsynt-a2bbe53345605f4da042d7baf8dae8ec", "clsynt-bea9729c4e7c5d85ac328b7a7db36e55", "clsynt-d022d5ec36c550859074b8636f825f74", "clsynt-e28c8436d4c758759e6f663c7e3cbe88"], "reports": ["clsynt-2c92624f08475d2798806ddd16c18a89", "clsynt-3d3fd3bce70850518c021b26115d3da6", "clsynt-a2ed0f8ca013506ca00d45d61defa634", "clsynt-a4e5271d6f775ca4b10a7e579f36dbf0"]});
  Object.freeze(COHORT.patients);Object.freeze(COHORT.reports);
  const failure=()=>{throw new Error('HAPI test connection could not be verified. No clinical conclusion was made.');};
  function tagged(resource){
    return Array.isArray(resource.meta?.tag)&&[COHORT.tag,'SYNTHETIC_ONLY'].every(code=>resource.meta.tag.some(t=>t?.system===TAG_SYSTEM&&t.code===code));
  }
  function bundle(body,type){
    if(!body||body.resourceType!=='Bundle'||body.type!=='searchset'||
      (body.entry!==undefined&&!Array.isArray(body.entry))||(body.entry?.length||0)>20||
      (body.link!==undefined&&(!Array.isArray(body.link)||body.link.some(l=>!l||typeof l.relation!=='string'))))failure();
    if((body.entry||[]).some(e=>e?.search?.mode==='outcome'))failure();
    const rows=(body.entry||[]).map(e=>e?.resource);
    if(rows.some(r=>!r||r.resourceType!==type||!tagged(r)))failure();
    if(new Set(rows.map(r=>r.id)).size!==rows.length)failure();
    return {rows,partial:(body.link||[]).some(l=>l.relation==='next')||
      (Number.isFinite(body.total)&&body.total>rows.length)};
  }
  function records(patients,reports){
    const p=bundle(patients,'Patient'),r=bundle(reports,'DiagnosticReport');
    if(!p.rows.length||p.rows.some(row=>!COHORT.patients.includes(row.id)))failure();
    const ids=new Set(p.rows.map(row=>row.id));
    const output=r.rows.map(row=>{
      if(!COHORT.reports.includes(row.id)||typeof row.subject?.reference!=='string'||!ids.has(row.subject.reference.replace(/^Patient\//,''))||
        !row.subject.reference.startsWith('Patient/')||typeof row.status!=='string'||row.status.length>80||
        (row.conclusion!==undefined&&(typeof row.conclusion!=='string'||row.conclusion.length>12000)))failure();
      return {status:row.status,conclusion:row.conclusion||'No plain-text conclusion supplied. Review the source report.'};
    });
    return {patients:p.rows.length,reports:output,partial:p.partial||r.partial,
      clinical_accuracy_established:false};
  }
  class HapiSandbox {
    #fetch; #controller=new AbortController(); #closed=false; #busy=false;
    constructor({fetcher=root.fetch.bind(root)}={}){this.#fetch=fetcher;}
    close(){this.#closed=true;this.#controller.abort();}
    async #json(path){
      if(this.#closed)failure();
      const controller=new AbortController(),abort=()=>controller.abort();
      this.#controller.signal.addEventListener('abort',abort,{once:true});
      const timer=setTimeout(abort,25000);
      try{
        const response=await this.#fetch(BASE+path,{method:'GET',headers:{Accept:'application/fhir+json'},
          credentials:'omit',redirect:'error',cache:'no-store',referrerPolicy:'no-referrer',signal:controller.signal});
        if(!response.ok||!/^application\/(?:fhir\+)?json\b/i.test(response.headers.get('content-type')||''))failure();
        const reader=response.body.getReader(),decoder=new TextDecoder();let text='',bytes=0;
        for(;;){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;
          if(bytes>2*1024*1024){await reader.cancel();failure();}text+=decoder.decode(value,{stream:true});}
        text+=decoder.decode();if(this.#closed||controller.signal.aborted)failure();return JSON.parse(text);
      }finally{clearTimeout(timer);this.#controller.signal.removeEventListener('abort',abort);}
    }
    async connect(confirmed){
      if(confirmed!==true||this.#closed||this.#busy)failure();this.#busy=true;
      try{
        const metadata=await this.#json('/metadata');
        if(metadata.resourceType!=='CapabilityStatement'||!/^4\.0\./.test(metadata.fhirVersion||''))failure();
        const query='?'+new URLSearchParams({_tag:TAG_SYSTEM+'|'+COHORT.tag,_count:'20'});
        const patients=await this.#json('/Patient'+query);
        const reports=await this.#json('/DiagnosticReport'+query);
        return {...records(patients,reports),fhir_version:metadata.fhirVersion};
      }finally{this.#busy=false;}
    }
  }
  function mount({document:doc=root.document,window:win=root,createClient=()=>new HapiSandbox(),
    schedule=setTimeout,cancel=clearTimeout}={}){
    const start=doc.getElementById('hapi-connect');if(!start)return;
    const status=doc.getElementById('hapi-status'),output=doc.getElementById('hapi-reports'),
      confirmation=doc.getElementById('hapi-synthetic'),disconnect=doc.getElementById('hapi-disconnect');
    let client=null,epoch=0,timer;
    function clear(message){epoch++;if(client)client.close();client=null;cancel(timer);output.replaceChildren();
      status.textContent=message;start.disabled=false;}
    function touch(){cancel(timer);if(client)timer=schedule(()=>clear('HAPI session expired. Reconnect to read the synthetic cohort again.'),10*60*1000);}
    disconnect.addEventListener('click',()=>clear('Disconnected. Synthetic HAPI reports cleared from this page.'));
    win.addEventListener('pagehide',()=>clear('Disconnected.'));
    win.addEventListener('pageshow',e=>{if(e.persisted)clear('Disconnected. Reconnect to read the synthetic cohort again.');});
    doc.addEventListener('pointerdown',touch);doc.addEventListener('keydown',touch);
    start.addEventListener('click',async()=>{
      if(!confirmation.checked){status.textContent='Confirm the synthetic test cohort before connecting.';return;}
      clear('Connecting to HAPI FHIR R4…');client=createClient();const job=epoch;start.disabled=true;touch();
      try{
        const result=await client.connect(true);if(job!==epoch)return;
        status.textContent='Connected to HAPI FHIR R4. '+result.patients+' synthetic patients verified; '+result.reports.length+' source reports received.';
        const note=doc.createElement('p');note.textContent=result.partial?'Partial test cohort returned. Missing data does not establish normal results or completed care.':'Read-only source preview. This connection does not run clinical analysis or a language model.';output.appendChild(note);
        for(const report of result.reports){const article=doc.createElement('article'),h=doc.createElement('h3'),p=doc.createElement('p');
          h.textContent='Synthetic report · '+report.status;p.className='report-text';p.textContent=report.conclusion;article.append(h,p);output.appendChild(article);}
        if(!result.reports.length){const empty=doc.createElement('p');empty.textContent='No reports returned. This does not establish normal results.';output.appendChild(empty);}
      }catch(_){if(job===epoch)clear('HAPI test connection could not be verified. The public test cohort may be unavailable; no clinical conclusion was made.');}
    });
  }
  const api={HapiSandbox,records,mount,BASE,COHORT,TAG_SYSTEM};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else{root.ClinLoopHapiSandbox=api;mount();}
})(typeof globalThis!=='undefined'?globalThis:this);
