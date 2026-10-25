'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('js/appearance-controls.js','utf8');
function environment(isolated) {
  const attrs={},writes=[],buttons=[];
  const root={lang:'en',getAttribute:k=>attrs[k]||null,setAttribute:(k,v)=>{attrs[k]=v;}};
  const body={getAttribute:()=>isolated?'true':null};
  const doc={readyState:'complete',documentElement:root,body,getElementById:()=>null,createElement:tag=>{const el={tag,attrs:{},children:[],events:{},setAttribute(k,v){this.attrs[k]=v;},append(x){this.children.push(x);},addEventListener(k,v){this.events[k]=v;}};if(tag==='button')buttons.push(el);return el;},querySelector:s=>s==='.workspace-header'?{insertBefore(){},querySelector:()=>null}:null};
  const context={document:doc,window:{matchMedia:()=>({matches:false})}};
  if(isolated) for(const key of ['localStorage','sessionStorage','fetch'])Object.defineProperty(context.window,key,{get(){throw Error('Isolated appearance accessed '+key);}});
  else context.window.localStorage={setItem:(k,v)=>writes.push([k,v])};
  vm.runInNewContext(source,context);return {attrs,writes,buttons,root};
}
test('isolated appearance changes stay in memory without requests or browser storage',()=>{
 const e=environment(true);assert.equal(e.buttons.length,2);
 e.buttons[1].events.click();assert.equal(e.attrs['data-theme'],'dark');assert.equal(e.buttons[1].attrs['aria-pressed'],'true');
 e.buttons[0].events.click();assert.equal(e.attrs['data-theme'],'light');assert.equal(e.buttons[0].attrs['aria-pressed'],'true');
});
test('clinical pages remember only a display preference and preserve translated button labels',()=>{
 const e=environment(false);e.root.lang='ko';e.buttons[1].events.click();assert.deepEqual(e.writes,[['clinloop_theme','dark']]);assert.equal(e.buttons[0].textContent,'라이트');assert.equal(e.buttons[1].textContent,'다크');
});
test('isolated navigation reveals the current page after rotation without moving keyboard focus or accessing session data',()=>{
 const events={},focus={id:'synthetic-focus'};let width=1200;
 const active={getBoundingClientRect:()=>({left:900-nav.scrollLeft,right:1010-nav.scrollLeft})};
 const nav={scrollLeft:0,scrollWidth:1200,get clientWidth(){return width;},
   getBoundingClientRect:()=>({left:0,right:width}),querySelector:()=>active,
   addEventListener:(name,callback)=>{events['nav:'+name]=callback;}};
 const document={activeElement:focus,querySelector:()=>nav};
 const context={location:{hostname:'127.0.0.1',protocol:'http:',pathname:'/review'},document,
   window:{addEventListener:(name,callback)=>{events[name]=callback;},
     ResizeObserver:class {constructor(callback){events.elementResize=callback;}observe(element){assert.equal(element,nav);}}}};
 for(const key of ['fetch','localStorage','sessionStorage'])Object.defineProperty(context.window,key,{get(){throw Error('Navigation accessed '+key);}});
 vm.runInNewContext(fs.readFileSync('js/workspace-navigation.js','utf8'),context);
 assert.equal(nav.scrollLeft,0);width=300;events.elementResize();
 assert(active.getBoundingClientRect().right<=width);assert.equal(document.activeElement,focus);
 nav.scrollLeft=1000;events.resize();assert(active.getBoundingClientRect().left>=0);
 const previous=nav.scrollLeft;events.resize();assert.equal(nav.scrollLeft,previous);
});
test('cockpit theme and sound labels follow the selected language and actual sound state',()=>{
 const nodes=Object.fromEntries(['theme-opt-light','theme-opt-dark','sound-toggle'].map(id=>[id,{attrs:{},setAttribute(k,v){this.attrs[k]=v;}}]));
 const context={window:{},location:{hostname:'clinloopai.app',protocol:'https:'},document:{addEventListener(){},getElementById:id=>nodes[id]||null}};
 vm.runInNewContext(fs.readFileSync('js/app.js','utf8')+'\nthis.update = ClinLoopApp.prototype.updateDisplayLabels;',context);
 for(const currentLang of ['en','ko','en'])for(const soundEnabled of [false,true]){
  context.update.call({currentLang,soundEnabled});
  assert.equal(nodes['theme-opt-light'].textContent,currentLang==='ko'?'라이트':'Light');
  assert.equal(nodes['theme-opt-dark'].textContent,currentLang==='ko'?'다크':'Dark');
  assert.equal(nodes['sound-toggle'].textContent,currentLang==='ko'?(soundEnabled?'소리: 켜짐':'소리: 꺼짐'):(soundEnabled?'Sound: on':'Sound: off'));
  assert.equal(nodes['sound-toggle'].attrs['aria-pressed'],String(soundEnabled));
 }
});
test('cockpit examples remain hidden until initialization completes and failures keep a clear message',async()=>{
 const app=fs.readFileSync('js/app.js','utf8');const boot=app.slice(app.lastIndexOf("document.addEventListener('DOMContentLoaded'"));
 for(const lang of ['en','ko']) for(const failed of [false,true]){
  let callback,ready=false;const status={hidden:false,textContent:'',setAttribute(k,v){this[k]=v;}};const document={documentElement:{lang},addEventListener:(_e,fn)=>{callback=fn;},body:{classList:{remove:name=>{assert.equal(name,'cockpit-loading');ready=true;}}},getElementById:()=>status};
  vm.runInNewContext(boot,{document,window:{},ClinLoopApp:class{async init(){if(failed)throw Error('synthetic-only');}}});await callback();
  assert.equal(ready,!failed);assert.equal(status.hidden,!failed);if(failed){assert.match(status.textContent,lang==='en'?/Refresh/:/새로고침/);assert.equal(/[가-힣]/.test(status.textContent),lang==='ko');assert.equal(status['data-demo-copy'],'loadFailed');}
 }
 const html=fs.readFileSync('index.html','utf8');assert.equal((html.match(/<nav class="app-nav"/g)||[]).length,1);assert(!html.includes('floating-theme-switch-dock'));
});
