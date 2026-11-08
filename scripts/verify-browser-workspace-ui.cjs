'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const ownerA = '00000000-0000-4000-8000-000000000101';
const ownerB = '00000000-0000-4000-8000-000000000102';

async function install(page) {
  const errors = [];
  const unexpectedRequests = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://www.askcrump.com/app', route => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: '<!doctype html><html data-theme="light" data-cv-shell="ready"><body class="crump-v1-body"><button data-browser-workspace-entry hidden aria-hidden="true">Browse and research</button><main id="stage"></main></body></html>',
  }));
  page.on('request', request => {
    if (request.url() !== 'https://www.askcrump.com/app') unexpectedRequests.push(request.url());
  });
  await page.goto('https://www.askcrump.com/app');
  await page.addStyleTag({path: path.join(root, 'public', 'crump-design-pass.css')});
  await page.addStyleTag({path: path.join(root, 'public', 'crump-browser-workspace-1.0.css')});
  await page.evaluate(({ownerA, ownerB}) => {
    const ids = {
      taskA: '00000000-0000-4000-8000-000000000111',
      taskB: '00000000-0000-4000-8000-000000000112',
      approval: '00000000-0000-4000-8000-000000000113',
    };
    let ownerId = ownerA;
    let revision = 0;
    let view = null;
    let randomCounter = 200;
    const scrubbers = new Map();
    const requestReceipts = new Map();
    const receiptReads = new Map();
    const tasks = new Map([
      [ownerA, []],
      [ownerB, [{
        id: ids.taskB,
        objective: 'Owner B private task',
        mode: 'research',
        status: 'paused',
        stage: 'progress',
        summary: 'Only owner B can see this.',
        progress: [], sources: [], receipts: [],
        canPause: false, canResume: true, canCancel: true,
      }]],
    ]);
    window.currentUser = {id: ownerA};
    Object.defineProperty(window.crypto, 'randomUUID', {
      configurable: true,
      value: () => `10000000-0000-4000-8000-${(randomCounter++).toString(16).padStart(12, '0')}`,
    });
    window.CrumpAuthBoundary = Object.freeze({
      authenticatedUserId: () => ownerId,
      revision: () => revision,
      register: (name, scrub) => {
        scrubbers.set(name, scrub);
        return () => scrubbers.delete(name);
      },
    });
    window.CrumpVision = Object.freeze({
      registerView(id, definition) {
        if (id !== 'browser') return false;
        view = definition;
        return true;
      },
      navigate(id) {
        if (id === 'home') {
          view?.onHide?.();
          document.getElementById('stage').replaceChildren();
          return;
        }
        if (id !== 'browser' || !view) return;
        const stage = document.getElementById('stage');
        view.render(stage);
        view.onShow?.();
      },
    });
    window.__switchBrowserOwner = nextOwner => {
      const nextUserId = String(nextOwner || '');
      revision += 1;
      scrubbers.forEach(scrub => scrub({
        reason: nextUserId ? 'authenticated-user-changed' : 'authenticated-user-cleared',
        previousUserId: ownerId,
        nextUserId,
        revision,
      }));
      ownerId = nextUserId;
      window.currentUser = nextUserId ? {id: nextUserId} : null;
    };
    let loseCreateResponse = true;
    let loseApprovalResponse = true;
    let browserReleased = true;
    let offlineRefreshes = 0;
    let malformedTasksOnce = false;
    let taskCreatePosts = 0;
    window.__setBrowserOffline = count => { offlineRefreshes = Number(count) || 0; };
    window.__setBrowserReleased = released => { browserReleased = released === true; };
    window.__patchBrowserTask = patch => {
      const current = tasks.get(ownerId) || [];
      if (!current[0]) return;
      tasks.set(ownerId, [{...current[0], ...patch}]);
    };
    window.__malformBrowserTasksOnce = () => { malformedTasksOnce = true; };
    window.__browserCreatePostCount = () => taskCreatePosts;
    window.fetch = async (url, options = {}) => {
      const pathname = new URL(url, location.origin).pathname;
      const expectedOwner = String(options.headers?.['X-Ask-Crump-Expected-Owner'] || '');
      const mutationRequestId = String(options.headers?.['X-Request-Id'] || '');
      if (!ownerId || expectedOwner !== ownerId) {
        return new Response(JSON.stringify({success: false, code: 'AUTH_OWNER_MISMATCH'}), {
          status: 409,
          headers: {'Content-Type': 'application/json'},
        });
      }
      if (offlineRefreshes > 0 && (pathname.endsWith('/status') || pathname.endsWith('/tasks'))) {
        offlineRefreshes -= 1;
        throw new TypeError('simulated transient browser refresh outage');
      }
      let payload;
      if (pathname.endsWith('/status')) {
        payload = {success: true, released: browserReleased};
      } else if (/\/requests\/[0-9a-f-]+$/.test(pathname)) {
        const receiptId = pathname.split('/').at(-1);
        const reads = receiptReads.get(receiptId) || 0;
        receiptReads.set(receiptId, reads + 1);
        payload = reads === 0
          ? {success: true, settled: false}
          : requestReceipts.get(receiptId) || {success: true, settled: false};
      } else if (pathname.endsWith('/tasks') && (options.method || 'GET') === 'GET') {
        if (malformedTasksOnce) {
          malformedTasksOnce = false;
          payload = {success: true, tasks: null};
        } else {
          payload = {success: true, tasks: tasks.get(ownerId) || []};
        }
      } else if (pathname.endsWith('/tasks') && options.method === 'POST') {
        taskCreatePosts += 1;
        const body = JSON.parse(options.body || '{}');
        const task = {
          id: ids.taskA,
          objective: body.objective,
          mode: body.mode,
          status: 'running',
          stage: 'progress',
          currentDomain: 'example.com',
          summary: 'Reviewing public sources.',
          progress: [{title: 'Opened source set', detail: 'Public pages only.'}],
          sources: [], receipts: [],
          canPause: true, canResume: false, canCancel: true,
        };
        tasks.set(ownerId, [task]);
        requestReceipts.set(mutationRequestId, {success: true, settled: true, task});
        if (loseCreateResponse) {
          loseCreateResponse = false;
          throw new TypeError('simulated create response loss after durable settlement');
        }
        payload = {success: true, task};
      } else if (/\/tasks\/[^/]+\/pause$/.test(pathname)) {
        const task = {...tasks.get(ownerId)[0], status: 'paused', canPause: false, canResume: true};
        tasks.set(ownerId, [task]);
        payload = {success: true, task};
      } else if (/\/tasks\/[^/]+\/resume$/.test(pathname)) {
        const task = {
          ...tasks.get(ownerId)[0],
          status: 'waiting_approval', stage: 'review', canPause: false, canResume: false,
          approval: {
            id: ids.approval,
            destination: 'example.com',
            action: 'Submit one prepared form',
            dataShared: 'Name and prepared message',
            account: 'No connected account',
            sideEffect: 'Creates one public form submission',
            expiresAt: '2026-11-08T18:00:00Z',
          },
        };
        tasks.set(ownerId, [task]);
        payload = {success: true, task};
      } else if (/\/approvals\/[^/]+$/.test(pathname)) {
        const task = {
          ...tasks.get(ownerId)[0],
          status: 'done', stage: 'result', approval: null,
          summary: 'Research complete with one reviewed action.',
          sources: [{title: 'Primary source', detail: 'Official documentation.', url: 'https://example.com/docs'}],
          receipts: [{action: 'Form submitted once', detail: 'Durably settled.'}],
          canPause: false, canResume: false, canCancel: false,
        };
        tasks.set(ownerId, [task]);
        requestReceipts.set(mutationRequestId, {success: true, settled: true, task});
        if (loseApprovalResponse) {
          loseApprovalResponse = false;
          throw new TypeError('simulated response loss after durable settlement');
        }
        payload = {success: true, task};
      } else {
        payload = {success: false, code: 'NOT_FOUND'};
      }
      return new Response(JSON.stringify(payload), {
        status: payload.success ? 200 : 404,
        headers: {'Content-Type': 'application/json'},
      });
    };
    window.__browserFixture = {ownerA, ownerB};
  }, {ownerA, ownerB});
  await page.addScriptTag({path: path.join(root, 'public', 'crump-browser-workspace-1.0.js')});
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('crump:body-runtime-ready')));
  await page.waitForFunction(() => document.querySelector('[data-browser-workspace-entry]')?.hidden === false);
  return {errors, unexpectedRequests};
}

