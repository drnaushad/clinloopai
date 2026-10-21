'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {Workspace, localAddress} = require('../js/private-workspace.js');
const MODEL = 'synthetic-test:1b';
const tags = {models: [{name: MODEL}]};
const info = {details: {family: 'test'}, model_info: {'general.architecture': 'test'}, capabilities: ['completion']};
const reply = {model: MODEL, done: true, done_reason: 'stop', response: 'Synthetic answer.'};
const ok = value => ({status: 200, json: async () => value});
function setup(overrides = {}) {
  const calls = [], events = [];
  const workspace = new Workspace(async (url, options) => {
    calls.push({url, options});
    const path = new URL(url).pathname;
    if (overrides[path]) return overrides[path](url, options);
    return ok(path === '/api/tags' ? tags : path === '/api/show' ? info : reply);
  }, event => events.push(event));
  return {workspace, calls, events};
}

test('only literal loopback destinations without credentials, queries or paths', () => {
  assert.equal(localAddress('http://127.0.0.1:11435'), 'http://127.0.0.1:11435');
  assert.equal(localAddress('http://localhost:11434/'), 'http://localhost:11434');
  for (const value of ['https://api.example.test', 'http://192.168.1.2:11434', 'http://localhost.evil.test',
    'http://user:secret@localhost:11434', 'http://localhost/api', 'http://localhost/?token=x',
    'http://localhost/#secret', 'file:///etc/passwd', 'http://0.0.0.0:11434']) {
    assert.throws(() => localAddress(value));
  }
});

test('local-only attestation and address checks occur before model calls', async () => {
  const {workspace, calls} = setup();
  await assert.rejects(workspace.connect('http://localhost:11434', false));
  await assert.rejects(workspace.connect('https://shared.test', true));
  assert.equal(calls.length, 0);
  assert.equal(workspace.address, '');
});

test('cloud tags and remote aliases cannot be selected', async () => {
  const {workspace} = setup({'/api/tags': () => ok({models: [{name: MODEL}, {name: 'large:cloud'},
    {name: 'alias', remote_host: 'https://cloud.test'}, {name: 'alias2', details: {remote_model: 'x'}}]})});
  assert.deepEqual(await workspace.connect('http://localhost:11434', true), [MODEL]);
  await assert.rejects(workspace.run('alias', 'Synthetic text'));
});

test('a remote model revealed by inspection receives no user text', async () => {
  const {workspace, calls} = setup({'/api/show': () => ok({...info, remote_host: 'https://cloud.test'})});
  await workspace.connect('http://localhost:11434', true);
  await assert.rejects(workspace.run(MODEL, 'Synthetic private marker'));
  assert.equal(calls.length, 2);
  assert(!JSON.stringify(calls).includes('Synthetic private marker'));
});

test('nested remote metadata and malformed local metadata receive no user text', async () => {
  for (const details of [{...info, details: {remote_model: 'synthetic-remote'}},
    {...info, details: {remote_host: 'https://synthetic-cloud.test'}},
    {...info, details: []}, {...info, model_info: {}}, {...info, model_info: 'unknown'}]) {
    const {workspace, calls} = setup({'/api/show': () => ok(details)});
    await workspace.connect('http://localhost:11434', true);
    await assert.rejects(workspace.run(MODEL, 'Synthetic private marker'));
    assert.equal(calls.length, 2);
    assert(!JSON.stringify(calls).includes('Synthetic private marker'));
  }
});

test('requests omit credentials, reject redirects and have no public fallback', async () => {
  const {workspace, calls} = setup();
  await workspace.connect('http://127.0.0.1:11435', true);
  assert.equal(await workspace.run(MODEL, 'Synthetic first request'), reply.response);
  for (const call of calls) {
    assert.equal(new URL(call.url).origin, 'http://127.0.0.1:11435');
    assert.equal(call.options.credentials, 'omit');
    assert.equal(call.options.redirect, 'error');
    assert.equal(call.options.cache, 'no-store');
    assert.equal(call.options.referrerPolicy, 'no-referrer');
  }
  const body = JSON.parse(calls.at(-1).options.body);
  assert.equal(body.keep_alive, 0);
  assert.equal(body.options.num_ctx, 8192);
});

test('independent workspaces do not share model selection or conversation', async () => {
  const first = setup(), second = setup();
  await first.workspace.connect('http://localhost:11434', true);
  await second.workspace.connect('http://127.0.0.1:11435', true);
  await first.workspace.run(MODEL, 'Synthetic alpha');
  await second.workspace.run(MODEL, 'Synthetic beta');
  first.workspace.clear(true);
  assert(second.workspace.models.includes(MODEL));
  assert(!JSON.stringify(second.calls).includes('Synthetic alpha'));
  assert(!JSON.stringify(first.calls).includes('Synthetic beta'));
});

test('no history or prior context is sent with a later request', async () => {
  const {workspace, calls} = setup();
  await workspace.connect('http://localhost:11434', true);
  await workspace.run(MODEL, 'Synthetic earlier marker');
  workspace.clear(false);
  await workspace.run(MODEL, 'Synthetic next marker');
  const body = calls.at(-1).options.body;
  assert(!body.includes('earlier marker'));
  assert(!Object.hasOwn(JSON.parse(body), 'context'));
  assert(!Object.values(workspace).includes('Synthetic earlier marker'));
});

test('failed connection clears all model choices and emits only generic errors', async () => {
  const {workspace, calls} = setup({'/api/tags': () => {throw new Error('synthetic secret');}});
  await assert.rejects(workspace.connect('http://localhost:11434', true), error => !error.message.includes('synthetic secret'));
  assert.equal(workspace.address, '');
  assert.deepEqual(workspace.models, []);
  assert.equal(calls.length, 1);
});

