const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const consoleErrors = [];
  const openFixture = async (query, viewport = {width: 390, height: 844}) => {
    const page = await browser.newPage({
      viewport,
      hasTouch: viewport.width <= 640,
    });
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => consoleErrors.push(error.message));
    await page.goto(`http://127.0.0.1:8765/tests/fixtures/project-save-stall.html${query}`, {
      waitUntil: 'networkidle',
    });
    await page.waitForFunction(() => {
      const button = document.querySelector('.outcome-project-btn');
      return button && !button.disabled && button.textContent.includes('Keep in a new Project');
    });
    return page;
  };

  const inspectHierarchy = page => page.evaluate(() => {
    const group = document.querySelector('.outcome-feedback');
    const continuity = document.querySelector('.outcome-continuity');
    const button = document.querySelector('.outcome-project-btn');
    const buttonBox = button?.getBoundingClientRect();
    const continuityBox = continuity?.getBoundingClientRect();
    const feedbackButtons = Array.from(document.querySelectorAll('.outcome-feedback-question .outcome-feedback-btn'));
    const responseActions = Array.from(document.querySelectorAll('.message-actions .message-action-btn'));
    return {
      children: Array.from(group?.children || []).map(node => node.className),
      title: document.querySelector('.outcome-continuity-prompt')?.textContent || '',
      detail: document.querySelector('.outcome-continuity-detail')?.textContent || '',
      question: document.querySelector('.outcome-feedback-question')?.textContent || '',
      buttonWidth: Math.round(buttonBox?.width || 0),
      buttonHeight: Math.round(buttonBox?.height || 0),
      continuityWidth: Math.round(continuityBox?.width || 0),
      feedbackButtonHeights: feedbackButtons.map(item => Math.round(item.getBoundingClientRect().height)),
      responseActionHeights: responseActions.map(item => Math.round(item.getBoundingClientRect().height)),
      responseActionFontSizes: responseActions.map(item => Number.parseFloat(getComputedStyle(item).fontSize)),
      overflow: document.documentElement.scrollWidth > window.innerWidth,
    };
  });

  const stalledPage = await openFixture('');
  const mobileHierarchy = await inspectHierarchy(stalledPage);
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

  const desktopPage = await openFixture('?layout=desktop', {width: 1440, height: 900});
  const desktopHierarchy = await inspectHierarchy(desktopPage);
  await desktopPage.screenshot({path: 'artifacts/project-save-desktop.png', fullPage: true});

  const expectedAnalytics = [{
    eventName: 'ProjectSaveOfferShown',
    values: {eventKey: 'project-save-offer-shown', source: 'conversation_result'},
  }, {
    eventName: 'ProjectSaveIntentReached',
    values: {eventKey: 'project-save-intent', source: 'new_project'},
  }];
  assert.equal(pending.button, 'Saving…');
  assert.equal(pending.busy, 'true');
  assert.match(pending.prompt, /Saving this conversation privately/);
  assert.deepEqual(mobileHierarchy.children, ['outcome-continuity', 'outcome-feedback-question']);
  assert.equal(mobileHierarchy.title, 'Continue this work later');
  assert.equal(mobileHierarchy.detail, 'Keep this conversation in a private Project.');
  assert.match(mobileHierarchy.question, /Did this move your work forward\?YesNot yet/);
  assert.ok(mobileHierarchy.buttonHeight >= 44);
  assert.deepEqual(mobileHierarchy.feedbackButtonHeights, [44, 44]);
  assert.ok(mobileHierarchy.responseActionHeights.length >= 4);
  assert.ok(mobileHierarchy.responseActionHeights.every(height => height >= 44));
  assert.ok(mobileHierarchy.responseActionFontSizes.every(size => size >= 12));
  assert.ok(mobileHierarchy.buttonWidth >= mobileHierarchy.continuityWidth - 26);
  assert.equal(mobileHierarchy.overflow, false);
  assert.equal(desktopHierarchy.title, mobileHierarchy.title);
  assert.equal(desktopHierarchy.detail, mobileHierarchy.detail);
  assert.ok(desktopHierarchy.buttonWidth < desktopHierarchy.continuityWidth / 2);
  assert.ok(desktopHierarchy.feedbackButtonHeights.every(height => height >= 30));
  assert.equal(desktopHierarchy.overflow, false);
  assert.equal(recovered.button, 'Keep in a new Project');
  assert.match(recovered.prompt, /Couldn’t save yet/);
  assert.deepEqual(recovered.analytics, expectedAnalytics);
  assert.equal(recovered.projectBodies[0]?.continuitySource, 'result_action');
  assert.equal(recovered.errors, 0);
  assert.equal(saved.button, 'Open Project');
  assert.match(saved.prompt, /Saved privately/);
  assert.deepEqual(saved.analytics, expectedAnalytics);
  assert.equal(saved.projectBodies[0]?.continuitySource, 'result_action');
  assert.equal(saved.projectRequests, 1);
  assert.equal(saved.unexpectedRequests, 0);
  assert.equal(saved.errors, 0);
  assert.deepEqual(consoleErrors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({mobileHierarchy, desktopHierarchy, pending, recovered, saved, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
