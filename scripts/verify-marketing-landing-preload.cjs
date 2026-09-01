const { chromium } = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8766';
const executablePath = process.env.ASK_CRUMP_BROWSER_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const analyticsScriptUrl = 'https://www.askcrump.com/_vercel/insights/script.js';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function analyticsRuntime() {
  const response = await fetch(analyticsScriptUrl, {
    headers: { 'Cache-Control': 'no-cache' },
  });
  assert(response.ok, `live Vercel analytics runtime returned HTTP ${response.status}`);
  const body = await response.text();
  assert(body.includes('window.vaq'), 'live Vercel analytics runtime does not drain window.vaq');
  return body;
}

async function createPage(browser, script) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36',
  });
  await context.addInitScript(() => {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
      configurable: true,
      get: () => undefined,
    });
  });
  const events = [];
  await context.route('**/_vercel/insights/script.js', route => route.fulfill({
    status: 200,
    contentType: 'application/javascript',
    body: script,
  }));
  await context.route('**/_vercel/insights/event*', async route => {
    events.push(JSON.parse(route.request().postData() || '{}'));
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await context.route('**/_vercel/insights/view*', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: '{}',
  }));
  await context.route('**/_vercel/speed-insights/**', route => route.fulfill({ status: 204, body: '' }));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return { context, page, events, errors };
}

function marketingLandings(events) {
  return events.filter(event => event?.en === 'MarketingLanding');
}

(async () => {
  const script = await analyticsRuntime();
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    const campaign = await createPage(browser, script);
    const firstUrl = `${baseUrl}/guides/rough-idea-six-week-launch-plan.html?acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=projects`;
    await campaign.page.goto(firstUrl, { waitUntil: 'load' });
    await campaign.page.waitForFunction(() => sessionStorage.getItem('askcrump.marketing-landing-emitted') === '1');
    await campaign.page.waitForTimeout(250);
    const firstEvents = marketingLandings(campaign.events);
    assert(firstEvents.length === 1, `exact deferred order emitted ${firstEvents.length} campaign landing events`);
    assert(JSON.stringify(firstEvents[0].ed) === JSON.stringify({
      touchpoint: 'facebook.organic-social.real-product-continuity.continuity-feed',
      intent: 'projects',
    }), 'deferred queue produced the wrong content-free campaign payload');

    const secondUrl = `${baseUrl}/guides/rough-idea-six-week-launch-plan.html?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-story&intent=projects`;
    await campaign.page.goto(secondUrl, { waitUntil: 'load' });
    await campaign.page.waitForTimeout(250);
    assert(marketingLandings(campaign.events).length === 1, 'same-tab navigation emitted a second landing event');
    assert(campaign.errors.length === 0, `exact-order campaign errors: ${campaign.errors.join(' | ')}`);
    await campaign.context.close();

    const profile = await createPage(browser, script);
    const profileUrl = `${baseUrl}/guides/rough-idea-six-week-launch-plan.html?acquisition=facebook&source=profile-link&campaign=real-product-continuity&intent=projects`;
    await profile.page.goto(profileUrl, { waitUntil: 'load' });
    await profile.page.waitForTimeout(250);
    const profileState = await profile.page.evaluate(() => ({
      firstTouch: JSON.parse(sessionStorage.getItem('askcrump.first-touch-attribution') || 'null'),
      marker: sessionStorage.getItem('askcrump.marketing-landing-emitted'),
    }));
    assert(profileState.firstTouch?.campaign === 'real-product-continuity', 'profile-link campaign was not preserved');
    assert(profileState.firstTouch?.creative === null, 'profile-link unexpectedly invented a creative');
    const profileEvents = marketingLandings(profile.events);
    assert(profileState.marker === '1', 'registered profile-link did not write the once marker after queueing');
    assert(profileEvents.length === 1, `registered profile-link emitted ${profileEvents.length} landing events`);
    assert(JSON.stringify(profileEvents[0].ed) === JSON.stringify({
      touchpoint: 'facebook.profile-link.real-product-continuity',
      intent: 'projects',
    }), 'registered profile-link invented a creative or emitted the wrong touchpoint');
    assert(profile.errors.length === 0, `profile-link browser errors: ${profile.errors.join(' | ')}`);
    await profile.context.close();

    console.log('Marketing landing preload proof passed: the official deferred queue drains exact feed and creative-free profile events while preserving same-tab immutability.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
