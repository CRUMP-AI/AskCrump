const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const root = path.resolve(__dirname, '..');

async function startServer() {
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url || '/', 'http://127.0.0.1').pathname;
    const relative = pathname.replace(/^\/+/, '');
    const filePath = path.resolve(root, relative);
    if (!filePath.startsWith(`${root}${path.sep}`)) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, {
        'Content-Type': pathname.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8',
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

(async () => {
  const fixture = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(
      `http://127.0.0.1:${fixture.port}/tests/fixtures/chat-owner-boundary.html`,
      {waitUntil: 'load'},
    );

    const sameOwner = await page.evaluate(() => window.__fixture.sameOwner());
    assert.equal(sameOwner.success, true);
    const afterSame = await page.evaluate(() => ({
      requests: window.__fixture.requests.slice(),
      mutations: window.__fixture.serverMutations.slice(),
    }));
    assert.deepEqual(afterSame.requests.map(item => item.claim), [
      '11111111-1111-4111-8111-111111111111',
      '11111111-1111-4111-8111-111111111111',
      '11111111-1111-4111-8111-111111111111',
    ]);
    assert.deepEqual(afterSame.mutations.map(item => item.owner), [
      '11111111-1111-4111-8111-111111111111',
      '11111111-1111-4111-8111-111111111111',
    ]);

    const cookieSkew = await page.evaluate(() => window.__fixture.cookieSkew());
    assert.deepEqual(cookieSkew, {rejected: true, code: 'AUTH_OWNER_MISMATCH', status: 409});
    const mutationsAfterSkew = await page.evaluate(() => window.__fixture.serverMutations.slice());
    assert.equal(mutationsAfterSkew.length, 2);

    const delayed = await page.evaluate(() => window.__fixture.delayedCompletion());
    assert.deepEqual(delayed, {rejected: true, code: 'AUTH_OWNER_CHANGED', quiet: true});
    const final = await page.evaluate(() => ({
      requests: window.__fixture.requests.slice(),
      mutations: window.__fixture.serverMutations.slice(),
      allowanceOwners: window.__fixture.allowanceOwners.slice(),
    }));
    assert.equal(final.requests.at(-1).claim, '11111111-1111-4111-8111-111111111111');
    assert.equal(final.mutations.filter(item => item.owner === 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb').length, 0);
    assert.equal(final.allowanceOwners.includes('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'), false);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      sameOwnerClaims: afterSame.requests.map(item => item.claim),
      cookieSkewRejected: true,
      delayedOwnerCompletionIgnored: true,
      serverMutations: final.mutations,
      errors,
    }));
  } finally {
    await browser.close();
    await new Promise(resolve => fixture.server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
