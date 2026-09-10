const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const publicDirectory = path.resolve(process.cwd(), 'public');
const runtimePath = '/runtime-body-v1.js';
const runtimeUrl = `${runtimePath}?v=5.9.76-checkout-session-recovery-1`;
const fixturePath = '/__returning-load.html';
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
});

function fixtureHtml() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <link rel="icon" href="data:,">
  <title>Returning workspace load proof</title>
</head>
<body>
  <main>Returning workspace load proof</main>
  <script src="${runtimeUrl}"></script>
  <script>
    navigator.serviceWorker.register('/sw.js', {scope: '/'}).catch(error => {
      document.documentElement.dataset.registrationError = error.message;
    });
  </script>
</body>
</html>`;
}

function safePublicPath(pathname) {
  const requested = pathname === '/app' ? '/app.html' : pathname;
  const relative = requested.replace(/^\/+/, '');
  const resolved = path.resolve(publicDirectory, relative);
  return resolved.startsWith(`${publicDirectory}${path.sep}`) ? resolved : null;
}

async function startServer() {
  const counts = new Map();
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    counts.set(url.pathname, (counts.get(url.pathname) || 0) + 1);
    response.setHeader('Cache-Control', 'no-store');

    if (url.pathname === fixturePath) {
      response.writeHead(200, {'Content-Type': contentTypes['.html']});
      response.end(fixtureHtml());
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
  return {server, counts, port: server.address().port};
}

(async () => {
  const {server, counts, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const context = await browser.newContext({serviceWorkers: 'allow'});
    const page = await context.newPage();
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    const destination = `http://127.0.0.1:${port}${fixturePath}`;

    await page.goto(destination, {waitUntil: 'load'});
    await page.evaluate(() => navigator.serviceWorker.ready);
    if (!await page.evaluate(() => Boolean(navigator.serviceWorker.controller))) {
      await page.reload({waitUntil: 'load'});
    }
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
    assert.equal(await page.evaluate(() => Boolean(window.CrumpWorkspaceRuntime)), true);

    counts.clear();
    await page.reload({waitUntil: 'load'});
    await page.waitForFunction(() => Boolean(window.CrumpWorkspaceRuntime));

    const originRuntimeRequests = counts.get(runtimePath) || 0;
    assert.equal(
      originRuntimeRequests,
      0,
      `returning controlled load re-requested ${runtimePath} from the origin`,
    );
    assert.equal(counts.get(fixturePath), 1, 'the HTML shell should still revalidate on return');
    assert.deepEqual(errors, []);
    process.stdout.write(JSON.stringify({originRuntimeRequests, shellRequests: counts.get(fixturePath), errors}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
