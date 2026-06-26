/* TG Stremio online-only service worker: no Cache API, no offline fallback. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // Remove any old cache left by previous builds, then claim clients.
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  // Network only. Offline requests intentionally fail instead of using saved pages/data.
  event.respondWith(fetch(event.request, { cache: 'no-store' }));
});
