'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {start}=require('../js/display-start.js');
function environment({isolated=false,theme=null,language=null,deviceDark=false,deviceLanguage='en',page='worklist',blocked=false,search=''}={}){
 const attrs={'data-workspace':page,'data-language-options':page==='deployment'?'en':'en ko',...(isolated?{'data-isolated-session':'true'}:{})},reads=[];
 const html={lang:'en',getAttribute:key=>attrs[key]||null,setAttribute:(key,value)=>{attrs[key]=value;}};
 const win={matchMedia:()=>({matches:deviceDark}),navigator:{language:deviceLanguage},URLSearchParams,location:{search}};
 Object.defineProperty(win,'localStorage',{get(){if(isolated)throw Error('Isolated page touched storage');if(blocked)throw Error('Blocked');return {getItem(key){reads.push(key);assert(['clinloop_theme','clinloop_lang'].includes(key));return key==='clinloop_theme'?theme:language;}};}});
 for(const key of ['fetch','sessionStorage'])Object.defineProperty(win,key,{get(){throw Error('Display setup accessed '+key);}});
 return {doc:{documentElement:html},win,attrs,reads,html};
}
test('saved display preferences are applied before body, form or model elements exist',()=>{
 const e=environment({theme:'dark',language:'ko'});start(e.doc,e.win);
 assert.equal(e.attrs['data-theme'],'dark');assert.equal(e.html.lang,'ko');assert.deepEqual(e.reads,['clinloop_theme','clinloop_lang']);
});
test('isolated workspaces use device appearance without touching storage, requests or credentials',()=>{
 const e=environment({isolated:true,deviceDark:true,search:'?theme=light'});start(e.doc,e.win);assert.equal(e.attrs['data-theme'],'dark');assert.deepEqual(e.reads,[]);
});
test('blocked preference storage leaves device appearance usable',()=>{
 const e=environment({blocked:true,deviceDark:true});start(e.doc,e.win);assert.equal(e.attrs['data-theme'],'dark');
});
test('only supported languages and validated cockpit display URL options are applied',()=>{
 const e=environment({page:'index',theme:'dark',language:'ko',search:'?theme=light&lang=en'});start(e.doc,e.win);assert.equal(e.attrs['data-theme'],'light');assert.equal(e.html.lang,'en');
 const english=environment({page:'deployment',language:'ko'});start(english.doc,english.win);assert.equal(english.html.lang,'en');assert.deepEqual(english.reads,['clinloop_theme']);
 const device=environment({deviceLanguage:'ko-KR'});start(device.doc,device.win);assert.equal(device.html.lang,'ko');
});
async function update(version,{reject=false}={}){
 const boxes=[],events={},reloads=[];
 function element(tag){return {tag,children:[],textContent:'',attrs:{},events:{},append(...items){this.children.push(...items);},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.events[k]=v;},remove(){this.removed=true;}};}
 const document={readyState:'complete',documentElement:{lang:'en'},getElementById:id=>{assert.equal(id,'clinloop-update-notice');return boxes[0]||null;},createElement:element,body:{append:box=>boxes.push(box)},addEventListener:(name,callback)=>{events[name]=callback;}};
 const request=async()=>{if(reject)throw Error('offline');return {ok:true,json:async()=>({version})};};
 const context={window:{fetch:request},fetch:request,document,location:{protocol:'https:',reload:()=>reloads.push(true)},Date};
 for(const key of ['localStorage','sessionStorage'])Object.defineProperty(context.window,key,{get(){throw Error('Update check accessed '+key);}});
 const source=fs.readFileSync('js/appnav.js','utf8');vm.runInNewContext(source.slice(source.indexOf('  // Check for updates'),source.indexOf('  var PAGES = [')),context);await new Promise(resolve=>setImmediate(resolve));
 return {boxes,reloads};
}
test('a newer version never reloads until the user explicitly chooses Refresh',async()=>{
 const e=await update('2099-01-01.release');assert.equal(e.reloads.length,0);assert.equal(e.boxes.length,1);assert.match(e.boxes[0].children[0].textContent,/Save your work/);
 e.boxes[0].children[2].events.click();assert.equal(e.boxes[0].removed,true);assert.equal(e.reloads.length,0);
 e.boxes[0].children[1].events.click();assert.equal(e.reloads.length,1);
});
test('current releases, invalid version metadata and offline checks never interrupt the page',async()=>{
 const source=fs.readFileSync('js/appnav.js','utf8');const current=/APP_VERSION = '([^']+)'/.exec(source)[1];
 for(const version of [current,'<script>untrusted</script>']){const e=await update(version);assert.equal(e.boxes.length,0);assert.equal(e.reloads.length,0);}
 const offline=await update('2099-01-01.release',{reject:true});assert.equal(offline.boxes.length,0);assert.equal(offline.reloads.length,0);
});

async function readerStartup({failure=false,empty=false}={}){
 const html=fs.readFileSync('reports.html','utf8');
 const source=html.slice(html.lastIndexOf('(async () => {'),html.indexOf('</script>',html.lastIndexOf('(async () => {')));
 const nodes=Object.fromEntries(['list','note','clinloop-workspace','report-load-status'].map(id=>[id,{textContent:'',hidden:false,replaceChildren(){},append(){},setAttribute(k,v){this[k]=v;}}]));
 let release;const reading=new Promise(resolve=>{release=resolve;});const removed=[];
 const context={connectLiveModel:async()=>{},getReport:async()=>{if(failure)throw Error('offline');return {ok:true,json:async()=>({note:'Synthetic catalogue',cases:empty?[]:[{id:'synthetic',title:'Example',language:'en',teaches:'Example'}]})};},$:id=>nodes[id],el:()=>({dataset:{},append(){},addEventListener(){}}),openCase:()=>reading,document:{body:{classList:{remove:name=>removed.push(name)}}}};
 const done=vm.runInNewContext(source,context);await new Promise(resolve=>setImmediate(resolve));
 return {done,release,removed,nodes};
}
test('report startup remains busy until the first saved case completes',async()=>{
 const e=await readerStartup();assert.deepEqual(e.removed,[]);assert.equal(e.nodes['report-load-status'].hidden,false);
 e.release();await e.done;assert.deepEqual(e.removed,['report-loading']);assert.equal(e.nodes['clinloop-workspace']['aria-busy'],'false');assert.equal(e.nodes['report-load-status'].hidden,true);
});
test('report startup reveals recoverable errors and empty catalogues instead of remaining hidden',async()=>{
 for(const options of [{failure:true},{empty:true}]){const e=await readerStartup(options);await e.done;assert.deepEqual(e.removed,['report-loading']);assert.equal(e.nodes['report-load-status'].hidden,true);if(options.failure)assert.match(e.nodes.list.textContent,/unavailable/);}
});
