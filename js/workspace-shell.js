/** Shared presentation only: preserve existing controls, sessions and event handlers.
 * No model calls, browser storage, authentication values or report content are accessed.
 */
(function () {
  'use strict';
  var ROUTES = ['/', '/worklist', '/patient', '/quality', '/governance', '/pilot', '/imaging',
    '/analyse', '/reports', '/review', '/private', '/validation', '/deployment'];

  function route(href) {
    if (typeof href !== 'string') return null;
    var path = href.replace(/\?lang=(?:en|ko)$/, '').replace(/^\.\//, '/');
    if (path.charAt(0) !== '/') path = '/' + path;
    path = path.replace(/\/index\.html$/, '/').replace(/\.html$/, '');
    return ROUTES.indexOf(path) >= 0 ? path : null;
  }
  function destination(value, current) {
    var next = route(value);
    return next && next !== route(current) ? next : null;
  }
  function catalog(links, language) {
    var seen = {};
    return Array.from(links).reduce(function (items, link) {
      var path = route(link.getAttribute('href'));
      if (!path || seen[path]) return items;
      seen[path] = true;
      items.push({ path: path, label: link.getAttribute('data-label-' + (language || 'en')) || link.textContent.trim(),
        group: ROUTES.indexOf(path) < 8 ? 0 : ROUTES.indexOf(path) < 11 ? 1 : 2 });
      return items;
    }, []).sort(function (a, b) { return ROUTES.indexOf(a.path) - ROUTES.indexOf(b.path); });
  }
  function mount(doc, win) {
    var nav = doc.querySelector('nav.app-nav, nav.workspace-nav');
    if (!nav) return;
    var shell = doc.querySelector('.clinloop-shell');
    if (shell && shell.getAttribute('data-shell-bound') === 'true') return;
    var controls, mobile, label, picker;
    if (shell) {
      // The header is already in its final place before paint. Attach behavior only.
      controls = shell.querySelector('.clinloop-shell-controls');
      mobile = shell.querySelector('.clinloop-shell-mobile');
      label = mobile.querySelector('label');
      picker = mobile.querySelector('select');
    } else {
    var cockpit = doc.querySelector('.cockpit-workspace');
    var oldWorkspace = doc.querySelector('.workspace-header');
    var oldCockpit = doc.querySelector('.app-header--pro');
    shell = doc.createElement('header'); shell.className = 'clinloop-shell';
    var top = doc.createElement('div'); top.className = 'clinloop-shell-top';
    controls = doc.createElement('div'); controls.className = 'clinloop-shell-controls';
    var brand = cockpit && oldCockpit ? oldCockpit.querySelector('.brand-section') : null;
    if (!brand) {
      brand = doc.createElement('a'); brand.href = './'; brand.className = 'clinloop-shell-brand';
      var logo = doc.createElement('img'); logo.src = 'icons/logo.svg'; logo.alt = ''; logo.width = 32; logo.height = 32;
      var name = doc.createElement('span'); name.textContent = 'ClinLoop AI'; brand.append(logo, name);
    }
    var language = doc.getElementById('btn-lang');
    if (cockpit && oldCockpit) {
      ['.theme-segmented-control', '.prominent-lang-pill'].forEach(function (selector) {
        var group = oldCockpit.querySelector(selector); if (group) controls.append(group);
      });
    } else if (language) {
      var account = language.parentElement;
      account.setAttribute('role', 'group'); account.setAttribute('data-shell-account', '');
      controls.append(account);
    } else {
      var appearance = doc.querySelector('.appearance-controls'); if (appearance) controls.append(appearance);
    }
    var host = cockpit ? doc.getElementById('top-chrome') : doc.body;
    host.prepend(shell); top.append(brand, controls); shell.append(top, nav);
    nav.classList.add('clinloop-shell-links');
    mobile = doc.createElement('div'); mobile.className = 'clinloop-shell-mobile';
    label = doc.createElement('label'); label.htmlFor = 'clinloop-page-picker';
    picker = doc.createElement('select'); picker.id = 'clinloop-page-picker';
    mobile.append(label, picker); shell.append(mobile);
    if (cockpit && oldCockpit) {
      var tools = doc.createElement('div'); tools.className = 'app-header--pro cockpit-tools';
      var actions = oldCockpit.querySelector('.header-actions'); if (actions) tools.append(actions);
      oldCockpit.replaceWith(tools);
    }
    if (oldWorkspace) oldWorkspace.remove();
    doc.body.classList.add('clinloop-page');
    if (!cockpit && !doc.querySelector('.wrap, main')) {
      var main = doc.createElement('main'); main.className = 'clinloop-content';
      Array.from(doc.body.children).forEach(function (child) {
        if (child !== shell && child.tagName !== 'SCRIPT' && !child.classList.contains('skip-link')) main.append(child);
      });
      doc.body.append(main);
    }
    var content = doc.querySelector('.cockpit-workspace, .wrap, main');
    if (content && !doc.querySelector('.skip-link')) {
      if (!content.id) content.id = 'clinloop-workspace';
      if (content.tagName !== 'MAIN') content.setAttribute('role', 'main');
      content.setAttribute('tabindex', '-1');
      var skip = doc.createElement('a'); skip.className = 'skip-link shell-skip'; skip.href = '#' + content.id;
      doc.body.prepend(skip);
    }
    // Keep the original translated title nodes; remove only the redundant brand prefix.
    if (!cockpit) doc.querySelectorAll('.wrap > header h1').forEach(function (heading) {
      Array.from(heading.childNodes).forEach(function (node) {
        if (node.nodeType === 3) node.textContent = node.textContent.replace(/^ClinLoop\s+/, '');
      });
    });
    }
    shell.setAttribute('data-shell-bound', 'true');
    var signature = '';
    function revealActive() {
      var active = nav.querySelector('[aria-current="page"]');
      if (!active || nav.scrollWidth <= nav.clientWidth) return;
      var item = active.getBoundingClientRect(), edge = nav.getBoundingClientRect();
      if (item.left < edge.left + 8) nav.scrollLeft += item.left - edge.left - 8;
      else if (item.right > edge.right - 8) nav.scrollLeft += item.right - edge.right + 8;
    }
    function sync() {
      var ko = doc.documentElement.lang.indexOf('ko') === 0;
      var here = route(win.location.pathname) || '/';
      var labelText = ko ? '화면 이동' : 'Go to page';
      if (label.textContent !== labelText) label.textContent = labelText;
      nav.setAttribute('aria-label', ko ? 'ClinLoop 화면' : 'ClinLoop pages');
      nav.querySelectorAll('a[href]').forEach(function (link) {
        if (route(link.getAttribute('href')) === here) {
          if (link.getAttribute('aria-current') !== 'page') link.setAttribute('aria-current', 'page');
        } else if (link.getAttribute('aria-current') !== null) link.removeAttribute('aria-current');
      });
      controls.setAttribute('role', 'group');
      controls.setAttribute('aria-label', ko ? '화면 및 계정 설정' : 'Display and account');
      var themeGroup = controls.querySelector('.theme-segmented-control');
      if (themeGroup) themeGroup.setAttribute('aria-label', ko ? '화면 테마' : 'Appearance');
      var languageGroup = controls.querySelector('.prominent-lang-pill');
      if (languageGroup) languageGroup.setAttribute('aria-label', ko ? '언어' : 'Language');
      var account = controls.querySelector('[data-shell-account]');
      if (account) account.setAttribute('aria-label', ko ? '화면 및 계정 설정' : 'Display and account');
      var skip = doc.querySelector('.shell-skip'); if (skip) skip.textContent = ko ? '작업 공간으로 건너뛰기' : 'Skip to workspace';
      var items = catalog(nav.querySelectorAll('a[href]'), ko ? 'ko' : 'en');
      var next = JSON.stringify([ko, items]);
      if (next !== signature) {
        signature = next;
        var groups = (ko ? ['진료 작업 공간', '연구', '검증 및 설정'] : ['Clinical workspace', 'Research', 'Evidence and setup']).map(function (text) {
          var group = doc.createElement('optgroup'); group.label = text; return group;
        });
        items.forEach(function (item) {
          var option = doc.createElement('option'); option.value = item.path; option.textContent = item.label;
          groups[item.group].append(option);
        });
        picker.replaceChildren.apply(picker, groups);
      }
      // Back/Forward can restore the old select value from the page cache.
      // Always reflect the actual address, even when the labels did not change.
      picker.value = here;
      if (win.requestAnimationFrame) win.requestAnimationFrame(revealActive);
    }
    picker.addEventListener('change', function () {
      var next = destination(picker.value, win.location.pathname);
      if (next) win.location.assign(next + '?lang=' + (doc.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en'));
      else picker.value = route(win.location.pathname) || '/';
    });
    sync();
    if (win.addEventListener) {
      win.addEventListener('pageshow', sync);
      win.addEventListener('popstate', sync);
    }
    if (win.ResizeObserver) new win.ResizeObserver(revealActive).observe(nav);
    if (win.MutationObserver) {
      new win.MutationObserver(sync).observe(nav, {childList: true, subtree: true, characterData: true});
      new win.MutationObserver(sync).observe(doc.documentElement, {attributes: true, attributeFilter: ['lang']});
    }
  }
  if (typeof module === 'object' && module.exports) module.exports = {route: route, destination: destination, catalog: catalog, mount: mount};
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { mount(document, window); }, {once: true});
    else mount(document, window);
  }
})();
