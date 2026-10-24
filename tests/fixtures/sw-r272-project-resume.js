const CACHE_NAME = 'ask-crump-new-body-v1-r272-project-resume-auth-boundary-1';

const CORE = [
  '/app',
  '/app.html',
  '/legal.html',
  '/delete-account.html',
  '/manifest.json',
  '/appearance-theme.js?v=5.9.76-appearance-choice-3',
  '/appearance-controls.css?v=5.9.76-appearance-choice-3',
  '/landing-5.6.css?v=5.9.76-accessibility-1',
  '/use-case.css?v=5.9.76',
  '/landing.js?v=5.9.76-free-guest-entry-1',
  '/styles.css',
  '/billing.css',
  '/install-prompt.css?v=5.9.76',
  '/onboarding.css?v=5.9.76-friendly-workspace-1',
  '/conversation.css?v=5.9.76-muse-release-repair-1',
  '/auth-styles.css?v=5.9.76-guest-free-contract-2',
  '/crump-v1-body.css?v=5.9.76-owned-workspace-access-1',
  '/credit-confirmation.css?v=5.9.76-credit-confirmation-1',
  '/lifecycle.css?v=5.9.76-lifecycle-activation-1',
  '/crump-design-pass.css?v=5.9.76-ui-release-audit-2',
  '/crump-activity-center-1.0.css?v=5.9.76-autonomous-continuity-1',
  '/crump-ui-guardrails.css?v=5.9.76-ui-guardrails-1',
  '/crump-motion-system.css?v=5.9.76-motion-system-2',
  '/crump-v1-body.js?v=5.9.76-atelier-workspace-1&workspaceRelease=guest-free-contract-2',
  '/crump-v1-stability.css',
  '/crump-v1-stability.js?v=5.9.76-intelligence-architecture-1',
  '/crump-navigation-5.2.5.css',
  '/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1',
  '/crump-navigation-5.9.30.css?v=5.9.76-nav-focus-visibility-1',
  '/crump-navigation-5.9.30.js?v=5.9.76-atelier-workspace-1',
  '/crump-vision-shell-1.0.css?v=5.9.76-atelier-workspace-1',
  '/crump-vision-shell-1.0.js?v=5.9.76-atelier-workspace-1',
  '/crump-vision-chats-1.0.css?v=5.9.76-atelier-workspace-1',
  '/crump-vision-chats-1.0.js?v=5.9.76-atelier-workspace-1',
  '/crump-vision-library-1.0.css?v=5.9.76-atelier-workspace-1',
  '/crump-vision-library-1.0.js?v=5.9.76-atelier-workspace-1',
  '/crump-vision-projects-1.0.css?v=5.9.76-project-resume-1',
  '/crump-vision-projects-1.0.js?v=5.9.76-project-resume-1',
  '/crump-vision-studios-1.0.css?v=5.9.76-atelier-workspace-1',
  '/crump-code-loader.js?v=5.9.76-autonomous-continuity-1&workspaceRelease=guest-free-contract-2',
  '/crump-product-loader.js?v=5.9.76-manuscript-export-delivery-1&workspaceRelease=guest-free-contract-2',
  '/crump-product-5.3.1.css',
  '/crump-product-5.3.1.js?v=5.9.76-conversation-action-labels-2',
  '/crump-polish-5.6.css',
  '/crump-polish-5.6.js?v=5.9.76-friendly-workspace-1',
  '/crump-media-save.js?v=5.9.76-library-crud-privacy-1',
  '/crump-library-loader.js?v=5.9.76-library-reconciliation-1',
  '/crump-subscriptions-5.3.2.js?v=5.9.76-checkout-destination-label-1',
  '/runtime-body-v1.js?v=5.9.76-auth-boundary-sync-1',
  '/home-document-entry.js?v=5.9.76-home-document-entry-1',
  '/native-runtime.js',
  '/mobile-bridge.js',
  '/safe-storage.js',
  '/install-prompt.js?v=5.9.76-update-work-guard-1',
  '/onboarding.js?v=5.9.76-friendly-workspace-1',
  '/scroll-manager.js?v=5.9.76-muse-release-repair-1',
  '/profile-manager.js',
  '/billing-manager.js?v=5.9.76-credit-entitlement-sync-1',
  '/subscription-ui.js?v=5.9.76-commerce-recovery-1',
  '/credit-confirmation.js?v=5.9.76-credit-confirmation-1',
  '/chat-resilience.js?v=5.9.76-credit-confirmation-1&workspaceRelease=guest-free-contract-2',
  '/ui-functions.js?v=5.9.76-response-continuity-cleanup-1',
  '/presence-manager.js?v=5.9.76-native-push-handoff-1',
  '/auth-resilience.js?v=5.9.76',
  '/device-auth.js?v=5.9.76-native-billing-identity-1',
  '/sync-manager.js?v=5.9.76-auth-boundary-sync-1',
  '/chat-sync.js?v=5.9.76-auth-boundary-sync-1',
  '/account-manager.js?v=5.9.76-account-storage-deletion-1',
  '/app.js?v=5.9.76-grounded-research-1&workspaceRelease=guest-free-contract-2',
  '/product-analytics.js?v=5.9.76-navigation-discovery-1',
  '/lifecycle-share.js?v=5.9.76-settings-invite-1',
  '/lifecycle-manager.js?v=5.9.76-lifecycle-idle-send-1',
  '/crump-activity-center-1.0.js?v=5.9.76-autonomous-continuity-1',
  '/auth-controller.js?v=5.9.76-guest-admission-1',
  '/crump-4.3.css',
  '/crump-4.3.js?v=5.9.76-atelier-workspace-1',
  '/crump-4.4.css?v=5.9.76-friendly-workspace-1',
  '/crump-4.4.js?v=5.9.76-friendly-workspace-1',
  '/crump-5.0.css?v=5.9.76-reference-fidelity-hard-contract-1',
  '/crump-5.0.js?v=5.9.76-precision-ai-persistence-1&workspaceRelease=guest-free-contract-2',
  '/crump-precision-image-edit-loader.js?v=5.9.76-precision-ai-persistence-1',
  '/crump-billing-5.1.css?v=5.9.76-credit-truth-1',
  '/crump-billing-5.1.js?v=5.9.76-checkout-destination-label-1&workspaceRelease=guest-free-contract-2',
  '/crump-5.2.css',
  '/crump-5.2.js?v=5.9.76-plan-status-line-1&workspaceRelease=guest-free-contract-2',
  '/crump-5.2.2.css?v=5.9.76-new-response-cue-1',
  '/crump-5.2.2.js?v=5.9.76-muse-release-repair-1&workspaceRelease=guest-free-contract-2',
  '/assets/brand/crump-shell-lockup-light.webp?v=5.9.76-shell-no-tagline-1',
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
    url.pathname === '/appearance-theme.js' ||
    url.pathname === '/appearance-controls.css' ||
    url.pathname === '/app.js' ||
    url.pathname === '/runtime-body-v1.js' ||
    url.pathname === '/home-document-entry.js' ||
    url.pathname === '/crump-v1-body.js' ||
    url.pathname === '/crump-v1-body.css' ||
    url.pathname === '/lifecycle.css' ||
    url.pathname === '/crump-activity-center-1.0.css' ||
    url.pathname === '/crump-activity-center-1.0.js' ||
    url.pathname === '/crump-ui-guardrails.css' ||
    url.pathname === '/crump-motion-system.css' ||
    url.pathname === '/crump-v1-stability.js' ||
    url.pathname === '/crump-v1-stability.css' ||
    url.pathname === '/crump-navigation-5.2.5.js' ||
    url.pathname === '/crump-navigation-5.2.5.css' ||
    url.pathname === '/crump-navigation-5.9.30.js' ||
    url.pathname === '/crump-navigation-5.9.30.css' ||
    url.pathname === '/crump-code-loader.js' ||
    url.pathname === '/crump-product-loader.js' ||
    url.pathname === '/crump-product-5.3.1.js' ||
    url.pathname === '/crump-subscriptions-5.3.2.js' ||
    url.pathname === '/crump-product-5.3.1.css' ||
    url.pathname === '/crump-polish-5.6.js' ||
    url.pathname === '/crump-polish-5.6.css' ||
    url.pathname === '/crump-media-save.js' ||
    url.pathname === '/crump-library-loader.js' ||
    url.pathname === '/conversation.css' ||
    url.pathname === '/credit-confirmation.css' ||
    url.pathname === '/credit-confirmation.js' ||
    url.pathname === '/chat-resilience.js' ||
    url.pathname === '/crump-5.0.js' ||
    url.pathname === '/crump-5.0.css' ||
    url.pathname === '/crump-precision-image-edit-loader.js' ||
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

function mustRevalidate(request, url) {
  return request.mode === 'navigate' ||
    url.pathname === '/app.html' ||
    url.pathname === '/app.js';
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (_) {
    return Response.error();
  }
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const requestUrl = new URL(request.url);
    const response = await fetch(request, requestUrl.pathname === '/app.js' ? { cache: 'no-store' } : undefined);
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

  event.respondWith(mustRevalidate(request, url)
    ? networkFirst(request)
    : bootCritical(request, url)
      ? cacheFirst(request)
      : staleWhileRevalidate(request));
});
