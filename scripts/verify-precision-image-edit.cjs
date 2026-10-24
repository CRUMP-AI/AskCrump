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
  const resetAiFixtureState = async ({
    failLocalSave = false,
    holdLocalSave = false,
    ignoreLocalSaveAbort = false,
    localSaveSize = '',
  } = {}) => {
    await page.evaluate(({shouldFail, holdSave, ignoreAbort, savedSize}) => {
      window.__releaseLocalSave?.();
      window.__precisionStaged = null;
      window.__localSaveRequest = null;
      window.__localSaveRequests = [];
      window.__localSaveFailure = shouldFail;
      window.__localSaveMetadataSize = savedSize;
      window.__holdLocalSave = holdSave;
      window.__ignoreLocalSaveAbort = ignoreAbort;
      window.__releaseLocalSave = null;
      window.__localSaveAborts = 0;
      window.__localSaveIgnoredAborts = 0;
      window.__localSaveResponses = 0;
      window.__appliedLocalFile = null;
      window.__localAppliedEvents = 0;
      window.__precisionStageCalls = 0;
      window.__lastToast = null;
      window.currentChatId = '22222222-2222-4222-8222-222222222222';
    }, {
      shouldFail: failLocalSave,
      holdSave: holdLocalSave,
      ignoreAbort: ignoreLocalSaveAbort,
      savedSize: localSaveSize,
    });
  };
  const paintSelection = async dialog => {
    const clear = dialog.getByRole('button', {name: 'Clear'});
    if (await clear.isEnabled()) await clear.click();
    await dialog.getByRole('button', {name: 'Brush'}).click();
    const mask = dialog.locator('.crump-precision-mask');
    const bounds = await mask.boundingBox();
    if (!bounds) throw new Error('Precision selection canvas was not visible.');
    await page.mouse.move(bounds.x + bounds.width * .4, bounds.y + bounds.height * .4);
    await page.mouse.down();
    await page.mouse.move(bounds.x + bounds.width * .6, bounds.y + bounds.height * .6, {steps: 8});
    await page.mouse.up();
    return mask;
  };
  const addExactOverlay = async dialog => {
    const overlayInput = dialog.getByLabel('Exact overlay image');
    const pending = await overlayInput.evaluate((input, encoded) => {
      const bytes = Uint8Array.from(atob(encoded), value => value.charCodeAt(0));
      const transfer = new DataTransfer();
      transfer.items.add(new File([bytes], 'approved-logo.png', {type: 'image/png'}));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles: true}));
      const editorNode = input.closest('.crump-precision-editor');
      return {
        useDisabled: editorNode.querySelector('.crump-precision-use')?.disabled,
        saveDisabled: editorNode.querySelector('.crump-precision-save-local')?.disabled,
        addDisabled: editorNode.querySelector('.crump-precision-overlay-actions button')?.disabled,
      };
    }, 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl2cAAAAASUVORK5CYII=');
    await page.waitForFunction(() => {
      const editorNode = document.querySelector('.crump-precision-editor');
      const overlay = editorNode?.querySelector('.crump-precision-exact-canvas');
      const add = editorNode?.querySelector('.crump-precision-overlay-actions button');
      const save = editorNode?.querySelector('.crump-precision-save-local');
      const use = editorNode?.querySelector('.crump-precision-use');
      return overlay && !overlay.hidden && add && !add.disabled && save && !save.disabled && use && !use.disabled;
    });
    return {
      ...pending,
      useEnabledAfter: await dialog.getByRole('button', {name: 'Continue with AI edit'}).isEnabled(),
      saveEnabledAfter: await dialog.getByRole('button', {name: 'Apply changes'}).isEnabled(),
    };
  };
  const dataUrlProof = async kind => page.evaluate(async proofKind => {
    const request = window.__localSaveRequests?.[0]?.body || {};
    const dataUrl = proofKind === 'requestMask'
      ? request.maskDataUrl
      : proofKind === 'requestOverlay'
        ? request.overlayDataUrl
        : window.__precisionStaged?.maskDataUrl;
    const image = new Image();
    image.src = String(dataUrl || '');
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d', {alpha: true});
    context.drawImage(image, 0, 0);
    const center = context.getImageData(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1).data[3];
    const corner = context.getImageData(0, 0, 1, 1).data[3];
    let nonzeroAlpha = false;
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const stride = Math.max(4, Math.floor((canvas.width * canvas.height) / 50_000) * 4);
    for (let index = 3; index < pixels.length; index += stride) {
      if (pixels[index] > 0) {
        nonzeroAlpha = true;
        break;
      }
    }
    return {width: canvas.width, height: canvas.height, center, corner, nonzeroAlpha};
  }, kind);
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
  // The dialog scales during entry. Compare one settled layout snapshot so
  // separate browser calls cannot mistake animation progress for misalignment.
  await editor.evaluate(async node => {
    await Promise.all(node.getAnimations().map(animation => animation.finished));
  });
  const visibleImage = await editor.evaluate(node => {
    const image = node.querySelector('.crump-precision-canvas-frame img');
    const mask = node.querySelector('.crump-precision-mask');
    const imageRect = image.getBoundingClientRect();
    const maskRect = mask.getBoundingClientRect();
    return {
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
      width: imageRect.width,
      height: imageRect.height,
      canvasWidth: maskRect.width,
      canvasHeight: maskRect.height,
    };
  });
  await page.waitForFunction(() => Boolean(window.__versionRequest));
  const versions = {
    count: await editor.locator('.crump-precision-version').count(),
    copy: await editor.locator('.crump-precision-versions').textContent(),
    current: await editor.locator('.crump-precision-version[aria-current="true"]').count(),
  };
  await editor.getByRole('button', {name: 'Rotate image right 90 degrees'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-mask')?.width === 480);
  const resetFrameEnabled = await editor.getByRole('button', {name: 'Reset frame'}).isEnabled();
  await editor.getByRole('button', {name: 'Reset frame'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-mask')?.width === 640);
  await editor.getByRole('button', {name: 'Rotate image right 90 degrees'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-mask')?.width === 480);
  await editor.getByRole('button', {name: '4:5', exact: true}).click();
  const cropGuideVisible = await editor.locator('.crump-precision-crop-guide').isVisible();
  await editor.getByRole('button', {name: 'Apply crop'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-mask')?.width < 480);
  const transformedSize = await canvas.evaluate(node => ({width: node.width, height: node.height}));
  await editor.getByRole('button', {name: 'Apply changes'}).click();
  await page.waitForFunction(() => Boolean(window.__localSaveRequest && window.__appliedLocalFile));
  const geometrySave = await page.evaluate(() => ({
    operations: window.__localSaveRequest?.body?.transform?.operations,
    mask: window.__localSaveRequest?.body?.maskDataUrl,
    overlay: window.__localSaveRequest?.body?.overlayDataUrl,
    requestFileId: window.__localSaveRequest?.savedFileId,
    fileId: window.__appliedLocalFile?.id,
    sourceFileId: window.__appliedLocalFile?.metadata?.sourceFileId,
  }));
  await page.evaluate(() => {
    window.__localSaveRequest = null;
    window.__appliedLocalFile = null;
    window.__lastToast = null;
  });
  await open.click();
  await editor.waitFor();
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
  await editor.getByRole('button', {name: 'Fit image to screen'}).click();
  await editor.getByRole('button', {name: 'Lasso', exact: true}).click();
  const lassoCanvas = editor.locator('.crump-precision-mask');
  const lassoBox = await lassoCanvas.boundingBox();
  if (!lassoBox) throw new Error('Precision lasso canvas was not visible.');
  await page.mouse.move(lassoBox.x + lassoBox.width * .25, lassoBox.y + lassoBox.height * .25);
  await page.mouse.down();
  await page.mouse.move(lassoBox.x + lassoBox.width * .75, lassoBox.y + lassoBox.height * .25, {steps: 5});
  await page.mouse.move(lassoBox.x + lassoBox.width * .75, lassoBox.y + lassoBox.height * .75, {steps: 5});
  await page.mouse.move(lassoBox.x + lassoBox.width * .25, lassoBox.y + lassoBox.height * .75, {steps: 5});
  const lassoGuideVisible = await editor.locator('.crump-precision-lasso-guide').isVisible();
  await page.mouse.move(lassoBox.x + lassoBox.width * .25, lassoBox.y + lassoBox.height * .25, {steps: 5});
  await page.mouse.up();
  const lassoSelected = await lassoCanvas.evaluate(node => {
    const context = node.getContext('2d');
    return {
      center: context.getImageData(320, 240, 1, 1).data[3],
      corner: context.getImageData(10, 10, 1, 1).data[3],
    };
  });
  await editor.getByRole('button', {name: 'Invert', exact: true}).click();
  const lassoInverted = await lassoCanvas.evaluate(node => {
    const context = node.getContext('2d');
    return {
      center: context.getImageData(320, 240, 1, 1).data[3],
      corner: context.getImageData(10, 10, 1, 1).data[3],
    };
  });
  await editor.getByRole('button', {name: 'Undo'}).click();
  const lassoUndo = await lassoCanvas.evaluate(node => {
    const context = node.getContext('2d');
    return {
      center: context.getImageData(320, 240, 1, 1).data[3],
      corner: context.getImageData(10, 10, 1, 1).data[3],
    };
  });
  await editor.getByRole('button', {name: 'Redo'}).click();
  const lassoRedo = await lassoCanvas.evaluate(node => {
    const context = node.getContext('2d');
    return {
      center: context.getImageData(320, 240, 1, 1).data[3],
      corner: context.getImageData(10, 10, 1, 1).data[3],
    };
  });
  const lassoProof = {
    pressed: await editor.getByRole('button', {name: 'Lasso', exact: true}).getAttribute('aria-pressed'),
    guideVisible: lassoGuideVisible,
    selected: lassoSelected,
    inverted: lassoInverted,
    undo: lassoUndo,
    redo: lassoRedo,
  };
  await editor.getByRole('button', {name: 'Clear'}).click();
  await editor.getByRole('button', {name: 'Brush'}).click();
  await page.mouse.click(lassoBox.x + lassoBox.width * .5, lassoBox.y + lassoBox.height * .5);
  await editor.getByRole('button', {name: 'Invert', exact: true}).click();
  const broadInvertGuard = {
    status: await editor.locator('.crump-precision-status').textContent(),
    pixels: await lassoCanvas.evaluate(node => {
      const context = node.getContext('2d');
      return {
        center: context.getImageData(320, 240, 1, 1).data[3],
        corner: context.getImageData(10, 10, 1, 1).data[3],
      };
    }),
  };
  await editor.getByRole('button', {name: 'Clear'}).click();
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
  await editor.getByRole('slider', {name: 'Selection edge feather'}).fill('1');
  const feather = await editor.getByRole('slider', {name: 'Selection edge feather'}).inputValue();
  await resetAiFixtureState();
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => Boolean(window.__precisionStaged));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const staged = await page.evaluate(() => ({
    fileId: window.__precisionStaged?.file?.id,
    prefix: String(window.__precisionStaged?.maskDataUrl || '').slice(0, 22),
    width: window.__precisionStaged?.width,
    height: window.__precisionStaged?.height,
    instruction: window.__precisionStaged?.instruction,
    localSaveCount: window.__localSaveRequests?.length || 0,
    stageCalls: window.__precisionStageCalls,
    appliedLocalFile: window.__appliedLocalFile,
    appliedEventCount: window.__localAppliedEvents,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    focused: document.activeElement?.id,
  }));
  staged.maskProof = await dataUrlProof('stagedMask');

  await resetAiFixtureState({holdLocalSave: true});
  await open.click();
  await editor.waitFor();
  await paintSelection(editor);
  const aiWarmth = editor.getByRole('slider', {name: 'Warmth adjustment'});
  await aiWarmth.fill('12');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => window.__localSaveRequests?.length === 1);
  const adjustmentLock = await page.evaluate(() => {
    const modal = document.querySelector('.crump-precision-editor');
    return {
      modalBusy: modal?.getAttribute('aria-busy'),
      useEnabled: !modal?.querySelector('.crump-precision-use')?.disabled,
      saveEnabled: !modal?.querySelector('.crump-precision-save-local')?.disabled,
      warmthEnabled: !modal?.querySelector('[aria-label="Warmth adjustment"]')?.disabled,
      closeEnabled: !modal?.querySelector('.crump-precision-close')?.disabled,
      cancelEnabled: !modal?.querySelector('.crump-precision-cancel')?.disabled,
      stagedBeforeRelease: window.__precisionStaged,
      stageCallsBeforeRelease: window.__precisionStageCalls,
    };
  });
  await page.evaluate(() => window.__releaseLocalSave?.());
  await page.waitForFunction(() => Boolean(window.__precisionStaged && window.__localSaveRequests?.length === 1));
  const adjustmentAi = await page.evaluate(() => ({
    saveCount: window.__localSaveRequests?.length || 0,
    request: window.__localSaveRequests?.[0] || null,
    stagedFileId: window.__precisionStaged?.file?.id,
    stagedWidth: window.__precisionStaged?.width,
    stagedHeight: window.__precisionStaged?.height,
    stagedMaskPrefix: String(window.__precisionStaged?.maskDataUrl || '').slice(0, 22),
    maskMatchesPersisted: window.__precisionStaged?.maskDataUrl === window.__localSaveRequests?.[0]?.body?.maskDataUrl,
    savedMetadata: window.__precisionStaged?.file?.metadata,
    stageCalls: window.__precisionStageCalls,
    appliedLocalFile: window.__appliedLocalFile,
    appliedEventCount: window.__localAppliedEvents,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
  }));
  adjustmentAi.lock = adjustmentLock;
  adjustmentAi.maskProof = await dataUrlProof('stagedMask');

  await resetAiFixtureState();
  await open.click();
  await editor.waitFor();
  await paintSelection(editor);
  await editor.getByRole('textbox', {name: 'Exact overlay text'}).fill('APPROVED');
  await editor.getByRole('button', {name: 'Add text'}).click();
  await page.waitForFunction(() => !document.querySelector('.crump-precision-save-local')?.disabled);
  const overlayPending = await addExactOverlay(editor);
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => Boolean(window.__precisionStaged && window.__localSaveRequests?.length === 1));
  const overlayAi = await page.evaluate(() => ({
    saveCount: window.__localSaveRequests?.length || 0,
    request: window.__localSaveRequests?.[0] || null,
    stagedFileId: window.__precisionStaged?.file?.id,
    stagedWidth: window.__precisionStaged?.width,
    stagedHeight: window.__precisionStaged?.height,
    stagedMaskPrefix: String(window.__precisionStaged?.maskDataUrl || '').slice(0, 22),
    savedMetadata: window.__precisionStaged?.file?.metadata,
    stageCalls: window.__precisionStageCalls,
    appliedLocalFile: window.__appliedLocalFile,
    appliedEventCount: window.__localAppliedEvents,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
  }));
  overlayAi.pendingImport = overlayPending;
  overlayAi.maskProof = await dataUrlProof('stagedMask');
  overlayAi.overlayProof = await dataUrlProof('requestOverlay');

  await resetAiFixtureState();
  await open.click();
  await editor.waitFor();
  await editor.getByRole('button', {name: 'Rotate image right 90 degrees'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-mask')?.width === 480);
  await paintSelection(editor);
  await editor.getByRole('slider', {name: 'Exposure adjustment'}).fill('9');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await addExactOverlay(editor);
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => Boolean(window.__precisionStaged && window.__localSaveRequests?.length === 1));
  const combinedAi = await page.evaluate(() => ({
      saveCount: window.__localSaveRequests?.length || 0,
      request: window.__localSaveRequests?.[0] || null,
      stagedFileId: window.__precisionStaged?.file?.id,
      stagedWidth: window.__precisionStaged?.width,
      stagedHeight: window.__precisionStaged?.height,
      stagedMaskPrefix: String(window.__precisionStaged?.maskDataUrl || '').slice(0, 22),
      maskMatchesPersisted: window.__precisionStaged?.maskDataUrl === window.__localSaveRequests?.[0]?.body?.maskDataUrl,
      savedMetadata: window.__precisionStaged?.file?.metadata,
      stageCalls: window.__precisionStageCalls,
      appliedLocalFile: window.__appliedLocalFile,
      appliedEventCount: window.__localAppliedEvents,
      modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
  }));
  combinedAi.maskProof = await dataUrlProof('stagedMask');
  combinedAi.overlayProof = await dataUrlProof('requestOverlay');

  await resetAiFixtureState({failLocalSave: true});
  await open.click();
  await editor.waitFor();
  await editor.getByRole('button', {name: 'Rotate image right 90 degrees'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-mask')?.width === 480);
  const failedMask = await paintSelection(editor);
  await editor.getByRole('slider', {name: 'Saturation adjustment'}).fill('11');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await addExactOverlay(editor);
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-status')?.textContent?.includes('Fixture local save failed.'));
  const failedAi = {
    ...(await page.evaluate(() => ({
      saveCount: window.__localSaveRequests?.length || 0,
      request: window.__localSaveRequests?.[0] || null,
      staged: window.__precisionStaged,
      stageCalls: window.__precisionStageCalls,
      appliedLocalFile: window.__appliedLocalFile,
      appliedEventCount: window.__localAppliedEvents,
      modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
      modalBusy: document.querySelector('.crump-precision-editor')?.getAttribute('aria-busy'),
    }))),
    saturation: await editor.getByRole('slider', {name: 'Saturation adjustment'}).inputValue(),
    overlayPixels: await editor.locator('.crump-precision-exact-canvas').evaluate(node => {
      const pixels = node.getContext('2d').getImageData(0, 0, node.width, node.height).data;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] > 0) return true;
      }
      return false;
    }),
    dimensions: await failedMask.evaluate(node => ({width: node.width, height: node.height})),
    selectedAlpha: await failedMask.evaluate(node => {
      const context = node.getContext('2d');
      return context.getImageData(Math.floor(node.width / 2), Math.floor(node.height / 2), 1, 1).data[3];
    }),
    resetFrameEnabled: await editor.getByRole('button', {name: 'Reset frame'}).isEnabled(),
    saveEnabled: await editor.getByRole('button', {name: 'Apply changes'}).isEnabled(),
    useEnabled: await editor.getByRole('button', {name: 'Continue with AI edit'}).isEnabled(),
    useBusy: await editor.getByRole('button', {name: 'Continue with AI edit'}).getAttribute('aria-busy'),
  };
  await editor.getByRole('button', {name: 'Close Precision Edit'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  await resetAiFixtureState();

  await resetAiFixtureState({localSaveSize: '639x480'});
  await open.click();
  await editor.waitFor();
  await paintSelection(editor);
  await editor.getByRole('slider', {name: 'Warmth adjustment'}).fill('5');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-status')?.textContent?.includes('dimensions did not match'));
  const dimensionMismatch = await page.evaluate(() => ({
    saveCount: window.__localSaveRequests?.length || 0,
    staged: window.__precisionStaged,
    stageCalls: window.__precisionStageCalls,
    appliedLocalFile: window.__appliedLocalFile,
    appliedEventCount: window.__localAppliedEvents,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    modalBusy: document.querySelector('.crump-precision-editor')?.getAttribute('aria-busy'),
    useBusy: document.querySelector('.crump-precision-use')?.getAttribute('aria-busy'),
    useEnabled: !document.querySelector('.crump-precision-use')?.disabled,
  }));
  await editor.getByRole('button', {name: 'Close Precision Edit'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  await resetAiFixtureState({holdLocalSave: true});
  await open.click();
  await editor.waitFor();
  await paintSelection(editor);
  await editor.getByRole('slider', {name: 'Warmth adjustment'}).fill('7');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => window.__localSaveRequests?.length === 1);
  await page.evaluate(() => {
    window.currentChatId = '44444444-4444-4444-8444-444444444444';
    window.__releaseLocalSave?.();
  });
  await page.waitForFunction(() => document.querySelector('.crump-precision-status')?.textContent?.includes('conversation changed'));
  const conversationRace = await page.evaluate(() => ({
    saveCount: window.__localSaveRequests?.length || 0,
    requestChatId: window.__localSaveRequests?.[0]?.body?.chatId,
    staged: window.__precisionStaged,
    stageCalls: window.__precisionStageCalls,
    appliedLocalFile: window.__appliedLocalFile,
    appliedEventCount: window.__localAppliedEvents,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    modalBusy: document.querySelector('.crump-precision-editor')?.getAttribute('aria-busy'),
    useEnabled: !document.querySelector('.crump-precision-use')?.disabled,
  }));
  await editor.getByRole('button', {name: 'Cancel'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');

  await resetAiFixtureState({holdLocalSave: true, ignoreLocalSaveAbort: true});
  await open.click();
  await editor.waitFor();
  await paintSelection(editor);
  await editor.getByRole('slider', {name: 'Warmth adjustment'}).fill('7');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => window.__localSaveRequests?.length === 1);
  const cancelWasEnabled = await editor.getByRole('button', {name: 'Cancel'}).isEnabled();
  const cancellationFocus = await page.evaluate(() => document.activeElement?.className || '');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('.crump-precision-editor'));
  await page.evaluate(() => window.__releaseLocalSave?.());
  await page.waitForFunction(() => window.__localSaveResponses === 1);
  const cancelledLateSuccess = await page.evaluate(enabled => ({
    cancelWasEnabled: enabled,
    saveCount: window.__localSaveRequests?.length || 0,
    saveAborts: window.__localSaveAborts,
    ignoredAborts: window.__localSaveIgnoredAborts,
    responses: window.__localSaveResponses,
    staged: window.__precisionStaged,
    stageCalls: window.__precisionStageCalls,
    appliedLocalFile: window.__appliedLocalFile,
    appliedEventCount: window.__localAppliedEvents,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    bodyOpen: document.body.classList.contains('crump-precision-open'),
  }), cancelWasEnabled);
  cancelledLateSuccess.cancellationFocus = cancellationFocus;
  await resetAiFixtureState();

  await open.click();
  await editor.waitFor();
  await paintSelection(editor);
  await editor.getByRole('slider', {name: 'Exposure adjustment'}).fill('6');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    return Boolean(preview && !preview.hidden);
  });
  await page.evaluate(() => {
    window.__fixtureImageStudio = window.CrumpImageStudio;
    window.CrumpImageStudio = null;
  });
  await editor.getByRole('button', {name: 'Continue with AI edit'}).click();
  await page.waitForFunction(() => document.querySelector('.crump-precision-status')?.textContent?.includes('AI edit workspace is unavailable'));
  const unavailableWorkspace = await page.evaluate(() => ({
    saveCount: window.__localSaveRequests?.length || 0,
    staged: window.__precisionStaged,
    stageCalls: window.__precisionStageCalls,
    modalOpen: Boolean(document.querySelector('.crump-precision-editor')),
    modalBusy: document.querySelector('.crump-precision-editor')?.getAttribute('aria-busy'),
    useBusy: document.querySelector('.crump-precision-use')?.getAttribute('aria-busy'),
    useEnabled: !document.querySelector('.crump-precision-use')?.disabled,
  }));
  await page.evaluate(() => { window.CrumpImageStudio = window.__fixtureImageStudio; });
  await editor.getByRole('button', {name: 'Close Precision Edit'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  await resetAiFixtureState();

  await open.click();
  await editor.waitFor();
  const warmth = editor.getByRole('slider', {name: 'Warmth adjustment'});
  const exposure = editor.getByRole('slider', {name: 'Exposure adjustment'});
  const saturation = editor.getByRole('slider', {name: 'Saturation adjustment'});
  const previewPixel = () => editor.locator('.crump-precision-preview').evaluate(node => {
    const context = node.getContext('2d');
    return [...context.getImageData(Math.floor(node.width / 2), Math.floor(node.height / 2), 1, 1).data];
  });
  await warmth.fill('18');
  await page.waitForFunction(() => {
    const preview = document.querySelector('.crump-precision-preview');
    if (!preview || preview.hidden) return false;
    const x = Math.floor(preview.width / 2);
    const y = Math.floor(preview.height / 2);
    return preview.getContext('2d').getImageData(x, y, 1, 1).data[3] > 0;
  });
  const warmthPixels = await previewPixel();
  await exposure.fill('16');
  await page.waitForFunction(previous => {
    const preview = document.querySelector('.crump-precision-preview');
    const current = [...preview.getContext('2d').getImageData(Math.floor(preview.width / 2), Math.floor(preview.height / 2), 1, 1).data];
    return current.some((value, index) => value !== previous[index]);
  }, warmthPixels);
  const exposurePixels = await previewPixel();
  await saturation.fill('-14');
  await page.waitForFunction(previous => {
    const preview = document.querySelector('.crump-precision-preview');
    const current = [...preview.getContext('2d').getImageData(Math.floor(preview.width / 2), Math.floor(preview.height / 2), 1, 1).data];
    return current.some((value, index) => value !== previous[index]);
  }, exposurePixels);
  const saturationPixels = await previewPixel();
  const preview = {
    warmth: await warmth.inputValue(),
    exposure: await exposure.inputValue(),
    saturation: await saturation.inputValue(),
    warmthPixels,
    exposurePixels,
    saturationPixels,
    visible: await editor.locator('.crump-precision-preview').isVisible(),
    saveEnabled: await editor.getByRole('button', {name: 'Apply changes'}).isEnabled(),
    pixels: await editor.evaluate(node => {
      const previewCanvas = node.querySelector('.crump-precision-preview');
      const maskCanvas = node.querySelector('.crump-precision-mask');
      const previewContext = previewCanvas.getContext('2d');
      const maskContext = maskCanvas.getContext('2d');
      const centerX = Math.floor(previewCanvas.width / 2);
      const centerY = Math.floor(previewCanvas.height / 2);
      return {
        outsideAlpha: previewContext.getImageData(5, 5, 1, 1).data[3],
        selectedAlpha: previewContext.getImageData(centerX, centerY, 1, 1).data[3],
        maskSelectedAlpha: maskContext.getImageData(centerX, centerY, 1, 1).data[3],
      };
    }),
  };
  await editor.getByRole('button', {name: 'Show original'}).click();
  const originalVisible = await editor.locator('.crump-precision-canvas-frame').evaluate(node => node.classList.contains('is-comparing-original'));
  await editor.getByRole('button', {name: 'Show edit'}).click();
  await editor.getByRole('button', {name: 'Apply changes'}).click();
  await page.waitForFunction(() => Boolean(window.__localSaveRequest && window.__appliedLocalFile));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const localSave = await page.evaluate(() => ({
    url: window.__localSaveRequest?.url,
    prefix: String(window.__localSaveRequest?.body?.maskDataUrl || '').slice(0, 22),
    adjustments: window.__localSaveRequest?.body?.adjustments,
    chatId: window.__localSaveRequest?.body?.chatId,
    requestFileId: window.__localSaveRequest?.savedFileId,
    fileId: window.__appliedLocalFile?.id,
    sourceFileId: window.__appliedLocalFile?.metadata?.sourceFileId,
    toast: window.__lastToast,
    focused: document.activeElement?.id,
  }));

  await page.evaluate(() => {
    window.__localSaveRequest = null;
    window.__appliedLocalFile = null;
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
    saveEnabled: await editor.getByRole('button', {name: 'Apply changes'}).isEnabled(),
    localCopy: await editor.locator('.crump-precision-exact-overlay').textContent(),
    hasVisiblePixels: await overlayCanvas.evaluate(node => {
      const pixels = node.getContext('2d').getImageData(0, 0, node.width, node.height).data;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] > 0) return true;
      }
      return false;
    }),
  };
  await editor.getByRole('button', {name: 'Apply changes'}).click();
  await page.waitForFunction(() => Boolean(window.__localSaveRequest?.body?.overlayDataUrl && window.__appliedLocalFile));
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const overlaySave = await page.evaluate(() => ({
    mask: window.__localSaveRequest?.body?.maskDataUrl,
    overlayPrefix: String(window.__localSaveRequest?.body?.overlayDataUrl || '').slice(0, 22),
    overlayLength: String(window.__localSaveRequest?.body?.overlayDataUrl || '').length,
    adjustments: window.__localSaveRequest?.body?.adjustments,
    requestFileId: window.__localSaveRequest?.savedFileId,
    fileId: window.__appliedLocalFile?.id,
    sourceFileId: window.__appliedLocalFile?.metadata?.sourceFileId,
    toast: window.__lastToast,
    focused: document.activeElement?.id,
  }));

  await page.evaluate(() => {
    const button = document.createElement('button');
    button.id = 'openOverlay';
    button.type = 'button';
    button.textContent = 'Open Exact Overlay';
    button.addEventListener('click', () => {
      const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#18222d"/></svg>',
      )}`;
      window.CrumpPrecisionImageEditor.open({
        file: {id: '11111111-1111-4111-8111-111111111111', name: 'private-photo.png', type: 'image/png'},
        url,
        entryMode: 'overlay',
        returnFocus: button,
      });
    });
    document.getElementById('fixtureWorkspace').appendChild(button);
  });
  const openOverlay = page.locator('#openOverlay');
  await openOverlay.click();
  const exactEditor = page.getByRole('dialog', {name: /Place an exact logo or wordmark/});
  await exactEditor.waitFor();
  await page.waitForFunction(() => document.activeElement?.textContent?.trim() === 'Add logo or image');
  const exactEntry = {
    entryMode: await exactEditor.getAttribute('data-entry-mode'),
    heading: await exactEditor.getByRole('heading').textContent(),
    placePressed: await exactEditor.getByRole('button', {name: 'Place'}).getAttribute('aria-pressed'),
    firstPanel: await exactEditor.locator('.crump-precision-controls').evaluate(node => node.children[1]?.className || ''),
    focused: await page.evaluate(() => document.activeElement?.textContent?.trim() || ''),
    status: await exactEditor.locator('.crump-precision-status').textContent(),
    copy: await exactEditor.locator('.crump-precision-exact-overlay').textContent(),
  };
  await exactEditor.getByRole('button', {name: 'Close Exact Overlay'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'openOverlay');
  const exactCloseFocus = await page.evaluate(() => document.activeElement?.id || '');

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
    saveVisible: await editor.getByRole('button', {name: 'Apply changes'}).isVisible(),
    aiVisible: await editor.getByRole('button', {name: 'Continue with AI edit'}).isVisible(),
    workspaceScrollable: await editor.locator('.crump-precision-workspace').evaluate(node => node.scrollHeight > node.clientHeight),
    imageWidth: await editor.locator('.crump-precision-canvas-frame img').evaluate(node => node.getBoundingClientRect().width),
    imageHeight: await editor.locator('.crump-precision-canvas-frame img').evaluate(node => node.getBoundingClientRect().height),
    canvasWidth: await editor.locator('.crump-precision-mask').evaluate(node => node.getBoundingClientRect().width),
    canvasHeight: await editor.locator('.crump-precision-mask').evaluate(node => node.getBoundingClientRect().height),
  };
  await page.screenshot({path: 'artifacts/precision-image-edit-mobile.png', fullPage: true});
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.activeElement?.id === 'openPrecision');
  const escaped = await page.evaluate(() => !document.querySelector('.crump-precision-editor'));
  const unexpectedFetches = await page.evaluate(() => window.__unexpectedFetches || []);
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
    || visibleImage.naturalWidth !== 640
    || visibleImage.naturalHeight !== 480
    || visibleImage.width <= 0
    || visibleImage.height <= 0
    || Math.abs(visibleImage.canvasWidth - visibleImage.width) > 2
    || Math.abs(visibleImage.canvasHeight - visibleImage.height) > 2
    || versions.count !== 2
    || versions.current !== 1
    || !versions.copy.includes('Original')
    || !versions.copy.includes('Current version')
    || !cropGuideVisible
    || !resetFrameEnabled
    || transformedSize.width >= 480
    || transformedSize.height >= 640
    || geometrySave.operations?.length !== 2
    || geometrySave.operations?.[0]?.type !== 'rotate'
    || geometrySave.operations?.[1]?.type !== 'crop'
    || geometrySave.mask !== ''
    || geometrySave.overlay !== ''
    || geometrySave.fileId !== geometrySave.requestFileId
    || geometrySave.sourceFileId !== '11111111-1111-4111-8111-111111111111'
    || zoomed.label !== '150%'
    || zoomed.width <= fittedWidth * 1.4
    || movePressed !== 'true'
    || lassoProof.pressed !== 'true'
    || !lassoProof.guideVisible
    || lassoProof.selected.center === 0
    || lassoProof.selected.corner !== 0
    || lassoProof.inverted.center !== 0
    || lassoProof.inverted.corner === 0
    || lassoProof.undo.center === 0
    || lassoProof.undo.corner !== 0
    || lassoProof.redo.center !== 0
    || lassoProof.redo.corner === 0
    || !broadInvertGuard.status.includes('too broad')
    || broadInvertGuard.pixels.center === 0
    || broadInvertGuard.pixels.corner !== 0
    || !redoEnabled
    || feather !== '1'
    || !guidedInstruction.includes('subtly warmer')
    || desktop.overflowX
    || staged.fileId !== '11111111-1111-4111-8111-111111111111'
    || staged.prefix !== 'data:image/png;base64,'
    || staged.width !== 640
    || staged.height !== 480
    || !staged.instruction.includes('subtly warmer')
    || staged.localSaveCount !== 0
    || staged.stageCalls !== 1
    || staged.appliedLocalFile !== null
    || staged.appliedEventCount !== 0
    || staged.maskProof.width !== 640
    || staged.maskProof.height !== 480
    || staged.maskProof.center === 0
    || staged.maskProof.corner !== 0
    || !staged.maskProof.nonzeroAlpha
    || staged.modalOpen
    || staged.focused !== 'openPrecision'
    || adjustmentAi.saveCount !== 1
    || !adjustmentAi.request?.url?.endsWith('/11111111-1111-4111-8111-111111111111/image-adjust')
    || !String(adjustmentAi.request?.body?.maskDataUrl || '').startsWith('data:image/png;base64,')
    || adjustmentAi.request?.body?.adjustments?.warmth !== 12
    || adjustmentAi.request?.body?.chatId !== '22222222-2222-4222-8222-222222222222'
    || adjustmentAi.request?.body?.overlayDataUrl !== ''
    || adjustmentAi.request?.body?.transform?.operations?.length !== 0
    || adjustmentAi.stagedFileId !== adjustmentAi.request?.savedFileId
    || adjustmentAi.stagedWidth !== 640
    || adjustmentAi.stagedHeight !== 480
    || adjustmentAi.stagedMaskPrefix !== 'data:image/png;base64,'
    || adjustmentAi.savedMetadata?.size !== '640x480'
    || adjustmentAi.savedMetadata?.sourceFileId !== '11111111-1111-4111-8111-111111111111'
    || adjustmentAi.stageCalls !== 1
    || !adjustmentAi.maskMatchesPersisted
    || adjustmentAi.maskProof.width !== 640
    || adjustmentAi.maskProof.height !== 480
    || adjustmentAi.maskProof.center === 0
    || adjustmentAi.maskProof.corner !== 0
    || !adjustmentAi.maskProof.nonzeroAlpha
    || adjustmentAi.appliedLocalFile !== null
    || adjustmentAi.appliedEventCount !== 0
    || adjustmentAi.modalOpen
    || adjustmentAi.lock.modalBusy !== 'true'
    || adjustmentAi.lock.useEnabled
    || adjustmentAi.lock.saveEnabled
    || adjustmentAi.lock.warmthEnabled
    || !adjustmentAi.lock.closeEnabled
    || !adjustmentAi.lock.cancelEnabled
    || adjustmentAi.lock.stagedBeforeRelease !== null
    || adjustmentAi.lock.stageCallsBeforeRelease !== 0
    || overlayAi.saveCount !== 1
    || overlayAi.request?.body?.maskDataUrl !== ''
    || !String(overlayAi.request?.body?.overlayDataUrl || '').startsWith('data:image/png;base64,')
    || overlayAi.request?.body?.adjustments?.warmth !== 0
    || overlayAi.request?.body?.adjustments?.exposure !== 0
    || overlayAi.request?.body?.adjustments?.saturation !== 0
    || overlayAi.request?.body?.transform?.operations?.length !== 0
    || overlayAi.request?.body?.chatId !== '22222222-2222-4222-8222-222222222222'
    || overlayAi.stagedFileId !== overlayAi.request?.savedFileId
    || overlayAi.stagedWidth !== 640
    || overlayAi.stagedHeight !== 480
    || overlayAi.stagedMaskPrefix !== 'data:image/png;base64,'
    || overlayAi.savedMetadata?.size !== '640x480'
    || overlayAi.savedMetadata?.sourceFileId !== '11111111-1111-4111-8111-111111111111'
    || overlayAi.stageCalls !== 1
    || !overlayAi.pendingImport.useDisabled
    || !overlayAi.pendingImport.saveDisabled
    || !overlayAi.pendingImport.addDisabled
    || !overlayAi.pendingImport.useEnabledAfter
    || !overlayAi.pendingImport.saveEnabledAfter
    || overlayAi.maskProof.width !== 640
    || overlayAi.maskProof.height !== 480
    || overlayAi.maskProof.center === 0
    || overlayAi.maskProof.corner !== 0
    || !overlayAi.maskProof.nonzeroAlpha
    || overlayAi.overlayProof.width !== 640
    || overlayAi.overlayProof.height !== 480
    || !overlayAi.overlayProof.nonzeroAlpha
    || overlayAi.overlayProof.corner !== 0
    || overlayAi.appliedLocalFile !== null
    || overlayAi.appliedEventCount !== 0
    || overlayAi.modalOpen
    || combinedAi.saveCount !== 1
    || !String(combinedAi.request?.body?.maskDataUrl || '').startsWith('data:image/png;base64,')
    || !String(combinedAi.request?.body?.overlayDataUrl || '').startsWith('data:image/png;base64,')
    || combinedAi.request?.body?.adjustments?.exposure !== 9
    || combinedAi.request?.body?.transform?.operations?.length !== 1
    || combinedAi.request?.body?.transform?.operations?.[0]?.type !== 'rotate'
    || combinedAi.request?.body?.chatId !== '22222222-2222-4222-8222-222222222222'
    || combinedAi.stagedFileId !== combinedAi.request?.savedFileId
    || combinedAi.stagedWidth !== 480
    || combinedAi.stagedHeight !== 640
    || combinedAi.stagedMaskPrefix !== 'data:image/png;base64,'
    || combinedAi.savedMetadata?.size !== '480x640'
    || combinedAi.savedMetadata?.sourceFileId !== '11111111-1111-4111-8111-111111111111'
    || combinedAi.stageCalls !== 1
    || !combinedAi.maskMatchesPersisted
    || combinedAi.maskProof.width !== combinedAi.stagedWidth
    || combinedAi.maskProof.height !== combinedAi.stagedHeight
    || combinedAi.maskProof.center === 0
    || combinedAi.maskProof.corner !== 0
    || !combinedAi.maskProof.nonzeroAlpha
    || combinedAi.overlayProof.width !== combinedAi.stagedWidth
    || combinedAi.overlayProof.height !== combinedAi.stagedHeight
    || !combinedAi.overlayProof.nonzeroAlpha
    || combinedAi.overlayProof.corner !== 0
    || combinedAi.appliedLocalFile !== null
    || combinedAi.appliedEventCount !== 0
    || combinedAi.modalOpen
    || failedAi.saveCount !== 1
    || failedAi.staged !== null
    || failedAi.stageCalls !== 0
    || failedAi.appliedLocalFile !== null
    || failedAi.appliedEventCount !== 0
    || !failedAi.modalOpen
    || failedAi.modalBusy !== null
    || failedAi.saturation !== '11'
    || failedAi.request?.body?.adjustments?.saturation !== 11
    || failedAi.request?.body?.transform?.operations?.length !== 1
    || failedAi.request?.body?.transform?.operations?.[0]?.type !== 'rotate'
    || !String(failedAi.request?.body?.maskDataUrl || '').startsWith('data:image/png;base64,')
    || !String(failedAi.request?.body?.overlayDataUrl || '').startsWith('data:image/png;base64,')
    || !failedAi.overlayPixels
    || failedAi.dimensions.width !== 480
    || failedAi.dimensions.height !== 640
    || failedAi.selectedAlpha === 0
    || !failedAi.resetFrameEnabled
    || !failedAi.saveEnabled
    || !failedAi.useEnabled
    || failedAi.useBusy !== null
    || dimensionMismatch.saveCount !== 1
    || dimensionMismatch.staged !== null
    || dimensionMismatch.stageCalls !== 0
    || dimensionMismatch.appliedLocalFile !== null
    || dimensionMismatch.appliedEventCount !== 0
    || !dimensionMismatch.modalOpen
    || dimensionMismatch.modalBusy !== null
    || dimensionMismatch.useBusy !== null
    || !dimensionMismatch.useEnabled
    || conversationRace.saveCount !== 1
    || conversationRace.requestChatId !== '22222222-2222-4222-8222-222222222222'
    || conversationRace.staged !== null
    || conversationRace.stageCalls !== 0
    || conversationRace.appliedLocalFile !== null
    || conversationRace.appliedEventCount !== 0
    || !conversationRace.modalOpen
    || conversationRace.modalBusy !== null
    || !conversationRace.useEnabled
    || !cancelledLateSuccess.cancelWasEnabled
    || cancelledLateSuccess.cancellationFocus !== 'crump-precision-cancel'
    || cancelledLateSuccess.saveCount !== 1
    || cancelledLateSuccess.saveAborts !== 0
    || cancelledLateSuccess.ignoredAborts !== 1
    || cancelledLateSuccess.responses !== 1
    || cancelledLateSuccess.staged !== null
    || cancelledLateSuccess.stageCalls !== 0
    || cancelledLateSuccess.appliedLocalFile !== null
    || cancelledLateSuccess.appliedEventCount !== 0
    || cancelledLateSuccess.modalOpen
    || cancelledLateSuccess.bodyOpen
    || unavailableWorkspace.saveCount !== 0
    || unavailableWorkspace.staged !== null
    || unavailableWorkspace.stageCalls !== 0
    || !unavailableWorkspace.modalOpen
    || unavailableWorkspace.modalBusy !== null
    || unavailableWorkspace.useBusy !== null
    || !unavailableWorkspace.useEnabled
    || unexpectedFetches.length !== 0
    || preview.warmth !== '18'
    || preview.exposure !== '16'
    || preview.saturation !== '-14'
    || JSON.stringify(preview.warmthPixels) === JSON.stringify(preview.exposurePixels)
    || JSON.stringify(preview.exposurePixels) === JSON.stringify(preview.saturationPixels)
    || !preview.visible
    || !preview.saveEnabled
    || preview.pixels.outsideAlpha === 0
    || preview.pixels.selectedAlpha === 0
    || preview.pixels.maskSelectedAlpha !== 0
    || !originalVisible
    || !localSave.url.endsWith('/11111111-1111-4111-8111-111111111111/image-adjust')
    || localSave.prefix !== 'data:image/png;base64,'
    || localSave.adjustments?.warmth !== 18
    || localSave.adjustments?.exposure !== 16
    || localSave.adjustments?.saturation !== -14
    || localSave.chatId !== '22222222-2222-4222-8222-222222222222'
    || localSave.fileId !== localSave.requestFileId
    || localSave.sourceFileId !== '11111111-1111-4111-8111-111111111111'
    || !localSave.toast?.message?.includes('Changes applied in this conversation')
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
    || overlaySave.fileId !== overlaySave.requestFileId
    || overlaySave.sourceFileId !== '11111111-1111-4111-8111-111111111111'
    || !overlaySave.toast?.message?.includes('Changes applied in this conversation')
    || overlaySave.focused !== 'openPrecision'
    || exactEntry.entryMode !== 'overlay'
    || exactEntry.heading !== 'Place an exact logo or wordmark.'
    || exactEntry.placePressed !== 'true'
    || exactEntry.firstPanel !== 'crump-precision-exact-overlay'
    || exactEntry.focused !== 'Add logo or image'
    || !exactEntry.status.includes('drag the approved artwork into place')
    || !exactEntry.copy.includes('NO AI OR CREDITS')
    || !exactEntry.copy.includes('flattened PNG or WebP wordmark')
    || exactCloseFocus !== 'openOverlay'
    || mobile.overflowX
    || Math.abs(mobile.editorWidth - mobile.viewportWidth) > 4
    || !mobile.closeVisible
    || !mobile.localControlsVisible
    || !mobile.saveVisible
    || !mobile.aiVisible
    || mobile.imageWidth <= 0
    || mobile.imageHeight <= 0
    || Math.abs(mobile.canvasWidth - mobile.imageWidth) > 2
    || Math.abs(mobile.canvasHeight - mobile.imageHeight) > 2
    || !mobile.workspaceScrollable
    || !escaped
  ) {
    throw new Error(JSON.stringify({desktop, visibleImage, versions, cropGuideVisible, resetFrameEnabled, transformedSize, geometrySave, zoomed, fittedWidth, movePressed, lassoProof, broadInvertGuard, redoEnabled, feather, guidedInstruction, staged, adjustmentAi, overlayAi, combinedAi, failedAi, dimensionMismatch, conversationRace, cancelledLateSuccess, unavailableWorkspace, unexpectedFetches, preview, originalVisible, localSave, overlayPreview, overlaySave, exactEntry, exactCloseFocus, mobile, escaped, errors}));
  }
  process.stdout.write(`${JSON.stringify({desktop, visibleImage, versions, cropGuideVisible, resetFrameEnabled, transformedSize, geometrySave, zoomed, fittedWidth, movePressed, lassoProof, broadInvertGuard, redoEnabled, feather, guidedInstruction, staged, adjustmentAi, overlayAi, combinedAi, failedAi, dimensionMismatch, conversationRace, cancelledLateSuccess, unavailableWorkspace, unexpectedFetches, preview, originalVisible, localSave, overlayPreview, overlaySave, exactEntry, exactCloseFocus, mobile, escaped, errors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
