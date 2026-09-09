const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const browserErrors = [];
  page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
  page.on('pageerror', error => browserErrors.push(error.message));

  await page.goto(`${baseUrl}/tests/fixtures/outcome-issue-categories.html`, {waitUntil: 'networkidle'});
  await page.getByRole('button', {name: 'Not yet'}).click();
  await page.getByText('Thanks — what missed the mark? Optional.').waitFor();

  const expectedLabels = [
    'Wrong facts',
    'Missed request',
    'Format or clarity',
    'Image or video quality',
    'Slow or failed',
    'Safety or rejection',
    'Something else',
  ];
  for (const label of expectedLabels) {
    assert.equal(await page.getByRole('button', {name: `Feedback category: ${label}`}).count(), 1);
  }

  await page.evaluate(() => { window.__fixture.failNextCategory = true; });
  await page.getByRole('button', {name: 'Feedback category: Wrong facts'}).click();
  await page.waitForFunction(() => window.__fixture.toasts.length === 1);
  assert.equal(await page.getByRole('button', {name: 'Feedback category: Wrong facts'}).isEnabled(), true);

  await page.getByRole('button', {name: 'Feedback category: Missed request'}).click();
  await page.getByText('Thanks — that helps us improve.').waitFor();
  assert.equal(await page.locator('.outcome-issue-btn').count(), 0);

  await page.evaluate(() => window.renderMessages(window.__fixtureMessages));
  await page.getByText('Thanks — that helps us improve.').waitFor();
  assert.equal(await page.locator('.outcome-issue-btn').count(), 0);

  const result = await page.evaluate(() => ({
    analytics: window.__fixture.analytics,
    fixtureErrors: window.__fixture.errors,
    toasts: window.__fixture.toasts,
    horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  }));
  assert.deepEqual(result.analytics, [
    {
      eventName: 'OutcomeFeedbackSubmitted',
      values: {eventKey: 'outcome-feedback:response-issue-fixture', source: 'needs_work'},
    },
    {
      eventName: 'OutcomeIssueCategorized',
      values: {eventKey: 'outcome-issue:response-issue-fixture', source: 'accuracy'},
    },
    {
      eventName: 'OutcomeIssueCategorized',
      values: {eventKey: 'outcome-issue:response-issue-fixture', source: 'instructions'},
    },
  ]);
  assert.deepEqual(result.fixtureErrors, []);
  assert.deepEqual(result.toasts, ['Feedback category could not be saved. Try again.']);
  assert.equal(result.horizontalOverflow, false);
  assert.deepEqual(browserErrors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({result, browserErrors})}\n`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
