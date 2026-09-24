const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];
  const blockedRequests = [];
  const inlinePreviewRequests = [];
  const signedPreviewRequests = [];
  const nativeSignedRequests = [];
  const securityPolicyViolations = [];
  const fixtureUrl = 'http://127.0.0.1:8765/tests/fixtures/file-delivery.html';
  const signedPdfUrl = 'https://xncftwjfpjskgtwgbgci.supabase.co/storage/v1/object/sign/crump-files/fixture/project-brief.pdf?token=fixture-token';
  const nativeSignedUrl = (fileId, download = false) => {
    const suffix = download ? '&download=Ask-Crump-file' : '';
    return `https://xncftwjfpjskgtwgbgci.supabase.co/storage/v1/object/sign/crump-files/native/${fileId}.bin?token=native-token${suffix}`;
  };
  const artifactNames = ['Project brief.docx', 'Project brief.pdf', 'Project slides.pptx'];
  const artifactDownloads = [
    {href: '/api/files/22222222-2222-4222-8222-222222222222/content?download=1', target: '_self', download: 'Project brief.docx'},
    {href: '/api/files/33333333-3333-4333-8333-333333333333/content?download=1', target: '_self', download: 'Project brief.pdf'},
    {href: '/api/files/44444444-4444-4444-8444-444444444444/content?download=1', target: '_self', download: 'Project slides.pptx'},
  ];

  async function openFixture(viewport, label, {native = false} = {}) {
    const context = await browser.newContext({viewport});
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.setBlockedURLs', {
      urls: [signedPdfUrl, 'https://xncftwjfpjskgtwgbgci.supabase.co/storage/v1/object/sign/crump-files/native/*'],
    });
    await page.addInitScript(() => {
      window.__cspViolations = [];
      window.addEventListener('securitypolicyviolation', event => {
        window.__cspViolations.push({
          blockedURI: event.blockedURI,
          directive: event.effectiveDirective,
        });
      });
    });
    if (native) {
      await page.addInitScript(() => {
        window.CrumpAPI = {isNative: true};
      });
    }
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      const nativeSignedMatch = native
        ? url.pathname.match(/^\/api\/files\/([0-9a-f-]{36})\/signed$/i)
        : null;
      if (nativeSignedMatch) {
        const download = url.searchParams.get('download') === '1';
        nativeSignedRequests.push(`${label}: ${url.pathname}${url.search}`);
        if (nativeSignedMatch[1] === '88888888-8888-4888-8888-888888888888' && !download) {
          return route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({success: false, error: 'Signing unavailable'}),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            url: nativeSignedUrl(nativeSignedMatch[1], download),
            name: 'Ask-Crump-file',
            mimeType: 'application/octet-stream',
          }),
        });
      }
      if (url.pathname === '/api/files/33333333-3333-4333-8333-333333333333/content' && !url.search) {
        inlinePreviewRequests.push(`${label}: ${url.pathname}`);
        return route.fulfill({
          status: 302,
          headers: {location: signedPdfUrl, 'cache-control': 'no-store'},
          body: '',
        });
      }
      if (
        native
        && url.hostname === 'xncftwjfpjskgtwgbgci.supabase.co'
        && url.pathname.startsWith('/storage/v1/object/sign/crump-files/native/')
      ) {
        return route.abort();
      }
      if (url.hostname !== '127.0.0.1' || url.pathname.startsWith('/api/')) {
        blockedRequests.push(`${label}: ${url.href}`);
        return route.abort();
      }
      return route.continue();
    });
    page.on('request', request => {
      if (request.url() === signedPdfUrl) {
        signedPreviewRequests.push(`${label}: ${new URL(request.url()).origin}`);
      }
    });
    page.on('console', message => { if (message.type() === 'error') errors.push(`${label}: ${message.text()}`); });
    page.on('pageerror', error => errors.push(`${label}: ${error.message}`));
    await page.goto(fixtureUrl, {waitUntil: 'domcontentloaded'});
    return {page, context};
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

      const signedPreview = index === 1
        ? page.waitForRequest(request => request.url() === signedPdfUrl, {timeout: 3_000})
        : null;
      await open.evaluate(button => button.click());
      const viewer = page.locator('.crump50-file-viewer');
      await viewer.waitFor({state: 'visible'});
      assert.equal(await viewer.locator('#crump50FileViewerTitle').textContent(), artifactNames[index]);
      assert.ok(Number(await viewer.evaluate(element => getComputedStyle(element).zIndex)) > filesZIndex);
      assert.equal(await filesOverlay.isVisible(), true);
      if (index === 1) {
        await signedPreview;
      }
      await viewer.getByRole('button', {name: 'Done'}).click();
      await viewer.waitFor({state: 'detached'});

      await download.evaluate(button => button.click());
      assert.equal(await filesOverlay.isVisible(), true);
    }

    const result = await page.evaluate(() => window.__fixture);
    assert.equal(result.openedWindows, 0);
    assert.deepEqual(result.downloads, [...initialDownloads, ...artifactDownloads]);
    securityPolicyViolations.push(...await page.evaluate(() => window.__cspViolations));
    return result;
  }

  const mobileFixture = await openFixture({width: 390, height: 844}, 'mobile');
  const {page} = mobileFixture;
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
  await mobileFixture.context.close();

  const desktopFixture = await openFixture({width: 1280, height: 800}, 'desktop');
  const desktopPage = desktopFixture.page;
  const desktopResult = await verifyArtifactCardActions(desktopPage);
  await desktopFixture.context.close();

  const nativeFixture = await openFixture({width: 390, height: 844}, 'native', {native: true});
  const nativePage = nativeFixture.page;
  const nativeFiles = {
    pdf: {id: '55555555-5555-4555-8555-555555555555', name: 'Native preview.pdf', type: 'application/pdf'},
    image: {id: '66666666-6666-4666-8666-666666666666', name: 'Native image.png', type: 'image/png'},
    video: {id: '77777777-7777-4777-8777-777777777777', name: 'Native video.mp4', type: 'video/mp4'},
    deck: {id: '88888888-8888-4888-8888-888888888888', name: 'Native deck.pptx', type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation'},
  };

  await nativePage.evaluate(file => window.CrumpFileTools.open(file), nativeFiles.pdf);
  let nativeViewer = nativePage.locator('.crump50-file-viewer');
  await nativeViewer.waitFor({state: 'visible'});
  assert.equal(
    await nativeViewer.locator('iframe').getAttribute('src'),
    nativeSignedUrl(nativeFiles.pdf.id),
  );
  await nativeViewer.getByRole('button', {name: 'Done'}).click();

  await nativePage.evaluate(file => window.CrumpFileTools.open(file), nativeFiles.image);
  const nativeImageViewer = nativePage.locator('.crump50-lightbox');
  await nativeImageViewer.waitFor({state: 'visible'});
  assert.equal(
    await nativeImageViewer.locator('img').getAttribute('src'),
    nativeSignedUrl(nativeFiles.image.id),
  );
  await nativeImageViewer.getByRole('button', {name: 'Done'}).click();

  await nativePage.evaluate(file => window.CrumpFileTools.open(file), nativeFiles.video);
  nativeViewer = nativePage.locator('.crump50-file-viewer');
  await nativeViewer.waitFor({state: 'visible'});
  assert.equal(
    await nativeViewer.locator('video').getAttribute('src'),
    nativeSignedUrl(nativeFiles.video.id),
  );
  await nativeViewer.getByRole('button', {name: 'Done'}).click();

  await nativePage.evaluate(file => window.CrumpFileTools.open(file), nativeFiles.deck);
  nativeViewer = nativePage.locator('.crump50-file-viewer');
  await nativeViewer.waitFor({state: 'visible'});
  assert.equal(
    await nativeViewer.locator('.crump50-file-viewer-placeholder strong').textContent(),
    'Editable PowerPoint ready',
  );
  await nativeViewer.getByRole('button', {name: 'Done'}).click();

  await nativePage.evaluate(file => window.CrumpFileTools.open(file, true), nativeFiles.deck);
  const nativeResult = await nativePage.evaluate(() => window.__fixture);
  assert.deepEqual(nativeResult.downloads, [{
    href: nativeSignedUrl(nativeFiles.deck.id, true),
    target: '_blank',
    download: nativeFiles.deck.name,
  }]);
  await nativeFixture.context.close();

  assert.deepEqual(blockedRequests, []);
  assert.deepEqual(inlinePreviewRequests, [
    'mobile: /api/files/33333333-3333-4333-8333-333333333333/content',
    'desktop: /api/files/33333333-3333-4333-8333-333333333333/content',
  ]);
  assert.deepEqual(signedPreviewRequests, [
    'mobile: https://xncftwjfpjskgtwgbgci.supabase.co',
    'desktop: https://xncftwjfpjskgtwgbgci.supabase.co',
  ]);
  assert.deepEqual(nativeSignedRequests, [
    'native: /api/files/55555555-5555-4555-8555-555555555555/signed',
    'native: /api/files/66666666-6666-4666-8666-666666666666/signed',
    'native: /api/files/77777777-7777-4777-8777-777777777777/signed',
    'native: /api/files/88888888-8888-4888-8888-888888888888/signed?download=1',
  ]);
  assert.deepEqual(securityPolicyViolations, []);
  assert.deepEqual(errors, []);
  await browser.close();
  process.stdout.write(JSON.stringify({mobile: mobileResult, desktop: desktopResult, native: nativeResult, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
