const assert = require('node:assert/strict');
const { chromium } = require('playwright');

function blankPdf() {
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R >>',
    '<< /Length 0 >>\nstream\n\nendstream',
  ];
  objects.forEach((body, index) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) pdf += `${String(offset).padStart(10, '0')} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf);
}

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];

  for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    const blockedRequests = [];
    let pdfContentRequests = 0;
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      // Chromium's built-in PDF viewer loads chrome:// and chrome-extension://
      // resources after the local PDF response. Those are browser internals, not
      // outbound network destinations; keep the exfiltration assertion scoped to
      // HTTP(S) requests that can actually leave the fixture origin.
      if (!['http:', 'https:'].includes(url.protocol)) return route.continue();
      if (url.hostname !== '127.0.0.1') {
        blockedRequests.push(url.href);
        return route.abort();
      }
      if (url.pathname === '/api/files/file-extra-01/content') {
        pdfContentRequests += 1;
        return route.fulfill({status: 200, contentType: 'application/pdf', body: blankPdf()});
      }
      if (url.pathname.startsWith('/api/')) {
        blockedRequests.push(url.href);
        return route.abort();
      }
      return route.continue();
    });
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765/tests/fixtures/file-library-usability.html', {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => Boolean(window.CrumpProduct53));
    await page.evaluate(() => window.CrumpProduct53.openFiles());

    const dialog = page.getByRole('dialog', {name: 'Ask Crump Files'});
    await dialog.waitFor({state: 'visible'});
    const search = dialog.getByRole('searchbox', {name: 'Search files'});
    const sort = dialog.getByRole('combobox', {name: 'Sort'});
    assert.equal(await search.isVisible(), true);
    assert.equal(await sort.isVisible(), true);
    assert.deepEqual(await dialog.locator('[data-library-filter]').allTextContents(), [
      'All (15)', 'Videos (1)', 'Images (1)', 'Documents (13)',
    ]);
    assert.deepEqual(await dialog.locator('[data-library-file]').evaluateAll(elements => elements.map(element => element.dataset.libraryFile)), [
      'file-image', 'file-video', 'file-pitch', 'file-resume',
      'file-extra-01', 'file-extra-02', 'file-extra-03', 'file-extra-04',
      'file-extra-05', 'file-extra-06', 'file-extra-07', 'file-extra-08',
    ]);
    assert.match(await dialog.locator('#crump53LibraryStatus').textContent(), /Showing 12 of 15 saved items/);
    const more = dialog.locator('#crump53LibraryMore');
    assert.equal(await more.isVisible(), true);
    assert.equal(await more.textContent(), 'Show 3 more files');
    await more.click();
    assert.equal(await dialog.locator('[data-library-file]').count(), 15);
    assert.equal(await more.isVisible(), false);

    await search.fill('resume');
    assert.deepEqual(await dialog.locator('[data-library-file]').evaluateAll(elements => elements.map(element => element.dataset.libraryFile)), ['file-resume']);
    assert.match(await dialog.locator('#crump53LibraryStatus').textContent(), /1 of 15 saved items match/);
    assert.equal(await more.isVisible(), false);

    await search.fill('no-such-file');
    assert.equal(await dialog.locator('.crump53-library-empty').textContent(), 'No files match your search.');
    await search.fill('');

    const imageFilter = dialog.locator('[data-library-filter="image"]');
    await imageFilter.click();
    assert.equal(await imageFilter.getAttribute('aria-pressed'), 'true');
    assert.equal(await dialog.locator('[data-library-filter="all"]').getAttribute('aria-pressed'), 'false');
    assert.deepEqual(await dialog.locator('[data-library-file]').evaluateAll(elements => elements.map(element => element.dataset.libraryFile)), ['file-image']);

    await dialog.locator('[data-library-filter="all"]').click();
    await sort.selectOption('name');
    assert.deepEqual((await dialog.locator('[data-library-file]').evaluateAll(elements => elements.map(element => element.dataset.libraryFile))).slice(0, 4), [
      'file-image', 'file-video', 'file-pitch', 'file-resume',
    ]);
    await sort.selectOption('oldest');
    assert.deepEqual((await dialog.locator('[data-library-file]').evaluateAll(elements => elements.map(element => element.dataset.libraryFile))).slice(0, 3), [
      'file-extra-11', 'file-extra-10', 'file-extra-09',
    ]);

    await search.fill('pitch');
    await imageFilter.click();
    await dialog.getByRole('button', {name: 'Close'}).click();
    await page.evaluate(() => window.CrumpProduct53.openFiles());
    await dialog.waitFor({state: 'visible'});
    await page.waitForFunction(() => document.querySelectorAll('[data-library-file]').length === 12);
    assert.equal(await search.evaluate(element => element.value), '');
    assert.equal(await dialog.locator('[data-library-filter="all"]').getAttribute('aria-pressed'), 'true');
    assert.equal(await dialog.locator('[data-library-filter="image"]').getAttribute('aria-pressed'), 'false');
    assert.equal(await sort.evaluate(element => element.value), 'oldest');
    assert.equal(await dialog.locator('[data-library-file]').count(), 12);
    assert.equal(await more.isVisible(), true);

    const layout = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      searchFontSize: getComputedStyle(document.getElementById('crump53LibrarySearch')).fontSize,
      dialogHeight: document.getElementById('crump53Sheet').getBoundingClientRect().height,
      viewportHeight: window.innerHeight,
    }));
    assert.ok(layout.documentWidth <= layout.viewportWidth, `horizontal overflow at ${viewport.width}px`);
    assert.ok(layout.dialogHeight <= layout.viewportHeight, `dialog overflow at ${viewport.width}px`);
    if (viewport.width === 390) assert.equal(layout.searchFontSize, '16px');

    // Files must delegate PDF Open and Download to the real private file viewer.
    await page.waitForFunction(() => document.documentElement.dataset.crump50Booted === 'true');
    await search.fill('Z Archive 01');
    const pdfFile = dialog.locator('[data-library-file="file-extra-01"]');
    await pdfFile.waitFor({state: 'visible'});
    const previewResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/files/file-extra-01/content');
    await pdfFile.locator('[data-library-open]').click();
    const viewer = page.locator('.crump50-file-viewer');
    await viewer.waitFor({state: 'visible'});
    assert.equal(await viewer.locator('iframe').getAttribute('src'), '/api/files/file-extra-01/content');
    assert.equal(await viewer.locator('iframe').getAttribute('title'), 'Preview Z Archive 01.pdf');
    assert.equal((await previewResponse).status(), 200);
    assert.ok(pdfContentRequests > 0, 'PDF preview must request only the synthetic local content route');
    await viewer.getByRole('button', {name: 'Download'}).click();
    await viewer.getByRole('button', {name: 'Done'}).click();
    await pdfFile.locator('[data-library-download]').click();
    assert.deepEqual(await page.evaluate(() => window.__fileDelivery), {
      downloads: [
        {href: '/api/files/file-extra-01/content?download=1', target: '_self', download: 'Z Archive 01.pdf'},
        {href: '/api/files/file-extra-01/content?download=1', target: '_self', download: 'Z Archive 01.pdf'},
      ],
      openedWindows: 0,
    });
    assert.deepEqual(blockedRequests, []);
    await page.close();
  }

  assert.deepEqual(errors, []);
  await browser.close();
  process.stdout.write(JSON.stringify({viewports: ['1440x1000', '390x844'], errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
