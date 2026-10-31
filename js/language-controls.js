/** Language labels and decorative flags follow the selected UI language, never nationality.
 * No network, storage, report access or replacement language handlers. */
(function (root, factory) {
  'use strict';
  var ui = factory();
  if (typeof module === 'object' && module.exports) module.exports = ui;
  else ui.mount(root.document, root.MutationObserver);
})(typeof window === 'undefined' ? this : window, function () {
  'use strict';
  // Only app-owned notices are translated. Report text, quotes, names and rule patterns
  // keep their source language and are never rewritten by this presenter.
  var notices = {
    en: {
      snapshot: 'Synthetic snapshot · no live hospital connection. Actions here are browser-only simulations.',
      unavailable: 'Unavailable in this public demo. Use an approved local installation, or try synthetic text in Analyse patient.',
      controls: 'View local-installation controls (unavailable in this demo)',
      analyse: 'Analyse patient',
      serverDemo: 'Public demo: synthetic patients only, read-only snapshot. Do not enter real patient information.',
      loading: 'Loading synthetic examples…',
      loadFailed: 'The examples could not be loaded. Refresh to try again.'
    },
    ko: {
      snapshot: '합성 스냅샷 · 실제 병원과 연결되어 있지 않습니다. 여기의 조치는 브라우저 안에서만 시뮬레이션됩니다.',
      unavailable: '이 공개 데모에서는 사용할 수 없습니다. 승인된 로컬 설치를 사용하거나 환자 분석에서 합성 텍스트를 시험해 보세요.',
      controls: '로컬 설치용 기능 보기 (이 데모에서는 사용할 수 없음)',
      analyse: '환자 분석',
      serverDemo: '공개 데모: 합성(가상) 환자만 · 읽기 전용 스냅샷 · 실제 환자 정보를 입력하지 마십시오.',
      loading: '합성 예시를 불러오는 중입니다…',
      loadFailed: '예시를 불러오지 못했습니다. 새로고침해 주세요.'
    }
  };
  function localizeSessionStatus(doc) {
    var status = doc.getElementById && doc.getElementById('status');
    if (!status || (status.classList && status.classList.contains('error'))) return;
    // Recognize only the app's sign-in status sentence, never arbitrary messages or report text.
    var text = status.textContent;
    var match = /^Signed in as (.+) \(([^()]*)\)\.(?: · as of (.+))?$/.exec(text)
      || /^(.+)\(([^()]*)\)님으로 로그인했습니다\.(?: · 기준 (.+))?$/.exec(text);
    if (!match) return;
    var ko = doc.documentElement.lang.indexOf('ko') === 0;
    var roles = {admin:'관리자',clinician:'의료진',navigator:'진료 조정 담당자',viewer:'조회 사용자'};
    var role = Object.keys(roles).find(function (key) { return roles[key] === match[2]; }) || match[2];
    var roleLabel = ko ? roles[role] || role : role;
    var localized = ko ? match[1] + '(' + roleLabel + ')님으로 로그인했습니다.'
      : 'Signed in as ' + match[1].trimEnd() + ' (' + roleLabel + ').';
    if (match[3]) localized += (ko ? ' · 기준 ' : ' · as of ') + match[3];
    if (status.textContent !== localized) status.textContent = localized;
  }
  function localizeNotices(doc) {
    localizeSessionStatus(doc);
    var copy = notices[doc.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en'];
    doc.querySelectorAll('[data-demo-copy]').forEach(function (el) {
      var text = copy[el.getAttribute('data-demo-copy')];
      if (text && el.textContent !== text) el.textContent = text;
    });
  }
  var messageChoices = {'btn-lang-en':'en','btn-lang-ko':'ko'};
  var fixed = { 'lang-opt-ko': 'ko', 'lang-opt-en': 'en', 'dock-btn-ko': 'ko', 'dock-btn-en': 'en' };
  function target(button) {
    if (fixed[button.id] || messageChoices[button.id]) return fixed[button.id] || messageChoices[button.id];
    if (button.id !== 'btn-lang') return null;
    var text = button.textContent.trim();
    return text === '한국어' || text === 'Korean' ? 'ko' : text === 'English' || text === '영어' ? 'en' : null;
  }
  function decorate(button, current) {
    var language = target(button);
    if (!language) { button.removeAttribute('data-language'); return; }
    button.setAttribute('data-language', language);
    var label = current === 'ko' ? (language === 'ko' ? '한국어' : '영어') : (language === 'ko' ? 'Korean' : 'English');
    if (button.textContent !== label) button.textContent = label;
    button.setAttribute('lang', current === 'ko' ? 'ko' : 'en');
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
    if (fixed[button.id]) button.setAttribute('aria-pressed', String(language === current));
  }
  function mount(doc, Observer) {
    function start() {
      var buttons = Array.from(doc.querySelectorAll('#lang-opt-ko, #lang-opt-en, #dock-btn-ko, #dock-btn-en, #btn-lang, #btn-lang-en, #btn-lang-ko'));
      function update() {
        var current = doc.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en';
        buttons.forEach(function (button) { decorate(button, current); });
        localizeNotices(doc);
      }
      update();
      if (!Observer) return;
      // Translators replace textContent. Observe text only, so our attribute updates cannot loop.
      var textObserver = new Observer(update);
      buttons.forEach(function (button) { textObserver.observe(button, { childList: true, characterData: true, subtree: true }); });
      new Observer(update).observe(doc.documentElement, { attributes: true, attributeFilter: ['lang'] });
      if (doc.body) new Observer(function (records) {
        if (records.some(function (record) {
          var el = record.target.nodeType === 1 ? record.target : record.target.parentElement;
          if (el && el.closest && el.closest('[data-demo-copy], #status')) return true;
          return Array.from(record.addedNodes || []).some(function (node) {
            return node.nodeType === 1 && (node.matches('[data-demo-copy], #status') || node.querySelector('[data-demo-copy], #status'));
          });
        })) localizeNotices(doc);
      }).observe(doc.body, {childList: true, characterData: true, subtree: true});
    }
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
  }
  return { target: target, decorate: decorate, mount: mount, localizeNotices: localizeNotices, localizeSessionStatus: localizeSessionStatus };
});
