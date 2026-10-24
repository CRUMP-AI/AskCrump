import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

import { createNativePushActionQueue } from './native-push-action-queue.mjs';

const OWNER_A = '11111111-1111-4111-8111-111111111111';
const OWNER_B = '22222222-2222-4222-8222-222222222222';

function eventTarget() {
  const listeners = new Map();
  return {
    addEventListener(type, listener) {
      const group = listeners.get(type) || [];
      group.push(listener);
      listeners.set(type, group);
    },
    dispatchEvent(event) {
      for (const listener of listeners.get(event.type) || []) listener(event);
      return true;
    },
  };
}

const presenceSource = await readFile(new URL('../public/presence-manager.js', import.meta.url), 'utf8');

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
    snapshot: () => new Map(values),
  };
}

function pushAction(notificationId, chatId, extra = {}, ownerId = OWNER_A) {
  return {
    actionId: 'tap',
    notification: {
      id: notificationId,
      title: 'Private title that must not be persisted',
      body: 'Private body that must not be persisted',
      data: { ownerId, chatId, ignored: 'not persisted' },
    },
    ...extra,
  };
}

function createHarness({
  queue,
  storage,
  chats = [],
  sync,
  load = null,
  runtimeReady = false,
  ownerId = OWNER_A,
  revision = 1,
}) {
  const loadedChats = [];
  const toasts = [];
  const scheduled = [];
  const microtasks = [];
  const scrubbers = [];
  let currentOwnerId = ownerId;
  let currentRevision = revision;
  const windowTarget = eventTarget();
  const windowObject = {
    ...windowTarget,
    CrumpNative: {
      peekPendingPushActions: () => queue.peek(),
      acknowledgePushAction: queueId => queue.acknowledge(queueId),
    },
    CrumpAPI: { isNative: true, installationId: () => 'fixture-installation' },
    currentUser: currentOwnerId ? { id: currentOwnerId } : null,
    currentChatId: null,
    chats,
    syncChatsFromServer: sync,
    showToast(message, kind) {
      toasts.push({ message, kind });
    },
    CrumpAuthBoundary: {
      authenticatedUserId: () => currentOwnerId,
      revision: () => currentRevision,
      register(_name, callback) {
        scrubbers.push(callback);
        return () => {};
      },
    },
    loadChat(chatId, expectedBoundary) {
      if (
        expectedBoundary?.ownerId !== currentOwnerId
        || expectedBoundary?.revision !== currentRevision
      ) return false;
      if (typeof load === 'function') {
        return load({
          chatId: String(chatId),
          expectedBoundary,
          loadedChats,
          ownerId: () => currentOwnerId,
          revision: () => currentRevision,
          window: windowObject,
        });
      }
      const target = this.chats.find(chat => String(chat.id || chat.chat_id) === String(chatId));
      if (!target) return false;
      this.currentChatId = String(chatId);
      loadedChats.push(String(chatId));
      return true;
    },
  };
  const connectionStatus = {
    hidden: false,
    textContent: '',
    setAttribute() {},
  };
  const documentTarget = eventTarget();
  const context = {
    AbortController,
    window: windowObject,
    document: {
      ...documentTarget,
      hidden: false,
      documentElement: { dataset: { crumpBodyRuntime: runtimeReady ? 'ready' : 'loading' } },
      getElementById: id => id === 'connectionStatus' ? connectionStatus : null,
      querySelector: () => null,
    },
    navigator: { onLine: true },
    sessionStorage: storage,
    SafeStorage: { getItem: () => null },
    console,
    fetch: async () => new Response('{}', { status: 200 }),
    Response,
    queueMicrotask: callback => microtasks.push(callback),
    setTimeout: callback => {
      scheduled.push(callback);
      return scheduled.length;
    },
    clearTimeout() {},
    setInterval,
    clearInterval,
  };
  vm.runInNewContext(presenceSource, context, { filename: 'public/presence-manager.js' });
  return {
    loadedChats,
    microtasks,
    scheduled,
    toasts,
    window: windowObject,
    switchOwner(nextOwnerId) {
      currentRevision += 1;
      for (const scrub of scrubbers) scrub({
        reason: nextOwnerId ? 'authenticated-user-changed' : 'authentication-required',
        previousUserId: currentOwnerId,
        nextUserId: nextOwnerId,
        revision: currentRevision,
      });
      currentOwnerId = nextOwnerId;
      windowObject.currentUser = nextOwnerId ? { id: nextOwnerId } : null;
      if (nextOwnerId) windowObject.dispatchEvent({ type: 'crump:authenticated-ready' });
    },
    ownerId: () => currentOwnerId,
    revision: () => currentRevision,
    ready() {
      context.document.documentElement.dataset.crumpBodyRuntime = 'ready';
      windowObject.dispatchEvent({ type: 'crump:body-runtime-ready' });
    },
  };
}

