/**
 * appnav.js: one navigation for every ClinLoop page.
 *
 * Fills each <nav class="app-nav"> with the same links (Cockpit, Worklist, Patient graph, Quality,
 * Rule sign-off, Imaging), marks the current page (aria-current="page") and follows the page
 * language: <html lang> is set by every page's own language switch, so the labels update with it.
 * Deep links (#loop=…, #patient=…) are left to each page.
 */
(function () {
  'use strict';
  var PAGES = [
    { href: 'index.html', en: 'Cockpit', ko: '종합 화면' },
    { href: 'worklist.html', en: 'Worklist', ko: '업무 목록' },
    { href: 'patient.html', en: 'Patient graph', ko: '환자 그래프' },
    { href: 'quality.html', en: 'Quality', ko: '품질 지표' },
    { href: 'governance.html', en: 'Rule sign-off', ko: '규칙 승인' },
    { href: 'pilot.html', en: 'Pilot review', ko: '시범 검토' },
    { href: 'imaging.html', en: 'Imaging', ko: '영상' }
  ];

  // The Light/Dark choice made on the cockpit applies here too; without one, the page follows the device
  try {
    var theme = window.localStorage.getItem('clinloop_theme');
    if (theme === 'light' || theme === 'dark') document.documentElement.setAttribute('data-theme', theme);
  } catch (e) { /* storage blocked: follow the device */ }

  function current() {
    var file = window.location.pathname.split('/').pop() || 'index.html';
    return /\.html$/.test(file) ? file : file + '.html';     // "/worklist" is worklist.html
  }

  function render() {
    var navs = document.querySelectorAll('nav.app-nav');
    if (!navs.length) return;
    var ko = (document.documentElement.lang || '').indexOf('ko') === 0;
    var here = current();
    navs.forEach(function (nav) {
      if (!nav.getAttribute('aria-label')) nav.setAttribute('aria-label', ko ? 'ClinLoop 화면' : 'ClinLoop pages');
      nav.replaceChildren.apply(nav, PAGES.map(function (p) {
        var a = document.createElement('a');
        a.href = p.href;
        a.textContent = ko ? p.ko : p.en;
        a.className = 'app-nav-link';
        if (p.href === here) a.setAttribute('aria-current', 'page');
        return a;
      }));
    });
  }

  // A table or list that scrolls but holds nothing focusable cannot be scrolled from the keyboard
  // (WCAG 2.1.1): make it a focusable, labelled region. Pages render their tables later, so this re-runs.
  function focusableScrollers() {
    document.querySelectorAll('table, .case-queue-list, .scroll, .table-wrap').forEach(function (el) {
      if (el.hasAttribute('data-scroll-focus')) return;
      var scrolls = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
      if (!scrolls || el.querySelector('a, button, input, select, textarea, [tabindex]')) return;
      el.setAttribute('tabindex', '0');
      el.setAttribute('data-scroll-focus', '');
      if (!el.getAttribute('role') && el.tagName !== 'TABLE') el.setAttribute('role', 'region');
      var heading = el.closest('section, .card, div') && el.closest('section, .card, div').querySelector('h2, h3');
      if (!el.getAttribute('aria-label') && heading) el.setAttribute('aria-label', heading.textContent.trim().slice(0, 80));
    });
  }
  // ── Signing in once for every page ───────────────────────────────────────────────────────────
  // The clinical pages share one sign-in per browser tab (sessionStorage, gone when the tab closes):
  //  * served by the ClinLoop server, the API address is the page's own, so its field is hidden;
  //  * a token from this tab signs the page in again without asking (on every page, not only some);
  //  * "Sign out" forgets the token, for shared ward computers.
  // The public demo (js/demo.js) signs itself in and is left alone.
  function stored(key) { try { return sessionStorage.getItem(key) || ''; } catch (e) { return ''; } }
  function keep(key, value) {
    try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch (e) {}
  }
  function forget() { ['clinloop_token', 'clinloop_id_token', 'clinloop_token_exp', 'clinloop_sso'].forEach(function (k) { keep(k, null); }); }

  // ── Hospital single sign-on (OpenID Connect: authorization code with PKCE, no secret in the page) ──
  // Configured on the server (oidc.py), which publishes the public values in config.js. The provider
  // sends people back to worklist.html; from there they return to the page they started on.
  var SSO = window.CLINLOOP_OIDC || null;
  var CALLBACK = '/worklist.html';
  function b64url(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function randomText(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return b64url(a); }
  function ssoStart() {
    var verifier = randomText(48), st = randomText(24), nonce = randomText(24);
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)).then(function (hash) {
      keep('clinloop_sso', JSON.stringify({ v: verifier, s: st, n: nonce, back: location.pathname + location.hash }));
      var q = new URLSearchParams({ response_type: 'code', client_id: SSO.client_id, redirect_uri: location.origin + CALLBACK,
        scope: SSO.scope, state: st, nonce: nonce, code_challenge: b64url(new Uint8Array(hash)), code_challenge_method: 'S256' });
      location.assign(SSO.authorization_endpoint + (SSO.authorization_endpoint.indexOf('?') < 0 ? '?' : '&') + q.toString());
    });
  }
  function idTokenNonce(idToken) {
    try { return JSON.parse(atob(idToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).nonce; } catch (e) { return null; }
  }
  // Back from the provider with ?code=…&state=…: exchange the code, keep the token for this tab
  function ssoCallback(done) {
    var p = new URLSearchParams(location.search);
    if (!SSO || !(p.get('code') || p.get('error'))) return false;
    var saved = null;
    try { saved = JSON.parse(stored('clinloop_sso') || 'null'); } catch (e) { saved = null; }
    keep('clinloop_sso', null);
    history.replaceState(null, '', location.pathname + location.hash);       // the code is single-use: drop it
    if (p.get('error') || !saved || p.get('state') !== saved.s) { done(null, p.get('error') || 'the sign-in did not match this tab'); return true; }
    fetch(SSO.token_endpoint, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ grant_type: 'authorization_code', code: p.get('code'), redirect_uri: location.origin + CALLBACK,
        client_id: SSO.client_id, code_verifier: saved.v }) })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }, function () { return { ok: false, b: {} }; }); })
      .then(function (x) {
        var tok = x.ok && x.b[SSO.send];
        if (!tok) return done(null, x.b.error || 'no token from the identity provider');
        if (x.b.id_token && idTokenNonce(x.b.id_token) !== saved.n) return done(null, 'the sign-in response did not match this tab');
        keep('clinloop_token', tok);
        if (x.b.id_token) keep('clinloop_id_token', x.b.id_token);
        keep('clinloop_token_exp', String(Date.now() + 1000 * (Number(x.b.expires_in) || 300)));
        if (saved.back && saved.back.split('#')[0] !== location.pathname) { location.replace(saved.back); return; }
        done(tok);
      }, function () { done(null, 'identity provider unreachable'); });
    return true;
  }

  function session() {
    var form = document.getElementById('connect-form');
    if (!form || window.CLINLOOP_DEMO) return;
    var base = document.getElementById('api-base'), token = document.getElementById('token');
    var app = document.getElementById('app'), lang = document.getElementById('btn-lang');
    var status = document.getElementById('status');
    var ko = function () { return (document.documentElement.lang || '').indexOf('ko') === 0; };
    // A hospital sign-in expires: then sign in again instead of failing on every request
    var exp = Number(stored('clinloop_token_exp') || 0);
    if (exp && Date.now() > exp - 30000) forget();
    if (base && window.CLINLOOP_API_BASE && window.CLINLOOP_API_BASE === window.location.origin) {
      if (!base.value) base.value = window.location.origin;
      var field = base.closest('div');
      if (field && field !== form) field.hidden = true;
    }
    if (lang && !document.getElementById('btn-signout')) {
      var out = document.createElement('button');
      out.type = 'button';
      out.id = 'btn-signout';
      out.hidden = true;
      out.addEventListener('click', function () {
        var idToken = stored('clinloop_id_token');
        forget();
        if (token) token.value = '';
        if (SSO && SSO.end_session_endpoint && idToken) {          // also end the hospital session
          var q = new URLSearchParams({ client_id: SSO.client_id, id_token_hint: idToken,
            post_logout_redirect_uri: location.origin + location.pathname });
          location.assign(SSO.end_session_endpoint + (SSO.end_session_endpoint.indexOf('?') < 0 ? '?' : '&') + q.toString());
          return;
        }
        window.location.reload();
      });
      lang.parentNode.insertBefore(out, lang);
      var sync = function () {
        var ko = (document.documentElement.lang || '').indexOf('ko') === 0;
        out.textContent = ko ? '로그아웃' : 'Sign out';
        out.hidden = !(app && !app.hidden && stored('clinloop_token'));
      };
      sync();
      if (app) new MutationObserver(sync).observe(app, { attributes: true, attributeFilter: ['hidden'] });
      new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
    }
    if (SSO && !document.getElementById('btn-sso')) {
      var sso = document.createElement('button');
      sso.type = 'button';
      sso.id = 'btn-sso';
      sso.className = 'primary';
      sso.addEventListener('click', function () {
        if (!window.isSecureContext || !window.crypto || !crypto.subtle) {     // PKCE needs the browser's crypto
          if (status) {
            status.textContent = ko() ? '병원 계정 로그인은 HTTPS 주소에서만 사용할 수 있습니다. 관리자에게 문의하세요.'
              : 'Hospital sign-in works only over HTTPS. Ask your administrator for the https:// address.';
            status.classList.add('error');
          }
          return;
        }
        ssoStart();
      });
      var submit = form.querySelector('button[type="submit"]');
      // Both ways in share the submit button's place in the form's layout
      var pair = document.createElement('div');
      pair.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;align-items:end;';
      submit.parentNode.insertBefore(pair, submit);
      pair.appendChild(sso);
      pair.appendChild(submit);
      submit.classList.remove('primary');                    // the hospital account is the usual way in
      var label = function () { sso.textContent = ko() ? '병원 계정으로 로그인' : 'Sign in with hospital account'; };
      label();
      new MutationObserver(label).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
    }
    var handled = ssoCallback(function (tok, err) {
      if (tok) {
        if (token) token.value = tok;
        if (base && base.value && form.requestSubmit) form.requestSubmit();
      } else if (status) {
        status.textContent = (ko() ? '병원 계정 로그인 실패: ' : 'Hospital sign-in failed: ') + err;
        status.classList.add('error');
      }
    });
    if (handled) return;
    if (token && !token.value) token.value = stored('clinloop_token');
    if (token && token.value && base && base.value && app && app.hidden && form.requestSubmit) form.requestSubmit();
  }

  var pending = null;
  function soon() { if (!pending) pending = setTimeout(function () { pending = null; focusableScrollers(); }, 300); }

  function start() {
    render();
    session();
    focusableScrollers();
    new MutationObserver(soon).observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', soon);
    // Each page's language switch sets <html lang>; follow it
    new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
