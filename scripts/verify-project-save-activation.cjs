const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const consoleErrors = [];
  const openFixture = async query => {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => consoleErrors.push(error.message));
    await page.goto(`http://127.0.0.1:8765/tests/fixtures/project-save-stall.html${query}`, {
      waitUntil: 'networkidle',
    });
    await page.waitForFunction(() => {
      const button = document.querySelector('.outcome-project-btn');
      return button && !button.disabled && button.textContent.includes('Start a Project');
    });
    return page;
  };

  const stalledPage = await openFixture('');
  await stalledPage.locator('.outcome-project-btn').click();
  await stalledPage.waitForFunction(() => window.__fixture.projectRequests === 1);
  const pending = await stalledPage.evaluate(() => ({
    button: document.querySelector('.outcome-project-btn')?.textContent || '',
    busy: document.querySelector('.outcome-project-btn')?.getAttribute('aria-busy') || '',
    prompt: document.querySelector('.outcome-continuity-prompt')?.textContent || '',
  }));
  await stalledPage.waitForFunction(() => window.__fixture.abortedProjectRequests === 1);
  await stalledPage.waitForFunction(() => !document.querySelector('.outcome-project-btn')?.disabled);
  const recovered = await stalledPage.evaluate(() => ({
    button: document.querySelector('.outcome-project-btn')?.textContent || '',
    prompt: document.querySelector('.outcome-continuity-prompt')?.textContent || '',
    analytics: window.__fixture.analytics,
    projectBodies: window.__fixture.projectBodies,
    errors: Number(document.querySelector('#fixtureErrors')?.textContent || 0),
  }));
  await stalledPage.screenshot({path: 'artifacts/project-save-recovery.png', fullPage: true});

  const successPage = await openFixture('?save=success');
  await successPage.locator('.outcome-project-btn').click();
  await successPage.waitForFunction(() => document.querySelector('.outcome-project-btn')?.textContent === 'Open Project');
  const saved = await successPage.evaluate(() => ({
    button: document.querySelector('.outcome-project-btn')?.textContent || '',
    prompt: document.querySelector('.outcome-continuity-prompt')?.textContent || '',
    analytics: window.__fixture.analytics,
    projectBodies: window.__fixture.projectBodies,
    projectRequests: window.__fixture.projectRequests,
    unexpectedRequests: window.__fixture.unexpectedRequests,
    errors: Number(document.querySelector('#fixtureErrors')?.textContent || 0),
  }));
  await successPage.screenshot({path: 'artifacts/project-save-success.png', fullPage: true});

  const expectedIntent = [{
    eventName: 'ProjectSaveIntentReached',
    values: {eventKey: 'project-save-intent', source: 'new_project'},
  }];
  assert.equal(pending.button, 'Saving…');
  assert.equal(pending.busy, 'true');
  assert.match(pending.prompt, /Saving this conversation privately/);
  assert.equal(recovered.button, 'Start a Project');
  assert.match(recovered.prompt, /Couldn’t save yet/);
  assert.deepEqual(recovered.analytics, expectedIntent);
  assert.equal(recovered.projectBodies[0]?.continuitySource, 'result_action');
  assert.equal(recovered.errors, 0);
  assert.equal(saved.button, 'Open Project');
  assert.match(saved.prompt, /Saved privately/);
  assert.deepEqual(saved.analytics, expectedIntent);
  assert.equal(saved.projectBodies[0]?.continuitySource, 'result_action');
  assert.equal(saved.projectRequests, 1);
  assert.equal(saved.unexpectedRequests, 0);
  assert.equal(saved.errors, 0);
  assert.deepEqual(consoleErrors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({pending, recovered, saved, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
