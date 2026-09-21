const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(process.cwd());
const fixture = path.join(root, 'tests', 'fixtures', 'video-owner-continuity.html');
const product = path.join(root, 'public', 'crump-product-5.3.js');
const credit = path.join(root, 'public', 'credit-confirmation.js');
const upload = path.join(root, 'public', 'crump-5.0.js');

async function snapshot(page) {
  return page.evaluate(() => ({
    owner: window.currentUser?.id || '',
    jobA: localStorage.getItem('askcrump.videoJob53:user-a'),
    jobB: localStorage.getItem('askcrump.videoJob53:user-b'),
    requestA: localStorage.getItem('askcrump.videoRequest53:user-a'),
    requestB: localStorage.getItem('askcrump.videoRequest53:user-b'),
    legacyJob: localStorage.getItem('askcrump.videoJob53'),
    legacyRequest: localStorage.getItem('askcrump.videoRequest53'),
    status: document.getElementById('crump53VideoStatus')?.textContent || '',
    statusError: document.getElementById('crump53VideoStatus')?.classList.contains('is-error') || false,
    busy: document.getElementById('crump53GenerateVideo')?.disabled || false,
    result: document.getElementById('crump53VideoResult')?.textContent || '',
    files: document.getElementById('crump53LibraryGrid')?.textContent || '',
    calls: window.__calls.slice(),
  }));
}

async function openVideo(page) {
  await page.click('#openVideo');
  await page.locator('#crump53VideoPrompt').waitFor();
}

async function switchUser(page, owner) {
  await page.evaluate(id => window.__switchUser(id), owner);
}

async function startVideo(page, prompt) {
  await page.locator('#crump53VideoPrompt').fill(prompt);
  await page.click('#crump53GenerateVideo');
}

