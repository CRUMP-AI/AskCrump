const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];
  const blockedRequests = [];
  const inlinePreviewRequests = [];
  const fixtureUrl = 'http://127.0.0.1:8765/tests/fixtures/file-delivery.html';
  const artifactNames = ['Project brief.docx', 'Project brief.pdf', 'Project slides.pptx'];
  const artifactDownloads = [
    {href: '/api/files/22222222-2222-4222-8222-222222222222/content?download=1', target: '_self', download: 'Project brief.docx'},
    {href: '/api/files/33333333-3333-4333-8333-333333333333/content?download=1', target: '_self', download: 'Project brief.pdf'},
    {href: '/api/files/44444444-4444-4444-8444-444444444444/content?download=1', target: '_self', download: 'Project slides.pptx'},
  ];

  async function openFixture(viewport, label) {
    const page = await browser.newPage({viewport});
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/files/33333333-3333-4333-8333-333333333333/content' && !url.search) {
        inlinePreviewRequests.push(`${label}: ${url.pathname}`);
        return route.abort();
      }
      if (url.hostname !== '127.0.0.1' || url.pathname.startsWith('/api/')) {
        blockedRequests.push(`${label}: ${url.href}`);
        return route.abort();
      }
      return route.continue();
    });
    page.on('console', message => { if (message.type() === 'error') errors.push(`${label}: ${message.text()}`); });
    page.on('pageerror', error => errors.push(`${label}: ${error.message}`));
    await page.goto(fixtureUrl, {waitUntil: 'domcontentloaded'});
    return page;
  }

  async function verifyArtifactCardActions(page, initialDownloads = []) {
    await page.waitForFunction(() => window.renderMessages?.__crump50Wrapped === true);
    await page.evaluate(() => window.renderMessages(window.chats[0].messages));
    const filesOverlay = page.locator('.crump53-overlay');
    await filesOverlay.waitFor({state: 'visible'});
    const filesZIndex = Number(await filesOverlay.evaluate(element => getComputedStyle(element).zIndex));
    const artifactCards = page.locator('#chatContainer .message-wrapper > .crump50-artifact');
    assert.equal(await artifactCards.count(), 3);
    assert.deepEqual(await artifactCards.locator('span').allTextContents(), ['DOCX', 'PDF', 'PPTX']);

    for (let index = 0; index < artifactNames.length; index += 1) {
      const card = artifactCards.nth(index);
      const open = card.getByRole('button', {name: 'Open'});
      const download = card.getByRole('button', {name: 'Download'});
      assert.equal(await open.count(), 1);
      assert.equal(await download.count(), 1);

      // Files intentionally stays mounted. Activate the obscured synthetic chat
      // reply directly so this fixture can prove its viewer layers above Files.
      await open.evaluate(button => button.click());
      const viewer = page.locator('.crump50-file-viewer');
      await viewer.waitFor({state: 'visible'});
      assert.equal(await viewer.locator('#crump50FileViewerTitle').textContent(), artifactNames[index]);
      assert.ok(Number(await viewer.evaluate(element => getComputedStyle(element).zIndex)) > filesZIndex);
      assert.equal(await filesOverlay.isVisible(), true);
      await viewer.getByRole('button', {name: 'Done'}).click();
      await viewer.waitFor({state: 'detached'});

      await download.evaluate(button => button.click());
      assert.equal(await filesOverlay.isVisible(), true);
    }

    const result = await page.evaluate(() => window.__fixture);
    assert.equal(result.openedWindows, 0);
    assert.deepEqual(result.downloads, [...initialDownloads, ...artifactDownloads]);
    return result;
  }

  const page = await openFixture({width: 390, height: 844}, 'mobile');
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

  const initialDownload = {
    href: '/api/files/11111111-1111-4111-8111-111111111111/content?download=1',
    target: '_self',
    download: 'Quarterly strategy.pptx',
  };
  const mobileResult = await verifyArtifactCardActions(page, [initialDownload]);
  await page.close();

  const desktopPage = await openFixture({width: 1280, height: 800}, 'desktop');
  const desktopResult = await verifyArtifactCardActions(desktopPage);
  await desktopPage.close();

  assert.deepEqual(blockedRequests, []);
  assert.deepEqual(inlinePreviewRequests, [
    'mobile: /api/files/33333333-3333-4333-8333-333333333333/content',
    'desktop: /api/files/33333333-3333-4333-8333-333333333333/content',
  ]);
  assert.deepEqual(errors, []);
  await browser.close();
  process.stdout.write(JSON.stringify({mobile: mobileResult, desktop: desktopResult, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
