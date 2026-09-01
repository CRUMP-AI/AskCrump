const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 1100, height: 780}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/precision-image-edit.html', {waitUntil: 'networkidle'});

  const open = page.getByRole('button', {name: 'Open Precision Edit'});
  await open.click();
  const editor = page.getByRole('dialog', {name: /Choose exactly what may change/});
  await editor.waitFor();
  const desktop = {
    ariaModal: await editor.getAttribute('aria-modal'),
    heading: await editor.getByRole('heading').textContent(),
    boundary: await editor.locator('.crump-precision-boundary').textContent(),
    appearance: await editor.locator('.crump-precision-appearance').textContent(),
    brushPressed: await editor.getByRole('button', {name: 'Brush'}).getAttribute('aria-pressed'),
    overflowX: await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
  };
  await page.screenshot({path: 'artifacts/precision-image-edit-desktop.png', fullPage: true});

  const canvas = editor.locator('canvas');
  const box = await canvas.boundingBox();
  if (!box) throw new Error('Precision canvas was not visible.');
  await page.mouse.move(box.x + box.width * .42, box.y + box.height * .42);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .58, box.y + box.height * .56, {steps: 8});
  await page.mouse.up();
  await editor.getByRole('button', {name: 'Undo'}).click();
  await page.mouse.click(box.x + box.width * .5, box.y + box.height * .5);
  await editor.getByRole('button', {name: 'Use this selection'}).click();
  await page.waitForFunction(() => Boolean(window.__precisionStaged));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const staged = await page.evaluate(() => ({
    fileId: window.__precisionStaged?.file?.id,
    prefix: String(window.__precisionStaged?.maskDataUrl || '').slice(0, 22),
    width: window.__precisionStaged?.width,
    height: window.__precisionStaged?.height,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    focused: document.activeElement?.id,
  }));

  await page.setViewportSize({width: 390, height: 844});
  await open.click();
  await editor.waitFor();
  await page.waitForTimeout(250);
  const mobile = {
    overflowX: await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    editorWidth: await editor.evaluate(node => Math.round(node.getBoundingClientRect().width)),
    viewportWidth: await page.evaluate(() => window.innerWidth),
    closeVisible: await editor.getByRole('button', {name: 'Close Precision Edit'}).isVisible(),
  };
  await page.screenshot({path: 'artifacts/precision-image-edit-mobile.png', fullPage: true});
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const escaped = await page.evaluate(() => !document.querySelector('.crump-precision-editor'));
  await browser.close();

  if (
    errors.length
    || desktop.ariaModal !== 'true'
    || desktop.heading !== 'Choose exactly what may change.'
    || !desktop.boundary.includes('restores protected pixels')
    || !desktop.appearance.includes('Skin tone is not a race label')
    || desktop.brushPressed !== 'true'
    || desktop.overflowX
    || staged.fileId !== '11111111-1111-4111-8111-111111111111'
    || staged.prefix !== 'data:image/png;base64,'
    || staged.width !== 640
    || staged.height !== 480
    || staged.modalOpen
    || staged.focused !== 'openPrecision'
    || mobile.overflowX
    || Math.abs(mobile.editorWidth - mobile.viewportWidth) > 4
    || !mobile.closeVisible
    || !escaped
  ) {
    throw new Error(JSON.stringify({desktop, staged, mobile, escaped, errors}));
  }
  process.stdout.write(`${JSON.stringify({desktop, staged, mobile, escaped, errors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
