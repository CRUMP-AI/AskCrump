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

  await page.goto('http://127.0.0.1:8765/tests/fixtures/video-reference-upload.html', {waitUntil: 'networkidle'});
  await page.evaluate(() => localStorage.removeItem('askcrump.videoRequest53'));
  await page.evaluate(() => {
    localStorage.removeItem('askcrump.videoReferenceDraft53');
    localStorage.removeItem(`askcrump.videoReferenceDraft53:${encodeURIComponent(window.__fixtureUser.id)}`);
  });

  await page.evaluate(() => window.CrumpProduct53.handleCreationHandoff({
    kind: 'video',
    brief: 'Animate the approved bus while preserving its appearance.',
    autoOpen: true,
    autoStart: true,
    idempotencyKey: 'chat-video:reference-fixture',
    referenceFiles: [
      {id: '00000000-0000-0000-0000-000000000021', name: 'bus.png', type: 'image/png', size: 100, role: 'subject'},
      {id: '00000000-0000-0000-0000-000000000022', name: 'mascot.png', type: 'image/png', size: 100, role: 'mascot'},
    ],
  }));
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 2);
  const handoffResult = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    selectedEngine: document.querySelector('#crump53VideoEngine')?.value || '',
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }));
  if (
    handoffResult.requestStarted
    || handoffResult.selectedEngine !== 'extendable'
    || handoffResult.referenceCards !== 2
    || JSON.stringify(handoffResult.roles) !== JSON.stringify(['subject', 'mascot'])
    || !handoffResult.status.includes('Confirm each ordered role')
    || !handoffResult.status.includes('before credits')
    || !handoffResult.status.includes('Exact logos and readable text are not locked')
  ) {
    throw new Error(JSON.stringify({handoffResult, consoleErrors}));
  }

  await page.evaluate(() => window.CrumpProduct53.handleCreationHandoff({
    kind: 'video',
    brief: 'Do not start with a missing reference.',
    autoOpen: true,
    autoStart: true,
    idempotencyKey: 'chat-video:invalid-reference-fixture',
    referenceFiles: [
      {id: '00000000-0000-0000-0000-000000000025', name: 'valid.png', type: 'image/png', size: 100},
      {id: '00000000-0000-0000-0000-000000000026', name: 'invalid.pdf', type: 'application/pdf', size: 100},
    ],
  }));
  await page.locator('#crump53GenerateVideo').click();
  const invalidHandoff = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    statusIsError: document.querySelector('#crump53VideoStatus')?.classList.contains('is-error') || false,
  }));
  if (
    invalidHandoff.requestStarted
    || !invalidHandoff.status.includes('Reattach them before creating')
    || !invalidHandoff.statusIsError
  ) {
    throw new Error(JSON.stringify({invalidHandoff, consoleErrors}));
  }

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

  await page.evaluate(() => {
    localStorage.removeItem('askcrump.videoReferenceDraft53');
    localStorage.removeItem(`askcrump.videoReferenceDraft53:${encodeURIComponent(window.__fixtureUser.id)}`);
  });
  await page.reload({waitUntil: 'networkidle'});
  await page.evaluate(() => localStorage.removeItem('askcrump.videoRequest53'));
  await page.locator('#openVideo').click();
  await page.locator('#crump53VideoEngine').selectOption('extendable');
  await page.locator('#crump53VideoReferenceInput').setInputFiles([
    {name: 'bus.png', mimeType: 'image/png', buffer: png},
    {name: 'logo.png', mimeType: 'image/png', buffer: png},
  ]);
  await page.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 2);
  const roleSelectors = page.locator('[data-video-reference-role]');
  await roleSelectors.nth(1).selectOption('logo');
  await page.locator('#crump53VideoPrompt').fill('A blue school bus drives carefully through a quiet neighborhood.');
  await page.locator('#crump53GenerateVideo').click();
  await page.waitForFunction(() => document.querySelector('#crump53GenerateVideo')?.textContent.includes('Confirm'));
  const beforeConfirmation = await page.evaluate(() => ({
    requestStarted: Boolean(window.__videoRequest),
    button: document.querySelector('#crump53GenerateVideo')?.textContent || '',
    status: document.querySelector('#crump53VideoStatus')?.textContent || '',
    plan: document.querySelector('#crump53VideoReferencePlan')?.textContent || '',
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
    referenceIds: [...document.querySelectorAll('[data-video-reference-id]')].map(card => card.dataset.videoReferenceId),
    storedDraft: localStorage.getItem(`askcrump.videoReferenceDraft53:${encodeURIComponent(window.currentUser.id)}`) || '',
  }));
  await page.reload({waitUntil: 'networkidle'});
  await page.locator('#openVideo').click();
  await page.waitForFunction(() => (
    document.querySelectorAll('.crump53-video-reference-card').length === 2
    && document.querySelector('#crump53GenerateVideo')?.textContent === 'Confirm & create video'
  ));
  const restoredDraft = await page.evaluate(() => {
    const storedDraft = localStorage.getItem(`askcrump.videoReferenceDraft53:${encodeURIComponent(window.currentUser.id)}`) || '';
    return {
      selectedEngine: document.querySelector('#crump53VideoEngine')?.value || '',
      button: document.querySelector('#crump53GenerateVideo')?.textContent || '',
      status: document.querySelector('#crump53VideoStatus')?.textContent || '',
      plan: document.querySelector('#crump53VideoReferencePlan')?.textContent || '',
      roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
      referenceIds: [...document.querySelectorAll('[data-video-reference-id]')].map(card => card.dataset.videoReferenceId),
      imageSources: [...document.querySelectorAll('.crump53-video-reference-card img')].map(image => image.getAttribute('src') || ''),
      storedDraft,
      storedDraftContainsImageData: /base64|data:image|blob:/i.test(storedDraft),
      storedDraftContainsPreviewUrl: /"url"\s*:/i.test(storedDraft),
      storedConfirmation: Boolean(JSON.parse(storedDraft || '{}').confirmationSignature),
    };
  });
  await page.locator('#crump53VideoPrompt').fill('A blue school bus drives carefully through a quiet neighborhood.');
  await page.locator('#crump53GenerateVideo').click();
  await page.waitForFunction(() => Boolean(window.__videoRequest));
  await page.waitForFunction(() => (
    !localStorage.getItem(`askcrump.videoReferenceDraft53:${encodeURIComponent(window.currentUser.id)}`)
  ));
  await page.waitForFunction(() => document.querySelectorAll('[data-video-reference-receipt] [data-reference-input]').length === 2);

  const result = await page.evaluate(() => {
    const storedRequest = localStorage.getItem('askcrump.videoRequest53') || '';
    const receipt = document.querySelector('[data-video-reference-receipt]');
    return {
      label: document.querySelector('#crump53VideoReferenceLabel')?.textContent || '',
      help: document.querySelector('#crump53VideoReferenceHelp')?.textContent || '',
      referenceCards: document.querySelectorAll('.crump53-video-reference-card').length,
      referenceFileIds: window.__videoRequest?.referenceFileIds || [],
      referencePlan: window.__videoRequest?.referencePlan || [],
      requestContainsImageData: /base64|data:image/i.test(JSON.stringify(window.__videoRequest || {})),
      recoveryContainsImageData: /base64|data:image/i.test(storedRequest),
      referenceDraftCleared: !localStorage.getItem(`askcrump.videoReferenceDraft53:${encodeURIComponent(window.currentUser.id)}`),
      selectedEngine: window.__videoRequest?.engine || '',
      providerStarts: window.__videoProviderStarts,
      receiptCount: document.querySelectorAll('[data-video-reference-receipt]').length,
      receiptHeading: receipt?.querySelector('h3')?.textContent || '',
      receiptText: receipt?.textContent || '',
      receiptTransport: receipt?.querySelector('[data-video-reference-transport]')?.textContent || '',
      receiptMode: receipt?.dataset.referenceMode || '',
      receiptVerification: receipt?.dataset.referenceVerification || '',
      receiptInputs: [...(receipt?.querySelectorAll('[data-reference-input]') || [])].map(item => ({
        input: item.querySelector('strong')?.textContent || '',
        role: item.querySelector('span')?.textContent || '',
      })),
      receiptAction: receipt?.querySelector('[data-video-reference-compare]')?.textContent || '',
      runwayAttributionVisible: document.querySelector('#crump53RunwayAttribution')?.getClientRects().length > 0,
      mobileOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      errorOverlay: Boolean(document.querySelector('[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay')),
    };
  });
  const startingFrameReceipt = await page.evaluate(() => {
    const root = document.createElement('div');
    document.body.appendChild(root);
    const rendered = window.CrumpVideoReferenceReceipt?.render(root, {
      status: 'ready',
      referenceMode: 'initial-frame',
      referenceVerification: 'not-performed',
      referencePlan: [{
        input: 1,
        fileId: '00000000-0000-0000-0000-000000000011',
        role: 'subject',
      }],
    });
    const receipt = root.querySelector('[data-video-reference-receipt]');
    const value = {
      rendered,
      transport: receipt?.querySelector('[data-video-reference-transport]')?.textContent || '',
      inputs: [...(receipt?.querySelectorAll('[data-reference-input]') || [])].map(item => item.textContent || ''),
      verification: receipt?.dataset.referenceVerification || '',
    };
    root.remove();
    return value;
  });
  const accountPage = await browser.newPage({viewport: {width: 390, height: 844}});
  await accountPage.route('**/api/files/*/content', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: png,
  }));
  accountPage.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(`account lifecycle: ${message.text()}`);
  });
  accountPage.on('pageerror', error => consoleErrors.push(`account lifecycle: ${error.message}`));
  await accountPage.goto('http://127.0.0.1:8765/tests/fixtures/video-reference-upload.html', {waitUntil: 'networkidle'});
  const accountBId = '00000000-0000-0000-0000-000000000002';
  await accountPage.evaluate(accountB => {
    const base = 'askcrump.videoReferenceDraft53';
    localStorage.removeItem(base);
    localStorage.removeItem(`${base}:${encodeURIComponent(window.__fixtureUser.id)}`);
    localStorage.removeItem(`${base}:${encodeURIComponent(accountB)}`);
  }, accountBId);
  await accountPage.evaluate(() => {
    localStorage.setItem('askcrump.videoReferenceDraft53', JSON.stringify({
      version: 1,
      userId: window.__fixtureUser.id,
      updatedAt: Date.now(),
      engine: 'quick',
      handoffInvalid: false,
      confirmationSignature: '',
      files: [{
        id: '00000000-0000-0000-0000-000000000019',
        name: 'legacy-account-a.png',
        type: 'image/png',
        size: 68,
        role: 'subject',
      }],
    }));
  });
  await accountPage.evaluate(accountB => {
    window.currentUser = {id: accountB};
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  }, accountBId);
  const legacyWhileBActive = await accountPage.evaluate(() => ({
    cards: document.querySelectorAll('.crump53-video-reference-card').length,
    legacyPreserved: Boolean(localStorage.getItem('askcrump.videoReferenceDraft53')),
  }));
  await accountPage.evaluate(() => {
    window.currentUser = window.__fixtureUser;
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  });
  await accountPage.waitForFunction(() => (
    document.querySelector('.crump53-video-reference-card span')?.textContent === 'legacy-account-a.png'
  ));
  const legacyMigratedForA = await accountPage.evaluate(() => {
    const accountKey = `askcrump.videoReferenceDraft53:${encodeURIComponent(window.__fixtureUser.id)}`;
    return {
      accountKey,
      legacyRemoved: !localStorage.getItem('askcrump.videoReferenceDraft53'),
      accountDraft: JSON.parse(localStorage.getItem(accountKey) || 'null'),
    };
  });
  await accountPage.evaluate(accountKey => {
    window.SafeStorage.removeItem(accountKey);
    window.currentUser = null;
    window.dispatchEvent(new CustomEvent('crump:authentication-required', {detail: {reason: 'checkout'}}));
    window.currentUser = window.__fixtureUser;
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  }, legacyMigratedForA.accountKey);
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 0);
  const legacyOwnership = {legacyWhileBActive, legacyMigratedForA};
  await accountPage.locator('#openVideo').click();
  await accountPage.locator('#crump53VideoReferenceInput').setInputFiles({
    name: 'account-a.png',
    mimeType: 'image/png',
    buffer: png,
  });
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 1);
  await accountPage.locator('[data-video-reference-role]').selectOption('logo');
  const accountABeforeLogout = await accountPage.evaluate(() => {
    const key = `askcrump.videoReferenceDraft53:${encodeURIComponent(window.currentUser.id)}`;
    return {
      key,
      stored: localStorage.getItem(key) || '',
      cards: document.querySelectorAll('.crump53-video-reference-card').length,
      roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
    };
  });
  await accountPage.evaluate(() => {
    window.currentUser = null;
    window.dispatchEvent(new CustomEvent('crump:authentication-required', {detail: {reason: 'checkout'}}));
  });
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 0);
  const signedOutState = await accountPage.evaluate(key => ({
    cards: document.querySelectorAll('.crump53-video-reference-card').length,
    planHidden: document.querySelector('#crump53VideoReferencePlan')?.hidden === true,
    resultEmpty: !document.querySelector('#crump53VideoResult')?.textContent?.trim(),
    accountADraftPreserved: Boolean(localStorage.getItem(key)),
  }), accountABeforeLogout.key);
  await accountPage.evaluate(user => {
    window.currentUser = user;
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  }, {id: '00000000-0000-0000-0000-000000000001'});
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 1);
  const sameUserRestored = await accountPage.evaluate(() => ({
    names: [...document.querySelectorAll('.crump53-video-reference-card span')].map(item => item.textContent),
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }));
  await accountPage.evaluate(userId => {
    window.currentUser = {id: userId};
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  }, accountBId);
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 0);
  await accountPage.locator('#crump53VideoReferenceInput').setInputFiles({
    name: 'account-b.png',
    mimeType: 'image/png',
    buffer: png,
  });
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 1);
  await accountPage.locator('[data-video-reference-role]').selectOption('style');
  const accountBStored = await accountPage.evaluate(accountB => {
    const base = 'askcrump.videoReferenceDraft53';
    const accountAKey = `${base}:${encodeURIComponent(window.__fixtureUser.id)}`;
    const accountBKey = `${base}:${encodeURIComponent(accountB)}`;
    return {
      accountAKey,
      accountBKey,
      accountA: JSON.parse(localStorage.getItem(accountAKey) || 'null'),
      accountB: JSON.parse(localStorage.getItem(accountBKey) || 'null'),
      legacyDraft: localStorage.getItem(base) || '',
    };
  }, accountBId);
  await accountPage.evaluate(() => {
    window.currentUser = window.__fixtureUser;
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  });
  await accountPage.waitForFunction(() => (
    document.querySelector('.crump53-video-reference-card span')?.textContent === 'account-a.png'
  ));
  const switchedBackToA = await accountPage.evaluate(() => ({
    names: [...document.querySelectorAll('.crump53-video-reference-card span')].map(item => item.textContent),
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }));
  await accountPage.evaluate(accountB => {
    window.currentUser = {id: accountB};
    window.CrumpProduct53.open('video');
  }, accountBId);
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 0);
  const staleUserBlocked = await accountPage.evaluate(({accountAKey, accountBKey}) => ({
    cards: document.querySelectorAll('.crump53-video-reference-card').length,
    accountADraftPreserved: Boolean(localStorage.getItem(accountAKey)),
    accountBDraftPreserved: Boolean(localStorage.getItem(accountBKey)),
  }), accountBStored);
  await accountPage.evaluate(accountB => {
    window.currentUser = {id: accountB};
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  }, accountBId);
  await accountPage.waitForFunction(() => (
    document.querySelector('.crump53-video-reference-card span')?.textContent === 'account-b.png'
  ));
  const switchedToB = await accountPage.evaluate(() => ({
    names: [...document.querySelectorAll('.crump53-video-reference-card span')].map(item => item.textContent),
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }));
  await accountPage.evaluate(({accountAKey, accountBKey}) => {
    window.SafeStorage.persistent = false;
    localStorage.removeItem(accountAKey);
    localStorage.removeItem(accountBKey);
    window.currentUser = null;
    window.dispatchEvent(new CustomEvent('crump:authentication-required', {detail: {reason: 'checkout'}}));
  }, accountBStored);
  await accountPage.waitForFunction(() => document.querySelectorAll('.crump53-video-reference-card').length === 0);
  await accountPage.evaluate(accountB => {
    window.currentUser = {id: accountB};
    window.dispatchEvent(new Event('crump:authenticated-ready'));
  }, accountBId);
  await accountPage.waitForFunction(() => (
    document.querySelector('.crump53-video-reference-card span')?.textContent === 'account-b.png'
  ));
  const safeStorageMemoryFallback = await accountPage.evaluate(({accountAKey, accountBKey}) => ({
    persistent: window.SafeStorage.persistent,
    accountAInMemory: Boolean(window.SafeStorage.getItem(accountAKey)),
    accountBInMemory: Boolean(window.SafeStorage.getItem(accountBKey)),
    accountAInLocalStorage: Boolean(localStorage.getItem(accountAKey)),
    accountBInLocalStorage: Boolean(localStorage.getItem(accountBKey)),
    names: [...document.querySelectorAll('.crump53-video-reference-card span')].map(item => item.textContent),
    roles: [...document.querySelectorAll('[data-video-reference-role]')].map(select => select.value),
  }), accountBStored);
  const accountLifecycle = {
    legacyOwnership,
    accountABeforeLogout,
    signedOutState,
    sameUserRestored,
    accountBStored,
    switchedBackToA,
    staleUserBlocked,
    switchedToB,
    safeStorageMemoryFallback,
  };
  await accountPage.close();
  await page.screenshot({path: 'artifacts/video-reference-mobile.png', fullPage: true});
  await browser.close();

  if (
    consoleErrors.length
    || result.label !== 'Optional appearance guidance · up to 3'
    || !result.help.includes('best-effort appearance guidance')
    || result.referenceCards !== 2
    || beforeConfirmation.requestStarted
    || beforeConfirmation.button !== 'Confirm & create video'
    || !beforeConfirmation.status.includes('Review before credits')
    || !beforeConfirmation.status.includes('Reference 1: Subject / product')
    || !beforeConfirmation.status.includes('Reference 2: Logo / wordmark')
    || !beforeConfirmation.plan.includes('ORDERED REFERENCE PLAN')
    || !beforeConfirmation.plan.includes('not a pixel-locked frame or layout')
    || JSON.stringify(beforeConfirmation.roles) !== JSON.stringify(['subject', 'logo'])
    || /base64|data:image|blob:/i.test(beforeConfirmation.storedDraft)
    || /"url"\s*:/i.test(beforeConfirmation.storedDraft)
    || restoredDraft.selectedEngine !== 'extendable'
    || restoredDraft.button !== 'Confirm & create video'
    || !restoredDraft.status.includes('reviewed ordered plan')
    || !restoredDraft.plan.includes('ORDERED REFERENCE PLAN')
    || JSON.stringify(restoredDraft.roles) !== JSON.stringify(beforeConfirmation.roles)
    || JSON.stringify(restoredDraft.referenceIds) !== JSON.stringify(beforeConfirmation.referenceIds)
    || restoredDraft.imageSources.some(source => !/^\/api\/files\/[^/]+\/content$/.test(source))
    || restoredDraft.storedDraftContainsImageData
    || restoredDraft.storedDraftContainsPreviewUrl
    || !restoredDraft.storedConfirmation
    || result.referenceFileIds.length !== 2
    || result.referencePlan.length !== 2
    || result.referencePlan[0]?.fileId !== result.referenceFileIds[0]
    || result.referencePlan[0]?.role !== 'subject'
    || result.referencePlan[1]?.fileId !== result.referenceFileIds[1]
    || result.referencePlan[1]?.role !== 'logo'
    || result.requestContainsImageData
    || result.recoveryContainsImageData
    || !result.referenceDraftCleared
    || result.selectedEngine !== 'extendable'
    || result.providerStarts !== 1
    || result.receiptCount !== 1
    || result.receiptHeading !== 'What was sent with this video'
    || result.receiptMode !== 'appearance-guidance'
    || result.receiptVerification !== 'not-performed'
    || !result.receiptTransport.includes('best-effort appearance guidance')
    || !result.receiptTransport.includes('not as pixel-locked frames or layouts')
    || JSON.stringify(result.receiptInputs) !== JSON.stringify([
      {input: 'Input image 1', role: 'Subject / product'},
      {input: 'Input image 2', role: 'Logo / wordmark'},
    ])
    || !result.receiptText.includes('Exact logos, readable text, and subject identity were not automatically verified')
    || !result.receiptText.includes('Pause on representative frames and compare them side by side')
    || !result.receiptText.includes('deterministic overlay')
    || result.receiptAction !== 'Open Files to compare'
    || !startingFrameReceipt.rendered
    || !startingFrameReceipt.transport.includes('sent as the starting frame')
    || !startingFrameReceipt.transport.includes('not verified frame-by-frame fidelity')
    || startingFrameReceipt.inputs.length !== 1
    || !startingFrameReceipt.inputs[0].includes('Input image 1Subject / product')
    || startingFrameReceipt.verification !== 'not-performed'
    || accountLifecycle.legacyOwnership.legacyWhileBActive.cards !== 0
    || !accountLifecycle.legacyOwnership.legacyWhileBActive.legacyPreserved
    || !accountLifecycle.legacyOwnership.legacyMigratedForA.legacyRemoved
    || accountLifecycle.legacyOwnership.legacyMigratedForA.accountDraft?.userId !== '00000000-0000-0000-0000-000000000001'
    || accountLifecycle.legacyOwnership.legacyMigratedForA.accountDraft?.files?.[0]?.name !== 'legacy-account-a.png'
    || accountLifecycle.accountABeforeLogout.cards !== 1
    || JSON.stringify(accountLifecycle.accountABeforeLogout.roles) !== JSON.stringify(['logo'])
    || !accountLifecycle.accountABeforeLogout.stored
    || accountLifecycle.signedOutState.cards !== 0
    || !accountLifecycle.signedOutState.planHidden
    || !accountLifecycle.signedOutState.resultEmpty
    || !accountLifecycle.signedOutState.accountADraftPreserved
    || JSON.stringify(accountLifecycle.sameUserRestored.names) !== JSON.stringify(['account-a.png'])
    || JSON.stringify(accountLifecycle.sameUserRestored.roles) !== JSON.stringify(['logo'])
    || accountLifecycle.accountBStored.accountA?.userId !== '00000000-0000-0000-0000-000000000001'
    || accountLifecycle.accountBStored.accountB?.userId !== accountBId
    || accountLifecycle.accountBStored.accountA?.files?.[0]?.name !== 'account-a.png'
    || accountLifecycle.accountBStored.accountB?.files?.[0]?.name !== 'account-b.png'
    || accountLifecycle.accountBStored.legacyDraft
    || JSON.stringify(accountLifecycle.switchedBackToA.names) !== JSON.stringify(['account-a.png'])
    || JSON.stringify(accountLifecycle.switchedBackToA.roles) !== JSON.stringify(['logo'])
    || accountLifecycle.staleUserBlocked.cards !== 0
    || !accountLifecycle.staleUserBlocked.accountADraftPreserved
    || !accountLifecycle.staleUserBlocked.accountBDraftPreserved
    || JSON.stringify(accountLifecycle.switchedToB.names) !== JSON.stringify(['account-b.png'])
    || JSON.stringify(accountLifecycle.switchedToB.roles) !== JSON.stringify(['style'])
    || accountLifecycle.safeStorageMemoryFallback.persistent
    || !accountLifecycle.safeStorageMemoryFallback.accountAInMemory
    || !accountLifecycle.safeStorageMemoryFallback.accountBInMemory
    || accountLifecycle.safeStorageMemoryFallback.accountAInLocalStorage
    || accountLifecycle.safeStorageMemoryFallback.accountBInLocalStorage
    || JSON.stringify(accountLifecycle.safeStorageMemoryFallback.names) !== JSON.stringify(['account-b.png'])
    || JSON.stringify(accountLifecycle.safeStorageMemoryFallback.roles) !== JSON.stringify(['style'])
    || result.runwayAttributionVisible
    || result.mobileOverflow
    || result.errorOverlay
  ) {
    throw new Error(JSON.stringify({beforeConfirmation, restoredDraft, result, startingFrameReceipt, accountLifecycle, consoleErrors}));
  }
  process.stdout.write(`${JSON.stringify({beforeConfirmation, restoredDraft, result, startingFrameReceipt, accountLifecycle, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
