const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
const viewports = [
  {name: 'phone', width: 390, height: 844},
  {name: 'desktop', width: 1280, height: 720},
];

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({viewport});
      const page = await context.newPage();
      const browserErrors = [];
      page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
      page.on('pageerror', error => browserErrors.push(error.message));
      await page.goto(`${baseUrl}/tests/fixtures/plan-center-clarity.html`, {waitUntil: 'load'});
      await page.waitForFunction(() => typeof window.showBillingCenter === 'function');
      await page.waitForTimeout(1400);
      await page.getByRole('button', {name: 'Plan & credits'}).click();
      await page.locator('#billing52Packs .billing51-buy:not([disabled])').first().waitFor({state: 'visible'});
      await page.waitForTimeout(850);

      const state = await page.evaluate(() => {
        const cards = [...document.querySelectorAll('#billing52Packs .billing51-pack[data-crump-pack]')];
        const buttons = cards.map(card => card.querySelector('.billing51-buy'));
        return {
          cardCount: cards.length,
          nestedInteractiveCards: cards.filter(card => card.hasAttribute('role') || card.hasAttribute('tabindex')).length,
          buttonCount: buttons.filter(Boolean).length,
          labels: buttons.map(button => button?.getAttribute('aria-label') || ''),
          disabled: buttons.map(button => Boolean(button?.disabled)),
          browserErrors: Number(document.getElementById('billingFixtureErrors')?.textContent || 0),
        };
      });
      assert.equal(state.cardCount, 3);
      assert.equal(state.nestedInteractiveCards, 0);
      assert.equal(state.buttonCount, 3);
      assert.deepEqual(state.labels, [
        'Add 50 Crump Credits for $4.99',
        'Add 150 Crump Credits for $9.99',
        'Add 400 Crump Credits for $19.99',
      ]);
      assert.deepEqual(state.disabled, [false, false, false]);
      assert.equal(state.browserErrors, 0);
      assert.deepEqual(browserErrors, []);

      const first = page.getByRole('button', {name: 'Add 50 Crump Credits for $4.99', exact: true});
      assert.equal(await first.count(), 1);
      await page.getByRole('button', {name: 'Close', exact: true}).focus();
      await page.keyboard.press('Tab');
      assert.equal(await first.evaluate(node => document.activeElement === node), true);

      await page.locator('[data-crump-pack="credits_150"] .billing51-pack-amount').click();
      await page.waitForFunction(() => Number(document.getElementById('billingFixtureCheckouts')?.textContent || 0) === 1);
      await page.waitForFunction(() => !document.querySelector('[data-crump-pack="credits_150"] .billing51-buy')?.disabled);
      assert.equal(
        await page.locator('[data-crump-pack="credits_150"] .billing51-buy').getAttribute('aria-label'),
        'Add 150 Crump Credits for $9.99',
      );
      assert.equal(Number(await page.locator('#billingFixtureCheckouts').textContent()), 1);
      assert.equal(Number(await page.locator('#billingFixtureErrors').textContent()), 0);
      assert.deepEqual(browserErrors, []);
      results.push({viewport: viewport.name, ...state});
      await context.close();
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({runs: results.length, results}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
