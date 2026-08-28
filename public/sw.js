const CACHE_NAME = 'ask-crump-new-body-v1-r101';

const CORE = [
  '/app',
  '/app.html',
  '/legal.html',
  '/delete-account.html',
  '/manifest.json',
  '/landing-5.6.css?v=5.9.67',
  '/use-case.css?v=5.9.67',
  '/landing.js?v=5.9.67',
  '/styles.css',
  '/billing.css',
  '/install-prompt.css?v=5.9.67',
  '/onboarding.css',
  '/conversation.css?v=5.9.67',
  '/auth-styles.css',
  '/crump-v1-body.css?v=5.9.67',
  '/crump-v1-body.js',
  '/crump-v1-stability.css',
  '/crump-v1-stability.js',
  '/crump-navigation-5.2.5.css',
  '/crump-navigation-5.2.5.js',
  '/crump-navigation-5.9.30.css',
  '/crump-navigation-5.9.30.js',
  '/crump-code-5.9.35.css',
  '/crump-code-5.9.35.js',
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
  '/install-prompt.js?v=5.9.67',
  '/onboarding.js',
  '/scroll-manager.js',
  '/profile-manager.js',
  '/billing-manager.js',
  '/subscription-ui.js',
  '/chat-resilience.js?v=5.9.67',
  '/ui-functions.js?v=5.9.67',
  '/presence-manager.js?v=5.9.67',
  '/auth-resilience.js?v=5.9.67',
  '/device-auth.js?v=5.9.67',
  '/sync-manager.js?v=5.9.67',
  '/chat-sync.js?v=5.9.67',
  '/account-manager.js',
  '/app.js?v=5.9.67',
  '/product-analytics.js?v=5.9.67',
  '/auth-controller.js?v=5.9.67',
  '/crump-4.3.css',
  '/crump-4.3.js?v=5.9.67',
  '/crump-4.4.css',
  '/crump-4.4.js',
  '/crump-5.0.css',
  '/crump-5.0.js?v=5.9.67',
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
    url.pathname === '/crump-navigation-5.9.30.js' ||
    url.pathname === '/crump-navigation-5.9.30.css' ||
    url.pathname === '/crump-code-5.9.35.js' ||
    url.pathname === '/crump-code-5.9.35.css' ||
    url.pathname === '/crump-product-5.3.js' ||
    url.pathname === '/crump-product-5.3.css' ||
    url.pathname === '/crump-product-5.3.1.js' ||
    url.pathname === '/crump-subscriptions-5.3.2.js' ||
    url.pathname === '/crump-product-5.3.1.css' ||
    url.pathname === '/crump-polish-5.6.js' ||
    url.pathname === '/crump-polish-5.6.css' ||
    url.pathname === '/crump-library-5.7.js' ||
    url.pathname === '/crump-library-5.7.css' ||
    url.pathname === '/conversation.css' ||
    url.pathname === '/chat-resilience.js' ||
    url.pathname === '/crump-5.0.js' ||
    url.pathname === '/ui-functions.js' ||
    url.pathname === '/auth-resilience.js' ||
    url.pathname === '/install-prompt.js' ||
    url.pathname === '/install-prompt.css' ||
    url.pathname === '/device-auth.js' ||
    url.pathname === '/sync-manager.js' ||
    url.pathname === '/onboarding.js' ||
    url.pathname === '/product-analytics.js' ||
    url.pathname === '/auth-controller.js' ||
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
