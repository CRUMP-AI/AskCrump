const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE
    || process.env.ASK_CRUMP_BROWSER_PATH
    || process.env.CODEX_BROWSER_EXECUTABLE
    || undefined;
  const origin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];

  async function openScenario(scenario) {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    page.on('console', message => {
      if (message.type() === 'error') errors.push(`${scenario}: ${message.text()}`);
    });
    page.on('pageerror', error => errors.push(`${scenario}: ${error.message}`));
    await page.goto(`${origin}/tests/fixtures/project-vision-resume.html?scenario=${scenario}`, {
      waitUntil: 'domcontentloaded',
    });
    await page.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'}).waitFor();
    return page;
  }

  const samePage = await openScenario('same');
  const sameButton = samePage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'});
  assert.equal(await sameButton.getAttribute('type'), 'button');
  const sameBox = await sameButton.boundingBox();
  assert.ok(sameBox && sameBox.height >= 44, `Expected a 44px touch target, received ${sameBox?.height}.`);
  assert.ok(sameBox.x >= 0 && sameBox.x + sameBox.width <= 390, 'Continue action overflowed the phone viewport.');
  await sameButton.focus();
  await samePage.keyboard.press('Enter');
  await samePage.waitForFunction(() => window.__fixture.events.length === 1);
  await samePage.waitForFunction(() => document.activeElement?.id === 'userInput');
  const same = await samePage.evaluate(() => ({
    actions: window.__fixture.actions,
    currentChatId: window.currentChatId,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    syncCalls: window.__fixture.syncCalls,
    overflow: document.documentElement.scrollWidth > window.innerWidth,
  }));
  assert.equal(same.syncCalls, 0);
  assert.deepEqual(same.loadCalls, ['33333333-3333-4333-8333-333333333333']);
  assert.deepEqual(same.navigations, ['ask']);
  assert.equal(same.currentChatId, '33333333-3333-4333-8333-333333333333');
  assert.deepEqual(same.actions, [
    'load:33333333-3333-4333-8333-333333333333',
    'navigate:ask',
    'track',
  ]);
  assert.deepEqual(same.events, [{
    name: 'RecentWorkResumed',
    detail: {eventKey: 'recent-work-resumed', source: 'project'},
  }]);
  assert.equal(same.overflow, false);
  const serializedEvent = JSON.stringify(same.events);
  assert.equal(serializedEvent.includes('Supervisor launch plan'), false);
  assert.equal(serializedEvent.includes('33333333-3333-4333-8333-333333333333'), false);

  const preClickPage = await openScenario('same');
  const preClickButton = preClickPage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'});
  const staleButtonHandle = await preClickButton.elementHandle();
  assert.ok(staleButtonHandle);
  await preClickPage.evaluate(() => window.__fixture.switchOwner());
  await preClickPage.getByRole('button', {name: 'Continue “Owner B handoff” in Ask'}).waitFor();
  await staleButtonHandle.evaluate(button => button.click());
  await preClickPage.waitForTimeout(25);
  const preClickOwnerSwitch = await preClickPage.evaluate(() => ({
    actions: window.__fixture.actions,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    rootText: document.getElementById('fixtureRoot').textContent,
    toasts: window.__fixture.toasts,
  }));
  assert.deepEqual(preClickOwnerSwitch.actions, []);
  assert.deepEqual(preClickOwnerSwitch.events, []);
  assert.deepEqual(preClickOwnerSwitch.loadCalls, []);
  assert.deepEqual(preClickOwnerSwitch.navigations, []);
  assert.deepEqual(preClickOwnerSwitch.toasts, []);
  assert.equal(preClickOwnerSwitch.rootText.includes('Supervisor launch plan'), false);
  assert.equal(preClickOwnerSwitch.rootText.includes('A private continuation fixture.'), false);
  assert.ok(preClickOwnerSwitch.rootText.includes('Owner B Project'));

  await preClickPage.getByRole('button', {name: 'Continue “Owner B handoff” in Ask'}).click();
  await preClickPage.waitForFunction(() => window.__fixture.events.length === 1);
  const ownerBReopen = await preClickPage.evaluate(() => ({
    actions: window.__fixture.actions,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    currentChatId: window.currentChatId,
  }));
  assert.deepEqual(ownerBReopen.loadCalls, ['bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb']);
  assert.deepEqual(ownerBReopen.navigations, ['ask']);
  assert.equal(ownerBReopen.currentChatId, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
  assert.deepEqual(ownerBReopen.events, [{
    name: 'RecentWorkResumed',
    detail: {eventKey: 'recent-work-resumed', source: 'project'},
  }]);

  const syncPage = await openScenario('sync');
  await syncPage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'}).click();
  await syncPage.waitForFunction(() => window.__fixture.events.length === 1);
  const synced = await syncPage.evaluate(() => ({
    actions: window.__fixture.actions,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    syncCalls: window.__fixture.syncCalls,
  }));
  assert.equal(synced.syncCalls, 1);
  assert.deepEqual(synced.actions, [
    'sync',
    'load:33333333-3333-4333-8333-333333333333',
    'navigate:ask',
    'track',
  ]);
  assert.equal(synced.loadCalls.length, 1);
  assert.deepEqual(synced.navigations, ['ask']);
  assert.deepEqual(synced.events, [{
    name: 'RecentWorkResumed',
    detail: {eventKey: 'recent-work-resumed', source: 'project'},
  }]);

  const failurePage = await openScenario('failure');
  const failureButton = failurePage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'});
  await failureButton.click();
  await failurePage.waitForFunction(() => window.__fixture.toasts.length === 1);
  const failure = await failurePage.evaluate(() => ({
    actions: window.__fixture.actions,
    currentChatId: window.currentChatId,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    syncCalls: window.__fixture.syncCalls,
    toasts: window.__fixture.toasts,
    projectVisible: Boolean(document.querySelector('.cvp-project-head')),
    button: {
      busy: document.querySelector('[data-cvp-chat]')?.getAttribute('aria-busy'),
      disabled: document.querySelector('[data-cvp-chat]')?.disabled,
      text: document.querySelector('[data-cvp-chat]')?.textContent,
    },
  }));
  assert.equal(failure.syncCalls, 1);
  assert.deepEqual(failure.actions, ['sync']);
  assert.deepEqual(failure.loadCalls, []);
  assert.deepEqual(failure.navigations, []);
  assert.deepEqual(failure.events, []);
  assert.equal(failure.currentChatId, '');
  assert.equal(failure.projectVisible, true);
  assert.deepEqual(failure.button, {busy: null, disabled: false, text: 'Continue'});
  assert.deepEqual(failure.toasts, [{
    message: 'That conversation could not be restored on this device yet. Your Project is still here—try again.',
    type: 'error',
  }]);

  const staleCases = [];
  for (const staleKind of ['owner', 'logout', 'project']) {
    const stalePage = await openScenario('pending');
    const staleButton = stalePage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'});
    await staleButton.click();
    await stalePage.waitForFunction(() => window.__fixture.syncCalls === 1);
    assert.equal(await staleButton.isDisabled(), true);
    assert.equal(await staleButton.getAttribute('aria-busy'), 'true');
    await stalePage.evaluate(() => {
      document.querySelector('[data-cvp-chat]').click();
      document.querySelector('[data-cvp-chat]').click();
    });
    assert.equal(await stalePage.evaluate(() => window.__fixture.syncCalls), 1);
    await stalePage.evaluate(kind => {
      if (kind === 'owner') window.__fixture.switchOwner();
      else if (kind === 'logout') window.__fixture.switchOwner('');
      else document.getElementById('cvpProjectDetail').dataset.cvpActiveProject = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
      window.__fixture.resolveSync();
    }, staleKind);
    await stalePage.waitForFunction(() => document.querySelector('[data-cvp-chat]')?.dataset.cvpOpening !== 'true');
    const stale = await stalePage.evaluate(() => ({
      actions: window.__fixture.actions,
      events: window.__fixture.events,
      loadCalls: window.__fixture.loadCalls,
      navigations: window.__fixture.navigations,
      syncCalls: window.__fixture.syncCalls,
      toasts: window.__fixture.toasts,
      chats: window.chats,
      rootText: document.getElementById('fixtureRoot').textContent,
    }));
    assert.equal(stale.syncCalls, 1);
    assert.deepEqual(stale.actions, ['sync']);
    assert.deepEqual(stale.loadCalls, []);
    assert.deepEqual(stale.navigations, []);
    assert.deepEqual(stale.events, []);
    assert.deepEqual(stale.toasts, []);
    if (staleKind !== 'project') {
      const serializedChats = JSON.stringify(stale.chats);
      assert.equal(serializedChats.includes('33333333-3333-4333-8333-333333333333'), false);
      assert.equal(serializedChats.includes('Supervisor launch plan'), false);
      assert.equal(stale.rootText.includes('Supervisor launch plan'), false);
    }
    staleCases.push({kind: staleKind, ...stale});
    await stalePage.close();
  }

  async function openAuthBoundaryScenario(scenario) {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    page.on('console', message => {
      if (message.type() === 'error') errors.push(`auth-${scenario}: ${message.text()}`);
    });
    page.on('pageerror', error => errors.push(`auth-${scenario}: ${error.message}`));
    await page.goto(
      `${origin}/tests/fixtures/project-resume-auth-boundary.html?scenario=${scenario}`,
      {waitUntil: 'domcontentloaded'},
    );
    await page.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'}).waitFor();
    return page;
  }

  const realSamePage = await openAuthBoundaryScenario('same');
  await realSamePage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'}).click();
  await realSamePage.waitForFunction(() => window.__fixture.pullCalls === 1);
  await realSamePage.evaluate(() => window.__fixture.resolveOwnerAPull());
  await realSamePage.waitForFunction(() => window.__fixture.syncSettled && window.__fixture.events.length === 1);
  const realSame = await realSamePage.evaluate(() => ({
    actions: window.__fixture.actions,
    currentChatId: window.currentChatId,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    pullCalls: window.__fixture.pullCalls,
    pushCalls: window.__fixture.pushCalls,
    replaceCalls: window.__fixture.replaceCalls,
    renderListCalls: window.__fixture.renderListCalls,
    syncResult: window.__fixture.syncResult,
    aCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerA}`),
    bCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerB}`),
  }));
  assert.equal(realSame.pullCalls, 1);
  assert.equal(realSame.pushCalls, 1);
  assert.equal(realSame.replaceCalls, 1);
  assert.equal(realSame.renderListCalls, 1);
  assert.deepEqual(realSame.loadCalls, ['33333333-3333-4333-8333-333333333333']);
  assert.deepEqual(realSame.navigations, ['ask']);
  assert.equal(realSame.currentChatId, '33333333-3333-4333-8333-333333333333');
  assert.equal(realSame.syncResult.success, true);
  assert.equal(realSame.aCursor, '"2026-10-24T06:30:00Z"');
  assert.equal(realSame.bCursor, '"b-cursor-original"');
  assert.deepEqual(realSame.events, [{
    name: 'RecentWorkResumed',
    detail: {eventKey: 'recent-work-resumed', source: 'project'},
  }]);

  const staleSyncPage = await openAuthBoundaryScenario('switch');
  await staleSyncPage.getByRole('button', {name: 'Continue “Supervisor launch plan” in Ask'}).click();
  await staleSyncPage.waitForFunction(() => window.__fixture.pullCalls === 1);
  await staleSyncPage.evaluate(() => window.__fixture.switchToOwnerB());
  await staleSyncPage.getByRole('button', {name: 'Continue “Owner B work” in Ask'}).waitFor();
  await staleSyncPage.evaluate(() => window.__fixture.resolveOwnerAPull());
  await staleSyncPage.waitForFunction(() => window.__fixture.syncSettled);
  const staleSync = await staleSyncPage.evaluate(() => ({
    actions: window.__fixture.actions,
    currentChatId: window.currentChatId,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    pullCalls: window.__fixture.pullCalls,
    pushCalls: window.__fixture.pushCalls,
    replaceCalls: window.__fixture.replaceCalls,
    renderListCalls: window.__fixture.renderListCalls,
    renderMessageCalls: window.__fixture.renderMessageCalls,
    rootText: document.getElementById('fixtureRoot').textContent,
    chats: window.chats,
    syncResult: window.__fixture.syncResult,
    toasts: window.__fixture.toasts,
    aCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerA}`),
    bCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerB}`),
    aStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerA}`),
    bStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerB}`),
  }));
  assert.equal(staleSync.pullCalls, 1);
  assert.equal(staleSync.pushCalls, 0);
  assert.equal(staleSync.replaceCalls, 0);
  assert.equal(staleSync.renderListCalls, 0);
  assert.equal(staleSync.renderMessageCalls, 0);
  assert.deepEqual(staleSync.actions, []);
  assert.deepEqual(staleSync.events, []);
  assert.deepEqual(staleSync.loadCalls, []);
  assert.deepEqual(staleSync.navigations, []);
  assert.deepEqual(staleSync.toasts, []);
  assert.equal(staleSync.currentChatId, '');
  assert.equal(staleSync.syncResult.code, 'SYNC_AUTH_BOUNDARY_CHANGED');
  assert.equal(staleSync.aCursor, '"a-cursor-original"');
  assert.equal(staleSync.bCursor, '"b-cursor-original"');
  assert.equal(staleSync.aStorage, '[]');
  assert.ok(staleSync.bStorage.includes('Owner B work'));
  assert.equal(JSON.stringify(staleSync.chats).includes('owner-a-private-content'), false);
  assert.equal(staleSync.rootText.includes('Supervisor launch plan'), false);
  assert.equal(staleSync.rootText.includes('A private continuation fixture.'), false);
  assert.ok(staleSync.rootText.includes('Owner B Project'));

  async function openRealStateBoundary(label) {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    page.on('console', message => {
      if (message.type() === 'error') errors.push(`real-${label}: ${message.text()}`);
    });
    page.on('pageerror', error => errors.push(`real-${label}: ${error.message}`));
    await page.goto(`${origin}/tests/fixtures/project-resume-real-state-boundary.html`, {
      waitUntil: 'domcontentloaded',
    });
    await page.getByRole('button', {name: 'Continue “Owner A private launch plan” in Ask'}).waitFor();
    await page.waitForFunction(() => (
      document.getElementById('chatsList')?.textContent.includes('Owner A private launch plan')
      && document.getElementById('chatContainer')?.textContent.includes('owner-a-private-content')
    ));
    return page;
  }

  const realStateFailurePage = await openRealStateBoundary('failure');
  await realStateFailurePage.evaluate(() => { void window.__fixture.startSync(); });
  await realStateFailurePage.waitForFunction(() => window.__fixture.pullClaims.length === 1);
  await realStateFailurePage.evaluate(() => {
    window.__fixture.seedOwnerAPrefetch();
    window.__fixture.switchToOwnerB();
  });
  await realStateFailurePage.getByRole('button', {name: 'Continue “Owner B retained work” in Ask'}).waitFor();
  const scrubbedBeforeCompletion = await realStateFailurePage.evaluate(() => ({
    chats: window.chats,
    currentChatId: window.currentChatId,
    sidebar: document.getElementById('chatsList').textContent,
    messages: document.getElementById('chatContainer').textContent,
    prefetched: window.__crumpSyncData,
    root: document.getElementById('fixtureRoot').textContent,
    aStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerA}`),
    bStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerB}`),
    aCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerA}`),
    bCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerB}`),
    originals: {
      aStorage: window.__fixture.aStorageOriginal,
      bStorage: window.__fixture.bStorageOriginal,
      aCursor: window.__fixture.aCursorOriginal,
      bCursor: window.__fixture.bCursorOriginal,
    },
  }));
  assert.deepEqual(scrubbedBeforeCompletion.chats, []);
  assert.equal(scrubbedBeforeCompletion.currentChatId, null);
  assert.equal(scrubbedBeforeCompletion.sidebar.includes('Owner A'), false);
  assert.equal(scrubbedBeforeCompletion.messages.includes('owner-a-private-content'), false);
  assert.equal(scrubbedBeforeCompletion.prefetched, null);
  assert.equal(scrubbedBeforeCompletion.root.includes('Owner A'), false);
  assert.ok(scrubbedBeforeCompletion.root.includes('Owner B Project'));
  assert.equal(scrubbedBeforeCompletion.aStorage, scrubbedBeforeCompletion.originals.aStorage);
  assert.equal(scrubbedBeforeCompletion.bStorage, scrubbedBeforeCompletion.originals.bStorage);
  assert.equal(scrubbedBeforeCompletion.aCursor, scrubbedBeforeCompletion.originals.aCursor);
  assert.equal(scrubbedBeforeCompletion.bCursor, scrubbedBeforeCompletion.originals.bCursor);

  await realStateFailurePage.getByRole('button', {name: 'Continue “Owner B retained work” in Ask'}).click();
  await realStateFailurePage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerA));
  await realStateFailurePage.waitForFunction(() => window.__fixture.pullClaims.length === 2);
  await realStateFailurePage.evaluate(() => window.__fixture.resolvePull(
    window.__fixture.ownerB,
    {success: false},
  ));
  await realStateFailurePage.waitForFunction(() => window.__fixture.toasts.length === 1);
  const realStateFailure = await realStateFailurePage.evaluate(() => ({
    chats: window.chats,
    currentChatId: window.currentChatId,
    sidebar: document.getElementById('chatsList').textContent,
    messages: document.getElementById('chatContainer').textContent,
    root: document.getElementById('fixtureRoot').textContent,
    actions: window.__fixture.actions,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    pullClaims: window.__fixture.pullClaims,
    pushClaims: window.__fixture.pushClaims,
    toasts: window.__fixture.toasts,
    aStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerA}`),
    bStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerB}`),
    aCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerA}`),
    bCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerB}`),
    originals: {
      aStorage: window.__fixture.aStorageOriginal,
      bStorage: window.__fixture.bStorageOriginal,
      aCursor: window.__fixture.aCursorOriginal,
      bCursor: window.__fixture.bCursorOriginal,
    },
  }));
  assert.deepEqual(realStateFailure.pullClaims, [
    '11111111-1111-4111-8111-111111111111',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  ]);
  assert.deepEqual(realStateFailure.pushClaims, []);
  assert.deepEqual(realStateFailure.chats, []);
  assert.equal(realStateFailure.currentChatId, null);
  assert.equal(realStateFailure.sidebar.includes('Owner A'), false);
  assert.equal(realStateFailure.messages.includes('owner-a-private-content'), false);
  assert.equal(realStateFailure.root.includes('Owner A'), false);
  assert.deepEqual(realStateFailure.loadCalls, []);
  assert.deepEqual(realStateFailure.navigations, []);
  assert.deepEqual(realStateFailure.events, []);
  assert.equal(realStateFailure.aStorage, realStateFailure.originals.aStorage);
  assert.equal(realStateFailure.bStorage, realStateFailure.originals.bStorage);
  assert.equal(realStateFailure.aCursor, realStateFailure.originals.aCursor);
  assert.equal(realStateFailure.bCursor, realStateFailure.originals.bCursor);

  const realStateSuccessPage = await openRealStateBoundary('success');
  await realStateSuccessPage.evaluate(() => { void window.__fixture.startSync(); });
  await realStateSuccessPage.waitForFunction(() => window.__fixture.pullClaims.length === 1);
  await realStateSuccessPage.evaluate(() => {
    window.__fixture.seedOwnerAPrefetch();
    window.__fixture.switchToOwnerB();
  });
  await realStateSuccessPage.getByRole('button', {name: 'Continue “Owner B retained work” in Ask'}).click();
  await realStateSuccessPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerA));
  await realStateSuccessPage.waitForFunction(() => window.__fixture.pullClaims.length === 2);
  await realStateSuccessPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerB));
  await realStateSuccessPage.waitForFunction(() => window.__fixture.events.length === 1);
  const realStateSuccess = await realStateSuccessPage.evaluate(() => ({
    actions: window.__fixture.actions,
    events: window.__fixture.events,
    loadCalls: window.__fixture.loadCalls,
    navigations: window.__fixture.navigations,
    currentChatId: window.currentChatId,
    toasts: window.__fixture.toasts,
    chats: window.chats,
    pushClaims: window.__fixture.pushClaims,
    pushPayloads: window.__fixture.pushPayloads,
  }));
  assert.deepEqual(realStateSuccess.loadCalls, ['bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb']);
  assert.deepEqual(realStateSuccess.navigations, ['ask']);
  assert.equal(realStateSuccess.currentChatId, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
  assert.deepEqual(realStateSuccess.toasts, []);
  assert.equal(JSON.stringify(realStateSuccess.chats).includes('owner-a-private-content'), false);
  assert.deepEqual(realStateSuccess.events, [{
    name: 'RecentWorkResumed',
    detail: {eventKey: 'recent-work-resumed', source: 'project'},
  }]);
  assert.equal(JSON.stringify(realStateSuccess.events).includes('Owner B'), false);
  assert.equal(JSON.stringify(realStateSuccess.events).includes('bbbbbbbb'), false);
  assert.deepEqual(realStateSuccess.pushClaims, ['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa']);
  assert.equal(JSON.stringify(realStateSuccess.pushPayloads).includes('owner-a-private-content'), false);
  assert.ok(JSON.stringify(realStateSuccess.pushPayloads).includes('owner-b-private-content'));
  assert.equal(JSON.stringify(realStateSuccess.pushPayloads).includes('44444444-4444-4444-8444-444444444444'), false);
  assert.ok(JSON.stringify(realStateSuccess.pushPayloads).includes('cccccccc-cccc-4ccc-8ccc-cccccccccccc'));

  const ownerReconciliationPage = await openRealStateBoundary('owner-reconciliation');
  await ownerReconciliationPage.evaluate(() => { void window.__fixture.startSync(); });
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 1);
  await ownerReconciliationPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerA));
  await ownerReconciliationPage.waitForFunction(() => (
    window.__fixture.syncResults.length === 1 && window.__fixture.pushClaims.length === 1
  ));

  await ownerReconciliationPage.evaluate(() => {
    window.__fixture.switchToOwnerB();
    void window.__fixture.startSync();
  });
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 2);
  await ownerReconciliationPage.evaluate(() => window.__fixture.resolvePull(
    window.__fixture.ownerB,
    {success: false},
  ));
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.syncResults.length === 2);

  await ownerReconciliationPage.evaluate(() => { void window.__fixture.startSync(); });
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 3);
  await ownerReconciliationPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerB));
  await ownerReconciliationPage.waitForFunction(() => (
    window.__fixture.syncResults.length === 3 && window.__fixture.pushClaims.length === 2
  ));

  await ownerReconciliationPage.evaluate(() => { void window.__fixture.startSync(); });
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 4);
  await ownerReconciliationPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerB));
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.syncResults.length === 4);

  await ownerReconciliationPage.evaluate(() => {
    window.__fixture.restartOwnerBSession();
    void window.__fixture.startSync();
  });
  await ownerReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 5);
  await ownerReconciliationPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerB));
  await ownerReconciliationPage.waitForFunction(() => (
    window.__fixture.syncResults.length === 5 && window.__fixture.pushClaims.length === 3
  ));
  const ownerReconciliation = await ownerReconciliationPage.evaluate(() => ({
    pullClaims: window.__fixture.pullClaims,
    pushClaims: window.__fixture.pushClaims,
    pushPayloads: window.__fixture.pushPayloads,
    syncResults: window.__fixture.syncResults,
  }));
  assert.deepEqual(ownerReconciliation.pullClaims, [
    '11111111-1111-4111-8111-111111111111',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  ]);
  assert.deepEqual(ownerReconciliation.pushClaims, [
    '11111111-1111-4111-8111-111111111111',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  ]);
  assert.equal(ownerReconciliation.syncResults[1]?.success, false);
  assert.equal(JSON.stringify(ownerReconciliation.pushPayloads[0]).includes('owner-a-private-content'), true);
  assert.equal(JSON.stringify(ownerReconciliation.pushPayloads[0]).includes('owner-b-private-content'), false);
  assert.equal(JSON.stringify(ownerReconciliation.pushPayloads[0]).includes('44444444-4444-4444-8444-444444444444'), true);
  assert.equal(JSON.stringify(ownerReconciliation.pushPayloads[0]).includes('cccccccc-cccc-4ccc-8ccc-cccccccccccc'), false);
  assert.equal(JSON.stringify(ownerReconciliation.pushPayloads[1]).includes('44444444-4444-4444-8444-444444444444'), false);
  assert.equal(JSON.stringify(ownerReconciliation.pushPayloads[1]).includes('cccccccc-cccc-4ccc-8ccc-cccccccccccc'), true);
  for (const payload of ownerReconciliation.pushPayloads.slice(1)) {
    assert.equal(JSON.stringify(payload).includes('owner-a-private-content'), false);
    assert.equal(JSON.stringify(payload).includes('owner-b-private-content'), true);
  }

  const concurrentReconciliationPage = await openRealStateBoundary('concurrent-owner-reconciliation');
  await concurrentReconciliationPage.evaluate(() => {
    void window.__fixture.startSync();
    void window.__fixture.startSync();
  });
  await concurrentReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 1);
  await concurrentReconciliationPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerA));
  await concurrentReconciliationPage.waitForFunction(() => window.__fixture.pullClaims.length === 2);
  await concurrentReconciliationPage.evaluate(() => window.__fixture.resolvePull(window.__fixture.ownerA));
  await concurrentReconciliationPage.waitForFunction(() => window.__fixture.syncResults.length === 2);
  const concurrentReconciliation = await concurrentReconciliationPage.evaluate(() => ({
    pullClaims: window.__fixture.pullClaims,
    pushClaims: window.__fixture.pushClaims,
    pushPayloads: window.__fixture.pushPayloads,
    syncResults: window.__fixture.syncResults,
  }));
  assert.deepEqual(concurrentReconciliation.pullClaims, [
    '11111111-1111-4111-8111-111111111111',
    '11111111-1111-4111-8111-111111111111',
  ]);
  assert.deepEqual(concurrentReconciliation.pushClaims, [
    '11111111-1111-4111-8111-111111111111',
  ]);
  assert.equal(concurrentReconciliation.pushPayloads.length, 1);
  assert.equal(concurrentReconciliation.syncResults.every(result => result?.success !== false), true);

  const hiddenProjectsPage = await openRealStateBoundary('hidden');
  await hiddenProjectsPage.evaluate(() => {
    window.__fixture.openLibrary();
    window.__fixture.switchToOwnerB();
  });
  await hiddenProjectsPage.waitForTimeout(30);
  const hiddenProjects = await hiddenProjectsPage.evaluate(() => ({
    destination: window.__fixture.currentDestination(),
    root: document.getElementById('fixtureRoot').textContent,
    projectRoot: Boolean(document.querySelector('.cvp-root')),
  }));
  assert.equal(hiddenProjects.destination, 'library');
  assert.ok(hiddenProjects.root.includes('Library remains active'));
  assert.equal(hiddenProjects.projectRoot, false);
  await hiddenProjectsPage.evaluate(() => window.__fixture.reopenProjects());
  await hiddenProjectsPage.getByRole('button', {name: 'Continue “Owner B retained work” in Ask'}).waitFor();
  const reopenedProjects = await hiddenProjectsPage.evaluate(() => ({
    destination: window.__fixture.currentDestination(),
    root: document.getElementById('fixtureRoot').textContent,
  }));
  assert.equal(reopenedProjects.destination, 'projects');
  assert.ok(reopenedProjects.root.includes('Owner B Project'));
  assert.equal(reopenedProjects.root.includes('Owner A'), false);

  const logoutPage = await openRealStateBoundary('logout');
  await logoutPage.evaluate(() => window.__fixture.switchToLogout());
  await logoutPage.waitForTimeout(30);
  const logoutState = await logoutPage.evaluate(() => ({
    chats: window.chats,
    currentChatId: window.currentChatId,
    sidebar: document.getElementById('chatsList').textContent,
    messages: document.getElementById('chatContainer').textContent,
    prefetched: window.__crumpSyncData,
    aStorage: localStorage.getItem(`crump_chats:${window.__fixture.ownerA}`),
    aStorageOriginal: window.__fixture.aStorageOriginal,
  }));
  assert.deepEqual(logoutState.chats, []);
  assert.equal(logoutState.currentChatId, null);
  assert.equal(logoutState.sidebar, '');
  assert.equal(logoutState.messages, '');
  assert.equal(logoutState.prefetched, null);
  assert.equal(logoutState.aStorage, logoutState.aStorageOriginal);

  const ownerHeaderPage = await browser.newPage();
  ownerHeaderPage.on('console', message => {
    if (message.type() === 'error') errors.push(`owner-header: ${message.text()}`);
  });
  ownerHeaderPage.on('pageerror', error => errors.push(`owner-header: ${error.message}`));
  await ownerHeaderPage.goto(`${origin}/tests/fixtures/sync-owner-header-boundary.html`, {
    waitUntil: 'domcontentloaded',
  });
  await ownerHeaderPage.evaluate(() => { void window.__fixture.startPull(); });
  await ownerHeaderPage.waitForFunction(() => window.__fixture.pendingCount('GET') === 1);
  await ownerHeaderPage.evaluate(() => {
    window.__fixture.setServerOwner(window.__fixture.ownerB);
    window.__fixture.resolveNext('GET');
  });
  await ownerHeaderPage.waitForFunction(() => window.__fixture.results.length === 1);
  await ownerHeaderPage.evaluate(() => { void window.__fixture.startPush(window.__fixture.chatA); });
  await ownerHeaderPage.waitForFunction(() => window.__fixture.pendingCount('POST') === 1);
  await ownerHeaderPage.evaluate(() => window.__fixture.resolveNext('POST'));
  await ownerHeaderPage.waitForFunction(() => window.__fixture.results.length === 2);
  const staleOwnerHeaders = await ownerHeaderPage.evaluate(() => ({
    requests: window.__fixture.requests,
    results: window.__fixture.results,
    aQueue: localStorage.getItem(`crump_sync_queue_v4:${window.__fixture.ownerA}`),
    bQueue: localStorage.getItem(`crump_sync_queue_v4:${window.__fixture.ownerB}`),
    aCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerA}`),
    bCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerB}`),
  }));
  assert.deepEqual(staleOwnerHeaders.requests.map(request => [request.method, request.claim]), [
    ['GET', '11111111-1111-4111-8111-111111111111'],
    ['POST', '11111111-1111-4111-8111-111111111111'],
  ]);
  assert.equal(staleOwnerHeaders.results[0].result.code, 'SYNC_OWNER_MISMATCH');
  assert.equal(staleOwnerHeaders.results[1].result.code, 'SYNC_OWNER_MISMATCH');
  assert.ok(staleOwnerHeaders.aQueue.includes('Owner A queued work'));
  assert.equal(staleOwnerHeaders.bQueue, '[]');
  assert.equal(staleOwnerHeaders.aCursor, '"a-cursor-original"');
  assert.equal(staleOwnerHeaders.bCursor, '"b-cursor-original"');

  await ownerHeaderPage.evaluate(() => {
    window.__fixture.switchClient(window.__fixture.ownerB);
    window.__fixture.startPull();
  });
  await ownerHeaderPage.waitForFunction(() => window.__fixture.pendingCount('GET') === 1);
  await ownerHeaderPage.evaluate(() => window.__fixture.resolveNext('GET'));
  await ownerHeaderPage.waitForFunction(() => window.__fixture.results.length === 3);
  await ownerHeaderPage.evaluate(() => { void window.__fixture.startPush(window.__fixture.chatB); });
  await ownerHeaderPage.waitForFunction(() => window.__fixture.pendingCount('POST') === 1);
  await ownerHeaderPage.evaluate(() => window.__fixture.resolveNext('POST'));
  await ownerHeaderPage.waitForFunction(() => window.__fixture.results.length === 4);
  const freshOwnerHeaders = await ownerHeaderPage.evaluate(() => ({
    requests: window.__fixture.requests,
    results: window.__fixture.results,
    aQueue: localStorage.getItem(`crump_sync_queue_v4:${window.__fixture.ownerA}`),
    bQueue: localStorage.getItem(`crump_sync_queue_v4:${window.__fixture.ownerB}`),
    aCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerA}`),
    bCursor: localStorage.getItem(`crump_last_sync_v4:${window.__fixture.ownerB}`),
  }));
  assert.deepEqual(freshOwnerHeaders.requests.slice(2).map(request => [request.method, request.claim]), [
    ['GET', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'],
    ['POST', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'],
  ]);
  assert.equal(freshOwnerHeaders.results[2].result.success, true);
  assert.equal(freshOwnerHeaders.results[3].result.success, true);
  assert.ok(freshOwnerHeaders.aQueue.includes('Owner A queued work'));
  assert.equal(freshOwnerHeaders.bQueue, '[]');
  assert.equal(freshOwnerHeaders.aCursor, '"a-cursor-original"');
  assert.equal(freshOwnerHeaders.bCursor, '"2026-10-24T08:01:00Z"');

  assert.deepEqual(errors, []);
  await samePage.close();
  await syncPage.close();
  await failurePage.close();
  await preClickPage.close();
  await realSamePage.close();
  await staleSyncPage.close();
  await realStateFailurePage.close();
  await realStateSuccessPage.close();
  await hiddenProjectsPage.close();
  await logoutPage.close();
  await ownerHeaderPage.close();
  await browser.close();
  process.stdout.write(JSON.stringify({
    same,
    preClickOwnerSwitch,
    ownerBReopen,
    synced,
    failure,
    staleCases,
    realSame,
    staleSync,
    scrubbedBeforeCompletion,
    realStateFailure,
    realStateSuccess,
    hiddenProjects,
    reopenedProjects,
    logoutState,
    staleOwnerHeaders,
    freshOwnerHeaders,
    errors,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
