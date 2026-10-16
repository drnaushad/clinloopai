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
    { href: 'imaging.html', en: 'Imaging', ko: '영상' }
  ];

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
  function session() {
    var form = document.getElementById('connect-form');
    if (!form || window.CLINLOOP_DEMO) return;
    var base = document.getElementById('api-base'), token = document.getElementById('token');
    var app = document.getElementById('app'), lang = document.getElementById('btn-lang');
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
        try { sessionStorage.removeItem('clinloop_token'); } catch (e) {}
        if (token) token.value = '';
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
