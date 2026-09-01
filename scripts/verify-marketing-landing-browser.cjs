const { chromium } = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:4173';
const executablePath = process.env.ASK_CRUMP_BROWSER_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function createPage(browser) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  });
  await context.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
  await context.addInitScript(() => {
    window.__marketingEvents = [];
    window.va = (type, payload) => window.__marketingEvents.push({ type, payload });
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return { context, page, errors };
}

async function landingEvents(page) {
  return page.evaluate(() => window.__marketingEvents
    .filter(event => event?.payload?.name === 'MarketingLanding'));
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    const first = await createPage(browser);
    const valid = `${baseUrl}/ask-crump.html?acquisition=facebook&source=profile-link&campaign=real-product-continuity&creative=continuity-feed&intent=projects`;
    await first.page.goto(valid, { waitUntil: 'networkidle' });
    await first.page.waitForFunction(() => window.__marketingEvents.some(event => event?.payload?.name === 'MarketingLanding'));
    const validEvents = await landingEvents(first.page);
    assert(validEvents.length === 1, 'valid campaign must emit exactly once');
    assert(JSON.stringify(validEvents[0]) === JSON.stringify({
      type: 'event',
      payload: {
        name: 'MarketingLanding',
        data: {
          touchpoint: 'facebook.profile-link.real-product-continuity.continuity-feed',
          intent: 'projects',
        },
      },
    }), 'valid campaign event must contain only the exact content-free payload');
    const overflow = await first.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(overflow <= 1, `mobile landing overflows by ${overflow}px`);

    const second = `${baseUrl}/ask-crump.html?acquisition=instagram&source=profile-link&campaign=real-product-continuity&creative=continuity-story&intent=projects`;
    await first.page.goto(second, { waitUntil: 'networkidle' });
    assert((await landingEvents(first.page)).length === 0, 'second campaign in the same tab must not emit');
    assert(first.errors.length === 0, `valid campaign browser errors: ${first.errors.join(' | ')}`);
    await first.context.close();

    const referral = await createPage(browser);
    await referral.page.goto(`${baseUrl}/ask-crump.html?acquisition=referral&source=response-share`, { waitUntil: 'networkidle' });
    await referral.page.waitForFunction(() => window.__marketingEvents.some(event => event?.payload?.name === 'MarketingLanding'));
    const referralEvents = await landingEvents(referral.page);
    assert(referralEvents.length === 1, 'exact response-share referral must emit once');
    assert(JSON.stringify(referralEvents[0].payload.data) === JSON.stringify({
      touchpoint: 'referral.response-share',
      intent: 'unspecified',
    }), 'referral event payload must stay content-free');
    assert(referral.errors.length === 0, `referral browser errors: ${referral.errors.join(' | ')}`);
    await referral.context.close();

    const invalid = await createPage(browser);
    const crossCombined = `${baseUrl}/ask-crump.html?acquisition=facebook&source=profile-link&campaign=real-product-continuity&creative=continuity-story&intent=research`;
    await invalid.page.goto(crossCombined, { waitUntil: 'networkidle' });
    assert((await landingEvents(invalid.page)).length === 0, 'invalid cross-combined tuple must fail closed');
    assert(invalid.errors.length === 0, `invalid campaign browser errors: ${invalid.errors.join(' | ')}`);
    await invalid.context.close();

    console.log('Marketing landing browser proof passed: exact campaign, immutable same-tab first touch, referral, invalid tuple, and mobile layout.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
