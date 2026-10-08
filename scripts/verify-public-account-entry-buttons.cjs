const { chromium } = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8770';
const executablePath = process.env.ASK_CRUMP_BROWSER_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

const creationPages = new Map([
  ['/ai-document-generator.html', 'document'],
  ['/ai-presentation-maker.html', 'presentation'],
  ['/ai-project-workspace.html', 'projects'],
  ['/ai-resume-builder.html', 'resume'],
  ['/ai-video-generator.html', 'video'],
]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function normalizedAppUrl(href) {
  const destination = new URL(href, baseUrl);
  destination.pathname = '/app.html';
  return destination.href;
}

function pageErrors(page) {
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return errors;
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await context.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    await context.route('**/api/auth/check-session*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: false }),
    }));
    const authMutations = [];
    const registrationPayloads = [];
    await context.route('**/api/auth/register', route => {
      authMutations.push('register');
      registrationPayloads.push(route.request().postDataJSON());
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({success: true, message: 'Verification email sent.', pendingAccount: false}),
      });
    });
    await context.route('**/api/auth/resend-verification', route => {
      authMutations.push('resend-verification');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({success: true, message: 'Verification email sent.'}),
      });
    });
    const page = await context.newPage();
    const errors = pageErrors(page);

    for (const [path, expectedIntent] of creationPages) {
      await page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });
      const ctas = await page.locator('[data-cta]').evaluateAll(nodes => nodes.map(node => ({
        name: node.dataset.cta,
        plan: node.dataset.plan,
        href: node.getAttribute('href'),
      })));
      assert(ctas.length > 0, `${path} has no account-entry actions`);
      for (const cta of ctas) {
        const destination = new URL(cta.href, baseUrl);
        assert(destination.pathname === '/app', `${path} ${cta.name} misses /app`);
        assert(destination.searchParams.get('intent') === expectedIntent, `${path} ${cta.name} drops ${expectedIntent} intent`);
        assert(destination.searchParams.get('plan') === cta.plan, `${path} ${cta.name} plan mismatch`);
        if (cta.name.includes('signin')) {
          assert(!destination.searchParams.has('signup'), `${path} ${cta.name} incorrectly opens registration`);
        } else {
          assert(destination.searchParams.get('signup') === '1', `${path} ${cta.name} does not open registration`);
        }
      }
    }

    await page.goto(`${baseUrl}/ask-crump.html`, { waitUntil: 'networkidle' });
    const videoHref = await page.locator('[data-cta="video"]').getAttribute('href');
    const videoDestination = new URL(videoHref, baseUrl);
    assert(videoDestination.searchParams.get('intent') === 'video', 'homepage Video button drops the Video intent');
    assert(videoDestination.searchParams.get('plan') === 'professional', 'homepage Video button drops the Professional plan review');

    await page.goto(normalizedAppUrl(videoHref), { waitUntil: 'networkidle' });
    assert(await page.locator('#registrationTitle').textContent() === 'Open your Video Studio.', 'Video signup title is generic');
    assert((await page.locator('#registrationDescription').textContent()).includes('find completed clips in Projects → Files'), 'Video delivery promise is missing');
    assert(await page.locator('#registrationExploreLink').textContent() === 'Explore Video Studio first', 'Video explore action is generic');
    assert(await page.locator('#registrationSubmitBtn').textContent() === 'Create account & review Professional', 'paid plan remains unclear before account creation');
    assert(await page.locator('#registerEmail').evaluate(node => node === document.activeElement), 'Video registration does not focus the email field');

    await page.locator('#showLoginLink').click();
    assert(await page.locator('#loginForm').isVisible(), 'registration Sign in link does not open login');
    await page.locator('#showRegisterLink').click();
    assert(await page.locator('#registerForm').isVisible(), 'login Create account link does not open registration');
    await page.locator('#showLoginLink').click();
    await page.locator('#showForgotPasswordLink').click();
    assert(await page.locator('#forgotPasswordForm').isVisible(), 'Forgot password link does not open recovery');
    await page.locator('#showLoginFromForgot').click();
    assert(await page.locator('#loginForm').isVisible(), 'recovery Sign in link does not return to login');

    await page.locator('#showRegisterLink').click();
    await page.locator('#registerEmail').fill('correct-this@example.test');
    await page.locator('#registerPassword').fill('CorrectionProof12345');
    await page.locator('#registerTerms').check();
    await page.locator('#registerFormElement').evaluate(form => form.requestSubmit());
    await page.locator('#registrationPending').waitFor({state: 'visible'});
    assert(authMutations.join(',') === 'register', 'registration proof did not make exactly one account request');
    await page.locator('#registrationPendingDifferentEmailBtn').click();
    await page.waitForFunction(() => document.activeElement?.id === 'registerEmail');
    const correctionState = await page.evaluate(() => {
      const email = document.getElementById('registerEmail');
      const password = document.getElementById('registerPassword');
      return {
        pendingVisible: document.getElementById('registrationPending').style.display !== 'none',
        entryVisible: document.getElementById('registerEntry').style.display !== 'none',
        email: email.value,
        password: password.value,
        passwordType: password.type,
        focused: document.activeElement === email,
        toggleText: document.getElementById('registerPasswordToggle').textContent,
        togglePressed: document.getElementById('registerPasswordToggle').getAttribute('aria-pressed'),
        passwordInvalid: password.getAttribute('aria-invalid'),
        passwordStatus: document.getElementById('registerPasswordStatus').textContent,
        metRules: document.querySelectorAll('#registerPasswordHint [data-password-rule].is-met').length,
        notice: document.getElementById('registerSuccess').textContent,
      };
    });
    assert(!correctionState.pendingVisible, 'Use a different email leaves the pending screen visible');
    assert(correctionState.entryVisible, 'Use a different email does not restore registration');
    assert(correctionState.email === 'correct-this@example.test', 'Use a different email loses the address to correct');
    assert(correctionState.password === '', 'Use a different email retains the prior password');
    assert(correctionState.passwordType === 'password', 'Use a different email leaves the password visible');
    assert(correctionState.toggleText === 'Show' && correctionState.togglePressed === 'false', 'Use a different email leaves stale password-toggle state');
    assert(correctionState.passwordInvalid === null, 'Use a different email leaves stale password validation state');
    assert(correctionState.metRules === 0, 'Use a different email leaves stale password rule checks');
    assert(correctionState.passwordStatus.includes('Password requires'), 'Use a different email leaves stale password guidance');
    assert(correctionState.focused, 'Use a different email does not focus the address');
    assert(correctionState.notice.includes('enter your password again'), 'Use a different email does not explain the safe retry');
    assert(authMutations.join(',') === 'register', 'Use a different email performs an unexpected network mutation');
    await page.locator('#registerPassword').fill('UnchangedProof12345');
    await page.locator('#registerFormElement').evaluate(form => form.requestSubmit());
    assert(authMutations.join(',') === 'register', 'unchanged correction email performed an unexpected account request');
    assert((await page.locator('#registerError').textContent()).includes('Enter a different email address'), 'unchanged correction email is not rejected clearly');
    await page.keyboard.type('replacement@example.test');
    assert(await page.locator('#registerEmail').inputValue() === 'replacement@example.test', 'Use a different email does not select the prior address for replacement');
    await page.locator('#registerPassword').fill('ReplacementProof12345');
    await page.locator('#registerFormElement').evaluate(form => form.requestSubmit());
    await page.waitForFunction(() => document.getElementById('registrationPending')?.style.display !== 'none');
    assert(authMutations.join(',') === 'register,register', 'corrected registration did not make exactly one deliberate follow-up request');
    assert(registrationPayloads.length === 2, 'corrected registration payload was not captured exactly twice');
    assert(registrationPayloads[1].email === 'replacement@example.test', 'corrected registration sent the stale email');
    assert(registrationPayloads[1].password === 'ReplacementProof12345', 'corrected registration did not send the re-entered password');

    await page.goto(`${baseUrl}/app.html?token=button-proof`, { waitUntil: 'networkidle' });
    assert(await page.locator('#resetPasswordForm').isVisible(), 'reset token does not open the reset form');
    await page.locator('#showLoginFromReset').click();
    assert(await page.locator('#loginForm').isVisible(), 'reset Back to sign in link does not return to login');
    assert(!(new URL(page.url())).searchParams.has('token'), 'reset Back to sign in leaves the reset token in the URL');

    const bodyWidth = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(bodyWidth <= 1, `Video registration overflows the phone viewport by ${bodyWidth}px`);
    assert(errors.length === 0, `browser errors: ${errors.join(' | ')}`);

    const socialContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      userAgent: 'Mozilla/5.0 (Linux; Android 15; Mobile) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36 [FBAN/FB4A;FBAV/500.0.0.0.0;]',
    });
    await socialContext.addInitScript(() => {
      window.__socialFunnelEvents = [];
      window.va = (command, payload) => {
        if (command === 'event') window.__socialFunnelEvents.push(payload);
      };
    });
    await socialContext.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    await socialContext.route('**/api/auth/check-session*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: false }),
    }));
    const socialPage = await socialContext.newPage();
    const socialErrors = pageErrors(socialPage);
    const socialUrl = `${baseUrl}/app.html?signup=1&acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=projects`;
    await socialPage.goto(socialUrl, {
      waitUntil: 'networkidle',
      referer: 'https://m.facebook.com/',
    });

    assert(await socialPage.locator('#registerForm').isVisible(), 'Facebook mobile handoff does not show registration');
    assert(
      await socialPage.locator('#registrationTitle').textContent() === 'Open your private Project workspace.',
      'Facebook mobile handoff loses the promised Projects outcome',
    );
    assert(
      await socialPage.locator('#registerEmail').evaluate(node => node === document.activeElement),
      'Facebook mobile handoff does not focus the email field',
    );
    assert(
      await socialPage.evaluate(() => document.referrer === 'https://m.facebook.com/'),
      'Facebook mobile handoff does not preserve the browser referrer',
    );

    await socialPage.locator('#registerEmail').fill('social-proof@example.test');
    await socialPage.locator('#registerPassword').fill('SocialProof12345');
    const socialEvents = await socialPage.evaluate(() => window.__socialFunnelEvents);
    for (const name of ['SignupIntent', 'SignupStarted', 'SignupCredentialsReady']) {
      const matches = socialEvents.filter(event => event?.name === name);
      assert(matches.length === 1, `Facebook mobile handoff recorded ${matches.length} ${name} events`);
      const data = matches[0].data || {};
      assert(data.acquisition === 'facebook', `${name} loses Facebook acquisition`);
      assert(data.source === 'organic-social', `${name} loses organic-social placement`);
      assert(data.campaign === 'real-product-continuity', `${name} loses campaign`);
      assert(data.creative === 'continuity-feed', `${name} loses creative`);
      assert(data.intent === 'projects', `${name} loses Projects intent`);
    }
    assert(
      socialEvents.find(event => event?.name === 'SignupIntent')?.data?.location === 'deep-link',
      'Facebook mobile handoff does not retain the deep-link signup location',
    );
    assert(socialErrors.length === 0, `Facebook mobile browser errors: ${socialErrors.join(' | ')}`);
    await socialContext.close();

    console.log('Public account-entry button proof passed: five creation surfaces preserve their destination, the homepage Video action opens the exact Video + Professional handoff, auth navigation and local email correction work safely on phone width, and a Facebook embedded-mobile handoff reaches Projects registration with one privacy-safe signup milestone sequence.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
