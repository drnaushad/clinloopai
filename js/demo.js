/**
 * demo.js: the public demo, for anyone, on any device.
 *
 * Two cases:
 *  1. A ClinLoop server started with CLINLOOP_DEMO=1 sets window.CLINLOOP_DEMO (in /config.js):
 *     banner, published view-only token, automatic sign-in.
 *  2. The public website (clinloopai.app) has no server at all. The clinical pages then read a
 *     read-only snapshot of the demo (demo/api/, built by scripts/build_static_demo.py) through
 *     the same requests they would send to a server: the whole app works from static files, so
 *     any number of people can use it at once. Changes need a real server and say so.
 * On a hospital's own server neither applies and this script does nothing.
 */
(function () {
  'use strict';
  var CLINICAL_PAGE = /\/(worklist|patient|quality|governance|imaging)\.html$/;
  var local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
  var STATIC_PATH = '/__static-demo__';

  if (!window.CLINLOOP_DEMO && window.CLINLOOP_API_BASE == null && !local &&
      CLINICAL_PAGE.test(window.location.pathname) && window.fetch) {
    startStatic();
  }
  var demo = window.CLINLOOP_DEMO;
  if (!demo || !demo.token) return;

  // ── 2. static snapshot ────────────────────────────────────────────────────
  function startStatic() {
    var base = window.location.origin + STATIC_PATH;
    window.CLINLOOP_API_BASE = base;
    document.documentElement.classList.add('static-demo');      // hides the server connection form
    window.CLINLOOP_DEMO = {
      token: 'public-demo-static', static: true,
      note: 'Public demo: synthetic patients only, read-only snapshot. Do not enter real patient information.'
    };
    var realFetch = window.fetch.bind(window);

    function fnv1a(text) {
      var bytes = new TextEncoder().encode(text), h = 0x811c9dc5;
      for (var i = 0; i < bytes.length; i++) {
        h ^= bytes[i];
        h = Math.imul(h, 0x01000193) >>> 0;
      }
      return ('0000000' + h.toString(16)).slice(-8);
    }
    function reply(status, body) {
      return Promise.resolve(new Response(JSON.stringify(body), {
        status: status, headers: { 'Content-Type': 'application/json' }
      }));
    }
    window.fetch = function (input, opts) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.indexOf(base) !== 0) return realFetch(input, opts);
      var method = ((opts && opts.method) || (input && input.method) || 'GET').toUpperCase();
      if (method !== 'GET') {
        return reply(403, { detail: 'This public demo is read-only. Acting on a loop, uploading or signing off ' +
          'needs your own ClinLoop server (see the README: one command with Docker).' });
      }
      var u = new URL(url);
      var path = decodeURIComponent(u.pathname.slice(STATIC_PATH.length));
      var pairs = [];
      u.searchParams.forEach(function (v, k) { if (v !== '') pairs.push([k, v]); });
      pairs.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
      var key = path + (pairs.length ? '?' + pairs.map(function (p) { return p[0] + '=' + p[1]; }).join('&') : '');
      return realFetch(new URL('demo/api/' + fnv1a(key) + '.json', window.location.href).href)
        .then(function (r) {
          return r.ok ? r : reply(404, { detail: 'Not part of the public demo snapshot. ' +
            'Try a listed patient, or run your own server for anything else.' });
        })
        .catch(function () { return reply(503, { detail: 'Could not load the demo snapshot. Check your connection.' }); });
    };
  }

  // ── banner, sign-in, patient list ─────────────────────────────────────────
  function run() {
    var ko = (document.documentElement.lang || '').indexOf('ko') === 0;
    var banner = document.createElement('div');
    banner.setAttribute('role', 'note');
    banner.id = 'clinloop-demo-banner';
    banner.style.cssText = 'background:#7c2d12;color:#fff7ed;padding:8px 16px;font:600 13px/1.4 system-ui,sans-serif;' +
      'text-align:center;position:relative;z-index:1000;overflow-wrap:anywhere;';
    banner.textContent = ko
      ? (demo.static ? '공개 데모: 합성(가상) 환자만 · 읽기 전용 스냅샷 · 실제 환자 정보를 입력하지 마십시오'
                     : '공개 데모: 합성(가상) 환자만 · 읽기 전용 · 재시작 시 초기화 · 실제 환자 정보를 입력하지 마십시오')
      : demo.note;
    document.body.insertBefore(banner, document.body.firstChild);

    if (demo.static) {
      window.fetch(window.CLINLOOP_API_BASE.replace(STATIC_PATH, '') + '/demo/api/index.json')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (index) {
          if (!index) return;
          banner.textContent += ko ? ' · 생성 ' + index.built_at.slice(0, 10) : ' Snapshot of ' + index.built_at.slice(0, 10) + '.';
          var input = document.getElementById('patient');
          if (input && index.patients) {          // patient page: offer the demo patients
            var list = document.createElement('datalist');
            list.id = 'demo-patients';
            index.patients.forEach(function (p) { var o = document.createElement('option'); o.value = p; list.appendChild(o); });
            document.body.appendChild(list);
            input.setAttribute('list', 'demo-patients');
            if (!input.value) input.placeholder = index.patients.slice(0, 3).join(', ') + ' …';
          }
        })
        .catch(function () {});
    }

    var token = document.getElementById('token');
    var form = token && token.closest('form');
    if (!form || form.id !== 'connect-form' || !form.requestSubmit) return;
    var base = document.getElementById('api-base');
    if (base && (demo.static || !base.value)) base.value = window.CLINLOOP_API_BASE || window.location.origin;
    if (demo.static || !token.value) {
      token.value = demo.token;
      form.requestSubmit();
      return;
    }
    // A token from this tab's session is already filled in. Some pages sign in with it
    // themselves; sign in here only if, after a moment, none has happened.
    setTimeout(function () {
      var app = document.getElementById('app');
      var status = document.getElementById('status');
      if (app && app.hidden && !(status && status.textContent.trim())) form.requestSubmit();
    }, 1500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
