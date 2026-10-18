// scripts/test-rename-persistence.mjs
//
// Regression tests for the conversation-rename persistence fix.
//
// The defect: the rename dialog captured the chat object at dialog-open; an
// intervening saveChats()/replaceChats() replaced every chat with a normalized
// copy, orphaning the captured reference; Save then mutated the orphan while
// saveChats() serialized the untouched canonical array — yet still announced
// "Conversation renamed."
//
// These tests load the REAL production files in a node:vm sandbox:
//   - public/app.js                 -> real saveChats / replaceChats /
//                                      normalizeLocalChat (identity-replacing)
//   - public/crump-product-5.3.1.js -> real rename dialog + Save handler
// and drive the actual handler through dialog-open -> intervening
// normalization -> Save.
//
// The sync layer is a FAITHFUL in-memory model of the production contract:
//   - push applies migrations/002 apply_chat_sync semantics (recency gate,
//     title CASE keeping the old title for older incoming rows, revision
//     advancement), returning real accepted/ignored lists;
//   - pull returns raw server rows (server-style snake_case fields), which is
//     what the handler's authoritative readback consumes.
// Seeded rows are server-style (updated_at, not only updatedAt), because
// normalizeLocalChat prefers updated_at.
//
// Run: node scripts/test-rename-persistence.mjs   (from the repo root)

import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { strict as assert } from 'node:assert';

const here = new URL('.', import.meta.url);
const readPublic = (name) => readFileSync(new URL(`../public/${name}`, here), 'utf8');

function makeElement(tag) {
  const listeners = new Map();
  const el = {
    tagName: String(tag).toUpperCase(),
    children: [],
    dataset: {},
    style: {},
    attributes: {},
    disabled: false,
    value: '',
    textContent: '',
    removed: false,
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute(k, v) { this.attributes[String(k)] = String(v); },
    getAttribute(k) { return this.attributes[String(k)] ?? null; },
    appendChild(child) { this.children.push(child); return child; },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener() {},
    click() {
      if (this.disabled) return;
      const evt = { preventDefault() {}, stopPropagation() {}, target: this };
      for (const fn of listeners.get('click') || []) fn(evt);
    },
    focus() {},
    select() {},
    remove() { this.removed = true; },
    contains(node) { return node === this; },
    getBoundingClientRect() { return { top: 0, bottom: 40, left: 0, right: 160 }; },
    querySelector(sel) {
      if (sel === 'input') return this._input || (this._input = makeElement('input'));
      if (sel === '.crump531-secondary') return this._cancel || (this._cancel = makeElement('button'));
      if (sel === '.crump531-primary') return this._save || (this._save = makeElement('button'));
      if (sel === '[data-crump531-action="rename"]') return this._renameBtn || (this._renameBtn = makeElement('button'));
      if (sel === '[data-crump531-action="delete"]') return this._deleteBtn || (this._deleteBtn = makeElement('button'));
      if (sel === '.chat-title') return { textContent: '' };
      return null;
    },
    querySelectorAll() { return []; },
    closest() { return null; },
  };
  return el;
}

