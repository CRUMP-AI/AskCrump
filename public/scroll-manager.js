// ==========================================
// CRUMP AI - SERVICE WORKER v2.0.0
// FOR /public/ DIRECTORY STRUCTURE
// ==========================================
const CACHE_NAME = 'crump-v2.0.0-pwa-ready';

const urlsToCache = [
    // Core HTML/JSON
    '/',
    '/index.html',
    '/manifest.json',
    
    // CSS files - /public/ directory
    '/public/styles.css',
    '/public/new-features.css',
    '/public/professional-tiers.css',
    '/public/assistant-character.css',
    '/public/pwa-styles.css',
    
    // JavaScript files - /public/ directory
    '/public/app.js',
    '/public/engines.js',
    '/public/autonomous.js',
    '/public/profile-manager.js',
    '/public/image-generation.js',
    '/public/ui-functions.js',
    '/public/developer-mode.js',
    '/public/scroll-manager.js',
    '/public/tutorial.js',
    '/public/self-debug-v3.js',
    '/public/pwa-manager.js',
    '/public/network-status.js',
    '/public/upgrade-ui.js',
    '/public/mobile-keyboard-handler.js',
    
    // Images - /public/assets/
    '/public/assets/logo-c.png',
    '/public/assets/assistant.png',
    '/public/assets/icon-192.png',
    '/public/assets/icon-512.png',
    '/public/assets/icon-1024.png'
];

// ==========================================
// INSTALL - Cache all files
// ==========================================
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker: Installing v2.0.0...');
    
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
    
    // Force immediate activation
    self.skipWaiting();
});

// ==========================================
// ACTIVATE - Clean up old caches
// ==========================================
self.addEventListener('activate', (event) => {
    console.log('🔧 Service Worker: Activating v2.0.0...');
    
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
        }).then(() => {
            console.log('✅ Service Worker: Cache cleanup complete');
        })
    );
    
    // Take control immediately
    return self.clients.claim();
});

// ==========================================
// MESSAGE HANDLER (for skip waiting)
// ==========================================
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        console.log('📱 Received SKIP_WAITING message');
        self.skipWaiting();
    }
});

// ==========================================
// FETCH - Network first, cache fallback
// ==========================================
self.addEventListener('fetch', (event) => {
    // Skip API calls - always fetch fresh
    if (event.request.url.includes('/api/')) {
        return;
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
        // Try network first (ensures latest version)
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

// ==========================================
// BACKGROUND SYNC (Optional - for offline features)
// ==========================================
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-messages') {
        console.log('🔄 Background sync triggered');
        // Could implement message queue sync here
    }
});

console.log('✅ Service Worker v2.0.0 loaded - Auto-updates enabled');
