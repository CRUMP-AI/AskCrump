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
  await page.locator('#openImageStudio').click();
  const studio = page.getByRole('dialog', {name: 'Image Studio'});
  await studio.waitFor();
  const initialStudio = {
    modal: await studio.getAttribute('aria-modal'),
    closeFocused: await studio.getByRole('button', {name: 'Close Image Studio'}).evaluate(node => document.activeElement === node),
    addReferenceVisible: await studio.getByRole('button', {name: /Add images to guide the result/}).isVisible(),
    exactOverlayDisabled: await studio.getByRole('button', {name: /Add exact logo or wordmark/}).isDisabled(),
    createWithoutReferenceVisible: await studio.getByRole('button', {name: 'Create without reference'}).isVisible(),
    squarePressed: await studio.getByRole('button', {name: 'Square'}).getAttribute('aria-pressed'),
    guidance: await studio.locator('.crump50-image-guidance').textContent(),
    workspaceInert: await page.locator('#fixtureWorkspace').getAttribute('inert'),
    workspaceAriaHidden: await page.locator('#fixtureWorkspace').getAttribute('aria-hidden'),
  };
  await page.keyboard.press('Shift+Tab');
  const reverseWrapFocus = await page.evaluate(() => document.activeElement?.textContent?.trim() || '');
  await page.keyboard.press('Tab');
  const forwardWrapFocus = await page.evaluate(() => document.activeElement?.getAttribute('aria-label') || '');
  await studio.getByRole('button', {name: 'Close Image Studio'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'openImageStudio');
  const directCloseFocus = await page.evaluate(() => ({
    activeId: document.activeElement?.id || '',
    workspaceInert: document.getElementById('fixtureWorkspace')?.hasAttribute('inert') || false,
    workspaceAriaHidden: document.getElementById('fixtureWorkspace')?.getAttribute('aria-hidden'),
  }));

  await page.locator('#openImageStudioTransient').click();
  await studio.waitFor();
  await studio.getByRole('button', {name: 'Close Image Studio'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  const transientCloseFocus = await page.evaluate(() => ({
    activeId: document.activeElement?.id || '',
    transientHidden: document.getElementById('transientImageEntry')?.hidden || false,
    workspaceInert: document.getElementById('fixtureWorkspace')?.hasAttribute('inert') || false,
    workspaceAriaHidden: document.getElementById('fixtureWorkspace')?.getAttribute('aria-hidden'),
  }));

  await page.locator('#openImageStudio').click();
  await studio.waitFor();
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  const fileChooser = page.waitForEvent('filechooser');
  await studio.getByRole('button', {name: /Add images to guide the result/}).click();
  await (await fileChooser).setFiles({name: 'fixture.png', mimeType: 'image/png', buffer: png});
  await page.waitForFunction(() => document.querySelector('[data-crump50-upload-meta]')?.textContent.includes('B'));

  await studio.getByRole('button', {name: /1 reference image ready/}).waitFor();
  const readyStudio = {
    referenceReadyVisible: await studio.getByRole('button', {name: /1 reference image ready/}).isVisible(),
    confirmReferencePlanVisible: await studio.getByRole('button', {name: 'Confirm reference plan'}).isVisible(),
    referenceNameVisible: (await studio.textContent()).includes('Reference 1 · fixture.png'),
    referenceRole: await studio.locator('[aria-label="Role for reference 1"]').inputValue(),
    referenceSummaryVisible: (await studio.textContent()).includes('Reference 1 → Starting canvas / composition'),
    exactOverlayVisible: await studio.getByRole('button', {name: /Add exact logo or wordmark/}).isVisible(),
    exactOverlayEnabled: await studio.getByRole('button', {name: /Add exact logo or wordmark/}).isEnabled(),
  };
  const invalidReplacementChooser = page.waitForEvent('filechooser');
  await studio.getByRole('button', {name: /1 reference image ready/}).click();
  await (await invalidReplacementChooser).setFiles({name: 'not-an-image.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image')});
  await page.waitForFunction(() => window.__lastToast?.tone === 'error');
  const invalidReplacement = await page.evaluate(() => ({
    toast: window.__lastToast,
    cardCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    studioOpen: Boolean(document.querySelector('[role="dialog"][aria-label="Image Studio"]')),
  }));
  await page.waitForTimeout(250);
  await page.screenshot({path: 'artifacts/visual-media-reference-entry.png', fullPage: true});
  await page.evaluate(() => {
    window.CrumpPrecisionImageEditor = null;
    window.CrumpPrecisionImageEditLoader = null;
    window.__lastToast = null;
    window.__precisionOpen = null;
  });
  await studio.getByRole('button', {name: /Add exact logo or wordmark/}).click();
  await page.waitForFunction(() => window.__lastToast?.tone === 'error' && document.activeElement?.id === 'userInput');
  const exactOverlayUnavailable = await page.evaluate(() => ({
    toast: window.__lastToast,
    editorCalled: Boolean(window.__precisionOpen),
    imageModeVisible: document.getElementById('crump50ToolChipHost')?.textContent.includes('Create image') || false,
    attachmentCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    focused: document.activeElement?.id || '',
  }));
  await page.evaluate(() => {
    window.CrumpPrecisionImageEditor = window.__precisionEditorStub;
    window.__lastToast = null;
  });
  await page.locator('#openImageStudio').click();
  await studio.waitFor();
  await studio.getByRole('button', {name: /Add exact logo or wordmark/}).click();
  await page.waitForFunction(() => window.__precisionOpen?.entryMode === 'overlay');
  const exactOverlayHandoff = await page.evaluate(() => ({
    payload: window.__precisionOpen,
    studioOpen: Boolean(document.querySelector('[role="dialog"][aria-label="Image Studio"]')),
    workspaceInert: document.getElementById('fixtureWorkspace')?.hasAttribute('inert') || false,
    workspaceAriaHidden: document.getElementById('fixtureWorkspace')?.getAttribute('aria-hidden'),
  }));
  await page.locator('#openImageStudio').click();
  await studio.waitFor();
  await studio.getByRole('button', {name: 'Confirm reference plan'}).click();

  const result = await page.evaluate(() => ({
    previewImagesAdded: window.__previewImagesAdded,
    previewImageCount: document.querySelectorAll('.crump50-upload-visual img').length,
    cardCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    status: document.querySelector('[data-crump50-upload-meta]')?.textContent || '',
    bodyHasContent: document.body.innerText.trim().length > 0,
    imageModeVisible: document.getElementById('crump50ToolChipHost')?.textContent.includes('Create image') || false,
    editPlaceholder: document.getElementById('userInput')?.placeholder || '',
    errorOverlay: Boolean(document.querySelector('[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay')),
  }));
  await page.screenshot({path: 'artifacts/visual-media-preview-stability.png', fullPage: true});
  await browser.close();

  if (
    consoleErrors.length
    || initialStudio.modal !== 'true'
    || !initialStudio.closeFocused
    || !initialStudio.addReferenceVisible
    || !initialStudio.exactOverlayDisabled
    || !initialStudio.createWithoutReferenceVisible
    || initialStudio.squarePressed !== 'true'
    || !initialStudio.guidance.includes('does not infer race or ethnicity')
    || initialStudio.workspaceInert !== ''
    || initialStudio.workspaceAriaHidden !== 'true'
    || reverseWrapFocus !== 'Create without reference'
    || forwardWrapFocus !== 'Close Image Studio'
    || directCloseFocus.activeId !== 'openImageStudio'
    || directCloseFocus.workspaceInert
    || directCloseFocus.workspaceAriaHidden !== null
    || transientCloseFocus.activeId !== 'userInput'
    || !transientCloseFocus.transientHidden
    || transientCloseFocus.workspaceInert
    || transientCloseFocus.workspaceAriaHidden !== null
    || !readyStudio.referenceReadyVisible
    || !readyStudio.confirmReferencePlanVisible
    || !readyStudio.referenceNameVisible
    || readyStudio.referenceRole !== 'base'
    || !readyStudio.referenceSummaryVisible
    || !readyStudio.exactOverlayVisible
    || !readyStudio.exactOverlayEnabled
    || invalidReplacement.toast?.message !== 'Choose JPG, PNG, WebP, HEIC, or HEIF reference images.'
    || invalidReplacement.cardCount !== 1
    || !invalidReplacement.studioOpen
    || exactOverlayUnavailable.toast?.message !== 'Exact Overlay is unavailable right now. No AI request was started and your image is unchanged.'
    || exactOverlayUnavailable.editorCalled
    || !exactOverlayUnavailable.imageModeVisible
    || exactOverlayUnavailable.attachmentCount !== 1
    || exactOverlayUnavailable.focused !== 'userInput'
    || exactOverlayHandoff.payload?.fileId !== '11111111-1111-4111-8111-111111111111'
    || exactOverlayHandoff.payload?.entryMode !== 'overlay'
    || exactOverlayHandoff.payload?.returnFocusId !== 'userInput'
    || exactOverlayHandoff.studioOpen
    || exactOverlayHandoff.workspaceInert
    || exactOverlayHandoff.workspaceAriaHidden !== null
    || result.previewImagesAdded !== 1
    || result.previewImageCount !== 1
    || result.cardCount !== 1
    || !result.bodyHasContent
    || !result.imageModeVisible
    || result.editPlaceholder !== 'Describe the result. Crump will follow the confirmed reference plan…'
    || result.errorOverlay
  ) {
    throw new Error(JSON.stringify({initialStudio, reverseWrapFocus, forwardWrapFocus, directCloseFocus, transientCloseFocus, readyStudio, invalidReplacement, exactOverlayUnavailable, exactOverlayHandoff, result, consoleErrors}));
  }
  process.stdout.write(`${JSON.stringify({initialStudio, reverseWrapFocus, forwardWrapFocus, directCloseFocus, transientCloseFocus, readyStudio, invalidReplacement, exactOverlayUnavailable, exactOverlayHandoff, result, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
