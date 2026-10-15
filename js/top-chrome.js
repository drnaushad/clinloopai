/**
 * top-chrome.js: on tablets and phones (where the page scrolls) the full top bar scrolls away with the
 * page and a slim bar (#mini-bar: logo + page navigation) slides in over the top once it is gone.
 *
 * The slim bar is position: fixed and moves with a transform, so showing or hiding it never changes the
 * page's layout. An earlier version shrank the sticky top bar instead; that moved the page under the
 * reader's finger, which moved the scroll position back past the threshold, and the bar flickered
 * between its two sizes on every scroll. An IntersectionObserver (no scroll handler) decides.
 * Wide screens use the app shell (css/responsive.css), where the top bar never moves; the slim bar is hidden.
 */
(function () {
  'use strict';
  var bar = document.getElementById('top-chrome');
  var mini = document.getElementById('mini-bar');
  if (!bar || !mini) return;
  function show(on) {
    mini.classList.toggle('is-visible', on);
    if (on) mini.removeAttribute('inert'); else mini.setAttribute('inert', '');
  }
  show(false);
  if (!('IntersectionObserver' in window)) return;
  // Shown once less than 1 px of the top bar is left on screen
  new IntersectionObserver(function (entries) {
    show(!entries[entries.length - 1].isIntersecting);
  }, { threshold: 0 }).observe(bar);
})();
