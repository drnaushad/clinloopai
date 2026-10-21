'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');
const {Sandbox, issuer, endpoints, redirectFor, launcherFor, challenge, consume, reportsFrom, KEY, TTL, SCOPE} = require('../js/smart-sandbox.js');
const ISS = 'https://launch.smarthealthit.org/v/r4/fhir';
const BASE = 'https://clinloopai.app/smart/';
const META = {authorization_endpoint: ISS.replace('/fhir', '/auth/authorize'),
  token_endpoint: ISS.replace('/fhir', '/auth/token'), code_challenge_methods_supported: ['S256']};
const PATIENT = {resourceType: 'Patient', id: 'synthetic-1'};
const BUNDLE = {resourceType: 'Bundle', type: 'searchset', total: 1,
  entry: [{resource: {resourceType: 'DiagnosticReport', subject: {reference: 'Patient/synthetic-1'},
    status: 'final', conclusion: 'Synthetic conclusion. Clinical review required.'}}]};
const TOKEN = {access_token: 'synthetic-token', token_type: 'Bearer', patient: PATIENT.id, expires_in: 300, scope: SCOPE};
const json = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
function storage() {
  const m = new Map(); return {getItem: k => m.get(k) || null, setItem: (k,v) => m.set(k,v), removeItem: k => m.delete(k), m};
}
function setup(overrides = {}) {
  const calls = [], store = storage(); let now = 1000;
  const fetcher = async (url, options) => {
    calls.push({url, options: {...options, headers: {...options.headers}}});
    if (overrides[url]) return overrides[url](url, options);
    return json(url.endsWith('smart-configuration') ? META : url.endsWith('/token') ? TOKEN :
      url.includes('/Patient/') ? PATIENT : BUNDLE);
  };
  const client = new Sandbox({fetcher, storage: store, crypto: webcrypto, now: () => now});
  return {client, calls, store, advance: t => now += t};
}
async function begin(s) {
  const auth = new URL(await s.client.authorize(BASE + 'launch.html?' + new URLSearchParams({iss: ISS, launch: 'synthetic-context'}), true));
  return BASE + 'callback.html?' + new URLSearchParams({state: auth.searchParams.get('state'), code: 'synthetic-code'});
}
test('only canonical SMART sandbox R4 issuers are permitted', () => {
  assert.equal(issuer(ISS), ISS);
  assert.equal(issuer(ISS.replace('/fhir','/sim/WzAsIiJd/fhir')), ISS.replace('/fhir','/sim/WzAsIiJd/fhir'));
  for (const bad of [ISS+'/', ISS+'?x=1', ISS+'#x', ISS.replace('https:', 'http:'),
    ISS.replace('launch.smarthealthit.org', 'launch.smarthealthit.org.evil.test'),
    ISS.replace('https://', 'https://user:pass@'), ISS.replace('/r4/', '/r3/'),
    'https://launch.smarthealthit.org/v/r4/x/../fhir', ISS.replace('/fhir', '/sim/%2e%2e/fhir')]) assert.throws(() => issuer(bad));
});
test('discovery cannot redirect codes or tokens to a foreign endpoint or omit PKCE', () => {
  assert.equal(endpoints(ISS, META).token, META.token_endpoint);
  for (const change of [{token_endpoint: 'https://evil.test/token'}, {authorization_endpoint: META.authorization_endpoint+'?next=x'},
    {token_endpoint: META.token_endpoint+'/'}, {code_challenge_methods_supported: ['plain']}])
    assert.throws(() => endpoints(ISS, {...META, ...change}));
});
test('redirect URLs are fixed paths on production or loopback preview only', () => {
  assert.equal(redirectFor(BASE+'launch.html?iss=x'), BASE+'callback.html');
  assert.equal(redirectFor('http://127.0.0.1:18126/smart/launch.html'), 'http://127.0.0.1:18126/smart/callback.html');
  for (const bad of ['https://evil.test/smart/launch.html', 'http://clinloopai.app/smart/launch.html',
    BASE+'other.html', 'https://user@clinloopai.app/smart/launch.html', 'http://localhost.evil.test/smart/launch.html'])
    assert.throws(() => redirectFor(bad));
});
test('PKCE S256 matches the RFC 7636 test vector', async () => {
  assert.equal(await challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk', webcrypto),
    'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
});
test('the generated launcher requires exact client, scopes, redirect and PKCE', () => {
  const u = new URL(launcherFor(BASE+'launch.html'));
  const options = JSON.parse(Buffer.from(u.searchParams.get('launch'), 'base64url').toString());
  assert.equal(u.searchParams.get('validation'), '1');
  assert.equal(u.searchParams.get('launch_url'), BASE+'launch.html');
  assert.equal(options[7], SCOPE); assert.equal(options[8], BASE+'callback.html');
  assert.equal(options[9], 'clinloop-smart-sandbox-ui'); assert.equal(options[15], 2);
});
test('confirmation and valid launch context are required before any network call', async () => {
  const s = setup();
  await assert.rejects(s.client.authorize(BASE+'launch.html', false));
  await assert.rejects(s.client.authorize(BASE+'launch.html?iss='+ISS, true));
  await assert.rejects(s.client.authorize(BASE+'launch.html?iss='+ISS+'&iss='+ISS+'&launch=x', true));
  assert.equal(s.calls.length, 0);
});
test('authorization uses random state, PKCE and minimal patient read scopes without secrets', async () => {
  const s = setup(); const callback = await begin(s); const h = JSON.parse(s.store.getItem(KEY));
  assert.equal(h.state.length, 43); assert.equal(h.verifier.length, 43);
  assert(callback.includes('state=')); assert.equal(s.calls.length, 1);
  assert(!s.store.getItem(KEY).includes('access_token'));
  const s2 = setup(); await begin(s2);
  assert.notEqual(h.state, JSON.parse(s2.store.getItem(KEY)).state);
});
test('successful round trip verifies context and never stores tokens or records', async () => {
  const s = setup(); const callback = await begin(s);
  const result = await s.client.complete(callback);
  assert.deepEqual(result, {reports: [{status: 'final', conclusion: BUNDLE.entry[0].resource.conclusion}], partial: false});
  assert.equal(s.store.m.size, 0);
  assert.equal(s.calls.length, 4);
  assert.equal(s.calls[3].url, ISS+'/DiagnosticReport?patient=synthetic-1&_count=20');
  for (const {url, options} of s.calls) {
    assert.equal(new URL(url).origin, 'https://launch.smarthealthit.org');
    assert.equal(options.credentials, 'omit'); assert.equal(options.redirect, 'error');
    assert.equal(options.cache, 'no-store'); assert.equal(options.referrerPolicy, 'no-referrer');
  }
  assert(s.calls[1].options.body.includes('code_verifier='));
  assert(!s.calls[1].options.body.includes('client_secret'));
  await assert.rejects(s.client.complete(callback));
  assert.equal(s.calls.length, 4);
});
test('invalid, duplicate, expired, future and denied callbacks consume state without exchanging codes', async () => {
  for (const change of ['state', 'duplicate', 'expired', 'future', 'denied', 'code-duplicate', 'no-code']) {
    const s = setup(); const u = new URL(await begin(s));
    if (change === 'state') u.searchParams.set('state', 'x'.repeat(43));
    if (change === 'duplicate') u.searchParams.append('state', u.searchParams.get('state'));
    if (change === 'expired') s.advance(TTL+1);
    if (change === 'future') s.advance(-1);
    if (change === 'denied') u.searchParams.set('error', 'access_denied');
    if (change === 'code-duplicate') u.searchParams.append('code', 'other');
    if (change === 'no-code') u.searchParams.delete('code');
    await assert.rejects(s.client.complete(u.href));
    assert.equal(s.calls.length, 1); assert.equal(s.store.m.size, 0);
  }
});
test('handshake endpoint tampering cannot exfiltrate an authorization code', async () => {
  const s = setup(); const callback = await begin(s); const h = JSON.parse(s.store.getItem(KEY));
  s.store.setItem(KEY, JSON.stringify({...h, token: 'https://evil.test/token'}));
  await assert.rejects(s.client.complete(callback)); assert.equal(s.calls.length, 1);
});
test('unusable tokens, missing patient and insufficient scopes stop before FHIR reads', async () => {
  for (const change of [{patient: ''}, {patient: '../other'}, {token_type: 'Unknown'}, {access_token: 'bad\r\nheader'},
    {expires_in: 0}, {scope: 'launch patient/Patient.r'}, {access_token: ''}]) {
    const s = setup({[META.token_endpoint]: () => json({...TOKEN, ...change})});
    await assert.rejects(s.client.complete(await begin(s))); assert.equal(s.calls.length, 2);
  }
});
test('wrong Patient context is rejected before report search', async () => {
  const s = setup({[ISS+'/Patient/synthetic-1']: () => json({...PATIENT, id: 'other'})});
  await assert.rejects(s.client.complete(await begin(s))); assert.equal(s.calls.length, 3);
});
test('another patient, absolute foreign references and outcome entries fail closed', () => {
  for (const ref of ['Patient/other', 'https://evil.test/Patient/synthetic-1', undefined]) {
    const bundle = structuredClone(BUNDLE); bundle.entry[0].resource.subject.reference = ref;
    assert.throws(() => reportsFrom(bundle, PATIENT.id, ISS));
  }
  const bundle = structuredClone(BUNDLE); bundle.entry[0].search = {mode: 'outcome'};
  assert.throws(() => reportsFrom(bundle, PATIENT.id, ISS));
});
test('empty and partial searches remain explicit; pagination URLs are never followed', async () => {
  assert.deepEqual(reportsFrom({resourceType: 'Bundle', type: 'searchset'}, PATIENT.id, ISS), {reports: [], partial: false});
  const bundle = {...BUNDLE, total: 100, link: [{relation: 'next', url: 'https://evil.test/steal'}]};
  const s = setup({[ISS+'/DiagnosticReport?patient=synthetic-1&_count=20']: () => json(bundle)});
  assert.equal((await s.client.complete(await begin(s))).partial, true); assert.equal(s.calls.length, 4);
});
test('malformed, oversized, unauthorized and non-JSON responses do not become results', async () => {
  for (const response of [() => json({error: 'synthetic'}, 401), () => new Response('<html>bad</html>'),
    () => new Response('{', {headers: {'Content-Type': 'application/json'}}),
    () => new Response('x'.repeat(2*1024*1024+1), {headers: {'Content-Type': 'application/json'}})]) {
    const s = setup({[META.token_endpoint]: response});
    await assert.rejects(s.client.complete(await begin(s))); assert.equal(s.calls.length, 2);
  }
});
test('disconnect cancels an in-flight response and prevents stale records returning', async () => {
  let release;
  const pending = new Promise(resolve => {release = resolve;});
  const s = setup({[ISS+'/DiagnosticReport?patient=synthetic-1&_count=20']: () => pending});
  const task = s.client.complete(await begin(s));
  while (s.calls.length < 4) await new Promise(resolve => setImmediate(resolve));
  s.client.close(); release(json(BUNDLE));
  await assert.rejects(task); assert.equal(s.store.m.size, 0);
});
test('independent tabs cannot use each other’s handshake', async () => {
  const a = setup(), b = setup(); const callback = await begin(a); await begin(b);
  await assert.rejects(b.client.complete(callback)); assert.equal(b.calls.length, 1);
});
test('source XHTML and attachment URLs are not rendered or fetched', () => {
  const bundle = structuredClone(BUNDLE);
  bundle.entry[0].resource.text = {div: '<img src="https://evil.test/track">'};
  bundle.entry[0].resource.presentedForm = [{url: 'https://evil.test/attachment'}];
  const result = reportsFrom(bundle, PATIENT.id, ISS);
  assert(!JSON.stringify(result).includes('evil.test'));
});
function page(callback = false) {
  const elements = {}, events = {}, clientCalls = [];
  for (const id of ['status', 'reports', 'start', 'disconnect', 'synthetic'])
    elements[id] = {checked: true, children: [], addEventListener: (name, fn) => {events[id+':'+name] = fn;},
      replaceChildren() {this.children=[];}, appendChild(x) {this.children.push(x);}};
  if (callback) elements.start = null;
  const location = {pathname: '/smart/'+(callback?'callback':'launch')+'.html', href: BASE+(callback?'callback.html?code=secret&state=state':'launch.html?iss=x&launch=x'),
    replace: () => {events.pagehide();}};
  const context = {document: {getElementById: id=>elements[id], addEventListener() {},
    createElement: () => ({append() {}})}, location, history: {replaceState: (...args) => clientCalls.push(['scrub', ...args])},
    setTimeout: ()=>1, clearTimeout() {}, window: {addEventListener: (name, fn)=>{events[name]=fn;},
      ClinLoopSmartSandbox: {Sandbox: class {authorize = async()=> 'https://launch.smarthealthit.org/test';
        complete = async()=> ({reports:[],partial:false}); close = value=>clientCalls.push(['close',value]);}}}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../js/smart-sandbox-page.js'),'utf8'), context);
  return {elements, events, clientCalls};
}
test('leaving for OAuth preserves only the short-lived handshake; normal leave clears it', async () => {
  const p = page(); p.events['start:click'](); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(p.clientCalls, [['close', true]]);
  const q = page(); q.events.pagehide(); assert.deepEqual(q.clientCalls, [['close', undefined]]);
});
test('callback scrubs authorization query and disconnect clears displayed records', async () => {
  const p = page(true); await new Promise(resolve => setImmediate(resolve));
  assert.equal(p.clientCalls[0][0], 'scrub');
  assert.equal(p.clientCalls[0][3], '/smart/callback.html');
  assert.equal(p.elements.reports.children.length, 2);
  p.events['disconnect:click'](); assert.equal(p.elements.reports.children.length, 0);
});
test('restoring a page from browser cache clears the previous session', () => {
  const p = page(); p.events.pageshow({persisted:true});
  assert.deepEqual(p.clientCalls, [['close',undefined]]);
});
