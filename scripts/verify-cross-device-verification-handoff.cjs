const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
const fixtureUrl = `${fixtureOrigin}/tests/fixtures/creation-intent-handoff.html`;

async function harness(browser) {
  const context = await browser.newContext({viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const errors = [];
  const httpFailures = [];
  const networkViolations = [];
  const allowedOrigin = new URL(fixtureOrigin).origin;
  const protectedPath = /\/(?:media|features?|billing|providers?|checkout|uploads?|generations?|credits?)(?:\/|$)/i;
  page.on('request', request => {
    const url = new URL(request.url());
    const method = request.method().toUpperCase();
    if (
      method !== 'GET'
      || url.origin !== allowedOrigin
      || url.pathname === '/api'
      || url.pathname.startsWith('/api/')
      || protectedPath.test(url.pathname)
    ) networkViolations.push(`${method} ${url.origin}${url.pathname}`);
  });
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400) httpFailures.push(`${response.status()} ${response.url()}`);
  });
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+5MzdAAAAAElFTkSuQmCC',
      'base64',
    ),
  }));
  return {context, page, errors, httpFailures, networkViolations};
}

async function state(page) {
  return page.evaluate(() => ({
    calls: [...window.__fixture.calls],
    forbidden: [...window.__fixture.forbidden],
    consumed: [...window.__fixture.consumed],
    pendingCreation: localStorage.getItem('askcrump.pending-creation-intent'),
    pendingPlan: localStorage.getItem('askcrump.pending-plan-intent'),
    query: location.search,
    errors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
    registration: {
      visible: Boolean(document.getElementById('registerForm')?.getClientRects().length),
      title: document.getElementById('registrationTitle')?.textContent || '',
      description: document.getElementById('registrationDescription')?.textContent || '',
      button: document.getElementById('registrationSubmitBtn')?.textContent || '',
      assurance: document.getElementById('registrationAssurance')?.textContent || '',
      explore: document.getElementById('registrationExploreLink')?.getAttribute('href') || '',
      exploreLabel: document.getElementById('registrationExploreLink')?.textContent || '',
    },
  }));
}

async function waitForCalls(page, count) {
  await page.waitForFunction(expected => window.__fixture?.calls?.length === expected, count);
  await page.waitForTimeout(40);
}

function assertClean(current) {
  assert.deepEqual(current.httpFailures, []);
  assert.deepEqual(current.errors, []);
  assert.deepEqual(current.networkViolations, []);
}

async function verifySameTab(browser) {
  const current = await harness(browser);
  await current.page.goto(
    `${fixtureUrl}?auth=0&signup=1&source=image&plan=professional&intent=image`,
    {waitUntil: 'domcontentloaded'},
  );
  await current.page.waitForFunction(() => {
    const pending = JSON.parse(localStorage.getItem('askcrump.pending-creation-intent') || 'null');
    return pending?.kind === 'image';
  });
  const signedOut = await state(current.page);
  assert.deepEqual(signedOut.calls, []);
  assert.equal(JSON.parse(signedOut.pendingCreation).kind, 'image');
  assert.equal(JSON.parse(signedOut.pendingPlan).plan, 'professional');
  assert.equal(signedOut.registration.title, 'Open your Image Studio.');
  assert.match(signedOut.registration.description, /Professional includes Advanced Intelligence/);
  assert.equal(signedOut.registration.button, 'Create account & open Image Studio');
  assert.match(signedOut.registration.assurance, /does not start billing/);
  assert.equal(signedOut.registration.explore, '/#use-cases');
  assert.equal(signedOut.registration.exploreLabel, 'See Image Studio details first');

  await current.page.goto(fixtureUrl, {waitUntil: 'domcontentloaded'});
  await waitForCalls(current.page, 1);
  const delivered = await state(current.page);
  assert.deepEqual(delivered.calls, [{tool: 'image', action: 'open'}]);
  assert.equal(delivered.consumed.length, 1);
  assert.equal(delivered.consumed[0].kind, 'image');
  assert(delivered.consumed[0].capturedAt > 0);
  assert.equal(delivered.pendingCreation, null);
  assert.equal(delivered.pendingPlan, null);
  assert.deepEqual(delivered.forbidden, []);
  assert.equal(delivered.query, '');

  await current.page.reload({waitUntil: 'domcontentloaded'});
  await current.page.waitForTimeout(120);
  const replay = await state(current.page);
  assert.deepEqual(replay.calls, []);
  assert.deepEqual(replay.consumed, []);
  assert.equal(replay.pendingCreation, null);
  assert.equal(replay.pendingPlan, null);
  assert.deepEqual(replay.forbidden, []);
  assertClean(current);
  await current.context.close();
  return {signedOut, delivered, replay};
}

async function verifyCrossDevice(browser) {
  const current = await harness(browser);
  await current.page.goto(
    `${fixtureUrl}?verification=success&source=image&plan=professional&intent=image`,
    {waitUntil: 'domcontentloaded'},
  );
  await waitForCalls(current.page, 1);
  const result = await state(current.page);
  assert.deepEqual(result.calls, [{tool: 'image', action: 'open'}]);
  assert.equal(result.consumed.length, 1);
  assert.equal(result.consumed[0].kind, 'image');
  assert(result.consumed[0].capturedAt > 0);
  assert.equal(result.pendingCreation, null);
  assert.equal(result.pendingPlan, null);
  assert.equal(result.query, '');
  assert.deepEqual(result.forbidden, []);
  assert.equal(result.errors, 0);
  assertClean(current);
  await current.context.close();
  return result;
}

