const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || process.env.CODEX_BROWSER_EXECUTABLE
  || undefined;

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];

  for (const viewport of [
    {name: 'desktop', width: 1280, height: 760},
    {name: 'phone', width: 390, height: 844},
  ]) {
    for (const destination of ['existing', 'new']) {
      const page = await browser.newPage({viewport});
      const browserErrors = [];
      page.on('console', message => {
        if (message.type() === 'error') browserErrors.push(message.text());
      });
      page.on('pageerror', error => browserErrors.push(error.message));
      const query = destination === 'new' ? '?target=new&file=slow' : '?file=slow';
      await page.goto(`${baseUrl}/tests/fixtures/project-target-disclosure.html${query}`, {
        waitUntil: 'networkidle',
      });
      await page.waitForFunction(expected => {
        const button = document.querySelector('[data-artifact-project]');
        const target = window.CrumpProduct53?.projectTarget?.();
        return button?.textContent === 'Keep in a Project'
          && (expected === 'new' ? !target?.id : Boolean(target?.id));
      }, destination);

      const button = page.locator('[data-artifact-project]');
      assert.equal(await button.getAttribute('aria-label'),
        'Keep Website launch checklist and its source conversation together in a private Project');
      await button.click();
      await page.waitForFunction(() => document.querySelector('[data-artifact-project]')?.textContent === 'Saving…');
      const pending = await page.evaluate(() => ({
        label: document.querySelector('[data-artifact-project]')?.textContent || '',
        busy: document.querySelector('[data-artifact-project]')?.getAttribute('aria-busy') || '',
        status: document.querySelector('.crump50-artifact small')?.textContent || '',
      }));
      await page.waitForFunction(() => document.querySelector('[data-artifact-project]')?.textContent === 'Open Project');
      const completed = await page.evaluate(() => ({
        label: document.querySelector('[data-artifact-project]')?.textContent || '',
        busy: document.querySelector('[data-artifact-project]')?.getAttribute('aria-busy'),
        status: document.querySelector('.crump50-artifact small')?.textContent || '',
        requests: window.__fixture.requests,
        analytics: window.__fixture.analytics,
        unexpectedRequests: window.__fixture.unexpectedRequests,
        fixtureErrors: Number(document.querySelector('#fixtureErrors')?.textContent || 0),
      }));

      assert.deepEqual(pending, {
        label: 'Saving…',
        busy: 'true',
        status: 'Saving file and conversation privately…',
      });
      assert.equal(completed.label, 'Open Project');
      assert.equal(completed.busy, null);
      assert.equal(completed.status, 'Created by Crump · Saved in Project');
      assert.deepEqual(completed.analytics, [{
        eventName: 'ProjectSaveIntentReached',
        values: {
          eventKey: 'project-save-intent',
          source: destination === 'new' ? 'new_project' : 'existing_project',
        },
      }]);
      assert.equal(completed.requests.length, 2);
      assert.equal(
        completed.requests[0].destination,
        destination === 'new' ? 'new' : '00000000-0000-4000-8000-000000000062',
      );
      assert.equal(
        completed.requests[1].destination,
        destination === 'new'
          ? 'new:file'
          : '00000000-0000-4000-8000-000000000062:file',
      );
      assert.equal(completed.requests[0].body.continuitySource, undefined);
      assert.equal(completed.requests[1].body.role, 'generated_document');
      assert.equal(completed.requests[1].body.continuitySource, 'result_action');
      assert.equal(completed.unexpectedRequests, 0);
      assert.equal(completed.fixtureErrors, 0);
      assert.deepEqual(browserErrors, []);

      await button.click();
      await page.locator('#crump53Studio').waitFor({state: 'visible'});
      const opened = await page.evaluate(() => {
        const dialog = document.querySelector('#crump53Sheet');
        const studio = document.querySelector('#crump53Studio');
        return {
          studioHidden: studio?.hidden ?? null,
          dialogLabel: dialog?.getAttribute('aria-label') || '',
          heading: document.querySelector('#crump53ProjectWorkspaceName')?.textContent || '',
          opened: document.querySelector('#fixtureOpened')?.textContent || '',
        };
      });
      assert.equal(opened.studioHidden, false);
      assert.equal(
        opened.dialogLabel,
        destination === 'new'
          ? 'Ask Crump Project: Website launch checklist'
          : 'Ask Crump Project: Q3 Finance Forecast',
      );
      assert.equal(
        opened.heading,
        destination === 'new' ? 'Website launch checklist' : 'Q3 Finance Forecast',
      );
      await page.waitForFunction(() => document.querySelector('#fixtureOpened')?.textContent.startsWith('Opened '));
      assert.equal(await page.locator('#fixtureErrors').textContent(), '0');
      assert.equal((await page.evaluate(() => window.__fixture.unexpectedRequests)), 0);
      assert.deepEqual(browserErrors, []);

      results.push({viewport: viewport.name, destination, pending, completed, opened, browserErrors});
      await page.close();
    }
  }

  await browser.close();
  process.stdout.write(`${JSON.stringify({runs: results.length, results})}\n`);
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