(async () => {
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url || '/', 'http://127.0.0.1').pathname;
    const target = pathname === '/fixture.html' ? fixture
      : pathname === '/public/crump-product-5.3.js' ? product
        : pathname === '/public/credit-confirmation.js' ? credit
          : pathname === '/public/crump-5.0.js' ? upload : null;
    if (!target) { response.writeHead(404); response.end('Not found'); return; }
    response.writeHead(200, {
      'Content-Type': target.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(await readFile(target));
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const failures = [];
  const base = `http://127.0.0.1:${server.address().port}/fixture.html`;
  async function pageFor(mode = '') {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on('pageerror', error => failures.push(error.message));
    await page.goto(`${base}?mode=${mode}`, {waitUntil: 'networkidle'});
    await openVideo(page);
    return {context, page};
  }
  try {
    {
      const {context, page} = await pageFor('legacy');
      await page.waitForFunction(() => window.__calls.some(call => call.owner === 'user-b' && call.url === '/api/media/video/user-a-job'));
      let state = await snapshot(page);
      assert.equal(state.legacyJob, 'user-a-job', 'B must not delete A’s legacy handle after owner-protected 404');
      assert.equal(state.jobB, null);
      assert.equal(state.busy, false, 'B must not be blocked by A’s legacy job');
      assert.equal(state.statusError, false, 'B must not see A’s owner-protected 404');
      await switchUser(page, 'user-a');
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-a') === 'user-a-job');
      state = await snapshot(page);
      assert.equal(state.legacyJob, null, 'Verified A handle should migrate once');
      await switchUser(page, 'user-b');
      await startVideo(page, 'B makes a separate video');
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-b') === 'user-b-job');
      state = await snapshot(page);
      assert.equal(state.jobA, 'user-a-job');
      assert.equal(state.jobB, 'user-b-job');
      assert.equal(state.statusError, false);
      await switchUser(page, 'user-a');
      await page.waitForFunction(() => window.__calls.some(call => call.owner === 'user-a' && call.url === '/api/media/video/user-a-job'));
      state = await snapshot(page);
      assert.equal(state.jobA, 'user-a-job', 'A must recover after B’s independent job');
      await context.close();
    }
    {
      const {context, page} = await pageFor();
      await page.evaluate(() => { window.__failNextPostFor = 'user-a'; });
      await startVideo(page, 'A retries one request');
      await page.waitForFunction(() => window.__calls.filter(call => call.method === 'POST' && call.url === '/api/media/video').length === 1);
      await page.waitForFunction(() => document.getElementById('crump53GenerateVideo')?.disabled === false);
      let state = await snapshot(page);
      const firstKey = state.calls.find(call => call.method === 'POST' && call.url === '/api/media/video').idempotencyKey;
      assert.ok(firstKey);
      assert.equal(JSON.parse(state.requestA).idempotencyKey, firstKey);
      await startVideo(page, 'A retries one request');
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-a') === 'user-a-job');
      state = await snapshot(page);
      const posts = state.calls.filter(call => call.method === 'POST' && call.url === '/api/media/video');
      assert.equal(posts.length, 2);
      assert.deepEqual(posts.map(call => call.idempotencyKey), [firstKey, firstKey]);
      assert.equal(state.legacyRequest, null);
      await context.close();
    }
    for (const mode of ['ambiguous', 'server-pending', 'success-pending']) {
      const {context, page} = await pageFor(mode);
      await startVideo(page, 'A unresolved video start');
      await page.waitForFunction(() => {
        const value = JSON.parse(localStorage.getItem('askcrump.videoRequest53:user-a') || 'null');
        return value?.reconciliationPending && value.jobId === 'user-a-job';
      });
      let state = await snapshot(page);
      const firstPost = state.calls.find(call => call.method === 'POST' && call.url === '/api/media/video');
      assert.ok(firstPost.idempotencyKey, 'Unresolved start must keep its idempotency key');
      assert.equal(state.busy, true);
      assert.match(state.status, /reconcil/i);
      await page.evaluate(() => document.getElementById('crump53VideoForm')
        .dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
      state = await snapshot(page);
      assert.equal(state.calls.filter(call => call.method === 'POST' && call.owner === 'user-a').length, 1,
        'Unresolved start must never dispatch another paid request');
      await switchUser(page, 'user-b');
      await startVideo(page, 'B independent video');
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-b') === 'user-b-job');
      await switchUser(page, 'user-a');
      state = await snapshot(page);
      assert.equal(JSON.parse(state.requestA).idempotencyKey, firstPost.idempotencyKey);
      assert.equal(state.jobB, 'user-b-job');
      await page.reload({waitUntil: 'networkidle'});
      await openVideo(page);
      await page.waitForFunction(() => document.getElementById('crump53GenerateVideo')?.disabled === true);
      state = await snapshot(page);
      assert.equal(state.calls.filter(call => call.method === 'POST' && call.owner === 'user-a').length, 0,
        'Reloaded unresolved claim must resume status without replaying POST');
      assert.equal(JSON.parse(state.requestA).idempotencyKey, firstPost.idempotencyKey);
      await page.evaluate(() => {
        window.__unknownResolved = true;
        window.CrumpProduct53.open('video');
      });
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoRequest53:user-a') === null);
      state = await snapshot(page);
      assert.equal(state.jobA, 'user-a-job', 'Resolved processing job remains tracked');
      assert.equal(state.busy, true, 'Known processing job still prevents another charge');
      await context.close();
    }
    {
      const {context, page} = await pageFor();
      await page.evaluate(() => window.__makeHold('POST:user-a:/api/media/video'));
      await startVideo(page, 'A slow video');
      await page.waitForFunction(() => window.__calls.some(call => call.method === 'POST' && call.owner === 'user-a'));
      await switchUser(page, 'user-b');
      assert.equal(await page.locator('#crump53VideoPrompt').inputValue(), '', 'B must not inherit A’s private prompt');
      await startVideo(page, 'B independent video');
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-b') === 'user-b-job');
      await page.evaluate(() => window.__release('POST:user-a:/api/media/video'));
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-a') === 'user-a-job');
      const state = await snapshot(page);
      assert.equal(state.jobB, 'user-b-job');
      assert.equal(state.owner, 'user-b');
      assert.doesNotMatch(state.result, /user-a/);
      assert.equal(state.statusError, false);
      await context.close();
    }
    {
      const {context, page} = await pageFor('poll');
      await page.waitForFunction(() => window.__calls.some(call => call.owner === 'user-a' && call.url === '/api/media/video/user-a-job'));
      await switchUser(page, 'user-b');
      await page.evaluate(() => window.__release('GET:user-a:/api/media/video/user-a-job'));
      const state = await snapshot(page);
      assert.equal(state.jobA, 'user-a-job');
      assert.equal(state.jobB, null);
      assert.equal(state.busy, false);
      assert.doesNotMatch(state.status, /saved video job|generating|not found/i);
      await context.close();
    }
    {
      const {context, page} = await pageFor('library');
      await page.waitForFunction(() => window.__calls.some(call => call.owner === 'user-a' && call.url === '/api/files?limit=200'));
      await switchUser(page, 'user-b');
      await page.evaluate(() => window.__release('GET:user-a:/api/files?limit=200'));
      await page.evaluate(() => window.CrumpProduct53.openFiles());
      await page.waitForFunction(() => document.getElementById('crump53LibraryGrid')?.textContent.includes('user-b-private-file'));
      const state = await snapshot(page);
      assert.doesNotMatch(state.files, /user-a-private-file/);
      await context.close();
    }
    {
      const {context, page} = await pageFor();
      await page.evaluate(() => window.__useCreditGate());
      await startVideo(page, 'A unconfirmed video');
      await page.waitForFunction(() => Boolean(localStorage.getItem('askcrump.videoRequest53:user-a')));
      await switchUser(page, 'user-b');
      await page.evaluate(() => window.__release('credit'));
      await page.waitForTimeout(50);
      let state = await snapshot(page);
      assert.equal(state.calls.filter(call => call.method === 'POST' && call.url === '/api/media/video').length, 0,
        'A’s delayed credit confirmation must not send B a video charge');
      assert.equal(state.jobB, null);
      assert.equal(state.statusError, false);
      await page.evaluate(() => { window.CrumpCreditConfirmation = null; });
      await startVideo(page, 'B fresh video');
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-b') === 'user-b-job');
      state = await snapshot(page);
      assert.equal(state.jobA, null);
      assert.equal(state.jobB, 'user-b-job');
      await context.close();
    }
    {
      const {context, page} = await pageFor('quote');
      await startVideo(page, 'A private credit-quoted video');
      await page.locator('.crump-credit-confirmation').waitFor();
      assert.match(await page.locator('.crump-credit-confirmation').textContent(), /80 credits/);
      await switchUser(page, 'user-b');
      await page.locator('.crump-credit-confirmation').waitFor({state: 'detached'});
      const state = await snapshot(page);
      assert.equal(state.calls.filter(call => call.method === 'POST' && call.url === '/api/media/video').length, 1);
      assert.equal(state.calls.some(call => call.method === 'POST' && call.owner === 'user-b'), false);
      assert.equal(await page.locator('#crump53VideoPrompt').inputValue(), '');
      assert.equal(state.statusError, false);
      await context.close();
    }
    {
      const {context, page} = await pageFor('quote');
      await startVideo(page, 'A quote before checkout reauthentication');
      await page.locator('.crump-credit-confirmation').waitFor();
      await page.evaluate(() => window.dispatchEvent(new CustomEvent('crump:authentication-required', {
        detail: {reason: 'checkout'},
      })));
      await page.locator('.crump-credit-confirmation').waitFor({state: 'detached'});
      const state = await snapshot(page);
      assert.equal(state.calls.filter(call => call.method === 'POST' && call.url === '/api/media/video').length, 1);
      await context.close();
    }
    {
      const {context, page} = await pageFor();
      await page.evaluate(() => window.__makeHoldQueue('POST:user-a:/api/media/video', 2));
      await startVideo(page, 'A old request');
      await page.waitForFunction(() => window.__calls.filter(call => call.method === 'POST' && call.owner === 'user-a').length === 1);
      await switchUser(page, 'user-b');
      await switchUser(page, 'user-a');
      await startVideo(page, 'A new session request');
      await page.waitForFunction(() => window.__calls.filter(call => call.method === 'POST' && call.owner === 'user-a').length === 2);
      await page.evaluate(() => window.__releaseQueued('POST:user-a:/api/media/video', 0));
      await page.waitForTimeout(50);
      await page.evaluate(() => document.getElementById('crump53VideoForm')
        .dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
      let state = await snapshot(page);
      assert.equal(state.calls.filter(call => call.method === 'POST' && call.owner === 'user-a').length, 2,
        'Old A finally must not unlock the newer A request after A→B→A');
      await page.evaluate(() => window.__releaseQueued('POST:user-a:/api/media/video', 1));
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-a') === 'user-a-job');
      state = await snapshot(page);
      assert.equal(state.jobA, 'user-a-job');
      await context.close();
    }
    {
      const {context, page} = await pageFor();
      await page.evaluate(() => window.__makeHold('POST:user-a:/api/media/video'));
      await startVideo(page, 'A pending video before deletion');
      await page.waitForFunction(() => window.__calls.some(call => call.method === 'POST' && call.owner === 'user-a'));
      await page.evaluate(() => {
        window.dispatchEvent(new CustomEvent('crump:account-deleted', {detail: {userId: 'user-a'}}));
        localStorage.removeItem('askcrump.videoJob53:user-a');
        localStorage.removeItem('askcrump.videoRequest53:user-a');
        window.__release('POST:user-a:/api/media/video');
      });
      await page.waitForFunction(() => window.__responses.includes('POST:user-a:/api/media/video'));
      await page.waitForTimeout(20);
      const state = await snapshot(page);
      assert.equal(state.jobA, null, 'A deleted account must not regain a local job handle from a late POST');
      assert.equal(state.requestA, null);
      assert.equal(state.jobB, null);
      await context.close();
    }
    {
      const {context, page} = await pageFor('library');
      await page.waitForFunction(() => Boolean(document.getElementById('crump53ContinueScene')));
      await page.click('#crump53ContinueScene');
      await page.locator('#crump53ContinuePrompt').fill('A private continuation');
      await page.evaluate(() => window.__makeHold('POST:user-a:/api/media/video/user-a-ready/continue'));
      await page.click('#crump53SubmitContinuation');
      await page.waitForFunction(() => window.__calls.some(call => call.method === 'POST' && call.url === '/api/media/video/user-a-ready/continue'));
      await switchUser(page, 'user-b');
      await page.evaluate(() => window.__release('POST:user-a:/api/media/video/user-a-ready/continue'));
      await page.waitForFunction(() => localStorage.getItem('askcrump.videoJob53:user-a') === 'user-a-continued');
      const state = await snapshot(page);
      assert.equal(state.jobB, null);
      assert.doesNotMatch(state.result, /user-a/);
      assert.equal(state.statusError, false);
      await context.close();
    }
    {
      const {context, page} = await pageFor('continue-list');
      await page.evaluate(() => window.CrumpProduct53.openFiles());
      await page.locator('[data-library-continue="user-a-ready"]').waitFor();
      await page.evaluate(() => window.__makeHold('GET:user-a:/api/media/video/user-a-ready'));
      await page.click('[data-library-continue="user-a-ready"]');
      await page.waitForFunction(() => window.__calls.some(call => call.owner === 'user-a' && call.url === '/api/media/video/user-a-ready'));
      await switchUser(page, 'user-b');
      await page.evaluate(() => window.__release('GET:user-a:/api/media/video/user-a-ready'));
      const state = await snapshot(page);
      assert.doesNotMatch(state.result + state.files, /user-a-private-video|user-a-video-file/);
      assert.equal(state.statusError, false);
      await context.close();
    }
    {
      const {context, page} = await pageFor();
      await page.addScriptTag({url: '/public/crump-5.0.js?v=video-owner-fixture-1'});
      await page.evaluate(() => {
        window.__makeHold('normalize');
        window.createImageBitmap = async () => {
          await window.__holds.get('normalize')?.promise;
          return {width: 1, height: 1, close() {}};
        };
        const file = new File([new Uint8Array([1, 2, 3])], 'private.heic', {type: 'image/heic'});
        window.__uploadOutcome = window.CrumpFileTools.upload(file, {expectedOwner: 'user-a'})
          .then(() => 'unexpected-success', error => error.code || error.message);
      });
      await switchUser(page, 'user-b');
      await page.evaluate(() => window.__release('normalize'));
      const outcome = await page.evaluate(() => window.__uploadOutcome);
      const state = await snapshot(page);
      assert.equal(outcome, 'UPLOAD_OWNER_CHANGED');
      assert.equal(state.calls.some(call => call.url === '/api/files/sign-upload'), false,
        'A reference must never be signed into B Files after HEIC normalization');
      await context.close();
    }
    assert.deepEqual(failures, []);
    process.stdout.write(JSON.stringify({success: true, scenarios: 16, pageErrors: failures}) + '\n');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
