const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const token = `${Date.now()}`;
  const consoleErrors = [];

  async function run(mode) {
    const page = await browser.newPage({viewport: {width: 390, height: 430}});
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(`${mode}: ${message.text()}`);
    });
    page.on('pageerror', error => consoleErrors.push(`${mode}: ${error.message}`));
    await page.goto(
      `${fixtureOrigin}/tests/fixtures/runtime-update-auth-guard.html?mode=${mode}&token=${token}`,
      {waitUntil: 'domcontentloaded'},
    );
    await page.waitForFunction(() => ['reloaded', 'preserved', 'lost'].includes(
      document.getElementById('fixtureStatus')?.textContent || '',
    ));
    const result = await page.evaluate(() => ({
      status: document.getElementById('fixtureStatus')?.textContent || '',
      notice: document.querySelectorAll('.runtime-update-notice.visible').length,
      email: document.getElementById('fixtureEmail')?.value || '',
      checked: document.getElementById('fixtureTerms')?.checked === true,
      reloadGuard: Boolean(sessionStorage.getItem('crump_runtime_reload_started_at')),
    }));
    await page.close();
    return result;
  }

  const clean = await run('clean');
  const typed = await run('typed');
  const checked = await run('checked');

  assert.equal(clean.status, 'reloaded');
  assert.equal(clean.notice, 0);
  assert.equal(clean.reloadGuard, true);
  assert.equal(typed.status, 'preserved');
  assert.equal(typed.notice, 1);
  assert.equal(typed.email, 'draft@example.test');
  assert.equal(checked.status, 'preserved');
  assert.equal(checked.notice, 1);
  assert.equal(checked.checked, true);
  assert.deepEqual(consoleErrors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({clean, typed, checked, consoleErrors})}\n`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
