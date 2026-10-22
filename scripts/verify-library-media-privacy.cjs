const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const fixturePath = '/tests/fixtures/library-media-privacy.html';
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
});

function safePath(pathname) {
  const relative = pathname.replace(/^\/+/, '');
  const resolved = path.resolve(root, relative);
  return resolved.startsWith(root + path.sep) ? resolved : null;
}

async function startServer() {
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const filePath = safePath(url.pathname);
    if (!filePath) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': contentTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
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

async function resetToAccountA(page) {
  await page.evaluate(async () => {
    window.fixtureReset();
    await window.fixtureUseAccountA();
  });
}

async function evidence(page) {
  return page.evaluate(() => ({
    signedRequests: window.fixtureEvidence.signedRequests.map(request => ({aborted: request.aborted})),
    blobRequests: window.fixtureEvidence.blobRequests.map(request => ({
      aborted: request.aborted,
      credentials: request.credentials,
    })),
    photoSaves: window.fixtureEvidence.photoSaves.length,
    videoSaves: window.fixtureEvidence.videoSaves.length,
    shares: window.fixtureEvidence.shares.length,
    fallbacks: [...window.fixtureEvidence.fallbacks],
    sourceHandoffs: window.fixtureEvidence.sourceHandoffs.map(handoff => ({
      fileId: handoff.file.id,
      url: handoff.file.url,
      hasSignal: Boolean(handoff.options.signal),
      aborted: Boolean(handoff.options.signal?.aborted),
      hasGuard: typeof handoff.options.shouldProceed === 'function',
      mayProceed: handoff.options.shouldProceed?.() === true,
    })),
    sourceViewers: [...window.fixtureEvidence.sourceViewers],
    toasts: [...window.fixtureEvidence.toasts],
  }));
}

(async () => {
  const {server, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const page = await browser.newPage();
    const browserErrors = [];
    page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
    page.on('pageerror', error => browserErrors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}${fixturePath}`, {waitUntil: 'load'});
    await page.waitForFunction(() => document.getElementById('fixtureReady')?.textContent === 'ready');

    await resetToAccountA(page);
    await page.evaluate(() => window.fixtureSetMode({fetch: 'deferred-sign', isNative: true}));
    const nativeSign = page.evaluate(() => window.fixtureRunMedia());
    await page.waitForFunction(() => window.fixtureDeferredSigns.length === 1);
    await page.evaluate(() => {
      window.fixtureSwitchAccount(window.fixtureUserB);
      window.fixtureResolveSign();
    });
    assert.deepEqual(await nativeSign, {value: false, errorName: 'AbortError'});
    let result = await evidence(page);
    assert.equal(result.signedRequests[0].aborted, true);
    assert.equal(result.photoSaves, 0, 'account A signed URL reached the Photos plugin after A→B');
    assert.deepEqual(result.fallbacks, []);
    assert.deepEqual(result.toasts, [], 'account A emitted a stale media status after A→B');

    await resetToAccountA(page);
    await page.evaluate(() => window.fixtureSetMode({isNative: true}));
    const nativeSuccess = await page.evaluate(() => window.fixtureRunMedia());
    assert.deepEqual(nativeSuccess, {value: true, errorName: ''});
    result = await evidence(page);
    assert.equal(result.photoSaves, 1, 'same-account native image save did not reach Photos');
    assert.deepEqual(result.toasts, [{message: 'Image saved to Photos.', type: 'success'}]);

    await resetToAccountA(page);
    await page.evaluate(() => window.fixtureSetMode({fetch: 'deferred-blob', coarse: true}));
    const blobShare = page.evaluate(() => window.fixtureRunMedia());
    await page.waitForFunction(() => window.fixtureDeferredBlobs.length === 1);
    await page.evaluate(() => {
      window.fixtureSwitchAccount(window.fixtureUserB);
      window.fixtureResolveBlob();
    });
    assert.deepEqual(await blobShare, {value: false, errorName: 'AbortError'});
    result = await evidence(page);
    assert.equal(result.blobRequests[0].credentials, 'omit');
    assert.equal(result.blobRequests[0].aborted, true);
    assert.equal(result.shares, 0, 'account A blob reached navigator.share after A→B');
    assert.deepEqual(result.fallbacks, []);
    assert.deepEqual(result.toasts, [], 'account A emitted a stale share status after A→B');

    await resetToAccountA(page);
    await page.evaluate(() => {
      window.fixtureSetMode({native: 'deferred-failure', isNative: true});
      document.getElementById('fixtureVideoDownload').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredNativeSaves.length === 1);
    await page.evaluate(() => {
      window.fixtureSwitchAccount(window.fixtureUserB);
      window.fixtureRejectNativeSave();
    });
    await page.waitForTimeout(25);
    result = await evidence(page);
    assert.equal(result.videoSaves, 1, 'the direct video action did not reach the native adapter');
    assert.deepEqual(result.fallbacks, [], 'direct video navigation fell back after A→B');
    assert.deepEqual(result.toasts, [], 'account A emitted a fallback warning after A→B');

    await resetToAccountA(page);
    await page.evaluate(() => {
      window.fixtureSetMode({native: 'deferred-failure', isNative: true});
      document.getElementById('fixtureVideoDownload').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredNativeSaves.length === 1);
    await page.evaluate(() => {
      window.fixtureDetachedVideoLink = document.getElementById('fixtureVideoDownload');
      window.fixtureDetachedVideoLink.remove();
      window.fixtureRejectNativeSave();
    });
    await page.waitForTimeout(25);
    result = await evidence(page);
    assert.deepEqual(result.fallbacks, [], 'detached direct-video action triggered a stale fallback');
    assert.deepEqual(result.toasts, [], 'detached direct-video action emitted a stale warning');
    await page.evaluate(() => {
      document.querySelector('.crump53-video-result-actions').appendChild(window.fixtureDetachedVideoLink);
      delete window.fixtureDetachedVideoLink;
    });

    await resetToAccountA(page);
    const ordinary = await page.evaluate(async () => {
      window.fixtureSetMode();
      return window.fixtureRunMedia();
    });
    assert.deepEqual(ordinary, {value: false, errorName: ''});
    result = await evidence(page);
    assert.deepEqual(result.fallbacks, [], 'ordinary Files delivery must keep canonical fallback ownership');

    await resetToAccountA(page);
    const urlOnly = await page.evaluate(() => window.fixtureRunUrlOnlyMedia());
    assert.deepEqual(urlOnly, {value: false, errorName: ''});
    result = await evidence(page);
    assert.equal(result.signedRequests.length, 0, 'URL-only media must not enter ID-based signing');
    assert.deepEqual(result.fallbacks, [], 'URL-only media fallback must remain owned by CrumpFileTools');

    await resetToAccountA(page);
    await page.evaluate(() => {
      window.fixtureSetMode();
      document.getElementById('fixtureVideoDownload').click();
    });
    await page.waitForFunction(() => window.fixtureEvidence.fallbacks.length === 1);
    result = await evidence(page);
    assert.deepEqual(result.fallbacks, ['/api/files/00000000-0000-4000-8000-000000000602/content?download=1']);

    await resetToAccountA(page);
    await page.evaluate(() => window.fixtureOpenOriginal());
    await page.waitForFunction(() => window.fixtureDeferredSources.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount(window.fixtureUserB));
    result = await evidence(page);
    assert.deepEqual(result.sourceHandoffs, [{
      fileId: '00000000-0000-4000-8000-000000000601',
      url: '',
      hasSignal: true,
      aborted: true,
      hasGuard: true,
      mayProceed: false,
    }]);
    await page.evaluate(() => window.fixtureDeferredSources[0].resolve(true));
    await page.waitForTimeout(25);
    result = await evidence(page);
    assert.deepEqual(result.sourceViewers, [], 'account A original source opened after A→B');
    assert.deepEqual(result.toasts, [], 'account A original-source delivery emitted a stale status after A→B');

    assert.equal(await page.locator('#fixtureErrors').textContent(), '0');
    assert.deepEqual(browserErrors, []);
    process.stdout.write(JSON.stringify({
      nativeSignBlocked: true,
      nativeSameAccountSuccess: true,
      blobShareBlocked: true,
      postSwitchFallbackBlocked: true,
      detachedVideoFallbackBlocked: true,
      directVideoFallbackCurrent: true,
      ordinaryFallbackCallerOwned: true,
      urlOnlyFallbackCallerOwned: true,
      originalSourceViewerBlocked: true,
    }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
