const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765/tests/fixtures/native-plan-center-billing.html', {waitUntil:'load'});

    await page.waitForFunction(() => document.querySelector('#upgradeBtnSidebar')?.dataset.crump52Billing === 'true');
    await page.click('#upgradeBtnSidebar');
    await page.waitForSelector('.crump52-billing-modal');
    await page.waitForFunction(() => {
      const credit = document.querySelector('.billing51-pack[data-crump-pack="credits_50"] .billing51-buy');
      const plans = document.querySelector('.crump52-billing-modal')?.dataset.crumpSubscriptions532;
      return credit && !credit.disabled && plans === 'ready';
    });

    const visible = await page.evaluate(() => ({
      creditPrice: document.querySelector('.billing51-pack[data-crump-pack="credits_50"] .billing51-pack-price')?.textContent?.trim(),
      professionalPrice: document.querySelector('.billing51-plan[data-crump-plan="professional"] .billing51-plan-top span')?.textContent?.trim(),
      restoreVisible: Boolean(document.querySelector('#billing52Restore')),
      modalText: document.querySelector('.crump52-billing-modal')?.textContent || '',
    }));
    assert.equal(visible.creditPrice, '$4.49');
    assert.equal(visible.professionalPrice, '$18.99/month');
    assert.equal(visible.restoreVisible, true);
    assert.equal(visible.modalText.includes('Stripe'), false);
    assert.ok(visible.modalText.includes('device store'));

    await page.click('.billing51-pack[data-crump-pack="credits_50"] .billing51-buy');
    await page.waitForFunction(() => window.__fixture.purchasedProductIds.includes('askcrump_credits_50'));
    await page.waitForFunction(() => window.__fixture.creditSyncRequests >= 1);

    await page.click('.billing51-plan[data-crump-plan="professional"] .billing51-plan-button');
    await page.waitForFunction(() => window.__fixture.purchasedProductIds.includes('askcrump_professional_monthly'));
    await page.waitForFunction(() => window.__fixture.entitlementSyncRequests >= 1);

    await page.click('#billing52Restore');
    await page.waitForFunction(() => window.__fixture.restoreCalls === 1);
    await page.waitForFunction(() => window.__fixture.creditSyncRequests >= 2 && window.__fixture.entitlementSyncRequests >= 2);

    const evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.checkoutRequests, 0);
    assert.equal(evidence.blockedWebBillingAttempts, 0);
    assert.deepEqual(evidence.purchasedProductIds, [
      'askcrump_credits_50',
      'askcrump_professional_monthly',
    ]);
    assert.equal(evidence.restoreCalls, 1);
    assert.ok(evidence.toasts.some(item => item.message === 'Credits added' && item.tone === 'success'));
    assert.ok(evidence.toasts.some(item => item.message === 'Subscription activated' && item.tone === 'success'));
    assert.ok(evidence.toasts.some(item => item.message === 'Purchases restored' && item.tone === 'success'));
    assert.deepEqual(errors, []);
    process.stdout.write(JSON.stringify({
      checkoutRequests: evidence.checkoutRequests,
      blockedWebBillingAttempts: evidence.blockedWebBillingAttempts,
      purchasedProductIds: evidence.purchasedProductIds,
      restoreCalls: evidence.restoreCalls,
      creditPrice: visible.creditPrice,
      professionalPrice: visible.professionalPrice,
      errors,
    }));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
