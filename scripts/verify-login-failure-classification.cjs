const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium, webkit} = require(playwrightModule);
const browserEngineName = process.env.ASKCRUMP_AUTH_BROWSER || 'chromium';
const browserEngine = {chromium, webkit}[browserEngineName];
if (!browserEngine) throw new Error('ASKCRUMP_AUTH_BROWSER must be chromium or webkit.');

const cases = [
  {
    name: 'credentials',
    loginResult: {success: false, error: 'Invalid email or password.', code: 'INVALID_CREDENTIALS'},
    reason: 'credentials_rejected',
  },
  {
    name: 'verification',
    loginResult: {
      success: false,
      error: 'Verify your email before signing in.',
      code: 'EMAIL_VERIFICATION_REQUIRED',
      needsVerification: true,
    },
    reason: 'verification_required',
  },
  {
    name: 'rate-limit',
    loginResult: {success: false, error: 'Try again later.', code: 'RATE_LIMITED'},
    reason: 'rate_limited',
  },
  {
    name: 'session-establishment',
    loginResult: {
      success: false,
      error: 'Your session could not be established.',
      code: 'SESSION_ESTABLISHMENT_FAILED',
    },
    reason: 'session_establishment',
  },
  {
    name: 'timeout',
    loginError: {message: 'Signing in took too long.', code: 'AUTH_REQUEST_TIMEOUT'},
    reason: 'timeout',
  },
  {
    name: 'offline',
    loginError: {message: 'Network unavailable.', code: 'NETWORK_ERROR'},
    offline: true,
    reason: 'offline',
  },
  {
    name: 'unknown',
    loginError: {message: 'Temporary request failure.', code: 'UNSTRUCTURED_PRIVATE_DETAIL'},
    reason: 'request_failed',
  },
];

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await browserEngine.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];

  for (const entry of cases) {
    const page = await browser.newPage({viewport: {width: 390, height: 500}});
    const browserErrors = [];
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });
    page.on('pageerror', error => browserErrors.push(error.message));
    await page.goto('http://127.0.0.1:8765/tests/fixtures/auth-navigation-focus.html?source=login-failure-signin', {
      waitUntil: 'networkidle',
    });
    await page.evaluate(config => {
      window.__fixture.loginResult = config.loginResult || {success: false};
      window.__fixture.loginError = config.loginError || null;
      window.__fixture.events = [];
      window.__fixture.eventPayloads = [];
    }, entry);
    if (entry.offline) await page.context().setOffline(true);
    await page.locator('#loginEmail').fill('login-measurement@example.test');
    await page.locator('#loginPassword').fill('synthetic-password');
    await page.locator('#loginFormElement').evaluate(form => form.requestSubmit());
    await page.waitForFunction(() => window.__fixture.events.includes('LoginFailed'));
    const observed = await page.evaluate(() => {
      const failure = window.__fixture.eventPayloads.find(payload => payload.name === 'LoginFailed');
      const action = document.getElementById('loginRecoveryAction');
      const actionRect = action?.getBoundingClientRect();
      const recoveryVisible = Boolean(action && getComputedStyle(action).display !== 'none');
      return {
        reason: failure?.data?.reason || '',
        error: document.getElementById('loginError')?.textContent || '',
        recoveryVisible,
        recoveryInViewport: Boolean(
          recoveryVisible && actionRect && actionRect.top >= 0 && actionRect.bottom <= innerHeight
        ),
      };
    });
    if (entry.name === 'credentials') {
      await page.locator('#loginEmail').fill('');
      observed.recoveryClearedAfterEdit = await page.locator('#loginRecoveryAction').isHidden();
      await page.locator('#loginEmail').fill('login-measurement@example.test');
      await page.locator('#loginFormElement').evaluate(form => form.requestSubmit());
      await page.waitForFunction(() => (
        window.__fixture.events.filter(name => name === 'LoginFailed').length === 2
        && getComputedStyle(document.getElementById('loginRecoveryAction')).display !== 'none'
      ));
      await page.locator('#loginRecoveryAction').click();
      await page.waitForFunction(() => document.activeElement?.id === 'forgotPasswordEmail');
      Object.assign(observed, await page.evaluate(() => ({
        recoveryOpened: getComputedStyle(document.getElementById('forgotPasswordForm')).display !== 'none',
        recoveryEmail: document.getElementById('forgotPasswordEmail').value,
        recoveryFocused: document.activeElement?.id === 'forgotPasswordEmail',
        resetRequests: window.__fixture.fetchCalls.filter(url => url.includes('/api/auth/forgot-password')).length,
      })));
    }
    results.push({name: entry.name, expected: entry.reason, ...observed, browserErrors});
    if (entry.offline) await page.context().setOffline(false);
    await page.close();
  }

  await browser.close();
  const failed = results.filter(result => (
    result.reason !== result.expected
    || !result.error
    || (result.name === 'credentials' && (
      !result.recoveryVisible
      || !result.recoveryInViewport
      || !result.recoveryClearedAfterEdit
      || !result.recoveryOpened
      || result.recoveryEmail !== 'login-measurement@example.test'
      || !result.recoveryFocused
      || result.resetRequests !== 0
    ))
    || (result.name !== 'credentials' && result.recoveryVisible)
    || result.browserErrors.length
  ));
  if (failed.length) throw new Error(`Login failure classification failed: ${JSON.stringify(failed)}`);
  console.log(JSON.stringify(results, null, 2));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
