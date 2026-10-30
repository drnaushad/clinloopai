'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
if(!global.crypto)Object.defineProperty(global,'crypto',{value:require('node:crypto').webcrypto});
global.ClinLoopPrivate=require('../js/private-workspace.js');
const {kind,Importer}=require('../js/report-file-import.js');
const CODE='synthetic_gateway_code_'+'x'.repeat(32);
const doc={kind:'pdf',text:'SYNTHETIC original source.',pages:[{number:1,text:'SYNTHETIC original source.',method:'pdf-text',confidence:null}],page_count:1,text_review_allowed:true,sha256:require('node:crypto').createHash('sha256').update(Buffer.from([37,80,68,70,45])).digest('hex'),external_model_called:false,human_check_required:true};
const file={name:'synthetic.pdf',size:5,arrayBuffer:async()=>new Uint8Array([37,80,68,70,45]).buffer};
function importer(value=doc){const calls=[];return {calls,client:new Importer(async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify(value),{status:200});})};}
test('file type and byte bounds reject unsupported and oversized inputs before reading',()=>{
 for(const [name,size] of [['report.exe',5],['a.pdf',0],['a.pdf',5242881],['a.txt',6001]])assert.throws(()=>kind(name,size));
 for(const ext of ['txt','pdf','png','jpg','jpeg','tif','tiff','dcm'])assert.equal(kind('SYNTHETIC.'+ext.toUpperCase(),3),ext);
});
test('binary import goes only to the selected loopback endpoint without cookies or fallback',async()=>{
 const {client,calls}=importer();assert.deepEqual(await client.run(file,'http://127.0.0.1:18127',CODE,true,'eng'),doc);
 assert.equal(calls.length,1);assert.equal(calls[0].url,'http://127.0.0.1:18127/review/files/import');
 const opts=calls[0].options;assert.equal(opts.credentials,'omit');assert.equal(opts.redirect,'error');assert.equal(opts.cache,'no-store');
 const body=JSON.parse(opts.body);assert.equal(body.content_base64,'JVBERi0=');assert(body.synthetic_only&&body.local_processing_allowed);assert(!('filename' in body));
});
test('consent, access code and local address are checked before any network request',async()=>{
 for(const changes of [{confirmed:false},{address:'https://cloud.test'},{code:'sk-not-a-gateway-code'},{language:'unknown'}]){
  const {client,calls}=importer();await assert.rejects(client.run(file,changes.address||'http://localhost:18127',changes.code||CODE,changes.confirmed??true,changes.language||'eng'));assert.equal(calls.length,0);
 }
});
test('malformed, inconsistent and oversized responses never become source text',async()=>{
 for(const value of [{...doc,text:'different'}, {...doc,pages:[]},{...doc,external_model_called:true},{...doc,sha256:'wrong'},{...doc,text:'x'.repeat(120001)},{...doc,kind:'dicom-image',text_review_allowed:true}]){
  const {client}=importer(value);await assert.rejects(client.run(file,'http://127.0.0.1:18127',CODE,true,'eng'));
 }
});
test('clearing during file read prevents a late import from sending any bytes',async()=>{
 let finish;const pending=new Promise(r=>finish=r);const {client,calls}=importer();const task=client.run({...file,arrayBuffer:()=>pending},'http://localhost:18127',CODE,true,'eng');
 client.clear();finish(new Uint8Array(5).buffer);await assert.rejects(task);assert.equal(calls.length,0);
});

test('a valid-looking digest for a different document cannot be accepted',async()=>{
 const {client}=importer({...doc,sha256:'f'.repeat(64)});
 await assert.rejects(client.run(file,'http://127.0.0.1:18127',CODE,true,'eng'),/Unexpected file response/);
});
