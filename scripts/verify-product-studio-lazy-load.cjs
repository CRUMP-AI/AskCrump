const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const publicDirectory = path.resolve(process.cwd(), 'public');
const assetPaths = Object.freeze({
  loader: '/crump-product-loader.js',
  script: '/crump-product-5.3.js',
  style: '/crump-product-5.3.css',
});

function fixtureHtml(mode) {
  const persisted = mode === 'persisted'
    ? "window.currentUser = {id: 'fixture-user'}; localStorage.setItem('askcrump.activeProject53', 'fixture-project');"
    : "window.currentUser = null;";
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><link rel="icon" href="data:,"><title>Product Studio lazy-load proof</title></head>
<body>
  <button id="projects" type="button" data-v1-command="projects">Projects</button>
  <button id="video" type="button" data-crump5930-destination="video">Video</button>
  <output id="status">idle</output>
  <script>
    ${persisted}
    window.chats = [];
    window.productOpens = [];
    window.toasts = [];
    window.showToast = (message, type) => {
      window.toasts.push({message, type});
      document.getElementById('status').textContent = type === 'error' ? 'retry' : message;
    };
  </script>
  <script src="${assetPaths.loader}?v=5.9.76-product-studio-lazy-load-1"></script>
  <script>
    document.getElementById('projects').addEventListener('click', () => {
      void window.CrumpProduct53.open('projects');
    });
    document.getElementById('video').addEventListener('click', () => {
      void window.CrumpProduct53.open('video');
    });
  </script>
</body>
</html>`;
}

function productStub() {
  return `(() => {
    window.__fixtureProductLoaded = true;
    window.CrumpProduct53 = Object.freeze({
      open(destination) {
        window.productOpens.push(destination);
        document.getElementById('status').textContent = 'open:' + destination;
        return true;
      },
      openProject(projectId) { window.productOpens.push('project:' + projectId); return true; },
      openFiles() { window.productOpens.push('files'); return true; },
      projectTarget() { return {id: 'fixture-project', name: 'Launch Operations'}; },
      projectForConversation() { return Promise.resolve(null); },
      resolveOutcomeProject() { return Promise.resolve({saved: false, project: null}); },
      keepConversation() { return Promise.resolve({success: true}); },
      keepArtifact() { return Promise.resolve({success: true}); },
      openManuscript() { window.productOpens.push('manuscript'); return true; },
      handleCreationHandoff() { return Promise.resolve(true); },
    });
  })();`;
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
    const mode = url.searchParams.get('fixtureMode') || String(request.headers.cookie || '').match(/fixture_mode=([^;]+)/)?.[1] || 'normal';
    const key = `${mode}:${url.pathname}`;
    counts.set(key, (counts.get(key) || 0) + 1);
    response.setHeader('Cache-Control', 'no-store');

    if (url.pathname === '/fixture.html') {
      const fixtureMode = ['normal', 'retry', 'persisted'].includes(url.searchParams.get('mode'))
        ? url.searchParams.get('mode')
        : 'normal';
      response.setHeader('Set-Cookie', `fixture_mode=${fixtureMode}; Path=/; SameSite=Lax`);
      response.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
      response.end(fixtureHtml(fixtureMode));
      return;
    }
    if (mode === 'retry' && url.pathname === assetPaths.style && counts.get(key) === 1) {
      await new Promise(resolve => setTimeout(resolve, 100));
      response.writeHead(503, {'Content-Type': 'text/plain; charset=utf-8'});
      response.end('Temporary fixture failure');
      return;
    }
    if (url.pathname === assetPaths.script) {
      await new Promise(resolve => setTimeout(resolve, 80));
      response.writeHead(200, {'Content-Type': 'text/javascript; charset=utf-8'});
      response.end(productStub());
      return;
    }

    const filePath = safePublicPath(url.pathname);
    try {
      const body = filePath ? await readFile(filePath) : null;
      if (!body) throw new Error('not found');
      if (url.pathname === assetPaths.style) await new Promise(resolve => setTimeout(resolve, 80));
      response.writeHead(200, {'Content-Type': url.pathname.endsWith('.css') ? 'text/css; charset=utf-8' : 'text/javascript; charset=utf-8'});
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
    projectBusy: document.getElementById('projects')?.getAttribute('aria-busy'),
    projectDisabled: document.getElementById('projects')?.disabled,
    videoBusy: document.getElementById('video')?.getAttribute('aria-busy'),
    opens: window.productOpens.slice(),
    toasts: window.toasts.slice(),
    loader: Boolean(window.CrumpProductLoader?.load),
    facade: Boolean(window.CrumpProduct53?.open),
    full: Boolean(window.__fixtureProductLoaded),
    styleNodes: document.querySelectorAll('link[data-crump-product-lazy-style]').length,
    scriptNodes: document.querySelectorAll('script[data-crump-product-lazy-script]').length,
    loadedStyleNodes: document.querySelectorAll('link[data-crump-product-lazy-style][data-crump-product-loaded="true"]').length,
    loadedScriptNodes: document.querySelectorAll('script[data-crump-product-lazy-script][data-crump-product-loaded="true"]').length,
    target: window.CrumpProduct53?.projectTarget?.() || null,
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
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}/fixture.html?mode=normal`, {waitUntil: 'networkidle'});
    const initial = await state(page);
    assert.equal(initial.loader, true);
    assert.equal(initial.facade, true);
    assert.equal(initial.full, false);
    assert.equal(initial.styleNodes, 0);
    assert.equal(initial.scriptNodes, 0);
    assert.deepEqual(initial.opens, []);
    assert.deepEqual(initial.toasts, []);
    assert.equal(counts.get(`normal:${assetPaths.script}`) || 0, 0);
    assert.equal(counts.get(`normal:${assetPaths.style}`) || 0, 0);

    await page.click('#projects', {noWaitAfter: true});
    await page.waitForFunction(() => document.getElementById('projects')?.getAttribute('aria-busy') === 'true');
    await page.waitForFunction(() => document.getElementById('status')?.textContent === 'open:projects');
    const opened = await state(page);
    assert.equal(opened.projectBusy, null);
    assert.equal(opened.projectDisabled, false);
    assert.equal(opened.videoBusy, null);
    assert.deepEqual(opened.opens, ['projects']);
    assert.deepEqual(opened.toasts, [{message: 'Opening Projects…', type: 'info'}]);
    assert.equal(opened.full, true);
    assert.equal(opened.loadedStyleNodes, 1);
    assert.equal(opened.loadedScriptNodes, 1);
    assert.deepEqual(opened.target, {id: 'fixture-project', name: 'Launch Operations'});
    await page.click('#video');
    await page.waitForFunction(() => window.productOpens.length === 2);
    const reused = await state(page);
    assert.deepEqual(reused.opens, ['projects', 'video']);
    assert.deepEqual(reused.toasts, [{message: 'Opening Projects…', type: 'info'}]);
    assert.equal(counts.get(`normal:${assetPaths.script}`), 1);
    assert.equal(counts.get(`normal:${assetPaths.style}`), 1);
    await context.close();

    const retryContext = await browser.newContext();
    const retryPage = await retryContext.newPage();
    retryPage.on('pageerror', error => errors.push(`retry: ${error.message}`));
    await retryPage.goto(`http://127.0.0.1:${port}/fixture.html?mode=retry`, {waitUntil: 'networkidle'});
    await retryPage.click('#projects');
    await retryPage.waitForFunction(() => document.getElementById('status')?.textContent === 'retry');
    const failed = await state(retryPage);
    assert.equal(failed.projectBusy, null);
    assert.equal(failed.projectDisabled, false);
    assert.deepEqual(failed.opens, []);
    assert.equal(failed.styleNodes, 0);
    assert.equal(failed.loadedScriptNodes, 1);
    await retryPage.click('#projects');
    await retryPage.waitForFunction(() => window.productOpens.length === 1);
    const recovered = await state(retryPage);
    assert.deepEqual(recovered.opens, ['projects']);
    assert.equal(recovered.loadedStyleNodes, 1);
    assert.equal(counts.get(`retry:${assetPaths.script}`), 1);
    assert.equal(counts.get(`retry:${assetPaths.style}`), 2);
    await retryContext.close();

    const persistedContext = await browser.newContext();
    const persistedPage = await persistedContext.newPage();
    persistedPage.on('console', message => { if (message.type() === 'error') errors.push(`persisted: ${message.text()}`); });
    persistedPage.on('pageerror', error => errors.push(`persisted: ${error.message}`));
    await persistedPage.goto(`http://127.0.0.1:${port}/fixture.html?mode=persisted`, {waitUntil: 'networkidle'});
    await persistedPage.waitForFunction(() => window.__fixtureProductLoaded === true);
    const persisted = await state(persistedPage);
    assert.deepEqual(persisted.opens, []);
    assert.deepEqual(persisted.target, {id: 'fixture-project', name: 'Launch Operations'});
    assert.equal(counts.get(`persisted:${assetPaths.script}`), 1);
    assert.equal(counts.get(`persisted:${assetPaths.style}`), 1);
    await persistedContext.close();

    assert.deepEqual(errors, []);
    process.stdout.write(JSON.stringify({initial, opened, failed, recovered, persisted, requests: Object.fromEntries(counts), errors}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
