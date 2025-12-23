// ==========================================
// CRUMP AI - SERVICE WORKER v1.0.3
// Files served from ROOT directory
// ==========================================
const CACHE_NAME = 'crump-v1.0.5-consciousness';

const urlsToCache = [
    // Core HTML/JSON
    '/',
    '/index.html',
    '/manifest.json',
    
    // CSS files - ROOT directory
    '/styles.css',
    '/new-features.css',
    
    // JavaScript files - ROOT directory (confirmed from network tab)
    '/app.js',
    '/chat-sync.js',
    '/engines.js',
    '/autonomous.js',
    '/profile-manager.js',
    '/image-generation.js',
    '/ui-functions.js',
    '/developer-mode.js',
    '/scroll-manager.js',
    '/tutorial.js',
    '/self-debug-v3.js',
    '/consciousness-engine.js',
    '/consciousness-integration.js',
    
    // Images - /assets/
    '/assets/logo-c.png',
    '/assets/assistant.png',
    '/assets/icon-192.png',
    '/assets/icon-512.png'
];

// ==========================================
// INSTALL - Cache all files
// ==========================================
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker: Installing v1.0.3...');
    
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('✅ Service Worker: Cache opened');
                
                // Cache files individually for better error reporting
                return Promise.allSettled(
                    urlsToCache.map(url => 
                        cache.add(url)
                            .then(() => console.log('✅ Cached:', url))
                            .catch(err => console.warn('⚠️ Failed to cache:', url, err.message))
                    )
                );
            })
            .then((results) => {
                const succeeded = results.filter(r => r.status === 'fulfilled').length;
                const failed = results.filter(r => r.status === 'rejected').length;
                console.log(`✅ Service Worker: Cached ${succeeded}/${urlsToCache.length} files (${failed} failed)`);
            })
            .catch((err) => {
                console.error('❌ Service Worker: Cache failed', err);
            })
    );
    
    self.skipWaiting();
});

// ==========================================
// ACTIVATE - Clean up old caches
// ==========================================
self.addEventListener('activate', (event) => {
    console.log('🔧 Service Worker: Activating...');
    
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
    console.log('✅ Service Worker: Active and ready');
});

// ==========================================
// FETCH - Network first, cache fallback
// ==========================================
self.addEventListener('fetch', (event) => {
   // Skip API calls and auth-related requests - always fetch fresh
if (event.request.url.includes('/api/') || 
    event.request.url.includes('/auth') ||
    event.request.url.includes('refresh') ||
    event.request.url.includes('login') ||
    event.request.url.includes('manifest.json') ||
    event.request.url.includes('check-session')) {
    // Let browser handle these normally (with cookies)
    return fetch(event.request);
}
    
    // Skip external CDN resources
    if (event.request.url.includes('googleapis.com') ||
        event.request.url.includes('cdnjs.cloudflare.com') ||
        event.request.url.includes('jsdelivr.net') ||
        event.request.url.includes('stripe.com') ||
        event.request.url.includes('stripe.network') ||
        event.request.url.includes('gstatic.com')) {
        return;
    }
    
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    // Skip non-HTTP protocols
    if (!event.request.url.startsWith('http')) {
        return;
    }
    
    event.respondWith(
        // Try network first
        fetch(event.request)
            .then((response) => {
                // Only cache successful responses
                if (!response || response.status !== 200 || response.type === 'error') {
                    return response;
                }
                
                // Clone for cache
                const responseClone = response.clone();
                
                // Update cache in background
                caches.open(CACHE_NAME)
                    .then((cache) => {
                        cache.put(event.request, responseClone);
                    })
                    .catch(err => {
                        console.warn('⚠️ Cache write failed:', err.message);
                    });
                
                return response;
            })
            .catch(() => {
                // Network failed, try cache
                return caches.match(event.request)
                    .then(cachedResponse => {
                        if (cachedResponse) {
                            console.log('📦 Serving from cache:', event.request.url);
                            return cachedResponse;
                        }
                        
                        // No cache available
                        return new Response('Offline - content not cached', {
                            status: 503,
                            statusText: 'Service Unavailable',
                            headers: { 'Content-Type': 'text/plain' }
                        });
                    });
            })
    );
});

console.log('✅ Service Worker v1.0.3 loaded');
