const assert = require('node:assert/strict');
const path = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const analyticsPath = path.resolve(process.cwd(), 'public', 'product-analytics.js');

async function openScenario(browser, options = {}) {
  const page = await browser.newPage();
  const browserErrors = [];
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.setContent('<!doctype html><html><body></body></html>');
  await page.evaluate(config => {
    const realDate = window.Date;
    const nativeSetTimeout = window.setTimeout.bind(window);
    const state = {
      owner: config.owner || 'account-a',
      revision: 1,
      visibility: config.visibility || 'visible',
      online: config.online !== false,
      now: config.now || '2026-10-24T18:00:00.000Z',
      behaviors: [...(config.behaviors || [{type: 'response', status: 200, body: {
        success: true, accepted: true, recorded: true,
      }}])],
      calls: [],
      deferred: [],
      scrubbers: new Map(),
    };
    window.__workspaceOpenedFixture = state;
    window.Date = class FixtureDate extends realDate {
      constructor(...args) {
        super(...(args.length ? args : [state.now]));
      }
      static now() { return new realDate(state.now).getTime(); }
    };
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => state.visibility,
    });
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      get: () => state.online,
    });
    window.setTimeout = (callback, delay, ...args) => nativeSetTimeout(
      callback,
      Number(delay) >= 1000 ? 12 : delay,
      ...args,
    );
    window.CrumpAuthBoundary = Object.freeze({
      authenticatedUserId: () => state.owner,
      revision: () => state.revision,
      register(name, scrub) {
        state.scrubbers.set(name, scrub);
        return () => state.scrubbers.delete(name);
      },
    });
    const fixtureResponse = behavior => new Response(JSON.stringify(behavior.body || {}), {
      status: behavior.status || 200,
      headers: {'Content-Type': 'application/json'},
    });
    window.fetch = async (url, request = {}) => {
      const headers = Object.fromEntries(new Headers(request.headers || {}).entries());
      state.calls.push({
        url: String(url),
        method: request.method,
        credentials: request.credentials,
        keepalive: request.keepalive,
        headers,
        body: JSON.parse(String(request.body || '{}')),
      });
      const behavior = state.behaviors.shift() || {
        type: 'response',
        status: 200,
        body: {success: true, accepted: true, recorded: true},
      };
      if (behavior.type === 'reject') throw new TypeError('fixture network rejection');
      if (behavior.type !== 'deferred') return fixtureResponse(behavior);
      return new Promise((resolve, reject) => {
        const deferred = {
          resolve: (body = behavior.body || {success: true, accepted: true, recorded: true}) => {
            resolve(fixtureResponse({...behavior, body}));
          },
          reject,
        };
        state.deferred.push(deferred);
        if (!behavior.ignoreAbort && request.signal) {
          request.signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          }, {once: true});
        }
      });
    };
    window.__setWorkspaceVisibility = visibility => {
      state.visibility = visibility;
      document.dispatchEvent(new Event('visibilitychange'));
    };
    window.__setWorkspaceOnline = online => {
      state.online = Boolean(online);
      if (state.online) window.dispatchEvent(new Event('online'));
    };
    window.__setWorkspaceNow = now => { state.now = now; };
    window.__rotateWorkspaceOwner = owner => {
      state.revision += 1;
      for (const scrub of state.scrubbers.values()) {
        scrub({reason: 'authenticated-user-changed', nextUserId: owner, revision: state.revision});
      }
      state.owner = owner;
    };
    window.__resolveWorkspaceDeferred = (index, body) => state.deferred[index]?.resolve(body);
  }, options);
  await page.addScriptTag({path: analyticsPath});
  return {page, browserErrors};
}

async function waitForCalls(page, count) {
  await page.waitForFunction(expected => (
    window.__workspaceOpenedFixture.calls.length === expected
  ), count, {timeout: 2000});
}

