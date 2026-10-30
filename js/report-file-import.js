/* Local file extraction only: never send a binary file to a model provider. */
(function(root){
  'use strict';
  const MAX_BYTES=5*1024*1024;
  const EXTENSIONS=['pdf','png','jpg','jpeg','tif','tiff','dcm'];
  function kind(name,size){
    if(typeof name!=='string'||!Number.isInteger(size)||size<1||size>MAX_BYTES)throw Error('Choose a non-empty file up to 5 MB.');
    const ext=name.toLowerCase().split('.').pop();
    if(ext!=='txt'&&!EXTENSIONS.includes(ext))throw Error('Choose TXT, PDF, PNG, JPEG, TIFF or DICOM.');
    if(ext==='txt'&&size>6000)throw Error('Text reports must fit within 6000 UTF-8 bytes. Nothing was truncated.');
    return ext;
  }
  class Importer{
    constructor(fetcher){this.fetcher=fetcher;this.epoch=0;this.controller=null;}
    clear(){this.epoch++;if(this.controller)this.controller.abort();this.controller=null;}
    async run(file,address,code,confirmed,language){
      const ext=kind(file.name,file.size);
      if(ext==='txt')throw Error('Read text files directly in this browser.');
      if(confirmed!==true)throw Error('Confirm synthetic local file processing first.');
      const base=root.ClinLoopPrivate.localAddress(address);
      if(typeof code!=='string'||!/^[A-Za-z0-9_-]{32,128}$/.test(code)||/^(?:sk-|AIza)/i.test(code))throw Error('Enter the separate local gateway access code, not a provider API key.');
      if(!['eng','kor+eng'].includes(language))throw Error('Choose an OCR language.');
      this.clear();const epoch=this.epoch,c=new AbortController();this.controller=c;
      const timeout=setTimeout(()=>c.abort(),100000);
      try{
        const bytes=new Uint8Array(await file.arrayBuffer());
        if(epoch!==this.epoch||bytes.length!==file.size)throw Error('File import cancelled.');
        if(!root.crypto||!root.crypto.subtle)throw Error('File integrity checks are unavailable. Use an approved secure local installation.');
        const digest=Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
        if(epoch!==this.epoch||c.signal.aborted)throw Error('File import cancelled.');
        let binary='';for(let start=0;start<bytes.length;start+=8192)binary+=String.fromCharCode(...bytes.subarray(start,start+8192));
        const r=await this.fetcher(base+'/review/files/import',{method:'POST',credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',signal:c.signal,
          headers:{Authorization:'Bearer '+code,'Content-Type':'application/json'},body:JSON.stringify({extension:ext,content_base64:root.btoa(binary),ocr_language:language,synthetic_only:true,local_processing_allowed:true})});
        if(epoch!==this.epoch||!r.ok)throw Error('Local file processing failed. Check the gateway, file tools, OCR languages and access code. Nothing was sent to a model.');
        const reader=r.body.getReader();let chunks=[],size=0;
        while(true){const chunk=await reader.read();if(chunk.done)break;size+=chunk.value.length;if(size>600000){await reader.cancel();throw Error('Import response too large.');}chunks.push(chunk.value);}
        const raw=new Uint8Array(size);let offset=0;for(const chunk of chunks){raw.set(chunk,offset);offset+=chunk.length;}
        const data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
        if(epoch!==this.epoch||c.signal.aborted)throw Error('File import cancelled.');
        if(!data||typeof data.text!=='string'||new TextEncoder().encode(data.text).length>120000||typeof data.text_review_allowed!=='boolean'||
          !Array.isArray(data.pages)||data.pages.length>20||data.page_count!==data.pages.length||data.external_model_called!==false||data.human_check_required!==true||
          data.sha256!==digest||!['pdf','image','dicom-pdf','dicom-sr','dicom-image'].includes(data.kind)||
          data.pages.some((p,i)=>p.number!==i+1||typeof p.text!=='string'||!['pdf-text','ocr','dicom-sr'].includes(p.method))||
          data.text!==data.pages.map(p=>p.text).join('\n\n')||
          (data.kind==='dicom-image'&&(data.text_review_allowed||data.text||data.pages.length))||
          (data.kind!=='dicom-image'&&data.pages.length===0))throw Error('Unexpected file response. Check the original document.');
        return data;
      }finally{clearTimeout(timeout);if(epoch===this.epoch)this.controller=null;}
    }
  }
  const api={kind,Importer};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ClinLoopFileImport=api;
})(typeof window==='undefined'?globalThis:window);
