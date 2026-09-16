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
    const loadingPlans = page.getByRole('button', {name:'Loading plan…', exact:true});
    await loadingPlans.first().waitFor({state:'visible'});
    assert.equal(await loadingPlans.count(), 2);
    assert.equal(await loadingPlans.nth(0).isDisabled(), true);
    assert.equal(await loadingPlans.nth(1).isDisabled(), true);
    assert.equal(await page.locator('.billing51-modal').getAttribute('data-crump-subscriptions532'), null);

    await page.evaluate(() => window.__loadFixtureSubscriptions());
    await page.waitForFunction(() => (
      document.querySelector('.billing51-modal')?.dataset.crumpSubscriptions532 === 'ready'
    ));
    assert.equal(await loadingPlans.count(), 0);
    const professionalPlan = page.getByRole('button', {name:'Review Professional in Stripe', exact:true});
    const enterprisePlan = page.getByRole('button', {name:'Review Enterprise in Stripe', exact:true});
    assert.equal(await professionalPlan.isEnabled(), true);
    assert.equal(await enterprisePlan.isEnabled(), true);
    assert.equal(Number(await page.locator('#checkoutFixtureRequests').textContent()), 0);

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
    const plan = page.getByRole('button', {name:'Review Professional in Stripe', exact:true});
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

    const destinationContract = await page.evaluate(() => ({
      checkout: window.BillingManager.stripeDestination(
        'https://checkout.stripe.com/c/pay/cs_fixture',
        'checkout',
      ),
      portal: window.BillingManager.stripeDestination(
        'https://billing.stripe.com/p/session/bps_fixture',
        'portal',
      ),
      deceptiveCheckout: window.BillingManager.stripeDestination(
        'https://checkout.stripe.com.evil.test/c/pay/cs_fixture',
        'checkout',
      ),
      deceptivePortal: window.BillingManager.stripeDestination(
        'https://billing.stripe.com@evil.test/p/session/bps_fixture',
        'portal',
      ),
    }));
    assert.equal(destinationContract.checkout, 'https://checkout.stripe.com/c/pay/cs_fixture');
    assert.equal(destinationContract.portal, 'https://billing.stripe.com/p/session/bps_fixture');
    assert.equal(destinationContract.deceptiveCheckout, null);
    assert.equal(destinationContract.deceptivePortal, null);

    await page.evaluate(() => { window.__fixtureCheckoutMode = 'invalid'; });
    await page.getByRole('button', {name:'Close', exact:true}).click();
    await page.getByRole('button', {name:'Plan & credits'}).click();
    const unsafeCredit = page.getByRole('button', {name:'Add 50 Crump Credits for $4.99', exact:true});
    await unsafeCredit.click();
    await page.waitForFunction(() => /secure checkout destination/i.test(
      window.__fixtureToasts.at(-1)?.message || '',
    ));
    assert.equal(await unsafeCredit.isEnabled(), true);
    assert.match(page.url(), /checkout-session-recovery\.html$/);

    await page.getByRole('button', {name:'Close', exact:true}).click();
    await page.getByRole('button', {name:'Plan & credits'}).click();
    const unsafePlan = page.getByRole('button', {name:'Review Enterprise in Stripe', exact:true});
    await unsafePlan.click();
    await page.waitForFunction(() => /secure checkout destination/i.test(
      window.__fixtureToasts.at(-1)?.message || '',
    ));
    assert.equal(await unsafePlan.isEnabled(), true);
    assert.match(page.url(), /checkout-session-recovery\.html$/);
    assert.equal(Number(await page.locator('#checkoutFixtureRequests').textContent()), 4);

    await page.getByRole('button', {name:'Close', exact:true}).click();
    await page.evaluate(() => {
      document.getElementById('tosModal').style.display = 'flex';
      document.getElementById('tosAccept').checked = false;
      document.getElementById('tosAcceptBtn').disabled = true;
    });
    const termsCheckbox = page.locator('#tosAccept');
    const termsButton = page.getByRole('button', {name:'Continue to Ask Crump', exact:true});
    assert.equal(await termsButton.isDisabled(), true);
    await page.evaluate(() => document.getElementById('tosAcceptBtn').click());
    assert.equal(Number(await page.locator('#checkoutFixtureTermsRequests').textContent()), 0);
    await termsCheckbox.check();
    assert.equal(await termsButton.isEnabled(), true);
    await termsButton.click();
    await page.waitForFunction(() => /Fixture terms save failed/.test(
      window.__fixtureToasts.at(-1)?.message || '',
    ));
    assert.equal(Number(await page.locator('#checkoutFixtureTermsRequests').textContent()), 1);
    assert.equal(await termsButton.isEnabled(), true);
    assert.equal(await termsButton.textContent(), 'Continue to Ask Crump');
    assert.equal(await page.locator('#tosModal').isVisible(), true);
    await page.evaluate(() => { window.__fixtureTermsMode = 'success'; });
    await termsButton.click();
    await page.waitForFunction(() => document.getElementById('tosModal')?.style.display === 'none');
    assert.equal(Number(await page.locator('#checkoutFixtureTermsRequests').textContent()), 2);

    assert.equal(Number(await page.locator('#checkoutFixtureErrors').textContent()), 0);
    assert.deepEqual(browserErrors, []);
    process.stdout.write(JSON.stringify({
      planHydration:{loadingPlaceholders:2, liveActions:2, checkoutRequestsBeforeAction:0},
      checkoutRequests:4,
      reauthenticationHandoffs:2,
      automaticCheckoutRequests:0,
      recovered:['credits_150', 'professional'],
      rejectedDestinations:['credit', 'subscription'],
      termsAcceptance:{blockedBeforeConsent:true, retryRecovered:true, requests:2},
    }));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
