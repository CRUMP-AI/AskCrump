const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const consoleErrors = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', error => consoleErrors.push(error.message));

  await page.goto('http://127.0.0.1:8765/tests/fixtures/video-reference-upload.html', {waitUntil: 'networkidle'});
  await page.locator('#openVideo').click();
  await page.locator('#crump53VideoEngine').selectOption('extendable');
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  await page.locator('#crump53VideoReferenceInput').setInputFiles([
    {name: 'bus.png', mimeType: 'image/png', buffer: png},
    {name: 'logo.png', mimeType: 'image/png', buffer: png},
  ]);
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 2);
  await page.locator('#crump53VideoPrompt').fill('A blue school bus drives carefully through a quiet neighborhood.');
  await page.locator('#crump53GenerateVideo').click();
  await page.waitForFunction(() => Boolean(window.__videoRequest));

  const result = await page.evaluate(() => {
    const storedRequest = localStorage.getItem('askcrump.videoRequest53') || '';
    return {
      label: document.querySelector('#crump53VideoReferenceLabel')?.textContent || '',
      referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
      referenceFileIds: window.__videoRequest?.referenceFileIds || [],
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
    || result.label !== 'Optional appearance references · up to 3'
    || result.referenceCards !== 2
    || result.referenceFileIds.length !== 2
    || result.requestContainsImageData
    || result.recoveryContainsImageData
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
