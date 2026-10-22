const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const fixturePath = '/tests/fixtures/library-crud-privacy.html';
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

async function boot(page, port) {
  await page.goto(`http://127.0.0.1:${port}${fixturePath}`, {waitUntil: 'load'});
  await page.waitForFunction(() => document.getElementById('fixtureReady')?.textContent === 'ready');
  await page.evaluate(async () => {
    window.fixtureSetBooks([window.fixtureBooks.a, window.fixtureBooks.b]);
    window.fixtureSetDeletedBooks([window.fixtureBooks.deletedA, window.fixtureBooks.deletedB]);
    window.fixtureSetProjects([window.fixtureProjects.a, window.fixtureProjects.b]);
    await window.fixtureRefresh();
  });
  await page.waitForFunction(() => document.querySelectorAll('[data-crump57-book]').length === 2);
}

async function requestEvidence(page, key) {
  return page.evaluate(value => window.fixtureRequestEvidence(value), key);
}

async function snapshot(page) {
  return page.evaluate(() => window.fixtureSnapshot());
}

async function click(page, selector) {
  await page.evaluate(value => window.fixtureClick(value), selector);
}

async function settle(page) {
  await page.waitForTimeout(35);
}

function assertFencedRequest(records, label, {aborted = true} = {}) {
  assert.ok(records.length > 0, `${label} did not reach the production request path`);
  assert.equal(records.at(-1).hasSignal, true, `${label} did not carry an AbortSignal`);
  assert.equal(records.at(-1).aborted, aborted, `${label} had the wrong abort state`);
}

async function staleReaderScenario(page, port, outcome) {
  await boot(page, port);
  await page.evaluate(() => {
    window.fixturePlan('reader:book-a');
    window.fixtureClick('[data-crump57-open="book-a"]');
  });
  await page.waitForFunction(() => window.fixtureDeferredCount('reader:book-a') === 1);
  await page.evaluate(() => window.fixtureSwitchAccount(window.fixtureUsers.b));
  if (outcome === 'resolve') {
    await page.evaluate(() => window.fixtureResolve('reader:book-a'));
  } else {
    await page.evaluate(() => window.fixtureReject('reader:book-a', 0, 'Private reader A failed.'));
  }
  await settle(page);
  assertFencedRequest(await requestEvidence(page, 'reader:book-a'), `reader A ${outcome}`);
  const result = await snapshot(page);
  assert.equal(result.overlayHtml, '', `reader A ${outcome} mutated a post-switch overlay`);
  assert.deepEqual(result.toasts, [], `reader A ${outcome} emitted a stale toast`);
  assert.deepEqual(result.navigations, [], `reader A ${outcome} navigated after A→B`);
  assert.doesNotMatch(await page.locator('body').textContent(), /Private content for book-a|Private reader A failed/);
}

