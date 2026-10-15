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
    return file === '' ? 'index.html' : file;
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

  function start() {
    render();
    // Each page's language switch sets <html lang>; follow it
    new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