const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await new Promise(resolve => setImmediate(resolve));
};

// A native callback is persisted before the deferred workspace consumer exists.
const durableStorage = memoryStorage();
const nativeQueue = createNativePushActionQueue({ limit: 4, storage: durableStorage });
const coldSource = pushAction('notification-cold', 'chat-cold');
const coldEntry = nativeQueue.retain(coldSource);
assert.ok(coldEntry);
assert.equal(nativeQueue.peek().length, 1);
assert.equal(nativeQueue.drain().length, 1);
assert.equal(nativeQueue.peek().length, 1, 'A drain/peek must not remove an unacknowledged action.');
assert.doesNotMatch(durableStorage.getItem('crump_native_push_actions_v2'), /Private title|Private body|ignored/);

// A WebView reload recreates the queue and restores the unacknowledged action.
const reloadedQueue = createNativePushActionQueue({ limit: 4, storage: durableStorage });
assert.equal(reloadedQueue.peek()[0].queueId, coldEntry.queueId);
const duplicateCold = reloadedQueue.retain(coldSource);
assert.equal(duplicateCold.queueId, coldEntry.queueId);
assert.equal(reloadedQueue.peek().length, 1, 'Duplicate native callbacks must share one queue entry.');

// A transient synchronization failure retains the action and retries it.
let syncAttempts = 0;
const retryChats = [];
const retryHarness = createHarness({
  queue: reloadedQueue,
  storage: durableStorage,
  chats: retryChats,
  sync: async () => {
    syncAttempts += 1;
    if (syncAttempts === 1) return { success: false, offline: true };
    retryChats.push({ id: 'chat-cold' });
    return { success: true };
  },
});
retryHarness.ready();
await flush();
assert.equal(reloadedQueue.peek().length, 1, 'A failed handoff must remain pending.');
assert.deepEqual(retryHarness.loadedChats, []);
assert.equal(retryHarness.scheduled.length, 1);
retryHarness.scheduled.shift()();
await flush();
assert.deepEqual(retryHarness.loadedChats, ['chat-cold']);
assert.equal(reloadedQueue.peek().length, 0);
assert.equal(reloadedQueue.retain(coldSource), null, 'An acknowledged callback must remain deduplicated after success.');

// Event delivery followed by the retained-action peek must still navigate once.
const orderingStorage = memoryStorage();
const orderingQueue = createNativePushActionQueue({ storage: orderingStorage });
const orderingEntry = orderingQueue.retain(pushAction('notification-ordering', 'chat-ordering'));
const orderingHarness = createHarness({
  queue: orderingQueue,
  storage: orderingStorage,
  chats: [{ id: 'chat-ordering' }],
  sync: async () => ({ success: true }),
  runtimeReady: true,
});
orderingHarness.window.dispatchEvent({ type: 'crump:push-action', detail: orderingEntry });
orderingHarness.microtasks.splice(0).forEach(callback => callback());
await flush();
assert.deepEqual(orderingHarness.loadedChats, ['chat-ordering']);
assert.equal(orderingQueue.peek().length, 0);

// Some native providers place navigation data at the action's top level.
const topLevelStorage = memoryStorage();
const topLevelQueue = createNativePushActionQueue({ storage: topLevelStorage });
topLevelQueue.retain({
  actionId: 'tap',
  notification: { id: 'notification-top-level' },
  data: { ownerId: OWNER_A, chatId: 'chat-top-level' },
});
const topLevelHarness = createHarness({
  queue: topLevelQueue,
  storage: topLevelStorage,
  chats: [{ id: 'chat-top-level' }],
  sync: async () => ({ success: true }),
});
topLevelHarness.ready();
await flush();
assert.deepEqual(topLevelHarness.loadedChats, ['chat-top-level']);
assert.equal(topLevelQueue.peek().length, 0);

