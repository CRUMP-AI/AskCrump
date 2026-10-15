/* Local synthetic fixture only. No backend, worker, or paid API is started. */
const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile, mkdir} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const allowed = new Map([
  ['/', 'tests/fixtures/autonomous-workbench.html'],
  ['/fixture.html', 'tests/fixtures/autonomous-workbench.html'],
  ['/crump-code-5.9.35.js', 'public/crump-code-5.9.35.js'],
  ['/crump-code-5.9.35.css', 'public/crump-code-5.9.35.css'],
  ['/crump-design-pass.css', 'public/crump-design-pass.css'],
]);
const types = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css'};

async function startServer() {
  const unexpected = [];
  const server = createServer(async (req, res) => {
    const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; font-src 'self'; object-src 'none'; base-uri 'none'");
    const relative = allowed.get(pathname);
    if (!relative || req.method !== 'GET') {
      unexpected.push(`${req.method} ${pathname}`); res.writeHead(404); res.end('Local fixture route not found'); return;
    }
    try {
      const body = await readFile(path.join(root, relative));
      res.writeHead(200, {'Content-Type': `${types[path.extname(relative)]}; charset=utf-8`}); res.end(body);
    } catch (error) { res.writeHead(500); res.end('Fixture asset unavailable'); }
  });
  const requested = process.argv.find(arg => arg.startsWith('--port='));
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(requested ? Number(requested.split('=')[1]) : 0, '127.0.0.1', resolve); });
  return {server, unexpected, url: `http://127.0.0.1:${server.address().port}/fixture.html`};
}

