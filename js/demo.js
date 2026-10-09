/**
 * demo.js: public demo mode.
 *
 * Only a ClinLoop server started with CLINLOOP_DEMO=1 sets window.CLINLOOP_DEMO (in
 * /config.js). On such a server this script shows a banner, fills in the published
 * view-only token and signs in, so anyone with the link sees the full app on synthetic
 * patients. On any other server it does nothing.
 */
(function () {
  'use strict';
  var demo = window.CLINLOOP_DEMO;
  if (!demo || !demo.token) return;

  function run() {
    var ko = (document.documentElement.lang || '').indexOf('ko') === 0;
    var banner = document.createElement('div');
    banner.setAttribute('role', 'note');
    banner.id = 'clinloop-demo-banner';
    banner.style.cssText = 'background:#7c2d12;color:#fff7ed;padding:8px 16px;font:600 13px/1.4 system-ui,sans-serif;' +
      'text-align:center;position:relative;z-index:1000;';
    banner.textContent = ko
      ? '공개 데모: 합성(가상) 환자만 · 읽기 전용 · 재시작 시 초기화 · 실제 환자 정보를 입력하지 마십시오'
      : demo.note;
    document.body.insertBefore(banner, document.body.firstChild);

    var token = document.getElementById('token');
    var form = token && token.closest('form');
    if (!form || form.id !== 'connect-form' || !form.requestSubmit) return;
    var base = document.getElementById('api-base');
    if (base && !base.value) base.value = window.CLINLOOP_API_BASE || window.location.origin;
    if (!token.value) {
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
