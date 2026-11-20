// VideoPocket service worker.
//
// Caches ONLY the static app shell (HTML/CSS/JS/icons/manifest) so the UI
// itself can open instantly from a PWA install. It deliberately never
// intercepts /api/* requests — analysis, job status, and video downloads
// always hit the network directly. There is no offline video downloading:
// this cache only makes the interface open faster/offline, not functional
// without the server.
const CACHE_NAME = 'videopocket-shell-v1';
const SHELL_FILES = [
  './',
  'index.html',
  'styles.css',
  'app.js',
  'config.js',
  'manifest.webmanifest',
  'assets/icon-192.png',
  'assets/icon-512.png',
  'assets/icon-maskable-192.png',
  'assets/icon-maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache or intercept API calls or the video download route: always
  // go to the network so analysis, progress, and files are always fresh.
  if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
    return;
  }

  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).catch(() => cached);
    })
  );
});
