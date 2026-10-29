const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const engines = require(process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright');
const engineName = process.env.ASKCRUMP_AUTH_BROWSER || 'chromium';
assert.ok(['chromium', 'webkit'].includes(engineName), 'Unsupported auth test browser.');

const root = path.resolve(__dirname, '../public');
const fixtureUser = {
  id: 'runtime-deadline-fixture', email: 'runtime-deadline@example.test', fullName: 'Fixture User',
  isVerified: true, isGuest: false, termsAcceptedAt: '2026-10-28T12:00:00Z', subscription: 'free',
};
let mode = 'normal';
let loginPosts = 0;
let checkCalls = 0;
let held = [];
const apiPaths = new Set();
const mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml'};
const json = (response, data, headers = {}) => {
  response.writeHead(200, {'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers});
  response.end(JSON.stringify(data));
};
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    const pathname = url.pathname;
    if (pathname.startsWith('/api/')) {
      apiPaths.add(pathname);
      if (pathname === '/api/auth/login') {
        loginPosts += 1;
        const chunks = [];
        for await (const chunk of request) chunks.push(chunk);
        const credentials = JSON.parse(Buffer.concat(chunks));
        assert.equal(credentials.email, 'runtime-deadline@example.test');
        assert.equal(credentials.password, 'Fixture-password-123');
        if (mode === 'setup-response-loss') {
          // The existing setup cookie proves inbox verification. Withhold a
          // rejected login's body so its matching-cookie readback is exercised.
          const headers = {'Content-Type': 'application/json', 'Cache-Control': 'no-store'};
          response.writeHead(401, headers);
          response.flushHeaders();
          held.push({response, body: JSON.stringify({success: false, code: 'INVALID_CREDENTIALS'}), headers});
          return;
        }
        json(response, {success: true, data: {user: fixtureUser, settings: {}}}, {'Set-Cookie': 'runtime-fixture-session=active; HttpOnly; SameSite=Lax; Path=/'});
        return;
      }
      if (pathname === '/api/auth/check-session') {
        checkCalls += 1;
        const authenticated = String(request.headers.cookie || '').includes('runtime-fixture-session=active');
        const user = mode === 'setup-response-loss' ? {...fixtureUser, passwordSetupRequired: true} : fixtureUser;
        json(response, authenticated ? {success: true, authenticated: true, data: {user, settings: {}}} : {success: true, authenticated: false});
        return;
      }
      json(response, {
        success: true, user: fixtureUser, data: {chats: [], deletedChatIds: []}, chats: [], projects: [], files: [],
        preferences: {}, credits: {balance: 0}, serverTime: '2026-10-28T12:00:00Z',
        freeMessageAllowance: {limit: 5, used: 0, remaining: 5},
      });
      return;
    }
    if (pathname.startsWith('/_vercel/')) {
      response.writeHead(200, {'Content-Type': 'text/javascript'}); response.end(''); return;
    }
    const relative = pathname === '/app' || pathname === '/' ? 'app.html' : pathname.slice(1);
    const file = path.resolve(root, relative);
    if (file !== root && !file.startsWith(`${root}${path.sep}`)) throw new Error('Invalid fixture path.');
    const original = await fs.readFile(file);
    let body = original;
    if (pathname === '/runtime-body-v1.js') {
      // Exercise the production algorithm with shorter clock budgets only.
      body = original.toString().replace('ASSET_TIMEOUT_MS = 12_000', 'ASSET_TIMEOUT_MS = 350').replace('WORKSPACE_BOOT_TIMEOUT_MS = 35_000', 'WORKSPACE_BOOT_TIMEOUT_MS = 2_500');
    }
    if (mode === 'setup-response-loss' && pathname === '/auth-resilience.js') {
      body = original.toString().replace('LOGIN_TIMEOUT_MS = 30_000', 'LOGIN_TIMEOUT_MS = 350');
    }
    const headers = {'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store'};
    if ((mode === 'style-hang' && pathname === '/billing.css') || (mode === 'script-hang' && pathname === '/profile-manager.js')) {
      held.push({response, body, headers});
      return;
    }
    response.writeHead(200, headers);
    response.end(body);
  } catch (error) {
    response.writeHead(500, {'Content-Type': 'text/plain'});
    response.end(error.message);
  }
});