async function callCount(page) {
  return page.evaluate(() => window.__workspaceOpenedFixture.calls.length);
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  try {
    {
      const {page, browserErrors} = await openScenario(browser);
      await page.evaluate(() => Promise.all([
        window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible(),
        window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible(),
      ]));
      await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      assert.equal(await callCount(page), 1, 'success must be single-flight and recorded once');
      assert.deepEqual(browserErrors, []);
      results.push('success-no-duplicate-single-flight');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {behaviors: [{
        type: 'response', status: 200, body: {success: true, accepted: true, recorded: false},
      }]});
      assert.equal(await page.evaluate(() => (
        window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible()
      )), true);
      await page.waitForTimeout(50);
      assert.equal(await callCount(page), 1, 'an idempotent duplicate is accepted without retry');
      results.push('duplicate-accepted');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {behaviors: [
        {type: 'response', status: 200, body: {success: true, recorded: false}},
        {type: 'response', status: 200, body: {success: true, accepted: true, recorded: true}},
      ]});
      void await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      await waitForCalls(page, 2);
      assert.equal(await page.evaluate(() => (
        window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible()
      )), true);
      assert.equal(await callCount(page), 2, '200 recorded:false without accepted must retry');
      results.push('legacy-false-retried');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {behaviors: [
        {type: 'response', status: 503, body: {success: false}},
        {type: 'reject'},
        {type: 'response', status: 200, body: {success: true, accepted: true, recorded: true}},
      ]});
      void await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      await waitForCalls(page, 3);
      await page.waitForTimeout(30);
      assert.equal(await callCount(page), 3);
      results.push('non-2xx-and-rejection-retried');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {online: false});
      void await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      await page.waitForTimeout(25);
      assert.equal(await callCount(page), 0, 'offline entry must not consume an attempt');
      await page.evaluate(() => window.__setWorkspaceOnline(true));
      await waitForCalls(page, 1);
      results.push('offline-online-wake');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {visibility: 'hidden'});
      void await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      await page.waitForTimeout(25);
      assert.equal(await callCount(page), 0, 'hidden entry must not consume an attempt');
      await page.evaluate(() => window.__setWorkspaceVisibility('visible'));
      await waitForCalls(page, 1);
      results.push('hidden-visible-wake');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {behaviors: [
        {type: 'deferred', ignoreAbort: true},
        {type: 'response', status: 200, body: {success: true, accepted: true, recorded: true}},
      ]});
      await page.evaluate(() => { void window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible(); });
      await waitForCalls(page, 1);
      await page.evaluate(() => {
        window.__rotateWorkspaceOwner('account-b');
        void window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible();
      });
      await waitForCalls(page, 2);
      await page.evaluate(() => window.__resolveWorkspaceDeferred(0, {
        success: true, accepted: true, recorded: true,
      }));
      await page.waitForTimeout(50);
      await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      const calls = await page.evaluate(() => window.__workspaceOpenedFixture.calls);
      assert.equal(calls.length, 2, 'stale completion must not mark or retry the new owner');
      assert.equal(calls[0].headers['x-ask-crump-expected-owner'], 'account-a');
      assert.equal(calls[1].headers['x-ask-crump-expected-owner'], 'account-b');
      results.push('auth-rotation-fenced');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {
        now: '2026-10-24T23:59:59.000Z',
        behaviors: [
          {type: 'response', status: 200, body: {success: true, accepted: true, recorded: true}},
          {type: 'response', status: 200, body: {success: true, accepted: true, recorded: true}},
        ],
      });
      await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      await page.evaluate(() => {
        window.__setWorkspaceVisibility('hidden');
        window.__setWorkspaceNow('2026-10-25T00:00:01.000Z');
        window.__setWorkspaceVisibility('visible');
      });
      await waitForCalls(page, 2);
      const keys = await page.evaluate(() => (
        window.__workspaceOpenedFixture.calls.map(call => call.body.eventKey)
      ));
      assert.deepEqual(keys, ['workspace-open:2026-10-24', 'workspace-open:2026-10-25']);
      results.push('utc-rollover-recomputed');
      await page.close();
    }

    {
      const {page} = await openScenario(browser, {behaviors: [
        {type: 'response', status: 503},
        {type: 'response', status: 503},
        {type: 'response', status: 503},
        {type: 'response', status: 200, body: {success: true, accepted: true, recorded: true}},
      ]});
      void await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      await waitForCalls(page, 3);
      await page.waitForTimeout(60);
      await page.evaluate(() => window.__setWorkspaceOnline(true));
      await page.waitForTimeout(30);
      assert.equal(await callCount(page), 3, 'retry cap must survive later same-day wake events');
      results.push('bounded-retry-cap');
      await page.close();
    }

    {
      const {page, browserErrors} = await openScenario(browser, {owner: 'guest-session'});
      await page.evaluate(() => window.CrumpAnalytics.recordWorkspaceOpenedWhenVisible());
      const call = await page.evaluate(() => window.__workspaceOpenedFixture.calls[0]);
      assert.equal(call.url, '/api/analytics/events');
      assert.equal(call.method, 'POST');
      assert.equal(call.credentials, 'same-origin');
      assert.equal(call.keepalive, true);
      assert.deepEqual(call.body, {
        eventName: 'WorkspaceOpened',
        eventKey: 'workspace-open:2026-10-24',
      });
      assert.equal(call.headers['x-ask-crump-expected-owner'], 'guest-session');
      assert.equal(JSON.stringify(call.body).includes('guest-session'), false);
      assert.deepEqual(browserErrors, []);
      results.push('guest-content-free-contract');
      await page.close();
    }

    process.stdout.write(JSON.stringify({runs: results.length, results}) + '\n');
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write((error.stack || error) + '\n');
  process.exitCode = 1;
});
