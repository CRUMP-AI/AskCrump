const CACHE_NAME = 'ask-crump-new-body-v1-r170';

const CORE = [
  '/app',
  '/app.html',
  '/legal.html',
  '/delete-account.html',
  '/manifest.json',
  '/landing-5.6.css?v=5.9.76-truthful-destinations-1',
  '/use-case.css?v=5.9.76',
  '/landing.js?v=5.9.76-marketing-landing-1',
  '/styles.css',
  '/billing.css',
  '/install-prompt.css?v=5.9.76',
  '/onboarding.css?v=5.9.76-video-destination-1',
  '/conversation.css?v=5.9.76-intelligence-receipt-1',
  '/auth-styles.css',
  '/crump-v1-body.css?v=5.9.76-intelligence-architecture-1',
  '/lifecycle.css?v=5.9.76-lifecycle-activation-1',
  '/crump-v1-body.js?v=5.9.76-desktop-chats-default-1',
  '/crump-v1-stability.css',
  '/crump-v1-stability.js?v=5.9.76-intelligence-architecture-1',
  '/crump-navigation-5.2.5.css',
  '/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1',
  '/crump-navigation-5.9.30.css?v=5.9.76-video-destination-1',
  '/crump-navigation-5.9.30.js?v=5.9.76-video-destination-1',
  '/crump-code-5.9.35.css?v=5.9.76-intelligence-architecture-1',
  '/crump-code-5.9.35.js?v=5.9.76-intelligence-architecture-1',
  '/crump-product-5.3.css?v=5.9.76-visual-media-reliability-1',
  '/crump-product-5.3.js?v=5.9.76-visual-media-reliability-1',
  '/crump-product-5.3.1.css',
  '/crump-product-5.3.1.js?v=5.9.76-core-reliability-1',
  '/crump-polish-5.6.css',
  '/crump-polish-5.6.js?v=5.9.76-video-destination-1',
  '/crump-library-5.7.css',
  '/crump-library-5.7.js?v=5.9.76-demand-hydration-1',
  '/crump-subscriptions-5.3.2.js?v=5.9.76-intelligence-plan-handoff-1',
  '/runtime-body-v1.js?v=5.9.76-video-destination-1',
  '/native-runtime.js',
  '/mobile-bridge.js',
  '/safe-storage.js',
  '/install-prompt.js?v=5.9.76',
  '/onboarding.js?v=5.9.76-video-destination-1',
  '/scroll-manager.js',
  '/profile-manager.js',
  '/billing-manager.js',
  '/subscription-ui.js?v=5.9.76-truthful-plan-1',
  '/chat-resilience.js?v=5.9.76-image-safety-recovery-1',
  '/ui-functions.js?v=5.9.76-image-scroll-stability-1',
  '/presence-manager.js?v=5.9.76',
  '/auth-resilience.js?v=5.9.76',
  '/device-auth.js?v=5.9.76',
  '/sync-manager.js?v=5.9.76',
  '/chat-sync.js?v=5.9.76-sync-cadence-1',
  '/account-manager.js',
  '/app.js?v=5.9.76-core-reliability-1',
  '/product-analytics.js?v=5.9.76',
  '/lifecycle-share.js?v=5.9.76-lifecycle-activation-1',
  '/lifecycle-manager.js?v=5.9.76-lifecycle-activation-1',
  '/auth-controller.js?v=5.9.76-weekly-growth-attribution-1',
  '/crump-4.3.css',
  '/crump-4.3.js?v=5.9.76-intelligence-architecture-1',
  '/crump-4.4.css',
  '/crump-4.4.js?v=5.9.76-core-reliability-1',
  '/crump-5.0.css',
  '/crump-5.0.js?v=5.9.76-image-scroll-stability-1',
  '/crump-billing-5.1.css?v=5.9.76-contextual-plan-recovery-1',
  '/crump-billing-5.1.js?v=5.9.76-weekly-growth-attribution-1',
  '/crump-5.2.css',
  '/crump-5.2.js?v=5.9.76-weekly-growth-attribution-1',
  '/crump-5.2.2.css',
  '/crump-5.2.2.js?v=5.9.76-image-scroll-stability-1',
  '/assets/brand/crump-shell-lockup-light.png',
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
    url.pathname === '/lifecycle.css' ||
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
    url.pathname === '/lifecycle-share.js' ||
    url.pathname === '/lifecycle-manager.js' ||
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
