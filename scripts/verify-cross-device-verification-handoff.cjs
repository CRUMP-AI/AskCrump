const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  const httpFailures = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400) httpFailures.push(`${response.status()} ${response.url()}`);
  });
  await page.route('**/assets/brand/crump-mark.png', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+5MzdAAAAAElFTkSuQmCC',
      'base64',
    ),
  }));

  await page.goto(
    `${fixtureOrigin}/tests/fixtures/creation-intent-handoff.html?verification=success&intent=presentation&plan=professional`,
    {waitUntil: 'domcontentloaded'},
  );
  await page.waitForFunction(() => {
    const calls = JSON.parse(document.getElementById('fixtureCalls')?.textContent || '[]');
    return calls.some(call => call.tool === 'document' && call.format === 'pptx')
      && calls.some(call => call.tool === 'plan' && call.plan === 'professional');
  });
  const result = await page.evaluate(() => ({
    calls: JSON.parse(document.getElementById('fixtureCalls')?.textContent || '[]'),
    pendingCreation: localStorage.getItem('askcrump.pending-creation-intent'),
    pendingPlan: localStorage.getItem('askcrump.pending-plan-intent'),
    query: location.search,
    errors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
  }));

  assert.ok(result.calls.some(call => call.tool === 'document' && call.action === 'select' && call.format === 'pptx'));
  assert.ok(result.calls.some(call => call.tool === 'plan' && call.action === 'open' && call.plan === 'professional'));
  assert.equal(result.pendingCreation, null);
  assert.equal(result.pendingPlan, null);
  assert.equal(result.query, '');
  assert.equal(result.errors, 0);
  assert.deepEqual(httpFailures, []);
  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({...result, httpFailures, browserErrors: errors})}\n`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
