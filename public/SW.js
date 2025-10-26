// Crump AI Service Worker v1.0
const CACHE_NAME = 'crump-v1.0.0';
const urlsToCache = [
'/',
'/index.html',
'/styles.css',
'/app.js',
'/engines.js',
'/autonomous.js',
'/profile-manager.js',
'/image-generation.js',
'/ui-functions.js',
'/developer-mode.js',
'/scroll-manager.js',
'/tutorial.js',
'/manifest.json',
'/assets/logo-c.png',
'/assets/icon-192.png',
'/assets/icon-512.png',
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
// Skip API calls from cache
if (event.request.url.includes('/api/')) {
return fetch(event.request);
}
event.respondWith(
fetch(event.request)
.then((response) => {
// Clone response for cache
const responseClone = response.clone();
    // Update cache in background
    caches.open(CACHE_NAME).then((cache) => {
      cache.put(event.request, responseClone);
    });
    
    return response;
  })
  .catch(() => {
    // Network failed, try cache
    return caches.match(event.request);
  })
);
});
