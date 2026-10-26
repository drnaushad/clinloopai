'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require.resolve('../reports.html'),'utf8');
function harness(){
 const nodes={},buttons=['A','B'].map(id=>({dataset:{id},setAttribute(k,v){this[k]=v;}})),pending={};
 const context={document:{querySelectorAll:()=>buttons},$:id=>nodes[id]||(nodes[id]={textContent:'',replaceChildren(){},append(){}}),getReport:p=>new Promise((resolve,reject)=>pending[p.split('/').pop()]={resolve,reject}),el:()=>({append(){}}),showReport(){},showModel(){},liveBackend:'https://synthetic.invalid'};
 vm.createContext(context);vm.runInContext('let current=null,caseEpoch=0,liveBusy=false;'+html.slice(html.indexOf('async function openCase(id)'),html.indexOf('$("live").addEventListener')),context);
 const reply=id=>({ok:true,json:async()=>({id,title:'Synthetic '+id,text:id,rules:[],model_reading:{items:[]},model:{}})});
 return {context,nodes,buttons,pending,reply};
}
test('late old report cannot replace the newly selected report',async()=>{
 const h=harness(),a=h.context.openCase('A'),b=h.context.openCase('B');
 h.pending.B.resolve(h.reply('B'));await b;h.pending.A.resolve(h.reply('A'));await a;
 assert.equal(h.nodes.title.textContent,'Synthetic B');assert.equal(h.buttons.find(b=>b['aria-current']).dataset.id,'B');
});
test('late JSON decode cannot replace a newer case',async()=>{
 const h=harness();let decode;const a=h.context.openCase('A');h.pending.A.resolve({ok:true,json:()=>new Promise(r=>decode=r)});await new Promise(setImmediate);
 const b=h.context.openCase('B');h.pending.B.resolve(h.reply('B'));await b;decode(await h.reply('A').json());await a;assert.equal(h.nodes.title.textContent,'Synthetic B');
});
test('failed old request does not overwrite a newer successful case',async()=>{
 const h=harness(),a=h.context.openCase('A'),b=h.context.openCase('B');h.pending.B.resolve(h.reply('B'));await b;h.pending.A.reject(new Error('synthetic error'));await a;assert.equal(h.nodes.title.textContent,'Synthetic B');
});
test('current failed request clears stale state and hides live action',async()=>{
 const h=harness(),a=h.context.openCase('A');h.pending.A.reject(new Error('synthetic error'));await a;assert.match(h.nodes.title.textContent,/unavailable/);assert.equal(h.nodes.live.hidden,true);
});
test('unavailable model reading clears previous provenance',()=>{
 const nodes={modelmeta:{textContent:'OLD PROVENANCE'},model:{replaceChildren(){},append(){}},modelheading:{}};
 const c={$:id=>nodes[id],el:()=>({})};vm.createContext(c);vm.runInContext(html.slice(html.indexOf('function showModel('),html.indexOf('async function openCase(')),c);
 c.showModel({available:false,reason:'Unavailable'},{name:'synthetic'});assert.equal(nodes.modelmeta.textContent,'');
});
test('optional model discovery is bounded and does not gate catalogue loading',async()=>{
 const source=html.slice(html.indexOf('async function connectLiveModel()'),html.indexOf('function showReport('));
 const requests=[];const nodes={modelchoice:{options:[],replaceChildren(){},append(x){this.options.push(x);}},live:{}};
 const c={URL,AbortSignal,current:{id:'A'},liveBusy:false,$:id=>nodes[id],el:()=>({}),fetch:async(url,opts)=>{requests.push({url,opts});return {ok:true,json:async()=>url==='public-models.json'?{enabled:true,base_url:'https://synthetic.invalid'}:url.endsWith('/models')?{models:[{name:'synthetic',role:'test',installed:true}]}:{}};}};
 vm.createContext(c);vm.runInContext('let liveBackend=null;'+source,c);await c.connectLiveModel();
 assert.equal(requests.length,3);assert(requests.every(r=>r.opts.signal instanceof AbortSignal));assert.equal(nodes.live.hidden,false);
 // Execute the actual initialization with a never-resolving optional connection.
 let catalogueRequested=false;
 const init=html.slice(html.indexOf('(async () => {'),html.indexOf('</script>', html.indexOf('(async () => {')));
 const boot={connectLiveModel:()=>new Promise(()=>{}),getReport:async()=>{catalogueRequested=true;return {ok:true,json:async()=>({note:'Synthetic',cases:[]})};},$:()=>({replaceChildren(){},append(){},setAttribute(){}}),document:{body:{classList:{remove(){}}}}};
 vm.createContext(boot);await vm.runInContext(init,boot);assert(catalogueRequested);
});
test('static snapshot disables unsupported input forms without changing hospital mode',()=>{
 const source=fs.readFileSync(require.resolve('../js/demo.js'),'utf8');
 const fn=source.slice(source.indexOf('function explainSnapshot()'),source.indexOf("    if (document.readyState === 'loading')"));
 const inputs=[{disabled:false},{disabled:false}];let notice='',selector='';const form={before(){},querySelectorAll:()=>inputs,addEventListener(){}};
 const c={document:{querySelector:()=>null,createElement:()=>({style:{},setAttribute(){},append(){}}),body:{prepend:n=>notice=n.textContent},querySelectorAll:s=>{selector=s;return [form];}}};vm.createContext(c);vm.runInContext(fn,c);c.explainSnapshot();
 assert.match(notice,/Synthetic snapshot/);assert(inputs.every(x=>x.disabled));assert(selector.includes('#note-form')&&selector.includes('#file-form'));
});
