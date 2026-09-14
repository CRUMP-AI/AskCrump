const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  try {
    await page.goto(`${fixtureOrigin}/tests/fixtures/recent-work-continuation.html`, {
      waitUntil: 'domcontentloaded',
    });
    const button = page.locator('#v1RecentWorkButton');
    await page.waitForFunction(() => document.getElementById('v1RecentWorkButton')?.dataset.chatId === 'newer-chat');
    assert.equal(await button.getAttribute('aria-label'), 'Continue: Newest planning note');
    assert.match(await button.textContent(), /Newest planning note/);

    await button.click();
    await page.waitForFunction(() => window.__openedChat === 'newer-chat');
    const result = await page.evaluate(() => ({
      openedChat: window.__openedChat,
      events: window.__events,
      toast: window.__toast,
    }));
    assert.equal(result.openedChat, 'newer-chat');
    assert.equal(result.toast, null);
    assert.deepEqual(result.events, [{
      name: 'RecentWorkResumed',
      detail: {eventKey: 'recent-work-resumed', source: 'launchpad'},
    }]);
    assert.deepEqual(errors, []);
    process.stdout.write('Recent-work proof passed: the visible label and fallback destination stay bound to the same conversation.\n');
  } finally {
    await page.close();
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
