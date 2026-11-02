const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
const html=fs.readFileSync('analyse.html','utf8'),start=html.indexOf('  let engine = null;'),end=html.indexOf('\n  async function analyseHere');
const loader=html.slice(start,end)+'\nstartEngine();';
async function attempt(change=()=>{},http=200){
 const manifest=JSON.parse(fs.readFileSync('js/engine_manifest.json','utf8'));
 const sources={files:Object.fromEntries(manifest.files.map(f=>[f,fs.readFileSync(f,'utf8')]))};change(manifest,sources);
 const writes=[],calls=[];
 const py={loadPackage:async()=>{},FS:{mkdirTree:()=>{},writeFile:(p,text)=>writes.push(p)},runPython:()=>{},pyimport:()=>({analyse_json:()=>{}})};
 const context={crypto:webcrypto,TextEncoder,Uint8Array,PYODIDE_URL:'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/',setRun:()=>{},t:()=>({}),
  window:{loadPyodide:async()=>{calls.push('runtime');return py;}},fetch:async path=>({ok:http===200,json:async()=>path==='js/engine_manifest.json'?manifest:sources})};
 try{await vm.runInNewContext(loader,context);return {writes,calls};}catch(error){return {error,writes,calls};}
}
test('actual page loader verifies and installs every manifest asset',async()=>{
 const r=await attempt();assert.equal(r.error,undefined);assert.equal(r.writes.length,21);assert.equal(r.calls.length,1);
});
for(const [name,change] of [
 ['altered source',(m,s)=>{s.files[m.files[0]]+='\n# tampered';}],
 ['missing source',(m,s)=>{delete s.files[m.files[0]];}],
 ['extra source',(m,s)=>{s.files['src/clinloop_engine/api.py']='private';}],
 ['unsafe path',(m,s)=>{m.files[0]='../escape.py';}],
 ['redirected bundle',(m,s)=>{m.source_bundle='https://foreign.invalid/source';}]
])test(name+' fails before Python starts',async()=>{
 const r=await attempt(change);assert(r.error);assert.equal(r.calls.length,0);assert.equal(r.writes.length,0);
});
test('failed HTTP response fails before Python starts',async()=>{
 const r=await attempt(()=>{},404);assert(r.error);assert.equal(r.calls.length,0);
});
