// Network-only service worker. Source reports and API responses have no offline fallback.
self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
  // Cache storage belongs to the origin, including unrelated applications.
  // Do not erase another application's data or reuse a stale clinical response.
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  event.respondWith(fetch(event.request));
});
