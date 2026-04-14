const CACHE_VERSION = 'tsumevault-v1';

const STATIC_ASSETS = [
  '/tsumevault.html',
  '/wgo/wgo.min.js',
  '/wgo/sgfparser.js',
  '/wgo/kifu.js',
  '/audio/stone.mp3',
  '/audio/right.mp3',
  '/audio/wrong.mp3',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

// Instalación: cachear assets estáticos
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_VERSION).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activación: borrar caches antiguas
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: cache-first para SGFs y assets estáticos, network-first para API
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API del servidor — nunca cachear
  if (url.port === '3002' || url.pathname.startsWith('/db/') || url.pathname.startsWith('/sync/')) {
    return; // deja pasar al navegador
  }

  // SGFs — cache on demand (network-first con fallback a cache)
  if (url.pathname.endsWith('.sgf')) {
    e.respondWith(
      caches.open(CACHE_VERSION).then(async cache => {
        const cached = await cache.match(e.request);
        if (cached) return cached;
        try {
          const response = await fetch(e.request);
          if (response.ok) cache.put(e.request, response.clone());
          return response;
        } catch {
          return cached || new Response('SGF not found', { status: 404 });
        }
      })
    );
    return;
  }

  // sql.js WASM desde CDN — cache on demand
  if (url.hostname === 'cdnjs.cloudflare.com') {
    e.respondWith(
      caches.open(CACHE_VERSION).then(async cache => {
        const cached = await cache.match(e.request);
        if (cached) return cached;
        const response = await fetch(e.request);
        if (response.ok) cache.put(e.request, response.clone());
        return response;
      })
    );
    return;
  }

  // Assets estáticos — cache-first
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});

// Mensaje desde el cliente para pre-cachear SGFs nuevos
self.addEventListener('message', e => {
  if (e.data?.type === 'PRECACHE_SGFS') {
    const urls = e.data.urls || [];
    caches.open(CACHE_VERSION).then(async cache => {
      for (const url of urls) {
        const cached = await cache.match(url);
        if (!cached) {
          try {
            const response = await fetch(url);
            if (response.ok) cache.put(url, response.clone());
          } catch {}
        }
      }
      // Notificar al cliente cuando termine
      e.source?.postMessage({ type: 'PRECACHE_DONE' });
    });
  }
});