(async () => {
  const {server, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const browserErrors = [];
  try {
    const page = await browser.newPage();
    page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
    page.on('pageerror', error => browserErrors.push(error.message));

    await staleReaderScenario(page, port, 'resolve');
    await staleReaderScenario(page, port, 'reject');

    // Same-account reader success and visible error/retry remain functional.
    await boot(page, port);
    await click(page, '[data-crump57-open="book-a"]');
    await page.waitForSelector('.crump57-reader');
    assert.match(await page.locator('.crump57-reader').textContent(), /Private content for book-a/);
    assertFencedRequest(await requestEvidence(page, 'reader:book-a'), 'active reader success', {aborted: false});
    await click(page, '.crump57-close');
    await page.evaluate(() => {
      window.fixturePlan('reader:book-a');
      window.fixtureClick('[data-crump57-open="book-a"]');
    });
    await page.waitForFunction(() => window.fixtureDeferredCount('reader:book-a') === 1);
    await page.evaluate(() => window.fixtureResolve('reader:book-a', 0, {success: false, error: 'Reader retry fixture.'}, 500));
    await page.waitForFunction(() => document.querySelector('.crump57-reader-loading')?.textContent.includes('Reader retry fixture.'));
    assert.match(await page.locator('.crump57-reader-loading').textContent(), /Book could not open.*Reader retry fixture/s);
    await click(page, '.crump57-close');
    await click(page, '[data-crump57-open="book-a"]');
    await page.waitForSelector('.crump57-reader');
    assert.match(await page.locator('.crump57-reader').textContent(), /Private content for book-a/);

    // Preview A's deferred cover must never bind its open action onto Preview B.
    await boot(page, port);
    await page.evaluate(() => {
      window.fixtureSetBooks(window.fixtureCoveredBooks());
      window.fixturePlan('signed:front-cover-book-a', 2);
      void window.fixtureRefresh();
    });
    await page.waitForFunction(() => window.fixtureDeferredCount('signed:front-cover-book-a') === 1);
    await click(page, '[data-crump57-preview="book-a"]');
    await page.waitForFunction(() => window.fixtureDeferredCount('signed:front-cover-book-a') === 2);
    await click(page, '[data-crump57-preview="book-b"]');
    await page.waitForFunction(() => document.querySelector('.crump57-preview-sheet h3')?.textContent === 'Book B');
    const previewB = await snapshot(page);
    await page.evaluate(() => {
      window.fixtureResolve('signed:front-cover-book-a', 1);
      window.fixtureResolve('signed:front-cover-book-a', 0);
    });
    await settle(page);
    const previewAfterA = await snapshot(page);
    assert.equal(previewAfterA.overlayHtml, previewB.overlayHtml, 'stale Preview A mutated Preview B');
    assertFencedRequest(await requestEvidence(page, 'signed:front-cover-book-a'), 'preview A cover');
    await click(page, '#crump57PreviewOpen');
    await settle(page);
    assert.deepEqual((await snapshot(page)).navigations.map(item => item.manuscriptId), ['book-b'], 'Preview B opened the stale Preview A manuscript');

    // An import whose Project refresh crosses A→B must never mount.
    await boot(page, port);
    await page.evaluate(() => {
      window.fixturePlan('projects');
      void window.fixtureOpenImport();
    });
    await page.waitForFunction(() => window.fixtureDeferredCount('projects') === 1);
    await page.evaluate(() => {
      window.fixtureSwitchAccount(window.fixtureUsers.b);
      window.fixtureResolve('projects');
    });
    await settle(page);
    assertFencedRequest(await requestEvidence(page, 'projects'), 'import Project refresh');
    assert.equal((await snapshot(page)).overlayHtml, '', 'A-initiated import modal mounted after A→B');

    // Import A upload may resolve after Import B replaces it, but cannot read B's fields or POST/close/navigate.
    await boot(page, port);
    await page.evaluate(() => void window.fixtureOpenImport());
    await page.waitForSelector('#crump57ImportForm');
    await page.locator('#crump57Title').fill('Import A title');
    await page.locator('#crump57SourceFile').setInputFiles({name: 'import-a.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: Buffer.from('A')});
    await page.evaluate(() => window.fixturePlanUpload());
    await page.locator('#crump57ImportForm').evaluate(form => form.requestSubmit());
    await page.waitForFunction(() => window.fixtureDeferredCount('upload') === 1);
    await page.evaluate(() => void window.fixtureOpenImport());
    await page.waitForFunction(() => document.querySelectorAll('#crump57ImportForm').length === 1);
    await page.locator('#crump57Title').fill('Import B title');
    const importBRemovals = (await snapshot(page)).overlayRemovals.length;
    await page.evaluate(() => window.fixtureResolveUpload());
    await settle(page);
    const importUpload = await page.evaluate(() => window.fixtureUploadEvidence());
    assert.deepEqual(importUpload, [{fileName: 'import-a.docx', hasSignal: true, aborted: true, hasGuard: true, initialMayProceed: true, mayProceed: false}]);
    assert.equal((await requestEvidence(page, 'import')).length, 0, 'Import A posted hybrid metadata from Import B');
    assert.equal(await page.locator('#crump57Title').inputValue(), 'Import B title');
    let result = await snapshot(page);
    assert.equal(result.overlayLabel, 'Import manuscript', 'Import A closed or replaced Import B');
    assert.equal(result.overlayRemovals.length, importBRemovals, 'Import A closed an unrelated replacement modal');
    assert.deepEqual(result.toasts, [], 'Import A emitted a stale toast');
    assert.deepEqual(result.navigations, [], 'Import A navigated after modal replacement');

    // Editor upload and PATCH continuations must not mutate or close Editor B.
    await boot(page, port);
    await click(page, '[data-crump57-edit="book-a"]');
    await page.locator('#crump57EditTitle').fill('Editor A upload');
    await page.locator('#crump57EditFront').setInputFiles({name: 'editor-a.png', mimeType: 'image/png', buffer: Buffer.from('image')});
    await page.evaluate(() => window.fixturePlanUpload());
    await page.locator('#crump57BookForm').evaluate(form => form.requestSubmit());
    await page.waitForFunction(() => window.fixtureDeferredCount('upload') === 1);
    await click(page, '[data-crump57-edit="book-b"]');
    await page.waitForFunction(() => document.querySelector('#crump57BookForm h3')?.textContent === null, {timeout: 100}).catch(() => {});
    await page.locator('#crump57EditTitle').fill('Editor B intact');
    const editorUploadRemovals = (await snapshot(page)).overlayRemovals.length;
    await page.evaluate(() => window.fixtureResolveUpload());
    await settle(page);
    assert.deepEqual(await page.evaluate(() => window.fixtureUploadEvidence()), [{fileName: 'editor-a.png', hasSignal: true, aborted: true, hasGuard: true, initialMayProceed: true, mayProceed: false}]);
    assert.equal((await requestEvidence(page, 'edit:book-a')).length, 0, 'Editor A PATCHed after its upload outlived the modal');
    assert.equal(await page.locator('#crump57EditTitle').inputValue(), 'Editor B intact');
    result = await snapshot(page);
    assert.equal(result.overlayLabel, 'Book details');
    assert.equal(result.overlayRemovals.length, editorUploadRemovals);
    assert.deepEqual(result.toasts, []);

    await boot(page, port);
    await click(page, '[data-crump57-edit="book-a"]');
    await page.locator('#crump57EditTitle').fill('Editor A patch');
    await page.evaluate(() => window.fixturePlan('edit:book-a'));
    await page.locator('#crump57BookForm').evaluate(form => form.requestSubmit());
    await page.waitForFunction(() => window.fixtureDeferredCount('edit:book-a') === 1);
    await click(page, '[data-crump57-edit="book-b"]');
    await page.locator('#crump57EditTitle').fill('Editor B still intact');
    const editorPatchRemovals = (await snapshot(page)).overlayRemovals.length;
    await page.evaluate(() => window.fixtureResolve('edit:book-a'));
    await settle(page);
    assertFencedRequest(await requestEvidence(page, 'edit:book-a'), 'Editor A PATCH');
    assert.equal(await page.locator('#crump57EditTitle').inputValue(), 'Editor B still intact');
    result = await snapshot(page);
    assert.equal(result.overlayLabel, 'Book details');
    assert.equal(result.overlayRemovals.length, editorPatchRemovals);
    assert.deepEqual(result.toasts, []);

    // Trash, restore, and permanent delete carry signals and have no stale surface effects.
    await boot(page, port);
    await click(page, '[data-crump57-trash="book-a"]');
    await page.evaluate(() => window.fixturePlan('trash:book-a'));
    await click(page, '#crump57TrashConfirm');
    await page.waitForFunction(() => window.fixtureDeferredCount('trash:book-a') === 1);
    await click(page, '[data-crump57-edit="book-b"]');
    await page.locator('#crump57EditTitle').fill('Editor B after trash');
    const trashRemovals = (await snapshot(page)).overlayRemovals.length;
    await page.evaluate(() => window.fixtureResolve('trash:book-a'));
    await settle(page);
    assertFencedRequest(await requestEvidence(page, 'trash:book-a'), 'trash A');
    assert.equal(await page.locator('#crump57EditTitle').inputValue(), 'Editor B after trash');
    result = await snapshot(page);
    assert.equal(result.overlayRemovals.length, trashRemovals);
    assert.deepEqual(result.toasts, []);

    await boot(page, port);
    await page.evaluate(() => void window.fixtureOpenDeleted());
    await page.waitForSelector('[data-crump57-restore="deleted-a"]');
    await page.evaluate(() => window.fixturePlan('restore:deleted-a'));
    await click(page, '[data-crump57-restore="deleted-a"]');
    await page.waitForFunction(() => window.fixtureDeferredCount('restore:deleted-a') === 1);
    await click(page, '[data-crump57-edit="book-b"]');
    await page.locator('#crump57EditTitle').fill('Editor B after restore');
    const restoreRemovals = (await snapshot(page)).overlayRemovals.length;
    await page.evaluate(() => window.fixtureResolve('restore:deleted-a'));
    await settle(page);
    assertFencedRequest(await requestEvidence(page, 'restore:deleted-a'), 'restore A');
    assert.equal(await page.locator('#crump57EditTitle').inputValue(), 'Editor B after restore');
    result = await snapshot(page);
    assert.equal(result.overlayRemovals.length, restoreRemovals);
    assert.deepEqual(result.toasts, []);

    await boot(page, port);
    await page.evaluate(() => void window.fixtureOpenDeleted());
    await page.waitForSelector('[data-crump57-permanent="deleted-a"]');
    await click(page, '[data-crump57-permanent="deleted-a"]');
    await page.locator('#crump57PermanentPhrase').fill('DELETE');
    await page.evaluate(() => window.fixturePlan('delete:deleted-a'));
    await click(page, '#crump57PermanentConfirm');
    await page.waitForFunction(() => window.fixtureDeferredCount('delete:deleted-a') === 1);
    await page.evaluate(() => {
      window.fixtureSwitchAccount(window.fixtureUsers.b);
      window.fixtureResolve('delete:deleted-a');
    });
    await settle(page);
    assertFencedRequest(await requestEvidence(page, 'delete:deleted-a'), 'permanent delete A');
    result = await snapshot(page);
    assert.equal(result.overlayHtml, '');
    assert.deepEqual(result.toasts, []);
    assert.deepEqual(result.navigations, []);

    // Latest request wins independently for books, deleted books, and Projects.
    await boot(page, port);
    await page.evaluate(() => {
      window.fixturePlan('books', 2);
      void window.fixtureRefresh();
      void window.fixtureRefresh();
    });
    await page.waitForFunction(() => window.fixtureDeferredCount('books') === 2);
    await page.evaluate(() => window.fixtureResolve('books', 1, {success: true, books: [window.fixtureNamedBook('new-book', 'Newest books response', '2026-10-22T12:00:00Z')]}));
    await page.waitForFunction(() => document.getElementById('crump57Bookshelf')?.textContent.includes('Newest books response'));
    await page.evaluate(() => window.fixtureResolve('books', 0, {success: true, books: [window.fixtureNamedBook('old-book', 'Old books response', '2026-10-22T09:00:00Z')]}));
    await settle(page);
    assert.match((await snapshot(page)).bookshelfText, /Newest books response/);
    assert.doesNotMatch((await snapshot(page)).bookshelfText, /Old books response/);
    const booksRequests = await requestEvidence(page, 'books');
    assert.equal(booksRequests.at(-2).hasSignal, true);
    assert.equal(booksRequests.at(-2).aborted, true, 'superseded books request was not aborted');
    assert.equal(booksRequests.at(-1).hasSignal, true);

    await boot(page, port);
    await page.evaluate(() => {
      window.fixturePlan('deleted', 2);
      void window.fixtureOpenDeleted();
      void window.fixtureOpenDeleted();
    });
    await page.waitForFunction(() => window.fixtureDeferredCount('deleted') === 2);
    await page.evaluate(() => window.fixtureResolve('deleted', 1, {success: true, books: [window.fixtureNamedBook('new-deleted', 'Newest deleted response')]}));
    await page.waitForFunction(() => document.querySelector('.crump57-deleted-list')?.textContent.includes('Newest deleted response'));
    await page.evaluate(() => window.fixtureResolve('deleted', 0, {success: true, books: [window.fixtureNamedBook('old-deleted', 'Old deleted response')]}));
    await settle(page);
    result = await snapshot(page);
    assert.match(result.overlayHtml, /Newest deleted response/);
    assert.doesNotMatch(result.overlayHtml, /Old deleted response/);
    const deletedRequests = await requestEvidence(page, 'deleted');
    assert.equal(deletedRequests.at(-2).hasSignal, true);
    assert.equal(deletedRequests.at(-2).aborted, true, 'superseded deleted-books request was not aborted');

    await boot(page, port);
    await page.evaluate(() => {
      window.fixturePlan('projects', 2);
      void window.fixtureOpenImport();
      void window.fixtureOpenImport();
    });
    await page.waitForFunction(() => window.fixtureDeferredCount('projects') === 2);
    await page.evaluate(() => window.fixtureResolve('projects', 1, {success: true, projects: [{id: 'new-project', name: 'Newest Project response'}], limit: 10}));
    await page.waitForFunction(() => document.getElementById('crump57Project')?.textContent.includes('Newest Project response'));
    await page.evaluate(() => window.fixtureResolve('projects', 0, {success: true, projects: [{id: 'old-project', name: 'Old Project response'}], limit: 10}));
    await settle(page);
    result = await snapshot(page);
    assert.match(result.overlayHtml, /Newest Project response/);
    assert.doesNotMatch(result.overlayHtml, /Old Project response/);
    const projectRequests = await requestEvidence(page, 'projects');
    assert.equal(projectRequests.at(-2).hasSignal, true);
    assert.equal(projectRequests.at(-2).aborted, true, 'superseded Project request was not aborted');

    // Current same-account import succeeds with captured A-only metadata and guarded upload.
    await boot(page, port);
    await page.evaluate(() => void window.fixtureOpenImport());
    await page.waitForSelector('#crump57ImportForm');
    await page.locator('#crump57Title').fill('Active import title');
    await page.locator('#crump57Author').fill('Active author');
    await page.locator('#crump57SourceFile').setInputFiles({name: 'active.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: Buffer.from('active')});
    await page.locator('#crump57ImportForm').evaluate(form => form.requestSubmit());
    await page.waitForFunction(() => window.fixtureRequestEvidence('import').length === 1);
    await settle(page);
    const activeUploads = await page.evaluate(() => window.fixtureUploadEvidence());
    assert.deepEqual(activeUploads, [{fileName: 'active.docx', hasSignal: true, aborted: false, hasGuard: true, initialMayProceed: true, mayProceed: false}]);
    const importRequests = await requestEvidence(page, 'import');
    assertFencedRequest(importRequests, 'active import', {aborted: false});
    assert.equal(importRequests[0].body.title, 'Active import title');
    assert.equal(importRequests[0].body.authorName, 'Active author');
    assert.equal(importRequests[0].body.sourceFileId, 'uploaded-active.docx');
    result = await snapshot(page);
    assert.deepEqual(result.toasts, [{message: 'Imported fixture added to your Library.', type: 'success'}]);
    assert.deepEqual(result.navigations.map(item => item.manuscriptId), ['imported-book']);

    // Current permanent-delete failure remains actionable and retry succeeds.
    await boot(page, port);
    await page.evaluate(() => void window.fixtureOpenDeleted());
    await page.waitForSelector('[data-crump57-permanent="deleted-a"]');
    await click(page, '[data-crump57-permanent="deleted-a"]');
    await page.locator('#crump57PermanentPhrase').fill('DELETE');
    await page.evaluate(() => window.fixturePlan('delete:deleted-a', 2));
    await click(page, '#crump57PermanentConfirm');
    await page.waitForFunction(() => window.fixtureDeferredCount('delete:deleted-a') === 1);
    await page.evaluate(() => window.fixtureResolve('delete:deleted-a', 0, {success: false, error: 'Delete retry fixture.'}, 500));
    await page.waitForFunction(() => document.getElementById('crump57PermanentStatus')?.textContent.includes('Delete retry fixture.'));
    assert.equal(await page.locator('#crump57PermanentConfirm').isEnabled(), true, 'same-account delete error did not permit retry');
    await click(page, '#crump57PermanentConfirm');
    await page.waitForFunction(() => window.fixtureDeferredCount('delete:deleted-a') === 2);
    await page.evaluate(() => window.fixtureResolve('delete:deleted-a', 1));
    await page.waitForFunction(() => !document.querySelector('.crump57-overlay'));
    const retryRequests = await requestEvidence(page, 'delete:deleted-a');
    assert.equal(retryRequests.length, 2);
    retryRequests.forEach((request, index) => assertFencedRequest([request], `delete retry request ${index + 1}`, {aborted: false}));
    assert.deepEqual((await snapshot(page)).toasts, [{message: 'Deleted A permanently deleted.', type: 'success'}]);

    assert.equal(await page.locator('#fixtureErrors').textContent(), '0');
    assert.deepEqual(browserErrors, []);
    process.stdout.write(JSON.stringify({
      readerResolveFence: true,
      readerRejectFence: true,
      readerSuccessRetry: true,
      previewResourceFence: true,
      importMountFence: true,
      importHybridFence: true,
      editorUploadFence: true,
      editorPatchFence: true,
      trashFence: true,
      restoreFence: true,
      permanentDeleteFence: true,
      refreshLatestWins: true,
      activeImportSuccess: true,
      activeDeleteRetry: true,
    }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
