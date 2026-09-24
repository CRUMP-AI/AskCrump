const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const publicDirectory = path.join(root, 'public');
const frozenDirectory = path.join(root, 'tests', 'fixtures', 'activation-cache-r253');
const oldCacheName = 'ask-crump-new-body-v1-r253';
const newCacheName = 'ask-crump-new-body-v1-r254';
const oldRuntimeUrl = '/runtime-body-v1.js?v=5.9.76-owner-isolation-native-store-1';
const newRuntimeUrl = '/runtime-body-v1.js?v=5.9.76-server-authoritative-activation-1';
const oldAppUrl = '/app.js?v=5.9.76-video-owner-composer-1';
const newAppUrl = '/app.js?v=5.9.76-server-authoritative-activation-1';
const oldAnalyticsUrl = '/product-analytics.js?v=5.9.76-navigation-discovery-1';
const newAnalyticsUrl = '/product-analytics.js?v=5.9.76-server-authoritative-activation-1';
const fixturePath = '/__server-authoritative-activation-upgrade.html';
const oldWorkerPath = '/__server-authoritative-activation-r253-sw.js';
const expectedAppHash = 'e4371a5e873a17385df6111e0cc7335c84b939176edff95c56c5dc1bd6d2848a';
const expectedAnalyticsHash = '23d5d3bcb23a078c37f2b3d35086865fbb670fecba0a2b7a7999b26d3ccbef1c';
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
});

function normalizeSource(source) {
  return String(source).replace(/\r\n/g, '\n');
}

function sourceHash(source) {
  return createHash('sha256').update(normalizeSource(source), 'utf8').digest('hex');
}

function fixtureHtml() {
  return '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    + '<link rel="icon" href="data:"><title>Activation cache upgrade proof</title>'
    + '</head><body><main>Activation cache upgrade proof</main></body></html>';
}

