const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  const imageRequests = new Map();
  await page.route('**/tests/fixtures/delayed-image.png*', async route => {
    const key = new URL(route.request().url()).search;
    imageRequests.set(key, (imageRequests.get(key) || 0) + 1);
    await new Promise(resolve => setTimeout(resolve, 1200));
    await route.fulfill({status: 200, contentType: 'image/png', body: png});
  });
  await page.route('**/api/files/11111111-1111-4111-8111-111111111111/content', async route => {
    const key = 'uploaded-reference';
    imageRequests.set(key, (imageRequests.get(key) || 0) + 1);
    await new Promise(resolve => setTimeout(resolve, 400));
    await route.fulfill({status: 200, contentType: 'image/png', body: png});
  });
  await page.route('**/api/files/22222222-2222-4222-8222-222222222222/content', async route => {
    const key = 'changed-reference';
    imageRequests.set(key, (imageRequests.get(key) || 0) + 1);
    await route.fulfill({status: 200, contentType: 'image/png', body: png});
  });

  await page.goto('http://127.0.0.1:8765/tests/fixtures/image-scroll-stability.html', {waitUntil: 'domcontentloaded'});
  const reserved = await page.locator('.message-image').evaluate(image => ({
    width: image.getAttribute('width'),
    height: image.getAttribute('height'),
    aspect: image.dataset.imageAspect,
    renderedHeight: Math.round(image.getBoundingClientRect().height),
  }));
  assert.equal(reserved.width, '1024');
  assert.equal(reserved.height, '1536');
  assert.equal(reserved.aspect, 'portrait');
  assert(reserved.renderedHeight > 400);
  await page.locator('[data-message-id="image-answer"] .message-image').evaluate(image => {
    image.loading = 'eager';
    image.scrollIntoView({block: 'center'});
  });
  await page.waitForFunction(() => {
    const image = document.querySelector('[data-message-id="image-answer"] .message-image');
    return image?.complete && image.naturalWidth > 0;
  });
  await page.locator('[data-message-id="user-2"] .crump52-image-attachment img').waitFor({state: 'attached'});
  await page.locator('[data-message-id="user-2"] .crump52-image-attachment img').evaluate(image => {
    image.loading = 'eager';
  });
  await page.waitForFunction(() => {
    const image = document.querySelector('[data-message-id="user-2"] .crump52-image-attachment img');
    return image?.complete && image.naturalWidth > 0;
  });
  await page.evaluate(() => {
    window.__initialImageNode = document.querySelector('[data-message-id="image-answer"] .message-image');
    window.__uploadedImageNode = document.querySelector('[data-message-id="user-2"] .crump52-image-attachment img');
  });

  await page.waitForFunction(() => document.querySelector('#scrollToEndBtn')?.dataset.crump522 === 'true');
  const initialCue = await page.evaluate(() => ({
    pending: document.getElementById('scrollToEndBtn')?.dataset.newResponse || '',
    label: document.getElementById('scrollToEndBtn')?.getAttribute('aria-label') || '',
    announcement: document.getElementById('crump522NewResponseStatus')?.textContent || '',
  }));
  assert.equal(initialCue.pending, '');
  assert.equal(initialCue.label, 'Jump to newest message');
  assert.equal(initialCue.announcement, '');

  const userControlledResult = await page.evaluate(async () => {
    const chat = document.getElementById('chatContainer');
    chat.scrollTop = Math.min(420, Math.max(1, chat.scrollHeight - chat.clientHeight - 320));
    chat.dispatchEvent(new Event('scroll'));
    const before = Math.round(chat.scrollTop);
    const initialImageIsStable = () => (
      document.querySelector('[data-message-id="image-answer"] .message-image')
        === window.__initialImageNode
    );
    const uploadedImageIsStable = () => (
      document.querySelector('[data-message-id="user-2"] .crump52-image-attachment img')
        === window.__uploadedImageNode
    );
    const imageIdentity = [initialImageIsStable()];
    const uploadedImageIdentity = [uploadedImageIsStable()];

    const renderCallsBeforePresence = window.__renderCalls;
    window.CrumpPresence.start('thinking');
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterPresence = Math.round(chat.scrollTop);
    const presencePending = document.getElementById('scrollToEndBtn')?.dataset.newResponse || '';
    window.__presenceNode = document.querySelector('.presence-message');
    const renderCallsAfterPresenceStart = window.__renderCalls;
    imageIdentity.push(initialImageIsStable());
    uploadedImageIdentity.push(uploadedImageIsStable());

    await new Promise(resolve => setTimeout(resolve, 2900));
    const afterPresenceExpansion = Math.round(chat.scrollTop);
    const renderCallsAfterPresenceExpansion = window.__renderCalls;
    const expansionPresenceNodeStable = document.querySelector('.presence-message') === window.__presenceNode;
    const expansionLabel = document.querySelector('.presence-message .presence-label')?.textContent || '';
    imageIdentity.push(initialImageIsStable());
    uploadedImageIdentity.push(uploadedImageIsStable());

    await new Promise(resolve => setTimeout(resolve, 1450));
    const afterPresenceRotation = Math.round(chat.scrollTop);
    const renderCallsAfterPresenceRotation = window.__renderCalls;
    const rotationPresenceNodeStable = document.querySelector('.presence-message') === window.__presenceNode;
    const rotationLabel = document.querySelector('.presence-message .presence-label')?.textContent || '';
    imageIdentity.push(initialImageIsStable());
    uploadedImageIdentity.push(uploadedImageIsStable());

    window.CrumpPresence.update('searching');
    await new Promise(resolve => setTimeout(resolve, 40));
    const afterPresenceUpdate = Math.round(chat.scrollTop);
    const renderCallsAfterPresenceUpdate = window.__renderCalls;
    const updatePresenceNodeStable = document.querySelector('.presence-message') === window.__presenceNode;
    const updateLabel = document.querySelector('.presence-message .presence-label')?.textContent || '';
    imageIdentity.push(initialImageIsStable());
    uploadedImageIdentity.push(uploadedImageIsStable());

    window.chats[0].messages.push({
      id: 'new-answer',
      role: 'assistant',
      content: 'A newly completed image response.',
      imageUrl: '/tests/fixtures/delayed-image.png?new-answer=1',
      imageAspect: 'portrait',
    });
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterReply = Math.round(chat.scrollTop);
    imageIdentity.push(initialImageIsStable());
    uploadedImageIdentity.push(uploadedImageIsStable());
    window.__newImageNode = document.querySelector('[data-message-id="new-answer"] .message-image');
    window.__newImageNode.loading = 'eager';
    const replyCue = {
      pending: document.getElementById('scrollToEndBtn')?.dataset.newResponse || '',
      label: document.getElementById('scrollToEndBtn')?.getAttribute('aria-label') || '',
      announcement: document.getElementById('crump522NewResponseStatus')?.textContent || '',
    };

    window.chats[0].messages.at(-1).content += ' Streaming text arrived.';
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterStream = Math.round(chat.scrollTop);
    imageIdentity.push(
      initialImageIsStable(),
      document.querySelector('[data-message-id="new-answer"] .message-image')
        === window.__newImageNode,
    );
    uploadedImageIdentity.push(uploadedImageIsStable());

    window.crumpScrollManager.scrollToBottom({force: true});
    window.crumpScrollManager.autoScrollToBottom();
    window.crumpScrollManager.scrollToMessageTop(document.querySelector('[data-message-id="new-answer"]'));
    await new Promise(resolve => setTimeout(resolve, 160));
    const afterLegacyCalls = Math.round(chat.scrollTop);

    window.renderMessages([...window.chats[0].messages]);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterHistoryRestore = Math.round(chat.scrollTop);
    imageIdentity.push(
      initialImageIsStable(),
      document.querySelector('[data-message-id="new-answer"] .message-image')
        === window.__newImageNode,
    );
    uploadedImageIdentity.push(uploadedImageIsStable());

    await new Promise(resolve => setTimeout(resolve, 1500));
    const afterImageLoad = Math.round(chat.scrollTop);
    imageIdentity.push(
      initialImageIsStable(),
      document.querySelector('[data-message-id="new-answer"] .message-image')
        === window.__newImageNode,
    );
    uploadedImageIdentity.push(uploadedImageIsStable());

    const uploadedMessage = window.chats[0].messages.find(message => message.id === 'user-2');
    uploadedMessage.files = [{
      id: '22222222-2222-4222-8222-222222222222',
      name: 'replacement-reference.png',
      type: 'image/png',
      size: 4096,
    }];
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 160));
    const replacementImage = document.querySelector('[data-message-id="user-2"] .crump52-image-attachment img');
    replacementImage.loading = 'eager';
    await new Promise(resolve => setTimeout(resolve, 80));
    const changedAttachmentReplaced = replacementImage !== window.__uploadedImageNode
      && replacementImage.getAttribute('src') === '/api/files/22222222-2222-4222-8222-222222222222/content';
    const afterAttachmentChange = Math.round(chat.scrollTop);

    uploadedMessage.files = [];
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    const removedAttachmentIsGone = !document.querySelector('[data-message-id="user-2"] .crump52-rich-attachments');
    const afterAttachmentRemoval = Math.round(chat.scrollTop);

    window.crumpScrollManager.scrollToBottom({force: true});
    return {
      before,
      afterPresence,
      presencePending,
      renderCallsBeforePresence,
      renderCallsAfterPresenceStart,
      afterPresenceExpansion,
      renderCallsAfterPresenceExpansion,
      expansionPresenceNodeStable,
      expansionLabel,
      afterPresenceRotation,
      renderCallsAfterPresenceRotation,
      rotationPresenceNodeStable,
      rotationLabel,
      afterPresenceUpdate,
      renderCallsAfterPresenceUpdate,
      updatePresenceNodeStable,
      updateLabel,
      afterReply,
      replyCue,
      afterStream,
      afterLegacyCalls,
      afterHistoryRestore,
      afterImageLoad,
      imageIdentity,
      uploadedImageIdentity,
      changedAttachmentReplaced,
      removedAttachmentIsGone,
      afterAttachmentChange,
      afterAttachmentRemoval,
      jumpVisible: document.getElementById('scrollToEndBtn').classList.contains('visible'),
    };
  });
  assert(userControlledResult.before > 0);
  assert.equal(userControlledResult.afterPresence, userControlledResult.before);
  assert.equal(userControlledResult.presencePending, '');
  assert.equal(
    userControlledResult.renderCallsAfterPresenceStart,
    userControlledResult.renderCallsBeforePresence + 1,
  );
  assert.equal(userControlledResult.afterPresenceExpansion, userControlledResult.before);
  assert.equal(
    userControlledResult.renderCallsAfterPresenceExpansion,
    userControlledResult.renderCallsAfterPresenceStart,
  );
  assert.equal(userControlledResult.expansionPresenceNodeStable, true);
  assert.equal(userControlledResult.expansionLabel, 'Crump is thinking…');
  assert.equal(userControlledResult.afterPresenceRotation, userControlledResult.before);
  assert.equal(
    userControlledResult.renderCallsAfterPresenceRotation,
    userControlledResult.renderCallsAfterPresenceStart,
  );
  assert.equal(userControlledResult.rotationPresenceNodeStable, true);
  assert.equal(userControlledResult.rotationLabel, 'Crump is connecting the thread…');
  assert.equal(userControlledResult.afterPresenceUpdate, userControlledResult.before);
  assert.equal(
    userControlledResult.renderCallsAfterPresenceUpdate,
    userControlledResult.renderCallsAfterPresenceStart,
  );
  assert.equal(userControlledResult.updatePresenceNodeStable, true);
  assert.equal(userControlledResult.updateLabel, 'Crump is searching…');
  assert.equal(userControlledResult.afterReply, userControlledResult.before);
  assert.equal(userControlledResult.replyCue.pending, 'true');
  assert.equal(userControlledResult.replyCue.label, 'New response available. Jump to newest message');
  assert.equal(
    userControlledResult.replyCue.announcement,
    'New response available. Use Jump to newest message when you are ready.',
  );
  assert.equal(userControlledResult.afterStream, userControlledResult.before);
  assert.equal(userControlledResult.afterLegacyCalls, userControlledResult.before);
  assert.equal(userControlledResult.afterHistoryRestore, userControlledResult.before);
  assert.equal(userControlledResult.afterImageLoad, userControlledResult.before);
  assert(userControlledResult.imageIdentity.every(Boolean));
  assert(userControlledResult.uploadedImageIdentity.every(Boolean));
  assert.equal(userControlledResult.changedAttachmentReplaced, true);
  assert.equal(userControlledResult.removedAttachmentIsGone, true);
  assert.equal(userControlledResult.afterAttachmentChange, userControlledResult.before);
  assert.equal(userControlledResult.afterAttachmentRemoval, userControlledResult.before);
  assert.equal(imageRequests.get(''), 1);
  assert.equal(imageRequests.get('?new-answer=1'), 1);
  assert.equal(imageRequests.get('uploaded-reference'), 1);
  assert.equal(imageRequests.get('changed-reference'), 1);
  assert.equal(userControlledResult.jumpVisible, true);

  const presenceStopResult = await page.evaluate(() => {
    const chat = document.getElementById('chatContainer');
    const scrollTop = Math.round(chat.scrollTop);
    const image = document.querySelector('[data-message-id="image-answer"] .message-image');
    const renderCalls = window.__renderCalls;
    window.CrumpPresence.stop();
    return {
      before: scrollTop,
      after: Math.round(chat.scrollTop),
      imageStable: document.querySelector('[data-message-id="image-answer"] .message-image') === image,
      renderCallsBefore: renderCalls,
      renderCallsAfter: window.__renderCalls,
      presenceRemoved: !document.querySelector('.presence-message'),
    };
  });
  assert.equal(presenceStopResult.after, presenceStopResult.before);
  assert.equal(presenceStopResult.imageStable, true);
  assert.equal(presenceStopResult.renderCallsAfter, presenceStopResult.renderCallsBefore + 1);
  assert.equal(presenceStopResult.presenceRemoved, true);

  const explicitJump = await page.evaluate(() => {
    const chat = document.getElementById('chatContainer');
    const before = Math.round(chat.scrollHeight - chat.scrollTop - chat.clientHeight);
    document.getElementById('scrollToEndBtn').click();
    const after = Math.round(chat.scrollHeight - chat.scrollTop - chat.clientHeight);
    return {before, after};
  });
  assert(explicitJump.before > 1);
  const explicitJumpDistance = explicitJump.after;
  assert(explicitJumpDistance <= 1);
  const clearedCue = await page.evaluate(() => ({
    pending: document.getElementById('scrollToEndBtn')?.dataset.newResponse || '',
    label: document.getElementById('scrollToEndBtn')?.getAttribute('aria-label') || '',
    announcement: document.getElementById('crump522NewResponseStatus')?.textContent || '',
  }));
  assert.equal(clearedCue.pending, '');
  assert.equal(clearedCue.label, 'Jump to newest message');
  assert.equal(clearedCue.announcement, '');

  const manualScrollResult = await page.locator('#chatContainer').evaluate(async chat => {
    const target = Math.max(1, Math.round(chat.scrollTop / 2));
    chat.scrollTop = target;
    chat.dispatchEvent(new Event('scroll'));
    await new Promise(resolve => setTimeout(resolve, 250));
    return {target, actual: Math.round(chat.scrollTop)};
  });
  assert.equal(manualScrollResult.actual, manualScrollResult.target);
  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({
    reserved,
    initialCue,
    userControlledResult,
    presenceStopResult,
    explicitJump,
    explicitJumpDistance,
    clearedCue,
    manualScrollResult,
    errors,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
