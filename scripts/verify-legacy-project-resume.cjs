const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const productSource = readFileSync(path.join(root, 'public', 'crump-product-5.3.js'), 'utf8');
const chatId = '33333333-3333-4333-8333-333333333333';
const projectA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const projectB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

function extractNamedFunction(source, name) {
  const marker = `async function ${name}(`;
  const start = source.indexOf(marker);
  const bodyStart = source.indexOf('{', start);
  assert.ok(start >= 0 && bodyStart >= 0, `${name} must remain a named async function.`);
  let depth = 0;
  let quote = '';
  let escaped = false;
  for (let index = bodyStart; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === quote) quote = '';
      continue;
    }
    if (character === '"' || character === "'" || character === '`') {
      quote = character;
      continue;
    }
    if (character === '{') depth += 1;
    else if (character === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`${name} body is incomplete.`);
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, reject, resolve};
}

function jsonClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function createHarness({
  local = true,
  syncAddsChat = true,
  syncResult = {success: true},
  syncError = null,
  syncGate = null,
  loadResult = true,
  loadCurrentChatId = chatId,
  loadError = null,
  loadGate = null,
  navigationError = null,
} = {}) {
  let ownerId = 'owner-a';
  let ownerSequence = 1;
  const actions = [];
  const events = [];
  const toasts = [];
  const state = {activeProject: {id: projectA}};
  const window = {
    chats: local ? [{id: chatId, title: 'Private title'}] : [],
    currentChatId: '',
    showToast(message, level) {
      toasts.push({message, level});
    },
    CrumpNavigation5930: {
      open(destination) {
        actions.push(`navigate:${destination}`);
        if (navigationError) throw navigationError;
      },
    },
    CrumpAnalytics: {
      track(name, detail) {
        actions.push('track');
        events.push({name, detail});
        return Promise.resolve({accepted: true});
      },
    },
    async syncChatsFromServer() {
      actions.push('sync');
      if (syncGate) await syncGate.promise;
      if (syncError) throw syncError;
      if (syncAddsChat) window.chats = [{id: chatId, title: 'Private title'}];
      return syncResult;
    },
    async loadChat(candidate) {
      actions.push(`load:${candidate}`);
      if (loadGate) await loadGate.promise;
      if (loadError) throw loadError;
      window.currentChatId = loadCurrentChatId;
      return loadResult;
    },
  };
  const context = vm.createContext({
    Promise,
    String,
    Array,
    Boolean,
    Error,
    window,
    state,
    projectOperationContext() {
      return {userId: ownerId, sequence: ownerSequence};
    },
    projectOperationIsCurrent(operation) {
      return Boolean(
        operation?.userId
        && operation.userId === ownerId
        && operation.sequence === ownerSequence
      );
    },
    closeStudio() {
      actions.push('navigate:ask');
    },
    byId() {
      return null;
    },
    requestAnimationFrame() {},
  });
  const resumeSource = extractNamedFunction(productSource, 'resumeProjectConversation');
  vm.runInContext(`${resumeSource}\nglobalThis.__resumeProjectConversation = resumeProjectConversation;`, context);

  return {
    actions,
    events,
    state,
    toasts,
    window,
    resume: context.__resumeProjectConversation,
    logout() {
      ownerId = '';
      ownerSequence += 1;
    },
    switchOwner() {
      ownerId = 'owner-b';
      ownerSequence += 1;
    },
    switchProject() {
      state.activeProject = {id: projectB};
    },
  };
}

async function expectSuccess(options, expectedActions) {
  const harness = createHarness(options);
  assert.equal(await harness.resume(chatId), true);
  assert.deepEqual(harness.actions, expectedActions);
  assert.deepEqual(jsonClone(harness.events), [{
    name: 'RecentWorkResumed',
    detail: {eventKey: 'recent-work-resumed', source: 'project'},
  }]);
  assert.equal(JSON.stringify(harness.events).includes(chatId), false);
  assert.equal(JSON.stringify(harness.events).includes('Private title'), false);
  assert.deepEqual(harness.toasts, []);
}

async function expectFailure(options, expectedActions, {allowNavigationAttempt = false} = {}) {
  const harness = createHarness(options);
  assert.equal(await harness.resume(chatId), false);
  assert.deepEqual(harness.actions, expectedActions);
  assert.deepEqual(harness.events, []);
  if (!allowNavigationAttempt) {
    assert.equal(harness.actions.some(action => action.startsWith('navigate:')), false);
  }
  return harness;
}

(async () => {
  await expectSuccess(
    {local: true},
    [`load:${chatId}`, 'navigate:ask', 'track'],
  );
  await expectSuccess(
    {local: false},
    ['sync', `load:${chatId}`, 'navigate:ask', 'track'],
  );

  const rejected = await expectFailure(
    {local: false, syncError: new Error('offline')},
    ['sync'],
  );
  assert.equal(rejected.toasts.length, 1);
  const explicitFailure = await expectFailure(
    {local: false, syncResult: {success: false}},
    ['sync'],
  );
  assert.equal(explicitFailure.toasts.length, 1);
  const missing = await expectFailure(
    {local: false, syncAddsChat: false},
    ['sync'],
  );
  assert.equal(missing.toasts.length, 1);
  const loadFalse = await expectFailure(
    {local: true, loadResult: false},
    [`load:${chatId}`],
  );
  assert.equal(loadFalse.toasts.length, 1);
  const loadMismatch = await expectFailure(
    {local: true, loadCurrentChatId: '44444444-4444-4444-8444-444444444444'},
    [`load:${chatId}`],
  );
  assert.equal(loadMismatch.toasts.length, 1);
  const loadRejected = await expectFailure(
    {local: true, loadError: new Error('load failed')},
    [`load:${chatId}`],
  );
  assert.equal(loadRejected.toasts.length, 1);
  const navigationRejected = await expectFailure(
    {local: true, navigationError: new Error('navigation failed')},
    [`load:${chatId}`, 'navigate:ask'],
    {allowNavigationAttempt: true},
  );
  assert.equal(navigationRejected.toasts.length, 1);

  for (const staleAction of ['switchOwner', 'logout', 'switchProject']) {
    const syncGate = deferred();
    const staleSync = createHarness({local: false, syncGate});
    const pendingSync = staleSync.resume(chatId);
    await Promise.resolve();
    assert.deepEqual(staleSync.actions, ['sync']);
    staleSync[staleAction]();
    syncGate.resolve();
    assert.equal(await pendingSync, false);
    assert.deepEqual(staleSync.actions, ['sync']);
    assert.deepEqual(staleSync.events, []);
    assert.deepEqual(staleSync.toasts, []);
  }

  for (const staleAction of ['switchOwner', 'logout', 'switchProject']) {
    const loadGate = deferred();
    const staleLoad = createHarness({local: true, loadGate});
    const pendingLoad = staleLoad.resume(chatId);
    await Promise.resolve();
    assert.deepEqual(staleLoad.actions, [`load:${chatId}`]);
    staleLoad[staleAction]();
    loadGate.resolve();
    assert.equal(await pendingLoad, false);
    assert.deepEqual(staleLoad.actions, [`load:${chatId}`]);
    assert.deepEqual(staleLoad.events, []);
    assert.deepEqual(staleLoad.toasts, []);
  }

  process.stdout.write('Legacy Project resume verifier passed: load, navigation, analytics truth, privacy, recovery, and stale-boundary suppression are intact.\n');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
