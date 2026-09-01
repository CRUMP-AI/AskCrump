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
  await page.route('**/tests/fixtures/delayed-image.png', async route => {
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
  const reviewResult = await page.evaluate(async () => {
    const chat = document.getElementById('chatContainer');
    chat.scrollTop = 0;
    chat.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, pointerType: 'touch'}));
    window.__setPresence(true);
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    return {
      scrollTop: Math.round(chat.scrollTop),
      distanceFromBottom: Math.round(chat.scrollHeight - chat.scrollTop - chat.clientHeight),
      jumpVisible: document.getElementById('scrollToEndBtn').classList.contains('visible'),
    };
  });
  assert.equal(reviewResult.scrollTop, 0);
  assert(reviewResult.distanceFromBottom > 500);
  assert.equal(reviewResult.jumpVisible, true);

  const newReplyResult = await page.evaluate(async () => {
    const chat = document.getElementById('chatContainer');
    window.__setPresence(false);
    window.chats[0].messages.push({id: 'new-answer', role: 'assistant', content: 'A newly completed response.'});
    window.renderMessages(window.chats[0].messages);
    await new Promise(resolve => setTimeout(resolve, 80));
    const afterReply = Math.round(chat.scrollTop);
    window.crumpScrollManager.scrollToBottom({force: true});
    return {
      afterReply,
      forcedDistance: Math.round(chat.scrollHeight - chat.scrollTop - chat.clientHeight),
    };
  });
  assert.equal(newReplyResult.afterReply, 0);
  assert(newReplyResult.forcedDistance <= 1);
  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({reserved, reviewResult, newReplyResult, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
