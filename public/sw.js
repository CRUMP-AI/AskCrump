const CACHE_NAME = 'ask-crump-new-body-v1-r36';

const CORE = [
  '/app',
  '/app.html',
  '/legal.html',
  '/delete-account.html',
  '/manifest.json',
  '/landing-5.6.css',
  '/styles.css',
  '/billing.css',
  '/install-prompt.css',
  '/onboarding.css',
  '/conversation.css',
  '/auth-styles.css',
  '/crump-v1-body.css',
  '/crump-v1-body.js',
  '/crump-v1-stability.css',
  '/crump-v1-stability.js',
  '/crump-navigation-5.2.5.css',
  '/crump-navigation-5.2.5.js',
  '/crump-product-5.3.css',
  '/crump-product-5.3.js',
  '/crump-product-5.3.1.css',
  '/crump-product-5.3.1.js',
  '/crump-polish-5.6.css',
  '/crump-polish-5.6.js',
  '/crump-library-5.7.css',
  '/crump-library-5.7.js',
  '/crump-subscriptions-5.3.2.js',
  '/runtime-body-v1.js',
  '/native-runtime.js',
  '/mobile-bridge.js',
  '/safe-storage.js',
  '/install-prompt.js',
  '/onboarding.js',
  '/scroll-manager.js',
  '/profile-manager.js',
  '/billing-manager.js',
  '/subscription-ui.js',
  '/ui-functions.js',
  '/presence-manager.js',
  '/device-auth.js',
  '/sync-manager.js',
  '/chat-sync.js',
  '/account-manager.js',
  '/app.js',
  '/product-analytics.js',
  '/auth-controller.js',
  '/crump-4.3.css',
  '/crump-4.3.js',
  '/crump-4.4.css',
  '/crump-4.4.js',
  '/crump-5.0.css',
  '/crump-5.0.js',
  '/crump-billing-5.1.css',
  '/crump-billing-5.1.js',
  '/crump-5.2.css',
  '/crump-5.2.js',
  '/crump-5.2.2.css',
  '/crump-5.2.2.js',
  '/assets/brand/crump-mark.png',
  '/assets/brand/crump-horizontal-light.png',
  '/assets/brand/crump-horizontal-dark.png',
  '/assets/ask-crump-app-icon-v2-180.png',
  '/assets/ask-crump-app-icon-v2-192.png',
  '/assets/ask-crump-app-icon-v2-512.png',
  '/assets/ask-crump-app-icon-v2-1024.png',
];

async function preCache() {
  const cache = await caches.open(CACHE_NAME);
  await Promise.allSettled(
    CORE.map(async url => {
      const request = new Request(url, {cache: 'reload'});
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response);
    })
  );
}

self.addEventListener('install', event => {
  event.waitUntil(preCache().then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key !== CACHE_NAME && key.startsWith('ask-crump'))
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

function bootCritical(request, url) {
  return request.mode === 'navigate' ||
    url.pathname === '/app.html' ||
    url.pathname === '/runtime-body-v1.js' ||
    url.pathname === '/crump-v1-body.js' ||
    url.pathname === '/crump-v1-body.css' ||
    url.pathname === '/crump-v1-stability.js' ||
    url.pathname === '/crump-v1-stability.css' ||
    url.pathname === '/crump-navigation-5.2.5.js' ||
    url.pathname === '/crump-navigation-5.2.5.css' ||
    url.pathname === '/crump-product-5.3.js' ||
    url.pathname === '/crump-product-5.3.css' ||
    url.pathname === '/crump-product-5.3.1.js' ||
    url.pathname === '/crump-subscriptions-5.3.2.js' ||
    url.pathname === '/crump-product-5.3.1.css' ||
    url.pathname === '/crump-polish-5.6.js' ||
    url.pathname === '/crump-polish-5.6.css' ||
    url.pathname === '/crump-library-5.7.js' ||
    url.pathname === '/crump-library-5.7.css' ||
    url.pathname === '/onboarding.js' ||
    url.pathname === '/product-analytics.js' ||
    url.pathname === '/crump-4.3.js';
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (_) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (request.mode === 'navigate') {
      return (await cache.match('/app.html')) || Response.error();
    }
    return Response.error();
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then(async response => {
      if (response.ok) await cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  if (cached) {
    void network;
    return cached;
  }
  return (await network) || Response.error();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(bootCritical(request, url)
    ? networkFirst(request)
    : staleWhileRevalidate(request));
});
