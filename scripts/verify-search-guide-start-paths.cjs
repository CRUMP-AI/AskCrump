const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8766';
const executablePath = process.env.ASK_CRUMP_BROWSER_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

const guides = [
  {
    path: '/guides/rough-idea-six-week-launch-plan',
    key: 'rough-idea',
    intent: 'projects',
    campaign: 'rough-idea-launch-plan',
  },
  {
    path: '/guides/what-ai-project-should-remember',
    key: 'project-memory',
    intent: 'projects',
    campaign: 'project-memory-boundaries',
  },
  {
    path: '/guides/editable-ai-powerpoint-review',
    key: 'editable-powerpoint',
    intent: 'presentation',
    campaign: 'editable-powerpoint-review',
  },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function createPage(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  for (const guide of guides) {
    await context.route(`${baseUrl}${guide.path}*`, async route => {
      const requestUrl = new URL(route.request().url());
      if (requestUrl.pathname !== guide.path) return route.continue();
      const file = path.join(__dirname, '..', 'public', `${guide.path}.html`);
      return route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: fs.readFileSync(file),
      });
    });
  }
  await context.route('**/_vercel/**', route => route.fulfill({ status: 204, body: '' }));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return { context, page, errors };
}

async function destination(page, selector) {
  const href = await page.locator(selector).getAttribute('href');
  return new URL(href, baseUrl);
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    for (const guide of guides) {
      const direct = await createPage(browser);
      await direct.page.goto(`${baseUrl}${guide.path}?acquisition=direct`, { waitUntil: 'networkidle' });

      const navSelector = `[data-cta="${guide.key}-nav"]`;
      const heroSelector = `[data-cta="${guide.key}-hero"]`;
      assert(await direct.page.locator(navSelector).isVisible(), `${guide.key} nav start is hidden on phone width`);
      assert(await direct.page.locator(heroSelector).isVisible(), `${guide.key} hero start is hidden on phone width`);

      for (const selector of [navSelector, heroSelector]) {
        const target = await destination(direct.page, selector);
        assert(target.pathname === '/app', `${guide.key} start misses /app`);
        assert(target.searchParams.get('signup') === '1', `${guide.key} start misses signup handoff`);
        assert(target.searchParams.get('plan') === 'free', `${guide.key} start misses free-plan handoff`);
        assert(target.searchParams.get('intent') === guide.intent, `${guide.key} start loses intent`);
        assert(target.searchParams.get('acquisition') === 'direct', `${guide.key} direct start changes acquisition`);
        assert(!target.searchParams.has('campaign'), `${guide.key} direct start invents a campaign`);
        assert(!target.searchParams.has('creative'), `${guide.key} direct start invents a creative`);
      }

      await direct.page.locator(heroSelector).evaluate(node => {
        node.addEventListener('click', event => {
          window.__guideStartClicked = true;
          event.preventDefault();
        });
      });
      await direct.page.locator(heroSelector).click();
      assert(await direct.page.evaluate(() => window.__guideStartClicked === true), `${guide.key} hero start did not respond`);
      assert(direct.errors.length === 0, `${guide.key} direct errors: ${direct.errors.join(' | ')}`);
      await direct.context.close();

      const search = await createPage(browser);
      await search.page.goto(`${baseUrl}${guide.path}?acquisition=organic-search`, { waitUntil: 'networkidle' });
      const tracked = await destination(search.page, heroSelector);
      assert(tracked.searchParams.get('campaign') === guide.campaign, `${guide.key} search start loses campaign`);
      assert(tracked.searchParams.get('creative') === 'search-article', `${guide.key} search start loses creative`);
      assert(tracked.searchParams.get('source') === 'workflow-guide', `${guide.key} search start loses placement`);
      assert(tracked.searchParams.get('intent') === guide.intent, `${guide.key} tracked start loses intent`);
      assert(search.errors.length === 0, `${guide.key} search errors: ${search.errors.join(' | ')}`);
      await search.context.close();
    }

    console.log('Search guide start-path proof passed: all three guides expose responsive phone-width actions, preserve direct entry, and attach only the authoritative organic-search campaign tuple.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
