const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const executablePath = process.env.ASK_CRUMP_BROWSER_PATH
  || process.env.CODEX_BROWSER_EXECUTABLE
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

async function run(browser, mode) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${baseUrl}/tests/fixtures/lifecycle-referral-recovery.html?mode=${mode}`, {
    waitUntil: 'domcontentloaded',
  });
  await page.evaluate(() => window.CrumpLifecycle.evaluate({force: true}));
  const primary = page.locator('.crump-lifecycle-primary');
  await primary.waitFor({state: 'visible'});
  assert.equal(await primary.textContent(), 'Share Ask Crump');
  await primary.click();
  await page.waitForFunction(() => window.__fixture.actions.includes('acted'));
  await page.waitForTimeout(100);
  const result = await page.evaluate(() => window.__fixture);
  await page.close();
  return {result, errors};
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath});
  try {
    const canceled = await run(browser, 'cancel');
    assert.deepEqual(canceled.result.actions, ['shown', 'acted']);
    assert.equal(canceled.result.shareCalls, 1);
    assert.equal(canceled.result.clipboardCalls, 0);
    assert.deepEqual(canceled.result.analytics, []);
    assert.deepEqual(canceled.result.toasts, []);
    assert.deepEqual(canceled.errors, []);

    const unavailable = await run(browser, 'unavailable');
    assert.deepEqual(unavailable.result.actions, ['shown', 'acted']);
    assert.equal(unavailable.result.shareCalls, 1);
    assert.equal(unavailable.result.clipboardCalls, 1);
    assert.deepEqual(unavailable.result.analytics, []);
    assert.deepEqual(unavailable.result.toasts, [[
      'Sharing is unavailable right now. Nothing was posted or sent.',
      'error',
    ]]);
    assert.deepEqual(unavailable.errors, []);

    const clipboard = await run(browser, 'clipboard');
    assert.deepEqual(clipboard.result.actions, ['shown', 'acted']);
    assert.equal(clipboard.result.shareCalls, 1);
    assert.equal(clipboard.result.clipboardCalls, 1);
    assert.match(clipboard.result.clipboardValue, /acquisition=referral&source=response-share/);
    assert.equal(clipboard.result.analytics.length, 1);
    assert.equal(clipboard.result.analytics[0].eventName, 'ResponseShared');
    assert.equal(clipboard.result.analytics[0].payload.source, 'useful_prompt_clipboard');
    assert.deepEqual(clipboard.result.toasts, [['Ask Crump link copied', 'success']]);
    assert.deepEqual(clipboard.errors, []);

    console.log('Lifecycle referral recovery proof passed: cancel stays quiet, true failure is explicit, and clipboard success records only after delivery.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