// A successful authoritative sync that cannot find the chat treats the tap as stale.
const staleStorage = memoryStorage();
const staleQueue = createNativePushActionQueue({ storage: staleStorage });
staleQueue.retain(pushAction('notification-deleted', 'chat-deleted'));
const staleHarness = createHarness({
  queue: staleQueue,
  storage: staleStorage,
  chats: [],
  sync: async () => ({ success: true }),
});
staleHarness.ready();
await flush();
assert.equal(staleQueue.peek().length, 0, 'A deleted conversation must not retry forever.');
assert.equal(staleHarness.scheduled.length, 0);
assert.deepEqual(staleHarness.loadedChats, []);

// Ownerless pre-upgrade handoffs fail closed instead of navigating as whoever signs in next.
const legacyStorage = memoryStorage();
legacyStorage.setItem('crump_pending_chat', 'chat-legacy');
legacyStorage.setItem('crump_native_push_actions_v1', JSON.stringify({
  version: 1,
  pending: [{queueId: 'legacy', dedupKey: 'legacy', action: {data: {chatId: 'chat-legacy'}}}],
}));
const legacyQueue = createNativePushActionQueue({ storage: legacyStorage });
const legacyHarness = createHarness({
  queue: legacyQueue,
  storage: legacyStorage,
  chats: [{ id: 'chat-legacy' }],
  sync: async () => ({ success: true }),
});
legacyHarness.ready();
await flush();
assert.equal(legacyStorage.getItem('crump_pending_chat'), null);
assert.deepEqual(legacyHarness.loadedChats, []);
assert.equal(legacyQueue.peek().length, 0);

// Multiple retained taps drain in order so the latest user action remains visible.
const orderedStorage = memoryStorage();
const orderedQueue = createNativePushActionQueue({ storage: orderedStorage });
orderedQueue.retain(pushAction('notification-first', 'chat-first'));
orderedQueue.retain(pushAction('notification-latest', 'chat-latest'));
const orderedHarness = createHarness({
  queue: orderedQueue,
  storage: orderedStorage,
  chats: [{ id: 'chat-first' }, { id: 'chat-latest' }],
  sync: async () => ({ success: true }),
});
orderedHarness.ready();
await flush();
assert.deepEqual(orderedHarness.loadedChats, ['chat-first', 'chat-latest']);
assert.equal(orderedHarness.window.currentChatId, 'chat-latest');
assert.equal(orderedQueue.peek().length, 0);
assert.equal(orderedHarness.scheduled.length, 0);

// An action retained while an earlier action awaits sync joins the active drain.
const lateStorage = memoryStorage();
const lateQueue = createNativePushActionQueue({ storage: lateStorage });
lateQueue.retain(pushAction('notification-waiting', 'chat-waiting'));
const lateChats = [];
let releaseLateSync;
const lateSyncGate = new Promise(resolve => { releaseLateSync = resolve; });
const lateHarness = createHarness({
  queue: lateQueue,
  storage: lateStorage,
  chats: lateChats,
  sync: async () => {
    await lateSyncGate;
    return { success: true };
  },
});
lateHarness.ready();
await Promise.resolve();
const lateEntry = lateQueue.retain(pushAction('notification-arrived-late', 'chat-arrived-late'));
lateHarness.window.dispatchEvent({ type: 'crump:push-action', detail: lateEntry });
lateChats.push({ id: 'chat-waiting' }, { id: 'chat-arrived-late' });
releaseLateSync();
await flush();
assert.deepEqual(lateHarness.loadedChats, ['chat-waiting', 'chat-arrived-late']);
assert.equal(lateHarness.window.currentChatId, 'chat-arrived-late');
assert.equal(lateQueue.peek().length, 0);