// Faithful in-memory model of the production sync contract:
//  - push() mirrors migrations/002 apply_chat_sync: the recency gate, the
//    title CASE (old title retained when the incoming row is older), and
//    revision advancement; returns real accepted/ignored lists.
//  - pull() returns raw server rows, exactly what SyncManager.pull resolves
//    with (body.data.chats).
function makeFaithfulServer() {
  const rows = new Map();
  const toTime = (v) => { const t = new Date(v || 0).getTime(); return Number.isFinite(t) ? t : 0; };
  const sig = (m) => JSON.stringify(m || []);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  return {
    rows,
    seed(row) {
      const r = clone(row);
      rows.set(String(r.chat_id || r.id), r);
    },
    push(chats) {
      const accepted = [];
      const ignored = [];
      for (const c of chats || []) {
        const id = String(c.chat_id || c.id);
        const cur = rows.get(id);
        const exTime = toTime(c.updated_at);
        const exRev = Number(c.revision || 1);
        if (!cur) {
          rows.set(id, clone(c));
          accepted.push(id);
          continue;
        }
        const curTime = toTime(cur.updated_at);
        const curRev = Number(cur.revision || 1);
        const gate = exTime > curTime
          || (exTime === curTime && exRev > curRev)
          || sig(c.messages) !== sig(cur.messages);
        if (!gate) {
          ignored.push(id);
          continue;
        }
        const next = { ...cur };
        if (exTime >= curTime) next.title = c.title;
        next.messages = clone(c.messages || []);
        const w = new Date(Math.max(curTime, exTime, Date.now())).toISOString();
        next.updated_at = w;
        next.updatedAt = w;
        next.revision = Math.max(exRev, curRev + 1);
        rows.set(id, next);
        accepted.push(id);
      }
      return { success: true, accepted, ignored };
    },
    pull() {
      return {
        success: true,
        serverTime: new Date().toISOString(),
        data: { chats: [...rows.values()].map(clone) },
      };
    },
  };
}

function buildSandbox() {
  const toasts = [];
  const store = new Map();
  const docListeners = new Map();
  const bodyChildren = [];
  const pushedPayloads = [];
  const server = makeFaithfulServer();
  let syncImpl = null; // override for failure-shape tests
  let pullImpl = null; // override for readback tests
  let syncCalls = 0;

  const documentElement = makeElement('html');
  const body = makeElement('body');
  const origAppend = body.appendChild.bind(body);

  const documentStub = {
    readyState: 'complete',
    documentElement,
    body,
    activeElement: null,
    hidden: false,
    createElement: (tag) => makeElement(tag),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener(type, fn) {
      if (!docListeners.has(type)) docListeners.set(type, []);
      docListeners.get(type).push(fn);
    },
    removeEventListener() {},
  };
  body.appendChild = (child) => { bodyChildren.push(child); return origAppend(child); };

  const navigatorStub = { onLine: true };

  const windowStub = {
    chats: [],
    currentUser: { id: 'user-1' },
    innerWidth: 1280,
    innerHeight: 800,
    showToast: (message, type) => { toasts.push({ message, type }); },
    addEventListener() {},
    removeEventListener() {},
    requestAnimationFrame: () => 0,
    renderChatsList: () => {},
    dispatchEvent: () => true,
    syncChatsToServer: null, // assigned below
    SyncManager: null, // assigned below
  };

  const sandbox = {
    window: windowStub,
    document: documentStub,
    navigator: navigatorStub,
    location: { href: 'https://askcrump.com/app' },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    SafeStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => { store.set(k, String(v)); },
      removeItem: (k) => { store.delete(k); },
    },
    MutationObserver: class { observe() {} disconnect() {} },
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    Event: class Event { constructor(type) { this.type = type; } preventDefault() {} stopPropagation() {} },
    setTimeout: (fn) => { fn(); return 0; },
    clearTimeout: () => {},
    setInterval: () => 0,
    clearInterval: () => {},
    requestAnimationFrame: () => 0,
    crypto: { randomUUID: () => `00000000-0000-4000-8000-${String(Math.floor(Math.random() * 1e12)).padStart(12, '0')}` },
    fetch: () => Promise.reject(new Error('fetch not stubbed in rename tests')),
    console,
  };
  sandbox.globalThis = sandbox;
  createContext(sandbox);

  // Load the REAL production files under test.
  runInContext(readPublic('app.js'), sandbox, { filename: 'app.js' });
  runInContext(readPublic('crump-product-5.3.1.js'), sandbox, { filename: 'crump-product-5.3.1.js' });

  // Default: faithful sync plumbing. Individual tests override via
  // setSyncImpl / setPullImpl for failure-shape and readback cases.
  windowStub.syncChatsToServer = () => {
    syncCalls += 1;
    pushedPayloads.push(JSON.parse(JSON.stringify(windowStub.chats)));
    if (syncImpl) return syncImpl();
    return Promise.resolve(server.push(JSON.parse(JSON.stringify(windowStub.chats))));
  };
  windowStub.SyncManager = {
    pull: (...args) => {
      if (pullImpl) return pullImpl(...args);
      return Promise.resolve(server.pull());
    },
  };

  const api = {
    sandbox, toasts, store, docListeners, bodyChildren, pushedPayloads, server,
    navigator: navigatorStub,
    window: windowStub,
    makeElement,
    setSyncImpl(fn) { syncImpl = fn; syncCalls = 0; },
    setPullImpl(fn) { pullImpl = fn; },
    syncCalls: () => syncCalls,
    seedChat(chat) {
      // Seed both the faithful server (server-style row) and the client
      // (through the real production replaceChats normalization).
      server.seed(chat);
      windowStub.replaceChats([JSON.parse(JSON.stringify(chat))]);
    },
    canonical(id) {
      return (windowStub.chats || []).find((c) => String(c.id || c.chat_id) === String(id));
    },
    openRenameDialog(chatId) {
      const item = makeElement('div');
      item.dataset.chatId = chatId;
      const button = makeElement('button');
      button.closest = (sel) => (sel === '.crump531-chat-menu-button'
        ? button
        : sel === '.chat-item[data-chat-id]' ? item : null);
      for (const fn of docListeners.get('click') || []) {
        fn({ target: button, preventDefault() {}, stopPropagation() {} });
      }
      const menu = bodyChildren.filter((e) => e.className === 'crump531-chat-menu-popover').at(-1);
      assert.ok(menu, 'rename menu opened');
      menu.querySelector('[data-crump531-action="rename"]').click();
      const overlay = bodyChildren.filter((e) => e.className === 'crump531-rename-overlay').at(-1);
      assert.ok(overlay, 'rename dialog opened');
      return {
        overlay,
        input: overlay.querySelector('input'),
        save: overlay.querySelector('.crump531-primary'),
        cancel: overlay.querySelector('.crump531-secondary'),
      };
    },
  };
  return api;
}

