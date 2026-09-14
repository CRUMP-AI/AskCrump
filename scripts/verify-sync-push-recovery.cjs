const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  try {
    await page.goto(
      'http://127.0.0.1:8765/tests/fixtures/sync-push-recovery.html',
      {waitUntil: 'load'},
    );
    await page.waitForFunction(() => Boolean(window.SyncManager));

    const payload = {
      chats: [{
        chat_id: '00000000-0000-4000-8000-000000000081',
        title: 'Continuity plan',
        messages: [{role: 'user', content: 'Keep this work available on my other device.'}],
        created_at: '2026-09-14T00:04:00.000Z',
        updated_at: '2026-09-14T00:04:59.000Z',
        revision: 2,
      }],
      deletedChats: [],
    };

    const first = await page.evaluate(value => window.SyncManager.push(null, value), payload);
    const firstQueue = await page.evaluate(() => JSON.parse(
      localStorage.getItem('crump_sync_queue_v4:fixture-user') || '[]',
    ));
    assert.equal(first.success, false);
    assert.equal(first.code, 'DATABASE_ERROR');
    assert.equal(first.shouldRetry, false);
    assert.equal(first.queued, true);
    assert.equal(first.flushed, false);
    assert.equal(firstQueue.length, 1);

    const second = await page.evaluate(() => window.SyncManager.flush());
    const evidence = await page.evaluate(() => ({
      secondQueue: JSON.parse(localStorage.getItem('crump_sync_queue_v4:fixture-user') || '[]'),
      requests: window.fixtureRequests,
      status: document.getElementById('fixtureStatus').textContent,
    }));
    const {secondQueue, requests} = evidence;
    assert.equal(second.success, true);
    assert.equal(second.flushed, true);
    assert.equal(secondQueue.length, 0);
    assert.equal(requests.length, 2);
    assert.deepEqual(requests[1], requests[0]);
    assert.deepEqual(requests[0], {...payload, settings: null});
    assert.equal(evidence.status, 'attempt 2');
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({first, queuedAfterFailure: firstQueue.length, second, evidence, errors}));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