async function verifyAuthenticatedFullCta(browser) {
  const current = await harness(browser);
  await current.page.goto(
    `${fixtureUrl}?signup=1&source=image&plan=professional&intent=image`,
    {waitUntil: 'domcontentloaded'},
  );
  await waitForCalls(current.page, 1);
  const delivered = await state(current.page);
  assert.deepEqual(delivered.calls, [{tool: 'image', action: 'open'}]);
  assert.equal(delivered.pendingCreation, null);
  assert.equal(delivered.pendingPlan, null);
  assert.equal(delivered.query, '');
  assert.equal(delivered.registration.visible, false);
  assert.deepEqual(delivered.forbidden, []);

  await current.page.reload({waitUntil: 'domcontentloaded'});
  await current.page.waitForTimeout(120);
  const replay = await state(current.page);
  assert.deepEqual(replay.calls, []);
  assert.deepEqual(replay.consumed, []);
  assert.equal(replay.query, '');
  assert.equal(replay.registration.visible, false);
  assert.deepEqual(replay.forbidden, []);
  assertClean(current);
  await current.context.close();
  return {delivered, replay};
}

async function verifyInvalidIntent(browser) {
  const current = await harness(browser);
  await current.page.goto(
    `${fixtureUrl}?auth=0&signup=1&intent=image`,
    {waitUntil: 'domcontentloaded'},
  );
  await current.page.waitForFunction(() => Boolean(
    localStorage.getItem('askcrump.pending-creation-intent'),
  ));
  await current.page.goto(
    `${fixtureUrl}?verification=success&intent=private-prompt`,
    {waitUntil: 'domcontentloaded'},
  );
  await current.page.waitForTimeout(120);
  const result = await state(current.page);
  assert.deepEqual(result.calls, []);
  assert.deepEqual(result.consumed, []);
  assert.equal(result.pendingCreation, null);
  assert.equal(result.pendingPlan, null);
  assert.equal(result.query, '');
  assert.deepEqual(result.forbidden, []);
  assert.equal(result.errors, 0);
  assertClean(current);
  await current.context.close();
  return result;
}

async function verifyUnavailableImageStudio(browser) {
  const current = await harness(browser);
  await current.page.goto(
    `${fixtureUrl}?verification=success&intent=image&plan=professional&imageRuntime=0`,
    {waitUntil: 'domcontentloaded'},
  );
  await current.page.waitForTimeout(120);
  const result = await state(current.page);
  assert.deepEqual(result.calls, []);
  assert.deepEqual(result.consumed, []);
  assert.equal(JSON.parse(result.pendingCreation).kind, 'image');
  assert.equal(JSON.parse(result.pendingPlan).plan, 'professional');
  assert.deepEqual(result.forbidden, []);
  assert.equal(result.errors, 0);

  await current.page.reload({waitUntil: 'domcontentloaded'});
  await waitForCalls(current.page, 1);
  const recovered = await state(current.page);
  assert.deepEqual(recovered.calls, [{tool: 'image', action: 'open'}]);
  assert.equal(recovered.consumed.length, 1);
  assert.equal(recovered.consumed[0].kind, 'image');
  assert(recovered.consumed[0].capturedAt > 0);
  assert.equal(recovered.pendingCreation, null);
  assert.equal(recovered.pendingPlan, null);
  assert.equal(recovered.query, '');
  assert.deepEqual(recovered.forbidden, []);
  assert.equal(recovered.errors, 0);
  assertClean(current);
  await current.context.close();
  return {blocked: result, recovered};
}

async function verifyExistingPresentationPlan(browser) {
  const current = await harness(browser);
  await current.page.goto(
    `${fixtureUrl}?verification=success&intent=presentation&plan=professional`,
    {waitUntil: 'domcontentloaded'},
  );
  await waitForCalls(current.page, 2);
  const result = await state(current.page);
  assert.ok(result.calls.some(call => (
    call.tool === 'document' && call.action === 'select' && call.format === 'pptx'
  )));
  assert.ok(result.calls.some(call => (
    call.tool === 'plan' && call.action === 'open' && call.plan === 'professional'
  )));
  assert.equal(result.pendingCreation, null);
  assert.equal(result.pendingPlan, null);
  assert.equal(result.query, '');
  assert.deepEqual(result.forbidden, []);
  assert.equal(result.errors, 0);
  assertClean(current);
  await current.context.close();
  return result;
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  try {
    const sameTab = await verifySameTab(browser);
    const crossDevice = await verifyCrossDevice(browser);
    const authenticatedFullCta = await verifyAuthenticatedFullCta(browser);
    const invalid = await verifyInvalidIntent(browser);
    const unavailableImageStudio = await verifyUnavailableImageStudio(browser);
    const existingPresentationPlan = await verifyExistingPresentationPlan(browser);
    process.stdout.write(`${JSON.stringify({
      sameTab,
      crossDevice,
      authenticatedFullCta,
      invalid,
      unavailableImageStudio,
      existingPresentationPlan,
    })}\n`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
