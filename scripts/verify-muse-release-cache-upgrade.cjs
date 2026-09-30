const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const root = path.resolve(__dirname, '..');
const publicDirectory = path.join(root, 'public');
const oldCacheName = 'ask-crump-new-body-v1-r253';
const newCacheName = 'ask-crump-new-body-v1-r254';
const oldUrls = Object.freeze([
  '/runtime-body-v1.js?v=5.9.76-image-studio-entry-1',
  '/conversation.css?v=5.9.76-continuity-handoff-1',
  '/crump-design-pass.css?v=1',
  '/scroll-manager.js?v=5.9.76-user-controlled-scroll-1',
  '/ui-functions.js?v=5.9.76-project-save-offer-1',
  '/presence-manager.js?v=5.9.76',
  '/crump-v1-body.js?v=5.9.76-navigation-discovery-1',
  '/crump-5.2.2.js?v=5.9.76-stripe-destination-integrity-1',
]);
const releaseToken = '5.9.76-muse-release-repair-1';
const newUrls = Object.freeze({
  runtime: `/runtime-body-v1.js?v=${releaseToken}`,
  conversation: `/conversation.css?v=${releaseToken}`,
  design: `/crump-design-pass.css?v=${releaseToken}`,
  scroll: `/scroll-manager.js?v=${releaseToken}`,
  ui: `/ui-functions.js?v=${releaseToken}`,
  presence: `/presence-manager.js?v=${releaseToken}`,
  starter: `/crump-v1-body.js?v=${releaseToken}`,
  enhancedScroll: `/crump-5.2.2.js?v=${releaseToken}`,
  mascot: '/assets/brand/crump-mascot.png',
});
const fixturePath = '/__muse-release-cache-upgrade.html';
const oldWorkerPath = '/__muse-release-r253-sw.js';
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
    "      new Request(url), new Response('stale-r253:' + url, {headers: {'Content-Type': 'text/plain'}}),",
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
      response.end('<!doctype html><meta charset="utf-8"><title>Muse release cache upgrade</title>');
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
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
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
        await new Promise(resolve => navigator.serviceWorker.addEventListener(
          'controllerchange', resolve, {once: true},
        ));
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
    assert.equal(upgraded, true, 'r254 did not replace the frozen r253 cache');

    const result = await page.evaluate(async ({cacheName, previousUrls, urls}) => {
      const cache = await caches.open(cacheName);
      const read = async url => {
        const response = await cache.match(url);
        return response ? response.text() : '';
      };
      return {
        runtime: await read(urls.runtime),
        conversation: await read(urls.conversation),
        design: await read(urls.design),
        scroll: await read(urls.scroll),
        ui: await read(urls.ui),
        presence: await read(urls.presence),
        starter: await read(urls.starter),
        enhancedScroll: await read(urls.enhancedScroll),
        mascotPresent: Boolean(await cache.match(urls.mascot)),
        staleEntries: await Promise.all(previousUrls.map(url => caches.match(url).then(Boolean))),
      };
    }, {cacheName: newCacheName, previousUrls: oldUrls, urls: newUrls});

    for (const url of Object.values(newUrls).filter(url => url !== newUrls.mascot)) {
      assert.ok(result.runtime.includes(url) || url === newUrls.runtime);
    }
    assert.ok(result.conversation.length > 0);
    assert.ok(!result.conversation.includes('crump-typewriter-active'));
    assert.ok(!result.design.includes('@keyframes dp-msg-in'));
    assert.ok(result.design.includes('@media (prefers-reduced-motion: reduce)'));
    assert.ok(result.scroll.includes("behavior: 'auto'"));
    assert.ok(!result.scroll.includes("behavior: 'smooth'"));
    assert.ok(!result.ui.includes('typewriter'));
    assert.ok(!result.ui.includes('container.scrollTop = container.scrollHeight'));
    assert.ok(result.presence.includes('refreshVisiblePresence({ensureLabel: true});'));
    assert.ok(result.starter.includes("input.dispatchEvent(new Event('input', {bubbles: true}));"));
    assert.ok(result.enhancedScroll.includes("behavior: 'auto'"));
    assert.ok(!result.enhancedScroll.includes("behavior: 'smooth'"));
    assert.equal(result.mascotPresent, true);
    assert.deepEqual(result.staleEntries, oldUrls.map(() => false));
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      legacyCache: oldCacheName,
      activeCache: newCacheName,
      userControlledViewport: true,
      cachedRepairAssets: true,
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
