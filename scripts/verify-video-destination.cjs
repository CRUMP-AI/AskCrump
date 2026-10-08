const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { chromium } = require('playwright');

const expected = ['home', 'chats', 'projects', 'library', 'studios', 'you'];

async function inspect(page, selector) {
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html', {waitUntil: 'load'});

  const visible = await page.locator(`${selector} [data-crump5930-destination]`).evaluateAll(buttons => buttons
    .filter(button => !button.hidden && getComputedStyle(button).display !== 'none')
    .map(button => button.dataset.crump5930Destination));
  assert.deepEqual(visible, expected);

  await page.locator(`${selector} [data-crump5930-destination="studios"]`).click();
  await page.locator('[data-crump5930-studio="video"]').click();
  const direct = await page.evaluate(() => ({
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    title: document.getElementById('crump53WorkspaceTitle').textContent,
    active: document.querySelector('[data-crump5930-destination="studios"].is-active')?.dataset.crump5930Destination || '',
  }));
  assert.deepEqual(direct, {studioOpen: true, section: 'video', title: 'Video Studio', active: 'studios'});

  await page.evaluate(() => document.getElementById('crump53Close').click());
  await page.locator(`${selector} [data-crump5930-destination="studios"]`).click();
  await page.locator('[data-crump5930-studio="video"]').click();
  const createHandoff = await page.evaluate(() => ({
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    active: document.querySelector('[data-crump5930-destination="studios"].is-active')?.dataset.crump5930Destination || '',
  }));
  assert.deepEqual(createHandoff, {section: 'video', active: 'studios'});
  assert.deepEqual(errors, []);
  return {visible, direct, createHandoff, errors};
}

async function inspectTutorial(page) {
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));
  const expectedSteps = [
    ['Home', 'Welcome home.'],
    ['Chats', 'Every conversation, kept.'],
    ['Projects', 'Give continuing work a home.'],
    ['Library', 'Keep the things you create.'],
    ['Studios', 'A studio for everything you make.'],
    ['You', 'Your account has one clear home.'],
  ];
  const steps = [];
  for (const [index, [destination, title]] of expectedSteps.entries()) {
    await page.goto('http://127.0.0.1:8765/tests/fixtures/five-destination-tutorial.html', {waitUntil: 'load'});
    for (let advance = 0; advance < index; advance += 1) {
      await page.locator('.tutorial-btn-primary').click();
    }
    const guide = await page.evaluate(() => ({
      progress: document.querySelector('.tutorial-progress-label')?.textContent || '',
      title: document.getElementById('tutorialTitle')?.textContent || '',
      destinations: [...document.querySelectorAll('.tutorial-destination-map span')].map(item => item.textContent),
      current: document.querySelector('.tutorial-destination-map .is-current')?.textContent || '',
      action: document.querySelector('.tutorial-open-destination')?.textContent || '',
      description: document.getElementById('tutorialDescription')?.textContent || '',
      features: [...document.querySelectorAll('.tutorial-feature')].map(item => item.textContent || ''),
    }));
    assert.deepEqual({
      progress: guide.progress,
      title: guide.title,
      destinations: guide.destinations,
      current: guide.current,
      action: guide.action,
    }, {
      progress: `${index + 1} / 6`,
      title,
      destinations: ['Home', 'Chats', 'Projects', 'Library', 'Studios', 'You'],
      current: destination,
      action: `Open ${destination} →`,
    });
    if (destination === 'Studios') {
      assert.deepEqual(guide.features, ['Editable files', 'Local image adjustments', 'Video, manuscripts & code']);
      assert.match(guide.description, /Precision Edit/);
      assert.match(guide.description, /optional visual references/);
    }
    await page.locator('.tutorial-open-destination').click();
    await page.waitForFunction(expected => document.getElementById('fixtureDestination')?.textContent === expected, destination.toLowerCase());
    assert.equal(await page.locator('#fixtureDestination').textContent(), destination.toLowerCase());
    steps.push({...guide, opened: destination.toLowerCase()});
  }
  assert.deepEqual(errors, []);
  return {steps, errors};
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
