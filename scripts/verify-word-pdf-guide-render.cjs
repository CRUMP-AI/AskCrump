const path = require('node:path');
const os = require('node:os');
const {chromium} = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8766';
const route = '/guides/word-or-pdf-ai-document-output.html';
const expectedHref = '/ai-document-generator?signup=1&plan=free&acquisition=organic-search&source=workflow-guide&campaign=word-or-pdf-decision&creative=search-article&intent=document';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function inspect(page, viewport, screenshotName) {
  await page.setViewportSize(viewport);
  const response = await page.goto(`${baseUrl}${route}`, {waitUntil: 'networkidle'});
  assert(response && response.status() === 200, `page returned ${response?.status()}`);
  for (const image of await page.locator('img[loading="lazy"]').all()) {
    await image.scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState('networkidle');
  const screenshotPath = path.join(os.tmpdir(), screenshotName);
  await page.screenshot({path: screenshotPath, fullPage: true});
  const state = await page.evaluate(() => ({
    title: document.title,
    h1: document.querySelector('h1')?.textContent?.trim() || '',
    robots: document.querySelector('meta[name="robots"]')?.content || '',
    viewportWidth: window.innerWidth,
    bodyWidth: document.body.scrollWidth,
    primaryCount: document.querySelectorAll('.button.primary').length,
    primaryHref: document.querySelector('.button.primary')?.getAttribute('href') || '',
    overflowers: [...document.querySelectorAll('body *')]
      .map(element => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          id: element.id,
          className: String(element.className || ''),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
          scrollWidth: element.scrollWidth,
        };
      })
      .filter(item => item.left < -1 || item.right > window.innerWidth + 1)
      .slice(0, 20),
    imageStates: [...document.images].map(image => {
      const rect = image.getBoundingClientRect();
      return {
        source: image.getAttribute('src'),
        loading: image.loading,
        top: Math.round(rect.top),
        width: Math.round(rect.width),
        display: getComputedStyle(image).display,
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight,
        complete: image.complete,
      };
    }),
  }));
  assert(state.title === 'Word or PDF? Choose the Right AI Document Output | Ask Crump', 'title drifted');
  assert(state.h1 === 'Word or PDF? Start with what happens next.', 'H1 drifted');
  assert(state.robots === 'index,follow,max-image-preview:large', 'public robots contract drifted');
  assert(
    state.bodyWidth <= state.viewportWidth,
    `horizontal overflow ${state.bodyWidth}/${state.viewportWidth}: ${JSON.stringify(state.overflowers)}`,
  );
  assert(state.primaryCount === 1, `expected one primary CTA, found ${state.primaryCount}`);
  assert(state.primaryHref === expectedHref, 'primary CTA tuple drifted');
  assert(state.imageStates.length === 4, `expected four authentic images, found ${state.imageStates.length}`);
  for (const image of state.imageStates) {
    assert(
      image.complete && image.naturalWidth > 0 && image.naturalHeight > 0,
      `image failed: ${JSON.stringify(image)}`,
    );
  }
  return {viewport, screenshotPath, ...state};
}

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage();
  const consoleErrors = [];
  const externalRequests = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') externalRequests.push(request.url());
  });
  await page.route('**/_vercel/**', route => route.fulfill({
    status: 200,
    contentType: 'application/javascript',
    body: '',
  }));
  try {
    const mobile = await inspect(page, {width: 390, height: 844}, 'ask-crump-word-pdf-current-mobile-390x844.png');
    const desktop = await inspect(page, {width: 1440, height: 1000}, 'ask-crump-word-pdf-current-desktop-1440x1000.png');
    assert(externalRequests.length === 0, `external request escaped local fixture: ${externalRequests.join(', ')}`);
    assert(consoleErrors.length === 0, `browser console errors: ${consoleErrors.join(' | ')}`);
    console.log(JSON.stringify({
      status: 'PASS',
      route,
      mobile,
      desktop,
      consoleErrors,
      externalRequests,
      credentialsEntered: false,
      accountCreated: false,
      analyticsSent: false,
      productionVisited: false,
    }, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error.message);
  process.exit(1);
});