async function run({url, unexpected}) {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
  const page = await context.newPage();
  const errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== new URL(url).origin) { external.push(route.request().url()); return route.abort(); }
    return route.continue();
  });
  const visit = async query => { await page.goto(`${url}?${query}`, {waitUntil: 'networkidle'}); await page.waitForFunction(() => window.fixtureReady); };
  const results = [];
  try {
    for (const access of ['disabled', 'locked']) {
      await visit(`access=${access}`);
      assert.equal(await page.locator('#crumpCodeWorkspace').isHidden(), true, `${access} hardlock`);
      assert.equal(await page.evaluate(() => fixture.requests.some(item => item.path === '/api/projects')), false, 'Unavailable accounts must not load project data');
    }
    results.push('configured/entitled hardlock');

    await visit('scenario=completed');
    const selectedReads = await page.evaluate(() => fixture.requests.filter(item => item.path === '/api/code/tasks/fixture-task-001').length);
    await page.locator('[data-crump-code-task="fixture-task-001"]').click();
    await page.waitForFunction(count => fixture.requests.filter(item => item.path === '/api/code/tasks/fixture-task-001').length > count, selectedReads);
    assert.equal(await page.locator('[data-crump-code-task="fixture-task-001"]').getAttribute('aria-current'), 'true');

    await visit('scenario=queued');
    assert.equal(await page.locator('#crumpCodeRun').isDisabled(), true);
    await page.locator('#crumpCodeRunConfirmed').check();
    await page.locator('#crumpCodeRun').click();
    await page.waitForFunction(() => fixture.requests.some(item => item.path.endsWith('/run')));
    assert.deepEqual(await page.evaluate(() => fixture.requests.find(item => item.path.endsWith('/run')).body), {confirmed: true});
    await page.waitForFunction(() => document.querySelector('.crump-code-progress-status')?.textContent === 'Working in isolated copy');

    await visit('scenario=running');
    await page.locator('[data-code-action="cancel"]').click();
    await page.waitForFunction(() => document.querySelector('.crump-code-progress-status')?.textContent === 'Cancelled');
    assert.deepEqual(await page.evaluate(() => fixture.requests.find(item => item.path.endsWith('/cancel')).body), {});
    results.push('explicit final run confirmation / actual API contract');

    await visit('scenario=queued');
    await page.evaluate(async () => { fixture.task.payment_source = 'fixture-reserved'; await CrumpCodeWorkspace.open(); });
    await page.locator('#crumpCodeRunConfirmed').check();
    await page.locator('#crumpCodeRun').focus();
    await page.evaluate(() => fixture.pollUpdate({objective: 'A changed brief must be reviewed again.'}));
    await page.waitForFunction(() => document.querySelector('#crumpCodeTaskHeading')?.textContent === 'A changed brief must be reviewed again.');
    assert.equal(await page.locator('#crumpCodeRunConfirmed').isChecked(), false);
    assert.equal(await page.locator('#crumpCodeRun').isDisabled(), true);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'crumpCodeTaskHeading');
    results.push('changed run boundary resets confirmation with safe focus fallback');

    await visit('scenario=approval');
    await page.evaluate(() => {
      fixture.task.events = Array.from({length: 24}, (_, i) => ({event_type: `fixture.step.${i}`, created_at: '2026-10-15T15:30:00Z'}));
      fixture.pollUpdate();
    });
    await page.waitForFunction(() => document.querySelector('.crump-code-history summary')?.textContent.includes('(24)'));
    await page.locator('.crump-code-history summary').click();
    await page.locator('[data-code-decision="approved"]').focus();
    const beforeScroll = await page.evaluate(() => { const node = document.querySelector('.crump-code-main'); node.scrollTop = 140; return node.scrollTop; });
    await page.evaluate(() => {
      fixture.task.approvals[0].details = 'Updated synthetic boundary details during a poll.';
      fixture.task.events.push({event_type: 'fixture.poll.changed', created_at: '2026-10-15T15:31:00Z'});
      fixture.pollUpdate();
    });
    await page.waitForFunction(() => document.querySelector('.crump-code-history summary')?.textContent.includes('(25)'));
    assert.deepEqual(await page.evaluate(() => ({focus: document.activeElement.dataset.codeDecision, open: document.querySelector('.crump-code-history').open, scroll: document.querySelector('.crump-code-main').scrollTop})), {focus: 'approved', open: true, scroll: beforeScroll});
    const unchanged = await page.evaluate(() => {
      window.fixtureRetainedButton = document.querySelector('[data-code-decision="approved"]');
      window.dispatchEvent(new Event('online')); return fixture.requests.length;
    });
    await page.waitForFunction(count => fixture.requests.length > count, unchanged);
    assert.equal(await page.evaluate(() => fixtureRetainedButton === document.querySelector('[data-code-decision="approved"]')), true, 'Unchanged polls retain the same DOM');
    await page.locator('[data-code-decision="approved"]').focus();
    await page.evaluate(() => fixture.pollUpdate({status: 'running', approvals: []}));
    await page.waitForFunction(() => !document.querySelector('[data-code-decision="approved"]'));
    assert.equal(await page.evaluate(() => document.activeElement.id), 'crumpCodeTaskHeading');
    results.push('changed and unchanged polling preserves focus / disclosure / scroll');

    await visit('scenario=approval');
    await page.evaluate(() => { fixture.holdApproval = true; fixture.rejectApproval = true; });
    await page.locator('[data-code-decision="approved"]').click();
    await page.waitForFunction(() => typeof fixture.releaseApproval === 'function');
    await page.evaluate(() => {
      fixture.task.events.push({event_type: 'fixture.poll.during.approval', created_at: '2026-10-15T15:31:00Z'});
      fixture.pollUpdate();
    });
    await page.waitForFunction(() => document.querySelector('.crump-code-history summary')?.textContent.includes('(3)'));
    assert.equal(await page.locator('[data-code-decision="approved"]').isDisabled(), true);
    assert.equal(await page.locator('[data-code-decision="denied"]').isDisabled(), true);
    assert.equal(await page.locator('[data-code-decision="approved"]').textContent(), 'Approving…');
    await page.evaluate(() => fixture.releaseApproval());
    await page.waitForFunction(() => document.querySelector('#crumpCodeNotice')?.textContent.includes('Synthetic approval request failed'));
    assert.equal(await page.locator('[data-code-decision="approved"]').isDisabled(), false);
    assert.equal(await page.locator('[data-code-decision="denied"]').isDisabled(), false);
    assert.equal(await page.locator('[data-code-decision="approved"]').textContent(), 'Approve bounded retry');
    assert.equal(await page.evaluate(() => fixture.requests.filter(item => item.method === 'POST').length), 1);
    results.push('pending approval survives changed poll / failure restores live controls');

    await visit('scenario=running');
    await page.evaluate(() => { fixture.failNextTaskReads = 1; window.dispatchEvent(new Event('online')); });
    await page.waitForFunction(() => document.querySelector('#crumpCodeNotice')?.textContent.includes('current task status is not confirmed'));
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.waitForFunction(() => document.querySelector('#crumpCodeNotice')?.textContent === 'Connection restored. Task status is up to date.');
    results.push('poll failure uses uncertain status / online recovery clears stale delay');

    await visit('scenario=completed');
    assert.match(await page.locator('.crump-code-outcome strong').textContent(), /Reported checks passed/);
    // Active tasks can deliver a partial patch; terminal tasks correctly stop polling.
    await visit('scenario=approval');
    assert.equal(await page.locator('.crump-code-file').count(), 2);
    assert.equal(await page.locator('.crump-code-diff img').count(), 0);
    assert.equal(await page.evaluate(() => window.fixtureXss === true), false);
    assert.match(await page.locator('.crump-code-diff').first().textContent(), /<img src=x/);
    await page.locator('.crump-code-file').first().locator('summary').click();
    await page.locator('.crump-code-file').first().locator('summary').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelectorAll('.crump-code-file > summary')[1]), true, 'Closed details descendants must not enter the tab sequence');
    await page.locator('.crump-code-file').last().locator('summary').click();
    await page.locator('.crump-code-diff').last().focus();
    await page.evaluate(() => { document.querySelectorAll('.crump-code-diff')[1].scrollTop = 200; fixture.task.result_summary += '\nA synthetic status update.'; fixture.pollUpdate(); });
    await page.waitForFunction(() => document.querySelector('.crump-code-summary')?.textContent.includes('A synthetic status update.'));
    assert.equal(await page.locator('.crump-code-file').last().evaluate(node => node.open), true);
    assert.equal(await page.locator('.crump-code-diff').last().evaluate(node => node.scrollTop), 200);
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelectorAll('.crump-code-diff')[1]), true);
    results.push('safe text, file-oriented diff / closed-details keyboard / nested scroll');

    await visit('scenario=patch-edge');
    assert.deepEqual(await page.locator('.crump-code-file-name').allTextContents(), ['format.txt', 'second.txt']);
    assert.equal(await page.locator('.crump-code-file-counts').first().textContent(), '+1 / −1');
    assert.equal(await page.locator('.crump-code-diff-line.is-added code').first().textContent(), '+++ replacement heading');
    assert.equal(await page.locator('.crump-code-diff-line.is-removed code').first().textContent(), '--- previous heading');
    assert.deepEqual(await page.locator('.crump-code-file').last().locator('.is-removed .crump-code-line-number').allTextContents(), ['4', '']);
    assert.deepEqual(await page.locator('.crump-code-file').last().locator('.is-added .crump-code-line-number').allTextContents(), ['', '9']);
    await page.locator('#crumpCodePrepare').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.fixtureControl), 'scenario');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'crumpCodePrepare');
    await page.locator('[data-code-pane-target="brief"]').click();
    await page.locator('.crump-code-diff').first().focus();
    await page.setViewportSize({width: 390, height: 950});
    await page.waitForFunction(() => document.querySelector('[data-code-pane-target="review"]')?.getAttribute('aria-current') === 'step');
    assert.equal(await page.locator('[data-code-pane="review"]').isVisible(), true);
    assert.equal(await page.evaluate(() => document.activeElement.classList.contains('crump-code-diff')), true);
    await page.setViewportSize({width: 1440, height: 1000});
    results.push('hunk header-like content / exact line numbers / focus wrap / responsive focus');

    await visit('scenario=unknown');
    assert.equal(await page.locator('.crump-code-check > span').textContent(), 'Not reported');
    assert.equal(await page.locator('.crump-code-outcome strong').textContent(), 'Verification incomplete');
    await page.evaluate(async () => { fixture.task.verification = [null, {command: 'synthetic check', returnCode: 0}]; await CrumpCodeWorkspace.open(); });
    assert.equal(await page.locator('.crump-code-outcome strong').textContent(), 'Verification incomplete');
    await visit('scenario=failed');
    assert.equal(await page.locator('.crump-code-check > span').textContent(), 'Exited 1');
    assert.equal(await page.locator('.crump-code-outcome strong').textContent(), 'The run stopped');
    results.push('null check codes and failed runs are not presented as verified');

    await visit('scenario=oversize');
    assert.equal(await page.locator('.crump-code-preview-limit').count(), 1);
    assert.ok(await page.locator('.crump-code-diff-line').count() <= 1600);
    const original = await page.evaluate(() => fixture.task.result_patch);
    const downloadEvent = page.waitForEvent('download');
    await page.locator('[data-code-action="download"]').click();
    const download = await downloadEvent;
    const stream = await download.createReadStream(), chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    assert.equal(Buffer.concat(chunks).toString('utf8'), original, 'Download must retain the entire original patch');
    results.push('bounded large-patch DOM / byte-complete original download');

    await visit('scenario=completed');
    await page.addScriptTag({path: require.resolve('axe-core/axe.min.js')});
    const checkAccessibility = async label => {
      const accessibility = await page.evaluate(async () => axe.run(document.querySelector('.crump-code-shell'), {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag22aa']}}));
      assert.deepEqual(accessibility.violations.map(item => ({id: item.id, impact: item.impact, targets: item.nodes.map(node => node.target)})), [], label);
    };
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({width, height: 950});
        if (width < 821) {
          for (const pane of ['brief', 'progress', 'review']) {
            await page.locator(`[data-code-pane-target="${pane}"]`).click();
            const visible = await page.locator('[data-code-pane]').evaluateAll(nodes => nodes.filter(node => !node.hidden).map(node => node.dataset.codePane));
            assert.ok(visible.length && visible.every(value => value === pane), `${width}px ${pane} pane`);
            await checkAccessibility(`${theme} ${width}px ${pane} accessibility`);
          }
        }
        const overflow = await page.locator('.crump-code-shell').evaluate(node => node.scrollWidth > node.clientWidth + 1);
        assert.equal(overflow, false, `${theme} ${width}px shell must fit`);
        if (width > 820) await checkAccessibility(`${theme} ${width}px accessibility`);
      }
    }
    results.push('light/dark / desktop + 390px + 320px workflow / WCAG axe checks');
    const artifactDirectory = path.join(root, 'artifacts', 'autonomous-workbench');
    await mkdir(artifactDirectory, {recursive: true});
    const screenshots = [];
    for (const view of [
      {name: 'desktop-review.png', width: 1440, height: 1000, theme: 'light'},
      {name: 'mobile-390-dark-review.png', width: 390, height: 1000, theme: 'dark'},
    ]) {
      await page.setViewportSize({width: view.width, height: view.height});
      await page.locator('[data-fixture-control="theme"]').selectOption(view.theme);
      await page.locator('[data-code-pane-target="review"]').click();
      await page.locator('.crump-code-patch').evaluate(node => node.scrollIntoView({block: 'start', behavior: 'instant'}));
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const framing = await page.evaluate(() => {
        const banner = document.querySelector('.fixture-banner').getBoundingClientRect();
        const patch = document.querySelector('.crump-code-patch-head').getBoundingClientRect();
        const diff = document.querySelector('.crump-code-diff').getBoundingClientRect();
        return {bannerVisible: banner.top >= 0 && banner.bottom <= innerHeight, patchVisible: patch.top >= banner.bottom && patch.bottom < innerHeight, diffVisible: diff.top < innerHeight - 60 && diff.bottom > patch.bottom};
      });
      assert.deepEqual(framing, {bannerVisible: true, patchVisible: true, diffVisible: true}, `${view.name} must show fixture disclosure and actual patch review`);
      const screenshotPath = path.join(artifactDirectory, view.name);
      await page.screenshot({path: screenshotPath, fullPage: false});
      screenshots.push(screenshotPath);
    }
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#crumpCodeWorkspace').isHidden(), true);
    assert.deepEqual(await page.evaluate(() => fixture.blocked), []);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    return {passed: results, screenshots, fixtureOnly: true, externalRequests: 0, paidExecutions: 0};
  } finally { await context.close(); await browser.close(); }
}

(async () => {
  const fixture = await startServer();
  if (process.argv.includes('--serve')) {
    console.log(`Local test fixture — no paid execution: ${fixture.url}`);
    console.log('Optional query: ?scenario=approval&theme=dark (completed, queued, running, approval, failed, cancelled, unknown, oversize).');
    console.log('Loopback only. No browser opened. Stop with Ctrl+C.');
    return;
  }
  try { console.log(JSON.stringify(await run(fixture), null, 2)); }
  finally { await new Promise(resolve => fixture.server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
