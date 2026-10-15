/**
 * top-chrome.js: the cockpit's top bar stays pinned (CSS position: sticky) and condenses to one row
 * once the reader has scrolled down. Two thresholds (hysteresis) stop it flickering at the edge,
 * because condensing makes the bar shorter and so moves the page under it.
 */
(function () {
  'use strict';
  var bar = document.getElementById('top-chrome');
  if (!bar) return;
  var CONDENSE_AT = 80, EXPAND_AT = 8, ticking = false;
  function update() {
    ticking = false;
    var y = window.scrollY || document.documentElement.scrollTop || 0;
    if (!bar.classList.contains('is-condensed') && y > CONDENSE_AT) bar.classList.add('is-condensed');
    else if (bar.classList.contains('is-condensed') && y < EXPAND_AT) bar.classList.remove('is-condensed');
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
  }, { passive: true });
  update();
})();
