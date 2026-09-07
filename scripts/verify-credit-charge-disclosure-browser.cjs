const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
const viewports = [
  {name: 'phone', width: 390, height: 844},
  {name: 'desktop', width: 1280, height: 720},
];

async function openFixture(page) {
  await page.goto(`${baseUrl}/tests/fixtures/credit-charge-disclosure.html`, {waitUntil: 'load'});
  await page.waitForFunction(() => typeof window.CrumpCreditConfirmation?.run === 'function');
}

async function status(page, pattern) {
  await page.locator('#fixtureStatus').filter({hasText: pattern}).waitFor({state: 'visible'});
  return page.locator('#fixtureStatus').textContent();
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  const results = [];
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({viewport});
      const page = await context.newPage();
      const browserErrors = [];
      page.on('console', message => {
        if (message.type() === 'error') browserErrors.push(message.text());
      });
      page.on('pageerror', error => browserErrors.push(error.message));

      await openFixture(page);
      assert.equal(await page.locator('[data-case]').count(), 6);

      await page.locator('[data-case="included"]').click();
      assert.match(await status(page, 'PASS'), /Included now · 0 credits/);
      assert.equal(await page.locator('.crump-credit-confirmation').count(), 0);

      await page.locator('[data-case="insufficient"]').click();
      assert.match(await status(page, 'PASS'), /needs 10 Crump Credits/);
      assert.equal(await page.locator('.crump-credit-confirmation').count(), 0);

      await page.locator('[data-case="duplicate"]').click();
      assert.match(await status(page, 'PASS'), /2 accepted submissions · 1 deduction/);

      await page.locator('[data-case="positive"]').click();
      const positive = page.getByRole('dialog', {name: 'Review before Crump starts'});
      await positive.waitFor({state: 'visible'});
      assert.match(await positive.textContent(), /Current balance\s*50 credits/);
      await page.getByRole('button', {name: 'Use 6 credits', exact: true}).click();
      assert.match(await status(page, 'PASS'), /Used 6 credits · balance 44/);
      assert.equal(await page.locator('.crump-credit-confirmation').count(), 0);

      await page.locator('[data-case="stale"]').click();
      await page.getByRole('button', {name: 'Use 6 credits', exact: true}).click();
      await page.getByRole('button', {name: 'Use 10 credits', exact: true}).click();
      assert.match(await status(page, 'PASS'), /Higher current charge required a new confirmation/);

      await page.locator('[data-case="ceiling"]').click();
      const ceiling = page.getByRole('dialog', {name: 'Review before Crump starts'});
      await ceiling.waitFor({state: 'visible'});
      assert.match(await ceiling.textContent(), /Planned steps\s*5/);
      assert.match(await ceiling.textContent(), /Chargeable steps\s*3/);
      assert.match(await ceiling.textContent(), /Per charged step\s*8 credits/);
      await page.getByRole('button', {name: 'Allow up to 24 credits', exact: true}).click();
      assert.match(await status(page, 'PASS'), /Maximum 24 credits/);

      for (const dismiss of ['Not now', 'Cancel credit use', 'Escape', 'backdrop']) {
        await openFixture(page);
        await page.locator('[data-case="positive"]').click();
        await page.getByRole('dialog', {name: 'Review before Crump starts'}).waitFor({state: 'visible'});
        if (dismiss === 'Escape') {
          await page.keyboard.press('Escape');
        } else if (dismiss === 'backdrop') {
          await page.locator('.crump-credit-confirmation__backdrop').click({position: {x: 2, y: 2}});
        } else {
          await page.getByRole('button', {name: dismiss, exact: true}).click();
        }
        await page.locator('.crump-credit-confirmation').waitFor({state: 'detached'});
        assert.equal(await page.evaluate(() => window.__creditFixture.deductions), 0);
      }

      assert.deepEqual(browserErrors, []);
      results.push({viewport: viewport.name, cases: 6, dismissals: 4, browserErrors: 0});
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
