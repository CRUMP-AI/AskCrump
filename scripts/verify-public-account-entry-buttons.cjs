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

    await page.goto(`${baseUrl}/app.html?token=button-proof`, { waitUntil: 'networkidle' });
    assert(await page.locator('#resetPasswordForm').isVisible(), 'reset token does not open the reset form');
    await page.locator('#showLoginFromReset').click();
    assert(await page.locator('#loginForm').isVisible(), 'reset Back to sign in link does not return to login');
    assert(!(new URL(page.url())).searchParams.has('token'), 'reset Back to sign in leaves the reset token in the URL');

    const bodyWidth = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(bodyWidth <= 1, `Video registration overflows the phone viewport by ${bodyWidth}px`);
    assert(errors.length === 0, `browser errors: ${errors.join(' | ')}`);
    console.log('Public account-entry button proof passed: five creation surfaces preserve their destination, the homepage Video action opens the exact Video + Professional handoff, and all five auth navigation actions work on phone width.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
