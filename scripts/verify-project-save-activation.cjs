const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const consoleErrors = [];
  try {
    const openFixture = async (query, viewport = {width: 390, height: 844}) => {
      const page = await browser.newPage({viewport, hasTouch: viewport.width <= 640});
      await page.route('**/assets/brand/**', route => {
        const mapped = new URL(route.request().url());
        mapped.pathname = '/public' + mapped.pathname;
        return route.continue({url: mapped.href});
      });
      page.on('console', message => {
        if (message.type() === 'error') consoleErrors.push(message.text());
      });
      page.on('pageerror', error => consoleErrors.push(error.message));
      await page.goto('http://127.0.0.1:8765/tests/fixtures/project-save-stall.html' + query, {
        waitUntil: 'domcontentloaded',
      });
      await page.waitForFunction(() => (
        typeof window.CrumpOutcomeActions?.keepLatestInProject === 'function'
        && typeof window.CrumpProduct53?.resolveOutcomeProject === 'function'
      ));
      return page;
    };
    const inspect = page => page.evaluate(() => ({
      continuityCards: document.querySelectorAll('.outcome-continuity').length,
      projectButtons: document.querySelectorAll('.outcome-project-btn').length,
      responseActionHeights: Array.from(document.querySelectorAll('.message-actions .message-action-btn'))
        .map(item => Math.round(item.getBoundingClientRect().height)),
      feedbackButtons: document.querySelectorAll('.outcome-feedback-question .outcome-feedback-btn').length,
      overflow: document.documentElement.scrollWidth > window.innerWidth,
    }));
    const startAction = page => page.evaluate(() => {
      window.__projectFinished = false;
      window.__projectOperation = window.CrumpOutcomeActions.keepLatestInProject().then(result => {
        window.__projectResult = result;
        window.__projectFinished = true;
      });
    });
    const stalledPage = await openFixture('');
    const mobile = await inspect(stalledPage);
    assert.equal(await stalledPage.evaluate(() => window.__fixture.analytics.filter(item => (
      item.eventName === 'ProjectSaveOfferShown' && item.values.source === 'conversation_result'
    )).length), 0);
    await startAction(stalledPage);
    await stalledPage.waitForFunction(() => window.__fixture.projectRequests === 1);
    // Repeating the same explicit action while pending must not create a second Project.
    await stalledPage.evaluate(() => { void window.CrumpOutcomeActions.keepLatestInProject(); });
    await stalledPage.waitForFunction(() => window.__fixture.abortedProjectRequests === 1 && window.__projectFinished);
    const recovered = await stalledPage.evaluate(() => ({
      result: window.__projectResult,
      projectRequests: window.__fixture.projectRequests,
      projectBodies: window.__fixture.projectBodies,
      analytics: window.__fixture.analytics,
      toasts: Array.from(document.querySelectorAll('.toast__message')).map(node => node.textContent),
      errors: Number(document.querySelector('#fixtureErrors')?.textContent || 0),
    }));
    assert.equal(recovered.result, false);
    assert.equal(recovered.projectRequests, 1);
    assert.equal(recovered.analytics.filter(item => item.eventName === 'ProjectSaveOfferShown').length, 0);
    assert.ok(recovered.toasts.some(message => message.includes('Couldn’t save yet')));
    assert.equal(recovered.projectBodies[0]?.continuitySource, 'result_action');
    assert.equal(recovered.errors, 0);
    // A timed-out action releases its in-flight guard so a deliberate retry can proceed.
    await startAction(stalledPage);
    await stalledPage.waitForFunction(() => window.__fixture.abortedProjectRequests === 2 && window.__projectFinished);
    assert.equal(await stalledPage.evaluate(() => window.__fixture.projectRequests), 2);
    await stalledPage.screenshot({path: 'artifacts/project-save-recovery.png', fullPage: true});

    const successPage = await openFixture('?save=success');
    await startAction(successPage);
    await successPage.waitForFunction(() => window.__projectFinished);
    const saved = await successPage.evaluate(() => ({
      result: window.__projectResult,
      project: window.__fixture.savedProject,
      analytics: window.__fixture.analytics,
      projectBodies: window.__fixture.projectBodies,
      projectRequests: window.__fixture.projectRequests,
      unexpectedRequests: window.__fixture.unexpectedRequests,
      errors: Number(document.querySelector('#fixtureErrors')?.textContent || 0),
      continuityCards: document.querySelectorAll('.outcome-continuity').length,
    }));
    assert.equal(saved.result, true);
    assert.equal(saved.project?.name, 'Launch plan');
    assert.ok(saved.analytics.some(item => item.eventName === 'ProjectSaveIntentReached'
      && item.values.eventKey === 'project-save-intent' && item.values.source === 'new_project'));
    assert.equal(saved.analytics.filter(item => item.eventName === 'ProjectSaveOfferShown').length, 0);
    assert.equal(saved.projectBodies[0]?.continuitySource, 'result_action');
    assert.equal(saved.projectRequests, 1);
    assert.equal(saved.unexpectedRequests, 0);
    assert.equal(saved.errors, 0);
    assert.equal(saved.continuityCards, 0);
    await successPage.screenshot({path: 'artifacts/project-save-success.png', fullPage: true});

    const desktopPage = await openFixture('?layout=desktop', {width: 1440, height: 900});
    const desktop = await inspect(desktopPage);
    for (const state of [mobile, desktop]) {
      assert.equal(state.continuityCards, 0);
      assert.equal(state.projectButtons, 0);
      assert.equal(state.feedbackButtons, 2);
      assert.ok(state.responseActionHeights.length >= 4);
      assert.equal(state.overflow, false);
    }
    assert.ok(mobile.responseActionHeights.every(height => height >= 44));
    const cancelledSaves = [];
    for (const mode of ['cancelled', 'stale-failure']) {
      const cancelledPage = await openFixture('');
      const interrupted = await cancelledPage.evaluate(async mode => {
        let saves = 0;
        window.CrumpProduct53 = {
          ...window.CrumpProduct53,
          resolveOutcomeProject: async () => ({project: null, saved: false}),
          keepConversation: async () => {
            saves += 1;
            window.currentUser = {id: 'a-different-account'};
            if (mode === 'stale-failure') throw new Error('The previous account save was interrupted.');
            return {success: false, cancelled: true};
          },
        };
        const result = await window.CrumpOutcomeActions.keepLatestInProject();
        return {
          result,
          saves,
          toasts: Array.from(document.querySelectorAll('.toast__message')).map(node => node.textContent),
        };
      }, mode);
      assert.deepEqual(interrupted, {result: false, saves: 1, toasts: []});
      cancelledSaves.push({mode, ...interrupted});
    }
    assert.deepEqual(consoleErrors, []);
    process.stdout.write(JSON.stringify({mobile, desktop, recovered, saved, cancelledSaves, consoleErrors}) + '\n');
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write((error.stack || error) + '\n');
  process.exitCode = 1;
});
