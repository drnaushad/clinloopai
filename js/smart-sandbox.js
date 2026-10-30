/* Synthetic SMART R4 sandbox only. No clinical inference or shared API calls. */
(function (root) {
  'use strict';
  const HOST = 'https://launch.smarthealthit.org';
  const CLIENT = 'clinloop-smart-sandbox-ui';
  const SCOPE = 'launch patient/Patient.r patient/DiagnosticReport.rs';
  const KEY = 'clinloop.smart.sandbox.handshake.v1';
  const TTL = 5 * 60 * 1000;
  const fail = () => { throw new Error('Sandbox connection could not be verified. Restart from the SMART launcher.'); };
  function issuer(value) {
    const u = new URL(value);
    if (u.origin !== HOST || u.username || u.password || u.search || u.hash ||
        !/^\/v\/r4(?:\/sim\/[A-Za-z0-9_-]{1,12000})?\/fhir$/.test(u.pathname) || value !== u.href) fail();
    return u.href;
  }
  function endpoints(iss, metadata) {
    issuer(iss);
    const auth = iss.replace(/\/fhir$/, '/auth/');
    if (!metadata || metadata.authorization_endpoint !== auth + 'authorize' ||
        metadata.token_endpoint !== auth + 'token' ||
        !Array.isArray(metadata.code_challenge_methods_supported) ||
        !metadata.code_challenge_methods_supported.includes('S256')) fail();
    return {authorize: auth + 'authorize', token: auth + 'token'};
  }
  function redirectFor(href) {
    const u = new URL(href);
    if (!(u.origin === 'https://clinloopai.app' ||
        (u.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(u.hostname))) ||
        !['/smart/launch.html', '/smart/callback.html'].includes(u.pathname) || u.username || u.password) fail();
    return u.origin + '/smart/callback.html';
  }
  function one(params, key, maximum = 16000) {
    const values = params.getAll(key);
    if (values.length !== 1 || !values[0] || values[0].length > maximum) fail();
    return values[0];
  }
  function random(crypto) {
    return encode(crypto.getRandomValues(new Uint8Array(32)));
  }
  function launcherFor(href) {
    const redirect = redirectFor(href);
    const options = [0, '', '', 'AUTO', 0, 0, 0, SCOPE, redirect, CLIENT, '', '', '', '', 0, 2, ''];
    const target = new URL('https://launch.smarthealthit.org/');
    target.search = new URLSearchParams({launch_url: new URL(href).origin + '/smart/launch.html',
      launch: encode(new TextEncoder().encode(JSON.stringify(options))), validation: '1', tab: '1'}).toString();
    return target.href;
  }
  function encode(bytes) {
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  async function challenge(verifier, crypto) {
    return encode(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  }
  function consume(storage, params, href, now) {
    const raw = storage.getItem(KEY);
    storage.removeItem(KEY); // Every callback is single use, including denial and invalid callbacks.
    const h = JSON.parse(raw || 'null');
    if (!h || !Number.isFinite(h.created) || now < h.created || now - h.created > TTL ||
        !/^[A-Za-z0-9_-]{43}$/.test(h.state) || !/^[A-Za-z0-9_-]{43}$/.test(h.verifier) ||
        one(params, 'state', 43) !== h.state || h.redirect !== redirectFor(href) ||
        h.token !== issuer(h.iss).replace(/\/fhir$/, '/auth/token')) fail();
    if (params.has('error')) fail();
    const code = one(params, 'code', 16000);
    if (/[\x00-\x20\x7f]/.test(code)) fail();
    return {...h, code};
  }
  function patientId(value) {
    if (typeof value !== 'string' || !/^[A-Za-z0-9.-]{1,64}$/.test(value)) fail();
    return value;
  }
  function reportsFrom(bundle, patient, iss) {
    patientId(patient); issuer(iss);
    if (!bundle || bundle.resourceType !== 'Bundle' || bundle.type !== 'searchset' ||
        (bundle.entry !== undefined && !Array.isArray(bundle.entry)) || (bundle.entry?.length || 0) > 20 ||
        (bundle.link !== undefined && (!Array.isArray(bundle.link) || bundle.link.some(link => !link || typeof link.relation !== 'string'))) ||
        (bundle.total !== undefined && (!Number.isSafeInteger(bundle.total) || bundle.total < (bundle.entry?.length || 0)))) fail();
    const reports = (bundle.entry || []).map(entry => {
      const r = entry.resource;
      if (entry.search?.mode === 'outcome' || !r || r.resourceType !== 'DiagnosticReport' ||
          !['Patient/' + patient, iss + '/Patient/' + patient].includes(r.subject?.reference)) fail();
      // Deliberately do not render FHIR XHTML or load attachments, images or linked records.
      // Never silently drop a report tail: it may contain an addendum or follow-up request.
      if ((r.status !== undefined && (typeof r.status !== 'string' || r.status.length > 80)) ||
          (r.conclusion !== undefined && (typeof r.conclusion !== 'string' || r.conclusion.length > 12000))) fail();
      return {status: r.status || 'Status unavailable',
        conclusion: r.conclusion || 'No plain-text conclusion supplied. Review the original report in the source system.'};
    });
    return {reports, partial: (bundle.link || []).some(link => link.relation === 'next') ||
      (Number.isFinite(bundle.total) && bundle.total > reports.length)};
  }
  class Sandbox {
    #fetch; #storage; #crypto; #now; #controller = new AbortController(); #closed = false;
    constructor({fetcher = root.fetch.bind(root), storage = root.sessionStorage,
      crypto = root.crypto, now = Date.now} = {}) {
      this.#fetch = fetcher; this.#storage = storage; this.#crypto = crypto; this.#now = now;
    }
    close(preserveHandshake = false) {
      this.#closed = true; this.#controller.abort();
      if (!preserveHandshake) this.#storage.removeItem(KEY);
    }
    async #json(url, options = {}) {
      if (this.#closed) fail();
      const controller = new AbortController();
      const abort = () => controller.abort();
      this.#controller.signal.addEventListener('abort', abort, {once: true});
      const timer = setTimeout(abort, 25000);
      try {
        const r = await this.#fetch(url, {...options, signal: controller.signal, credentials: 'omit',
          redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer'});
        if (!r.ok || !/^application\/(?:fhir\+)?json\b/i.test(r.headers.get('content-type') || '')) fail();
        let text = '';
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let size = 0;
        for (;;) {
          const {done, value} = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 2 * 1024 * 1024) { await reader.cancel(); fail(); }
          text += decoder.decode(value, {stream: true});
        }
        text += decoder.decode();
        if (this.#closed || controller.signal.aborted) fail();
        return JSON.parse(text);
      } finally {
        clearTimeout(timer); this.#controller.signal.removeEventListener('abort', abort);
      }
    }
    async authorize(href, syntheticConfirmed) {
      this.#storage.removeItem(KEY);
      if (syntheticConfirmed !== true) fail();
      const url = new URL(href), redirect = redirectFor(href);
      const iss = issuer(one(url.searchParams, 'iss'));
      const launch = one(url.searchParams, 'launch');
      const metadata = await this.#json(iss + '/.well-known/smart-configuration', {headers: {Accept: 'application/json'}});
      const ep = endpoints(iss, metadata);
      const verifier = random(this.#crypto), state = random(this.#crypto);
      const hash = await challenge(verifier, this.#crypto);
      if (this.#closed) fail();
      this.#storage.setItem(KEY, JSON.stringify({iss, token: ep.token, redirect, state, verifier, created: this.#now()}));
      const target = new URL(ep.authorize);
      target.search = new URLSearchParams({response_type: 'code', client_id: CLIENT, redirect_uri: redirect,
        scope: SCOPE, aud: iss, launch, state, code_challenge: hash, code_challenge_method: 'S256'}).toString();
      return target.href;
    }
    async complete(href) {
      const url = new URL(href);
      const h = consume(this.#storage, url.searchParams, href, this.#now());
      let t = await this.#json(h.token, {method: 'POST', headers: {Accept: 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams({grant_type: 'authorization_code',
        code: h.code, client_id: CLIENT, redirect_uri: h.redirect, code_verifier: h.verifier}).toString()});
      const patient = patientId(t.patient);
      if (t.token_type !== 'Bearer' || typeof t.access_token !== 'string' ||
          !/^[A-Za-z0-9\-._~+/]+=*$/.test(t.access_token) || t.access_token.length > 16000 ||
          !Number.isFinite(t.expires_in) || t.expires_in <= 0 || typeof t.scope !== 'string' ||
          !['patient/Patient.r', 'patient/DiagnosticReport.rs'].every(scope => t.scope.split(/\s+/).includes(scope))) fail();
      // Token exists only in this function's memory, never in storage or rendered output.
      const expires = this.#now() + Math.min(t.expires_in * 1000, TTL);
      const headers = {Accept: 'application/fhir+json', Authorization: 'Bearer ' + t.access_token};
      t = null;
      try {
        const context = await this.#json(h.iss + '/Patient/' + patient, {headers});
        if (context.resourceType !== 'Patient' || context.id !== patient || this.#now() >= expires) fail();
        const bundle = await this.#json(h.iss + '/DiagnosticReport?' + new URLSearchParams({patient, _count: '20'}), {headers});
        if (this.#now() >= expires) fail();
        return reportsFrom(bundle, patient, h.iss);
      } finally { headers.Authorization = ''; }
    }
  }
  const api = {Sandbox, issuer, endpoints, redirectFor, launcherFor, challenge, consume, reportsFrom, KEY, CLIENT, SCOPE, TTL};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ClinLoopSmartSandbox = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
