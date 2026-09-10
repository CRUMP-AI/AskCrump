const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const publicDirectory = path.resolve(process.cwd(), 'public');
const assetPaths = Object.freeze({
  loader: '/crump-code-loader.js',
  script: '/crump-code-5.9.35.js',
  style: '/crump-code-5.9.35.css',
});
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
});

function modeFromRequest(request) {
  const cookie = String(request.headers.cookie || '');
  const match = cookie.match(/(?:^|;\s*)fixture_mode=(disabled|locked|entitled)(?:;|$)/);
  return match?.[1] || 'disabled';
}

function featurePayload(mode) {
  const configured = mode !== 'disabled';
  return JSON.stringify({
    success: true,
    internalAccess: false,
    features: {code_workspace: {configured, entitled: mode === 'entitled'}},
    providers: {code: {configured}},
  });
}

function fixtureHtml() {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><link rel="icon" href="data:,"><title>Code lazy-load proof</title></head>
<body>
  <button type="button" data-crump-code-destination hidden aria-label="Code">Code desktop</button>
  <button type="button" data-crump-code-destination hidden aria-label="Code">Code mobile</button>
  <script>window.currentUser = {id: 'fixture-user'};</script>
  <script src="${assetPaths.loader}?v=5.9.76-code-lazy-load-1"></script>
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
    counts.set(`${mode}:${url.pathname}`, (counts.get(`${mode}:${url.pathname}`) || 0) + 1);
    response.setHeader('Cache-Control', 'no-store');

    if (url.pathname === '/fixture.html') {
      const fixtureMode = ['disabled', 'locked', 'entitled'].includes(url.searchParams.get('mode'))
        ? url.searchParams.get('mode')
        : 'disabled';
      response.setHeader('Set-Cookie', `fixture_mode=${fixtureMode}; Path=/; SameSite=Lax`);
      response.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
      response.end(fixtureHtml());
      return;
    }
    if (url.pathname === '/api/features') {
      response.writeHead(200, {'Content-Type': 'application/json; charset=utf-8'});
      response.end(featurePayload(mode));
      return;
    }

    const filePath = safePublicPath(url.pathname);
    try {
      const body = filePath ? await readFile(filePath) : null;
      if (!body) throw new Error('not found');
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

async function inspect(page, destination) {
  await page.goto(destination, {waitUntil: 'networkidle'});
  return page.evaluate(() => {
    const destinations = [...document.querySelectorAll('[data-crump-code-destination]')];
    return {
      hidden: destinations.map(item => item.hidden),
      locked: destinations.map(item => item.classList.contains('is-locked')),
      labels: destinations.map(item => item.getAttribute('aria-label')),
      loader: Boolean(window.CrumpCodeLoader),
      workspace: Boolean(window.CrumpCodeWorkspace),
      shell: Boolean(document.getElementById('crumpCodeWorkspace')),
      bootstrapStatusRetained: Object.hasOwn(window, '__crumpCodeBootstrapStatus'),
    };
  });
}

(async () => {
  const {server, counts, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];
  try {
    const results = {};
    for (const mode of ['disabled', 'locked', 'entitled']) {
      const context = await browser.newContext();
      const page = await context.newPage();
      page.on('console', message => { if (message.type() === 'error') errors.push(`${mode}: ${message.text()}`); });
      page.on('pageerror', error => errors.push(`${mode}: ${error.message}`));
      results[mode] = await inspect(page, `http://127.0.0.1:${port}/fixture.html?mode=${mode}`);
      await context.close();
    }

    assert.deepEqual(results.disabled, {
      hidden: [true, true], locked: [false, false], labels: ['Code', 'Code'],
      loader: true, workspace: false, shell: false, bootstrapStatusRetained: false,
    });
    assert.equal(counts.get(`disabled:${assetPaths.script}`) || 0, 0);
    assert.equal(counts.get(`disabled:${assetPaths.style}`) || 0, 0);
    assert.equal(counts.get('disabled:/api/features'), 1);

    assert.deepEqual(results.locked.hidden, [false, false]);
    assert.deepEqual(results.locked.locked, [true, true]);
    assert.deepEqual(results.locked.labels, ['Code — Professional plan', 'Code — Professional plan']);
    assert.equal(results.locked.loader && results.locked.workspace && results.locked.shell, true);
    assert.equal(results.locked.bootstrapStatusRetained, false);
    assert.equal(counts.get(`locked:${assetPaths.script}`), 1);
    assert.equal(counts.get(`locked:${assetPaths.style}`), 1);
    assert.equal(counts.get('locked:/api/features'), 1);

    assert.deepEqual(results.entitled.hidden, [false, false]);
    assert.deepEqual(results.entitled.locked, [false, false]);
    assert.deepEqual(results.entitled.labels, ['Code', 'Code']);
    assert.equal(results.entitled.loader && results.entitled.workspace && results.entitled.shell, true);
    assert.equal(results.entitled.bootstrapStatusRetained, false);
    assert.equal(counts.get(`entitled:${assetPaths.script}`), 1);
    assert.equal(counts.get(`entitled:${assetPaths.style}`), 1);
    assert.equal(counts.get('entitled:/api/features'), 1);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({results, requests: Object.fromEntries(counts), errors}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
