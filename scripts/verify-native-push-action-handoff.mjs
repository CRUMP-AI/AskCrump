import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

import { createNativePushActionQueue } from './native-push-action-queue.mjs';

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

function pushAction(notificationId, chatId, extra = {}) {
  return {
    actionId: 'tap',
    notification: {
      id: notificationId,
      title: 'Private title that must not be persisted',
      body: 'Private body that must not be persisted',
      data: { chatId, ignored: 'not persisted' },
    },
    ...extra,
  };
}

function createHarness({ queue, storage, chats = [], sync, runtimeReady = false }) {
  const loadedChats = [];
  const scheduled = [];
  const microtasks = [];
  const windowTarget = eventTarget();
  const windowObject = {
    ...windowTarget,
    CrumpNative: {
      peekPendingPushActions: () => queue.peek(),
      acknowledgePushAction: queueId => queue.acknowledge(queueId),
    },
    CrumpAPI: { isNative: true, installationId: () => 'fixture-installation' },
    currentUser: { id: 'fixture-user' },
    currentChatId: null,
    chats,
    syncChatsFromServer: sync,
    loadChat(chatId) {
      const target = this.chats.find(chat => String(chat.id || chat.chat_id) === String(chatId));
      if (!target) return;
      this.currentChatId = String(chatId);
      loadedChats.push(String(chatId));
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
    window: windowObject,
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
assert.doesNotMatch(durableStorage.getItem('crump_native_push_actions_v1'), /Private title|Private body|ignored/);

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
  data: { chatId: 'chat-top-level' },
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

// A pre-upgrade pending-chat handoff must retry after a transient failure too.
const legacyStorage = memoryStorage();
legacyStorage.setItem('crump_pending_chat', 'chat-legacy');
const legacyQueue = createNativePushActionQueue({ storage: legacyStorage });
const legacyChats = [];
let legacySyncAttempts = 0;
const legacyHarness = createHarness({
  queue: legacyQueue,
  storage: legacyStorage,
  chats: legacyChats,
  sync: async () => {
    legacySyncAttempts += 1;
    if (legacySyncAttempts === 1) return { success: false, offline: true };
    legacyChats.push({ id: 'chat-legacy' });
    return { success: true };
  },
});
legacyHarness.ready();
await flush();
assert.equal(legacyStorage.getItem('crump_pending_chat'), 'chat-legacy');
assert.equal(legacyHarness.scheduled.length, 1);
legacyHarness.scheduled.shift()();
await flush();
assert.deepEqual(legacyHarness.loadedChats, ['chat-legacy']);
assert.equal(legacyStorage.getItem('crump_pending_chat'), null);

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

// A new queued tap arriving during legacy recovery is serialized after it.
const legacyRaceStorage = memoryStorage();
legacyRaceStorage.setItem('crump_pending_chat', 'chat-legacy-race');
const legacyRaceQueue = createNativePushActionQueue({ storage: legacyRaceStorage });
const legacyRaceChats = [];
let releaseLegacyRaceSync;
const legacyRaceSyncGate = new Promise(resolve => { releaseLegacyRaceSync = resolve; });
const legacyRaceHarness = createHarness({
  queue: legacyRaceQueue,
  storage: legacyRaceStorage,
  chats: legacyRaceChats,
  sync: async () => {
    await legacyRaceSyncGate;
    return { success: true };
  },
});
legacyRaceHarness.ready();
await Promise.resolve();
const newestDuringLegacy = legacyRaceQueue.retain(
  pushAction('notification-after-legacy', 'chat-after-legacy'),
);
legacyRaceHarness.window.dispatchEvent({ type: 'crump:push-action', detail: newestDuringLegacy });
legacyRaceChats.push({ id: 'chat-legacy-race' }, { id: 'chat-after-legacy' });
releaseLegacyRaceSync();
await flush();
assert.deepEqual(legacyRaceHarness.loadedChats, ['chat-legacy-race', 'chat-after-legacy']);
assert.equal(legacyRaceHarness.window.currentChatId, 'chat-after-legacy');
assert.equal(legacyRaceQueue.peek().length, 0);

// The queue is bounded and fallback identities are stable when a provider omits an ID.
const bounded = createNativePushActionQueue({ limit: 2, storage: memoryStorage() });
bounded.retain(pushAction('one', 'chat-one'));
const keptTwo = bounded.retain(pushAction('two', 'chat-two'));
const keptThree = bounded.retain(pushAction('three', 'chat-three'));
assert.deepEqual(bounded.peek().map(entry => entry.queueId), [keptTwo.queueId, keptThree.queueId]);
const fallback = { actionId: 'tap', notification: { data: { chatId: 'chat-fallback' } } };
const fallbackFirst = bounded.retain(fallback);
const fallbackSecond = bounded.retain({
  actionId: 'tap',
  notification: {
    title: 'Different private title',
    body: 'Different private body',
    data: { chatId: 'chat-fallback', ignored: 'still not identity' },
  },
});
assert.equal(fallbackFirst.queueId, fallbackSecond.queueId);
assert.equal(bounded.peek().length, 2, 'Private content changes must not create a new queue entry.');

const differentNavigation = bounded.retain({
  actionId: 'tap',
  notification: { data: { chatId: 'chat-other' } },
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
  notification: { data: { chatId: 'chat-shared', checkInId: 'check-in-one' } },
});
const duplicateCheckIn = checkInQueue.retain({
  actionId: 'tap',
  notification: {
    title: 'Changed private title',
    data: { chatId: 'chat-shared', checkInId: 'check-in-one' },
  },
});
const secondCheckIn = checkInQueue.retain({
  actionId: 'tap',
  notification: { data: { chatId: 'chat-shared', checkInId: 'check-in-two' } },
});
assert.equal(duplicateCheckIn.queueId, firstCheckIn.queueId);
assert.notEqual(secondCheckIn.queueId, firstCheckIn.queueId);
assert.equal(checkInQueue.peek().length, 2);

console.log('Native push handoff verified: durable retry, reload, ordering, and deduplication all pass.');
