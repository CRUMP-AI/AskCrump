const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;

function watch(page) {
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  return errors;
}

async function composerActions(browser) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = watch(page);
  await page.goto(`${fixtureOrigin}/tests/fixtures/composer-mode-handoff.html`, {
    waitUntil: 'domcontentloaded',
  });

  const think = page.getByRole('button', {name: 'Think with Crump', exact: true});
  const research = page.getByRole('button', {name: 'Research something', exact: true});
  const file = page.getByRole('button', {name: 'Analyze a file', exact: true});
  const image = page.getByRole('button', {name: 'Create an image', exact: true});

  await think.click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'userInput');
  assert.equal(await page.locator('#userInput').inputValue(), '');

  await research.click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'userInput');
  assert.equal(await page.locator('#userInput').inputValue(), 'Search the web for ');
  await research.click();
  assert.equal(await page.locator('#userInput').inputValue(), 'Search the web for ');

  await image.click();
  assert.equal(await page.evaluate(() => window.__imageStudioOpens), 1);

  await file.click();
  assert.equal(await page.evaluate(() => window.__filePickerClicks), 1);

  await page.waitForFunction(() => window.__starterEvents.length === 5);
  const events = await page.evaluate(() => window.__starterEvents);
  assert.deepEqual(events.map(item => item.name), Array(5).fill('StarterIntentReached'));
  assert.deepEqual(events.map(item => item.detail.eventKey), Array(5).fill('first-starter-intent'));
  assert.deepEqual(events.map(item => item.detail.source), [
    'focus', 'research', 'research', 'image', 'file',
  ]);
  assert.deepEqual(errors, []);
  await page.close();
}

async function delayedProductActions(browser) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = watch(page);
  await page.goto(`${fixtureOrigin}/tests/fixtures/launchpad-runtime-race.html`, {
    waitUntil: 'domcontentloaded',
  });

  const projects = page.getByRole('button', {name: 'Start or open a Project', exact: true});
  const video = page.getByRole('button', {name: 'Create a video', exact: true});
  await projects.click();
  assert.equal(await projects.getAttribute('aria-busy'), 'true');
  assert.deepEqual(await page.evaluate(() => window.__openedProductTabs), []);

  await video.click();
  assert.equal(await projects.getAttribute('aria-busy'), null);
  assert.equal(await video.getAttribute('aria-busy'), 'true');
  await page.evaluate(() => window.makeProductRuntimeReady());
  await page.waitForFunction(() => window.__openedProductTabs.length === 1);

  assert.deepEqual(await page.evaluate(() => window.__openedProductTabs), ['video']);
  assert.equal(await video.getAttribute('aria-busy'), null);
  const events = await page.evaluate(() => window.__starterEvents);
  assert.deepEqual(events.map(item => item.name), ['StarterIntentReached', 'StarterIntentReached']);
  assert.deepEqual(events.map(item => item.detail.eventKey), [
    'first-starter-intent', 'first-starter-intent',
  ]);
  assert.deepEqual(events.map(item => item.detail.source), ['projects', 'video']);
  assert.deepEqual(errors, []);
  await page.close();
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    await composerActions(browser);
    await delayedProductActions(browser);
    process.stdout.write('First-action proof passed: six cleanly named choices preserve their exact behavior and latest runtime-delayed destination.\n');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
