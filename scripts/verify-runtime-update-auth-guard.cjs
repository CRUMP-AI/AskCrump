const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const token = `${Date.now()}`;
  const consoleErrors = [];

  async function open(mode) {
    const page = await browser.newPage({viewport: {width: 390, height: 430}});
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(`${mode}: ${message.text()}`);
    });
    page.on('pageerror', error => consoleErrors.push(`${mode}: ${error.message}`));
    await page.goto(
      `${fixtureOrigin}/tests/fixtures/runtime-update-auth-guard.html?mode=${mode}&token=${token}`,
      {waitUntil: 'domcontentloaded'},
    );
    await page.waitForFunction(() => ['reloaded', 'deferred', 'notice', 'lost'].includes(
      document.getElementById('fixtureStatus')?.textContent || '',
    ));
    return page;
  }

  async function snapshot(page) {
    return page.evaluate(() => ({
      status: document.getElementById('fixtureStatus')?.textContent || '',
      notice: document.querySelectorAll('.runtime-update-notice.visible').length,
      email: document.getElementById('fixtureEmail')?.value || '',
      checked: document.getElementById('fixtureTerms')?.checked === true,
      draft: document.getElementById('userInput')?.value || '',
      fileCount: document.getElementById('filePreview')?.childElementCount || 0,
      precisionOpen: document.body.classList.contains('crump-precision-open'),
      sending: document.body.classList.contains('crump50-sending'),
      reloadGuard: Boolean(sessionStorage.getItem('crump_runtime_reload_started_at')),
    }));
  }

  async function runDeferred(mode, release) {
    const page = await open(mode);
    const before = await snapshot(page);
    await page.evaluate(release);
    await page.waitForFunction(() => document.querySelectorAll('.runtime-update-notice.visible').length === 1);
    const after = await snapshot(page);
    await page.close();
    return {before, after};
  }

  const cleanPage = await open('clean');
  const clean = await snapshot(cleanPage);
  await cleanPage.close();
  const typed = await runDeferred('typed', () => {
    const input = document.getElementById('fixtureEmail');
    input.value = '';
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  const checked = await runDeferred('checked', () => {
    const input = document.getElementById('fixtureTerms');
    input.checked = false;
    input.dispatchEvent(new Event('change', {bubbles: true}));
  });
  const draft = await runDeferred('draft', () => {
    const input = document.getElementById('userInput');
    input.value = '';
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  const file = await runDeferred('file', () => {
    const preview = document.getElementById('filePreview');
    preview.replaceChildren();
    preview.hidden = true;
    preview.style.display = 'none';
  });
  const precision = await runDeferred('precision', () => {
    document.querySelector('.crump-precision-backdrop')?.remove();
    document.body.classList.remove('crump-precision-open');
  });
  const sending = await runDeferred('sending', () => {
    document.body.classList.remove('crump50-sending');
  });
  const lateDraftPage = await open('signedin');
  await lateDraftPage.evaluate(() => {
    const input = document.getElementById('userInput');
    input.value = 'draft started after the notice';
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  await lateDraftPage.waitForFunction(() => !document.querySelector('.runtime-update-notice'));
  const lateDraft = await snapshot(lateDraftPage);
  await lateDraftPage.evaluate(() => {
    const input = document.getElementById('userInput');
    input.value = '';
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  await lateDraftPage.waitForFunction(() => document.querySelectorAll('.runtime-update-notice.visible').length === 1);
  const lateDraftReleased = await snapshot(lateDraftPage);
  await lateDraftPage.close();

  assert.equal(clean.status, 'reloaded');
  assert.equal(clean.notice, 0);
  assert.equal(clean.reloadGuard, true);
  for (const [name, result] of Object.entries({typed, checked, draft, file, precision, sending})) {
    assert.equal(result.before.status, 'deferred', `${name} should defer the update`);
    assert.equal(result.before.notice, 0, `${name} should not show a reload action over work`);
    assert.equal(result.before.reloadGuard, false, `${name} should not begin reloading`);
    assert.equal(result.after.notice, 1, `${name} should offer the update after work clears`);
  }
  assert.equal(typed.before.email, 'draft@example.test');
  assert.equal(checked.before.checked, true);
  assert.equal(draft.before.draft, 'unfinished thought');
  assert.equal(file.before.fileCount, 1);
  assert.equal(precision.before.precisionOpen, true);
  assert.equal(sending.before.sending, true);
  assert.equal(lateDraft.draft, 'draft started after the notice');
  assert.equal(lateDraft.notice, 0);
  assert.equal(lateDraft.reloadGuard, false);
  assert.equal(lateDraftReleased.notice, 1);

  const latePrecisionPage = await open('signedin');
  await latePrecisionPage.evaluate(() => {
    document.body.classList.add('crump-precision-open');
    const editor = document.createElement('section');
    editor.className = 'crump-precision-backdrop';
    editor.textContent = 'Unsaved image edit';
    document.body.appendChild(editor);
    document.querySelector('.runtime-update-action')?.click();
  });
  await latePrecisionPage.waitForFunction(() => !document.querySelector('.runtime-update-notice'));
  const latePrecision = await snapshot(latePrecisionPage);
  await latePrecisionPage.evaluate(() => {
    document.querySelector('.crump-precision-backdrop')?.remove();
    document.body.classList.remove('crump-precision-open');
  });
  await latePrecisionPage.waitForFunction(() => document.querySelectorAll('.runtime-update-notice.visible').length === 1);
  const latePrecisionReleased = await snapshot(latePrecisionPage);
  await latePrecisionPage.close();

  assert.equal(latePrecision.precisionOpen, true);
  assert.equal(latePrecision.notice, 0);
  assert.equal(latePrecision.reloadGuard, false);
  assert.equal(latePrecisionReleased.notice, 1);
  assert.deepEqual(consoleErrors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({clean, typed, checked, draft, file, precision, sending, lateDraft, lateDraftReleased, latePrecision, latePrecisionReleased, consoleErrors})}\n`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
