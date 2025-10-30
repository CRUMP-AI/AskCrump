// ==========================================
// CRUMP AI - ENHANCED SERVICE WORKER v2.0
// Claude-level caching and offline support
// ==========================================

const CACHE_VERSION = 'crump-v2.0.0';
const CACHE_STATIC = `${CACHE_VERSION}-static`;
const CACHE_DYNAMIC = `${CACHE_VERSION}-dynamic`;
const CACHE_IMAGES = `${CACHE_VERSION}-images`;

// Static assets that rarely change
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/manifest.json',
    '/styles.css',
    '/new-features.css',
    '/professional-tiers.css',
    '/assistant-character.css',
    '/pwa-installer.css',
    '/app.js',
    '/engines.js',
    '/autonomous.js',
    '/profile-manager.js',
    '/image-generation.js',
    '/ui-functions.js',
    '/developer-mode.js',
    '/scroll-manager.js',
    '/tutorial.js',
    '/self-debug-v3.js',
    '/upgrade-ui.js',
    '/pwa-installer.js',
    '/mobile-keyboard-handler.js'
];

// Image assets
const IMAGE_ASSETS = [
    '/assets/logo-c.png',
    '/assets/assistant.png',
    '/assets/icon-192.png',
    '/assets/icon-512.png',
    '/assets/icon-1024.png'
];

// Maximum cache sizes
const MAX_DYNAMIC_CACHE = 50;
const MAX_IMAGE_CACHE = 100;

// ==========================================
// INSTALL - Cache static assets
// ==========================================
self.addEventListener('install', (event) => {
    console.log('ðŸ”§ Service Worker v2.0: Installing...');
    
    event.waitUntil(
        Promise.all([
            // Cache static assets
            caches.open(CACHE_STATIC).then(cache => {
                console.log('ðŸ“¦ Caching static assets...');
                return Promise.allSettled(
                    STATIC_ASSETS.map(url =>
                        cache.add(url)
                            .then(() => console.log('âœ… Cached:', url))
                            .catch(err => console.warn('âš ï¸ Failed:', url))
                    )
                );
            }),
            // Cache images
            caches.open(CACHE_IMAGES).then(cache => {
                console.log('ðŸ–¼ï¸ Caching images...');
                return Promise.allSettled(
                    IMAGE_ASSETS.map(url =>
                        cache.add(url)
                            .then(() => console.log('âœ… Cached:', url))
                            .catch(err => console.warn('âš ï¸ Failed:', url))
                    )
                );
            })
        ]).then(() => {
            console.log('âœ… Service Worker: Installation complete');
            self.skipWaiting();
        })
    );
});

// ==========================================
// ACTIVATE - Clean up old caches
// ==========================================
self.addEventListener('activate', (event) => {
    console.log('ðŸ”§ Service Worker v2.0: Activating...');
    
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (!cacheName.startsWith(CACHE_VERSION)) {
                        console.log('ðŸ—‘ï¸ Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            console.log('âœ… Service Worker: Active and claiming clients');
            return self.clients.claim();
        })
    );
});

// ==========================================
// FETCH - Smart caching strategies
// ==========================================
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') return;
    
    // Skip cross-origin requests (except CDN resources we control)
    if (url.origin !== location.origin && !isTrustedCDN(url)) {
        return;
    }
    
    // Skip API calls - always fetch fresh
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(request).catch(() => {
                return new Response(
                    JSON.stringify({ error: 'Offline - API unavailable' }),
                    { 
                        status: 503,
                        headers: { 'Content-Type': 'application/json' }
                    }
                );
            })
        );
        return;
    }
    
    // Different strategies for different asset types
    if (isStaticAsset(url.pathname)) {
        event.respondWith(cacheFirst(request, CACHE_STATIC));
    } else if (isImageAsset(url.pathname)) {
        event.respondWith(cacheFirst(request, CACHE_IMAGES));
    } else if (isHTMLPage(url.pathname)) {
        event.respondWith(networkFirst(request, CACHE_DYNAMIC));
    } else {
        event.respondWith(staleWhileRevalidate(request, CACHE_DYNAMIC));
    }
});

// ==========================================
// CACHING STRATEGIES
// ==========================================

// Cache First - For static assets that rarely change
async function cacheFirst(request, cacheName) {
    const cached = await caches.match(request);
    if (cached) {
        return cached;
    }
    
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        console.error('Fetch failed:', error);
        return new Response('Offline', { status: 503 });
    }
}

// Network First - For HTML pages that change frequently
async function networkFirst(request, cacheName) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
            trimCache(cacheName, MAX_DYNAMIC_CACHE);
        }
        return response;
    } catch (error) {
        const cached = await caches.match(request);
        if (cached) {
            return cached;
        }
        return new Response('Offline - Page not cached', { status: 503 });
    }
}

// Stale While Revalidate - For dynamic content
async function staleWhileRevalidate(request, cacheName) {
    const cached = await caches.match(request);
    
    const fetchPromise = fetch(request).then(response => {
        if (response.ok) {
            const cache = caches.open(cacheName);
            cache.then(c => c.put(request, response.clone()));
            trimCache(cacheName, MAX_DYNAMIC_CACHE);
        }
        return response;
    }).catch(() => cached);
    
    return cached || fetchPromise;
}

// ==========================================
// HELPER FUNCTIONS
// ==========================================

function isStaticAsset(pathname) {
    return /\.(js|css|woff2?|ttf|otf)$/.test(pathname);
}

function isImageAsset(pathname) {
    return /\.(png|jpg|jpeg|gif|webp|svg|ico)$/.test(pathname);
}

function isHTMLPage(pathname) {
    return pathname === '/' || /\.html$/.test(pathname);
}

function isTrustedCDN(url) {
    const trustedDomains = [
        'fonts.googleapis.com',
        'fonts.gstatic.com',
        'cdnjs.cloudflare.com',
        'cdn.jsdelivr.net'
    ];
    return trustedDomains.some(domain => url.hostname.includes(domain));
}

async function trimCache(cacheName, maxItems) {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    
    if (keys.length > maxItems) {
        const toDelete = keys.slice(0, keys.length - maxItems);
        await Promise.all(toDelete.map(key => cache.delete(key)));
        console.log(`ðŸ—‘ï¸ Trimmed ${toDelete.length} items from ${cacheName}`);
    }
}

// ==========================================
// BACKGROUND SYNC (Future Enhancement)
// ==========================================
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-messages') {
        event.waitUntil(syncMessages());
    }
});

async function syncMessages() {
    // Future: Sync pending messages when back online
    console.log('ðŸ”„ Syncing messages...');
}

// ==========================================
// PUSH NOTIFICATIONS (Future Enhancement)
// ==========================================
self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    
    const options = {
        body: data.body || 'New message from Crump',
        icon: '/assets/icon-192.png',
        badge: '/assets/icon-192.png',
        vibrate: [200, 100, 200],
        data: {
            url: data.url || '/'
        }
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title || 'Crump AI', options)
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});

// ==========================================
// MESSAGE HANDLER
// ==========================================
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CACHE_URLS') {
        const urls = event.data.urls || [];
        event.waitUntil(
            caches.open(CACHE_DYNAMIC).then(cache => {
                return cache.addAll(urls);
            })
        );
    }
});

console.log('âœ… Service Worker v2.0 loaded - Enhanced caching ready');
