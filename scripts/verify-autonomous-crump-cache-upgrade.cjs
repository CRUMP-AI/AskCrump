const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const publicDirectory = path.resolve(process.cwd(), 'public');
const oldCacheName = 'ask-crump-new-body-v1-r249';
const newCacheName = 'ask-crump-new-body-v1-r252';
const oldLoaderUrl = '/crump-code-loader.js?v=5.9.76-code-lazy-load-1';
const newLoaderUrl = '/crump-code-loader.js?v=5.9.76-autonomous-crump-1';
const fixturePath = '/__autonomous-crump-upgrade.html';
const oldWorkerPath = '/__autonomous-crump-old-sw.js';
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
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><link rel="icon" href="data:,"><title>Autonomous Crump upgrade proof</title></head>
<body><main>Autonomous Crump upgrade proof</main></body>
</html>`;
}

function oldWorkerSource() {
  return `const CACHE_NAME = ${JSON.stringify(oldCacheName)};
const OLD_LOADER_URL = ${JSON.stringify(oldLoaderUrl)};
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.put(
        new Request(OLD_LOADER_URL),
        new Response("window.__legacyWorkspaceName = 'Crump Code';", {
          headers: {'Content-Type': 'text/javascript; charset=utf-8'},
        }),
      ))
      .then(() => self.skipWaiting())
  );
});
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));`;
}

function safePublicPath(pathname) {
  const requested = pathname === '/app' ? '/app.html' : pathname;
  const relative = requested.replace(/^\/+/, '');
  const resolved = path.resolve(publicDirectory, relative);
  return resolved.startsWith(`${publicDirectory}${path.sep}`) ? resolved : null;
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
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}${fixturePath}`, {waitUntil: 'load'});

    await page.evaluate(async workerPath => {
      const registration = await navigator.serviceWorker.register(workerPath, {scope: '/'});
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true}));
      }
    }, oldWorkerPath);
    const legacyEvidence = await page.evaluate(async ({cacheName, loaderUrl}) => {
      const cache = await caches.open(cacheName);
      const response = await cache.match(loaderUrl);
      return {cacheKeys: await caches.keys(), loaderSource: response ? await response.text() : ''};
    }, {cacheName: oldCacheName, loaderUrl: oldLoaderUrl});
    assert.ok(legacyEvidence.cacheKeys.includes(oldCacheName));
    assert.ok(legacyEvidence.loaderSource.includes('Crump Code'));

    await page.evaluate(async () => {
      await navigator.serviceWorker.register('/sw.js', {scope: '/'});
    });
    const upgradeDeadline = Date.now() + 30_000;
    let upgradeReady = false;
    while (Date.now() < upgradeDeadline) {
      upgradeReady = await page.evaluate(async ({oldName, nextName}) => {
        const keys = await caches.keys();
        const controller = navigator.serviceWorker.controller;
        return keys.includes(nextName) && !keys.includes(oldName) && controller?.scriptURL.endsWith('/sw.js');
      }, {oldName: oldCacheName, nextName: newCacheName});
      if (upgradeReady) break;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.equal(upgradeReady, true, 'the current service worker did not finish replacing the legacy cache');

    const upgradedEvidence = await page.evaluate(async ({cacheName, oldUrl, nextUrl}) => {
      const cache = await caches.open(cacheName);
      const nextResponse = await cache.match(nextUrl);
      const staleResponse = await caches.match(oldUrl);
      const registrations = await navigator.serviceWorker.getRegistrations();
      const workerSource = await fetch('/sw.js', {cache: 'no-store'}).then(response => response.text());
      return {
        cacheKeys: await caches.keys(),
        controller: navigator.serviceWorker.controller?.scriptURL || '',
        loaderSource: nextResponse ? await nextResponse.text() : '',
        staleLoaderPresent: Boolean(staleResponse),
        registrations: registrations.map(registration => ({
          scope: registration.scope,
          active: registration.active?.scriptURL || '',
          waiting: registration.waiting?.scriptURL || '',
          installing: registration.installing?.scriptURL || '',
        })),
        workerDeletesLegacyCaches: workerSource.includes('async function deleteLegacyCaches()'),
      };
    }, {cacheName: newCacheName, oldUrl: oldLoaderUrl, nextUrl: newLoaderUrl});

    assert.ok(upgradedEvidence.cacheKeys.includes(newCacheName));
    assert.ok(
      !upgradedEvidence.cacheKeys.includes(oldCacheName),
      `legacy cache survived upgrade: ${JSON.stringify(upgradedEvidence)}`,
    );
    assert.ok(upgradedEvidence.controller.endsWith('/sw.js'));
    assert.ok(upgradedEvidence.loaderSource.includes('Autonomous Crump'));
    assert.ok(upgradedEvidence.loaderSource.includes('5.9.76-autonomous-crump-1'));
    assert.equal(upgradedEvidence.loaderSource.includes("'Crump Code'"), false);
    assert.equal(upgradedEvidence.staleLoaderPresent, false);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      legacyCache: oldCacheName,
      activeCache: newCacheName,
      controller: upgradedEvidence.controller,
      staleLoaderPresent: upgradedEvidence.staleLoaderPresent,
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
