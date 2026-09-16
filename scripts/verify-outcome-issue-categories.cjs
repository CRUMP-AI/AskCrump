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
  const refineButtonName = 'Refine this result by writing a follow-up; nothing is sent automatically';
  assert.equal(await page.getByRole('button', {name: refineButtonName}).count(), 1);
  await page.getByRole('button', {name: refineButtonName}).click();
  await page.getByText('Tell Crump what to change below — nothing was sent.').waitFor();
  assert.deepEqual(await page.evaluate(() => ({
    activeId: document.activeElement?.id || '',
    draft: document.getElementById('userInput')?.value || '',
  })), {activeId: 'userInput', draft: 'Keep this unfinished draft'});

  await page.evaluate(() => window.renderMessages(window.__fixtureMessages));
  await page.getByText('Thanks — that helps us improve.').waitFor();
  assert.equal(await page.locator('.outcome-issue-btn').count(), 0);
  assert.equal(await page.getByRole('button', {name: refineButtonName}).count(), 1);

  const reportTrigger = page.getByRole('button', {name: 'Report this response'});
  await reportTrigger.click();
  const reportDialog = page.getByRole('dialog', {name: 'Report this response'});
  await reportDialog.waitFor();
  await reportDialog.getByLabel('Reason').selectOption('privacy');
  await reportDialog.getByLabel('Details (optional)').fill('The response repeats private information.');
  await reportDialog.getByRole('button', {name: 'Send report'}).click();
  await page.waitForFunction(() => (
    window.__fixture.reportRequests.length === 1
    && window.__fixture.toasts.at(-1) === 'Connection interrupted. Try again.'
  ));
  assert.equal(await reportDialog.count(), 1);
  assert.equal(await reportDialog.getByLabel('Reason').inputValue(), 'privacy');
  assert.equal(
    await reportDialog.getByLabel('Details (optional)').inputValue(),
    'The response repeats private information.',
  );
  assert.equal(await reportDialog.getByRole('button', {name: 'Cancel'}).isEnabled(), true);
  assert.equal(await reportDialog.getByRole('button', {name: 'Send report'}).isEnabled(), true);
  assert.equal(await reportTrigger.isEnabled(), true);

  await reportDialog.getByRole('button', {name: 'Send report'}).click();
  await page.waitForFunction(() => (
    window.__fixture.reportRequests.length === 2
    && window.__fixture.toasts.at(-1) === 'Thanks — this response was sent for safety review.'
  ));
  assert.equal(await reportDialog.count(), 0);
  assert.equal(await page.getByRole('button', {name: 'Response reported'}).isDisabled(), true);

  const result = await page.evaluate(() => ({
    analytics: window.__fixture.analytics,
    fixtureErrors: window.__fixture.errors,
    reportRequests: window.__fixture.reportRequests,
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
  assert.deepEqual(result.reportRequests, [
    {
      chatId: '00000000-0000-4000-8000-000000000091',
      messageId: 'response-issue-fixture',
      category: 'privacy',
      comment: 'The response repeats private information.',
      response: 'A fictional result used only to verify fixed-category feedback controls.',
    },
    {
      chatId: '00000000-0000-4000-8000-000000000091',
      messageId: 'response-issue-fixture',
      category: 'privacy',
      comment: 'The response repeats private information.',
      response: 'A fictional result used only to verify fixed-category feedback controls.',
    },
  ]);
  assert.deepEqual(result.toasts, [
    'Feedback category could not be saved. Try again.',
    'Connection interrupted. Try again.',
    'Thanks — this response was sent for safety review.',
  ]);
  assert.equal(result.horizontalOverflow, false);
  assert.deepEqual(browserErrors, []);

  await browser.close();
  process.stdout.write(`${JSON.stringify({result, browserErrors})}\n`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
