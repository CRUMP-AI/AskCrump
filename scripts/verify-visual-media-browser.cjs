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

  await page.goto('http://127.0.0.1:8765/tests/fixtures/image-upload-preview-stability.html', {
    waitUntil: 'networkidle',
  });
  await page.waitForFunction(() => document.documentElement.dataset.crump50Booted === 'true');
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  await page.locator('#fileInput').setInputFiles({name: 'fixture.png', mimeType: 'image/png', buffer: png});
  await page.waitForFunction(() => document.querySelector('[data-crump50-upload-meta]')?.textContent.includes('B'));

  const result = await page.evaluate(() => ({
    previewImagesAdded: window.__previewImagesAdded,
    previewImageCount: document.querySelectorAll('.crump50-upload-visual img').length,
    cardCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    status: document.querySelector('[data-crump50-upload-meta]')?.textContent || '',
    bodyHasContent: document.body.innerText.trim().length > 0,
    errorOverlay: Boolean(document.querySelector('[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay')),
  }));
  await page.screenshot({path: 'artifacts/visual-media-preview-stability.png', fullPage: true});
  await browser.close();

  if (
    consoleErrors.length
    || result.previewImagesAdded !== 1
    || result.previewImageCount !== 1
    || result.cardCount !== 1
    || !result.bodyHasContent
    || result.errorOverlay
  ) {
    throw new Error(JSON.stringify({result, consoleErrors}));
  }
  process.stdout.write(`${JSON.stringify({result, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
