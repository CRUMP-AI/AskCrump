const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const publicDirectory = path.join(root, 'public');
const oldCacheName = 'ask-crump-new-body-v1-r255';
const newCacheName = 'ask-crump-new-body-v1-r256';
const oldRuntimeUrl = '/runtime-body-v1.js?v=5.9.76-reference-fidelity-1';
const newRuntimeUrl = '/runtime-body-v1.js?v=5.9.76-reference-review-persistence-1';
const oldComposerUrl = '/crump-5.0.js?v=5.9.76-reference-fidelity-1';
const newComposerUrl = '/crump-5.0.js?v=5.9.76-reference-review-persistence-1';
const oldProductLoaderUrl = '/crump-product-loader.js?v=5.9.76-reference-fidelity-1';
const newProductLoaderUrl = '/crump-product-loader.js?v=5.9.76-reference-review-persistence-1';
const oldProductUrl = '/crump-product-5.3.js?v=5.9.76-reference-fidelity-1';
const newProductUrl = '/crump-product-5.3.js?v=5.9.76-reference-review-persistence-1';
const newProductStyleUrl = '/crump-product-5.3.css?v=5.9.76-reference-review-persistence-1';
const oldAppUrl = '/app.js?v=5.9.76-server-authoritative-activation-1';
const newAppUrl = '/app.js?v=5.9.76-reference-review-persistence-1';
const fixturePath = '/__reference-fidelity-cache-upgrade.html';
const oldWorkerPath = '/__reference-fidelity-r255-sw.js';
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
});

function fixtureHtml() {
  return '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    + '<link rel="icon" href="data:"><title>Reference fidelity cache upgrade</title>'
    + '</head><body><main>Reference fidelity cache upgrade</main></body></html>';
}

function oldWorkerSource() {
  const oldUrls = [oldRuntimeUrl, oldComposerUrl, oldProductLoaderUrl, oldProductUrl, oldAppUrl];
  return [
    `const CACHE_NAME = ${JSON.stringify(oldCacheName)};`,
    `const URLS = ${JSON.stringify(oldUrls)};`,
    "self.addEventListener('install', event => {",
    '  event.waitUntil(caches.open(CACHE_NAME)',
    '    .then(cache => Promise.all(URLS.map(url => cache.put(',
    "      new Request(url), new Response('stale-r255:' + url, {headers: {'Content-Type': 'text/javascript'}}),",
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
      response.end(fixtureHtml());
      return;
    }
    if (url.pathname === oldWorkerPath) {
      response.writeHead(200, {
        'Content-Type': contentTypes['.js'],
        'Service-Worker-Allowed': '/',
      });
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
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}${fixturePath}`, {waitUntil: 'load'});

    await page.evaluate(async workerPath => {
      await navigator.serviceWorker.register(workerPath, {scope: '/'});
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true}));
      }
    }, oldWorkerPath);
    const seeded = await page.evaluate(async ({cacheName, urls}) => {
      const keys = await caches.keys();
      return {
        cachePresent: keys.includes(cacheName),
        entries: await Promise.all(urls.map(url => caches.match(url).then(Boolean))),
      };
    }, {cacheName: oldCacheName, urls: [oldRuntimeUrl, oldComposerUrl, oldProductLoaderUrl, oldProductUrl, oldAppUrl]});
    assert.equal(seeded.cachePresent, true);
    assert.deepEqual(seeded.entries, [true, true, true, true, true]);

    await page.evaluate(async () => {
      await navigator.serviceWorker.register('/sw.js', {scope: '/'});
    });
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
    assert.equal(upgraded, true, 'r256 did not replace the frozen r255 cache');

    const result = await page.evaluate(async ({
      cacheName, oldUrls, runtimeUrl, composerUrl, productLoaderUrl, productUrl, appUrl,
    }) => {
      const cache = await caches.open(cacheName);
      const runtime = await cache.match(runtimeUrl);
      const composer = await cache.match(composerUrl);
      const loader = await cache.match(productLoaderUrl);
      const app = await cache.match(appUrl);
      return {
        runtimeSource: runtime ? await runtime.text() : '',
        composerSource: composer ? await composer.text() : '',
        loaderSource: loader ? await loader.text() : '',
        appSource: app ? await app.text() : '',
        productWasPrecached: Boolean(await cache.match(productUrl)),
        staleEntries: await Promise.all(oldUrls.map(url => caches.match(url).then(Boolean))),
      };
    }, {
      cacheName: newCacheName,
      oldUrls: [oldRuntimeUrl, oldComposerUrl, oldProductLoaderUrl, oldProductUrl, oldAppUrl],
      runtimeUrl: newRuntimeUrl,
      composerUrl: newComposerUrl,
      productLoaderUrl: newProductLoaderUrl,
      productUrl: newProductUrl,
      appUrl: newAppUrl,
    });
    assert.ok(result.runtimeSource.includes(newComposerUrl));
    assert.ok(result.runtimeSource.includes(newProductLoaderUrl));
    assert.ok(result.composerSource.includes('imageReferencePlanConfirmed'));
    assert.ok(result.loaderSource.includes(newProductUrl));
    assert.ok(result.loaderSource.includes(newProductStyleUrl));
    assert.ok(result.appSource.includes('referenceReview'));
    assert.equal(result.productWasPrecached, false, 'Product Studio must remain lazy-loaded');
    assert.deepEqual(result.staleEntries, [false, false, false, false, false]);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      legacyCache: oldCacheName,
      activeCache: newCacheName,
      referencePlanDelivered: true,
      referenceReviewPersistenceDelivered: true,
      productStudioRemainsLazy: true,
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