async function verifyViewport(browser, viewport, fullJourney = false) {
  const page = await browser.newPage({viewport});
  const {errors, unexpectedRequests} = await install(page);
  await page.evaluate(() => window.CrumpBrowserWorkspace.open({mode: 'research'}));
  await page.waitForSelector('#cbwObjective:not([disabled])');
  const geometry = await page.evaluate(() => {
    const root = document.querySelector('.cbw-view');
    const buttons = [...root.querySelectorAll('button:not([hidden])')];
    const activeMode = root.querySelector('.cbw-mode-switch [aria-pressed="true"]');
    const inactiveMode = root.querySelector('.cbw-mode-switch [aria-pressed="false"]');
    return {
      background: getComputedStyle(root).backgroundColor,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      minimumTarget: Math.min(...buttons.map(button => button.getBoundingClientRect().height)),
      activeModeBackground: getComputedStyle(activeMode).backgroundColor,
      inactiveModeBackground: getComputedStyle(inactiveMode).backgroundColor,
    };
  });
  assert.equal(geometry.background, 'rgb(7, 10, 14)');
  assert.ok(geometry.overflow <= 1, `horizontal overflow ${geometry.overflow}px at ${viewport.width}x${viewport.height}`);
  assert.ok(geometry.minimumTarget >= 44, `small control ${geometry.minimumTarget}px at ${viewport.width}x${viewport.height}`);
  assert.notEqual(geometry.activeModeBackground, geometry.inactiveModeBackground, 'active Browser mode must be visibly selected');

  if (fullJourney) {
    await page.evaluate(() => {
      window.__setBrowserOffline(1);
      window.dispatchEvent(new Event('crump:authenticated-ready'));
    });
    await page.waitForTimeout(100);
    assert.equal(await page.locator('[data-browser-workspace-entry]').isHidden(), false);
    await page.locator('#cbwObjective').fill('Compare the official evidence');
    await page.getByRole('button', {name: 'Act', exact: true}).click();
    assert.equal(await page.locator('#cbwObjective').inputValue(), 'Compare the official evidence');
    await page.getByRole('button', {name: 'Research', exact: true}).click();
    await page.getByRole('button', {name: 'Start research'}).click();
    await page.getByText('The start request outcome is unknown. Verifying its durable request receipt before you can retry.').waitFor();
    assert.equal(await page.getByRole('button', {name: 'Verifying start…'}).isDisabled(), true);
    await page.getByRole('button', {name: 'Check verified state'}).evaluate(button => {
      button.focus();
      window.__stableReceiptControl = button;
    });
    await page.evaluate(() => window.CrumpBrowserWorkspace.refresh({quiet: true}));
    assert.equal(await page.evaluate(() => (
      window.__stableReceiptControl?.isConnected
      && document.activeElement === window.__stableReceiptControl
    )), true, 'an unchanged receipt notice must not be replaced or re-announced by polling');
    await page.locator('.cbw-form').evaluate(form => form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
    assert.equal(await page.evaluate(() => window.__browserCreatePostCount()), 1);
    await page.getByRole('button', {name: 'Pause'}).waitFor();
    assert.equal(await page.getByText(/request outcome/i).count(), 0);
    const afterCreate = await page.locator('body').innerText();
    assert.match(afterCreate, /Pause/, afterCreate);
    await page.locator('.cbw-task-row').focus();
    await page.evaluate(async () => {
      window.__patchBrowserTask({
        summary: 'Background progress advanced.',
        updatedAt: '2026-11-08T18:01:00Z',
      });
      await window.CrumpBrowserWorkspace.refresh({quiet: true});
    });
    assert.equal(
      await page.evaluate(() => document.activeElement?.dataset.cbwFocusKey),
      'task:00000000-0000-4000-8000-000000000111',
      'task sidebar focus must follow the same owner-scoped row after a targeted update',
    );
    await page.getByRole('button', {name: 'Pause'}).evaluate(button => {
      button.focus();
      window.__stableBrowserControl = button;
    });
    await page.evaluate(() => window.CrumpBrowserWorkspace.refresh({quiet: true}));
    assert.equal(await page.evaluate(() => (
      window.__stableBrowserControl?.isConnected
      && document.activeElement === window.__stableBrowserControl
    )), true, 'an unchanged background poll must not replace the focused task control');
    await page.evaluate(() => {
      window.__setBrowserOffline(1);
      void window.CrumpBrowserWorkspace.refresh({quiet: true});
    });
    await page.getByText('Browser status is temporarily unavailable. Your last verified tasks remain in place while Crump retries automatically.').waitFor();
    assert.equal(await page.getByRole('button', {name: 'Pause'}).count(), 1);
    assert.equal(await page.getByRole('button', {name: 'Retry now'}).isEnabled(), true);
    await page.waitForFunction(() => !document.body.textContent.includes('Browser status is temporarily unavailable'));
    await page.evaluate(() => {
      window.__malformBrowserTasksOnce();
      void window.CrumpBrowserWorkspace.refresh();
    });
    await page.getByText('Browser status is temporarily unavailable. Your last verified tasks remain in place while Crump retries automatically.').waitFor();
    assert.equal(await page.getByRole('button', {name: 'Pause'}).count(), 1);
    await page.waitForFunction(() => !document.body.textContent.includes('Browser status is temporarily unavailable'));
    await page.getByRole('button', {name: 'Pause'}).click();
    await page.getByRole('button', {name: 'New browser task'}).click();
    await page.locator('#cbwObjective').fill('Draft stays focused while background status changes');
    await page.locator('#cbwObjective').focus();
    await page.evaluate(async () => {
      window.__patchBrowserTask({status: 'blocked', canPause: false, canResume: false});
      await window.CrumpBrowserWorkspace.refresh({quiet: true});
    });
    assert.equal(await page.locator('#cbwObjective').inputValue(), 'Draft stays focused while background status changes');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'cbwObjective');
    assert.equal(await page.locator('.cbw-task-row').getByText('Blocked', {exact: true}).count(), 1);
    await page.evaluate(async () => {
      window.__patchBrowserTask({status: 'paused', canPause: false, canResume: true});
      await window.CrumpBrowserWorkspace.refresh({quiet: true});
    });
    assert.equal(await page.locator('#cbwObjective').inputValue(), 'Draft stays focused while background status changes');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'cbwObjective');
    await page.locator('.cbw-task-row').click();
    await page.getByRole('button', {name: 'Resume'}).click();
    await page.getByRole('heading', {name: 'Review the exact action'}).waitFor();
    await page.getByRole('button', {name: 'Approve once'}).click();
    await page.getByText('That review decision outcome is unknown. Verifying its durable receipt before you can retry or take another action.').waitFor();
    assert.equal(await page.getByRole('button', {name: 'Approve once'}).isDisabled(), true);
    await page.getByText('Browser work finished.').waitFor();
    assert.equal(await page.getByText(/review decision outcome is unknown/i).count(), 0);
    const source = page.getByRole('link', {name: /Open source/});
    assert.equal(await source.getAttribute('href'), 'https://example.com/docs');
    assert.equal(await source.getAttribute('rel'), 'noopener noreferrer');
    await page.keyboard.press('Escape');
    await page.getByRole('button', {name: 'New browser task'}).waitFor();
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'New browser task');
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'New browser task');
    await page.locator('#cbwObjective').fill('Draft survives a release-state refresh');
    await page.locator('#cbwObjective').focus();
    await page.evaluate(async () => {
      window.__setBrowserReleased(false);
      await window.CrumpBrowserWorkspace.refresh({quiet: true});
    });
    assert.equal(await page.locator('#cbwObjective').inputValue(), 'Draft survives a release-state refresh');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'cbwObjective');
    assert.equal(await page.getByRole('button', {name: 'Start research'}).isDisabled(), true);
    await page.getByText(/not released for this account yet/i).waitFor();
    await page.evaluate(async () => {
      window.__setBrowserReleased(true);
      await window.CrumpBrowserWorkspace.refresh({quiet: true});
    });
    assert.equal(await page.getByRole('button', {name: 'Start research'}).isEnabled(), true);
    await page.getByRole('button', {name: 'Act', exact: true}).click();
    await page.locator('#cbwObjective').fill('Owner A draft must not cross boundaries');
    await page.evaluate(() => { window.__staleBrowserForm = document.querySelector('.cbw-form'); });

    await page.evaluate(ownerB => window.__switchBrowserOwner(ownerB), ownerB);
    await page.waitForFunction(() => document.body.textContent.includes('Owner B private task'));
    assert.ok(!(await page.locator('body').innerText()).includes('Compare the official evidence'));
    assert.ok(!(await page.locator('body').innerText()).includes('Owner A draft must not cross boundaries'));
    await page.evaluate(() => window.__staleBrowserForm.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
    assert.equal(await page.evaluate(() => window.__browserCreatePostCount()), 1);
    await page.getByRole('button', {name: 'New browser task'}).click();
    assert.equal(await page.locator('#cbwObjective').inputValue(), '');
    assert.equal(await page.getByRole('button', {name: 'Research', exact: true}).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('button', {name: 'Start research'}).count(), 1);
    await page.locator('#cbwObjective').fill('Owner B draft must not reach guest');
    await page.evaluate(() => window.__switchBrowserOwner(''));
    await page.waitForFunction(() => document.body.textContent.includes('Sign in to use private browser work'));
    const guestText = await page.locator('body').innerText();
    assert.ok(!guestText.includes('Owner B private task'));
    assert.ok(!guestText.includes('Compare the official evidence'));
    assert.ok(!guestText.includes('Owner A draft must not cross boundaries'));
    assert.ok(!guestText.includes('Owner B draft must not reach guest'));
    assert.equal(await page.locator('[data-browser-workspace-entry]').isHidden(), true);
  }

  assert.deepEqual(errors, []);
  assert.deepEqual(unexpectedRequests, []);
  await page.close();
  return geometry;
}

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  for (const viewport of [
    {width: 390, height: 500},
    {width: 390, height: 844},
    {width: 1024, height: 1366},
    {width: 1440, height: 900},
  ]) {
    results.push({viewport, geometry: await verifyViewport(browser, viewport, viewport.height === 844)});
  }
  await browser.close();
  process.stdout.write(JSON.stringify({results}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
