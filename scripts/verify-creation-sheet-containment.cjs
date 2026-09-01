const assert = require('node:assert/strict');

const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const expectedBackground = ['fixtureSidebar', 'fixtureWorkspace', 'fixtureNavigation'];

async function backgroundState(page) {
  return page.evaluate(ids => Object.fromEntries(ids.map(id => {
    const element = document.getElementById(id);
    return [id, {
      inert: element?.hasAttribute('inert') || false,
      ariaHidden: element?.getAttribute('aria-hidden'),
    }];
  })), expectedBackground);
}

function assertIsolated(state) {
  for (const id of expectedBackground) {
    assert.equal(state[id].inert, true, `${id} should be inert while a creation sheet is open`);
    assert.equal(state[id].ariaHidden, 'true', `${id} should be hidden from assistive technology while a creation sheet is open`);
  }
}

function assertRestored(state) {
  for (const id of expectedBackground) {
    assert.equal(state[id].inert, false, `${id} should regain interaction after a creation sheet closes`);
    assert.equal(state[id].ariaHidden, null, `${id} should regain its prior accessibility state after a creation sheet closes`);
  }
}

async function runViewport(browser, viewport) {
  const page = await browser.newPage({viewport});
  const consoleErrors = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', error => consoleErrors.push(error.message));

  await page.goto('http://127.0.0.1:8765/tests/fixtures/creation-sheet-containment.html', {waitUntil:'networkidle'});
  await page.waitForFunction(() => document.documentElement.dataset.crump50Booted === 'true');

  await page.locator('#openDocumentStudio').click();
  const documentStudio = page.getByRole('dialog', {name:'Start with the outcome. Crump will structure the file.'});
  await documentStudio.waitFor();
  const closeDocument = documentStudio.getByRole('button', {name:'Close Document Studio'});
  assert.equal(await documentStudio.getAttribute('aria-modal'), 'true');
  assert.equal(await closeDocument.evaluate(node => document.activeElement === node), true);
  assert.equal(await page.locator('#toastContainer').getAttribute('inert'), null);
  assertIsolated(await backgroundState(page));

  await page.keyboard.press('Shift+Tab');
  assert.equal(await page.evaluate(() => document.activeElement?.textContent?.trim()), 'TXTText');
  await page.keyboard.press('Tab');
  assert.equal(await closeDocument.evaluate(node => document.activeElement === node), true);
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.activeElement?.id === 'openDocumentStudio');
  assertRestored(await backgroundState(page));

  await page.locator('#openDocumentStudioTransient').click();
  await documentStudio.waitFor();
  await closeDocument.click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  assert.equal(await page.locator('#transientDocumentEntry').getAttribute('hidden'), '');
  assertRestored(await backgroundState(page));

  await page.locator('#openDocumentStudio').click();
  await documentStudio.waitFor();
  await documentStudio.getByRole('button', {name:'PPTX PowerPoint'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  assert.equal(await page.locator('#userInput').getAttribute('placeholder'), 'Describe the PowerPoint document you want…');
  assert.match(await page.locator('#crump50ToolChipHost').textContent(), /Create PPTX/);
  assertRestored(await backgroundState(page));

  await page.getByRole('button', {name:'Add to conversation'}).click();
  const attachmentSheet = page.getByRole('dialog', {name:'Add to conversation'});
  await attachmentSheet.waitFor();
  const closeAttachment = attachmentSheet.getByRole('button', {name:'Close Add to conversation'});
  assert.equal(await attachmentSheet.getAttribute('aria-modal'), 'true');
  assert.equal(await closeAttachment.evaluate(node => document.activeElement === node), true);
  assertIsolated(await backgroundState(page));
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.activeElement?.id === 'attachBtn');
  assertRestored(await backgroundState(page));

  assert.deepEqual(consoleErrors, []);
  await page.close();
  return {viewport, documentModal:true, attachmentModal:true, focusRestored:true, consoleErrors};
}

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless:true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  for (const viewport of [{width:390,height:844}, {width:1280,height:720}]) {
    results.push(await runViewport(browser, viewport));
  }
  await browser.close();
  process.stdout.write(`${JSON.stringify(results)}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
