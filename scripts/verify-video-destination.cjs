const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { chromium } = require('playwright');

async function inspect(page, selector, expected) {
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html', {waitUntil: 'load'});

  const visible = await page.locator(`${selector} [data-cv-destination]`).evaluateAll(buttons => buttons
    .filter(button => !button.hidden && getComputedStyle(button).display !== 'none')
    .map(button => button.dataset.cvDestination));
  assert.deepEqual(visible, expected);

  await page.locator(`${selector} [data-cv-destination="video"]`).click();
  const direct = await page.evaluate(() => ({
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    title: document.getElementById('crump53WorkspaceTitle').textContent,
    active: document.querySelector('[data-cv-destination="video"].is-active')?.dataset.cvDestination || '',
  }));
  assert.deepEqual(direct, {studioOpen: true, section: 'video', title: 'Video Studio', active: 'video'});

  await page.evaluate(() => document.getElementById('crump53Close').click());
  await page.evaluate(() => window.CrumpNavigation5930.open('create'));
  await page.locator('[data-crump5930-create="video"]').click();
  const createHandoff = await page.evaluate(() => ({
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    active: document.querySelector('[data-cv-destination="video"].is-active')?.dataset.cvDestination || '',
  }));
  assert.deepEqual(createHandoff, {section: 'video', active: 'video'});
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
    ['Ask', 'Start with what you need.'],
    ['Projects', 'Give continuing work a home.'],
    ['Files', 'Find every useful result.'],
    ['Library', 'Keep long-form work on its own shelf.'],
    ['Video', 'Give motion its own studio.'],
    ['Autonomous', 'Hand off a bounded coding task.'],
    ['Profile', 'Your account has one clear home.'],
  ];
  const desktopDestinations = ['Ask', 'Projects', 'Files', 'Library', 'Video', 'Autonomous', 'Profile'];
  const mobileDestinations = ['Ask', 'Projects', 'Library', 'Video', 'More'];
  const mobileMore = new Set(['Files', 'Autonomous', 'Profile']);
  const steps = [];
  for (const [index, [destination, title]] of expectedSteps.entries()) {
    await page.goto('http://127.0.0.1:8765/tests/fixtures/five-destination-tutorial.html', {waitUntil: 'load'});
    for (let advance = 0; advance < index; advance += 1) {
      await page.locator('.tutorial-btn-primary').click();
    }
    const guide = await page.evaluate(() => ({
      progress: document.querySelector('.tutorial-progress-label')?.textContent || '',
      title: document.getElementById('tutorialTitle')?.textContent || '',
      desktopDestinations: [...document.querySelectorAll('.tutorial-destination-group:first-child .tutorial-destination-map span')].map(item => item.textContent),
      mobileDestinations: [...document.querySelectorAll('.tutorial-destination-group:last-child .tutorial-destination-map span')].map(item => item.textContent),
      desktopCurrent: document.querySelector('.tutorial-destination-group:first-child .is-current')?.textContent || '',
      mobileCurrent: document.querySelector('.tutorial-destination-group:last-child .is-current')?.textContent || '',
      action: document.querySelector('.tutorial-open-destination')?.textContent || '',
      description: document.getElementById('tutorialDescription')?.textContent || '',
      features: [...document.querySelectorAll('.tutorial-feature')].map(item => item.textContent || ''),
    }));
    assert.deepEqual({
      progress: guide.progress,
      title: guide.title,
      desktopDestinations: guide.desktopDestinations,
      mobileDestinations: guide.mobileDestinations,
      desktopCurrent: guide.desktopCurrent,
      mobileCurrent: guide.mobileCurrent,
      action: guide.action,
    }, {
      progress: `${index + 1} / 7`,
      title,
      desktopDestinations,
      mobileDestinations,
      desktopCurrent: destination,
      mobileCurrent: mobileMore.has(destination) ? 'More' : destination,
      action: destination === 'Autonomous' ? 'Open Autonomous Crump →' : `Open ${destination} →`,
    });
    if (destination === 'Files') {
      assert.match(guide.description, /home for documents, presentations, images, video exports, and uploads/i);
      assert.deepEqual(guide.features, ['Preview in the app', 'Download originals', 'Organized by Project']);
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
  const desktop = await inspect(
    await browser.newPage({viewport: {width: 1280, height: 800}}),
    '.cv-rail-nav',
    // This fixture intentionally has no authenticated coding-provider probe.
    // Autonomous therefore remains fail-closed here; its configured and
    // entitled states are exercised by verify-code-lazy-load.cjs.
    ['ask', 'projects', 'files', 'library', 'video'],
  );
  const mobile = await inspect(
    await browser.newPage({viewport: {width: 390, height: 844}}),
    '#cvMobileNav',
    ['ask', 'projects', 'library', 'video', 'more'],
  );
  const tutorial = await inspectTutorial(await browser.newPage({viewport: {width: 390, height: 844}}));
  await browser.close();
  process.stdout.write(JSON.stringify({desktop, mobile, tutorial}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