test('oversize and empty text is rejected before any request including multi-byte input', async () => {
  const {workspace, calls} = setup();
  await workspace.connect('http://localhost:11434', true);
  for (const text of ['', ' ', 'x'.repeat(6001), '한'.repeat(2001)]) await assert.rejects(workspace.run(MODEL, text));
  assert.equal(calls.length, 1);
});

test('unfinished, truncated, mismatched and malformed responses never become answers', async () => {
  for (const response of [{...reply, done: false}, {...reply, done_reason: 'length'},
    {...reply, model: 'different'}, {...reply, response: ''}, {...reply, response: {}},
    {...reply, response: 'x'.repeat(30001)}]) {
    const {workspace, events} = setup({'/api/generate': () => ok(response)});
    await workspace.connect('http://localhost:11434', true);
    await assert.rejects(workspace.run(MODEL, 'Synthetic text'));
    assert(!events.some(event => event.type === 'answer'));
  }
});

test('clear aborts pending generation and suppresses a late answer', async () => {
  let resolve;
  const {workspace, calls, events} = setup({'/api/generate': () => new Promise(done => {resolve = done;})});
  await workspace.connect('http://localhost:11434', true);
  const pending = workspace.run(MODEL, 'Synthetic text');
  while (!resolve) await new Promise(done => setImmediate(done));
  workspace.clear(true);
  assert.equal(calls.at(-1).options.signal.aborted, true);
  resolve(ok(reply));
  await assert.rejects(pending, /Session cleared/);
  assert(!events.some(event => event.type === 'answer'));
  assert.equal(workspace.address, '');
});

test('reconnection during model inspection cannot send the old prompt to the new model server', async () => {
  let resolve;
  const {workspace, calls} = setup({'/api/show': () => new Promise(done => {resolve = done;})});
  await workspace.connect('http://localhost:11434', true);
  const pending = workspace.run(MODEL, 'Synthetic old-session marker');
  await workspace.connect('http://127.0.0.1:11435', true);
  resolve(ok(info));
  await assert.rejects(pending, /Session cleared/);
  assert(!calls.some(call => call.url.endsWith('/api/generate')));
});

function pageHarness() {
  const elements = new Map();
  for (const id of ['status', 'prompt', 'answer', 'model', 'local-only', 'endpoint', 'connect', 'disconnect',
    'run', 'sample', 'clear', 'connect-form']) {
    elements.set(id, {value: '', checked: false, disabled: false, textContent: '', listeners: {},
      addEventListener(event, listener) {this.listeners[event] = listener;},
      replaceChildren(...children) {this.children = children; this.value = children[0]?.value || '';}});
  }
  elements.get('endpoint').value = 'http://localhost:11434';
  const listeners = {}, intervals = [], calls = [];
  const window = {ClinLoopPrivate: {Workspace}, fetch: async (url, options) => {
    calls.push({url, options});
    return ok(url.endsWith('/api/tags') ? tags : url.endsWith('/api/show') ? info :
      {...reply, response: '<img src=https://evil.test> Synthetic model markup'});
  }, addEventListener(event, listener) {listeners[event] = listener;}};
  const document = {getElementById: id => elements.get(id), addEventListener() {}};
  const storage = new Proxy({}, {get() {throw new Error('Persistent storage accessed');}});
  const context = vm.createContext({window, document, Date, Option: function (text, value) {return {text, value};},
    setInterval: (fn, ms) => {intervals.push({fn, ms});}, localStorage: storage, sessionStorage: storage});
  vm.runInContext(fs.readFileSync('js/private-workspace-page.js', 'utf8'), context);
  return {elements, listeners, intervals, calls};
}

test('actual page clears prior form state, renders model markup as text and clears on leaving', async () => {
  const {elements, listeners, calls} = pageHarness();
  elements.get('local-only').checked = true;
  await elements.get('connect-form').listeners.submit({preventDefault() {}});
  assert.equal(elements.get('run').disabled, false);
  elements.get('prompt').value = 'Synthetic marker';
  await elements.get('run').listeners.click();
  assert.match(elements.get('answer').textContent, /^<img src=/);
  assert(!Object.hasOwn(elements.get('answer'), 'innerHTML'));
  listeners.pagehide();
  assert.equal(elements.get('prompt').value, '');
  assert.equal(elements.get('answer').textContent, 'No response yet.');
  assert.equal(elements.get('run').disabled, true);
  assert.equal(calls.length, 3);
});

test('actual page clears session after inactivity', async () => {
  const {elements, intervals} = pageHarness();
  elements.get('local-only').checked = true;
  await elements.get('connect-form').listeners.submit({preventDefault() {}});
  elements.get('prompt').value = 'Synthetic stale marker';
  const original = Date.now;
  try {Date.now = () => original() + 600001; intervals[0].fn();} finally {Date.now = original;}
  assert.equal(elements.get('prompt').value, '');
  assert.equal(elements.get('run').disabled, true);
});

test('page has no shared scripts, analytics, storage or public model connection policy', () => {
  const html = fs.readFileSync('private.html', 'utf8');
  const csp = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1];
  assert(csp.includes("connect-src http://127.0.0.1:* http://localhost:*;"));
  assert(!html.includes('appnav.js'));
  assert(!html.includes('demo.js'));
  assert(!html.includes('config.js'));
  assert(!html.includes('public-models.json'));
  assert(!/<script[^>]+src="https?:/.test(html));
});
