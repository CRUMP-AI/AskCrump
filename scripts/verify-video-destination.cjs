const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { chromium } = require('playwright');

const expected = ['ask', 'projects', 'create', 'video', 'library', 'you'];

async function inspect(page, selector) {
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark.png', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html', {waitUntil: 'load'});

  const visible = await page.locator(`${selector} [data-crump5930-destination]`).evaluateAll(buttons => buttons
    .filter(button => !button.hidden && getComputedStyle(button).display !== 'none')
    .map(button => button.dataset.crump5930Destination));
  assert.deepEqual(visible, expected);

  await page.locator(`${selector} [data-crump5930-destination="video"]`).click();
  const direct = await page.evaluate(() => ({
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    title: document.getElementById('crump53WorkspaceTitle').textContent,
    active: document.querySelector('[data-crump5930-destination="video"].is-active')?.dataset.crump5930Destination || '',
  }));
  assert.deepEqual(direct, {studioOpen: true, section: 'video', title: 'Video Studio', active: 'video'});

  await page.evaluate(() => document.getElementById('crump53Close').click());
  await page.locator(`${selector} [data-crump5930-destination="create"]`).click();
  await page.locator('[data-crump5930-create="video"]').click();
  const createHandoff = await page.evaluate(() => ({
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    active: document.querySelector('[data-crump5930-destination="video"].is-active')?.dataset.crump5930Destination || '',
  }));
  assert.deepEqual(createHandoff, {section: 'video', active: 'video'});
  assert.deepEqual(errors, []);
  return {visible, direct, createHandoff, errors};
}

async function inspectTutorial(page) {
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark.png', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/five-destination-tutorial.html', {waitUntil: 'load'});
  await page.locator('.tutorial-btn-primary').click();
  await page.locator('.tutorial-btn-primary').click();
  await page.locator('.tutorial-btn-primary').click();
  const guide = await page.evaluate(() => ({
    progress: document.querySelector('.tutorial-progress-label')?.textContent || '',
    title: document.getElementById('tutorialTitle')?.textContent || '',
    destinations: [...document.querySelectorAll('.tutorial-destination-map span')].map(item => item.textContent),
    current: document.querySelector('.tutorial-destination-map .is-current')?.textContent || '',
    action: document.querySelector('.tutorial-open-destination')?.textContent || '',
  }));
  assert.deepEqual(guide, {
    progress: '4 / 6',
    title: 'Give motion its own studio.',
    destinations: ['Ask', 'Projects', 'Create', 'Video', 'Library', 'You'],
    current: 'Video',
    action: 'Open Video →',
  });
  await page.locator('.tutorial-open-destination').click();
  await page.waitForFunction(() => document.getElementById('fixtureDestination')?.textContent === 'video');
  assert.equal(await page.locator('#fixtureDestination').textContent(), 'video');
  assert.deepEqual(errors, []);
  return {guide, opened: 'video', errors};
}

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const desktop = await inspect(await browser.newPage({viewport: {width: 1280, height: 800}}), '.crump5930-rail-destinations');
  const mobile = await inspect(await browser.newPage({viewport: {width: 390, height: 844}}), '#crump5930MobileNav');
  const tutorial = await inspectTutorial(await browser.newPage({viewport: {width: 390, height: 844}}));
  await browser.close();
  process.stdout.write(JSON.stringify({desktop, mobile, tutorial}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
