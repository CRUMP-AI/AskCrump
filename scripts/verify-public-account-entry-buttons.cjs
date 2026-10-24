const { chromium } = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8770';
const executablePath = process.env.ASK_CRUMP_BROWSER_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

const creationPages = new Map([
  ['/ai-document-generator.html', { intent: 'document', signupPlan: 'professional' }],
  ['/ai-presentation-maker.html', { intent: 'presentation', signupPlan: 'professional' }],
  ['/ai-project-workspace.html', { intent: 'projects', signupPlan: 'professional' }],
  ['/ai-resume-builder.html', { intent: 'resume', signupPlan: 'professional' }],
  ['/ai-video-generator.html', { intent: 'video', signupPlan: 'professional' }],
]);

const paidCreationDisclosures = new Map([
  ['/ai-document-generator.html', 'Document creation requires a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed'],
  ['/ai-presentation-maker.html', 'Presentation creation requires a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed'],
  ['/ai-resume-builder.html', 'Résumé creation requires a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed'],
]);

const guideSigninPages = [
  '/guides/rough-idea-six-week-launch-plan.html',
  '/guides/what-ai-project-should-remember.html',
  '/guides/editable-ai-powerpoint-review.html',
  '/guides/word-or-pdf-ai-document-output.html',
  '/guides/audit-ai-resume-bullets.html',
];

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
    await context.addInitScript(() => {
      window.__entryFunnelEvents = [];
      window.va = (command, payload) => {
        if (command === 'event') window.__entryFunnelEvents.push(payload);
      };
    });
    await context.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    await context.route('**/api/billing/credits/status*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, credits: { balance: 0 } }),
    }));
    await context.route('**/api/intelligence/preferences*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, preferences: {}, entitlements: {} }),
    }));
    let guestMinted = false;
    const guestSessionChecks = [];
    const guestAdmissionInstallationIds = [];
    const guestUser = {
      id: 'public-entry-guest-20261024',
      email: 'guest-public-entry@guest.askcrump.local',
      fullName: '',
      isVerified: false,
      isGuest: true,
      subscriptionTier: 'free',
      tier: 'free',
      termsAcceptedAt: null,
      termsVersion: null,
      freeMessageLimit: 5,
      freeMessageWindowKind: 'rolling_24h',
      freeMessageWindowSeconds: 86400,
    };
    await context.route('**/api/auth/check-session*', route => {
      guestAdmissionInstallationIds.push({
        stage: guestMinted ? 'follow-up-check' : 'initial-check',
        value: route.request().headers()['x-installation-id'] || '',
      });
      guestSessionChecks.push(guestMinted);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(guestMinted ? {
          success: true,
          authenticated: true,
          data: {user: guestUser, settings: {}},
        } : {
          success: true,
          authenticated: false,
        }),
      });
    });
    let guestMintRequests = 0;
    await context.route('**/api/auth/guest*', route => {
      guestAdmissionInstallationIds.push({
        stage: 'guest-mint',
        value: route.request().headers()['x-installation-id'] || '',
      });
      guestMintRequests += 1;
      guestMinted = true;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Guest session started.',
          data: {user: guestUser, guest: true},
        }),
      });
    });
    const page = await context.newPage();
    const errors = pageErrors(page);

    for (const [path, expected] of creationPages) {
      await page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });
      const layout = await page.evaluate(() => {
        const navCta = document.querySelector('nav .nav-cta');
        const rect = navCta?.getBoundingClientRect();
        return {
          viewportWidth: window.innerWidth,
          overflow: document.documentElement.scrollWidth - window.innerWidth,
          navCtaVisible: Boolean(navCta && rect && rect.width > 0 && rect.height > 0),
          navCtaLeft: rect?.left ?? -1,
          navCtaRight: rect?.right ?? -1,
        };
      });
      assert(layout.overflow <= 1, `${path} overflows the phone viewport by ${layout.overflow}px`);
      assert(layout.navCtaVisible, `${path} hides its account-entry action on phone width`);
      assert(layout.navCtaLeft >= 0 && layout.navCtaRight <= layout.viewportWidth, `${path} clips its account-entry action on phone width`);
      const ctas = await page.locator('[data-cta]').evaluateAll(nodes => nodes.map(node => ({
        name: node.dataset.cta,
        plan: node.dataset.plan,
        href: node.getAttribute('href'),
      })));
      assert(ctas.length > 0, `${path} has no account-entry actions`);
      for (const cta of ctas) {
        const destination = new URL(cta.href, baseUrl);
        assert(destination.pathname === '/app', `${path} ${cta.name} misses /app`);
        assert(destination.searchParams.get('intent') === expected.intent, `${path} ${cta.name} drops ${expected.intent} intent`);
        assert(destination.searchParams.get('plan') === cta.plan, `${path} ${cta.name} plan mismatch`);
        if (cta.name.includes('signin')) {
          assert(!destination.searchParams.has('signup'), `${path} ${cta.name} incorrectly opens registration`);
        } else {
          assert(cta.plan === expected.signupPlan, `${path} ${cta.name} must review ${expected.signupPlan}`);
          assert(destination.searchParams.get('signup') === '1', `${path} ${cta.name} does not open registration`);
        }
      }
      if (paidCreationDisclosures.has(path)) {
        const disclosure = (await page.locator('.hero-foot').textContent()).trim();
        assert(disclosure === paidCreationDisclosures.get(path), `${path} paid-access disclosure drifted`);
      }
    }

    await page.goto(`${baseUrl}/ask-crump.html`, { waitUntil: 'networkidle' });
    const freeCtas = await page.locator('[data-cta][data-plan="free"]').evaluateAll(nodes => nodes.map(node => ({
      name: node.dataset.cta,
      href: node.getAttribute('href'),
    })));
    assert(freeCtas.length >= 5, 'homepage is missing its free-entry actions');
    for (const cta of freeCtas) {
      const destination = new URL(cta.href, baseUrl);
      assert(destination.pathname === '/app', `homepage ${cta.name} misses /app`);
      assert(destination.searchParams.get('plan') === 'free', `homepage ${cta.name} drops the Free plan`);
      assert(!destination.searchParams.has('signup'), `homepage ${cta.name} incorrectly forces registration`);
    }
    const heroHref = await page.locator('[data-cta="hero"]').getAttribute('href');
    const videoHref = await page.locator('[data-cta="video"]').getAttribute('href');
    const videoDestination = new URL(videoHref, baseUrl);
    assert(videoDestination.searchParams.get('intent') === 'video', 'homepage Video button drops the Video intent');
    assert(videoDestination.searchParams.get('plan') === 'professional', 'homepage Video button drops the Professional plan review');

    await page.locator('[data-cta="hero"]').evaluate(node => {
      node.addEventListener('click', event => event.preventDefault(), { once: true });
    });
    await page.locator('[data-cta="hero"]').click();
    const freeEntryEvents = await page.evaluate(() => window.__entryFunnelEvents);
    const freeStarts = freeEntryEvents.filter(event => (
      event?.name === 'MarketingCTA'
      && event?.data?.location === 'hero'
      && event?.data?.plan === 'free'
    ));
    assert(freeStarts.length === 1, `homepage Start free recorded ${freeStarts.length} MarketingCTA events`);
    assert(
      !freeEntryEvents.some(event => event?.name === 'MarketingSignin' && event?.data?.location === 'hero'),
      'homepage Start free is misclassified as a sign-in event',
    );

    const guestEntryRequest = page.waitForRequest(request => (
      request.method() === 'POST'
      && new URL(request.url()).pathname === '/api/auth/guest'
    ));
    await page.goto(normalizedAppUrl(heroHref), { waitUntil: 'networkidle' });
    await guestEntryRequest;
    await page.locator('#tosModal').waitFor({ state: 'visible' });
    assert(!(await page.locator('#registerForm').isVisible()), 'homepage Start free still opens registration');
    assert(!(await page.locator('#loginForm').isVisible()), 'successful guest entry incorrectly opens Welcome back');
    assert((await page.evaluate(() => window.currentUser?.isGuest)) === true, 'successful guest entry did not authenticate the minted guest');
    assert(
      guestSessionChecks.length >= 2 && guestSessionChecks[0] === false && guestSessionChecks[1] === true,
      `guest entry session checks were ${JSON.stringify(guestSessionChecks)} instead of signed-out then authenticated guest`,
    );
    const guestAdmissionHeaders = guestAdmissionInstallationIds.slice(0, 3);
    assert(
      JSON.stringify(guestAdmissionHeaders.map(row => row.stage)) === JSON.stringify([
        'initial-check',
        'guest-mint',
        'follow-up-check',
      ]),
      `guest admission header stages drifted: ${JSON.stringify(guestAdmissionHeaders)}`,
    );
    assert(
      guestAdmissionHeaders.every(row => /^[A-Za-z0-9._:-]{16,200}$/.test(row.value)),
      `guest admission omitted a valid opaque X-Installation-ID: ${JSON.stringify(guestAdmissionHeaders)}`,
    );
    assert(
      new Set(guestAdmissionHeaders.map(row => row.value)).size === 1,
      `guest admission changed X-Installation-ID between requests: ${JSON.stringify(guestAdmissionHeaders)}`,
    );
    assert(guestMintRequests === 1, `homepage Start free issued ${guestMintRequests} guest mint requests`);

    guestMinted = false;
    await page.evaluate(() => sessionStorage.clear());
    for (const [index, guidePath] of guideSigninPages.entries()) {
      const entryQuery = index === 0
        ? '?acquisition=organic-search&source=workflow-guide&campaign=rough-idea-launch-plan&creative=search-article&intent=projects'
        : '';
      await page.goto(`${baseUrl}${guidePath}${entryQuery}`, { waitUntil: 'networkidle' });
      const signinHref = await page.locator('.nav-signin').getAttribute('href');
      const signinDestination = new URL(signinHref, baseUrl);
      assert(signinDestination.searchParams.get('source')?.includes('signin'), `${guidePath} sign in does not declare login intent`);
      assert(!signinDestination.searchParams.has('signup'), `${guidePath} sign in incorrectly requests registration`);
      if (index === 0) {
        assert(signinDestination.searchParams.get('acquisition') === 'organic-search', `${guidePath} sign in loses acquisition`);
        assert(signinDestination.searchParams.get('campaign') === 'rough-idea-launch-plan', `${guidePath} sign in loses campaign`);
        assert(signinDestination.searchParams.get('creative') === 'search-article', `${guidePath} sign in loses creative`);
        assert(
          await page.evaluate(() => sessionStorage.getItem('askcrump.acquisition-placement')) === 'workflow-guide',
          `${guidePath} sign in loses stored placement`,
        );
      }
      await page.locator('.nav-signin').evaluate(node => {
        node.addEventListener('click', event => event.preventDefault(), { once: true });
      });
      await page.locator('.nav-signin').evaluate(node => node.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
      })));
      const signinEvents = await page.evaluate(() => window.__entryFunnelEvents);
      assert(
        signinEvents.some(event => event?.name === 'MarketingSignin' && event?.data?.location?.includes('signin')),
        `${guidePath} sign in is not measured as MarketingSignin`,
      );
      const guestRequestsBeforeSignin = guestMintRequests;
      await page.goto(normalizedAppUrl(signinHref), { waitUntil: 'networkidle' });
      assert(await page.locator('#loginForm').isVisible(), `${guidePath} sign in does not open login`);
      assert(guestMintRequests === guestRequestsBeforeSignin, `${guidePath} sign in incorrectly minted a guest session`);
    }

    await page.goto(normalizedAppUrl(videoHref), { waitUntil: 'networkidle' });
    assert(await page.locator('#registrationTitle').textContent() === 'Open your Video Studio.', 'Video signup title is generic');
    assert((await page.locator('#registrationDescription').textContent()).includes('find completed clips in Files'), 'Video delivery promise is missing');
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

    await page.goto(`${baseUrl}/app.html?token=button-proof`, { waitUntil: 'networkidle' });
    assert(await page.locator('#resetPasswordForm').isVisible(), 'reset token does not open the reset form');
    await page.locator('#showLoginFromReset').click();
    assert(await page.locator('#loginForm').isVisible(), 'reset Back to sign in link does not return to login');
    assert(!(new URL(page.url())).searchParams.has('token'), 'reset Back to sign in leaves the reset token in the URL');

    const bodyWidth = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(bodyWidth <= 1, `Video registration overflows the phone viewport by ${bodyWidth}px`);
    assert(errors.length === 0, `browser errors: ${errors.join(' | ')}`);

    const registeredTakeoverContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await registeredTakeoverContext.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    await registeredTakeoverContext.route('**/api/billing/credits/status*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, credits: { balance: 0 } }),
    }));
    await registeredTakeoverContext.route('**/api/intelligence/preferences*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, preferences: {}, entitlements: {} }),
    }));
    let registeredTakeoverAuthenticated = false;
    let registeredTakeoverGuestRequests = 0;
    const registeredTakeoverChecks = [];
    const registeredTakeoverUser = {
      ...guestUser,
      id: 'public-entry-registered-takeover-20261024',
      email: 'registered-takeover@example.test',
      isVerified: true,
      isGuest: false,
    };
    await registeredTakeoverContext.route('**/api/auth/check-session*', route => {
      registeredTakeoverChecks.push(registeredTakeoverAuthenticated);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(registeredTakeoverAuthenticated ? {
          success: true,
          authenticated: true,
          data: { user: registeredTakeoverUser, settings: {} },
        } : {
          success: true,
          authenticated: false,
        }),
      });
    });
    await registeredTakeoverContext.route('**/api/auth/guest*', route => {
      registeredTakeoverGuestRequests += 1;
      registeredTakeoverAuthenticated = true;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { user: registeredTakeoverUser, guest: false },
        }),
      });
    });
    const registeredTakeoverPage = await registeredTakeoverContext.newPage();
    const registeredTakeoverErrors = pageErrors(registeredTakeoverPage);
    await registeredTakeoverPage.goto(normalizedAppUrl(heroHref), { waitUntil: 'networkidle' });
    await registeredTakeoverPage.locator('#tosModal').waitFor({ state: 'visible' });
    assert(
      (await registeredTakeoverPage.evaluate(() => window.currentUser?.isGuest)) === false,
      'registered-session takeover was misclassified as a guest',
    );
    assert(!(await registeredTakeoverPage.locator('#guestEntryForm').isVisible()), 'registered-session takeover shows a false guest failure');
    assert(!(await registeredTakeoverPage.locator('#loginForm').isVisible()), 'registered-session takeover falls through to Welcome back');
    assert(!(await registeredTakeoverPage.locator('#registerForm').isVisible()), 'registered-session takeover forces registration');
    assert(registeredTakeoverGuestRequests === 1, `registered-session takeover issued ${registeredTakeoverGuestRequests} guest requests`);
    assert(
      registeredTakeoverChecks.length >= 2
        && registeredTakeoverChecks[0] === false
        && registeredTakeoverChecks[1] === true,
      `registered-session takeover checks drifted: ${JSON.stringify(registeredTakeoverChecks)}`,
    );
    assert(registeredTakeoverErrors.length === 0, `registered-session takeover browser errors: ${registeredTakeoverErrors.join(' | ')}`);
    await registeredTakeoverContext.close();

    const authenticatedGuestSigninContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await authenticatedGuestSigninContext.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    let authenticatedGuestSigninChecks = 0;
    let authenticatedGuestSigninMints = 0;
    await authenticatedGuestSigninContext.route('**/api/auth/check-session*', route => {
      authenticatedGuestSigninChecks += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          authenticated: true,
          data: { user: guestUser, settings: {} },
        }),
      });
    });
    await authenticatedGuestSigninContext.route('**/api/auth/guest*', route => {
      authenticatedGuestSigninMints += 1;
      return route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: 'Explicit Sign in must not remint a guest.' }),
      });
    });
    const authenticatedGuestSigninPage = await authenticatedGuestSigninContext.newPage();
    const authenticatedGuestSigninErrors = pageErrors(authenticatedGuestSigninPage);
    await authenticatedGuestSigninPage.goto(
      `${baseUrl}/app.html?source=homepage-signin-action&plan=free`,
      { waitUntil: 'networkidle' },
    );
    await authenticatedGuestSigninPage.locator('#loginForm').waitFor({ state: 'visible' });
    assert(!(await authenticatedGuestSigninPage.locator('#tosModal').isVisible()), 'authenticated guest explicit Sign in shows Terms');
    assert(!(await authenticatedGuestSigninPage.locator('#appContainer').isVisible()), 'authenticated guest explicit Sign in shows workspace');
    assert(!(await authenticatedGuestSigninPage.locator('#registerForm').isVisible()), 'authenticated guest explicit Sign in shows registration');
    assert(!(await authenticatedGuestSigninPage.locator('#guestEntryForm').isVisible()), 'authenticated guest explicit Sign in shows guest-entry failure');
    assert(authenticatedGuestSigninChecks >= 1, 'authenticated guest explicit Sign in skipped the authoritative session check');
    assert(authenticatedGuestSigninMints === 0, `authenticated guest explicit Sign in issued ${authenticatedGuestSigninMints} guest remints`);
    assert(
      authenticatedGuestSigninErrors.length === 0,
      `authenticated guest explicit Sign in browser errors: ${authenticatedGuestSigninErrors.join(' | ')}`,
    );
    await authenticatedGuestSigninContext.close();

    const staleRegisteredHintContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await staleRegisteredHintContext.addInitScript(() => {
      localStorage.setItem('crump_user_cache_v4', JSON.stringify({
        id: 'stale-registered-cache-20261024',
        email: 'stale-registered@example.test',
        isGuest: false,
        isVerified: true,
      }));
    });
    await staleRegisteredHintContext.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    await staleRegisteredHintContext.route('**/api/billing/credits/status*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, credits: { balance: 0 } }),
    }));
    await staleRegisteredHintContext.route('**/api/intelligence/preferences*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, preferences: {}, entitlements: {} }),
    }));
    let staleRegisteredHintMinted = false;
    let staleRegisteredHintMints = 0;
    const staleRegisteredHintChecks = [];
    await staleRegisteredHintContext.route('**/api/auth/check-session*', route => {
      staleRegisteredHintChecks.push(staleRegisteredHintMinted);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(staleRegisteredHintMinted ? {
          success: true,
          authenticated: true,
          data: { user: guestUser, settings: {} },
        } : {
          success: true,
          authenticated: false,
        }),
      });
    });
    await staleRegisteredHintContext.route('**/api/auth/guest*', route => {
      staleRegisteredHintMints += 1;
      staleRegisteredHintMinted = true;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Guest session started.',
          data: { user: guestUser, guest: true },
        }),
      });
    });
    const staleRegisteredHintPage = await staleRegisteredHintContext.newPage();
    const staleRegisteredHintErrors = pageErrors(staleRegisteredHintPage);
    await staleRegisteredHintPage.goto(normalizedAppUrl(heroHref), { waitUntil: 'networkidle' });
    await staleRegisteredHintPage.locator('#tosModal').waitFor({ state: 'visible' });
    assert(!(await staleRegisteredHintPage.locator('#loginForm').isVisible()), 'stale registered-device hint blocks explicit Free CTA with Welcome back');
    assert(!(await staleRegisteredHintPage.locator('#registerForm').isVisible()), 'stale registered-device hint forces Free CTA registration');
    assert(staleRegisteredHintMints === 1, `stale registered-device hint issued ${staleRegisteredHintMints} guest mint requests`);
    assert(
      staleRegisteredHintChecks.length >= 2
        && staleRegisteredHintChecks[0] === false
        && staleRegisteredHintChecks[1] === true,
      `stale registered-device hint checks drifted: ${JSON.stringify(staleRegisteredHintChecks)}`,
    );
    assert(staleRegisteredHintErrors.length === 0, `stale registered-device hint browser errors: ${staleRegisteredHintErrors.join(' | ')}`);
    await staleRegisteredHintContext.close();

    const rateLimitedContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await rateLimitedContext.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
    await rateLimitedContext.route('**/api/auth/check-session*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, authenticated: false }),
    }));
    let rateLimitedGuestRequests = 0;
    await rateLimitedContext.route('**/api/auth/guest*', route => {
      rateLimitedGuestRequests += 1;
      return route.fulfill({
        status: 429,
        headers: { 'Retry-After': '3600' },
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          code: 'RATE_LIMITED',
          error: 'Too many guest preview attempts.',
          retryAfter: 3600,
        }),
      });
    });
    const rateLimitedPage = await rateLimitedContext.newPage();
    const rateLimitedErrors = pageErrors(rateLimitedPage);
    await rateLimitedPage.goto(normalizedAppUrl(heroHref), { waitUntil: 'networkidle' });
    await rateLimitedPage.locator('#guestEntryForm').waitFor({ state: 'visible' });
    const guestEntryMessage = (await rateLimitedPage.locator('#guestEntryMessage').textContent()).trim();
    assert(
      /preview.*several times.*browser or network/i.test(guestEntryMessage),
      `429 copy is not truthful about the bounded browser or shared-network limit: ${guestEntryMessage}`,
    );
    assert(/you did nothing wrong/i.test(guestEntryMessage), `429 copy blames the visitor: ${guestEntryMessage}`);
    assert(!(await rateLimitedPage.locator('#loginForm').isVisible()), '429 incorrectly falls through to Welcome back');
    assert(!(await rateLimitedPage.locator('#registerForm').isVisible()), '429 incorrectly forces registration');
    assert(rateLimitedGuestRequests === 1, `429 path issued ${rateLimitedGuestRequests} guest mint requests`);
    const unexpectedRateLimitedErrors = rateLimitedErrors.filter(error => !/status of 429/i.test(error));
    assert(unexpectedRateLimitedErrors.length === 0, `429 browser errors: ${unexpectedRateLimitedErrors.join(' | ')}`);
    await rateLimitedContext.close();

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
    await socialContext.route('**/api/auth/guest*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: false }),
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

    console.log('Public account-entry button proof passed: free homepage actions carry one stable valid opaque X-Installation-ID through the signed-out check, guest mint and authenticated follow-up, then reach the guest Terms gate without showing login or registration; a concurrent registered-session takeover routes that account normally without a false guest failure; an explicit Sign in URL keeps an authenticated guest on login without Terms, workspace, registration or a guest remint; an explicit Free CTA overrides a stale registered-device cache after the server reports no session and reaches guest Terms; a separate 429 renders truthful shared-network retry guidance instead of Welcome back; five guide sign-in actions including an attributed organic-search path preserve campaign context while opening login without minting a guest; five paid creation surfaces preserve their destination; the homepage Video action opens the exact Video + Professional handoff; all five auth navigation actions work on phone width; and a Facebook embedded-mobile handoff reaches Projects registration with one privacy-safe signup milestone sequence.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
