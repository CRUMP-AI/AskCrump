const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/file-delivery.html', {waitUntil: 'domcontentloaded'});
  await page.locator('#fixtureOpener').focus();

  await page.evaluate(() => window.CrumpFileTools.open({
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Quarterly strategy.pptx',
    type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    size: 153600,
  }));
  const viewer = page.locator('.crump50-file-viewer');
  await viewer.waitFor({state: 'visible'});
  assert.equal(await viewer.getAttribute('role'), 'dialog');
  const viewerZIndex = Number(await viewer.evaluate(element => getComputedStyle(element).zIndex));
  const filesZIndex = Number(await page.locator('.crump53-overlay').evaluate(element => getComputedStyle(element).zIndex));
  assert.ok(viewerZIndex > filesZIndex, `file viewer layer ${viewerZIndex} must be above Files layer ${filesZIndex}`);
  assert.equal(await viewer.locator('#crump50FileViewerTitle').textContent(), 'Quarterly strategy.pptx');
  assert.equal(await viewer.locator('.crump50-file-viewer-placeholder strong').textContent(), 'Editable PowerPoint ready');
  assert.match(await viewer.locator('.crump50-file-viewer-placeholder p').textContent(), /keeps you on this screen/i);
  await viewer.locator('.crump50-file-viewer-placeholder button').click();

  const result = await page.evaluate(() => window.__fixture);
  assert.equal(result.openedWindows, 0);
  assert.deepEqual(result.downloads, [{
    href: '/api/files/11111111-1111-4111-8111-111111111111/content?download=1',
    target: '_self',
    download: 'Quarterly strategy.pptx',
  }]);

  await viewer.getByRole('button', {name: 'Done'}).click();
  await page.waitForTimeout(40);
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'fixtureOpener');
  await page.evaluate(() => window.CrumpFileTools.open({
    name: 'Campaign concept.png',
    type: 'image/png',
    size: 256,
    url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>',
  }));
  const imageViewer = page.locator('.crump50-lightbox');
  await imageViewer.waitFor({state: 'visible'});
  assert.equal(await imageViewer.getAttribute('role'), 'dialog');
  assert.equal(await imageViewer.getAttribute('aria-modal'), 'true');
  assert.equal(await imageViewer.locator('#crump50ImageViewerTitle').textContent(), 'Campaign concept.png');
  assert.ok(Number(await imageViewer.evaluate(element => getComputedStyle(element).zIndex)) > filesZIndex);
  await imageViewer.getByRole('button', {name: 'Done'}).click();
  await page.waitForTimeout(40);
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'fixtureOpener');
  assert.deepEqual(errors, []);
  await browser.close();
  process.stdout.write(JSON.stringify({result, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
