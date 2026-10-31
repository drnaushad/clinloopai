/** Interface-only bilingual copy. Never translate reports, prompts, model output or credentials. */
(function (root, factory) {
  'use strict';
  var copy = typeof module === 'object' && module.exports ? require('./interface-copy.js') : root.ClinLoopInterfaceCopy;
  var api = factory(copy || {});
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { root.ClinLoopUI = api; api.mount(root.document, root); }
})(typeof window === 'undefined' ? this : window, function (copy) {
  'use strict';
  var catalogueLabels = {"췌장 MRI f/u": "Pancreatic MRI follow-up", "요추 MRI": "Lumbar MRI", "뇌 CT": "Brain CT", "Korean report: MedGemma adds the gynaecology referral (부인과 진료 권함).": "Korean report: MedGemma adds a gynaecology referral.", "Normal report: 'f/u 불필요'. MedGemma quoted it; the check removes it.": "Normal report: no follow-up needed. MedGemma quoted this; the check removes it.", "Normal report: simple renal cyst, explicit 'f/u 불필요'.": "Normal report: simple renal cyst; follow-up explicitly not needed."};
  var originals = new WeakMap(), placeholders = new WeakMap(), attributes = new WeakMap(), documentRef;
  var templates = Object.keys(copy).filter(function (key) { return /\{\d+\}/.test(key); }).map(function (key) {
    var indices = [], pattern = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\{(\d+)\\\}/g, function (_, index) { indices.push(index); return '(.*?)'; });
    return {pattern: new RegExp('^' + pattern + '$'), indices: indices, target: copy[key]};
  });
  var routes = ['/', '/worklist', '/patient', '/quality', '/governance', '/pilot', '/imaging', '/analyse', '/reports', '/review', '/private', '/validation', '/deployment'];
  function normalized(text) { return String(text).replace(/\s+/g, ' ').trim(); }
  function language() { return documentRef && documentRef.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en'; }
  function translate(text, lang) {
    text = String(text);
    if (lang !== 'ko') return text;
    var key = normalized(text);
    if (Object.prototype.hasOwnProperty.call(copy, key)) return text.match(/^\s*/)[0] + copy[key] + text.match(/\s*$/)[0];
    for (var i = 0; i < templates.length; i++) {
      var item = templates[i], match = item.pattern.exec(key);
      if (match) return item.target.replace(/\{(\d+)\}/g, function (_, index) { return match[item.indices.indexOf(index) + 1]; });
    }
    return text;
  }
  function display(text, lang) { return translate(catalogueLabels[String(text)] || text, lang || language()); }
  function reset(el) { originals.delete(el); el.removeAttribute('data-ui-copy'); }
  function source(el, value) { reset(el); el.textContent = value; }
  function set(el, value) {
    // Call only for app-owned labels and status messages. Source-bearing nodes stay unmarked.
    var text = catalogueLabels[String(value)] || String(value);
    originals.set(el, text); el.setAttribute('data-ui-copy', ''); el.textContent = translate(text, language());
  }
  function render(doc) {
    var lang = doc.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en';
    doc.querySelectorAll('[data-ui-copy]').forEach(function (el) {
      if (!originals.has(el)) originals.set(el, el.textContent);
      var text = translate(originals.get(el), lang);
      if (el.textContent !== text) el.textContent = text;
    });
    doc.querySelectorAll('[data-ui-placeholder]').forEach(function (el) {
      if (!placeholders.has(el)) placeholders.set(el, el.getAttribute('placeholder') || '');
      el.setAttribute('placeholder', translate(placeholders.get(el), lang));
    });
  }
  function renderAttributes(doc) {
    if (!doc.querySelectorAll) return;
    var lang = doc.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en';
    doc.querySelectorAll('[data-ui-attributes]').forEach(function (el) {
      var values = attributes.get(el);
      if (!values) {
        values = {};
        (el.getAttribute('data-ui-attributes') || '').split(/\s+/).forEach(function (name) {
          if (['title','aria-label','alt','placeholder'].indexOf(name) >= 0 && el.getAttribute(name) !== null) values[name] = el.getAttribute('data-ui-en-' + name) || el.getAttribute(name);
        });
        attributes.set(el, values);
      }
      Object.keys(values).forEach(function (name) {
        var value = translate(values[name], lang);
        if (el.getAttribute(name) !== value) el.setAttribute(name, value);
      });
    });
  }
  function navigationHref(href, lang, theme) {
    if (typeof href !== 'string') return null;
    var parts = href.split('#'), anchor = parts.length === 2 && /^[A-Za-z][A-Za-z0-9_-]*$/.test(parts[1]) ? '#' + parts[1] : '';
    if (parts.length > 2 || (parts.length === 2 && !anchor)) return null;
    var bare = parts[0].replace(/\?(?:lang=(?:en|ko)(?:&theme=(?:light|dark))?|theme=(?:light|dark))$/, '');
    var path = bare === './' ? '/' : (bare.charAt(0) === '/' ? bare : '/' + bare);
    path = path.replace(/\/index\.html$/, '/').replace(/\.html$/, '');
    return routes.indexOf(path) < 0 && path !== '/smart/launch' ? null : bare + '?lang=' + (lang === 'ko' ? 'ko' : 'en')
      + (theme === 'light' || theme === 'dark' ? '&theme=' + theme : '') + anchor;
  }
  function mount(doc, win) {
    documentRef = doc;
    function start() {
      var owned = doc.documentElement.getAttribute('data-workspace') === 'index';
      var legacy = doc.getElementById('btn-lang');
      var en = doc.getElementById('lang-opt-en'), ko = doc.getElementById('lang-opt-ko');
      var previousLanguage = language(), previousTheme = doc.documentElement.getAttribute('data-theme');
      function update() {
        render(doc);
        renderAttributes(doc);
        var lang = language();
        var theme = doc.documentElement.getAttribute('data-theme');
        if ((lang !== previousLanguage || theme !== previousTheme) && win.history && win.history.replaceState && win.URLSearchParams) {
          var params = new win.URLSearchParams(win.location.search); params.set('lang', lang);
          if (theme === 'light' || theme === 'dark') params.set('theme', theme);
          win.history.replaceState(win.history.state, '', win.location.pathname + '?' + params.toString() + (win.location.hash || ''));
        }
        previousLanguage = lang; previousTheme = theme;
        if (en) en.setAttribute('aria-pressed', String(lang === 'en'));
        if (ko) ko.setAttribute('aria-pressed', String(lang === 'ko'));
        doc.querySelectorAll('a[href]').forEach(function (a) {
          var href = navigationHref(a.getAttribute('href'), lang, doc.documentElement.getAttribute('data-theme'));
          if (href && a.getAttribute('href') !== href) a.setAttribute('href', href);
        });
      }
      function choose(lang) {
        if (lang === language()) return;
        if (legacy) legacy.click(); // Retain the clinical page's own translations and handlers.
        else doc.documentElement.lang = lang;
        if (doc.documentElement.getAttribute('data-isolated-session') !== 'true' && !legacy) {
          try { win.localStorage.setItem('clinloop_lang', lang); } catch (_) { /* Optional display preference. */ }
        }
        update();
      }
      if (!owned) {
        if (en) en.addEventListener('click', function () { choose('en'); });
        if (ko) ko.addEventListener('click', function () { choose('ko'); });
      }
      // Query carries display language into isolated pages without storing session information.
      var requested = win.URLSearchParams && new win.URLSearchParams(win.location.search).get('lang');
      if (!owned && (requested === 'en' || requested === 'ko')) choose(requested);
      update();
      if (win.MutationObserver && doc.body) new win.MutationObserver(function (records) {
        if (records.some(function (record) { return Array.from(record.addedNodes || []).some(function (node) { return node.nodeType === 1 && (node.matches('[data-ui-attributes]') || node.querySelector('[data-ui-attributes]')); }); })) renderAttributes(doc);
      }).observe(doc.body, {childList:true, subtree:true});
      if (win.MutationObserver) new win.MutationObserver(update).observe(doc.documentElement, {attributes: true, attributeFilter: ['lang', 'data-theme']});
    }
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start, {once: true}); else start();
  }
  return {translate: translate, display: display, set: set, source: source, reset: reset, render: render, renderAttributes: renderAttributes, mount: mount, navigationHref: navigationHref};
});
