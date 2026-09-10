const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const publicDirectory = path.resolve(process.cwd(), 'public');
const assetPaths = Object.freeze({
  media: '/crump-media-save.js',
  loader: '/crump-library-loader.js',
  script: '/crump-library-5.7.js',
  style: '/crump-library-5.7.css',
});
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
});

function modeFromRequest(request) {
  const cookie = String(request.headers.cookie || '');
  return /(?:^|;\s*)fixture_mode=retry(?:;|$)/.test(cookie) ? 'retry' : 'normal';
}

function fixtureHtml() {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><link rel="icon" href="data:,"><title>Library lazy-load proof</title></head>
<body>
  <button id="library" type="button" data-crump5930-destination="library">Library</button>
  <div class="crump50-image-actions"><button type="button">Download</button></div>
  <output id="status">idle</output>
  <script>
    window.libraryOpens = 0;
    window.showToast = (message, type) => {
      document.getElementById('status').textContent = type === 'error' ? 'retry' : message;
    };
  </script>
  <script src="${assetPaths.media}?v=5.9.76-library-lazy-load-1"></script>
  <script src="${assetPaths.loader}?v=5.9.76-library-lazy-load-1"></script>
  <script>
    document.getElementById('library').addEventListener('click', () => {
      window.libraryOpens += 1;
      document.getElementById('status').textContent = 'open';
    });
  </script>
</body>
</html>`;
}

function safePublicPath(pathname) {
  const relative = pathname.replace(/^\/+/, '');
  const resolved = path.resolve(publicDirectory, relative);
  return resolved.startsWith(`${publicDirectory}${path.sep}`) ? resolved : null;
}

async function startServer() {
  const counts = new Map();
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const mode = modeFromRequest(request);
    const key = `${mode}:${url.pathname}`;
    counts.set(key, (counts.get(key) || 0) + 1);
    response.setHeader('Cache-Control', 'no-store');

    if (url.pathname === '/fixture.html') {
      const fixtureMode = url.searchParams.get('mode') === 'retry' ? 'retry' : 'normal';
      response.setHeader('Set-Cookie', `fixture_mode=${fixtureMode}; Path=/; SameSite=Lax`);
      response.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
      response.end(fixtureHtml());
      return;
    }
    if (mode === 'retry' && url.pathname === assetPaths.style && counts.get(key) === 1) {
      await new Promise(resolve => setTimeout(resolve, 125));
      response.writeHead(503, {'Content-Type': 'text/plain; charset=utf-8'});
      response.end('Temporary fixture failure');
      return;
    }

    const filePath = safePublicPath(url.pathname);
    try {
      const body = filePath ? await readFile(filePath) : null;
      if (!body) throw new Error('not found');
      if (url.pathname === assetPaths.script || url.pathname === assetPaths.style) {
        await new Promise(resolve => setTimeout(resolve, 75));
      }
      response.writeHead(200, {'Content-Type': contentTypes[path.extname(filePath)] || 'application/octet-stream'});
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
  return {server, counts, port: server.address().port};
}

async function state(page) {
  return page.evaluate(() => ({
    status: document.getElementById('status')?.textContent,
    busy: document.getElementById('library')?.getAttribute('aria-busy'),
    disabled: document.getElementById('library')?.disabled,
    opens: window.libraryOpens,
    loader: Boolean(window.CrumpLibraryLoader),
    media: Boolean(window.CrumpMediaSave?.saveMedia),
    library: Boolean(window.CrumpLibrary57?.refresh),
    mediaLabel: document.querySelector('.crump50-image-actions button')?.textContent,
    styleNodes: document.querySelectorAll('link[data-crump-library-lazy-style]').length,
    scriptNodes: document.querySelectorAll('script[data-crump-library-lazy-script]').length,
    loadedStyleNodes: document.querySelectorAll('link[data-crump-library-lazy-style][data-crump-library-loaded="true"]').length,
    loadedScriptNodes: document.querySelectorAll('script[data-crump-library-lazy-script][data-crump-library-loaded="true"]').length,
  }));
}

(async () => {
  const {server, counts, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on('console', message => { if (message.type() === 'error') errors.push(`normal: ${message.text()}`); });
    page.on('pageerror', error => errors.push(`normal: ${error.message}`));
    await page.goto(`http://127.0.0.1:${port}/fixture.html?mode=normal`, {waitUntil: 'networkidle'});
    assert.deepEqual(await state(page), {
      status: 'idle', busy: null, disabled: false, opens: 0,
      loader: true, media: true, library: false, mediaLabel: 'Save',
      styleNodes: 0, scriptNodes: 0, loadedStyleNodes: 0, loadedScriptNodes: 0,
    });
    assert.equal(counts.get(`normal:${assetPaths.script}`) || 0, 0);
    assert.equal(counts.get(`normal:${assetPaths.style}`) || 0, 0);
    await page.click('#library', {noWaitAfter: true});
    await page.waitForFunction(() => document.getElementById('library')?.getAttribute('aria-busy') === 'true');
    await page.waitForFunction(() => window.libraryOpens === 1);
    const normal = await state(page);
    assert.deepEqual(normal, {
      status: 'open', busy: null, disabled: false, opens: 1,
      loader: true, media: true, library: true, mediaLabel: 'Save',
      styleNodes: 1, scriptNodes: 1, loadedStyleNodes: 1, loadedScriptNodes: 1,
    });
    await page.click('#library');
    assert.equal((await state(page)).opens, 2);
    assert.equal(counts.get(`normal:${assetPaths.script}`), 1);
    assert.equal(counts.get(`normal:${assetPaths.style}`), 1);
    await context.close();

    const retryContext = await browser.newContext();
    const retryPage = await retryContext.newPage();
    retryPage.on('pageerror', error => errors.push(`retry: ${error.message}`));
    await retryPage.goto(`http://127.0.0.1:${port}/fixture.html?mode=retry`, {waitUntil: 'networkidle'});
    await retryPage.click('#library');
    await retryPage.waitForFunction(() => document.getElementById('status')?.textContent === 'retry');
    const failed = await state(retryPage);
    assert.equal(failed.busy, null);
    assert.equal(failed.disabled, false);
    assert.equal(failed.opens, 0);
    assert.equal(failed.styleNodes, 0);
    assert.equal(failed.library, true);
    await retryPage.click('#library');
    await retryPage.waitForFunction(() => window.libraryOpens === 1);
    const recovered = await state(retryPage);
    assert.equal(recovered.loadedStyleNodes, 1);
    assert.equal(recovered.loadedScriptNodes, 1);
    assert.equal(counts.get(`retry:${assetPaths.style}`), 2);
    assert.equal(counts.get(`retry:${assetPaths.script}`), 1);
    await retryContext.close();

    assert.deepEqual(errors, []);
    process.stdout.write(JSON.stringify({normal, failed, recovered, requests: Object.fromEntries(counts), errors}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
