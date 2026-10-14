const assert = require('node:assert/strict');
const {existsSync} = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const activityScript = path.join(root, 'public', 'crump-activity-center-1.0.js');
const configuredBrowser = process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || process.env.ASK_CRUMP_BROWSER_PATH
  || process.env.CODEX_BROWSER_EXECUTABLE
  || '';
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const executablePath = configuredBrowser || (existsSync(edge) ? edge : undefined);

async function activityPage(browser, {jobs = [], mode = 'success', videoJob = null} = {}) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  await page.route('https://activity.test/', route => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: '<!doctype html><html><body><main class="v1-workspace"></main></body></html>',
  }));
  await page.goto('https://activity.test/');
  await page.evaluate(({initialJobs, initialMode, initialVideoJob}) => {
    localStorage.clear();
    window.__ASKCRUMP_ACTIVITY_TEST__ = true;
    window.__ASKCRUMP_ACTIVITY_TEST_CONFIG__ = {requestTimeoutMs: 30};
    window.currentUser = {id: 'activity-test-user'};
    window.CrumpProductLoader = {authenticatedUserId: () => window.currentUser?.id || ''};
    window.CrumpVision = {navigate: destination => { window.__activityDestination = destination; }};
    window.chats = [];
    window.__activityApiJobs = initialJobs;
    window.__activityApiMode = initialMode;
    window.__activityApiCalls = 0;
    window.fetch = (_url, options = {}) => {
      window.__activityApiCalls += 1;
      if (window.__activityApiMode === 'success') {
        return Promise.resolve(new Response(JSON.stringify({jobs: window.__activityApiJobs}), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }));
      }
      return new Promise((resolve, reject) => {
        const abort = () => reject(new DOMException('Aborted', 'AbortError'));
        if (options.signal?.aborted) {
          abort();
          return;
        }
        options.signal?.addEventListener('abort', abort, {once: true});
      });
    };
    if (initialVideoJob) {
      localStorage.setItem(
        `askcrump.videoJob53:${encodeURIComponent(window.currentUser.id)}`,
        JSON.stringify(initialVideoJob),
      );
    }
  }, {initialJobs: jobs, initialMode: mode, initialVideoJob: videoJob});
  await page.addScriptTag({path: activityScript});
  await page.waitForFunction(() => Boolean(window.__CrumpActivityCenterTestHooks));
  return page;
}

async function verifyTerminalPermanence(browser) {
  const timestamp = new Date().toISOString();
  const page = await activityPage(browser, {
    jobs: [
      {id: 'ready-job', status: 'completed', createdAt: timestamp, updatedAt: timestamp},
      {id: 'failed-job', status: 'failed', createdAt: timestamp, updatedAt: timestamp},
    ],
  });
  try {
    await page.waitForFunction(() => {
      const counts = window.CrumpActivityCenter?.counts?.();
      return counts?.ready === 1 && counts?.failed === 1;
    });
    const statuses = await page.evaluate(() => {
      const storageKey = `askcrump.videoJob53:${encodeURIComponent(window.currentUser.id)}`;
      for (const jobId of ['ready-job', 'failed-job']) {
        localStorage.setItem(storageKey, JSON.stringify({
          version: 1,
          userId: window.currentUser.id,
          jobId,
          updatedAt: Date.now(),
        }));
        window.__CrumpActivityCenterTestHooks.reconcileStoredVideo();
      }
      return Object.fromEntries(
        window.__CrumpActivityCenterTestHooks.snapshot().items
          .filter(item => item.jobId)
          .map(item => [item.jobId, item.status]),
      );
    });
    assert.deepEqual(statuses, {'failed-job': 'failed', 'ready-job': 'ready'});
  } finally {
    await page.close();
  }
}

async function verifyFailurePriorityAndFocus(browser) {
  const page = await activityPage(browser);
  try {
    const result = await page.evaluate(() => {
      const base = Date.now();
      for (let index = 0; index < 18; index += 1) {
        window.CrumpActivityCenter.report({
          id: `video:ready-${index}`,
          jobId: `ready-${index}`,
          source: 'video',
          kind: 'video',
          status: 'ready',
          createdAt: base - index,
          updatedAt: base - index,
        });
      }
      window.CrumpActivityCenter.report({
        id: 'video:failed-priority',
        jobId: 'failed-priority',
        source: 'video',
        kind: 'video',
        status: 'failed',
        createdAt: base - 50,
        updatedAt: base - 50,
      });
      const trigger = document.getElementById('crumpActivityTrigger');
      trigger.focus();
      window.CrumpActivityCenter.open();
      const firstStatus = document.querySelector('[data-activity-status]')?.dataset.activityStatus || '';
      document.querySelector('.crump-activity-action')?.click();
      const itemCloseFocus = document.activeElement?.id || '';
      window.CrumpActivityCenter.open();
      document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
      return {
        counts: window.CrumpActivityCenter.counts(),
        firstStatus,
        triggerClass: trigger.className,
        triggerLabel: trigger.getAttribute('aria-label'),
        badge: trigger.querySelector('.crump-activity-badge')?.textContent || '',
        itemCloseFocus,
        outsideCloseFocus: document.activeElement?.id || '',
        persistedCount: JSON.parse(localStorage.getItem(
          `askcrump.activityCenter.v1:${encodeURIComponent(window.currentUser.id)}`,
        )).items.length,
      };
    });
    assert.deepEqual(result.counts, {queued: 0, running: 0, ready: 17, failed: 1});
    assert.equal(result.firstStatus, 'failed');
    assert.match(result.triggerClass, /\bhas-attention\b/);
    assert.match(result.triggerLabel, /1 needs attention/);
    assert.equal(result.badge, '1');
    assert.equal(result.persistedCount, 18);
    assert.equal(result.itemCloseFocus, 'crumpActivityTrigger');
    assert.equal(result.outsideCloseFocus, 'crumpActivityTrigger');
  } finally {
    await page.close();
  }
}

