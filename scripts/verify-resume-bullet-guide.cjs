const path = require('node:path');
const os = require('node:os');
const {chromium} = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8766';
const route = '/guides/audit-ai-resume-bullets.html';
const expectedHref = '/app?signup=1&source=resume-audit-start&plan=free&intent=resume&acquisition=direct';
const expectedCanonical = 'https://www.askcrump.com/guides/audit-ai-resume-bullets';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function inspect(page, viewport, screenshotName) {
  await page.setViewportSize(viewport);
  const response = await page.goto(`${baseUrl}${route}`, {waitUntil: 'networkidle'});
  assert(response && response.status() === 200, `page returned ${response?.status()}`);
  for (const image of await page.locator('img[loading="lazy"]').all()) {
    await image.scrollIntoViewIfNeeded();
    await page.waitForTimeout(150);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState('networkidle');
  const screenshotPath = path.join(os.tmpdir(), screenshotName);
  await page.screenshot({path: screenshotPath, fullPage: true});
  const state = await page.evaluate(() => ({
    title: document.title,
    h1: document.querySelector('h1')?.textContent?.trim() || '',
    robots: document.querySelector('meta[name="robots"]')?.content || '',
    canonical: document.querySelector('link[rel="canonical"]')?.href || '',
    ogUrl: document.querySelector('meta[property="og:url"]')?.content || '',
    ogImage: document.querySelector('meta[property="og:image"]')?.content || '',
    published: document.querySelector('meta[property="article:published_time"]')?.content || '',
    modified: document.querySelector('meta[property="article:modified_time"]')?.content || '',
    viewportWidth: window.innerWidth,
    bodyWidth: document.body.scrollWidth,
    primaryCount: document.querySelectorAll('.button.primary').length,
    primaryHref: document.querySelector('.button.primary')?.getAttribute('href') || '',
    auditRows: document.querySelectorAll('.guide-audit-table tbody tr').length,
    auditHeaders: [...document.querySelectorAll('.guide-audit-table th')].map(node => node.textContent.trim()),
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
          containedOverflow: Boolean(element.closest('.guide-table-wrap')),
        };
      })
      .filter(item => item.left < -1 || item.right > window.innerWidth + 1)
      .filter(item => !item.containedOverflow)
      .slice(0, 20),
    imageStates: [...document.images].map(image => ({
      source: image.getAttribute('src'),
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
      complete: image.complete,
      alt: image.getAttribute('alt') || '',
    })),
  }));
  assert(state.title === 'Fact-Check AI Résumé Bullets: A Five-Part Proof Test | Ask Crump', 'title drifted');
  assert(state.h1 === 'Fact-check AI résumé bullets before they reach an application.', 'H1 drifted');
  assert(state.robots === 'index,follow,max-image-preview:large', 'public robots contract drifted');
  assert(state.canonical === expectedCanonical, 'canonical drifted');
  assert(state.ogUrl === expectedCanonical, 'Open Graph URL drifted');
  assert(state.ogImage === 'https://www.askcrump.com/assets/social/ask-crump-resumes.png', 'Open Graph image drifted');
  assert(state.published === '2026-09-10' && state.modified === '2026-09-10', 'article dates drifted');
  assert(state.bodyWidth <= state.viewportWidth, `horizontal overflow ${state.bodyWidth}/${state.viewportWidth}: ${JSON.stringify(state.overflowers)}`);
  assert(state.overflowers.length === 0, `unexpected viewport overflow: ${JSON.stringify(state.overflowers)}`);
  assert(state.primaryCount === 1, `expected one primary CTA, found ${state.primaryCount}`);
  assert(state.primaryHref === expectedHref, 'direct-safe primary CTA drifted');
  assert(state.auditRows === 6 && state.auditHeaders.length === 4, 'claim audit table drifted');
  assert(state.imageStates.filter(image => image.source === '/assets/examples/resume-product-operations.png').length === 2, 'authentic résumé evidence count drifted');
  for (const image of state.imageStates) {
    assert(image.complete && image.naturalWidth > 0 && image.naturalHeight > 0, `image failed: ${JSON.stringify(image)}`);
    assert(image.alt.length > 0, `image lacks alt text: ${JSON.stringify(image)}`);
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
  await page.route('**/_vercel/**', route => route.fulfill({status: 200, contentType: 'application/javascript', body: ''}));
  try {
    const mobile = await inspect(page, {width: 390, height: 844}, 'ask-crump-resume-audit-mobile-390x844.png');
    const desktop = await inspect(page, {width: 1440, height: 1000}, 'ask-crump-resume-audit-desktop-1440x1000.png');
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
