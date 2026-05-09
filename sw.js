const CACHE_VERSION = 'tsumevault-v20';

const STATIC_ASSETS = [
  '/tsumevault/tsumevault.html',
  '/tsumevault/wgo/wgo.min.js',
  '/tsumevault/wgo/sgfparser.js',
  '/tsumevault/wgo/kifu.js',
  '/tsumevault/audio/stone.mp3',
  '/tsumevault/audio/right.mp3',
  '/tsumevault/audio/wrong.mp3',
  '/tsumevault/img/icons/icon-192.png',
  '/tsumevault/img/icons/icon-512.png',
];

// Instalación: cachear assets estáticos
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_VERSION).then(async cache => {
      for (const url of STATIC_ASSETS) {
        try {
          await cache.add(url);
        } catch {}
      }
    })
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
    return;
  }

  // SGFs — cache-first con fallback a network
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
          return new Response('SGF not found', { status: 404 });
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

// Mensaje desde el cliente
self.addEventListener('message', e => {
  if (e.data?.type === 'GET_CACHE_VERSION') {
    const port = e.ports?.[0];
    if (port) port.postMessage({ type: 'CACHE_VERSION', version: CACHE_VERSION });
    else e.source?.postMessage({ type: 'CACHE_VERSION', version: CACHE_VERSION });
    return;
  }

  if (e.data?.type === 'PRECACHE_SGFS') {
    const urls = e.data.urls || [];
    const BATCH = 20;
    caches.open(CACHE_VERSION).then(async cache => {
      let done = 0;
      for (let i = 0; i < urls.length; i += BATCH) {
        const batch = urls.slice(i, i + BATCH);
        await Promise.all(batch.map(async url => {
          const cached = await cache.match(url);
          if (!cached) {
            try {
              const response = await fetch(url);
              if (response.ok) cache.put(url, response.clone());
            } catch {}
          }
          done++;
        }));
        if (Math.floor(done / 100) > Math.floor((done - BATCH) / 100)) {
          e.source?.postMessage({ type: 'PRECACHE_PROGRESS', done, total: urls.length });
        }
      }
      e.source?.postMessage({ type: 'PRECACHE_DONE', total: urls.length });
    });
    return;
  }
});
