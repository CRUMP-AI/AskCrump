const assert = require('node:assert/strict');
const {existsSync} = require('node:fs');
const {readFile} = require('node:fs/promises');
const {createServer} = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');

async function startServer() {
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url || '/', 'http://127.0.0.1').pathname;
    const filePath = path.resolve(root, pathname.replace(/^\/+/, ''));
    if (!filePath.startsWith(`${root}${path.sep}`)) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, {
        'Content-Type': pathname.endsWith('.html')
          ? 'text/html; charset=utf-8'
          : 'text/javascript; charset=utf-8',
        'Cache-Control': 'no-store',
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

function browserLaunchOptions() {
  const requested = process.env.ASKCRUMP_BROWSER_EXECUTABLE
    || process.env.ASK_CRUMP_BROWSER_PATH
    || process.env.CODEX_BROWSER_EXECUTABLE
    || '';
  const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const executablePath = requested || (process.platform === 'win32' && existsSync(edge) ? edge : '');
  return {headless: true, ...(executablePath ? {executablePath} : {})};
}

(async () => {
  const fixture = await startServer();
  const browser = await chromium.launch(browserLaunchOptions());
  const page = await browser.newPage({viewport: {width: 820, height: 720}});
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  try {
    const fixtureUrl = `http://127.0.0.1:${fixture.port}/tests/fixtures/legacy-attachment-owner-boundary.html`;
    await page.goto(
      fixtureUrl,
      {waitUntil: 'load'},
    );
    await page.waitForFunction(() => window.__fixture.requests.length === 1);
    const owners = await page.evaluate(() => ({
      ownerA: window.__fixture.ownerA,
      ownerB: window.__fixture.ownerB,
      ownerAFileId: window.__fixture.ownerAFileId,
      ownerBFileId: window.__fixture.ownerBFileId,
    }));
    const ownerAStarted = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(ownerAStarted.requests[0].ownerAtRequest, owners.ownerA);
    assert.equal(ownerAStarted.requests[0].expectedOwner, owners.ownerA);
    assert.equal(ownerAStarted.requests[0].aborted, false);

    await page.evaluate(() => window.__fixture.switchToOwnerB());
    await page.waitForFunction(() => window.__fixture.requests.length === 2);
    const switchedToOwnerB = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(switchedToOwnerB.requests[0].aborted, true);
    assert.equal(switchedToOwnerB.requests[0].abortEvents, 1);
    assert.equal(switchedToOwnerB.requests[1].ownerAtRequest, owners.ownerB);
    assert.equal(switchedToOwnerB.requests[1].expectedOwner, owners.ownerB);
    assert.equal(switchedToOwnerB.ownerAFile.id, undefined);
    assert.equal(switchedToOwnerB.ownerBFile.id, undefined);

    await page.evaluate(() => window.__fixture.resolveOwnerA());
    await page.waitForFunction(() => window.__fixture.requests[0].settled === true);
    await page.waitForTimeout(60);
    const lateOwnerACompletion = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(lateOwnerACompletion.ownerAFile.id, undefined);
    assert.equal(lateOwnerACompletion.ownerBFile.id, undefined);
    assert.equal(lateOwnerACompletion.attachmentSignature.includes(owners.ownerAFileId), false);
    assert.equal(lateOwnerACompletion.attachmentText.includes('1 KB'), false);

    await page.evaluate(() => window.__fixture.resolveOwnerB());
    await page.waitForFunction(ownerBFileId => (
      window.__fixture.chatB.messages[0].files[0].id === ownerBFileId
      && document.querySelector('.crump52-rich-attachments')?.dataset
        .attachmentSignature.includes(ownerBFileId)
    ), owners.ownerBFileId);
    const ownerBHydrated = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(ownerBHydrated.ownerAFile.id, undefined);
    assert.equal(ownerBHydrated.ownerBFile.id, owners.ownerBFileId);
    assert.equal(ownerBHydrated.ownerBFile.size, 2048);
    assert.equal(ownerBHydrated.attachmentSignature.includes(owners.ownerAFileId), false);
    assert.equal(ownerBHydrated.attachmentSignature.includes(owners.ownerBFileId), true);
    assert.equal(ownerBHydrated.attachmentText.includes('2 KB'), true);
    assert.equal(ownerBHydrated.attachmentDisabled, false);

    await page.evaluate(() => window.__fixture.resetOwnerBLegacyFile());
    await page.waitForFunction(ownerBFileId => (
      window.__fixture.chatB.messages[0].files[0].id === ownerBFileId
    ), owners.ownerBFileId);
    const ownerBCacheReplay = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(ownerBCacheReplay.requests.length, 2);
    assert.equal(ownerBCacheReplay.ownerBFile.id, owners.ownerBFileId);

    await page.evaluate(() => window.__fixture.switchBackToOwnerA());
    await page.waitForFunction(() => window.__fixture.requests.length === 3);
    const ownerARetry = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(ownerARetry.requests[2].ownerAtRequest, owners.ownerA);
    assert.equal(ownerARetry.requests[2].expectedOwner, owners.ownerA);
    assert.equal(ownerARetry.ownerAFile.id, undefined);

    await page.goto(fixtureUrl, {waitUntil: 'load'});
    await page.waitForFunction(() => window.__fixture.requests.length === 1);
    await page.evaluate(() => window.__fixture.replaceOwnerAProjection());
    await page.waitForTimeout(40);
    const sameOwnerProjectionReplaced = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(sameOwnerProjectionReplaced.requests.length, 1);
    assert.equal(sameOwnerProjectionReplaced.ownerAFile.id, undefined);
    assert.equal(sameOwnerProjectionReplaced.ownerAReplacementFile.id, undefined);
    assert.equal(sameOwnerProjectionReplaced.ownerAReplacementWrites, 0);

    await page.evaluate(() => window.__fixture.resolveOwnerA());
    await page.waitForFunction(ownerAFileId => (
      window.__fixture.chatAReplacement.messages[0].files[0].id === ownerAFileId
      && document.querySelector('.crump52-rich-attachments')?.dataset
        .attachmentSignature.includes(ownerAFileId)
    ), owners.ownerAFileId);
    const sameOwnerProjectionHydrated = await page.evaluate(() => window.__fixture.snapshot());
    assert.equal(sameOwnerProjectionHydrated.requests.length, 1);
    assert.equal(sameOwnerProjectionHydrated.ownerAFile.id, undefined);
    assert.equal(sameOwnerProjectionHydrated.ownerAReplacementFile.id, owners.ownerAFileId);
    assert.equal(sameOwnerProjectionHydrated.ownerAReplacementWrites, 1);
    assert.equal(sameOwnerProjectionHydrated.attachmentSignature.includes(owners.ownerAFileId), true);
    assert.equal(sameOwnerProjectionHydrated.attachmentText.includes('1 KB'), true);
    assert.equal(sameOwnerProjectionHydrated.attachmentDisabled, false);
    assert.equal(errors.length, 0, errors.join('\n'));

    process.stdout.write(JSON.stringify({
      ownerAStarted,
      switchedToOwnerB,
      lateOwnerACompletion,
      ownerBHydrated,
      ownerBCacheReplay,
      ownerARetry,
      sameOwnerProjectionReplaced,
      sameOwnerProjectionHydrated,
      errors,
    }));
  } finally {
    await page.close();
    await browser.close();
    await new Promise(resolve => fixture.server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
