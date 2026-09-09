const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || process.env.CODEX_BROWSER_EXECUTABLE
  || undefined;
const fixturePath = '/tests/fixtures/presentation-attribution-registration.html';
const touches = [
  {name: 'facebook-profile', acquisition: 'facebook', placement: 'profile-link', campaign: 'presentation-proof-current', creative: null, intent: 'presentation'},
  {name: 'instagram-profile', acquisition: 'instagram', placement: 'profile-link', campaign: 'presentation-proof-current', creative: null, intent: 'presentation'},
  {name: 'facebook-feed', acquisition: 'facebook', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'fb-static', intent: 'presentation'},
  {name: 'instagram-story', acquisition: 'instagram', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'ig-story', intent: 'presentation'},
  {name: 'paid-facebook-feed', acquisition: 'paid-social', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'projects'},
];
const rejections = [
  {name: 'facebook-story-cross-pair', acquisition: 'facebook', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'ig-story', intent: 'presentation'},
  {name: 'instagram-feed-cross-pair', acquisition: 'instagram', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'fb-static', intent: 'presentation'},
  {name: 'profile-creative', acquisition: 'instagram', placement: 'profile-link', campaign: 'presentation-proof-current', creative: 'ig-feed', intent: 'presentation'},
  {name: 'facebook-profile-creative', acquisition: 'facebook', placement: 'profile-link', campaign: 'presentation-proof-current', creative: 'fb-static', intent: 'presentation'},
  {name: 'retired-ig-feed', acquisition: 'instagram', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'ig-feed', intent: 'presentation'},
  {name: 'blank-feed-creative', acquisition: 'facebook', placement: 'organic-social', campaign: 'presentation-proof-current', creative: '', intent: 'presentation'},
  {name: 'wrong-placement', acquisition: 'facebook', placement: 'workflow-guide', campaign: 'presentation-proof-current', creative: 'fb-static', intent: 'presentation'},
  {name: 'wrong-intent', acquisition: 'facebook', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'fb-static', intent: 'document'},
  {name: 'unlisted-acquisition', acquisition: 'linkedin', placement: 'organic-social', campaign: 'presentation-proof-current', creative: 'fb-static', intent: 'presentation'},
  {name: 'paid-organic-placement', acquisition: 'paid-social', placement: 'organic-social', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'projects'},
  {name: 'organic-paid-placement', acquisition: 'facebook', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'projects'},
  {name: 'paid-story', acquisition: 'paid-social', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-story', intent: 'projects'},
  {name: 'paid-reel', acquisition: 'paid-social', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-reel', intent: 'projects'},
  {name: 'instagram-paid', acquisition: 'instagram', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'projects'},
  {name: 'paid-profile', acquisition: 'paid-social', placement: 'profile-link', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'projects'},
  {name: 'paid-workflow', acquisition: 'paid-social', placement: 'workflow-guide', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'projects'},
  {name: 'paid-missing-creative', acquisition: 'paid-social', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: null, intent: 'projects'},
  {name: 'paid-wrong-campaign', acquisition: 'paid-social', placement: 'facebook-paid', campaign: 'presentation-proof-current', creative: 'rough-to-useful-current-feed', intent: 'projects'},
  {name: 'paid-wrong-intent', acquisition: 'paid-social', placement: 'facebook-paid', campaign: 'rough-to-useful-v2', creative: 'rough-to-useful-current-feed', intent: 'presentation'},
];

function attributionQuery(touch, {signup = false} = {}) {
  const query = new URLSearchParams({
    ...(signup ? {signup: '1'} : {}),
    acquisition: touch.acquisition,
    source: touch.placement,
    campaign: touch.campaign,
    intent: touch.intent,
  });
  if (touch.creative !== null) query.set('creative', touch.creative);
  return query;
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  const rejectedResults = [];
  try {
    for (const expected of touches) {
      const context = await browser.newContext();
      await context.route('**/favicon.ico', route => route.fulfill({status: 204, body: ''}));
      const page = await context.newPage();
      const browserErrors = [];
      page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
      page.on('pageerror', error => browserErrors.push(error.message));

      await page.goto(`${baseUrl}${fixturePath}?${attributionQuery(expected, {signup: true})}`, {waitUntil: 'load'});
      const registration = await page.evaluate(() => ({
        stored: JSON.parse(sessionStorage.getItem('askcrump.first-touch-attribution') || 'null'),
        registerCalls: window.__fixture.registerCalls,
        registrationVisible: getComputedStyle(document.querySelector('#registerForm')).display !== 'none',
        errors: window.__fixture.errors.slice(),
      }));
      assert.equal(registration.registerCalls, 0, `${expected.name} unexpectedly submitted registration`);
      assert.equal(registration.registrationVisible, true, `${expected.name} did not reach registration`);
      for (const key of ['acquisition', 'placement', 'campaign', 'creative', 'intent']) {
        assert.equal(registration.stored[key], expected[key], `${expected.name} stored touch changed ${key}`);
      }

      await page.goto(`${baseUrl}${fixturePath}?verified=1`, {waitUntil: 'load'});
      const afterVerification = await page.evaluate(() =>
        JSON.parse(sessionStorage.getItem('askcrump.first-touch-attribution') || 'null'));
      for (const key of ['acquisition', 'placement', 'campaign', 'creative', 'intent']) {
        assert.equal(afterVerification[key], expected[key], `${expected.name} verification return changed ${key}`);
      }

      const competing = new URLSearchParams({
        signin: '1', acquisition: 'instagram', source: 'organic-social',
        campaign: 'real-product-continuity', creative: 'continuity-story', intent: 'projects',
      });
      await page.goto(`${baseUrl}${fixturePath}?${competing}`, {waitUntil: 'load'});
      const afterSignIn = await page.evaluate(() => ({
        stored: JSON.parse(sessionStorage.getItem('askcrump.first-touch-attribution') || 'null'),
        errors: window.__fixture.errors.slice(),
      }));
      for (const key of ['acquisition', 'placement', 'campaign', 'creative', 'intent']) {
        assert.equal(afterSignIn.stored[key], expected[key], `${expected.name} sign-in changed ${key}`);
      }
      assert.deepEqual(registration.errors, []);
      assert.deepEqual(afterSignIn.errors, []);
      assert.deepEqual(browserErrors, []);
      results.push({name: expected.name, firstTouch: registration.stored, firstTouchImmutable: true});
      await context.close();
    }

    for (const rejected of rejections) {
      const context = await browser.newContext();
      await context.route('**/favicon.ico', route => route.fulfill({status: 204, body: ''}));
      const page = await context.newPage();
      const browserErrors = [];
      page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
      page.on('pageerror', error => browserErrors.push(error.message));
      await page.goto(`${baseUrl}${fixturePath}?${attributionQuery(rejected)}`, {waitUntil: 'load'});
      const state = await page.evaluate(() => ({
        stored: JSON.parse(sessionStorage.getItem('askcrump.first-touch-attribution') || 'null'),
        events: window.__fixture.events.slice(),
        registerCalls: window.__fixture.registerCalls,
        errors: window.__fixture.errors.slice(),
      }));
      assert.equal(state.stored.acquisition, rejected.acquisition, `${rejected.name} changed acquisition`);
      assert.equal(state.stored.placement, rejected.placement, `${rejected.name} changed placement`);
      assert.equal(state.stored.campaign, null, `${rejected.name} accepted the campaign`);
      assert.equal(state.stored.creative, null, `${rejected.name} accepted the creative`);
      assert.equal(state.stored.intent, rejected.intent, `${rejected.name} changed intent`);
      assert.equal(state.events.includes('MarketingLanding'), false, `${rejected.name} emitted marketing analytics`);
      assert.equal(state.registerCalls, 0, `${rejected.name} submitted registration`);
      assert.deepEqual(state.errors, []);
      assert.deepEqual(browserErrors, []);
      rejectedResults.push({name: rejected.name, campaign: null, creative: null});
      await context.close();
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(`${JSON.stringify({
    runs: results.length,
    rejectionRuns: rejectedResults.length,
    credentialsEntered: false,
    networkAccountCreated: false,
    analyticsSent: false,
    results,
    rejections: rejectedResults,
  })}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
