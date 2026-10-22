const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const mime = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
]);

function startServer() {
  const server = http.createServer((request, response) => {
    const requestUrl = new URL(request.url || '/', 'http://127.0.0.1');
    const relative = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, '');
    const target = path.resolve(root, relative || 'tests/fixtures/manuscript-export-delivery.html');
    if (target !== root && !target.startsWith(`${root}${path.sep}`)) {
      response.writeHead(403).end('Forbidden');
      return;
    }
    fs.readFile(target, (error, data) => {
      if (error) {
        response.writeHead(error.code === 'ENOENT' ? 404 : 500).end('Not found');
        return;
      }
      response.writeHead(200, {'Content-Type': mime.get(path.extname(target)) || 'application/octet-stream'});
      response.end(data);
    });
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      resolve({server, baseUrl: `http://127.0.0.1:${address.port}`});
    });
  });
}

async function waitForRestoredControls(page) {
  await page.waitForFunction(() => Array.from(document.querySelectorAll('[data-crump53-export]')).every(button => (
    !button.disabled && !button.hasAttribute('aria-busy')
  )));
}

async function snapshot(page) {
  return page.evaluate(() => ({
    requests: window.fixtureExportRequests.map(item => ({...item})),
    handoffs: window.fixtureFileHandoffs.map(item => ({
      download: item.download,
      id: item.file?.id || '',
      url: item.file?.url || '',
    })),
    windowOpenCalls: window.fixtureWindowOpenCalls.length,
    unexpectedRequests: [...window.fixtureUnexpectedRequests],
    status: document.getElementById('crump53ManuscriptStatus')?.textContent || '',
    statusError: document.getElementById('crump53ManuscriptStatus')?.classList.contains('is-error') || false,
    controls: Array.from(document.querySelectorAll('[data-crump53-export]')).map(button => ({
      format: button.dataset.crump53Export,
      label: button.textContent,
      disabled: button.disabled,
      busy: button.getAttribute('aria-busy'),
    })),
    href: location.href,
    fixtureErrors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
  }));
}

(async () => {
  const {server, baseUrl} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE
    || process.env.CODEX_BROWSER_EXECUTABLE
    || undefined;
  let browser;
  const browserErrors = [];
  const popupUrls = [];

  try {
    browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
    const page = await browser.newPage({viewport: {width: 1280, height: 800}});
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });
    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('popup', popup => popupUrls.push(popup.url()));
    const fixtureUrl = `${baseUrl}/tests/fixtures/manuscript-export-delivery.html`;
    await page.goto(fixtureUrl, {waitUntil: 'load'});
    await page.waitForFunction(() => document.getElementById('fixtureReady')?.textContent === 'ready');
    await page.waitForFunction(() => document.querySelectorAll('[data-crump53-export]').length === 3);

    const formats = [];
    for (const format of ['docx', 'pdf', 'epub']) {
      await page.evaluate(() => window.fixtureResetExportEvidence());
      await page.locator(`[data-crump53-export="${format}"]`).click();
      await waitForRestoredControls(page);
      const result = await snapshot(page);
      assert.equal(result.requests.length, 1, JSON.stringify(result));
      assert.deepEqual(result.requests[0], {
        format,
        method: 'POST',
        path: `/api/manuscripts/${await page.evaluate(() => window.fixtureManuscript.id)}/export`,
      });
      assert.equal(result.handoffs.length, 1, JSON.stringify(result));
      assert.equal(result.handoffs[0].download, true);
      assert.match(result.handoffs[0].id, /^[0-9a-f-]{36}$/i);
      assert.match(result.handoffs[0].url, /^https:\/\/fixture\.supabase\.co\//);
      assert.equal(result.windowOpenCalls, 0);
      assert.deepEqual(result.unexpectedRequests, []);
      assert.equal(result.href, fixtureUrl);
      assert.match(result.status, new RegExp(`^${format.toUpperCase()} ready`));
      assert.equal(result.statusError, false);
      assert.equal(result.fixtureErrors, 0);
      assert.deepEqual(result.controls, [
        {format: 'docx', label: 'KDP DOCX', disabled: false, busy: null},
        {format: 'pdf', label: 'KDP PDF', disabled: false, busy: null},
        {format: 'epub', label: 'Kindle EPUB', disabled: false, busy: null},
      ]);
      formats.push({format, requests: result.requests.length, handoffs: result.handoffs.length});
    }

    await page.evaluate(() => {
      window.fixtureResetExportEvidence();
      window.fixtureExportMode = 'deferred';
      const button = document.querySelector('[data-crump53-export="docx"]');
      button.dispatchEvent(new MouseEvent('click', {bubbles: true}));
      button.dispatchEvent(new MouseEvent('click', {bubbles: true}));
    });
    await page.waitForFunction(() => window.fixtureExportRequests.length === 1 && window.fixtureDeferredExport);
    const rapidPending = await snapshot(page);
    assert.equal(rapidPending.requests.length, 1);
    assert.equal(rapidPending.handoffs.length, 0);
    assert.equal(rapidPending.controls.every(control => control.disabled), true);
    assert.deepEqual(rapidPending.controls.find(control => control.format === 'docx'), {
      format: 'docx', label: 'Building DOCX…', disabled: true, busy: 'true',
    });
    await page.evaluate(() => window.fixtureResolveDeferredExport());
    await waitForRestoredControls(page);
    const rapidComplete = await snapshot(page);
    assert.equal(rapidComplete.requests.length, 1);
    assert.equal(rapidComplete.handoffs.length, 1);
    assert.equal(rapidComplete.windowOpenCalls, 0);
    assert.equal(rapidComplete.href, fixtureUrl);

    const failures = [];
    for (const failure of [
      {mode: 'missing-file', message: 'did not return a downloadable file'},
      {mode: 'failure', message: 'Fixture export request failed.'},
    ]) {
      await page.evaluate(mode => {
        window.fixtureResetExportEvidence();
        window.fixtureExportMode = mode;
      }, failure.mode);
      await page.locator('[data-crump53-export="pdf"]').click();
      await waitForRestoredControls(page);
      const result = await snapshot(page);
      assert.equal(result.requests.length, 1, JSON.stringify(result));
      assert.equal(result.handoffs.length, 0);
      assert.equal(result.windowOpenCalls, 0);
      assert.deepEqual(result.unexpectedRequests, []);
      assert.equal(result.href, fixtureUrl);
      assert.match(result.status, new RegExp(failure.message.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
      assert.equal(result.statusError, true);
      assert.equal(result.fixtureErrors, 0);
      assert.equal(result.controls.every(control => !control.disabled && control.busy === null), true);
      failures.push({mode: failure.mode, status: result.status});
    }

    assert.deepEqual(browserErrors, []);
    assert.deepEqual(popupUrls, []);
    process.stdout.write(`${JSON.stringify({formats, rapidRepeat: rapidComplete.requests.length, failures})}\n`);
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
