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
  await page.evaluate(() => {
    let sequence = 0;
    const files = new Map();
    window.fetch = async (input, init = {}) => {
      const url = String(input || '');
      if (url === '/api/files/sign-upload') {
        const request = JSON.parse(String(init.body || '{}'));
        sequence += 1;
        const suffix = String(sequence).padStart(12, '0');
        const file = {
          id: `11111111-1111-4111-8111-${suffix}`,
          name: request.name || `reference-${sequence}.png`,
          type: request.type || 'image/png',
          size: Number(request.size || 68),
        };
        files.set(file.id, file);
        return new Response(JSON.stringify({file, uploadUrl: `/fixture-upload/${file.id}`}), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        });
      }
      const complete = url.match(/\/api\/files\/([^/]+)\/complete/);
      if (complete) {
        const file = files.get(decodeURIComponent(complete[1]));
        return new Response(JSON.stringify({file}), {status: 200, headers: {'Content-Type': 'application/json'}});
      }
      return new Response('{}', {status: 200, headers: {'Content-Type': 'application/json'}});
    };
  });
  await page.locator('#openImageStudio').click();
  const studio = page.getByRole('dialog', {name: 'Image Studio'});
  await studio.waitFor();
  const initialStudio = {
    modal: await studio.getAttribute('aria-modal'),
    closeFocused: await studio.getByRole('button', {name: 'Close Image Studio'}).evaluate(node => document.activeElement === node),
    addReferenceVisible: await studio.getByRole('button', {name: /Add images to guide the result/}).isVisible(),
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
  await (await fileChooser).setFiles([
    {name: 'fixture.png', mimeType: 'image/png', buffer: png},
    {name: 'approved-logo.png', mimeType: 'image/png', buffer: png},
  ]);
  await page.waitForFunction(() => {
    const dialog = document.querySelector('[role="dialog"][aria-label="Image Studio"]');
    const exact = [...(dialog?.querySelectorAll('button') || [])]
      .find(button => button.textContent.includes('Add exact logo or wordmark'));
    return dialog
      && dialog.querySelectorAll('[aria-label^="Role for reference"]').length === 2
      && dialog.textContent.includes('2 reference images ready')
      && exact
      && !exact.disabled;
  });
  const readyStudio = {
    referenceReadyVisible: await studio.getByRole('button', {name: /2 reference images ready/}).isVisible(),
    confirmPlanVisible: await studio.getByRole('button', {name: 'Confirm reference plan'}).isVisible(),
    referenceNamesVisible: (await studio.textContent()).includes('fixture.png')
      && (await studio.textContent()).includes('approved-logo.png'),
    roles: await studio.locator('[aria-label^="Role for reference"]').evaluateAll(nodes => nodes.map(node => node.value)),
    exactOverlayVisible: await studio.getByRole('button', {name: /Add exact logo or wordmark/}).isVisible(),
    exactOverlayEnabled: await studio.getByRole('button', {name: /Add exact logo or wordmark/}).isEnabled(),
    guidance: await studio.locator('.crump50-image-guidance').evaluateAll(nodes => nodes.map(node => node.textContent || '').join(' ')),
  };
  await studio.getByLabel('Role for reference 2').selectOption('logo');
  const invalidReplacementChooser = page.waitForEvent('filechooser');
  await studio.getByRole('button', {name: /2 reference images ready/}).click();
  await (await invalidReplacementChooser).setFiles({name: 'not-an-image.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image')});
  await page.waitForFunction(() => window.__lastToast?.tone === 'error');
  const invalidReplacement = await page.evaluate(() => ({
    toast: window.__lastToast,
    cardCount: document.querySelectorAll('[data-crump50-attachment-id]').length,
    studioOpen: Boolean(document.querySelector('[role="dialog"][aria-label="Image Studio"]')),
  }));
  await page.waitForTimeout(250);
  await page.screenshot({path: 'artifacts/visual-media-reference-entry.png', fullPage: true});
  const confirmedSummary = await studio.locator('.crump50-image-guidance').evaluateAll(nodes => nodes.map(node => node.textContent || '').join(' '));
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
    || !readyStudio.confirmPlanVisible
    || !readyStudio.referenceNamesVisible
    || JSON.stringify(readyStudio.roles) !== JSON.stringify(['base', 'subject'])
    || !readyStudio.exactOverlayVisible
    || !readyStudio.exactOverlayEnabled
    || !readyStudio.guidance.includes('Crump sends every confirmed reference as a numbered visual constraint')
    || !confirmedSummary.includes('Reference 1 → Starting canvas / composition')
    || !confirmedSummary.includes('Reference 2 → Logo / wordmark')
    || invalidReplacement.toast?.message !== 'Choose JPG, PNG, WebP, HEIC, or HEIF reference images.'
    || invalidReplacement.cardCount !== 2
    || !invalidReplacement.studioOpen
    || result.previewImagesAdded !== 2
    || result.previewImageCount !== 2
    || result.cardCount !== 2
    || !result.bodyHasContent
    || !result.imageModeVisible
    || result.editPlaceholder !== 'Describe the result. Crump will follow the confirmed reference plan…'
    || result.errorOverlay
  ) {
    throw new Error(JSON.stringify({initialStudio, reverseWrapFocus, forwardWrapFocus, directCloseFocus, transientCloseFocus, readyStudio, invalidReplacement, result, consoleErrors}));
  }
  process.stdout.write(`${JSON.stringify({initialStudio, reverseWrapFocus, forwardWrapFocus, directCloseFocus, transientCloseFocus, readyStudio, invalidReplacement, result, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
