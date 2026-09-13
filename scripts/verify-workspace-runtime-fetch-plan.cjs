const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);
const assert = require('node:assert/strict');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];

  try {
    const results = {};
    for (const mode of ['normal', 'style-retry', 'script-retry']) {
      const page = await browser.newPage({viewport: {width: 1280, height: 760}});
      page.on('console', message => { if (message.type() === 'error') errors.push(`${mode}: ${message.text()}`); });
      page.on('pageerror', error => errors.push(`${mode}: ${error.message}`));
      await page.goto(
        `http://127.0.0.1:8765/tests/fixtures/workspace-runtime-fetch-plan.html?mode=${mode}`,
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
          styleAttempts: number('styleAttempts'),
          scriptAttempts: number('scriptAttempts'),
          readyEvents: number('readyEvents'),
          failureMessage: text('failureMessage'),
          fixtureBrowserErrors: number('browserErrors'),
        };
      });

      assert.equal(evidence.runtimeState, 'ready');
      assert.equal(evidence.styleCount, mode === 'style-retry' ? 18 : 17);
      assert.equal(evidence.maxStyles, 17);
      assert.equal(evidence.preloadCount, 34);
      assert.equal(evidence.scriptCount, mode === 'script-retry' ? 35 : 34);
      assert.equal(evidence.firstScript, '/onboarding.js?v=5.9.76-button-integrity-1');
      assert.equal(evidence.lastScript, '/lifecycle-manager.js?v=5.9.76-lifecycle-idle-send-1');
      assert.equal(evidence.styleAttempts, mode === 'style-retry' ? 2 : 1);
      assert.equal(evidence.scriptAttempts, mode === 'script-retry' ? 2 : 1);
      assert.equal(evidence.readyEvents, 1);
      assert.equal(evidence.failureMessage, 'none');
      assert.ok(
        evidence.runtimeMs > 0 && evidence.runtimeMs < 1_000,
        `Parallel runtime budget drifted in ${mode}: ${evidence.runtimeMs}ms`,
      );
      assert.equal(evidence.fixtureBrowserErrors, 0);
      results[mode] = evidence;
      await page.close();
    }

    const failPage = await browser.newPage({viewport: {width: 1280, height: 760}});
    failPage.on('console', message => { if (message.type() === 'error') errors.push(`style-fail: ${message.text()}`); });
    failPage.on('pageerror', error => errors.push(`style-fail: ${error.message}`));
    await failPage.goto(
      'http://127.0.0.1:8765/tests/fixtures/workspace-runtime-fetch-plan.html?mode=style-fail',
      {waitUntil: 'networkidle'},
    );
    await failPage.waitForFunction(
      () => document.getElementById('runtimeState')?.textContent === 'failed',
      null,
      {timeout: 10_000},
    );
    const failed = await failPage.evaluate(() => ({
      runtimeState: document.getElementById('runtimeState')?.textContent,
      styleCount: Number(document.getElementById('styleCount')?.textContent),
      scriptCount: Number(document.getElementById('scriptCount')?.textContent),
      styleAttempts: Number(document.getElementById('styleAttempts')?.textContent),
      readyEvents: Number(document.getElementById('readyEvents')?.textContent),
      failureMessage: document.getElementById('failureMessage')?.textContent,
    }));
    assert.deepEqual(failed, {
      runtimeState: 'failed',
      styleCount: 18,
      scriptCount: 0,
      styleAttempts: 2,
      readyEvents: 0,
      failureMessage: 'Ask Crump could not finish loading your workspace. Your sign-in is safe—check your connection and reload to try again.',
    });
    await failPage.evaluate(async () => {
      window.__fixtureAllowAssetSuccess = true;
      await window.__fixtureRunRuntime();
    });
    await failPage.waitForFunction(
      () => document.getElementById('runtimeState')?.textContent === 'ready',
      null,
      {timeout: 10_000},
    );
    const recovered = await failPage.evaluate(() => ({
      runtimeState: document.getElementById('runtimeState')?.textContent,
      styleCount: Number(document.getElementById('styleCount')?.textContent),
      scriptCount: Number(document.getElementById('scriptCount')?.textContent),
      styleAttempts: Number(document.getElementById('styleAttempts')?.textContent),
      readyEvents: Number(document.getElementById('readyEvents')?.textContent),
      failureMessage: document.getElementById('failureMessage')?.textContent,
    }));
    assert.deepEqual(recovered, {
      runtimeState: 'ready',
      styleCount: 19,
      scriptCount: 34,
      styleAttempts: 3,
      readyEvents: 1,
      failureMessage: 'none',
    });
    results['style-fail-recovery'] = {failed, recovered};
    await failPage.close();

    assert.deepEqual(errors, []);

    console.log(JSON.stringify({...results, browserErrors: errors}, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
