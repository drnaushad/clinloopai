/** Apply display preferences before paint. Never read credentials or report/session data. */
(function (root) {
  'use strict';
  function start(doc, win) {
    var html = doc.documentElement;
    var isolated = html.getAttribute('data-isolated-session') === 'true';
    var theme = win.matchMedia && win.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var language = html.lang || 'en';
    if (!isolated) {
      try {
        var saved = win.localStorage.getItem('clinloop_theme');
        if (saved === 'light' || saved === 'dark') theme = saved;
        if (html.getAttribute('data-language-options') === 'en ko') {
          var storedLanguage = win.localStorage.getItem('clinloop_lang');
          language = storedLanguage === 'ko' || storedLanguage === 'en' ? storedLanguage
            : html.getAttribute('data-workspace') === 'index' ? 'en'
            : (win.navigator.language || '').indexOf('ko') === 0 ? 'ko' : 'en';
        }
      } catch (_) { /* Blocked preference storage must not prevent the page from opening. */ }
      if (html.getAttribute('data-workspace') === 'index' && win.URLSearchParams) {
        var params = new win.URLSearchParams(win.location.search);
        var requestedTheme = params.get('theme'), requestedLanguage = params.get('lang');
        if (requestedTheme === 'light' || requestedTheme === 'dark') theme = requestedTheme;
        if (requestedLanguage === 'en' || requestedLanguage === 'ko') language = requestedLanguage;
      }
    }
    html.setAttribute('data-theme', theme);
    if (html.lang !== language) html.lang = language;
  }
  if (typeof module === 'object' && module.exports) module.exports = {start: start};
  else start(root.document, root);
})(typeof window === 'undefined' ? this : window);