const tick = async (n = 8) => { for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r)); };

// Server-style seed row: snake_case fields exactly as /api/sync/pull returns.
const T0 = '2026-10-18T00:30:00.000Z';
const CHAT = {
  chat_id: 'chat-qa-1',
  id: 'chat-qa-1',
  title: 'Reply with exactly QA_OK_20261018',
  messages: [
    { role: 'user', content: 'Reply with exactly: QA_OK_20261018' },
    { role: 'assistant', content: 'QA_OK_20261018' },
  ],
  created_at: T0,
  createdAt: T0,
  updated_at: T0,
  updatedAt: T0,
  revision: 1,
};

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('rename persists across an intervening saveChats normalization (faithful server)', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  // The real production saveChats() replaces every chat object with a
  // normalized copy, orphaning the dialog-open capture (the reported defect).
  // sync:false here: the test's setTimeout stub would otherwise collapse the
  // production 500ms debounce into a same-tick push, an artifact the real
  // timing does not have (pushLocal always reads fresh storage at fire time).
  sb.window.saveChats({ sync: false });
  dlg.input.value = 'QA readiness 2026-10-18';
  dlg.save.click();
  await tick();
  const current = sb.canonical('chat-qa-1');
  assert.equal(current.title, 'QA readiness 2026-10-18', 'canonical title updated');
  assert.ok(Number(current.revision) >= 2, 'revision advanced for the sync gate');
  // Blocker 2: both timestamp spellings must advance together, because
  // normalizeLocalChat prefers updated_at.
  assert.equal(current.updated_at, current.updatedAt, 'updated_at and updatedAt advance together');
  assert.ok(new Date(current.updated_at).getTime() > new Date(T0).getTime(), 'timestamp actually advanced past the seed');
  const lastPush = sb.pushedPayloads.at(-1)[0];
  assert.equal(lastPush.title, 'QA readiness 2026-10-18', 'pushed payload carries the new title');
  assert.equal(lastPush.updated_at, lastPush.updatedAt, 'pushed timestamps consistent');
  // Authoritative: the faithful server applied the title.
  assert.equal(sb.server.rows.get('chat-qa-1').title, 'QA readiness 2026-10-18', 'server row carries the new title');
  const success = sb.toasts.filter((t) => t.type === 'success');
  assert.equal(success.length, 1, 'exactly one success toast');
  assert.match(success[0].message, /renamed/i);
  assert.ok(!sb.toasts.some((t) => t.type === 'error'), 'no error toast');
  assert.ok(dlg.overlay.removed, 'dialog closed on confirmed success');
});

