// J.A.R.V.I.S. High-Tech Interface Service Worker
const CACHE_NAME = 'jarvis-hud-v2';
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[J.A.R.V.I.S. SW] Precaching app shell...');
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[J.A.R.V.I.S. SW] Precache warning:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Navegação: network-first com fallback para o shell cacheado (modo offline do PWA)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(event.request).then((cached) => cached || caches.match('/'))
      )
    );
    return;
  }

  // Network-only or Network-first for Realtime APIs, SSE and Audio TTS
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/events') ||
    url.pathname.startsWith('/tts') ||
    url.pathname.startsWith('/whisper') ||
    url.pathname.startsWith('/audio/') ||
    event.request.method !== 'GET'
  ) {
    event.respondWith(
      fetch(event.request).catch((err) => {
        return new Response(JSON.stringify({ error: 'offline', message: 'Offline fallback' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        });
      })
    );
    return;
  }

  // Cache-first, fall back to network for Shell & Assets
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Fetch in background to update cache (stale-while-revalidate)
        fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse));
          }
        }).catch(() => {});
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && event.request.method === 'GET') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      });
    })
  );
});

// Web Push: exibe notificações enviadas pelo servidor (VAPID)
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'J.A.R.V.I.S.', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'J.A.R.V.I.S.';
  const options = {
    body: data.body || '',
    tag: data.tag || 'jarvis',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: data.url || '/' }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// Clique na notificação: foca o HUD aberto ou abre um novo
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) return client.focus();
      }
      return self.clients.openWindow('/');
    })
  );
});

// Renovação da assinatura push quando o navegador a invalida
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    self.registration.pushManager.subscribe(event.oldSubscription ? event.oldSubscription.options : {})
      .then((subscription) => fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription)
      }))
  );
});
