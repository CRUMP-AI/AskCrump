const assert = require('node:assert/strict');
const {mkdirSync} = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const screenshotDir = String(process.argv[3] || '').trim();
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE
  || process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

async function snapshot(page) {
  return page.evaluate(() => {
    const desktop = document.querySelector('.crump53-active-project');
    const mobile = document.querySelector('.crump53-mobile-chat-project');
    return {
      desktopText: desktop?.textContent?.replace(/\s+/g, ' ').trim() || '',
      desktopDisplay: desktop ? getComputedStyle(desktop).display : 'missing',
      mobileText: mobile?.textContent?.replace(/\s+/g, ' ').trim() || '',
      mobileDisplay: mobile ? getComputedStyle(mobile).display : 'missing',
      bodyActive: document.body.classList.contains('crump53-chat-project-active'),
      dockSize: getComputedStyle(document.body).getPropertyValue('--ac-dock').trim(),
      storedTarget: localStorage.getItem('askcrump.activeProject53'),
      browserErrors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
    };
  });
}

async function verify(browser, viewport) {
  const page = await browser.newPage({viewport});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${baseUrl}/tests/fixtures/project-chat-context-boundary.html`, {waitUntil: 'load'});
  await page.waitForFunction(() => document.documentElement.dataset.fixtureReady === 'true');

  const projectId = await page.evaluate(() => fixtureProject.id);
  const {unrelatedChatId, linkedChatId, freshChatId} = await page.evaluate(() => window.fixtureIds);

  const selectedOnly = await snapshot(page);
  assert.equal(selectedOnly.storedTarget, projectId);
  assert.equal(selectedOnly.bodyActive, false, JSON.stringify(selectedOnly));

  const unrelated = await page.evaluate(async chatId => {
    window.fixtureOpenConversation(chatId);
    await new Promise(resolve => setTimeout(resolve, 80));
    return window.fixtureSend(chatId);
  }, unrelatedChatId);
  assert.equal(unrelated.projectId, undefined, JSON.stringify(unrelated));
  assert.equal(unrelated.projectContextChecked, true, JSON.stringify(unrelated));
  assert.equal((await snapshot(page)).bodyActive, false);

  await page.evaluate(chatId => window.fixtureOpenConversation(chatId), linkedChatId);
  await page.waitForFunction(() => document.body.classList.contains('crump53-chat-project-active'));
  const linked = await page.evaluate(chatId => window.fixtureSend(chatId), linkedChatId);
  const linkedState = await snapshot(page);
  assert.equal(linked.projectId, projectId, JSON.stringify(linked));
  assert.equal(linked.projectContextChecked, undefined, JSON.stringify(linked));
  assert.match(`${linkedState.desktopText} ${linkedState.mobileText}`, /Savannah Reading Series/);
  if (viewport.width <= 820) {
    assert.equal(linkedState.mobileDisplay, 'flex', JSON.stringify(linkedState));
    assert.equal(linkedState.desktopDisplay, 'none', JSON.stringify(linkedState));
    assert.equal(linkedState.dockSize, '146px', JSON.stringify(linkedState));
  } else {
    assert.equal(linkedState.desktopDisplay, 'inline-flex', JSON.stringify(linkedState));
    assert.equal(linkedState.mobileDisplay, 'none', JSON.stringify(linkedState));
  }
  if (screenshotDir) {
    mkdirSync(screenshotDir, {recursive: true});
    await page.screenshot({
      path: path.join(screenshotDir, viewport.width <= 820 ? 'mobile.png' : 'desktop.png'),
      fullPage: false,
    });
  }

  const leave = viewport.width <= 820
    ? page.locator('.crump53-mobile-chat-project button')
    : page.locator('.crump53-active-project button');
  await leave.click();
  await page.waitForFunction(() => !document.body.classList.contains('crump53-chat-project-active'));
  const paused = await page.evaluate(chatId => window.fixtureSend(chatId), linkedChatId);
  assert.equal(paused.projectId, undefined, JSON.stringify(paused));
  assert.equal(paused.projectContextChecked, true, JSON.stringify(paused));

  const fresh = await page.evaluate(async chatId => {
    window.fixtureOpenConversation(chatId, true);
    return window.fixtureSend(chatId);
  }, freshChatId);
  const freshState = await snapshot(page);
  assert.equal(fresh.projectId, undefined, JSON.stringify(fresh));
  assert.equal(fresh.projectContextChecked, true, JSON.stringify(fresh));
  assert.equal(freshState.storedTarget, projectId);
  assert.equal(freshState.bodyActive, false);
  assert.equal(freshState.browserErrors, 0);
  assert.deepEqual(errors, []);

  await page.close();
  return {viewport, selectedOnly, linkedState, freshState};
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath});
  try {
    const desktop = await verify(browser, {width: 1280, height: 760});
    const mobile = await verify(browser, {width: 390, height: 844});
    process.stdout.write(JSON.stringify({desktop, mobile}));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