test('accepted push but server kept the old title is not reported as success', async () => {
  // accepted only proves a write was applied; the server keeps the old title
  // when the incoming row is older (apply_chat_sync title CASE). The client
  // must verify the server title, never trust accepted + local mutation.
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setPullImpl(() => Promise.resolve({
    success: true,
    data: { chats: [{ chat_id: 'chat-qa-1', title: 'Reply with exactly QA_OK_20261018' }] },
  }));
  dlg.save.click();
  await tick();
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success without server title match');
  assert.ok(sb.toasts.some((t) => t.type === 'error'), 'conflict error shown');
  assert.ok(!dlg.overlay.removed, 'dialog stays open for retry');
});

test('a message arriving while the dialog is open is preserved', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  const live = sb.canonical('chat-qa-1');
  live.messages = [...live.messages, { role: 'user', content: 'follow-up while renaming' }];
  sb.window.saveChats({ sync: false });
  dlg.input.value = 'QA readiness 2026-10-18';
  dlg.save.click();
  await tick();
  const current = sb.canonical('chat-qa-1');
  assert.equal(current.title, 'QA readiness 2026-10-18', 'title applied');
  assert.equal(current.messages.length, 3, 'late-arriving message not clobbered');
  assert.equal(sb.server.rows.get('chat-qa-1').title, 'QA readiness 2026-10-18', 'server applied the title');
});

test('renaming a deleted chat shows an error and does not resurrect it', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  sb.window.replaceChats([]);
  dlg.input.value = 'QA readiness 2026-10-18';
  dlg.save.click();
  await tick();
  assert.equal(sb.window.chats.length, 0, 'chat stays deleted');
  assert.equal(sb.syncCalls(), 0, 'no push for a missing chat');
  assert.ok(sb.toasts.some((t) => t.type === 'error'), 'error toast shown');
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success toast');
});

test('a genuinely ignored push yields conflict, not success', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  // Another device advances the server row beyond this client's version.
  const future = new Date(Date.now() + 3600_000).toISOString();
  const advanced = { ...CHAT, title: 'Other device title', updated_at: future, updatedAt: future, revision: 4 };
  sb.server.seed(advanced);
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  dlg.save.click();
  await tick();
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success toast on ignored push');
  assert.ok(sb.toasts.some((t) => t.type === 'error' && /elsewhere|confirm|again/i.test(t.message)), 'conflict toast shown');
  assert.ok(!dlg.overlay.removed, 'dialog stays open for retry');
  assert.equal(dlg.save.disabled, false, 'save re-enabled for retry');
});

test('offline queue yields info about syncing later, not an error', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.navigator.onLine = false;
  sb.setSyncImpl(() => Promise.resolve({ success: false, queued: true, flushed: false }));
  dlg.save.click();
  await tick();
  assert.equal(sb.canonical('chat-qa-1').title, 'QA readiness 2026-10-18', 'local title saved');
  assert.ok(sb.toasts.some((t) => t.type === 'info' && /back online/i.test(t.message)), 'offline info toast shown');
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no premature success toast');
  assert.ok(dlg.overlay.removed, 'dialog closed');
});

