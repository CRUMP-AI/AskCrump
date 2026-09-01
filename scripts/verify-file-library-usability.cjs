const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];

  for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
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
    await page.close();
  }

  assert.deepEqual(errors, []);
  await browser.close();
  process.stdout.write(JSON.stringify({viewports: ['1440x1000', '390x844'], errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
