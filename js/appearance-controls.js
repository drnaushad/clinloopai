/** Display preferences only. Isolated workspaces never read or write browser storage. */
(function () {
  'use strict';
  function start() {
    var root = document.documentElement, body = document.body;
    var isolated = body.getAttribute('data-isolated-session') === 'true';
    var owned = document.getElementById('theme-opt-light');
    var group, light, dark;
    function selected() {
      if (owned) return body.classList.contains('dark-theme') ? 'dark' : 'light';
      var theme = root.getAttribute('data-theme');
      if (theme === 'light' || theme === 'dark') return theme;
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    function render() {
      var theme = selected(), ko = root.lang.indexOf('ko') === 0;
      if (owned) {
        document.querySelectorAll('#theme-opt-light, #theme-opt-dark').forEach(function (button) {
          button.setAttribute('aria-pressed', String(button.id === 'theme-opt-' + theme));
        });
        return;
      }
      group.setAttribute('aria-label', ko ? '화면 테마' : 'Appearance');
      light.textContent = ko ? '라이트' : 'Light'; dark.textContent = ko ? '다크' : 'Dark';
      light.setAttribute('aria-pressed', String(theme === 'light'));
      dark.setAttribute('aria-pressed', String(theme === 'dark'));
    }
    if (!owned) {
      group = document.createElement('div');group.className = 'appearance-controls';group.setAttribute('role','group');
      light = document.createElement('button');dark = document.createElement('button');
      [light,dark].forEach(function (button, index) {
        button.type = 'button';group.append(button);
        button.addEventListener('click', function () {
          var theme = index ? 'dark' : 'light';root.setAttribute('data-theme',theme);
          if (!isolated) {try { window.localStorage.setItem('clinloop_theme',theme); } catch (error) { /* Preferences are optional. */ }}
          render();
        });
      });
      var language = document.getElementById('btn-lang');
      if (language) language.before(group);
      else {
        var header = document.querySelector('.workspace-header');
        if (header) header.insertBefore(group,header.querySelector('nav'));
        else {var nav=document.querySelector('nav.app-nav');if(nav) nav.after(group);else return;}
      }
    }
    render();
    if (window.MutationObserver) {
      new MutationObserver(render).observe(root,{attributes:true,attributeFilter:['lang','data-theme']});
      if (owned) new MutationObserver(render).observe(body,{attributes:true,attributeFilter:['class']});
    }
    if (window.matchMedia) {var media=window.matchMedia('(prefers-color-scheme: dark)');if(media.addEventListener) media.addEventListener('change',render);}
    var more=document.querySelector('.more-menu');
    if(more) document.addEventListener('keydown',function(event){if(event.key==='Escape'&&more.open){more.open=false;more.querySelector('summary').focus();}});
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
