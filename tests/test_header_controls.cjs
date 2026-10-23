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
test('cockpit examples remain hidden until initialization completes and failures keep a clear message',async()=>{
 const app=fs.readFileSync('js/app.js','utf8');const boot=app.slice(app.lastIndexOf("document.addEventListener('DOMContentLoaded'"));
 for(const failed of [false,true]){
  let callback,ready=false;const status={hidden:false,textContent:''};const document={addEventListener:(_e,fn)=>{callback=fn;},body:{classList:{remove:name=>{assert.equal(name,'cockpit-loading');ready=true;}}},getElementById:()=>status};
  vm.runInNewContext(boot,{document,window:{},ClinLoopApp:class{async init(){if(failed)throw Error('synthetic-only');}}});await callback();
  assert.equal(ready,!failed);assert.equal(status.hidden,!failed);if(failed)assert.match(status.textContent,/Refresh/);
 }
 const html=fs.readFileSync('index.html','utf8');assert.equal((html.match(/<nav class="app-nav"/g)||[]).length,1);assert(!html.includes('floating-theme-switch-dock'));
});