// The queue is bounded and fallback identities are stable when a provider omits an ID.
const bounded = createNativePushActionQueue({ limit: 2, storage: memoryStorage() });
bounded.retain(pushAction('one', 'chat-one'));
const keptTwo = bounded.retain(pushAction('two', 'chat-two'));
const keptThree = bounded.retain(pushAction('three', 'chat-three'));
assert.deepEqual(bounded.peek().map(entry => entry.queueId), [keptTwo.queueId, keptThree.queueId]);
const fallback = {
  actionId: 'tap',
  notification: { data: { ownerId: OWNER_A, chatId: 'chat-fallback' } },
};
const fallbackFirst = bounded.retain(fallback);
const fallbackSecond = bounded.retain({
  actionId: 'tap',
  notification: {
    title: 'Different private title',
    body: 'Different private body',
    data: { ownerId: OWNER_A, chatId: 'chat-fallback', ignored: 'still not identity' },
  },
});
assert.equal(fallbackFirst.queueId, fallbackSecond.queueId);
assert.equal(bounded.peek().length, 2, 'Private content changes must not create a new queue entry.');

const differentNavigation = bounded.retain({
  actionId: 'tap',
  notification: { data: { ownerId: OWNER_A, chatId: 'chat-other' } },
});
assert.notEqual(differentNavigation.queueId, fallbackFirst.queueId);

let fallbackClock = 1_000;
const fallbackAfterAck = createNativePushActionQueue({
  storage: memoryStorage(),
  now: () => fallbackClock,
  fallbackDedupWindowMs: 1_000,
});
const acknowledgedFallback = fallbackAfterAck.retain(fallback);
assert.equal(fallbackAfterAck.acknowledge(acknowledgedFallback.queueId), true);
assert.equal(
  fallbackAfterAck.retain(fallback),
  null,
  'An immediate duplicate callback without an event ID must remain suppressed.',
);
fallbackClock += 1_001;
assert.ok(fallbackAfterAck.retain(fallback), 'The fallback suppression window must expire.');

const checkInQueue = createNativePushActionQueue({ limit: 4, storage: memoryStorage() });
const firstCheckIn = checkInQueue.retain({
  actionId: 'tap',
  notification: { data: { ownerId: OWNER_A, chatId: 'chat-shared', checkInId: 'check-in-one' } },
});
const duplicateCheckIn = checkInQueue.retain({
  actionId: 'tap',
  notification: {
    title: 'Changed private title',
    data: { ownerId: OWNER_A, chatId: 'chat-shared', checkInId: 'check-in-one' },
  },
});
const secondCheckIn = checkInQueue.retain({
  actionId: 'tap',
  notification: { data: { ownerId: OWNER_A, chatId: 'chat-shared', checkInId: 'check-in-two' } },
});
assert.equal(duplicateCheckIn.queueId, firstCheckIn.queueId);
assert.notEqual(secondCheckIn.queueId, firstCheckIn.queueId);
assert.equal(checkInQueue.peek().length, 2);

// Ownerless or contradictory callbacks are never retained, and identical
// provider identities remain distinct across owners.
const ownerQueue = createNativePushActionQueue({ limit: 4, storage: memoryStorage() });
assert.equal(ownerQueue.retain({
  actionId: 'tap',
  notification: { id: 'notification-ownerless', data: { chatId: 'chat-ownerless' } },
}), null);
assert.equal(ownerQueue.retain({
  actionId: 'tap',
  notification: { id: 'notification-conflict', data: { ownerId: OWNER_A, chatId: 'chat-a' } },
  data: { ownerId: OWNER_B, chatId: 'chat-a' },
}), null);
const ownerAEntry = ownerQueue.retain(pushAction('notification-shared', 'chat-shared', {}, OWNER_A));
const ownerBEntry = ownerQueue.retain(pushAction('notification-shared', 'chat-shared', {}, OWNER_B));
assert.notEqual(ownerAEntry.queueId, ownerBEntry.queueId);
assert.equal(ownerQueue.peek().length, 2);

// A queued action for A is discarded without sync, navigation, toast, or DOM
// state when the active account is B.
const mismatchStorage = memoryStorage();
const mismatchQueue = createNativePushActionQueue({ storage: mismatchStorage });
mismatchQueue.retain(pushAction('notification-a-under-b', 'chat-a', {}, OWNER_A));
const mismatchHarness = createHarness({
  queue: mismatchQueue,
  storage: mismatchStorage,
  ownerId: OWNER_B,
  chats: [{ id: 'chat-a' }],
  sync: async () => { throw new Error('mismatched owner must not synchronize'); },
});
mismatchHarness.ready();
await flush();
assert.equal(mismatchQueue.peek().length, 0);
assert.deepEqual(mismatchHarness.loadedChats, []);
assert.deepEqual(mismatchHarness.toasts, []);
assert.equal(mismatchHarness.window.currentChatId, null);

