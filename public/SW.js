// ==========================================
// CRUMP AI - SERVICE WORKER v2.12.0
// PWA offline support and caching
// ==========================================

const CACHE_VERSION = 'crump-v2.12.0';
const CACHE_NAME = `crump-cache-${CACHE_VERSION}`;

// Assets to cache on install
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/styles.css',
    '/new-features.css',
    '/app.js',
    '/engines.js',
    '/profile-manager.js',
    '/image-generation.js',
    '/ui-functions.js',
    '/upgrade-ui.js',
    '/core-fixes.js',
    '/manifest.json',
    '/assets/icon-192.png',
    '/assets/icon-512.png'
];

// External CDN resources to cache
const CDN_ASSETS = [
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/themes/prism-tomorrow.css',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/prism.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-python.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-javascript.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-typescript.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-jsx.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-css.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-bash.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-json.min.js',
    'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-sql.min.js',
    'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css',
    'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js',
    'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js',
    'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js',
    'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js'
];

// ==========================================
// INSTALL EVENT - Cache static assets
// ==========================================
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker: Installing...');
    
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('📦 Service Worker: Caching static assets');
            
            // Cache static assets (allow some to fail)
            const staticPromises = STATIC_ASSETS.map(url => {
                return cache.add(url).catch(err => {
                    console.warn(`⚠️ Failed to cache ${url}:`, err.message);
                    return null;
                });
            });
            
            // Cache CDN assets (allow these to fail too, we'll fetch them later)
            const cdnPromises = CDN_ASSETS.map(url => {
                return cache.add(url).catch(err => {
                    console.warn(`⚠️ Failed to cache CDN ${url}:`, err.message);
                    return null;
                });
            });
            
            return Promise.all([...staticPromises, ...cdnPromises]);
        }).then(() => {
            console.log('✅ Service Worker: Installation complete');
            // Force the waiting service worker to become active
            return self.skipWaiting();
        }).catch(err => {
            console.error('❌ Service Worker: Installation failed', err);
        })
    );
});

// ==========================================
// ACTIVATE EVENT - Clean up old caches
// ==========================================
self.addEventListener('activate', (event) => {
    console.log('🚀 Service Worker: Activating...');
    
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('🗑️ Service Worker: Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            console.log('✅ Service Worker: Activation complete');
            // Take control of all pages immediately
            return self.clients.claim();
        })
    );
});

// ==========================================
// FETCH EVENT - Serve from cache or network
// ==========================================
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Skip cross-origin requests that aren't CDN assets
    if (url.origin !== location.origin && !isCDNAsset(url.href)) {
        return;
    }
    
    // Handle API requests differently (network-first)
    if (url.pathname.includes('/api/') || url.pathname.includes('/chat')) {
        event.respondWith(networkFirst(event.request));
        return;
    }
    
    // Handle image generation (always network, never cache)
    if (url.hostname === 'image.pollinations.ai') {
        event.respondWith(fetch(event.request));
        return;
    }
    
    // Handle everything else (cache-first with network fallback)
    event.respondWith(cacheFirst(event.request));
});

// ==========================================
// CACHE STRATEGIES
// ==========================================

// Cache-first strategy (for static assets)
async function cacheFirst(request) {
    try {
        const cachedResponse = await caches.match(request);
        
        if (cachedResponse) {
            // Update cache in background
            updateCacheInBackground(request);
            return cachedResponse;
        }
        
        // Not in cache, fetch from network
        const networkResponse = await fetch(request);
        
        // Cache the new response
        if (networkResponse && networkResponse.status === 200) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
        
    } catch (error) {
        console.error('❌ Fetch failed:', error);
        
        // Try to return cached version as last resort
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline page or error
        return new Response('Offline - Content not available', {
            status: 503,
            statusText: 'Service Unavailable',
            headers: new Headers({
                'Content-Type': 'text/plain'
            })
        });
    }
}

// Network-first strategy (for API calls)
async function networkFirst(request) {
    try {
        const networkResponse = await fetch(request);
        
        // Optionally cache successful API responses
        if (networkResponse && networkResponse.status === 200) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
        
    } catch (error) {
        console.error('❌ Network request failed, trying cache:', error);
        
        // Fallback to cache
        const cachedResponse = await caches.match(request);
        
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // No cache available
        return new Response(JSON.stringify({
            error: 'Offline',
            message: 'No network connection and no cached data available'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Update cache in background without blocking response
function updateCacheInBackground(request) {
    fetch(request).then(response => {
        if (response && response.status === 200) {
            caches.open(CACHE_NAME).then(cache => {
                cache.put(request, response);
            });
        }
    }).catch(() => {
        // Silently fail
    });
}

// Check if URL is a CDN asset we cache
function isCDNAsset(url) {
    return CDN_ASSETS.some(asset => url.includes(asset) || asset.includes(url));
}

// ==========================================
// MESSAGE HANDLER - For skip waiting
// ==========================================
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        console.log('⏩ Service Worker: Skip waiting requested');
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CLEAR_CACHE') {
        console.log('🗑️ Service Worker: Clearing cache');
        event.waitUntil(
            caches.delete(CACHE_NAME).then(() => {
                console.log('✅ Cache cleared');
            })
        );
    }
});

// ==========================================
// BACKGROUND SYNC (if needed later)
// ==========================================
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-messages') {
        console.log('🔄 Service Worker: Background sync triggered');
        event.waitUntil(syncMessages());
    }
});

async function syncMessages() {
    // Placeholder for future background sync functionality
    console.log('📬 Syncing messages...');
}

// ==========================================
// PUSH NOTIFICATIONS (if needed later)
// ==========================================
self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'Crump AI';
    const options = {
        body: data.body || 'New notification',
        icon: '/assets/icon-192.png',
        badge: '/assets/icon-192.png',
        vibrate: [200, 100, 200],
        data: data
    };
    
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.openWindow('/')
    );
});

console.log('✅ Service Worker script loaded successfully');
