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
    movePressed: await editor.getByRole('button', {name: 'Move', exact: true}).getAttribute('aria-pressed'),
    zoom: await editor.locator('.crump-precision-zoom b').textContent(),
    guidedBoundary: await editor.locator('.crump-precision-adjustment small').textContent(),
    localBoundary: await editor.locator('.crump-precision-local').textContent(),
    overflowX: await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
  };
  const canvas = editor.locator('.crump-precision-mask');
  const fittedWidth = await canvas.evaluate(node => node.getBoundingClientRect().width);
  await editor.getByRole('button', {name: 'Zoom in'}).click();
  const zoomed = {
    label: await editor.locator('.crump-precision-zoom b').textContent(),
    width: await canvas.evaluate(node => node.getBoundingClientRect().width),
  };
  await editor.getByRole('button', {name: 'Move', exact: true}).click();
  const movePressed = await editor.getByRole('button', {name: 'Move', exact: true}).getAttribute('aria-pressed');
  await editor.getByRole('button', {name: 'Warmer', exact: true}).click();
  const guidedInstruction = await editor.getByRole('textbox', {name: 'Edit instruction'}).inputValue();
  await editor.getByRole('button', {name: 'Brush'}).click();
  await page.screenshot({path: 'artifacts/precision-image-edit-desktop.png', fullPage: true});

  const box = await canvas.boundingBox();
  if (!box) throw new Error('Precision canvas was not visible.');
  await page.mouse.move(box.x + box.width * .42, box.y + box.height * .42);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .58, box.y + box.height * .56, {steps: 8});
  await page.mouse.up();
  await editor.getByRole('button', {name: 'Undo'}).click();
  const redoEnabled = await editor.getByRole('button', {name: 'Redo'}).isEnabled();
  await editor.getByRole('button', {name: 'Redo'}).click();
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => Boolean(window.__precisionStaged));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const staged = await page.evaluate(() => ({
    fileId: window.__precisionStaged?.file?.id,
    prefix: String(window.__precisionStaged?.maskDataUrl || '').slice(0, 22),
    width: window.__precisionStaged?.width,
    height: window.__precisionStaged?.height,
    instruction: window.__precisionStaged?.instruction,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    focused: document.activeElement?.id,
  }));

  await open.click();
  await editor.waitFor();
  const localCanvas = editor.locator('.crump-precision-mask');
  const localBox = await localCanvas.boundingBox();
  if (!localBox) throw new Error('Precision local-edit canvas was not visible.');
  await page.mouse.click(localBox.x + localBox.width * .5, localBox.y + localBox.height * .5);
  const warmth = editor.getByRole('slider', {name: 'Warmth adjustment'});
  await warmth.fill('18');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    if (!preview || preview.hidden) return false;
    return preview.getContext('2d').getImageData(320, 240, 1, 1).data[3] > 0;
  });
  const preview = {
    warmth: await warmth.inputValue(),
    visible: await editor.locator('.crump-precision-preview').isVisible(),
    saveEnabled: await editor.getByRole('button', {name: 'Save local edit'}).isEnabled(),
    pixels: await editor.evaluate(node => {
      const previewCanvas = node.querySelector('.crump-precision-preview');
      const maskCanvas = node.querySelector('.crump-precision-mask');
      const previewContext = previewCanvas.getContext('2d');
      const maskContext = maskCanvas.getContext('2d');
      return {
        outsideAlpha: previewContext.getImageData(5, 5, 1, 1).data[3],
        selectedAlpha: previewContext.getImageData(320, 240, 1, 1).data[3],
        maskSelectedAlpha: maskContext.getImageData(320, 240, 1, 1).data[3],
      };
    }),
  };
  await editor.getByRole('button', {name: 'Show original'}).click();
  const originalVisible = await editor.locator('.crump-precision-canvas-frame').evaluate(node => node.classList.contains('is-comparing-original'));
  await editor.getByRole('button', {name: 'Show edit'}).click();
  await editor.getByRole('button', {name: 'Save local edit'}).click();
  await page.waitForFunction(() => Boolean(window.__localSaveRequest && window.__openedLocalFile));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const localSave = await page.evaluate(() => ({
    url: window.__localSaveRequest?.url,
    prefix: String(window.__localSaveRequest?.body?.maskDataUrl || '').slice(0, 22),
    adjustments: window.__localSaveRequest?.body?.adjustments,
    chatId: window.__localSaveRequest?.body?.chatId,
    fileId: window.__openedLocalFile?.id,
    toast: window.__lastToast,
    focused: document.activeElement?.id,
  }));

  await page.evaluate(() => {
    window.__localSaveRequest = null;
    window.__openedLocalFile = null;
    window.__lastToast = null;
  });
  await open.click();
  await editor.waitFor();
  const overlayCanvas = editor.locator('.crump-precision-exact-canvas');
  const overlayInput = editor.getByLabel('Exact overlay image');
  await overlayInput.setInputFiles({
    name: 'approved-logo.png',
    mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl2cAAAAASUVORK5CYII=', 'base64'),
  });
  await page.waitForFunction(() => {
    const canvas = document.querySelector('.crump-precision-exact-canvas');
    return canvas && !canvas.hidden;
  });
  await editor.getByRole('textbox', {name: 'Exact overlay text'}).fill('BLUE BIRD');
  await editor.getByRole('button', {name: 'Add text'}).click();
  await editor.getByRole('slider', {name: 'Selected overlay size'}).fill('12');
  await editor.getByRole('slider', {name: 'Selected overlay opacity'}).fill('85');
  const overlayMask = editor.locator('.crump-precision-mask');
  const overlayBox = await overlayMask.boundingBox();
  if (!overlayBox) throw new Error('Exact-overlay canvas was not visible.');
  await page.mouse.move(overlayBox.x + overlayBox.width * .5, overlayBox.y + overlayBox.height * .82);
  await page.mouse.down();
  await page.mouse.move(overlayBox.x + overlayBox.width * .66, overlayBox.y + overlayBox.height * .28, {steps: 8});
  await page.mouse.up();
  const overlayPreview = {
    placePressed: await editor.getByRole('button', {name: 'Place'}).getAttribute('aria-pressed'),
    canvasVisible: await overlayCanvas.isVisible(),
    guideVisible: await editor.locator('.crump-precision-overlay-guide').isVisible(),
    saveEnabled: await editor.getByRole('button', {name: 'Save local edit'}).isEnabled(),
    localCopy: await editor.locator('.crump-precision-exact-overlay').textContent(),
    hasVisiblePixels: await overlayCanvas.evaluate(node => {
      const pixels = node.getContext('2d').getImageData(0, 0, node.width, node.height).data;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] > 0) return true;
      }
      return false;
    }),
  };
  await editor.getByRole('button', {name: 'Save local edit'}).click();
  await page.waitForFunction(() => Boolean(window.__localSaveRequest?.body?.overlayDataUrl && window.__openedLocalFile));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const overlaySave = await page.evaluate(() => ({
    mask: window.__localSaveRequest?.body?.maskDataUrl,
    overlayPrefix: String(window.__localSaveRequest?.body?.overlayDataUrl || '').slice(0, 22),
    overlayLength: String(window.__localSaveRequest?.body?.overlayDataUrl || '').length,
    adjustments: window.__localSaveRequest?.body?.adjustments,
    fileId: window.__openedLocalFile?.id,
    toast: window.__lastToast,
    focused: document.activeElement?.id,
  }));

  await page.setViewportSize({width: 390, height: 844});
  await open.click();
  await editor.waitFor();
  await page.waitForTimeout(250);
  const mobileWarmth = editor.getByRole('slider', {name: 'Warmth adjustment'});
  await mobileWarmth.scrollIntoViewIfNeeded();
  const mobile = {
    overflowX: await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    editorWidth: await editor.evaluate(node => Math.round(node.getBoundingClientRect().width)),
    viewportWidth: await page.evaluate(() => window.innerWidth),
    closeVisible: await editor.getByRole('button', {name: 'Close Precision Edit'}).isVisible(),
    localControlsVisible: await mobileWarmth.isVisible(),
    saveVisible: await editor.getByRole('button', {name: 'Save local edit'}).isVisible(),
    aiVisible: await editor.getByRole('button', {name: 'Continue with AI edit'}).isVisible(),
    workspaceScrollable: await editor.locator('.crump-precision-workspace').evaluate(node => node.scrollHeight > node.clientHeight),
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
    || desktop.movePressed !== 'false'
    || desktop.zoom !== '100%'
    || !desktop.guidedBoundary.includes('No person is identified or classified')
    || !desktop.localBoundary.includes('NO AI OR CREDITS')
    || !desktop.localBoundary.includes('deterministically')
    || zoomed.label !== '150%'
    || zoomed.width <= fittedWidth * 1.4
    || movePressed !== 'true'
    || !redoEnabled
    || !guidedInstruction.includes('subtly warmer')
    || desktop.overflowX
    || staged.fileId !== '11111111-1111-4111-8111-111111111111'
    || staged.prefix !== 'data:image/png;base64,'
    || staged.width !== 640
    || staged.height !== 480
    || !staged.instruction.includes('subtly warmer')
    || staged.modalOpen
    || staged.focused !== 'openPrecision'
    || preview.warmth !== '18'
    || !preview.visible
    || !preview.saveEnabled
    || preview.pixels.outsideAlpha !== 0
    || preview.pixels.selectedAlpha === 0
    || preview.pixels.maskSelectedAlpha !== 255
    || !originalVisible
    || !localSave.url.endsWith('/11111111-1111-4111-8111-111111111111/image-adjust')
    || localSave.prefix !== 'data:image/png;base64,'
    || localSave.adjustments?.warmth !== 18
    || localSave.adjustments?.exposure !== 0
    || localSave.adjustments?.saturation !== 0
    || localSave.chatId !== '22222222-2222-4222-8222-222222222222'
    || localSave.fileId !== '33333333-3333-4333-8333-333333333333'
    || !localSave.toast?.message?.includes('No AI provider or Crump Credits were used')
    || localSave.focused !== 'openPrecision'
    || overlayPreview.placePressed !== 'true'
    || !overlayPreview.canvasVisible
    || !overlayPreview.guideVisible
    || !overlayPreview.saveEnabled
    || !overlayPreview.localCopy.includes('NO AI OR CREDITS')
    || !overlayPreview.localCopy.includes('does not ask a model to redraw it')
    || !overlayPreview.hasVisiblePixels
    || overlaySave.mask !== ''
    || overlaySave.overlayPrefix !== 'data:image/png;base64,'
    || overlaySave.overlayLength <= 100
    || overlaySave.adjustments?.warmth !== 0
    || overlaySave.adjustments?.exposure !== 0
    || overlaySave.adjustments?.saturation !== 0
    || overlaySave.fileId !== '33333333-3333-4333-8333-333333333333'
    || !overlaySave.toast?.message?.includes('No AI provider or Crump Credits were used')
    || overlaySave.focused !== 'openPrecision'
    || mobile.overflowX
    || Math.abs(mobile.editorWidth - mobile.viewportWidth) > 4
    || !mobile.closeVisible
    || !mobile.localControlsVisible
    || !mobile.saveVisible
    || !mobile.aiVisible
    || !mobile.workspaceScrollable
    || !escaped
  ) {
    throw new Error(JSON.stringify({desktop, zoomed, fittedWidth, movePressed, redoEnabled, guidedInstruction, staged, preview, originalVisible, localSave, overlayPreview, overlaySave, mobile, escaped, errors}));
  }
  process.stdout.write(`${JSON.stringify({desktop, zoomed, fittedWidth, movePressed, redoEnabled, guidedInstruction, staged, preview, originalVisible, localSave, overlayPreview, overlaySave, mobile, escaped, errors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
