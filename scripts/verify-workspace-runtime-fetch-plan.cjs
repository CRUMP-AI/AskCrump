const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);
const assert = require('node:assert/strict');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 1280, height: 760}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));

  try {
    await page.goto(
      'http://127.0.0.1:8765/tests/fixtures/workspace-runtime-fetch-plan.html',
      {waitUntil: 'networkidle'},
    );
    await page.waitForFunction(
      () => document.getElementById('runtimeState')?.textContent === 'ready',
      null,
      {timeout: 10_000},
    );

    const evidence = await page.evaluate(() => {
      const text = id => document.getElementById(id)?.textContent || '';
      const number = id => Number(text(id));
      return {
        runtimeState: text('runtimeState'),
        styleCount: number('styleCount'),
        maxStyles: number('maxStyles'),
        preloadCount: number('preloadCount'),
        scriptCount: number('scriptCount'),
        firstScript: text('firstScript'),
        lastScript: text('lastScript'),
        runtimeMs: number('runtimeMs'),
        fixtureBrowserErrors: number('browserErrors'),
      };
    });

    assert.equal(evidence.runtimeState, 'ready');
    assert.equal(evidence.styleCount, 19);
    assert.equal(evidence.maxStyles, 19);
    assert.equal(evidence.preloadCount, 33);
    assert.equal(evidence.scriptCount, 33);
    assert.equal(evidence.firstScript, '/onboarding.js?v=5.9.76-button-integrity-1');
    assert.equal(evidence.lastScript, '/lifecycle-manager.js?v=5.9.76-referral-cancel-recovery-1');
    assert.ok(
      evidence.runtimeMs > 0 && evidence.runtimeMs < 1_000,
      `Parallel runtime budget drifted: ${evidence.runtimeMs}ms`,
    );
    assert.equal(evidence.fixtureBrowserErrors, 0);
    assert.deepEqual(errors, []);

    console.log(JSON.stringify({...evidence, browserErrors: errors}, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