// With no authenticated owner the action remains deferred. Authentication of
// its stamped owner wakes the drain and completes it exactly once.
const deferredStorage = memoryStorage();
const deferredQueue = createNativePushActionQueue({ storage: deferredStorage });
deferredQueue.retain(pushAction('notification-deferred', 'chat-deferred', {}, OWNER_A));
const deferredHarness = createHarness({
  queue: deferredQueue,
  storage: deferredStorage,
  ownerId: '',
  chats: [{ id: 'chat-deferred' }],
  sync: async () => ({ success: true }),
});
deferredHarness.ready();
await flush();
assert.equal(deferredQueue.peek().length, 1);
assert.deepEqual(deferredHarness.loadedChats, []);
deferredHarness.switchOwner(OWNER_A);
await flush();
assert.equal(deferredQueue.peek().length, 0);
assert.deepEqual(deferredHarness.loadedChats, ['chat-deferred']);

// Switching A -> B while A awaits synchronization drops A's stale completion
// and lets B's later action proceed without A blocking the queue.
const syncRaceStorage = memoryStorage();
const syncRaceQueue = createNativePushActionQueue({ storage: syncRaceStorage });
syncRaceQueue.retain(pushAction('notification-sync-race-a', 'chat-sync-race-a', {}, OWNER_A));
const syncRaceChats = [];
let releaseSyncRace;
const syncRaceGate = new Promise(resolve => { releaseSyncRace = resolve; });
const syncRaceHarness = createHarness({
  queue: syncRaceQueue,
  storage: syncRaceStorage,
  chats: syncRaceChats,
  sync: async () => {
    await syncRaceGate;
    return { success: true };
  },
});
syncRaceHarness.ready();
await Promise.resolve();
syncRaceChats.push({ id: 'chat-sync-race-b' });
syncRaceQueue.retain(pushAction('notification-sync-race-b', 'chat-sync-race-b', {}, OWNER_B));
syncRaceHarness.switchOwner(OWNER_B);
await flush();
releaseSyncRace();
await flush();
assert.deepEqual(syncRaceHarness.loadedChats, ['chat-sync-race-b']);
assert.equal(syncRaceHarness.window.currentChatId, 'chat-sync-race-b');
assert.equal(syncRaceQueue.peek().length, 0);
assert.deepEqual(syncRaceHarness.toasts, []);

// The owner/revision fence is also passed into the final chat projection. A
// load that resumes after A -> B refuses to mutate B's active workspace.
const loadRaceStorage = memoryStorage();
const loadRaceQueue = createNativePushActionQueue({ storage: loadRaceStorage });
loadRaceQueue.retain(pushAction('notification-load-race-a', 'chat-load-race-a', {}, OWNER_A));
let releaseLoadRace;
const loadRaceGate = new Promise(resolve => { releaseLoadRace = resolve; });
const loadRaceHarness = createHarness({
  queue: loadRaceQueue,
  storage: loadRaceStorage,
  chats: [{ id: 'chat-load-race-a' }],
  sync: async () => ({ success: true }),
  load: async ({ chatId, expectedBoundary, loadedChats, ownerId, revision, window }) => {
    await loadRaceGate;
    if (expectedBoundary.ownerId !== ownerId() || expectedBoundary.revision !== revision()) {
      return false;
    }
    window.currentChatId = chatId;
    loadedChats.push(chatId);
    return true;
  },
});
loadRaceHarness.ready();
await Promise.resolve();
loadRaceHarness.switchOwner(OWNER_B);
releaseLoadRace();
await flush();
assert.deepEqual(loadRaceHarness.loadedChats, []);
assert.equal(loadRaceHarness.window.currentChatId, null);
assert.equal(loadRaceQueue.peek().length, 0);

console.log('Native push handoff verified: durable retry, reload, ordering, and deduplication all pass; owner fencing passes.');
