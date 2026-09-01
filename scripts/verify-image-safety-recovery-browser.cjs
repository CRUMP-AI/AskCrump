const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const consoleErrors = [];
  const mobilePage = async path => {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => consoleErrors.push(error.message));
    await page.goto(`http://127.0.0.1:8765${path}`, {waitUntil: 'networkidle'});
    await page.waitForFunction(() => document.documentElement.dataset.crump50Booted === 'true');
    await page.evaluate(() => {
      document.querySelector('#fileInput')?.addEventListener('click', () => { window.__fixture.fileInputClicks += 1; });
    });
    return page;
  };

  const page = await mobilePage('/tests/fixtures/image-safety-recovery.html');
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

  const replacementPage = await mobilePage('/tests/fixtures/image-safety-recovery.html?scenario=invalid-reference');
  await replacementPage.locator('.message-status').click();
  await replacementPage.waitForTimeout(120);
  const replacementRestored = await replacementPage.evaluate(() => ({
    label: document.querySelector('.message-status')?.textContent || '',
    prompt: document.querySelector('#userInput')?.value || '',
    attachmentCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    fileInputClicks: window.__fixture.fileInputClicks,
    toast: document.querySelector('.toast__message')?.textContent || '',
  }));
  await replacementPage.locator('#sendButton').click();
  await replacementPage.waitForTimeout(80);
  const replacementBlocked = await replacementPage.evaluate(() => ({
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    sendCalls: window.__fixture.sendCalls,
    lastToast: [...document.querySelectorAll('.toast__message')].at(-1)?.textContent || '',
  }));
  await replacementPage.screenshot({path: 'artifacts/image-reference-replacement.png', fullPage: true});

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
    && replacementRestored.label.includes('Tap to replace')
    && replacementRestored.prompt.includes('gentle storybook portrait')
    && replacementRestored.attachmentCount === 0
    && replacementRestored.fileInputClicks === 1
    && replacementRestored.toast.includes('Choose a different JPG, PNG, or WebP')
    && replacementBlocked.ensureUsageCalls === 0
    && replacementBlocked.sendCalls === 0
    && replacementBlocked.lastToast.includes('Add a different JPG, PNG, or WebP')
    && consoleErrors.length === 0
  );
  await browser.close();
  if (!valid) throw new Error(JSON.stringify({restored, unchanged, revised, replacementRestored, replacementBlocked, consoleErrors}));
  process.stdout.write(`${JSON.stringify({restored, unchanged, revised, replacementRestored, replacementBlocked, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
