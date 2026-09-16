/* Cache the shell so the app still opens in a basement or on the Tube.
   Map tiles are deliberately NOT cached - the tile set for 450 venues across London is
   unbounded, and OSM's usage policy discourages bulk caching. You get the app, your
   places and their details offline; you just don't get fresh map imagery. */
const V = 'london-v2';
const SHELL = [
  './', 'index.html', 'style.css', 'app.js',
  'vendor/leaflet-1.9.4.js', 'vendor/leaflet-1.9.4.css',
  'manifest.json', 'icons/icon-192.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== V).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;        // tiles and Instagram: straight to network

  // pins.json changes whenever a new venue is added, so always try the network first and
  // fall back to the last copy we saw.
  if (url.pathname.endsWith('pins.json')) {
    e.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(V).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Stale-while-revalidate for the shell: serve the cached copy instantly, but always
  // refresh it in the background. Plain cache-first would pin users to whatever version
  // they first installed until the cache name changed - easy to forget on a deploy, and
  // it silently strands people on old code.
  e.respondWith(
    caches.match(request).then((hit) => {
      const fresh = fetch(request)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(V).then((c) => c.put(request, copy));
          }
          return res;
        })
        .catch(() => hit);
      return hit || fresh;
    })
  );
});
