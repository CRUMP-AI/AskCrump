const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

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
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];

  for (const entry of cases) {
    const page = await browser.newPage();
    const browserErrors = [];
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });
    page.on('pageerror', error => browserErrors.push(error.message));
    await page.goto('http://127.0.0.1:8765/tests/fixtures/auth-navigation-focus.html', {
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
      return {
        reason: failure?.data?.reason || '',
        error: document.getElementById('loginError')?.textContent || '',
      };
    });
    results.push({name: entry.name, expected: entry.reason, ...observed, browserErrors});
    if (entry.offline) await page.context().setOffline(false);
    await page.close();
  }

  await browser.close();
  const failed = results.filter(result => (
    result.reason !== result.expected
    || !result.error
    || result.browserErrors.length
  ));
  if (failed.length) throw new Error(`Login failure classification failed: ${JSON.stringify(failed)}`);
  console.log(JSON.stringify(results, null, 2));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
