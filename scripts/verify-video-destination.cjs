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
  await page.waitForFunction(() => document.documentElement.dataset.cvShell === 'ready');

  const visible = await page.locator(`${selector} [data-cv-destination]`).evaluateAll(buttons => buttons
    .filter(button => !button.hidden && getComputedStyle(button).display !== 'none')
    .map(button => button.dataset.cvDestination));
  assert.deepEqual(visible, expected);

  // Studios is no longer a destination: its legacy id resolves to Projects.
  await page.evaluate(() => window.CrumpVision.navigate('studios'));
  const direct = await page.evaluate(() => ({
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    title: document.getElementById('crump53WorkspaceTitle').textContent,
    active: document.querySelector('[data-cv-destination="projects"].is-active')?.dataset.cvDestination || '',
  }));
  assert.deepEqual(direct, {studioOpen: true, section: 'projects', title: 'Projects', active: 'projects'});

  await page.evaluate(() => document.getElementById('crump53Close').click());
  await page.evaluate(() => window.CrumpNavigation5930.open('create'));
  await page.locator('[data-crump5930-create="video"]').click();
  const createHandoff = await page.evaluate(() => ({
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    active: document.querySelector('[data-cv-destination="projects"].is-active')?.dataset.cvDestination || '',
  }));
  assert.deepEqual(createHandoff, {section: 'video', active: 'projects'});
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
    ['Today', 'Start with the outcome.'],
    ['Chat', 'Every conversation, easy to find.'],
    ['Tasks', 'Work you can follow, in one record.'],
    ['Projects', 'Give continuing work a home.'],
    ['You', 'Your account has one clear home.'],
  ];
  const desktopDestinations = ['Today', 'Chat', 'Tasks', 'Projects', 'You'];
  const mobileDestinations = ['Today', 'Chat', 'Tasks', 'Projects', 'You'];
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
      progress: `${index + 1} / 5`,
      title,
      desktopDestinations,
      mobileDestinations,
      desktopCurrent: destination,
      mobileCurrent: destination,
      action: `Open ${destination} →`,
    });
    if (destination === 'Tasks') {
      assert.match(guide.description, /record of work Crump is doing for you/i);
      assert.deepEqual(guide.features, ['Waiting on you', 'Live work', 'Finished results']);
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
    ['today', 'chat', 'tasks', 'projects', 'you'],
  );
  const mobile = await inspect(
    await browser.newPage({viewport: {width: 390, height: 844}}),
    '#cvMobileNav',
    ['today', 'chat', 'tasks', 'projects', 'you'],
  );
  const tutorial = await inspectTutorial(await browser.newPage({viewport: {width: 390, height: 844}}));
  await browser.close();
  process.stdout.write(JSON.stringify({desktop, mobile, tutorial}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
