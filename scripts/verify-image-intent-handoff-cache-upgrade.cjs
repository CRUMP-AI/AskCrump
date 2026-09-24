const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const publicDirectory = path.join(root, 'public');
const oldCacheName = 'ask-crump-new-body-v1-r258';
const newCacheName = 'ask-crump-new-body-v1-r259';
const oldUrls = Object.freeze([
  '/landing.js?v=5.9.76-facebook-reel-attribution-1',
  '/crump-navigation-5.9.30.js?v=5.9.76-autonomous-crump-1',
  '/auth-controller.js?v=5.9.76-checkout-owner-reset-1',
]);
const newUrls = Object.freeze({
  landing: '/landing.js?v=5.9.76-image-intent-handoff-1',
  shell: '/app.html',
  runtime: '/runtime-body-v1.js?v=5.9.76-artifact-card-open-1',
  navigation: '/crump-navigation-5.9.30.js?v=5.9.76-image-intent-handoff-1',
  auth: '/auth-controller.js?v=5.9.76-image-intent-handoff-1',
  style: '/crump-5.0.css?v=5.9.76-exact-overlay-entry-1',
  composer: '/crump-5.0.js?v=5.9.76-artifact-card-open-1',
  loader: '/crump-precision-image-edit-loader.js?v=5.9.76-exact-overlay-entry-1',
  editorStyle: '/crump-precision-image-edit.css?v=5.9.76-exact-overlay-entry-1',
  editorScript: '/crump-precision-image-edit.js?v=5.9.76-exact-overlay-entry-1',
});
const fixturePath = '/__image-intent-handoff-cache-upgrade.html';
const oldWorkerPath = '/__image-intent-r258-sw.js';
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
});

function oldWorkerSource() {
  return [
    `const CACHE_NAME = ${JSON.stringify(oldCacheName)};`,
    `const URLS = ${JSON.stringify(oldUrls)};`,
    "self.addEventListener('install', event => {",
    '  event.waitUntil(caches.open(CACHE_NAME)',
    '    .then(cache => Promise.all(URLS.map(url => cache.put(',
    "      new Request(url), new Response('stale-r258:' + url, {headers: {'Content-Type': 'text/javascript'}}),",
    '    ))))',
    '    .then(() => self.skipWaiting()));',
    '});',
    "self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));",
  ].join('\n');
}

function safePublicPath(pathname) {
  const requested = pathname === '/app' ? '/app.html' : pathname;
  const relative = requested.replace(/^\/+/, '');
  const resolved = path.resolve(publicDirectory, relative);
  return resolved.startsWith(publicDirectory + path.sep) ? resolved : null;
}

async function startServer() {
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    response.setHeader('Cache-Control', 'no-store');
    if (url.pathname === fixturePath) {
      response.writeHead(200, {'Content-Type': contentTypes['.html']});
      response.end('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Image intent handoff cache upgrade</title></head><body>Image intent handoff cache upgrade</body></html>');
      return;
    }
    if (url.pathname === '/favicon.ico') {
      response.writeHead(204);
      response.end();
      return;
    }
    if (url.pathname === oldWorkerPath) {
      response.writeHead(200, {'Content-Type': contentTypes['.js'], 'Service-Worker-Allowed': '/'});
      response.end(oldWorkerSource());
      return;
    }
    const filePath = safePublicPath(url.pathname);
    if (!filePath) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, {
        'Content-Type': contentTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
        ...(url.pathname === '/sw.js' ? {'Service-Worker-Allowed': '/'} : {}),
      });
      response.end(body);
    } catch (_) {
      response.writeHead(404);
      response.end('Not found');
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return {server, port: server.address().port};
}

