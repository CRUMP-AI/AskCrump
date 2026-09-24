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

  await page.evaluate(() => {
    window.CrumpFileTools.addReference({
      id: '55555555-5555-4555-8555-555555555555',
      name: 'approved-logo.png',
      type: 'image/png',
      size: 68,
      url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    });
  });
  await page.locator('#userInput').fill('Create a gentle storybook portrait using this reference, with a blue garden background.');
  await page.locator('#sendButton').click();
  const referenceDialog = page.getByRole('dialog', {name: 'Image Studio'});
  await referenceDialog.waitFor();
  const beforeConfirmation = await page.evaluate(() => ({
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    sendCalls: window.__fixture.sendCalls,
    roles: [...document.querySelectorAll('[aria-label^="Role for reference"]')].map(select => select.value),
    summary: [...document.querySelectorAll('.crump50-image-guidance')].map(node => node.textContent || '').join(' '),
    projectReferenceName: document.body.textContent.includes('approved-logo.png'),
  }));
  await referenceDialog.locator('[aria-label="Role for reference 2"]').selectOption('logo');
  await referenceDialog.getByRole('button', {name: 'Confirm reference plan'}).click();
  await page.evaluate(() => {
    const send = window.CrumpChatTransport.send;
    window.__referenceContractFailurePending = true;
    window.CrumpChatTransport.send = async body => {
      const data = await send(body);
      if (window.__referenceContractFailurePending) {
        window.__referenceContractFailurePending = false;
        const error = new Error('The reference plan no longer matches the attached images.');
        error.code = 'IMAGE_REFERENCE_PLAN_INVALID';
        throw error;
      }
      data.referencePlan = [
        {input: 1, fileId: '11111111-1111-4111-8111-111111111111', role: 'base'},
        {input: 2, fileId: '55555555-5555-4555-8555-555555555555', role: 'logo'},
      ];
      data.referenceReview = {
        status: 'warn',
        method: 'local-reference-signals-v1',
        humanReviewRequired: true,
        reviewProviderUsed: false,
        reviewCreditsUsed: 0,
        limitations: ['identity', 'logos', 'text', 'pixel-fidelity'],
        message: 'Local checks are limited or need attention. Review every original before publishing.',
        references: [
          {
            input: 1,
            fileId: '11111111-1111-4111-8111-111111111111',
            role: 'base',
            status: 'pass',
            signals: {color: 'aligned', structure: 'aligned'},
            humanChecks: ['composition-details'],
            userReview: 'pending',
          },
          {
            input: 2,
            fileId: '55555555-5555-4555-8555-555555555555',
            role: 'logo',
            status: 'warn',
            signals: {color: 'aligned', structure: 'attention'},
            humanChecks: ['logo-shape', 'logo-colors'],
            userReview: 'pending',
          },
        ],
      };
      return data;
    };
  });
  await page.locator('#sendButton').click();
  await page.waitForFunction(() => window.__fixture.sendCalls === 1);
  await referenceDialog.waitFor();
  const contractRecovery = await page.evaluate(() => ({
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    sendCalls: window.__fixture.sendCalls,
    roles: [...document.querySelectorAll('[aria-label^="Role for reference"]')].map(select => select.value),
    prompt: document.querySelector('#userInput')?.value || '',
    toast: [...document.querySelectorAll('.toast__message')].at(-1)?.textContent || '',
    studioOpen: Boolean(document.querySelector('[role="dialog"][aria-label="Image Studio"]')),
  }));
  await referenceDialog.getByRole('button', {name: 'Confirm reference plan'}).click();
  await page.locator('#sendButton').click();
  await page.waitForFunction(() => window.__fixture.sendCalls === 2);
  const revised = await page.evaluate(() => ({
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    sendCalls: window.__fixture.sendCalls,
    message: window.__fixture.sentBody?.message || '',
    fileRefs: window.__fixture.sentBody?.fileRefs || [],
    referencePlan: window.__fixture.sentBody?.imageReferencePlan || [],
    referencePlanConfirmed: window.__fixture.sentBody?.imageReferencePlanConfirmed,
    referenceContractVersion: window.__fixture.sentBody?.imageReferenceContractVersion,
    receipt: document.querySelector('.crump50-reference-receipt')?.textContent || '',
    resultCount: document.querySelectorAll('.crump50-reference-result').length,
    signalCount: document.querySelectorAll('.crump50-reference-signals span').length,
    reviewActionCount: document.querySelectorAll('.crump50-reference-review-actions button').length,
  }));

  await page.getByRole('button', {name: 'Confirm reference 1 was reviewed'}).click();
  await page.getByRole('button', {name: 'Flag reference 2 as a mismatch'}).click();
  const userReviewed = await page.evaluate(() => ({
    receipt: document.querySelector('.crump50-reference-receipt')?.textContent || '',
    sendCalls: window.__fixture.sendCalls,
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    decisions: window.chats[0].messages
      .find(message => message.role === 'assistant')
      ?.referenceReview?.references?.map(reference => reference.userReview) || [],
  }));
  await page.evaluate(() => {
    const reference = window.chats[0].messages
      .find(message => message.role === 'assistant')
      ?.referenceReview?.references?.[1];
    if (reference) reference.status = 'mismatch';
  });
  await page.getByRole('button', {name: 'Confirm reference 2 was reviewed'}).click();
  const mismatchCleared = await page.evaluate(() => ({
    receipt: document.querySelector('.crump50-reference-receipt')?.textContent || '',
    sendCalls: window.__fixture.sendCalls,
    ensureUsageCalls: window.__fixture.ensureUsageCalls,
    decision: window.chats[0].messages
      .find(message => message.role === 'assistant')
      ?.referenceReview?.references?.[1]?.userReview || '',
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
    && beforeConfirmation.ensureUsageCalls === 0
    && beforeConfirmation.sendCalls === 0
    && JSON.stringify(beforeConfirmation.roles) === JSON.stringify(['base', 'subject'])
    && beforeConfirmation.summary.includes('Reference 1 → Starting canvas / composition')
    && beforeConfirmation.summary.includes('Reference 2 → Subject / product')
    && beforeConfirmation.projectReferenceName
    && contractRecovery.ensureUsageCalls === 1
    && contractRecovery.sendCalls === 1
    && JSON.stringify(contractRecovery.roles) === JSON.stringify(['base', 'logo'])
    && contractRecovery.prompt.includes('blue garden background')
    && contractRecovery.toast.includes('Review every ordered reference role')
    && contractRecovery.studioOpen
    && revised.ensureUsageCalls === 2
    && revised.sendCalls === 2
    && revised.message.includes('blue garden background')
    && revised.fileRefs.length === 2
    && revised.fileRefs[0] === '11111111-1111-4111-8111-111111111111'
    && revised.fileRefs[1] === '55555555-5555-4555-8555-555555555555'
    && JSON.stringify(revised.referencePlan) === JSON.stringify([
      {fileId: '11111111-1111-4111-8111-111111111111', role: 'base'},
      {fileId: '55555555-5555-4555-8555-555555555555', role: 'logo'},
    ])
    && revised.referencePlanConfirmed === true
    && revised.referenceContractVersion === 2
    && revised.receipt.includes('Reference check · 2 local comparisons')
    && revised.receipt.includes('Local color and structure checks only · no extra generation or credits')
    && revised.receipt.includes('Reference 1 · Starting canvas / composition')
    && revised.receipt.includes('Reference 2 · Logo / wordmark')
    && revised.receipt.includes('Signals align')
    && revised.receipt.includes('Review needed')
    && revised.receipt.includes('Color · aligns')
    && revised.receipt.includes('Structure · needs attention')
    && revised.receipt.includes('cannot verify identity, exact logos, spelling, or pixel fidelity')
    && revised.resultCount === 2
    && revised.signalCount === 4
    && revised.reviewActionCount === 4
    && userReviewed.receipt.includes('You reviewed this reference.')
    && userReviewed.receipt.includes('You flagged a mismatch.')
    && userReviewed.receipt.includes('Mismatch flagged')
    && JSON.stringify(userReviewed.decisions) === JSON.stringify(['confirmed', 'mismatch'])
    && userReviewed.sendCalls === 2
    && userReviewed.ensureUsageCalls === 2
    && mismatchCleared.receipt.includes('Reference 2 · Logo / wordmarkReview needed')
    && !mismatchCleared.receipt.includes('Mismatch flagged')
    && mismatchCleared.decision === 'confirmed'
    && mismatchCleared.sendCalls === 2
    && mismatchCleared.ensureUsageCalls === 2
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
  if (!valid) throw new Error(JSON.stringify({restored, unchanged, beforeConfirmation, contractRecovery, revised, userReviewed, mismatchCleared, replacementRestored, replacementBlocked, consoleErrors}));
  process.stdout.write(`${JSON.stringify({restored, unchanged, beforeConfirmation, contractRecovery, revised, userReviewed, mismatchCleared, replacementRestored, replacementBlocked, consoleErrors})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
