const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto(
    'http://127.0.0.1:8765/tests/fixtures/mobile-sidebar-actions.html?mode=mobile',
    {waitUntil: 'load'},
  );
  await page.waitForFunction(() => document.querySelector('.crump531-chat-menu-button'));

  const row = page.locator('.chat-item[data-chat-id="chat-1"]');
  const options = page.locator('.crump531-chat-menu-button');
  assert.equal(await row.getAttribute('aria-label'), 'Open conversation: Launch plan');
  assert.equal(await options.getAttribute('aria-label'), 'Conversation options for Launch plan');
  assert.equal(await options.getAttribute('aria-haspopup'), 'menu');
  assert.equal(await options.getAttribute('aria-expanded'), 'false');

  await page.locator('#menuBtn').click();
  await page.waitForFunction(() => document.getElementById('sidebar')?.classList.contains('active'));
  await options.click();
  const menu = page.locator('.crump531-chat-menu-popover');
  assert.equal(await options.getAttribute('aria-expanded'), 'true');
  assert.equal(await menu.getAttribute('role'), 'menu');
  assert.equal(await menu.getAttribute('aria-label'), 'Conversation actions for Launch plan');
  assert.equal(await menu.locator('[data-crump531-action="rename"]').getAttribute('aria-label'), 'Rename Launch plan');
  assert.equal(await menu.locator('[data-crump531-action="delete"]').getAttribute('aria-label'), 'Delete Launch plan');
  assert.equal(await page.evaluate(() => document.activeElement?.dataset.crump531Action), 'rename');
  assert.equal(await page.evaluate(() => window.fixtureEvents.chat), 0);
  assert.equal(await page.locator('#sidebar').evaluate(node => node.classList.contains('active')), true);

  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('.crump531-chat-menu-popover'));
  assert.equal(await options.getAttribute('aria-expanded'), 'false');
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('crump531-chat-menu-button')), true);
  assert.equal(await page.locator('#sidebar').evaluate(node => node.classList.contains('active')), true);

  await page.evaluate(() => { document.querySelector('.chat-title').textContent = 'Updated plan'; });
  await page.waitForFunction(() => (
    document.querySelector('.crump531-chat-menu-button')?.getAttribute('aria-label')
      === 'Conversation options for Updated plan'
  ));
  assert.equal(await row.getAttribute('aria-label'), 'Open conversation: Updated plan');

  if (!await page.locator('#sidebar').evaluate(node => node.classList.contains('active'))) {
    await page.locator('#menuBtn').click();
    await page.waitForFunction(() => document.getElementById('sidebar')?.classList.contains('active'));
  }
  await row.locator('.chat-item-content').click();
  assert.equal(await page.evaluate(() => window.fixtureEvents.chat), 1);
  assert.equal(await page.locator('#sidebar').evaluate(node => node.classList.contains('active')), false);
  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({
    row: 'Open conversation: Updated plan',
    options: 'Conversation options for Updated plan',
    menuRole: 'menu',
    escapeRestoredFocus: true,
    chatOpened: 1,
    errors,
  }));
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
