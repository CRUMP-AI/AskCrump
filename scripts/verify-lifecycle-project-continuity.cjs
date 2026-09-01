const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('http://127.0.0.1:8765/tests/fixtures/lifecycle-project-continuity.html', {
    waitUntil: 'domcontentloaded',
  });
  await page.evaluate(() => window.CrumpLifecycle.evaluate({force: true}));
  const primary = page.locator('.crump-lifecycle-primary');
  await primary.waitFor({state: 'attached'});
  assert.equal(await primary.textContent(), 'Keep it in a Project');
  await primary.click();
  await page.waitForFunction(() => window.__fixture.keepCalls === 1);

  const result = await page.evaluate(() => ({
    ...window.__fixture,
    projectButtonText: document.querySelector('.outcome-project-btn')?.textContent,
    projectButtonSaved: document.querySelector('.outcome-project-btn')?.dataset.saved,
    continuityText: document.querySelector('.outcome-continuity-prompt')?.textContent,
  }));
  assert.equal(result.keepCalls, 1);
  assert.equal(result.genericProjectOpens, 0);
  assert.deepEqual(result.projectArgs, [{projectId: null}]);
  assert.equal(result.projectButtonText, 'Open Project');
  assert.equal(result.projectButtonSaved, 'true');
  assert.equal(result.continuityText, 'Saved to "Launch plan".');
  assert.deepEqual(result.actions, ['shown', 'acted']);
  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({result, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
