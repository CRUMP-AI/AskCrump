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

const selectorFor = (surface, format) => surface === 'project'
  ? `[data-crump53-export="${format}"]`
  : `[data-crump57-export-format="${format}"]`;

async function snapshot(page) {
  return page.evaluate(() => ({
    requests: window.fixtureExportRequests.map(item => ({
      format: item.format,
      method: item.method,
      path: item.path,
      hasSignal: Boolean(item.signal),
      aborted: item.aborted,
    })),
    handoffs: window.fixtureFileHandoffs.map(item => ({
      download: item.download,
      id: item.file?.id || '',
      url: item.file?.url || '',
    })),
    fallbacks: window.fixtureFallbackDownloads.map(item => ({...item})),
    toasts: window.fixtureToasts.map(item => ({...item})),
    windowOpenCalls: window.fixtureWindowOpenCalls.length,
    unexpectedRequests: [...window.fixtureUnexpectedRequests],
    deferredPrivateRequests: window.fixtureDeferredPrivateRequests.map(item => ({
      key: item.key,
      hasSignal: Boolean(item.signal),
      aborted: item.aborted,
      resolved: item.resolved,
    })),
    signedRequests: window.fixtureSignedRequests.map(item => ({
      path: item.path,
      userId: item.userId,
      hasSignal: Boolean(item.signal),
      aborted: item.aborted,
    })),
    projectStatus: document.getElementById('crump53ManuscriptStatus')?.textContent || '',
    projectStatusError: document.getElementById('crump53ManuscriptStatus')?.classList.contains('is-error') || false,
    libraryStatus: document.getElementById('crump57ExportStatus')?.textContent || '',
    libraryStatusError: document.getElementById('crump57ExportStatus')?.classList.contains('is-error') || false,
    controls: Array.from(document.querySelectorAll('[data-crump53-export], [data-crump53-run-output], [data-crump57-export-format]')).map(button => ({
      surface: button.hasAttribute('data-crump57-export-format') ? 'library' : 'project',
      format: button.dataset.crump53Export || button.dataset.crump57ExportFormat || 'saved-output',
      html: button.innerHTML,
      disabled: button.disabled,
      busy: button.getAttribute('aria-busy'),
    })),
    savedOutput: (() => {
      const button = document.querySelector('[data-crump53-run-output]');
      return button ? {
        html: button.innerHTML,
        disabled: button.disabled,
        busy: button.getAttribute('aria-busy'),
      } : null;
    })(),
    manuscriptRunText: document.getElementById('crump53ManuscriptRun')?.textContent || '',
    rawOutputLinks: Array.from(document.querySelectorAll('#crump53ManuscriptRun a[href]')).map(link => link.href),
    run: window.__crumpManuscriptExportRun ? {
      token: window.__crumpManuscriptExportRun.token,
      userId: window.__crumpManuscriptExportRun.userId,
      surface: window.__crumpManuscriptExportRun.surface,
      aborted: window.__crumpManuscriptExportRun.controller.signal.aborted,
      keys: Object.keys(window.__crumpManuscriptExportRun).sort(),
    } : null,
    libraryModal: Boolean(document.querySelector('.crump57-download-sheet')),
    libraryShelfText: document.getElementById('crump57Bookshelf')?.textContent || '',
    activeElement: {
      tag: document.activeElement?.tagName || '',
      id: document.activeElement?.id || '',
      className: document.activeElement?.className || '',
      exportFormat: document.activeElement?.dataset?.crump57ExportFormat || '',
      downloadBook: document.activeElement?.dataset?.crump57Download || '',
      moreBook: document.activeElement?.closest?.('[data-crump57-book]')?.dataset?.crump57Book || '',
    },
    manuscriptDom: {
      workspaceHidden: document.getElementById('crump53ManuscriptWorkspace')?.hidden,
      createHidden: document.getElementById('crump53ManuscriptCreate')?.hidden,
      editorHidden: document.getElementById('crump53ManuscriptEditor')?.hidden,
      sectionEditorHidden: document.getElementById('crump53SectionEditor')?.hidden,
      runHidden: document.getElementById('crump53ManuscriptRun')?.hidden,
      editorTitle: document.getElementById('crump53EditorTitle')?.textContent || '',
      values: [
        'crump53ManuscriptTitle',
        'crump53ManuscriptAuthor',
        'crump53ManuscriptPremise',
        'crump53BlueprintBrief',
        'crump53SectionTitle',
        'crump53SectionContent',
        'crump53DraftInstruction',
      ].map(id => document.getElementById(id)?.value || ''),
      progress: document.getElementById('crump53ManuscriptProgress')?.textContent || '',
      sections: document.getElementById('crump53SectionList')?.textContent || '',
      list: document.getElementById('crump53ManuscriptList')?.textContent || '',
      run: document.getElementById('crump53ManuscriptRun')?.textContent || '',
    },
    libraryCoverSources: Array.from(document.querySelectorAll('#crump57Bookshelf img[src]')).map(image => image.src),
    href: location.href,
    fixtureErrors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
  }));
}

