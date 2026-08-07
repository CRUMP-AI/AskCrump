const CACHE_NAME = 'ask-crump-shell-v5.0.0';
const APP_SHELL = [
  '/app', '/app.html', '/legal.html', '/delete-account.html', '/manifest.json',
  '/styles.css', '/auth-styles.css', '/onboarding.css',
  '/install-prompt.css', '/billing.css', '/conversation.css', '/crump-4.3.css', '/crump-4.4.css', '/crump-5.0.css',
  '/runtime-config.js', '/native-runtime.js', '/mobile-bridge.js', '/safe-storage.js',
  '/install-prompt.js', '/onboarding.js', '/crump-4.3.js', '/crump-4.4.js', '/crump-5.0.js', '/scroll-manager.js',
  '/profile-manager.js', '/billing-manager.js', '/subscription-ui.js', '/ui-functions.js', '/presence-manager.js',
  '/device-auth.js', '/sync-manager.js', '/chat-sync.js', '/account-manager.js',
  '/app.js', '/auth-controller.js', '/landing.js',
  '/assets/logo-c.png', '/assets/ask-crump-logo.png', '/assets/icon-192.png', '/assets/icon-512.png', '/assets/icon-1024.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
      return response;
    }).catch(async () => (await caches.match(request)) || (await caches.match('/app.html'))));
    return;
  }
  event.respondWith(caches.match(request).then(cached => {
    const network = fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => undefined);
      }
      return response;
    }).catch(() => cached);
    return cached || network;
  }));
});
