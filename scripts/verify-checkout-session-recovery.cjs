const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;

async function signIn(page) {
  await page.locator('#loginEmail').fill('fixture@example.test');
  await page.locator('#loginPassword').fill('Fixture1234');
  await page.locator('#loginFormElement').evaluate(form => form.requestSubmit());
}

(async () => {
  const browser = await chromium.launch({headless:true, ...(executablePath ? {executablePath} : {})});
  try {
    const page = await browser.newPage({viewport:{width:390, height:844}});
    const browserErrors = [];
    page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
    page.on('pageerror', error => browserErrors.push(error.message));
    await page.goto(`${baseUrl}/tests/fixtures/checkout-session-recovery.html`, {waitUntil:'load'});
    await page.waitForFunction(() => typeof window.showBillingCenter === 'function');
    await page.waitForTimeout(900);

    await page.getByRole('button', {name:'Plan & credits'}).click();
    const credit = page.getByRole('button', {name:'Add 150 Crump Credits for $9.99', exact:true});
    await credit.waitFor({state:'visible'});
    await credit.click();

    await page.waitForFunction(() => document.getElementById('authContainer')?.style.display === 'flex');
    assert.match(await page.locator('#loginError').textContent(), /Nothing has been charged/);
    assert.equal(await page.locator('.billing51-modal').count(), 0);
    assert.equal(Number(await page.locator('#checkoutFixtureRequests').textContent()), 1);
    await page.waitForFunction(() => Number(document.getElementById('checkoutFixtureClearCalls')?.textContent || 0) === 1);
    assert.equal(Number(await page.locator('#checkoutFixtureClearCalls').textContent()), 1);
    const pendingCredit = await page.evaluate(() => window.BillingManager.pendingCheckoutRecovery());
    assert.equal(pendingCredit.kind, 'credit');
    assert.equal(pendingCredit.selection, 'credits_150');
    assert.ok(Number.isFinite(pendingCredit.capturedAt));

    await signIn(page);
    await page.waitForFunction(() => {
      const button = document.querySelector(
        '.billing51-pack[data-crump-pack="credits_150"] .billing51-buy:not([disabled])',
      );
      return button && document.activeElement === button;
    });
    assert.equal(Number(await page.locator('#checkoutFixtureRequests').textContent()), 1);
    assert.equal(await page.evaluate(() => window.BillingManager.pendingCheckoutRecovery()), null);
    assert.match(
      await page.evaluate(() => window.__fixtureToasts.at(-1)?.message || ''),
      /selected credit pack is ready to review.*Nothing has been purchased/i,
    );

    await page.getByRole('button', {name:'Close', exact:true}).click();
    await page.getByRole('button', {name:'Plan & credits'}).click();
    const plan = page.getByRole('button', {name:'Choose Professional', exact:true});
    await plan.waitFor({state:'visible'});
    await plan.click();

    await page.waitForFunction(() => document.getElementById('authContainer')?.style.display === 'flex');
    assert.equal(await page.locator('.billing51-modal').count(), 0);
    assert.equal(Number(await page.locator('#checkoutFixtureRequests').textContent()), 2);
    await page.waitForFunction(() => Number(document.getElementById('checkoutFixtureClearCalls')?.textContent || 0) === 2);
    assert.equal(Number(await page.locator('#checkoutFixtureClearCalls').textContent()), 2);
    const pendingPlan = await page.evaluate(() => window.BillingManager.pendingCheckoutRecovery());
    assert.equal(pendingPlan.kind, 'plan');
    assert.equal(pendingPlan.selection, 'professional');

    await signIn(page);
    await page.waitForFunction(() => {
      const button = document.querySelector(
        '.billing51-plan[data-crump-plan="professional"] button:not([disabled])',
      );
      return button && document.activeElement === button;
    });
    assert.equal(Number(await page.locator('#checkoutFixtureRequests').textContent()), 2);
    assert.equal(await page.evaluate(() => window.BillingManager.pendingCheckoutRecovery()), null);
    assert.equal(await page.locator('.billing51-plan[data-crump-plan="professional"]').evaluate(
      node => node.classList.contains('is-intent'),
    ), true);
    assert.match(
      await page.evaluate(() => window.__fixtureToasts.at(-1)?.message || ''),
      /selected plan is ready to review.*Nothing has been purchased/i,
    );
    assert.deepEqual(
      await page.evaluate(() => window.__fixtureCheckoutBodies.map(item => ({
        pathname:item.pathname,
        selection:item.body.pack || item.body.tier,
      }))),
      [
        {pathname:'/api/billing/credits/checkout', selection:'credits_150'},
        {pathname:'/api/stripe/create-checkout-session', selection:'professional'},
      ],
    );
    assert.equal(Number(await page.locator('#checkoutFixtureErrors').textContent()), 0);
    assert.deepEqual(browserErrors, []);
    process.stdout.write(JSON.stringify({
      checkoutRequests:2,
      reauthenticationHandoffs:2,
      automaticCheckoutRequests:0,
      recovered:['credits_150', 'professional'],
    }));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
