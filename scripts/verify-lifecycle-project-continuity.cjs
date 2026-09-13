const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];
  const fixtureUrl = 'http://127.0.0.1:8765/tests/fixtures/lifecycle-project-continuity.html';
  const openFixture = async () => {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(fixtureUrl, {waitUntil: 'domcontentloaded'});
    return page;
  };

  const page = await openFixture();
  assert.equal(await page.locator('#sendButton').isDisabled(), true);
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
  assert.equal(result.decisionCalls, 1);
  assert.equal(result.genericProjectOpens, 0);
  assert.deepEqual(result.projectArgs, [{projectId: null, continuitySource: 'result_action'}]);
  assert.equal(result.projectButtonText, 'Open Project');
  assert.equal(result.projectButtonSaved, 'true');
  assert.equal(result.continuityText, 'Saved privately to "Launch plan".');
  assert.deepEqual(result.actions, ['shown', 'acted']);

  const typedPage = await openFixture();
  await typedPage.locator('#userInput').fill('A draft the user has not sent');
  assert.equal(await typedPage.evaluate(() => window.CrumpLifecycle.evaluate({force: true})), false);
  assert.equal(await typedPage.evaluate(() => window.__fixture.decisionCalls), 0);
  assert.equal(await typedPage.locator('.crump-lifecycle-card').count(), 0);

  const attachmentPage = await openFixture();
  await attachmentPage.evaluate(() => { document.getElementById('filePreview').hidden = false; });
  assert.equal(await attachmentPage.evaluate(() => window.CrumpLifecycle.evaluate({force: true})), false);
  assert.equal(await attachmentPage.evaluate(() => window.__fixture.decisionCalls), 0);
  assert.equal(await attachmentPage.locator('.crump-lifecycle-card').count(), 0);

  const activeReplyPage = await openFixture();
  await activeReplyPage.evaluate(() => { window.__fixture.presenceActive = true; });
  assert.equal(await activeReplyPage.evaluate(() => window.CrumpLifecycle.evaluate({force: true})), false);
  assert.equal(await activeReplyPage.evaluate(() => window.__fixture.decisionCalls), 0);
  assert.equal(await activeReplyPage.locator('.crump-lifecycle-card').count(), 0);

  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({
    result,
    suppression: {typed: true, attachment: true, activeReply: true},
    errors,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