async function releaseHeld() {
  const pending = held;
  held = [];
  for (const item of pending) {
    if (item.response.destroyed) continue;
    item.response.writeHead(200, item.headers);
    item.response.end(item.body);
  }
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await engines[engineName].launch({headless: true, ...(executablePath && engineName === 'chromium' ? {executablePath} : {})});
  const evidence = [];
  try {
    for (const scenario of ['style-hang', 'script-hang']) {
      mode = scenario;
      loginPosts = 0;
      checkCalls = 0;
      const context = await browser.newContext({serviceWorkers: 'block'});
      const errors = [];
      await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
      await context.addInitScript(() => {
        window.__runtimeReadyEvents = 0;
        window.__runtimeInsertedScripts = [];
        window.addEventListener('crump:body-runtime-ready', () => { window.__runtimeReadyEvents += 1; });
        const append = Node.prototype.appendChild;
        Node.prototype.appendChild = function(node) {
          if (node.tagName === 'SCRIPT' && Object.keys(node.dataset).length) window.__runtimeInsertedScripts.push(node.src);
          return append.call(this, node);
        };
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${origin}/app?source=runtime-deadline-signin`, {waitUntil: 'domcontentloaded'});
      await page.locator('#loginEmail').fill('runtime-deadline@example.test');
      await page.locator('#loginPassword').fill('Fixture-password-123');
      await page.locator('#loginFormElement button[type="submit"]').click();
      await page.locator('#loginWorkspaceRecovery').waitFor({state: 'visible', timeout: 8_000});
      const failed = await page.evaluate(async () => {
        let error;
        const beforeRetry = window.__runtimeInsertedScripts.length;
        try { await window.CrumpWorkspaceRuntime.load(); } catch (failure) { error = failure; }
        return {
          state: document.documentElement.dataset.crumpBodyRuntime,
          buttonDisabled: document.querySelector('#loginFormElement button[type="submit"]').disabled,
          buttonText: document.querySelector('#loginFormElement button[type="submit"]').textContent,
          message: document.getElementById('loginError').textContent,
          owner: window.deviceAuth.session?.user?.id,
          readyEvents: window.__runtimeReadyEvents,
          insertedBeforeRetry: beforeRetry,
          insertedAfterRetry: window.__runtimeInsertedScripts.length,
          code: error?.code,
          reloadRequired: error?.reloadRequired,
        };
      });
      assert.equal(failed.state, 'failed');
      assert.equal(failed.buttonDisabled, false, 'login must recover its submit control after workspace failure');
      assert.equal(failed.buttonText, 'Sign In');
      assert.match(failed.message, /Your sign-in is safe/);
      assert.equal(failed.owner, fixtureUser.id, 'successful authentication must survive workspace asset failure');
      assert.equal(failed.readyEvents, 0);
      assert.equal(failed.code, 'WORKSPACE_ASSET_TIMEOUT');
      assert.equal(failed.reloadRequired, scenario === 'script-hang');
      if (scenario === 'script-hang') {
        assert.equal(failed.insertedBeforeRetry, 3);
        assert.equal(failed.insertedAfterRetry, 3, 'a timed-out classic script must not be inserted twice');
      }
      assert.equal(loginPosts, 1);
      assert.ok(checkCalls >= 2);
      await releaseHeld();
      await page.waitForTimeout(100);
      assert.equal(await page.evaluate(() => window.__runtimeReadyEvents), 0, 'late asset responses must not declare the failed boot ready');
      mode = 'normal';
      await page.locator('#loginWorkspaceRecovery').click();
      await page.waitForFunction(() => document.documentElement.dataset.crumpBodyRuntime === 'ready' && window.currentUser?.id === 'runtime-deadline-fixture' && getComputedStyle(document.getElementById('appContainer')).display !== 'none', null, {timeout: 10_000});
      const recovered = await page.evaluate(() => ({
        state: document.documentElement.dataset.crumpBodyRuntime,
        owner: window.currentUser.id,
        readyEvents: window.__runtimeReadyEvents,
        scriptCount: window.__runtimeInsertedScripts.length,
        uniqueScripts: new Set(window.__runtimeInsertedScripts).size,
        composerEnabled: !document.getElementById('userInput').disabled,
      }));
      assert.deepEqual(recovered, {state: 'ready', owner: fixtureUser.id, readyEvents: 1, scriptCount: 35, uniqueScripts: 35, composerEnabled: true});
      assert.equal(loginPosts, 1, 'Reload workspace must reuse the cookie instead of replaying credentials');
      assert.deepEqual(errors, []);
      evidence.push({scenario, failed, recovered, loginPosts, checkCalls});
      await context.close();
    }
    mode = 'setup-response-loss';
    loginPosts = 0;
    checkCalls = 0;
    const setupContext = await browser.newContext({serviceWorkers: 'block'});
    const setupErrors = [];
    await setupContext.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    await setupContext.addCookies([{name: 'runtime-fixture-session', value: 'active', url: origin, httpOnly: true, sameSite: 'Lax'}]);
    await setupContext.addInitScript(() => {
      window.__runtimeReadyEvents = 0;
      window.addEventListener('crump:body-runtime-ready', () => { window.__runtimeReadyEvents += 1; });
    });
    const setupPage = await setupContext.newPage();
    setupPage.on('pageerror', error => setupErrors.push(error.message));
    await setupPage.goto(`${origin}/app?source=recovered-setup-signin`, {waitUntil: 'domcontentloaded'});
    await setupPage.locator('#resetPasswordForm').waitFor({state: 'visible'});
    // A previous reset email can open its ordinary reset form while this
    // browser still holds the inbox-proof session that requires setup.
    await setupPage.goto(`${origin}/app?token=synthetic-old-reset-link`, {waitUntil: 'domcontentloaded'});
    await setupPage.locator('#showLoginFromReset').click();
    await setupPage.locator('#loginEmail').fill('runtime-deadline@example.test');
    await setupPage.locator('#loginPassword').fill('Fixture-password-123');
    await setupPage.locator('#loginFormElement button[type="submit"]').click();
    const assertSetupGate = async phase => {
      await setupPage.locator('#resetPasswordForm').waitFor({state: 'visible'});
      const result = await setupPage.evaluate(() => ({
        mode: document.getElementById('resetPasswordForm').dataset.mode,
        owner: window.currentUser?.id,
        setupRequired: window.currentUser?.passwordSetupRequired,
        workspaceVisible: getComputedStyle(document.getElementById('appContainer')).display !== 'none',
        runtimeState: document.documentElement.dataset.crumpBodyRuntime || 'unloaded',
        readyEvents: window.__runtimeReadyEvents,
        workspaceScripts: document.querySelectorAll('script[data-workspaceapp]').length,
        loginDisabled: document.querySelector('#loginFormElement button[type="submit"]').disabled,
      }));
      assert.deepEqual(result, {mode: 'setup', owner: fixtureUser.id, setupRequired: true, workspaceVisible: false, runtimeState: 'unloaded', readyEvents: 0, workspaceScripts: 0, loginDisabled: false}, phase);
      return result;
    };
    const recoveredSetup = await assertSetupGate('matching-email login readback must not bypass initial password setup');
    assert.equal(loginPosts, 1);
    assert.equal(checkCalls, 2, 'ambiguous login response gets one readback after the initial bootstrap check');
    await setupPage.reload({waitUntil: 'domcontentloaded'});
    const bootstrappedSetup = await assertSetupGate('persisted setup cookie must stay gated after reload');
    assert.equal(loginPosts, 1, 'setup recovery must not replay credentials');
    assert.deepEqual(setupErrors, []);
    evidence.push({scenario: 'recovered-password-setup', recoveredSetup, bootstrappedSetup, loginPosts, checkCalls});
    await setupContext.close();
    await releaseHeld();
    console.log(JSON.stringify({success: true, productionShell: true, realAuthAndWorkspaceScripts: true, cases: evidence, fixtureApiPaths: [...apiPaths].sort()}, null, 2));
  } finally {
    await browser.close();
    await releaseHeld();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error);
  server.closeAllConnections();
  server.close();
  process.exitCode = 1;
});
