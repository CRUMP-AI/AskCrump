const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];

  for (const viewport of [{width: 1280, height: 760}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${baseUrl}/tests/fixtures/settings-profile-trust.html`, {waitUntil: 'networkidle'});
    await page.getByRole('button', {name: 'Open settings'}).click();
    const dialog = page.getByRole('dialog', {name: 'Settings'});
    const email = dialog.getByRole('textbox', {name: 'Account email'});
    const assistant = dialog.getByRole('textbox', {name: 'Assistant name'});
    const save = dialog.getByRole('button', {name: 'Save changes'});
    await page.waitForFunction(() => document.getElementById('settingsEmail')?.value === 'demo@example.com');

    const initial = await page.evaluate(() => ({
      email: document.getElementById('settingsEmail')?.value || '',
      emailReadOnly: document.getElementById('settingsEmail')?.readOnly || false,
      emailBusy: document.getElementById('settingsEmail')?.getAttribute('aria-busy'),
      saveDisabled: document.getElementById('saveSettingsBtn')?.disabled || false,
      saveAriaDisabled: document.getElementById('saveSettingsBtn')?.getAttribute('aria-disabled'),
      saveTitle: document.getElementById('saveSettingsBtn')?.title || '',
    }));
    await assistant.fill('Echo');
    const edited = await page.evaluate(() => ({
      saveDisabled: document.getElementById('saveSettingsBtn')?.disabled || false,
      saveAriaDisabled: document.getElementById('saveSettingsBtn')?.getAttribute('aria-disabled'),
      saveTitle: document.getElementById('saveSettingsBtn')?.title || '',
    }));
    await assistant.fill('Crump');
    const reverted = await page.evaluate(() => ({
      saveDisabled: document.getElementById('saveSettingsBtn')?.disabled || false,
      saveAriaDisabled: document.getElementById('saveSettingsBtn')?.getAttribute('aria-disabled'),
    }));
    await dialog.getByRole('checkbox', {name: 'Work Mode'}).check();
    const behavior = await page.evaluate(() => ({
      saveDisabled: document.getElementById('saveSettingsBtn')?.disabled || false,
      workHoursDisplay: getComputedStyle(document.getElementById('workHoursGroup')).display,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      fixtureErrors: window.fixtureErrors,
    }));
    results.push({viewport, initial, edited, reverted, behavior, errors});
    await page.close();
  }
  await browser.close();

  const failed = results.some(result => (
    result.initial.email !== 'demo@example.com'
    || !result.initial.emailReadOnly
    || result.initial.emailBusy !== null
    || !result.initial.saveDisabled
    || result.initial.saveAriaDisabled !== 'true'
    || result.initial.saveTitle !== 'No changes to save'
    || result.edited.saveDisabled
    || result.edited.saveAriaDisabled !== 'false'
    || result.edited.saveTitle !== 'Save your changes'
    || !result.reverted.saveDisabled
    || result.reverted.saveAriaDisabled !== 'true'
    || result.behavior.saveDisabled
    || result.behavior.workHoursDisplay === 'none'
    || result.behavior.horizontalOverflow
    || result.behavior.fixtureErrors.length
    || result.errors.length
  ));
  if (failed) throw new Error(JSON.stringify(results));
  process.stdout.write(`${JSON.stringify(results)}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
