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

async function activityPage(browser, {
  jobs = [],
  codeActivity = [],
  mode = 'success',
  videoJob = null,
  requestTimeoutMs = 30,
  foreignActivityItems = [],
} = {}) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  await page.route('https://activity.test/', route => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: '<!doctype html><html><body><main class="v1-workspace"></main></body></html>',
  }));
  await page.goto('https://activity.test/');
  await page.evaluate(({
    initialJobs,
    initialCodeActivity,
    initialMode,
    initialVideoJob,
    initialRequestTimeoutMs,
    initialForeignActivityItems,
  }) => {
    localStorage.clear();
    window.__ASKCRUMP_ACTIVITY_TEST__ = true;
    window.__ASKCRUMP_ACTIVITY_TEST_CONFIG__ = {requestTimeoutMs: initialRequestTimeoutMs};
    window.currentUser = {id: 'activity-test-user'};
    window.CrumpProductLoader = {authenticatedUserId: () => window.currentUser?.id || ''};
    window.CrumpVision = {navigate: destination => { window.__activityDestination = destination; }};
    window.CrumpCodeLoader = {
      open: options => {
        window.__openedCodeTask = {...options};
        return Promise.resolve(true);
      },
    };
    window.chats = [];
    window.__activityApiJobs = initialJobs;
    window.__activityApiCode = initialCodeActivity;
    window.__activityApiMode = initialMode;
    window.__activityApiCalls = 0;
    window.__activityApiRequests = [];
    window.__activityDeferredRequests = [];
    window.fetch = (url, options = {}) => {
      const href = String(url || '');
      window.__activityApiCalls += 1;
      window.__activityApiRequests.push({url: href, method: options.method || 'GET'});
      if (window.__activityApiMode === 'success' || window.__activityApiMode === 'code-failure') {
        if (window.__activityApiMode === 'code-failure' && href.includes('/api/code/activity')) {
          return Promise.resolve(new Response(JSON.stringify({error: 'temporarily unavailable'}), {
            status: 503,
            headers: {'Content-Type': 'application/json'},
          }));
        }
        const body = href.includes('/api/code/activity')
          ? {activity: window.__activityApiCode}
          : {jobs: window.__activityApiJobs};
        return Promise.resolve(new Response(JSON.stringify(body), {
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
        if (window.__activityApiMode === 'deferred') {
          window.__activityDeferredRequests.push({url: href, resolve, reject});
        }
      });
    };
    if (initialVideoJob) {
      localStorage.setItem(
        `askcrump.videoJob53:${encodeURIComponent(window.currentUser.id)}`,
        JSON.stringify(initialVideoJob),
      );
    }
    if (initialForeignActivityItems.length) {
      localStorage.setItem('askcrump.activityCenter.v1:foreign-user', JSON.stringify({
        version: 1,
        userId: 'foreign-user',
        items: initialForeignActivityItems,
      }));
    }
  }, {
    initialJobs: jobs,
    initialCodeActivity: codeActivity,
    initialMode: mode,
    initialVideoJob: videoJob,
    initialRequestTimeoutMs: requestTimeoutMs,
    initialForeignActivityItems: foreignActivityItems,
  });
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

async function verifyCodeActivityContinuity(browser) {
  const timestamp = new Date().toISOString();
  const foreignTimestamp = Date.now();
  const page = await activityPage(browser, {
    codeActivity: [
      {
        id: 'code-task-ready',
        projectId: 'project-exact',
        status: 'completed',
        createdAt: timestamp,
        updatedAt: timestamp,
        completedAt: timestamp,
        objective: 'must never reach browser activity state',
        repository: 'https://example.invalid/private-context',
        resultPatch: 'secret patch content',
        failureDetail: 'private failure detail',
        usageReceipt: 'private usage receipt',
      },
      {
        id: 'code-task-attention',
        projectId: 'project-review',
        status: 'awaiting_approval',
        createdAt: timestamp,
        updatedAt: timestamp,
      },
    ],
    foreignActivityItems: [{
      id: 'code:foreign-task',
      taskId: 'foreign-task',
      projectId: 'foreign-project',
      codeStatus: 'running',
      source: 'code',
      kind: 'code',
      status: 'running',
      createdAt: foreignTimestamp,
      updatedAt: foreignTimestamp,
    }],
  });
  try {
    await page.waitForFunction(() => {
      const codeItems = window.__CrumpActivityCenterTestHooks.snapshot().items
        .filter(item => item.kind === 'code');
      return codeItems.length === 2;
    });
    const result = await page.evaluate(() => {
      const hooks = window.__CrumpActivityCenterTestHooks;
      const codeItems = hooks.snapshot().items.filter(item => item.kind === 'code');
      const persisted = JSON.parse(localStorage.getItem(
        `askcrump.activityCenter.v1:${encodeURIComponent(window.currentUser.id)}`,
      ));
      window.CrumpActivityCenter.open();
      document.querySelector('[data-activity-id="code:code-task-ready"] .crump-activity-action')?.click();
      return {
        codeItems,
        persistedCodeItems: persisted.items.filter(item => item.kind === 'code'),
        foreignVisible: hooks.snapshot().items.some(item => item.taskId === 'foreign-task'),
        openedCodeTask: window.__openedCodeTask,
        requests: window.__activityApiRequests,
      };
    });

    assert.equal(result.codeItems.length, 2);
    assert.equal(result.foreignVisible, false);
    assert.deepEqual(result.openedCodeTask, {
      projectId: 'project-exact',
      taskId: 'code-task-ready',
    });
    assert.deepEqual(
      result.codeItems.map(item => [item.taskId, item.codeStatus, item.status]).sort(),
      [
        ['code-task-attention', 'awaiting_approval', 'failed'],
        ['code-task-ready', 'completed', 'ready'],
      ],
    );
    const allowedKeys = [
      'codeStatus', 'createdAt', 'id', 'kind', 'projectId', 'source',
      'status', 'taskId', 'updatedAt',
    ];
    for (const item of [...result.codeItems, ...result.persistedCodeItems]) {
      assert.deepEqual(Object.keys(item).sort(), allowedKeys);
    }
    assert.ok(result.requests.length >= 2);
    assert.ok(result.requests.every(request => request.method === 'GET'));
    assert.ok(result.requests.every(request => (
      request.url === '/api/media/video' || request.url === '/api/code/activity'
    )));
  } finally {
    await page.close();
  }
}

async function verifyCodeOwnerFence(browser) {
  const page = await activityPage(browser, {
    mode: 'deferred',
    requestTimeoutMs: 1000,
  });
  try {
    await page.waitForFunction(() => window.__activityDeferredRequests.length === 2);
    const result = await page.evaluate(async () => {
      window.currentUser = {id: 'replacement-user'};
      const timestamp = new Date().toISOString();
      for (const request of window.__activityDeferredRequests) {
        const body = request.url.includes('/api/code/activity')
          ? {activity: [{
            id: 'late-owner-task',
            projectId: 'late-owner-project',
            status: 'running',
            createdAt: timestamp,
            updatedAt: timestamp,
          }]}
          : {jobs: []};
        request.resolve(new Response(JSON.stringify(body), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }));
      }
      await new Promise(resolve => setTimeout(resolve, 30));
      return window.__CrumpActivityCenterTestHooks.snapshot();
    });
    assert.equal(result.userId, 'activity-test-user');
    assert.equal(result.items.some(item => item.taskId === 'late-owner-task'), false);
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

async function verifyIndependentFeedBackoff(browser) {
  const timestamp = new Date().toISOString();
  const page = await activityPage(browser, {
    mode: 'code-failure',
    jobs: [{
      id: 'healthy-running-video',
      status: 'running',
      createdAt: timestamp,
      updatedAt: timestamp,
    }],
  });
  try {
    await page.waitForFunction(() => (
      window.__CrumpActivityCenterTestHooks.snapshot().feedFailureCount.code === 1
    ));
    const snapshot = await page.evaluate(() => window.__CrumpActivityCenterTestHooks.snapshot());
    assert.deepEqual(snapshot.feedFailureCount, {video: 0, code: 1});
    assert.equal(snapshot.networkUnavailable, true);
    assert.equal(snapshot.nextNetworkDelay, 30_000);
    assert.equal(snapshot.items.some(item => item.jobId === 'healthy-running-video'), true);
  } finally {
    await page.close();
  }
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    await verifyTerminalPermanence(browser);
    await verifyCodeActivityContinuity(browser);
    await verifyCodeOwnerFence(browser);
    await verifyFailurePriorityAndFocus(browser);
    await verifyTimeoutAndBackoff(browser);
    await verifyIndependentFeedBackoff(browser);
    process.stdout.write('Activity center behavioral verification passed.\n');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
