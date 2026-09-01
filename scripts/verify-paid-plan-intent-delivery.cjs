const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
const viewports = [
  {name: 'phone', width: 390, height: 844},
  {name: 'desktop', width: 1280, height: 720},
];
const plans = ['professional', 'enterprise'];
const consumerDelays = [180, 260, 340, 420, 500, 580, 660, 740, 820, 900];

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  try {
    for (const viewport of viewports) {
      for (const plan of plans) {
        for (const consumerDelay of consumerDelays) {
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
          await page.goto(url.toString(), {waitUntil: 'domcontentloaded'});

          const label = plan === 'enterprise' ? 'Enterprise' : 'Professional';
          const notice = page.getByText(`You chose ${label}. Review the details, then continue when you are ready.`, {exact: true});
          await notice.waitFor({state: 'visible', timeout: 4000});
          await page.waitForFunction(() => window.__fixture?.planConsumed === 1, null, {timeout: 4000});
          await page.waitForTimeout(80);

          const state = await page.evaluate(() => ({
            ...window.__fixture,
            pendingPlan: localStorage.getItem('askcrump.pending-plan-intent'),
            dialogs: document.querySelectorAll('.crump52-billing-modal[role="dialog"]').length,
            notices: document.querySelectorAll('.crump52-plan-intent').length,
            selectedCards: document.querySelectorAll('.billing51-plan.is-intent').length,
            selectedPlan: document.querySelector('.billing51-plan.is-intent')?.dataset.crumpPlan || '',
            openedFor: document.querySelector('.crump52-billing-modal')?.dataset.openedFor || '',
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
          assert.deepEqual(state.browserErrors, []);
          assert.deepEqual(browserErrors, []);
          assert.equal(new URL(page.url()).searchParams.get('plan'), plan);
          results.push({viewport: viewport.name, plan, consumerDelay});
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({runs: results.length, results}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
