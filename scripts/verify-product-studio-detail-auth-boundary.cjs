const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE
  || process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || process.env.ASK_CRUMP_BROWSER_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

async function snapshot(page) {
  return page.evaluate(() => ({
    queueText: document.getElementById('crump531ReferenceQueue')?.textContent
      ?.replace(/\s+/g, ' ').trim() || '',
    filesText: document.getElementById('crump531ProjectFilesList')?.textContent
      ?.replace(/\s+/g, ' ').trim() || '',
    statusText: document.getElementById('crump531ReferenceStatus')?.textContent
      ?.replace(/\s+/g, ' ').trim() || '',
    filesCardHidden: document.getElementById('crump531ProjectFilesCard')?.hidden !== false,
    fileRequests: window.fixtureProjectFileRequests.map(request => ({
      ownerUserId: request.ownerUserId,
      projectId: request.projectId,
      signalAborted: Boolean(request.signal?.aborted),
      abortEvents: request.abortEvents,
      settled: request.settled,
    })),
    uploads: window.fixtureUploads.map(upload => ({
      ownerUserId: upload.ownerUserId,
      fileName: upload.file?.name || '',
      signalAborted: Boolean(upload.controller?.signal?.aborted),
      abortCalls: Number(upload.controller?.abortCalls || 0),
      settled: upload.settled,
    })),
    attachRequests: window.fixtureProjectAttachRequests.map(request => ({...request})),
    browserErrors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
  }));
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath});
  const page = await browser.newPage({viewport: {width: 1280, height: 760}});
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  try {
    await page.goto(
      `${baseUrl}/tests/fixtures/product-studio-detail-auth-boundary.html`,
      {waitUntil: 'load'},
    );
    await page.waitForFunction(() => document.documentElement.dataset.fixtureReady === 'true');
    await page.waitForFunction(() => window.fixtureProjectFileRequests.length === 1);
    const accounts = await page.evaluate(() => window.fixtureAccounts);
    const names = {
      renderedA: 'Account-A-rendered-secret.pdf',
      queuedA: 'Account-A-queued-secret.pdf',
      queuedASecond: 'Account-A-second-secret.png',
      lateA: 'Account-A-late-secret.docx',
      renderedB: 'Account-B-owned-reference.pdf',
    };

    await page.evaluate(({renderedA}) => {
      window.fixtureResolveProjectFiles(0, [{
        id: 'fixture-account-a-rendered',
        name: renderedA,
        size: 4800,
        projectRole: 'reference',
      }]);
    }, names);
    await page.waitForFunction(name => (
      document.getElementById('crump531ProjectFilesList')?.textContent.includes(name)
    ), names.renderedA);

    await page.evaluate(({queuedA, queuedASecond}) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File(['account-a-private-one'], queuedA, {
        type: 'application/pdf',
      }));
      transfer.items.add(new File(['account-a-private-two'], queuedASecond, {
        type: 'image/png',
      }));
      const input = document.getElementById('crump531ReferenceInput');
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles: true}));
    }, names);
    await page.waitForFunction(({queuedA, queuedASecond}) => {
      const text = document.getElementById('crump531ReferenceQueue')?.textContent || '';
      return text.includes(queuedA) && text.includes(queuedASecond);
    }, names);

    await page.evaluate(() => {
      document.getElementById('crump53ProjectForm').dispatchEvent(new Event('submit', {
        bubbles: true,
        cancelable: true,
      }));
    });
    await page.waitForFunction(() => window.fixtureUploads.length === 1);
    const queuedBeforeBoundary = await snapshot(page);

    assert.match(queuedBeforeBoundary.queueText, new RegExp(names.queuedA));
    assert.match(queuedBeforeBoundary.queueText, new RegExp(names.queuedASecond));
    assert.match(queuedBeforeBoundary.filesText, new RegExp(names.renderedA));
    assert.equal(queuedBeforeBoundary.uploads[0].ownerUserId, accounts.accountA.id);
    assert.equal(queuedBeforeBoundary.uploads[0].fileName, names.queuedA);
    assert.equal(queuedBeforeBoundary.uploads[0].signalAborted, false);
    assert.deepEqual(queuedBeforeBoundary.attachRequests, []);

    await page.evaluate(accountB => {
      window.fixtureAuthenticationRequired();
      window.fixtureLogin(accountB);
    }, accounts.accountB);
    await page.waitForFunction(() => (
      document.getElementById('crump531ProjectFilesCard')?.hidden === true
      && document.getElementById('crump531ReferenceQueue')?.textContent
        .includes('No reference files selected.')
    ));
    const switchedToB = await snapshot(page);

    assert.equal(switchedToB.filesCardHidden, true, JSON.stringify(switchedToB));
    assert.equal(switchedToB.filesText, '', JSON.stringify(switchedToB));
    assert.equal(switchedToB.statusText, '', JSON.stringify(switchedToB));
    assert.equal(switchedToB.queueText, 'No reference files selected.');
    for (const accountAName of [
      names.renderedA,
      names.queuedA,
      names.queuedASecond,
      names.lateA,
    ]) {
      assert.equal(`${switchedToB.queueText} ${switchedToB.filesText}`.includes(accountAName), false);
    }
    assert.equal(switchedToB.uploads[0].signalAborted, true);
    assert.equal(switchedToB.uploads[0].abortCalls, 1);
    assert.deepEqual(switchedToB.attachRequests, []);

    await page.evaluate(() => {
      window.fixtureResolveUpload(0);
    });
    await page.waitForTimeout(100);
    const lateAccountACompletion = await snapshot(page);

    assert.equal(lateAccountACompletion.uploads.length, 1);
    assert.equal(lateAccountACompletion.uploads[0].settled, true);
    assert.deepEqual(lateAccountACompletion.attachRequests, []);
    for (const accountAName of [
      names.renderedA,
      names.queuedA,
      names.queuedASecond,
      names.lateA,
    ]) {
      assert.equal(
        `${lateAccountACompletion.queueText} ${lateAccountACompletion.filesText}`
          .includes(accountAName),
        false,
      );
    }

    await page.goto(
      `${baseUrl}/tests/fixtures/product-studio-detail-auth-boundary.html`,
      {waitUntil: 'load'},
    );
    await page.waitForFunction(() => document.documentElement.dataset.fixtureReady === 'true');
    await page.waitForFunction(() => window.fixtureProjectFileRequests.length === 1);
    const inFlightFetchBeforeBoundary = await snapshot(page);

    assert.equal(inFlightFetchBeforeBoundary.fileRequests[0].ownerUserId, accounts.accountA.id);
    assert.equal(inFlightFetchBeforeBoundary.fileRequests[0].projectId, accounts.projectA.id);
    assert.equal(inFlightFetchBeforeBoundary.fileRequests[0].signalAborted, false);
    assert.match(inFlightFetchBeforeBoundary.filesText, /Loading Project files/);

    await page.evaluate(accountB => {
      window.fixtureAuthenticationRequired();
      window.fixtureLogin(accountB);
    }, accounts.accountB);
    await page.waitForFunction(() => (
      document.getElementById('crump531ProjectFilesCard')?.hidden === true
    ));
    const fetchSwitchedToB = await snapshot(page);

    assert.equal(fetchSwitchedToB.fileRequests[0].signalAborted, true);
    assert.equal(fetchSwitchedToB.fileRequests[0].abortEvents, 1);
    assert.equal(fetchSwitchedToB.filesText, '');

    await page.evaluate(({lateA}) => {
      window.fixtureResolveProjectFiles(0, [{
        id: 'fixture-account-a-late',
        name: lateA,
        size: 9600,
        projectRole: 'reference',
      }]);
    }, names);
    await page.waitForTimeout(100);
    const lateAccountAFetchCompletion = await snapshot(page);

    assert.equal(lateAccountAFetchCompletion.fileRequests[0].settled, true);
    assert.equal(lateAccountAFetchCompletion.filesText.includes(names.lateA), false);
    assert.deepEqual(lateAccountAFetchCompletion.attachRequests, []);

    await page.evaluate(() => {
      window.dispatchEvent(new Event('crump:project-target-changed'));
    });
    await page.waitForFunction(() => window.fixtureProjectFileRequests.length === 2);
    await page.evaluate(({renderedB}) => {
      window.fixtureResolveProjectFiles(1, [{
        id: 'fixture-account-b-rendered',
        name: renderedB,
        size: 7200,
        projectRole: 'reference',
      }]);
    }, names);
    await page.waitForFunction(name => (
      document.getElementById('crump531ProjectFilesList')?.textContent.includes(name)
    ), names.renderedB);
    const accountBRendered = await snapshot(page);

    assert.equal(accountBRendered.fileRequests[1].ownerUserId, accounts.accountB.id);
    assert.equal(accountBRendered.fileRequests[1].projectId, accounts.projectB.id);
    assert.match(accountBRendered.filesText, new RegExp(names.renderedB));
    for (const accountAName of [
      names.renderedA,
      names.queuedA,
      names.queuedASecond,
      names.lateA,
    ]) {
      assert.equal(accountBRendered.filesText.includes(accountAName), false);
    }
    assert.deepEqual(accountBRendered.attachRequests, []);
    assert.equal(accountBRendered.browserErrors, 0);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      queuedBeforeBoundary,
      switchedToB,
      lateAccountACompletion,
      inFlightFetchBeforeBoundary,
      fetchSwitchedToB,
      lateAccountAFetchCompletion,
      accountBRendered,
      errors,
    }));
  } finally {
    await page.close();
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
