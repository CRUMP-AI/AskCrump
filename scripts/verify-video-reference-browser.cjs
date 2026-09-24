const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  await page.route('**/api/files/*/content', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: png,
  }));
  const consoleErrors = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', error => consoleErrors.push(error.message));

  await page.goto('http://127.0.0.1:8765/tests/fixtures/video-reference-upload.html', {waitUntil: 'networkidle'});
  await page.evaluate(() => localStorage.removeItem('askcrump.videoRequest53'));

  await page.evaluate(() => window.CrumpProduct53.handleCreationHandoff({
    kind: 'video',
    brief: 'Animate the approved bus while preserving its appearance.',
    autoOpen: true,
    autoStart: true,
    idempotencyKey: 'chat-video:reference-fixture',
    referenceFiles: [
      {id: '00000000-0000-0000-0000-000000000021', name: 'bus.png', type: 'image/png', size: 100, role: 'subject'},
      {id: '00000000-0000-0000-0000-000000000022', name: 'mascot.png', type: 'image/png', size: 100, role: 'mascot'},
    ],
  }));
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 2);
  const handoffResult = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    selectedEngine: document.querySelector('#crump53VideoEngine')?.value || '',
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }));
  if (
    handoffResult.requestStarted
    || handoffResult.selectedEngine !== 'extendable'
    || handoffResult.referenceCards !== 2
    || JSON.stringify(handoffResult.roles) !== JSON.stringify(['subject', 'mascot'])
    || !handoffResult.status.includes('Confirm each ordered role')
    || !handoffResult.status.includes('before credits')
    || !handoffResult.status.includes('Exact logos and readable text are not locked')
  ) {
    throw new Error(JSON.stringify({handoffResult, consoleErrors}));
  }

  await page.evaluate(() => window.CrumpProduct53.handleCreationHandoff({
    kind: 'video',
    brief: 'Do not start with a missing reference.',
    autoOpen: true,
    autoStart: true,
    idempotencyKey: 'chat-video:invalid-reference-fixture',
    referenceFiles: [
      {id: '00000000-0000-0000-0000-000000000025', name: 'valid.png', type: 'image/png', size: 100},
      {id: '00000000-0000-0000-0000-000000000026', name: 'invalid.pdf', type: 'application/pdf', size: 100},
    ],
  }));
  await page.locator('#crump53GenerateVideo').click();
  const invalidHandoff = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    statusIsError: document.querySelector('#crump53VideoStatus')?.classList.contains('is-error') || false,
  }));
  if (
    invalidHandoff.requestStarted
    || !invalidHandoff.status.includes('Reattach them before creating')
    || !invalidHandoff.statusIsError
  ) {
    throw new Error(JSON.stringify({invalidHandoff, consoleErrors}));
  }

  await page.evaluate(() => window.CrumpProduct53.handleCreationHandoff({
    kind: 'video',
    brief: 'Use all approved references.',
    autoOpen: true,
    autoStart: true,
    idempotencyKey: 'chat-video:over-limit-fixture',
    referenceFiles: [
      {id: '00000000-0000-0000-0000-000000000031', name: 'one.png', type: 'image/png', size: 100},
      {id: '00000000-0000-0000-0000-000000000032', name: 'two.png', type: 'image/png', size: 100},
      {id: '00000000-0000-0000-0000-000000000033', name: 'three.png', type: 'image/png', size: 100},
      {id: '00000000-0000-0000-0000-000000000034', name: 'four.png', type: 'image/png', size: 100},
    ],
  }));
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 4);
  await page.locator('#crump53GenerateVideo').click();
  const overLimitResult = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    selectedEngine: document.querySelector('#crump53VideoEngine')?.value || '',
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    statusIsError: document.querySelector('#crump53VideoStatus')?.classList.contains('is-error') || false,
  }));
  if (
    overLimitResult.requestStarted
    || overLimitResult.selectedEngine !== 'extendable'
    || !/remove 1/i.test(overLimitResult.status)
    || !overLimitResult.statusIsError
  ) {
    throw new Error(JSON.stringify({overLimitResult, consoleErrors}));
  }

  await page.reload({waitUntil: 'networkidle'});
  await page.evaluate(() => localStorage.removeItem('askcrump.videoRequest53'));
  await page.locator('#openVideo').click();
  await page.locator('#crump53VideoEngine').selectOption('extendable');
  await page.locator('#crump53VideoReferenceInput').setInputFiles([
    {name: 'bus.png', mimeType: 'image/png', buffer: png},
    {name: 'logo.png', mimeType: 'image/png', buffer: png},
  ]);
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 2);
  const roleSelectors = page.locator('[data-video-reference-role]');
  await roleSelectors.nth(1).selectOption('logo');
  await page.locator('#crump53VideoPrompt').fill('A blue school bus drives carefully through a quiet neighborhood.');
  await page.locator('#crump53GenerateVideo').click();
  await page.waitForFunction(() => document.querySelector('#crump53GenerateVideo')?.textContent.includes('Confirm'));
  const beforeConfirmation = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    button: document.querySelector('#crump53GenerateVideo')?.textContent || '',
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    plan: document.querySelector('#crump53VideoReferencePlan')?.textContent || '',
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }));
  await page.locator('#crump53GenerateVideo').click();
  await page.waitForFunction(() => Boolean(window.__videoRequest));

  const result = await page.evaluate(() => {
    const storedRequest = localStorage.getItem('askcrump.videoRequest53') || '';
    return {
      label: document.querySelector('#crump53VideoReferenceLabel')?.textContent || '',
      help: document.querySelector('#crump53VideoReferenceHelp')?.textContent || '',
      referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
      referenceFileIds: window.__videoRequest?.referenceFileIds || [],
      referencePlan: window.__videoRequest?.referencePlan || [],
      requestContainsImageData: /base64|data:image/i.test(JSON.stringify(window.__videoRequest || {})),
      recoveryContainsImageData: /base64|data:image/i.test(storedRequest),
      selectedEngine: window.__videoRequest?.engine || '',
      runwayAttributionVisible: document.querySelector('#crump53RunwayAttribution')?.getClientRects().length > 0,
      mobileOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      errorOverlay: Boolean(document.querySelector('[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay')),
    };
  });
  await page.screenshot({path: 'artifacts/video-reference-mobile.png', fullPage: true});
  await browser.close();

  if (
    consoleErrors.length
    || result.label !== 'Optional appearance guidance · up to 3'
    || !result.help.includes('best-effort appearance guidance')
    || result.referenceCards !== 2
    || beforeConfirmation.requestStarted
    || beforeConfirmation.button !== 'Confirm & create video'
    || !beforeConfirmation.status.includes('Review before credits')
    || !beforeConfirmation.status.includes('Reference 1: Subject / product')
    || !beforeConfirmation.status.includes('Reference 2: Logo / wordmark')
    || !beforeConfirmation.plan.includes('ORDERED REFERENCE PLAN')
    || !beforeConfirmation.plan.includes('not a pixel-locked frame or layout')
    || JSON.stringify(beforeConfirmation.roles) !== JSON.stringify(['subject', 'logo'])
    || result.referenceFileIds.length !== 2
    || result.referencePlan.length !== 2
    || result.referencePlan[0]?.fileId !== result.referenceFileIds[0]
    || result.referencePlan[0]?.role !== 'subject'
    || result.referencePlan[1]?.fileId !== result.referenceFileIds[1]
    || result.referencePlan[1]?.role !== 'logo'
    || result.requestContainsImageData
    || result.recoveryContainsImageData
    || result.selectedEngine !== 'extendable'
    || result.runwayAttributionVisible
    || result.mobileOverflow
    || result.errorOverlay
  ) {
    throw new Error(JSON.stringify({beforeConfirmation, result, consoleErrors}));
  }
  process.stdout.write(`${JSON.stringify({beforeConfirmation, result, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
