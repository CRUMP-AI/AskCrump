// Crump AI Service Worker v1.0
const CACHE_NAME = 'crump-v1.0.1'; // Bump version to force cache update
const urlsToCache = [
    '/',
    '/index.html',
    '/styles.css',
    '/new-features.css',          // ADDED
    '/assistant-character.css',   // ADDED (might as well include it)
    '/app.js',
    '/engines.js',
    '/autonomous.js',
    '/profile-manager.js',
    '/image-generation.js',
    '/ui-functions.js',
    '/upgrade-ui.js',             // ADDED
    '/developer-mode.js',
    '/scroll-manager.js',
    '/tutorial.js',
    '/self-debug-v3.js',          // ADDED
    '/manifest.json',
    '/assets/logo-c.png',
    '/assets/icon-192.png',
    '/assets/icon-512.png',
    '/assets/icon-1024.png',      // ADDED
    '/assets/assistant.png'
];
// Install event
self.addEventListener('install', (event) => {
event.waitUntil(
caches.open(CACHE_NAME)
.then((cache) => {
console.log('✅ Service Worker: Cache opened');
return cache.addAll(urlsToCache);
})
.catch((err) => {
console.error('❌ Service Worker: Cache failed', err);
})
);
self.skipWaiting();
});
// Activate event
self.addEventListener('activate', (event) => {
event.waitUntil(
caches.keys().then((cacheNames) => {
return Promise.all(
cacheNames.map((cacheName) => {
if (cacheName !== CACHE_NAME) {
console.log('🗑️ Service Worker: Deleting old cache', cacheName);
return caches.delete(cacheName);
}
})
);
})
);
self.clients.claim();
});
// Fetch event - Network first, fallback to cache
self.addEventListener('fetch', (event) => {
    // Skip API calls - let them go directly to network
    if (event.request.url.includes('/api/')) {
        return; // Don't call respondWith for API requests
    }
    
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    event.respondWith(
        fetch(event.request)
        .then((response) => {
            // Only cache successful responses
            if (!response || response.status !== 200 || response.type === 'error') {
                return response;
            }
            
            // Clone response for cache
            const responseClone = response.clone();
            
            // Update cache in background
            caches.open(CACHE_NAME).then((cache) => {
                cache.put(event.request, responseClone);
            }).catch(err => {
                console.warn('Cache write failed:', err);
            });
            
            return response;
        })
        .catch(() => {
            // Network failed, try cache
            return caches.match(event.request).then(cachedResponse => {
                if (cachedResponse) {
                    console.log('📦 Serving from cache:', event.request.url);
                    return cachedResponse;
                }
                // No cache, return offline page or basic error
                return new Response('Offline - content not cached', {
                    status: 503,
                    statusText: 'Service Unavailable'
                });
            });
        })
    );
});