test('transport and server failures do not promise a future sync', async () => {
  for (const failure of [
    { success: false, queued: true, retryable: true, flushed: false, error: 'Synchronization timed out. Your work is still queued.' },
    { success: false, error: 'Unauthorized', queued: true, flushed: true },
    { success: false, error: 'Internal Server Error', queued: true, flushed: true },
  ]) {
    const sb = buildSandbox();
    sb.seedChat({ ...CHAT });
    const dlg = sb.openRenameDialog('chat-qa-1');
    dlg.input.value = 'QA readiness 2026-10-18';
    sb.setSyncImpl(() => Promise.resolve({ ...failure }));
    dlg.save.click();
    await tick();
    assert.ok(!sb.toasts.some((t) => /back online/i.test(t.message)), `no "back online" promise for ${failure.error}`);
    assert.ok(sb.toasts.some((t) => t.type === 'error'), `error toast shown for ${failure.error}`);
    assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success toast');
    assert.ok(!dlg.overlay.removed, 'dialog stays open for retry');
  }
});

test('a rejected push yields an error, not success', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncImpl(() => Promise.reject(new Error('network down')));
  dlg.save.click();
  await tick();
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success toast on failure');
  assert.ok(sb.toasts.some((t) => t.type === 'error'), 'error toast shown');
});

test('double save click pushes only once', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  dlg.save.click();
  dlg.save.click();
  await tick();
  assert.equal(sb.syncCalls(), 1, 'exactly one sync push');
  assert.equal(sb.toasts.filter((t) => t.type === 'success').length, 1, 'exactly one success toast');
});

test('unreadable server title after accept is info, not success', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setPullImpl(() => Promise.reject(new Error('pull failed')));
  dlg.save.click();
  await tick();
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success without readback');
  assert.ok(sb.toasts.some((t) => t.type === 'info' && /server confirmation is unavailable/i.test(t.message)), 'unconfirmed info shown');
  assert.ok(dlg.overlay.removed, 'dialog closed');
});

test('a tombstoned server row is rejected even when the title matches', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setPullImpl(() => Promise.resolve({
    success: true,
    data: { chats: [{ chat_id: 'chat-qa-1', title: 'QA readiness 2026-10-18', deleted_at: '2026-10-18T01:30:00.000Z' }] },
  }));
  dlg.save.click();
  await tick();
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success for a tombstoned row');
  assert.ok(sb.toasts.some((t) => t.type === 'error' && /elsewhere/i.test(t.message)), 'changed-elsewhere error shown');
  assert.ok(!dlg.overlay.removed, 'dialog stays open for retry');
});

test('reload round-trip keeps the renamed title, version and messages', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  dlg.save.click();
  await tick();
  const persistedKey = [...sb.store.keys()].find((k) => /chat/i.test(k));
  assert.ok(persistedKey, 'chats persisted to storage');
  const reloaded = JSON.parse(sb.store.get(persistedKey));
  const chat = reloaded.find((c) => String(c.id || c.chat_id) === 'chat-qa-1');
  assert.equal(chat.title, 'QA readiness 2026-10-18', 'title survives reload');
  assert.ok(Number(chat.revision) >= 2, 'revision survives reload');
  assert.equal(chat.messages.length, 2, 'messages survive reload');
});

let failed = 0;
let unhandledRejections = 0;
process.on('unhandledRejection', () => { unhandledRejections += 1; });
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    failed += 1;
    console.error(`FAIL - ${name}`);
    console.error(`  ${String(error && error.message || error).split('\n').join('\n  ')}`);
  }
}
if (unhandledRejections > 0) {
  failed += 1;
  console.error(`FAIL - ${unhandledRejections} unhandled promise rejection(s) leaked`);
}
console.log(failed === 0 ? `\n${tests.length} passed` : `\n${failed} of ${tests.length} failed`);
process.exit(failed === 0 ? 0 : 1);
