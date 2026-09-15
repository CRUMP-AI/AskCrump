const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
const viewports = [
  {name: 'phone', width: 390, height: 844},
  {name: 'desktop', width: 1280, height: 720},
].filter(viewport => !process.env.ASKCRUMP_PLAN_VIEWPORT || viewport.name === process.env.ASKCRUMP_PLAN_VIEWPORT);
const plans = ['professional', 'enterprise'].filter(
  plan => !process.env.ASKCRUMP_PLAN_NAME || plan === process.env.ASKCRUMP_PLAN_NAME,
);
const consumerDelays = [180, 260, 340, 420, 500, 580, 660, 740, 820, 900];
const activeConsumerDelays = consumerDelays.slice(
  0,
  Math.max(1, Math.min(consumerDelays.length, Number(process.env.ASKCRUMP_PLAN_DELAY_RUNS || consumerDelays.length))),
);

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  try {
    for (const viewport of viewports) {
      for (const plan of plans) {
        for (const consumerDelay of activeConsumerDelays) {
          if (process.env.ASKCRUMP_PLAN_DEBUG === '1') {
            process.stderr.write(`starting ${viewport.name} ${plan} ${consumerDelay}\n`);
          }
          const context = await browser.newContext({viewport});
          const page = await context.newPage();
          const browserErrors = [];
          page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
          page.on('pageerror', error => browserErrors.push(error.message));
          const url = new URL('/tests/fixtures/cold-auth-entry-delay.html', baseUrl);
          url.searchParams.set('authenticated', '1');
          url.searchParams.set('signup', '1');
          url.searchParams.set('source', 'pricing');
          url.searchParams.set('acquisition', 'direct');
          url.searchParams.set('plan', plan);
          url.searchParams.set('sessionDelay', '40');
          url.searchParams.set('planConsumerDelay', String(consumerDelay));
          url.searchParams.set('legacyBillingOwner', '1');
          url.searchParams.set('billingDelay', '750');
          await page.goto(url.toString(), {waitUntil: 'domcontentloaded'});

          const label = plan === 'enterprise' ? 'Enterprise' : 'Professional';
          const notice = page.getByText(`You chose ${label}. Review the details, then continue when you are ready.`, {exact: true});
          try {
            await notice.waitFor({state: 'visible', timeout: 4000});
          } catch (error) {
            const diagnostic = await page.evaluate(() => ({
              fixture: window.__fixture,
              modalClasses: [...document.querySelectorAll('.billing51-modal')].map(node => node.className),
              modalHtml: document.querySelector('.billing51-modal')?.innerHTML.slice(0, 1200) || '',
            }));
            error.message += `\nPlan-delivery diagnostic: ${JSON.stringify(diagnostic)}`;
            throw error;
          }
          await page.waitForFunction(() => window.__fixture?.planConsumed === 1, null, {timeout: 4000});
          await page.waitForTimeout(80);

          const state = await page.evaluate(() => ({
            ...window.__fixture,
            pendingPlan: localStorage.getItem('askcrump.pending-plan-intent'),
            dialogs: document.querySelectorAll('.billing51-modal[role="dialog"]').length,
            notices: document.querySelectorAll('.crump52-plan-intent').length,
            selectedCards: document.querySelectorAll('.billing51-plan.is-intent').length,
            selectedPlan: document.querySelector('.billing51-plan.is-intent')?.dataset.crumpPlan || '',
            openedFor: document.querySelector('.billing51-modal')?.dataset.openedFor || '',
            enterpriseSummary: document.querySelector('[data-crump-plan="enterprise"] .billing51-plan-summary')?.textContent || '',
          }));
          assert.equal(state.planConsumerLoaded, true);
          assert.equal(state.billingOpens, 1);
          assert.equal(state.billingRequests, 1);
          assert.equal(state.planEvents, 1);
          assert.equal(state.planAnalytics, 1);
          assert.equal(state.planConsumed, 1);
          assert.equal(state.checkoutRequests, 0);
          assert.equal(state.pendingPlan, null);
          assert.equal(state.dialogs, 1);
          assert.equal(state.notices, 1);
          assert.equal(state.selectedCards, 1);
          assert.equal(state.selectedPlan, plan);
          assert.equal(state.openedFor, plan);
          assert.equal(state.enterpriseSummary, 'For sustained work that needs the largest current individual limits.');
          assert.equal(state.enterpriseSummary.toLowerCase().includes('organization'), false);
          assert.deepEqual(state.browserErrors, []);
          assert.deepEqual(browserErrors, []);
          assert.equal(new URL(page.url()).searchParams.get('plan'), plan);
          results.push({viewport: viewport.name, plan, consumerDelay});
          if (process.env.ASKCRUMP_PLAN_DEBUG === '1') {
            process.stderr.write(`passed ${viewport.name} ${plan} ${consumerDelay}\n`);
          }
          await context.close();
        }
      }
    }

    const visibilityContext = await browser.newContext({viewport: {width: 390, height: 844}});
    const visibilityPage = await visibilityContext.newPage();
    const visibilityErrors = [];
    visibilityPage.on('console', message => {
      if (message.type() === 'error') visibilityErrors.push(message.text());
    });
    visibilityPage.on('pageerror', error => visibilityErrors.push(error.message));
    const visibilityUrl = new URL('/tests/fixtures/cold-auth-entry-delay.html', baseUrl);
    visibilityUrl.searchParams.set('authenticated', '1');
    visibilityUrl.searchParams.set('signup', '1');
    visibilityUrl.searchParams.set('sessionDelay', '40');
    visibilityUrl.searchParams.set('visibility', 'hidden');
    await visibilityPage.goto(visibilityUrl.toString(), {waitUntil: 'domcontentloaded'});
    await visibilityPage.waitForFunction(() => window.__fixture?.appStarts === 1);

    const hiddenEvents = await visibilityPage.evaluate(() => window.__fixture.analyticsEvents);
    assert.equal(documentEventCount(hiddenEvents, 'WorkspaceOpened'), 0);

    await visibilityPage.evaluate(() => window.__fixtureSetVisibility('visible'));
    await visibilityPage.waitForFunction(() => (
      window.__fixture.analyticsEvents.filter(event => event.name === 'WorkspaceOpened').length === 1
    ));
    await visibilityPage.evaluate(() => window.__fixtureSetVisibility('visible'));
    await visibilityPage.waitForTimeout(40);

    const visibleEvents = await visibilityPage.evaluate(() => window.__fixture.analyticsEvents);
    const workspaceEvents = visibleEvents.filter(event => event.name === 'WorkspaceOpened');
    assert.equal(workspaceEvents.length, 1);
    assert.match(workspaceEvents[0].detail.eventKey, /^workspace-open:\d{4}-\d{2}-\d{2}$/);
    assert.deepEqual(visibilityErrors, []);
    results.push({visibilityGate: 'hidden-to-visible', workspaceEvents: workspaceEvents.length});
    await visibilityContext.close();
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({runs: results.length, results}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});

function documentEventCount(events, name) {
  return events.filter(event => event.name === name).length;
}
