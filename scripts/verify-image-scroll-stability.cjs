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
  await page.route('**/tests/fixtures/delayed-image.png*', async route => {
    await new Promise(resolve => setTimeout(resolve, 1200));
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

  await page.waitForFunction(() => document.querySelector('#scrollToEndBtn')?.dataset.crump522 === 'true');
  const userControlledResult = await page.evaluate(async () => {
    const chat = document.getElementById('chatContainer');
    chat.scrollTop = Math.min(420, Math.max(1, chat.scrollHeight - chat.clientHeight - 320));
    chat.dispatchEvent(new Event('scroll'));
    const before = Math.round(chat.scrollTop);

    window.__setPresence(true);
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterPresence = Math.round(chat.scrollTop);

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

    window.chats[0].messages.at(-1).content += ' Streaming text arrived.';
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterStream = Math.round(chat.scrollTop);

    window.crumpScrollManager.scrollToBottom({force: true});
    window.crumpScrollManager.autoScrollToBottom();
    window.crumpScrollManager.scrollToMessageTop(document.querySelector('[data-message-id="new-answer"]'));
    await new Promise(resolve => setTimeout(resolve, 160));
    const afterLegacyCalls = Math.round(chat.scrollTop);

    window.renderMessages([...window.chats[0].messages]);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterHistoryRestore = Math.round(chat.scrollTop);

    await new Promise(resolve => setTimeout(resolve, 1500));
    const afterImageLoad = Math.round(chat.scrollTop);

    window.crumpScrollManager.scrollToBottom({force: true});
    return {
      before,
      afterPresence,
      afterReply,
      afterStream,
      afterLegacyCalls,
      afterHistoryRestore,
      afterImageLoad,
      jumpVisible: document.getElementById('scrollToEndBtn').classList.contains('visible'),
    };
  });
  assert(userControlledResult.before > 0);
  assert.equal(userControlledResult.afterPresence, userControlledResult.before);
  assert.equal(userControlledResult.afterReply, userControlledResult.before);
  assert.equal(userControlledResult.afterStream, userControlledResult.before);
  assert.equal(userControlledResult.afterLegacyCalls, userControlledResult.before);
  assert.equal(userControlledResult.afterHistoryRestore, userControlledResult.before);
  assert.equal(userControlledResult.afterImageLoad, userControlledResult.before);
  assert.equal(userControlledResult.jumpVisible, true);

  await page.locator('#scrollToEndBtn').click();
  await page.waitForFunction(() => {
    const chat = document.getElementById('chatContainer');
    return chat && Math.round(chat.scrollHeight - chat.scrollTop - chat.clientHeight) <= 1;
  }, undefined, {timeout: 5000});
  const explicitJumpDistance = await page.locator('#chatContainer').evaluate(chat => (
    Math.round(chat.scrollHeight - chat.scrollTop - chat.clientHeight)
  ));
  assert(explicitJumpDistance <= 1);

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
    userControlledResult,
    explicitJumpDistance,
    manualScrollResult,
    errors,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
