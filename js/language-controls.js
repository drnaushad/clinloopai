/** Decorative flags follow the named language, never the user's nationality.
 * No network, storage, report access or replacement language handlers. */
(function (root, factory) {
  'use strict';
  var ui = factory();
  if (typeof module === 'object' && module.exports) module.exports = ui;
  else ui.mount(root.document, root.MutationObserver);
})(typeof window === 'undefined' ? this : window, function () {
  'use strict';
  var fixed = { 'lang-opt-ko': 'ko', 'lang-opt-en': 'en', 'dock-btn-ko': 'ko', 'dock-btn-en': 'en' };
  function target(button) {
    if (fixed[button.id]) return fixed[button.id];
    if (button.id !== 'btn-lang') return null;
    var text = button.textContent.trim();
    return text === '한국어' ? 'ko' : text === 'English' ? 'en' : null;
  }
  function decorate(button, current) {
    var language = target(button);
    if (!language) { button.removeAttribute('data-language'); return; }
    button.setAttribute('data-language', language);
    button.setAttribute('lang', language);
    button.setAttribute('aria-label', language === 'ko' ? '한국어' : 'English');
    if (fixed[button.id]) button.setAttribute('aria-pressed', String(language === current));
  }
  function mount(doc, Observer) {
    function start() {
      var buttons = Array.from(doc.querySelectorAll('#lang-opt-ko, #lang-opt-en, #dock-btn-ko, #dock-btn-en, #btn-lang'));
      function update() {
        var current = doc.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en';
        buttons.forEach(function (button) { decorate(button, current); });
      }
      update();
      if (!Observer) return;
      // Translators replace textContent. Observe text only, so our attribute updates cannot loop.
      var textObserver = new Observer(update);
      buttons.forEach(function (button) { textObserver.observe(button, { childList: true, characterData: true, subtree: true }); });
      new Observer(update).observe(doc.documentElement, { attributes: true, attributeFilter: ['lang'] });
    }
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
  }
  return { target: target, decorate: decorate, mount: mount };
});