async function verifyTimeoutAndBackoff(browser) {
  const page = await activityPage(browser, {
    mode: 'hang',
    videoJob: {
      version: 1,
      userId: 'activity-test-user',
      jobId: 'running-job',
      updatedAt: Date.now(),
    },
  });
  try {
    await page.waitForFunction(() => (
      window.__CrumpActivityCenterTestHooks.snapshot().networkIssue === 'timeout'
    ));
    const firstTimeout = await page.evaluate(async () => {
      const hooks = window.__CrumpActivityCenterTestHooks;
      const beforeCalls = window.__activityApiCalls;
      const nonForced = await hooks.refreshVideos({force: false});
      const snapshot = hooks.snapshot();
      return {
        beforeCalls,
        afterCalls: window.__activityApiCalls,
        nonForced,
        snapshot,
        networkState: document.getElementById('crumpActivitySummary')?.dataset.networkState,
        note: document.getElementById('crumpActivityNetworkNote')?.textContent || '',
      };
    });
    assert.equal(firstTimeout.nonForced, false);
    assert.equal(firstTimeout.afterCalls, firstTimeout.beforeCalls);
    assert.equal(firstTimeout.snapshot.networkUnavailable, true);
    assert.equal(firstTimeout.snapshot.networkIssue, 'timeout');
    assert.equal(firstTimeout.snapshot.networkFailureCount, 1);
    assert.equal(firstTimeout.snapshot.nextNetworkDelay, 60_000);
    assert.ok(firstTimeout.snapshot.lastNetworkAt > 0);
    assert.equal(firstTimeout.networkState, 'delayed');
    assert.match(firstTimeout.note, /took too long/i);

    const bounded = await page.evaluate(async () => {
      const hooks = window.__CrumpActivityCenterTestHooks;
      for (let index = 0; index < 5; index += 1) await hooks.refreshVideos({force: true});
      return hooks.snapshot();
    });
    assert.equal(bounded.networkFailureCount, 4);
    assert.equal(bounded.nextNetworkDelay, 480_000);

    const recovered = await page.evaluate(async () => {
      window.__activityApiMode = 'success';
      window.__activityApiJobs = [{
        id: 'running-job',
        status: 'running',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }];
      await window.__CrumpActivityCenterTestHooks.refreshVideos({force: true});
      return window.__CrumpActivityCenterTestHooks.snapshot();
    });
    assert.equal(recovered.networkUnavailable, false);
    assert.equal(recovered.networkIssue, '');
    assert.equal(recovered.networkFailureCount, 0);
    assert.equal(recovered.nextNetworkDelay, 30_000);

    const intentional = await page.evaluate(async () => {
      const hooks = window.__CrumpActivityCenterTestHooks;
      const before = hooks.snapshot().lastNetworkAt;
      window.__activityApiMode = 'hang';
      const request = hooks.refreshVideos({force: true});
      hooks.abortNetwork('visibility');
      await request;
      const afterVisibility = hooks.snapshot();
      const signoutRequest = hooks.refreshVideos({force: true});
      window.dispatchEvent(new Event('crump:authentication-required'));
      await signoutRequest;
      return {before, afterVisibility, afterSignout: hooks.snapshot()};
    });
    assert.equal(intentional.afterVisibility.networkUnavailable, false);
    assert.equal(intentional.afterVisibility.networkIssue, '');
    assert.equal(intentional.afterVisibility.networkFailureCount, 0);
    assert.equal(intentional.afterVisibility.lastNetworkAt, intentional.before);
    assert.equal(intentional.afterSignout.userId, '');
    assert.equal(intentional.afterSignout.networkUnavailable, false);
    assert.equal(intentional.afterSignout.networkIssue, '');
  } finally {
    await page.close();
  }
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    await verifyTerminalPermanence(browser);
    await verifyFailurePriorityAndFocus(browser);
    await verifyTimeoutAndBackoff(browser);
    process.stdout.write('Activity center behavioral verification passed.\n');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
