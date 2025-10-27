// ==========================================
// CRUMP AI - SERVICE WORKER v1.0.2
// All files in /public/ directory
// ==========================================
const CACHE_NAME = 'crump-v1.0.2';

const urlsToCache = [
    // Core HTML/JSON
    '/',
    '/index.html',
    '/manifest.json',
    
    // CSS files - /public/
    '/public/styles.css',
    '/public/new-features.css',
    '/public/assistant-character.css',
    
    // JavaScript files - /public/
    '/public/app.js',
    '/public/engines.js',
    '/public/autonomous.js',
    '/public/profile-manager.js',
    '/public/image-generation.js',
    '/public/ui-functions.js',
    '/public/upgrade-ui.js',
    '/public/developer-mode.js',
    '/public/scroll-manager.js',
    '/public/tutorial.js',
    '/public/self-debug-v3.js',
    
    // Images - /assets/
    '/assets/logo-c.png',
    '/assets/icon-192.png',
    '/assets/icon-512.png',
    '/assets/icon-1024.png',
    '/assets/assistant.png'
];

// ==========================================
// INSTALL - Cache all files
// ==========================================
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker: Installing v1.0.2...');
    
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
    // Skip API calls - always fetch fresh
    if (event.request.url.includes('/api/')) {
        return;
    }
    
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    // Skip non-HTTP protocols (chrome-extension, etc)
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

console.log('✅ Service Worker v1.0.2 loaded');
