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

  const guestPage = await browser.newPage({viewport: {width: 390, height: 844}});
  const guestErrors = [];
  guestPage.on('console', message => { if (message.type() === 'error') guestErrors.push(message.text()); });
  guestPage.on('pageerror', error => guestErrors.push(error.message));
  await guestPage.goto(`${baseUrl}/tests/fixtures/settings-profile-trust.html?guest=1`, {waitUntil: 'networkidle'});
  await guestPage.getByRole('button', {name: 'Open settings'}).click();
  await guestPage.waitForTimeout(500);
  const guest = await guestPage.evaluate(() => ({
    email: document.getElementById('settingsEmail')?.value || '',
    emailReadOnly: document.getElementById('settingsEmail')?.readOnly || false,
    emailBusy: document.getElementById('settingsEmail')?.getAttribute('aria-busy'),
    emailPlaceholder: document.getElementById('settingsEmail')?.placeholder || '',
    saveDisabled: document.getElementById('saveSettingsBtn')?.disabled || false,
    saveAriaDisabled: document.getElementById('saveSettingsBtn')?.getAttribute('aria-disabled'),
    horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    fixtureErrors: window.fixtureErrors,
  }));
  await guestPage.close();

  const saveCases = {};
  for (const saveCase of ['sync', 'presence', 'profile']) {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${baseUrl}/tests/fixtures/settings-profile-trust.html?save_case=${saveCase}`, {waitUntil: 'networkidle'});
    await page.getByRole('button', {name: 'Open settings'}).click();
    await page.waitForFunction(() => document.getElementById('settingsEmail')?.value === 'demo@example.com');
    await page.getByRole('textbox', {name: 'Assistant name'}).fill(`Echo ${saveCase}`);
    if (saveCase === 'profile') await page.getByRole('textbox', {name: 'Your name'}).fill('Updated Demo');
    await page.getByRole('checkbox', {name: 'Check-ins'}).check();
    await page.getByRole('button', {name: 'Save changes'}).click();
    await page.waitForFunction(() => document.getElementById('saveSettingsBtn')?.dataset.settingsSaving !== 'true');
    saveCases[saveCase] = await page.evaluate(() => ({
      syncAttempts: window.fixtureSyncAttempts,
      presenceAttempts: window.fixturePresenceAttempts,
      profileAttempts: window.fixtureProfileAttempts,
      modalVisible: getComputedStyle(document.getElementById('settingsModal')).display !== 'none',
      saveDisabled: document.getElementById('saveSettingsBtn')?.disabled || false,
      saveAriaDisabled: document.getElementById('saveSettingsBtn')?.getAttribute('aria-disabled'),
      toasts: window.fixtureToasts,
      fixtureErrors: window.fixtureErrors,
    }));
    saveCases[saveCase].errors = errors;
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
  const guestFailed = guest.email
    || !guest.emailReadOnly
    || guest.emailBusy !== null
    || guest.emailPlaceholder !== 'Sign in to view account email'
    || !guest.saveDisabled
    || guest.saveAriaDisabled !== 'true'
    || guest.horizontalOverflow
    || guest.fixtureErrors.length
    || guestErrors.length;
  const syncCase = saveCases.sync;
  const presenceCase = saveCases.presence;
  const profileCase = saveCases.profile;
  const saveCaseFailed = syncCase.syncAttempts !== 1
    || syncCase.presenceAttempts !== 1
    || syncCase.modalVisible
    || !syncCase.saveDisabled
    || syncCase.saveAriaDisabled !== 'true'
    || syncCase.toasts.at(-1)?.type !== 'warning'
    || !syncCase.toasts.at(-1)?.message.includes('cross-device sync is still pending')
    || syncCase.fixtureErrors.length
    || syncCase.errors.length
    || presenceCase.syncAttempts !== 1
    || presenceCase.presenceAttempts !== 1
    || !presenceCase.modalVisible
    || presenceCase.saveDisabled
    || presenceCase.saveAriaDisabled !== 'false'
    || presenceCase.toasts.at(-1)?.type !== 'error'
    || !presenceCase.toasts.at(-1)?.message.includes('unsaved changes remain here')
    || presenceCase.fixtureErrors.length
    || presenceCase.errors.length
    || profileCase.profileAttempts !== 1
    || profileCase.syncAttempts !== 1
    || profileCase.presenceAttempts !== 1
    || !profileCase.modalVisible
    || profileCase.saveDisabled
    || profileCase.saveAriaDisabled !== 'false'
    || profileCase.toasts.at(-1)?.type !== 'error'
    || !profileCase.toasts.at(-1)?.message.includes('Your name could not be saved')
    || profileCase.fixtureErrors.length
    || profileCase.errors.length;
  if (failed || guestFailed || saveCaseFailed) throw new Error(JSON.stringify({results, guest, guestErrors, saveCases}));
  process.stdout.write(`${JSON.stringify({results, guest, saveCases})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
