const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const expected = Object.freeze({
  acquisition: 'instagram',
  placement: 'profile-link',
  campaign: 'presentation-proof-current',
  creative: 'ig-feed',
  intent: 'presentation',
});

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage();
  try {
    const firstTouch = new URLSearchParams({
      signup: '1',
      acquisition: expected.acquisition,
      source: expected.placement,
      campaign: expected.campaign,
      creative: expected.creative,
      intent: expected.intent,
    });
    await page.goto(
      `http://127.0.0.1:8765/tests/fixtures/presentation-attribution-registration.html?${firstTouch}`,
      {waitUntil: 'load'},
    );
    await page.fill('#registerEmail', 'presentation-fixture@example.com');
    await page.fill('#registerPassword', 'FixturePass1234');
    await page.check('#registerTerms');
    await page.click('#registrationSubmitBtn');
    await page.waitForFunction(() => window.__fixture?.registerCalls === 1);

    const result = await page.evaluate(() => ({
      payload: window.__fixture.payload,
      stored: JSON.parse(sessionStorage.getItem('askcrump.first-touch-attribution') || 'null'),
      registerCalls: window.__fixture.registerCalls,
      errors: window.__fixture.errors.length,
      currentCampaign: new URLSearchParams(location.search).get('campaign'),
    }));
    assert(result.registerCalls === 1, 'Expected exactly one local registration request.');
    assert(result.errors === 0, 'Browser fixture reported a runtime error.');
    assert(result.currentCampaign === 'real-product-continuity', 'Second valid campaign was not presented.');
    for (const [key, value] of Object.entries(expected)) {
      assert(result.payload?.[key] === value, `Registration payload changed ${key}.`);
      assert(result.stored?.[key] === value, `Stored first touch changed ${key}.`);
    }
    assert(result.payload.termsAccepted === true, 'Terms acceptance was not carried.');
    assert(result.payload.hasSyntheticCredentials === true, 'Fixture credentials did not reach the local request boundary.');

    process.stdout.write(`${JSON.stringify({
      status: 'passed',
      registerCalls: result.registerCalls,
      sameTabSecondCampaignRejected: true,
      tuple: expected,
      networkAccountCreated: false,
      analyticsSent: false,
    })}\n`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
