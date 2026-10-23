/** Address and keyboard navigation only: no requests, storage or shared session. */
(function () {
  'use strict';
  if (location.hostname === 'clinloopai.app' && location.protocol === 'http:') {
    location.replace('https://clinloopai.app' + location.pathname + location.search + location.hash);
    return;
  }
  if (/\/(private|review)\.html$/.test(location.pathname) && location.protocol !== 'file:') {
    try { history.replaceState(history.state, '', location.pathname.replace(/\.html$/, '') + location.search + location.hash); }
    catch (error) { /* Keep the original address if the browser refuses. */ }
  }
  var nav = document.querySelector('.workspace-nav');
  if (!nav) return;
  nav.addEventListener('focusin', function (event) {
    var link = event.target.closest('a');
    if (!link) return;
    var item = link.getBoundingClientRect(), edge = nav.getBoundingClientRect();
    if (item.right > edge.right) nav.scrollLeft += item.right - edge.right + 8;
    else if (item.left < edge.left) nav.scrollLeft -= edge.left - item.left + 8;
  });
  var active = nav.querySelector('[aria-current="page"]');
  if (active && active.getBoundingClientRect().right > nav.getBoundingClientRect().right) {
    nav.scrollLeft = Math.max(0, active.offsetLeft - nav.firstElementChild.offsetLeft - 8);
  }
})();