function oldWorkerSource(frozenAppSource, frozenAnalyticsSource) {
  return [
    'const CACHE_NAME = ' + JSON.stringify(oldCacheName) + ';',
    'const OLD_RUNTIME_URL = ' + JSON.stringify(oldRuntimeUrl) + ';',
    'const OLD_APP_URL = ' + JSON.stringify(oldAppUrl) + ';',
    'const OLD_ANALYTICS_URL = ' + JSON.stringify(oldAnalyticsUrl) + ';',
    "self.addEventListener('install', event => {",
    '  event.waitUntil(',
    '    caches.open(CACHE_NAME)',
    '      .then(cache => Promise.all([',
    '        cache.put(new Request(OLD_RUNTIME_URL), new Response(',
    '          "window.__staleActivationRuntime = true;",',
    "          {headers: {'Content-Type': 'text/javascript; charset=utf-8'}},",
    '        )),',
    '        cache.put(new Request(OLD_APP_URL), new Response(',
    '          ' + JSON.stringify(frozenAppSource) + ',',
    "          {headers: {'Content-Type': 'text/javascript; charset=utf-8'}},",
    '        )),',
    '        cache.put(new Request(OLD_ANALYTICS_URL), new Response(',
    '          ' + JSON.stringify(frozenAnalyticsSource) + ',',
    "          {headers: {'Content-Type': 'text/javascript; charset=utf-8'}},",
    '        )),',
    '      ]))',
    '      .then(() => self.skipWaiting())',
    '  );',
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

async function startServer(frozenAppSource, frozenAnalyticsSource) {
  const analyticsPosts = [];
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    response.setHeader('Cache-Control', 'no-store');

    if (url.pathname === '/api/analytics/events') {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      let payload = {};
      try {
        payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      } catch (_) {
        payload = {};
      }
      analyticsPosts.push(payload);
      response.writeHead(422, {'Content-Type': 'application/json; charset=utf-8'});
      response.end(JSON.stringify({detail: 'ActivationReached is server-authoritative.'}));
      return;
    }
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
      response.end(oldWorkerSource(frozenAppSource, frozenAnalyticsSource));
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
  return {server, port: server.address().port, analyticsPosts};
}

(async () => {
  const frozenAppSource = normalizeSource(
    await readFile(path.join(frozenDirectory, 'app.js'), 'utf8'),
  );
  const frozenAnalyticsSource = normalizeSource(
    await readFile(path.join(frozenDirectory, 'product-analytics.js'), 'utf8'),
  );
  assert.equal(sourceHash(frozenAppSource), expectedAppHash);
  assert.equal(sourceHash(frozenAnalyticsSource), expectedAnalyticsHash);

  const completionStart = frozenAppSource.indexOf('function completeUserMessage(');
  const completionEnd = frozenAppSource.indexOf('function applyCompletedReplySafely(', completionStart);
  const completionSource = frozenAppSource.slice(completionStart, completionEnd);
  assert.ok(completionStart >= 0 && completionEnd > completionStart);
  assert.ok(completionSource.includes('void recordFirstSuccessfulResponse();'));
  assert.ok(
    completionSource.indexOf('void recordFirstSuccessfulResponse();')
      > completionSource.indexOf('syncCompletedReplyInBackground();'),
  );

  const activationStart = frozenAppSource.indexOf('async function recordFirstSuccessfulResponse()');
  const activationEndMarker = '\n}\n\nasync function processUserMessage';
  const activationEnd = frozenAppSource.indexOf(activationEndMarker, activationStart);
  assert.ok(activationStart >= 0 && activationEnd > activationStart);
  const activationFunctionSource = frozenAppSource.slice(activationStart, activationEnd + 2);

  const {server, port, analyticsPosts} = await startServer(
    frozenAppSource,
    frozenAnalyticsSource,
  );
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  try {
    const context = await browser.newContext({serviceWorkers: 'allow'});
    const page = await context.newPage();
    const errors = [];
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:' + port + fixturePath, {waitUntil: 'load'});

    await page.evaluate(async workerPath => {
      await navigator.serviceWorker.register(workerPath, {scope: '/'});
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise(resolve => {
          navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true});
        });
      }
    }, oldWorkerPath);

    const legacyResult = await page.evaluate(async ({
      cacheName, appUrl, analyticsUrl, functionSource,
    }) => {
      const cache = await caches.open(cacheName);
      const appSource = await cache.match(appUrl).then(response => response.text());
      const analyticsSource = await cache.match(analyticsUrl).then(response => response.text());
      const storageWrites = [];
      window.SafeStorage = {
        getItem: () => null,
        setItem: (...values) => storageWrites.push(values),
      };
      window.STORAGE_KEYS = {ACTIVATION_RECORDED: 'crump_activation_recorded'};
      window.eval(analyticsSource);
      window.eval(functionSource + '\nwindow.__legacyRecordActivation = recordFirstSuccessfulResponse;');
      window.__legacyMessageState = 'completed';
      await window.__legacyRecordActivation();
      return {
        appSource,
        analyticsSource,
        messageState: window.__legacyMessageState,
        storageWrites,
        cacheKeys: await caches.keys(),
      };
    }, {
      cacheName: oldCacheName,
      appUrl: oldAppUrl,
      analyticsUrl: oldAnalyticsUrl,
      functionSource: activationFunctionSource,
    });
    assert.equal(normalizeSource(legacyResult.appSource), frozenAppSource);
    assert.equal(normalizeSource(legacyResult.analyticsSource), frozenAnalyticsSource);
    assert.equal(legacyResult.messageState, 'completed');
    assert.deepEqual(legacyResult.storageWrites, []);
    assert.ok(legacyResult.cacheKeys.includes(oldCacheName));
    assert.deepEqual(analyticsPosts, [{
      eventName: 'ActivationReached',
      eventKey: 'first-successful-response',
    }]);

    await page.evaluate(async () => {
      await navigator.serviceWorker.register('/sw.js', {scope: '/'});
    });
    const upgradeDeadline = Date.now() + 30_000;
    let upgradeReady = false;
    while (Date.now() < upgradeDeadline) {
      upgradeReady = await page.evaluate(async ({oldName, nextName}) => {
        const keys = await caches.keys();
        const controller = navigator.serviceWorker.controller;
        return keys.includes(nextName)
          && !keys.includes(oldName)
          && controller?.scriptURL.endsWith('/sw.js');
      }, {oldName: oldCacheName, nextName: newCacheName});
      if (upgradeReady) break;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.equal(upgradeReady, true, 'r254 did not replace the frozen r253 cache');

    const upgraded = await page.evaluate(async ({
      cacheName, oldRuntime, oldApp, oldAnalytics, nextRuntime, nextApp, nextAnalytics,
    }) => {
      const cache = await caches.open(cacheName);
      const currentRuntime = await cache.match(nextRuntime);
      const currentApp = await cache.match(nextApp);
      const currentAnalytics = await cache.match(nextAnalytics);
      return {
        cacheKeys: await caches.keys(),
        controller: navigator.serviceWorker.controller?.scriptURL || '',
        runtimeSource: currentRuntime ? await currentRuntime.text() : '',
        appSource: currentApp ? await currentApp.text() : '',
        analyticsSource: currentAnalytics ? await currentAnalytics.text() : '',
        staleRuntimePresent: Boolean(await caches.match(oldRuntime)),
        staleAppPresent: Boolean(await caches.match(oldApp)),
        staleAnalyticsPresent: Boolean(await caches.match(oldAnalytics)),
      };
    }, {
      cacheName: newCacheName,
      oldRuntime: oldRuntimeUrl,
      oldApp: oldAppUrl,
      oldAnalytics: oldAnalyticsUrl,
      nextRuntime: newRuntimeUrl,
      nextApp: newAppUrl,
      nextAnalytics: newAnalyticsUrl,
    });
    assert.ok(upgraded.cacheKeys.includes(newCacheName));
    assert.ok(!upgraded.cacheKeys.includes(oldCacheName));
    assert.ok(upgraded.controller.endsWith('/sw.js'));
    assert.ok(upgraded.runtimeSource.includes(newAppUrl));
    assert.ok(upgraded.runtimeSource.includes(newAnalyticsUrl));
    assert.equal(upgraded.appSource.includes('recordFirstSuccessfulResponse'), false);
    assert.equal(upgraded.appSource.includes('ActivationReached'), false);
    assert.equal(upgraded.analyticsSource.includes('ActivationReached'), false);
    assert.equal(upgraded.staleRuntimePresent, false);
    assert.equal(upgraded.staleAppPresent, false);
    assert.equal(upgraded.staleAnalyticsPresent, false);

    const expectedLegacyRejections = errors.filter(message => message.includes('status of 422'));
    const unexpectedErrors = errors.filter(message => !message.includes('status of 422'));
    assert.ok(expectedLegacyRejections.length >= 1);
    assert.deepEqual(unexpectedErrors, []);

    process.stdout.write(JSON.stringify({
      frozenAppHash: expectedAppHash,
      frozenAnalyticsHash: expectedAnalyticsHash,
      legacyActivationRejected: true,
      legacyMessageState: legacyResult.messageState,
      legacyCache: oldCacheName,
      activeCache: newCacheName,
      expectedLegacyRejections: expectedLegacyRejections.length,
      errors: unexpectedErrors,
    }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
