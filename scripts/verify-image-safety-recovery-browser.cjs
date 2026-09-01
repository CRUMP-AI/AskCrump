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

  await page.goto('http://127.0.0.1:8765/tests/fixtures/image-safety-recovery.html', {waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.documentElement.dataset.crump50Booted === 'true');
  const status = page.locator('.message-status');
  await status.click();
  await page.waitForFunction(() => document.querySelectorAll('[data-crump50-attachment-id]').length === 1);

  const restored = await page.evaluate(() => ({
    label: document.querySelector('.message-status')?.textContent || '',
    prompt: document.querySelector('#userInput')?.value || '',
    attachmentCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    attachmentName: document.querySelector('[data-crump50-attachment-id] strong')?.textContent || '',
    toast: document.querySelector('.toast__message')?.textContent || '',
  }));

  await page.locator('#sendButton').click();
  await page.waitForTimeout(80);
  const unchanged = await page.evaluate(() => ({
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    sendCalls: window.__fixture.sendCalls,
    lastToast: [...document.querySelectorAll('.toast__message')].at(-1)?.textContent || '',
  }));

  await page.locator('#userInput').fill('Create a gentle storybook portrait using this reference, with a blue garden background.');
  await page.locator('#sendButton').click();
  await page.waitForFunction(() => window.__fixture.sendCalls === 1);
  const revised = await page.evaluate(() => ({
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    sendCalls: window.__fixture.sendCalls,
    message: window.__fixture.sentBody?.message || '',
    fileRefs: window.__fixture.sentBody?.fileRefs || [],
  }));

  await page.screenshot({path: 'artifacts/image-safety-recovery.png', fullPage: true});
  await browser.close();

  const valid = (
    restored.label.includes('Tap to revise')
    && restored.prompt.includes('gentle storybook portrait')
    && restored.attachmentCount === 1
    && restored.attachmentName === 'reference.png'
    && restored.toast.includes('failed attempt was refunded')
    && unchanged.ensureUsageCalls === 0
    && unchanged.sendCalls === 0
    && unchanged.lastToast.includes('Change the wording or reference image')
    && revised.ensureUsageCalls === 1
    && revised.sendCalls === 1
    && revised.message.includes('blue garden background')
    && revised.fileRefs.length === 1
    && revised.fileRefs[0] === '11111111-1111-4111-8111-111111111111'
    && consoleErrors.length === 0
  );
  if (!valid) throw new Error(JSON.stringify({restored, unchanged, revised, consoleErrors}));
  process.stdout.write(`${JSON.stringify({restored, unchanged, revised, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