async function loadFixture(page, fixtureUrl) {
  await page.goto(fixtureUrl, {waitUntil: 'load'});
  await page.waitForFunction(() => document.getElementById('fixtureReady')?.textContent === 'ready');
  await page.waitForFunction(() => document.querySelectorAll('[data-crump53-export]').length === 3);
}

async function closeLibraryModal(page) {
  const close = page.locator('.crump57-download-sheet .crump57-close');
  if (await close.count()) await close.click();
}

async function reset(page) {
  await closeLibraryModal(page);
  await page.evaluate(() => window.fixtureResetExportEvidence());
}

async function openLibrary(page) {
  await page.evaluate(() => window.fixtureOpenLibraryDownload());
  await page.waitForFunction(() => document.querySelectorAll('[data-crump57-export-format]').length === 3);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function openLibraryReader(page) {
  await page.evaluate(() => window.fixtureOpenLibraryReader());
  await page.waitForFunction(() => Boolean(document.querySelector('.crump57-reader-download')));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function readerMenuState(page) {
  return page.evaluate(() => {
    const details = document.querySelector('.crump57-reader-download');
    const summary = details?.querySelector('summary');
    return {
      open: Boolean(details?.open),
      summaryFocused: document.activeElement === summary,
      activeFormat: document.activeElement?.dataset?.crump57ExportFormat || '',
    };
  });
}

async function waitIdle(page) {
  await page.waitForFunction(() => !window.__crumpManuscriptExportRun);
}

async function clickExport(page, surface, format) {
  await page.evaluate(selector => {
    const button = document.querySelector(selector);
    if (!button) throw new Error(`Missing export control: ${selector}`);
    button.focus({preventScroll: true});
    button.click();
  }, selectorFor(surface, format));
  await waitIdle(page);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function trackedControlState(page, expression = 'window.fixtureTrackedControls') {
  return page.evaluate(source => (0, eval)(source).map(button => ({
    html: button.innerHTML,
    disabled: button.disabled,
    busy: button.getAttribute('aria-busy'),
    connected: button.isConnected,
  })), expression);
}

async function verifyNativeFileToolOwnershipBoundary(browser, baseUrl, browserErrors, results) {
  const context = await browser.newContext({viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const pending = [];
  const waiters = [];
  const takePending = () => pending.length
    ? Promise.resolve(pending.shift())
    : new Promise(resolve => waiters.push(resolve));
  const enqueue = value => {
    const waiter = waiters.shift();
    if (waiter) waiter(value);
    else pending.push(value);
  };
  const release = async (item, fileId) => {
    try {
      await item.route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          url: `https://fixture.invalid/native/${fileId}?token=stale`,
        }),
      });
    } catch (_) {
      // AbortSignal may cancel the request before the delayed route is released.
    } finally {
      item.done();
    }
  };

  try {
    await page.addInitScript(() => { window.CrumpAPI = {isNative: true}; });
    await context.route('**/api/files/*/signed?download=1', route => new Promise(done => {
      enqueue({route, done});
    }));
    page.on('console', message => { if (message.type() === 'error') browserErrors.push(`native-owner: ${message.text()}`); });
    page.on('pageerror', error => browserErrors.push(`native-owner: ${error.message}`));
    await page.goto(`${baseUrl}/tests/fixtures/file-delivery.html`, {waitUntil: 'load'});
    await page.waitForFunction(() => typeof window.CrumpFileTools?.open === 'function');

    const start = fileId => page.evaluate(id => {
      window.fixtureNativeOwner = true;
      window.fixtureNativeController = new AbortController();
      window.fixtureNativeDeliveryPromise = window.CrumpFileTools.open({
        id,
        name: 'Private manuscript.docx',
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      }, true, {
        signal: window.fixtureNativeController.signal,
        shouldProceed: () => window.fixtureNativeOwner === true,
      });
    }, fileId);

    const abortedId = '00000000-0000-4000-8000-000000000187';
    await start(abortedId);
    let delayed = await takePending();
    await page.evaluate(() => {
      window.fixtureNativeOwner = false;
      window.fixtureNativeController.abort();
    });
    await release(delayed, abortedId);
    assert.equal(await page.evaluate(() => window.fixtureNativeDeliveryPromise), false);
    assert.deepEqual(await page.evaluate(() => window.__fixture.downloads), []);
    results.accountSwitches.push('native:signed-fetch-abort');

    const guardedId = '00000000-0000-4000-8000-000000000188';
    await start(guardedId);
    delayed = await takePending();
    await page.evaluate(() => { window.fixtureNativeOwner = false; });
    await release(delayed, guardedId);
    assert.equal(await page.evaluate(() => window.fixtureNativeDeliveryPromise), false);
    assert.deepEqual(await page.evaluate(() => window.__fixture.downloads), []);
    results.accountSwitches.push('native:late-owner-guard');
  } finally {
    await context.close();
  }
}

(async () => {
  const {server, baseUrl} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE
    || process.env.CODEX_BROWSER_EXECUTABLE
    || undefined;
  let browser;
  const browserErrors = [];
  const popupUrls = [];
  const results = {success: [], fallbacks: [], failures: [], duplicates: [], focus: [], accountSwitches: [], resourceSwitches: []};

  try {
    browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
    const page = await browser.newPage({viewport: {width: 1280, height: 800}});
    page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('popup', popup => popupUrls.push(popup.url()));
    const fixtureUrl = `${baseUrl}/tests/fixtures/manuscript-export-delivery.html`;
    const manuscriptId = '00000000-0000-4000-8000-000000000182';
    await loadFixture(page, fixtureUrl);

    for (const surface of ['project', 'library']) {
      for (const format of ['docx', 'pdf', 'epub']) {
        await reset(page);
        if (surface === 'library') await openLibrary(page);
        await page.evaluate(() => {
          window.fixtureTrackedControls = Array.from(document.querySelectorAll('[data-crump53-export], [data-crump57-export-format]'));
          window.fixtureTrackedBaseline = window.fixtureTrackedControls.map(button => ({
            html: button.innerHTML,
            disabled: button.disabled,
            busy: button.getAttribute('aria-busy'),
          }));
        });
        await clickExport(page, surface, format);
        const result = await snapshot(page);
        assert.deepEqual(result.requests, [{
          format, method: 'POST', path: `/api/manuscripts/${manuscriptId}/export`, hasSignal: true, aborted: false,
        }], JSON.stringify(result));
        assert.equal(result.handoffs.length, 1, JSON.stringify(result));
        assert.equal(result.handoffs[0].download, true);
        assert.match(result.handoffs[0].id, /^[0-9a-f-]{36}$/i);
        assert.equal(result.handoffs[0].url, '', 'canonical delivery must not receive a raw storage URL');
        assert.deepEqual(result.fallbacks, []);
        assert.equal(result.windowOpenCalls, 0);
        assert.deepEqual(result.unexpectedRequests, []);
        assert.equal(result.href, fixtureUrl);
        assert.equal(result.fixtureErrors, 0);
        if (surface === 'library') {
          assert.equal(result.libraryModal, false);
          assert.equal(result.activeElement.tag, 'SUMMARY', JSON.stringify(result.activeElement));
          assert.equal(result.activeElement.moreBook, manuscriptId, JSON.stringify(result.activeElement));
        }
        const restored = await trackedControlState(page);
        const baseline = await page.evaluate(() => window.fixtureTrackedBaseline);
        assert.deepEqual(restored.map(({html, disabled, busy}) => ({html, disabled, busy})), baseline);
        results.success.push(`${surface}:${format}`);
      }
    }

    await reset(page);
    await openLibraryReader(page);
    await page.locator('.crump57-reader-download summary').click();
    await clickExport(page, 'library', 'docx');
    assert.deepEqual(await readerMenuState(page), {open: false, summaryFocused: true, activeFormat: ''});
    results.focus.push('reader:success-summary');

    await reset(page);
    await openLibraryReader(page);
    await page.locator('.crump57-reader-download summary').click();
    await page.evaluate(() => { window.fixtureExportMode = 'failure'; });
    await clickExport(page, 'library', 'pdf');
    assert.deepEqual(await readerMenuState(page), {open: true, summaryFocused: false, activeFormat: 'pdf'});
    results.focus.push('reader:failure-kept-open');

    await reset(page);
    await page.evaluate(() => {
      window.fixtureExportMode = 'deferred';
      document.querySelector('[data-crump53-export="epub"]').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredExports.length === 1);
    await openLibraryReader(page);
    await page.locator('.crump57-reader-download summary').click();
    await page.evaluate(() => {
      const button = document.querySelector('.crump57-reader-download [data-crump57-export-format="epub"]');
      button.focus({preventScroll: true});
      button.click();
    });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.deepEqual(await readerMenuState(page), {open: true, summaryFocused: false, activeFormat: 'epub'});
    assert.equal((await snapshot(page)).toasts.at(-1)?.message, 'Another manuscript export is already in progress.');
    await page.evaluate(() => window.fixtureResolveDeferredExport());
    await waitIdle(page);
    results.focus.push('reader:busy-kept-open');

    await reset(page);
    await page.evaluate(() => window.fixtureSetCanonicalMode('false'));
    await clickExport(page, 'project', 'docx');
    let result = await snapshot(page);
    assert.equal(result.handoffs.length, 1);
    assert.deepEqual(result.fallbacks, [{
      href: '/api/files/00000000-0000-4000-8000-000000000184/content?download=1',
      download: 'fixture-manuscript.docx',
    }]);
    results.fallbacks.push('project:false');

    await reset(page);
    await openLibrary(page);
    await page.evaluate(() => window.fixtureSetCanonicalMode('absent'));
    await clickExport(page, 'library', 'pdf');
    result = await snapshot(page);
    assert.deepEqual(result.handoffs, []);
    assert.deepEqual(result.fallbacks, [{
      href: '/api/files/00000000-0000-4000-8000-000000000185/content?download=1',
      download: 'fixture-manuscript.pdf',
    }]);
    results.fallbacks.push('library:absent');

    for (const surface of ['project', 'library']) {
      await reset(page);
      if (surface === 'library') await openLibrary(page);
      await page.evaluate(() => { window.fixtureExportMode = 'url-only'; });
      await clickExport(page, surface, 'epub');
      result = await snapshot(page);
      assert.deepEqual(result.handoffs, []);
      assert.deepEqual(result.fallbacks, []);
      const message = surface === 'project'
        ? result.projectStatus
        : result.toasts.at(-1)?.message || result.libraryStatus;
      assert.match(message, /Delivery could not be verified\. Check Files before trying again\./i);
      results.failures.push(`${surface}:url-only`);
    }

    for (const surface of ['project', 'library']) {
      await reset(page);
      if (surface === 'library') await openLibrary(page);
      await page.evaluate(currentSurface => {
        window.CrumpAPI.isNative = true;
        window.fixtureSetCanonicalMode(currentSurface === 'project' ? 'false' : 'absent');
      }, surface);
      await clickExport(page, surface, 'pdf');
      result = await snapshot(page);
      assert.deepEqual(result.fallbacks, []);
      const message = surface === 'project'
        ? result.projectStatus
        : result.toasts.at(-1)?.message || result.libraryStatus;
      assert.match(message, /Retry from Files/i);
      results.failures.push(`${surface}:native-fail-closed`);
    }

    for (const surface of ['project', 'library']) {
      for (const mode of ['failure', 'missing-file']) {
        await reset(page);
        if (surface === 'library') await openLibrary(page);
        await page.evaluate(nextMode => { window.fixtureExportMode = nextMode; }, mode);
        await clickExport(page, surface, 'pdf');
        result = await snapshot(page);
        assert.equal(result.requests.length, 1);
        assert.deepEqual(result.handoffs, []);
        assert.deepEqual(result.fallbacks, []);
        const message = surface === 'project'
          ? result.projectStatus
          : result.toasts.at(-1)?.message || result.libraryStatus;
        assert.match(message, mode === 'failure' ? /Fixture export request failed/ : /Delivery could not be verified|Check Files/i);
        results.failures.push(`${surface}:${mode}`);
      }
    }

    await reset(page);
    await openLibrary(page);
    result = await snapshot(page);
    assert.equal(result.activeElement.exportFormat, 'docx');
    await page.locator('.crump57-download-sheet .crump57-close').click();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    result = await snapshot(page);
    assert.equal(result.libraryModal, false);
    assert.equal(result.activeElement.tag, 'SUMMARY', JSON.stringify(result.activeElement));
    assert.equal(result.activeElement.moreBook, manuscriptId, JSON.stringify(result.activeElement));
    results.success.push('library:focus-lifecycle');

    await reset(page);
    await page.evaluate(() => {
      window.fixtureExportMode = 'deferred';
      document.querySelector('[data-crump53-export="docx"]').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredExports.length === 1);
    result = await snapshot(page);
    assert.deepEqual(result.run.keys, ['controller', 'surface', 'token', 'userId']);
    assert.equal(result.run.surface, 'project');
    await openLibrary(page);
    await page.evaluate(() => {
      document.querySelector('[data-crump57-export-format="pdf"]').dispatchEvent(new MouseEvent('click', {bubbles: true}));
      document.querySelector('[data-crump53-export="epub"]').dispatchEvent(new MouseEvent('click', {bubbles: true}));
    });
    result = await snapshot(page);
    assert.equal(result.requests.length, 1);
    assert.equal(result.toasts.at(-1)?.message, 'Another manuscript export is already in progress.');
    assert.equal(result.projectStatus, 'Another manuscript export is already in progress.');
    await page.evaluate(() => window.fixtureResolveDeferredExport());
    await waitIdle(page);
    result = await snapshot(page);
    assert.equal(result.requests.length, 1);
    assert.equal(result.handoffs.length, 1);
    results.duplicates.push('project-to-library');

    await reset(page);
    await openLibrary(page);
    await page.evaluate(() => {
      window.fixtureExportMode = 'deferred';
      document.querySelector('[data-crump57-export-format="docx"]').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredExports.length === 1);
    result = await snapshot(page);
    assert.equal(result.run.surface, 'library');
    await page.evaluate(() => {
      document.querySelector('[data-crump57-export-format="epub"]').dispatchEvent(new MouseEvent('click', {bubbles: true}));
      document.querySelector('[data-crump53-export="pdf"]').dispatchEvent(new MouseEvent('click', {bubbles: true}));
    });
    result = await snapshot(page);
    assert.equal(result.requests.length, 1);
    assert.equal(result.toasts.at(-1)?.message, 'Another manuscript export is already in progress.');
    assert.equal(result.projectStatus, 'Another manuscript export is already in progress.');
    await page.evaluate(() => window.fixtureResolveDeferredExport());
    await waitIdle(page);
    result = await snapshot(page);
    assert.equal(result.requests.length, 1);
    assert.equal(result.handoffs.length, 1);
    results.duplicates.push('library-to-project');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await openLibrary(page);
    const seededBaseline = await page.evaluate(() => {
      const projectPdf = document.querySelector('[data-crump53-export="pdf"]');
      const libraryEpub = document.querySelector('[data-crump57-export-format="epub"]');
      projectPdf.disabled = true;
      projectPdf.setAttribute('aria-busy', 'false');
      libraryEpub.disabled = true;
      libraryEpub.setAttribute('aria-busy', 'mixed');
      window.fixtureTrackedControls = Array.from(document.querySelectorAll('[data-crump53-export], [data-crump57-export-format]'));
      return window.fixtureTrackedControls.map(button => ({
        html: button.innerHTML, disabled: button.disabled, busy: button.getAttribute('aria-busy'),
      }));
    });
    await page.evaluate(() => {
      window.fixtureExportMode = 'failure';
      document.querySelector('[data-crump57-export-format="docx"]').click();
    });
    await waitIdle(page);
    assert.deepEqual(
      (await trackedControlState(page)).map(({html, disabled, busy}) => ({html, disabled, busy})),
      seededBaseline,
    );

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => {
      document.getElementById('crump53ManuscriptTitle').value = 'Account A private title';
      document.getElementById('crump53ManuscriptAuthor').value = 'Account A private author';
      document.getElementById('crump53ManuscriptPremise').value = 'Account A private premise';
      document.getElementById('crump53BlueprintBrief').value = 'Account A private blueprint';
      document.getElementById('crump53SectionTitle').value = 'Account A private section';
      document.getElementById('crump53SectionContent').value = 'Account A private content';
      document.getElementById('crump53DraftInstruction').value = 'Account A private direction';
      window.fixtureExportMode = 'deferred';
      document.querySelector('[data-crump53-export="docx"]').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredExports.length === 1);
    result = await snapshot(page);
    assert.equal(result.run.surface, 'project');
    assert.equal(result.run.userId, 'fixture-manuscript-export-user-a');
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.waitForFunction(() => !window.__crumpManuscriptExportRun);
    assert.equal((await snapshot(page)).requests[0].aborted, true);
    await page.evaluate(() => window.fixtureResolveDeferredExport());
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.deepEqual(result.handoffs, []);
    assert.deepEqual(result.fallbacks, []);
    assert.deepEqual(result.toasts, []);
    assert.equal(result.projectStatus, '');
    await page.evaluate(() => window.CrumpProduct53.openProject(window.fixtureProject.id));
    result = await snapshot(page);
    assert.equal(result.manuscriptDom.workspaceHidden, false);
    assert.equal(result.manuscriptDom.createHidden, false);
    assert.equal(result.manuscriptDom.editorHidden, true);
    assert.equal(result.manuscriptDom.sectionEditorHidden, true);
    assert.equal(result.manuscriptDom.runHidden, true);
    assert.equal(result.manuscriptDom.editorTitle, 'Manuscript');
    assert.deepEqual(result.manuscriptDom.values, ['', '', '', '', '', '', '']);
    assert.equal(result.manuscriptDom.progress, '');
    assert.equal(result.manuscriptDom.sections, '');
    assert.equal(result.projectStatus, '');
    results.accountSwitches.push('project:late-api');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await openLibrary(page);
    await page.evaluate(() => {
      window.fixtureExportMode = 'deferred';
      document.querySelector('[data-crump57-export-format="docx"]').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredExports.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.waitForFunction(() => !window.__crumpManuscriptExportRun);
    result = await snapshot(page);
    assert.equal(result.requests[0].aborted, true);
    assert.equal(result.libraryModal, false);
    assert.equal(result.libraryShelfText, '');
    await page.evaluate(() => window.fixtureResolveDeferredExport());
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.deepEqual(result.handoffs, []);
    assert.deepEqual(result.fallbacks, []);
    assert.deepEqual(result.toasts, []);
    results.accountSwitches.push('library:late-api');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => {
      window.fixtureSetCanonicalMode('deferred-false');
      document.querySelector('[data-crump53-export="epub"]').click();
    });
    await page.waitForFunction(() => Boolean(window.fixtureDeferredCanonical));
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.evaluate(() => window.fixtureResolveDeferredCanonical(false));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.equal(result.handoffs.length, 1, 'canonical handoff was attempted before the account switch');
    assert.deepEqual(result.fallbacks, [], 'a stale canonical false must not fall back after account switch');
    results.accountSwitches.push('project:late-canonical');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => {
      window.fixtureSetCanonicalMode('deferred-false');
      document.querySelector('[data-crump53-export="epub"]').click();
    });
    await page.waitForFunction(() => Boolean(window.fixtureDeferredCanonical));
    await page.evaluate(() => window.fixtureOpenProjectManuscriptB());
    await page.waitForFunction(() => document.getElementById('crump53EditorTitle')?.textContent === 'Fixture Manuscript B');
    await page.evaluate(() => window.fixtureResolveDeferredCanonical(false));
    await waitIdle(page);
    result = await snapshot(page);
    assert.equal(result.handoffs.length, 1, 'canonical handoff began while the original manuscript was active');
    assert.deepEqual(result.fallbacks, [], 'an export for manuscript A must not fall back after selecting manuscript B');
    assert.equal(result.manuscriptDom.editorTitle, 'Fixture Manuscript B');
    assert.notEqual(result.projectStatus, 'EPUB ready · 12,345 words · saved to Files.');
    results.resourceSwitches.push('project:late-canonical');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await openLibrary(page);
    await page.evaluate(() => {
      window.fixtureSetCanonicalMode('deferred-false');
      document.querySelector('[data-crump57-export-format="pdf"]').click();
    });
    await page.waitForFunction(() => Boolean(window.fixtureDeferredCanonical));
    await closeLibraryModal(page);
    await page.evaluate(() => window.fixtureResolveDeferredCanonical(false));
    await waitIdle(page);
    result = await snapshot(page);
    assert.equal(result.handoffs.length, 1, 'Library canonical handoff began before its originating modal closed');
    assert.deepEqual(result.fallbacks, [], 'a closed Library surface must not fall back or download');
    assert.deepEqual(result.toasts, []);
    results.resourceSwitches.push('library:closed-modal');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => window.fixtureSetManuscriptRunOutput({
      id: '00000000-0000-4000-8000-000000000189',
      name: 'saved-autopilot.docx',
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      url: 'https://fixture.supabase.co/storage/v1/object/sign/private/autopilot-docx',
    }, 'docx'));
    await page.waitForFunction(() => Boolean(document.querySelector('[data-crump53-run-output]')));
    const savedOutputBaseline = await page.evaluate(() => {
      const button = document.querySelector('[data-crump53-run-output]');
      return {html: button.innerHTML, disabled: button.disabled, busy: button.getAttribute('aria-busy')};
    });
    await page.locator('[data-crump53-run-output]').click();
    await waitIdle(page);
    result = await snapshot(page);
    assert.deepEqual(result.handoffs, [{
      download: true,
      id: '00000000-0000-4000-8000-000000000189',
      url: '',
    }]);
    assert.deepEqual(result.fallbacks, []);
    assert.deepEqual(result.rawOutputLinks, []);
    assert.deepEqual(result.savedOutput, savedOutputBaseline);
    assert.equal(result.projectStatus, 'Saved manuscript ready.');
    results.success.push('project:saved-output-id');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => window.fixtureSetManuscriptRunOutput({
      name: 'unsafe-url-only.docx',
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      url: 'https://fixture.supabase.co/storage/v1/object/sign/private/url-only-autopilot',
    }, 'docx'));
    await page.waitForFunction(() => /Delivery could not be verified/.test(document.getElementById('crump53ManuscriptRun')?.textContent || ''));
    result = await snapshot(page);
    assert.equal(result.savedOutput, null);
    assert.deepEqual(result.rawOutputLinks, []);
    assert.deepEqual(result.handoffs, []);
    assert.deepEqual(result.fallbacks, []);
    assert.match(result.manuscriptRunText, /Delivery could not be verified\. Check Files before trying again\./);
    results.failures.push('project:saved-output-url-only');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(async () => {
      window.CrumpAPI.isNative = true;
      window.fixtureSetCanonicalMode('deferred-false');
      await window.fixtureSetManuscriptRunOutput({
        id: '00000000-0000-4000-8000-000000000190',
        name: 'saved-native.pdf',
        type: 'application/pdf',
        url: 'https://fixture.supabase.co/storage/v1/object/sign/private/native-autopilot',
      }, 'pdf');
    });
    await page.waitForFunction(() => Boolean(document.querySelector('[data-crump53-run-output]')));
    const savedNativeBaseline = await page.evaluate(() => {
      const button = document.querySelector('[data-crump53-run-output]');
      return {html: button.innerHTML, disabled: button.disabled, busy: button.getAttribute('aria-busy')};
    });
    await page.locator('[data-crump53-run-output]').click();
    await page.waitForFunction(() => Boolean(window.fixtureDeferredCanonical));
    result = await snapshot(page);
    assert.equal(result.savedOutput.html, 'Preparing download…');
    assert.equal(result.savedOutput.disabled, true);
    assert.equal(result.savedOutput.busy, 'true');
    await page.evaluate(() => window.fixtureResolveDeferredCanonical(false));
    await waitIdle(page);
    result = await snapshot(page);
    assert.deepEqual(result.handoffs, [{
      download: true,
      id: '00000000-0000-4000-8000-000000000190',
      url: '',
    }]);
    assert.deepEqual(result.fallbacks, []);
    assert.match(result.projectStatus, /Retry from Files/i);
    assert.deepEqual(result.savedOutput, savedNativeBaseline);
    results.failures.push('project:saved-output-native-fail-closed');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(async () => {
      window.fixtureSetCanonicalMode('deferred-false');
      await window.fixtureSetManuscriptRunOutput({
        id: '00000000-0000-4000-8000-000000000191',
        name: 'saved-account-a.epub',
        type: 'application/epub+zip',
        url: 'https://fixture.supabase.co/storage/v1/object/sign/private/account-a-autopilot',
      }, 'epub');
      document.querySelector('[data-crump53-run-output]').click();
    });
    await page.waitForFunction(() => Boolean(window.fixtureDeferredCanonical));
    result = await snapshot(page);
    assert.equal(result.run.surface, 'project-run-output');
    assert.deepEqual(result.run.keys, ['controller', 'surface', 'token', 'userId']);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.waitForFunction(() => !window.__crumpManuscriptExportRun);
    await page.evaluate(() => window.fixtureResolveDeferredCanonical(false));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.equal(result.handoffs.length, 1, 'saved output canonical handoff began before account switch');
    assert.deepEqual(result.fallbacks, []);
    assert.equal(result.savedOutput, null);
    assert.equal(result.projectStatus, '');
    results.accountSwitches.push('project:saved-output-late-canonical');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(async () => {
      window.fixtureSetCanonicalMode('deferred-false');
      await window.fixtureSetManuscriptRunOutput({
        id: '00000000-0000-4000-8000-000000000196',
        name: 'saved-manuscript-a.epub',
        type: 'application/epub+zip',
        url: 'https://fixture.supabase.co/storage/v1/object/sign/private/manuscript-a-autopilot',
      }, 'epub');
      document.querySelector('[data-crump53-run-output]').click();
    });
    await page.waitForFunction(() => Boolean(window.fixtureDeferredCanonical));
    await page.evaluate(() => window.fixtureOpenProjectManuscriptB());
    await page.waitForFunction(() => document.getElementById('crump53EditorTitle')?.textContent === 'Fixture Manuscript B');
    await page.evaluate(() => window.fixtureResolveDeferredCanonical(false));
    await waitIdle(page);
    result = await snapshot(page);
    assert.equal(result.handoffs.length, 1, 'saved-output handoff began while manuscript A was active');
    assert.deepEqual(result.fallbacks, [], 'saved output for manuscript A must not fall back after selecting manuscript B');
    assert.equal(result.manuscriptDom.editorTitle, 'Fixture Manuscript B');
    assert.notEqual(result.projectStatus, 'Saved manuscript ready.');
    results.resourceSwitches.push('project:saved-output-late-canonical');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => {
      const path = `/api/projects/${window.fixtureProject.id}/manuscripts`;
      window.fixtureDelayNextRequest('GET', path);
      window.fixturePendingPrivateOperation = window.CrumpProduct53.openManuscript({
        projectId: window.fixtureProject.id,
        manuscriptId: window.fixtureManuscript.id,
        autoOpen: true,
      });
    });
    await page.waitForFunction(() => window.fixtureDeferredPrivateRequests.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    result = await snapshot(page);
    assert.equal(result.deferredPrivateRequests[0].hasSignal, true);
    assert.equal(result.deferredPrivateRequests[0].aborted, true);
    await page.evaluate(() => window.fixtureResolvePrivateRequest(0, {
      success: true,
      manuscripts: [{...window.fixtureManuscript, title: 'Account A private list title'}],
    }));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.doesNotMatch(result.manuscriptDom.list, /Account A private list title/);
    assert.equal(result.projectStatus, '');
    results.accountSwitches.push('project:late-list');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => {
      const path = `/api/manuscripts/${window.fixtureManuscript.id}`;
      window.fixtureDelayNextRequest('GET', path);
      window.fixturePendingPrivateOperation = window.CrumpProduct53.openManuscript({
        projectId: window.fixtureProject.id,
        manuscriptId: window.fixtureManuscript.id,
        autoOpen: true,
      });
    });
    await page.waitForFunction(() => window.fixtureDeferredPrivateRequests.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.evaluate(() => window.fixtureResolvePrivateRequest(0, {
      success: true,
      manuscript: {
        ...window.fixtureManuscript,
        title: 'Account A private loaded title',
        metadata: {premise: 'Account A private loaded premise', targetWords: 80000, plannedChapterCount: 1},
      },
      sections: [{...window.fixtureManuscript, id: '00000000-0000-4000-8000-000000000183', title: 'Account A private loaded section', content: 'Account A private loaded content'}],
      progress: {wordCount: 99, targetWords: 80000},
      run: {id: 'private-a-run', status: 'completed', stage: 'complete', error: 'Account A private run error'},
    }));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.equal(result.deferredPrivateRequests[0].aborted, true);
    assert.doesNotMatch(JSON.stringify(result.manuscriptDom), /Account A private loaded/);
    assert.equal(result.projectStatus, '');
    results.accountSwitches.push('project:late-load');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(async () => {
      window.fixtureSetManuscriptRun({
        id: '00000000-0000-4000-8000-000000000192',
        status: 'running',
        stage: 'drafting',
        totalSections: 1,
        completedSections: 0,
      });
      window.fixtureDelayNextRequest('GET', `/api/manuscripts/${window.fixtureManuscript.id}/run`);
      await window.CrumpProduct53.openManuscript({
        projectId: window.fixtureProject.id,
        manuscriptId: window.fixtureManuscript.id,
        autoOpen: true,
      });
    });
    await page.waitForFunction(() => window.fixtureDeferredPrivateRequests.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.evaluate(() => window.fixtureResolvePrivateRequest(0, {
      success: true,
      run: {
        id: '00000000-0000-4000-8000-000000000192',
        status: 'completed',
        stage: 'complete',
        error: 'Account A private late poll',
      },
    }));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.equal(result.deferredPrivateRequests[0].aborted, true);
    assert.equal(result.manuscriptDom.run, '');
    assert.equal(result.manuscriptDom.runHidden, true);
    assert.equal(result.projectStatus, '');
    results.accountSwitches.push('project:late-poll');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.locator('[data-section-id]').first().click();
    await page.evaluate(() => {
      document.getElementById('crump53DraftInstruction').value = 'Account A private draft direction';
      const path = `/api/manuscripts/${window.fixtureManuscript.id}/sections/00000000-0000-4000-8000-000000000183/draft`;
      window.fixtureDelayNextRequest('POST', path);
      document.getElementById('crump53DraftSection').click();
    });
    await page.waitForFunction(() => window.fixtureDeferredPrivateRequests.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    await page.evaluate(() => window.fixtureResolvePrivateRequest(0, {
      success: true,
      section: {
        id: '00000000-0000-4000-8000-000000000183',
        title: 'Account A private late draft title',
        content: 'Account A private late draft content',
        word_count: 6,
      },
      progress: {wordCount: 6, targetWords: 80000, wordProgress: 0, draftedSections: 1, plannedSections: 1},
    }));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.equal(result.deferredPrivateRequests[0].aborted, true);
    assert.doesNotMatch(JSON.stringify(result.manuscriptDom), /Account A private (draft direction|late draft)/);
    assert.equal(result.projectStatus, '');
    results.accountSwitches.push('project:late-draft');

    await loadFixture(page, fixtureUrl);
    await reset(page);
    await page.evaluate(() => {
      const coverId = '00000000-0000-4000-8000-000000000193';
      window.fixtureSetCover({id: coverId, name: 'Account A private cover.webp', type: 'image/webp'});
      window.fixtureDelayNextRequest('GET', `/api/files/${coverId}/signed`);
      window.fixturePendingPrivateOperation = window.CrumpLibrary57.refresh();
    });
    await page.waitForFunction(() => window.fixtureDeferredPrivateRequests.length === 1);
    await page.evaluate(() => window.fixtureSwitchAccount('fixture-manuscript-export-user-b'));
    result = await snapshot(page);
    assert.equal(result.signedRequests[0].hasSignal, true);
    assert.equal(result.signedRequests[0].aborted, true);
    await page.evaluate(() => window.fixtureResolvePrivateRequest(0, {
      success: true,
      url: 'https://fixture.supabase.co/private/account-a/cover.webp',
      expiresIn: 1200,
    }));
    await page.waitForTimeout(25);
    result = await snapshot(page);
    assert.equal(result.libraryShelfText, '');
    assert.deepEqual(result.libraryCoverSources, []);
    await page.evaluate(() => window.CrumpLibrary57.refresh());
    await page.waitForFunction(() => window.fixtureSignedRequests.length === 2);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('#crump57Bookshelf img[src]')).some(image => image.src.includes('fixture-manuscript-export-user-b')));
    result = await snapshot(page);
    assert.equal(result.signedRequests[1].userId, 'fixture-manuscript-export-user-b');
    assert.equal(result.signedRequests[1].hasSignal, true);
    assert.deepEqual(result.libraryCoverSources, ['https://fixture.supabase.co/private/fixture-manuscript-export-user-b/cover.webp']);
    results.accountSwitches.push('library:late-cover-sign');

    await verifyNativeFileToolOwnershipBoundary(browser, baseUrl, browserErrors, results);

    assert.deepEqual(browserErrors, []);
    assert.deepEqual(popupUrls, []);
    process.stdout.write(`${JSON.stringify(results)}\n`);
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
