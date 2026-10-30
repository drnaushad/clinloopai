
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function worker(fetcher) {
 const events={},calls=[];
 vm.runInNewContext(fs.readFileSync('sw.js','utf8'), {
  self:{addEventListener:(name,handler)=>events[name]=handler,
   skipWaiting:()=>Promise.resolve(),clients:{claim:()=>Promise.resolve()}},fetch:fetcher,
  caches:new Proxy({},{get(){throw Error('Cache storage accessed');}})
 });
 return events;
}
test('service worker forwards the exact request and never stores responses', async()=>{
 const request={url:'https://synthetic.example/api/v1/patient'},response={status:200};
 const events=worker(async value=>{assert.equal(value,request);return response;});
 let pending;events.activate({waitUntil:value=>pending=value});await pending;
 events.fetch({request,respondWith:value=>pending=value});assert.equal(await pending,response);
});
test('offline requests fail without replaying cached clinical content',async()=>{
 const events=worker(async()=>{throw Error('offline');});let pending;
 events.fetch({request:{},respondWith:value=>pending=value});await assert.rejects(pending,/offline/);
});
