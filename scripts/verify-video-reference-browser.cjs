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

  const fixtureBaseUrl = process.env.ASKCRUMP_FIXTURE_BASE_URL || 'http://127.0.0.1:8765';
  await page.goto(`${fixtureBaseUrl}/tests/fixtures/video-reference-upload.html`, {waitUntil: 'networkidle'});
  await page.evaluate(() => localStorage.removeItem('askcrump.videoRequest53'));

  await page.evaluate(() => window.CrumpProduct53.handleCreationHandoff({
    kind: 'video',
    brief: 'Animate the approved bus while preserving its appearance.',
    autoOpen: true,
    // The browser must still fail safe if a stale handoff asks to auto-start.
    autoStart: true,
    idempotencyKey: 'chat-video:reference-fixture',
    referenceFiles: [
      {id: '00000000-0000-0000-0000-000000000021', name: 'bus.png', type: 'image/png', size: 100},
      {id: '00000000-0000-0000-0000-000000000022', name: 'mascot.png', type: 'image/png', size: 100},
    ],
  }));
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 2);
  const handoffResult = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    selectedEngine: document.querySelector('#crump53VideoEngine')?.value || '',
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
    roleSelectors: document.querySelectorAll('[data-video-reference-role]').length,
  }));
  if (
    handoffResult.requestStarted
    || handoffResult.selectedEngine !== 'extendable'
    || handoffResult.referenceCards !== 2
    || handoffResult.roleSelectors !== 2
    || !handoffResult.status.includes('press Create video to confirm')
    || !handoffResult.status.includes('Confirm each reference role')
    || !handoffResult.status.includes('Exact logos and readable text are not locked')
  ) {
    throw new Error(JSON.stringify({handoffResult, consoleErrors}));
  }

  await page.locator('#crump53VideoEngine').selectOption('quick');
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
  await page.locator('[data-video-reference-role]').nth(1).selectOption('logo');
  await page.locator('#crump53VideoPrompt').fill('A blue school bus drives carefully through a quiet neighborhood.');
  await page.locator('#crump53GenerateVideo').click();
  await page.waitForFunction(() => Boolean(window.__videoRequest));

  const result = await page.evaluate(() => {
    const storedRequest = localStorage.getItem(`askcrump.videoRequest53:${encodeURIComponent(window.currentUser.id)}`) || '';
    return {
      label: document.querySelector('#crump53VideoReferenceLabel')?.textContent || '',
      referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
      referenceFileIds: window.__videoRequest?.referenceFileIds || [],
      referencePlan: window.__videoRequest?.referencePlan || [],
      requestContainsImageData: /base64|data:image/i.test(JSON.stringify(window.__videoRequest || {})),
      recoveryContainsImageData: /base64|data:image/i.test(storedRequest),
      unscopedRequestPresent: Boolean(localStorage.getItem('askcrump.videoRequest53')),
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
    || result.referenceCards !== 2
    || result.referenceFileIds.length !== 2
    || JSON.stringify(result.referencePlan) !== JSON.stringify([
      {fileId: '00000000-0000-0000-0000-000000000011', role: 'subject'},
      {fileId: '00000000-0000-0000-0000-000000000012', role: 'logo'},
    ])
    || result.requestContainsImageData
    || result.recoveryContainsImageData
    || result.unscopedRequestPresent
    || result.selectedEngine !== 'extendable'
    || result.runwayAttributionVisible
    || result.mobileOverflow
    || result.errorOverlay
  ) {
    throw new Error(JSON.stringify({result, consoleErrors}));
  }
  process.stdout.write(`${JSON.stringify({result, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