(async () => {
  const {server, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const context = await browser.newContext({serviceWorkers: 'allow'});
    const page = await context.newPage();
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}${fixturePath}`, {waitUntil: 'load'});

    await page.evaluate(async workerPath => {
      await navigator.serviceWorker.register(workerPath, {scope: '/'});
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true}));
      }
    }, oldWorkerPath);
    const seeded = await page.evaluate(async ({cacheName, urls}) => ({
      cachePresent: (await caches.keys()).includes(cacheName),
      entries: await Promise.all(urls.map(url => caches.match(url).then(Boolean))),
    }), {cacheName: oldCacheName, urls: oldUrls});
    assert.equal(seeded.cachePresent, true);
    assert.deepEqual(seeded.entries, oldUrls.map(() => true));

    await page.evaluate(() => navigator.serviceWorker.register('/sw.js', {scope: '/'}));
    const deadline = Date.now() + 30_000;
    let upgraded = false;
    while (Date.now() < deadline) {
      upgraded = await page.evaluate(async ({oldName, nextName}) => {
        const keys = await caches.keys();
        return keys.includes(nextName)
          && !keys.includes(oldName)
          && navigator.serviceWorker.controller?.scriptURL.endsWith('/sw.js');
      }, {oldName: oldCacheName, nextName: newCacheName});
      if (upgraded) break;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.equal(upgraded, true, 'r259 did not replace the frozen r258 cache');

    const result = await page.evaluate(async ({cacheName, previousUrls, urls}) => {
      const cache = await caches.open(cacheName);
      const read = async url => {
        const response = await cache.match(url);
        return response ? response.text() : '';
      };
      return {
        landingSource: await read(urls.landing),
        shellSource: await read(urls.shell),
        runtimeSource: await read(urls.runtime),
        navigationSource: await read(urls.navigation),
        authSource: await read(urls.auth),
        styleSource: await read(urls.style),
        composerSource: await read(urls.composer),
        loaderSource: await read(urls.loader),
        editorStylePrecached: Boolean(await cache.match(urls.editorStyle)),
        editorScriptPrecached: Boolean(await cache.match(urls.editorScript)),
        staleEntries: await Promise.all(previousUrls.map(url => caches.match(url).then(Boolean))),
      };
    }, {cacheName: newCacheName, previousUrls: oldUrls, urls: newUrls});

    assert.ok(result.landingSource.includes("'document', 'presentation', 'resume', 'video', 'image', 'projects'"));
    assert.ok(result.shellSource.includes(newUrls.auth));
    assert.ok(result.runtimeSource.includes(newUrls.navigation));
    assert.ok(result.runtimeSource.includes(newUrls.style));
    assert.ok(result.runtimeSource.includes(newUrls.composer));
    assert.ok(result.runtimeSource.includes(newUrls.loader));
    assert.ok(result.navigationSource.includes("new Set(['document', 'presentation', 'resume', 'image', 'video', 'projects'])"));
    assert.ok(result.navigationSource.includes('window.CrumpImageStudio.open();'));
    assert.ok(result.authSource.includes("'Create account & open Image Studio'"));
    assert.ok(result.authSource.includes("if (creationKind === 'image') discardPendingPlanIntent();"));
    assert.ok(result.authSource.includes('Number(event.detail?.capturedAt || 0) !== intent.capturedAt'));
    assert.ok(result.styleSource.includes('flex-wrap: wrap'));
    assert.ok(result.composerSource.includes('data-artifact-open'));
    assert.ok(result.composerSource.includes('openFile(message.artifact)'));
    assert.ok(result.loaderSource.includes(newUrls.editorStyle));
    assert.ok(result.loaderSource.includes(newUrls.editorScript));
    assert.equal(result.editorStylePrecached, false, 'Precision editor CSS must remain lazy-loaded');
    assert.equal(result.editorScriptPrecached, false, 'Precision editor JS must remain lazy-loaded');
    assert.deepEqual(result.staleEntries, oldUrls.map(() => false));
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      legacyCache: oldCacheName,
      activeCache: newCacheName,
      imageIntentHandoffDelivered: true,
      artifactCardTokenPreserved: true,
      exactOverlayTokenPreserved: true,
      precisionEditorRemainsLazy: true,
      errors,
    }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
