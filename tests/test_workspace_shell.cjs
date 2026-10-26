'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {route,destination,catalog,mount}=require('../js/workspace-shell.js');

test('page navigation permits only known local destinations and leaves the current session alone',()=>{
  assert.equal(route('./'),'/');assert.equal(route('review.html'),'/review');
  for(const input of ['https://elsewhere.example/review','//elsewhere.example','javascript:alert(1)','../private','review?token=secret','/api/v1/patients',null]) {
    assert.equal(route(input),null);assert.equal(destination(input,'/review'),null);
  }
  assert.equal(destination('/review','/review.html'),null);
  assert.equal(destination('/private','/review'),'/private');
});

class Element {
  constructor(tag) {this.tagName=tag.toUpperCase();this.children=[];this.attrs={};this.events={};this.textContent='';this.className='';
    this.classList={add:name=>{this.className+=' '+name;},contains:name=>this.className.split(' ').includes(name)};}
  append(...nodes){for(const node of nodes){node.remove();node.parentElement=this;this.children.push(node);}}
  prepend(node){node.remove();node.parentElement=this;this.children.unshift(node);}
  remove(){if(this.parentElement){const list=this.parentElement.children;list.splice(list.indexOf(this),1);this.parentElement=null;}}
  setAttribute(k,v){this.attrs[k]=v;} getAttribute(k){return Object.hasOwn(this.attrs,k)?this.attrs[k]:null;}
  removeAttribute(k){delete this.attrs[k];}
  addEventListener(k,fn){this.events[k]=fn;}
  querySelector(selector){return this.children.find(e=>selector==='[data-shell-account]'&&e.getAttribute('data-shell-account')!==null)||null;}
  querySelectorAll(){return this.children.filter(e=>e.tagName==='A');}
  replaceChildren(...nodes){for(const child of [...this.children])child.remove();this.append(...nodes);}
}
function fixture(account) {
  const body=new Element('body'),oldHeader=new Element('header'),main=new Element('main'),nav=new Element('nav');
  const appearance=new Element('div'),language=account?new Element('button'):null,accountGroup=new Element('nav');
  const oldCallback=()=> 'original handler';appearance.events.click=oldCallback;
  if(account){accountGroup.append(appearance,language);oldHeader.append(accountGroup,nav);}else oldHeader.append(appearance,nav);
  body.append(oldHeader,main);main.id='workspace';
  for(const [href,text] of [['./','Cockpit'],['worklist','Worklist'],['review','Report review'],['private','Personal workspace'],['validation','Validation evidence']]) {
    const link=new Element('a');link.setAttribute('href',href);link.textContent=text;nav.append(link);
  }
  const focus={id:'synthetic-report-field'},observers=[],assigned=[],events={};
  const doc={body,documentElement:{lang:'en'},activeElement:focus,
    createElement:tag=>new Element(tag),getElementById:id=>{assert.equal(id,'btn-lang');return language;},
    querySelectorAll:()=>[],querySelector(selector){
      if(selector==='nav.app-nav, nav.workspace-nav')return nav;
      if(selector==='.clinloop-shell')return body.children.find(e=>e.className==='clinloop-shell')||null;
      if(selector==='.workspace-header')return oldHeader;
      if(selector==='.appearance-controls')return appearance;
      if(selector==='.wrap, main'||selector==='.cockpit-workspace, .wrap, main')return main;
      if(selector==='.skip-link')return {id:'existing-skip'};
      return null;
    }};
  const win={location:{pathname:'/review',assign:path=>assigned.push(path)},
    addEventListener:(name,callback)=>{events[name]=callback;},
    MutationObserver:class{constructor(callback){observers.push(callback);}observe(){}}};
  for(const key of ['fetch','localStorage','sessionStorage'])Object.defineProperty(win,key,{get(){throw Error('Shell accessed '+key);}});
  return {doc,win,body,main,nav,appearance,accountGroup,oldCallback,focus,observers,assigned,events};
}
test('the catalogue keeps source labels, drops foreign links and groups clinical/research/setup pages',()=>{
  const make=(href,text)=>({getAttribute:()=>href,textContent:text});
  const items=catalog([make('worklist','Worklist'),make('review','보고서 검토'),make('review','duplicate'),make('validation','Validation evidence'),make('https://elsewhere.example','ignore')]);
  assert.deepEqual(items,[{path:'/worklist',label:'Worklist',group:0},{path:'/review',label:'보고서 검토',group:1},{path:'/validation',label:'Validation evidence',group:2}]);
});
test('page menus keep the same route order even if their source links arrive in a different order',()=>{
  const make=(href,text)=>({getAttribute:()=>href,textContent:text});
  const items=catalog([make('deployment','International setup'),make('review','보고서 검토'),make('./','Cockpit'),make('worklist','Worklist')]);
  assert.deepEqual(items.map(x=>x.path),['/','/worklist','/review','/deployment']);
  assert.equal(items.find(x=>x.path==='/review').label,'보고서 검토');
});
for(const account of [false,true])test((account?'clinical':'isolated')+' menu follows Back/Forward restoration without reading or changing the session',()=>{
  const f=fixture(account);mount(f.doc,f.win);
  const shell=f.body.children.find(e=>e.className==='clinloop-shell'),picker=shell.children.at(-1).children[1];
  const active=()=>f.nav.children.filter(x=>x.getAttribute('aria-current')==='page').map(x=>x.getAttribute('href'));
  assert.deepEqual(active(),['review']);
  picker.value='/private';f.events.pageshow({persisted:true});
  assert.equal(picker.value,'/review');assert.deepEqual(active(),['review']);
  f.win.location.pathname='/private';f.events.popstate();
  assert.equal(picker.value,'/private');assert.deepEqual(active(),['private']);
  f.win.location.pathname='/review.html';f.events.pageshow({persisted:false});
  assert.equal(picker.value,'/review');assert.deepEqual(active(),['review']);
  f.doc.documentElement.lang='ko';f.events.pageshow({persisted:true});
  assert.equal(f.nav.getAttribute('aria-label'),'ClinLoop 화면');
  assert.equal(f.doc.activeElement,f.focus);assert.deepEqual(f.assigned,[]);
  picker.value='https://elsewhere.example';picker.events.change();
  assert.equal(picker.value,'/review');assert.deepEqual(f.assigned,[]);
});
for(const account of [false,true])test((account?'clinical':'isolated')+' shell preserves controls, handlers, keyboard focus and current-page selection without session access',()=>{
  const f=fixture(account);mount(f.doc,f.win);
  const shell=f.body.children.find(e=>e.className==='clinloop-shell');assert(shell);
  assert.equal(f.nav.parentElement,shell);assert.equal(f.doc.activeElement,f.focus);
  assert.equal(f.appearance.events.click,f.oldCallback);assert.equal(f.appearance.events.click(),'original handler');
  assert(f.appearance.parentElement!==null);assert.equal(f.main.parentElement,f.body);
  if(account)assert.equal(f.appearance.parentElement,f.accountGroup);
  const mobile=shell.children.at(-1),label=mobile.children[0],picker=mobile.children[1];
  assert.equal(label.textContent,'Go to page');assert.equal(picker.value,'/review');
  picker.events.change();assert.deepEqual(f.assigned,[]);
  picker.value='/private';picker.events.change();assert.deepEqual(f.assigned,['/private']);
  f.doc.documentElement.lang='ko';f.observers.at(-1)();assert.equal(label.textContent,'화면 이동');assert.equal(picker.value,'/review');
  mount(f.doc,f.win);assert.equal(f.body.children.filter(e=>e.className==='clinloop-shell').length,1);
});
