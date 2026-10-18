// scripts/test-rename-sync-cursor.mjs
//
// Regression test for the rename verification read's sync-cursor behavior.
//
// The defect it guards: the rename handler verified the new title with
// SyncManager.pull(null, {full:true}). A successful pull advances the
// crump_last_sync_v4 watermark, but the handler consumed only the renamed
// title and discarded every other row. A concurrent remote update to another
// chat that landed before that read was then skipped by the next incremental
// pull — silently lost until a later full pull.
//
// The fix: the verification read passes {peek:true}, a non-mutating read
// that leaves the watermark alone (sync-manager.js).
//
// Unlike test-rename-persistence.mjs (which stubs SyncManager), these tests
// load the REAL public/sync-manager.js and public/chat-sync.js in a
// node:vm sandbox, with only `fetch` mocked against a fake server that
// implements since-filtered pulls and compare-and-apply pushes. They prove:
//   1. a normal pull advances the merge cursor;
//   2. the rename verification read does not;
//   3. a concurrent remote update to another chat remains discoverable by
//      the next incremental pull;
//   4. (negative control) the legacy non-peek full read advances the cursor
//      and hides the concurrent update — the exact regression.
//
// Run: node scripts/test-rename-sync-cursor.mjs   (from the repo root)

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

// Fake server: since-filtered pulls, compare-and-apply pushes, deterministic clock.
function makeServer() {
  const rows = new Map();
  let clock = Date.parse('2026-10-18T01:00:00.000Z');
  const tick = () => new Date((clock += 1000)).toISOString();
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const toTime = (v) => new Date(v || 0).getTime();
  return {
    rows,
    seed(row) { rows.set(String(row.chat_id || row.id), clone(row)); },
    remoteUpdate(chat_id, patch) {
      const cur = clone(rows.get(String(chat_id)));
      const stamp = tick();
      rows.set(String(chat_id), { ...cur, ...clone(patch), updated_at: stamp, updatedAt: stamp });
    },
    handlePull(since) {
      const chats = [...rows.values()]
        .filter((r) => !since || toTime(r.updated_at) > toTime(since))
        .map(clone);
      return { success: true, serverTime: tick(), data: { chats } };
    },
    handlePush(chats) {
      const accepted = [];
      const ignored = [];
      for (const c of chats || []) {
        const id = String(c.chat_id || c.id);
        const cur = rows.get(id);
        const exT = toTime(c.updated_at);
        const exR = Number(c.revision || 1);
        if (!cur) { rows.set(id, clone(c)); accepted.push(id); continue; }
        const curT = toTime(cur.updated_at);
        const curR = Number(cur.revision || 1);
        const gate = exT > curT
          || (exT === curT && exR > curR)
          || JSON.stringify(c.messages) !== JSON.stringify(cur.messages);
        if (!gate) { ignored.push(id); continue; }
        const next = { ...cur };
        if (exT >= curT) next.title = c.title;
        next.messages = clone(c.messages || []);
        const w = new Date(Math.max(curT, exT, Date.now())).toISOString();
        next.updated_at = w;
        next.updatedAt = w;
        next.revision = Math.max(exR, curR + 1);
        rows.set(id, next);
        accepted.push(id);
      }
      return { success: true, accepted, ignored };
    },
  };
}

function buildSandbox() {
  const toasts = [];
  const store = new Map();      // SafeStorage
  const localStore = new Map(); // window.localStorage (cursor lives here)
  const docListeners = new Map();
  const bodyChildren = [];
  const server = makeServer();
  const fetchCalls = [];

  const okJson = (data) => ({
    ok: true,
    status: 200,
    json: async () => JSON.parse(JSON.stringify(data)),
  });
  const mockFetch = async (url, options = {}) => {
    const u = new URL(String(url), 'https://askcrump.com');
    const method = (options.method || 'GET').toUpperCase();
    fetchCalls.push(`${method} ${u.pathname}${u.search}`);
    if (u.pathname === '/api/sync/pull' && method === 'GET') {
      return okJson(server.handlePull(u.searchParams.get('since')));
    }
    if (u.pathname === '/api/sync/push' && method === 'POST') {
      const payload = JSON.parse(options.body || '{}');
      return okJson(server.handlePush(payload.chats || []));
    }
    return { ok: false, status: 404, json: async () => ({ success: false, error: 'not found' }) };
  };

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

  const windowStub = {
    chats: [],
    currentUser: { id: 'user-1' },
    innerWidth: 1280,
    innerHeight: 800,
    localStorage: {
      getItem: (k) => (localStore.has(k) ? localStore.get(k) : null),
      setItem: (k, v) => { localStore.set(k, String(v)); },
      removeItem: (k) => { localStore.delete(k); },
    },
    showToast: (message, type) => { toasts.push({ message, type }); },
    addEventListener() {},
    removeEventListener() {},
    // Immediate timers: installObservers (dialog wiring) is gated behind
    // setTimeout, so timers must fire. The requestJson abort timer also fires
    // immediately, but the mocked fetch ignores the abort signal.
    setTimeout: (fn) => { fn(); return 0; },
    clearTimeout: () => {},
    requestAnimationFrame: () => 0,
    renderChatsList: () => {},
    dispatchEvent: () => true,
  };

  const sandbox = {
    window: windowStub,
    document: documentStub,
    navigator: { onLine: true },
    location: { href: 'https://askcrump.com/app' },
    localStorage: windowStub.localStorage,
    SafeStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => { store.set(k, String(v)); },
      removeItem: (k) => { store.delete(k); },
    },
    fetch: mockFetch,
    AbortController,
    MutationObserver: class { observe() {} disconnect() {} },
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    Event: class Event { constructor(type) { this.type = type; } preventDefault() {} stopPropagation() {} },
    setTimeout: (fn) => { fn(); return 0; },
    clearTimeout: () => {},
    setInterval: () => 0,
    clearInterval: () => {},
    requestAnimationFrame: () => 0,
    crypto: { randomUUID: () => `00000000-0000-4000-8000-${String(Math.floor(Math.random() * 1e12)).padStart(12, '0')}` },
    console,
  };
  sandbox.globalThis = sandbox;
  createContext(sandbox);

  // Load the REAL production files: app (storage/normalization),
  // sync-manager (pull/push + watermark), chat-sync (pushLocal wiring),
  // crump-product (rename dialog + handler under test).
  runInContext(readPublic('app.js'), sandbox, { filename: 'app.js' });
  sandbox.STORAGE_KEYS = sandbox.window.STORAGE_KEYS;
  runInContext(readPublic('sync-manager.js'), sandbox, { filename: 'sync-manager.js' });
  runInContext(readPublic('chat-sync.js'), sandbox, { filename: 'chat-sync.js' });
  runInContext(readPublic('crump-product-5.3.1.js'), sandbox, { filename: 'crump-product-5.3.1.js' });

  assert.equal(typeof windowStub.SyncManager?.pull, 'function', 'real SyncManager.pull loaded');
  assert.ok(String(windowStub.syncChatsToServer).includes('pushLocal'), 'real chat-sync pushLocal wired');

  const api = {
    sandbox, toasts, server, fetchCalls,
    window: windowStub,
    cursor() {
      const raw = localStore.get('crump_last_sync_v4:user-1');
      return raw ? JSON.parse(raw) : null;
    },
    seedLocal(chats) {
      for (const c of chats) server.seed(c);
      windowStub.replaceChats(JSON.parse(JSON.stringify(chats)));
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

const tick = async (n = 24) => { for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r)); };

const T0 = '2026-10-18T01:00:00.000Z';
const CHAT_A = {
  chat_id: 'chat-a', id: 'chat-a', title: 'Old A title',
  messages: [{ role: 'user', content: 'hello a' }],
  created_at: T0, createdAt: T0, updated_at: T0, updatedAt: T0, revision: 1,
};
const CHAT_B = {
  chat_id: 'chat-b', id: 'chat-b', title: 'B title',
  messages: [{ role: 'user', content: 'hello b' }],
  created_at: T0, createdAt: T0, updated_at: T0, updatedAt: T0, revision: 1,
};

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('a normal pull advances the merge cursor; a peek verification read does not', async () => {
  const sb = buildSandbox();
  sb.seedLocal([{ ...CHAT_A }, { ...CHAT_B }]);
  assert.equal(sb.cursor(), null, 'no cursor before the first pull');
  await sb.window.SyncManager.pull();
  const c1 = sb.cursor();
  assert.ok(c1, 'normal pull advances the cursor');
  await sb.window.SyncManager.pull(null, { full: true, peek: true });
  assert.equal(sb.cursor(), c1, 'peek verification read leaves the cursor untouched');
  await sb.window.SyncManager.pull(null, { full: false });
  assert.notEqual(sb.cursor(), c1, 'normal incremental pull advances the cursor again');
});

test('rename verification does not advance the cursor; concurrent B stays discoverable', async () => {
  const sb = buildSandbox();
  sb.seedLocal([{ ...CHAT_A }, { ...CHAT_B }]);
  // Baseline: establish the merge cursor with a normal pull.
  await sb.window.SyncManager.pull();
  const c1 = sb.cursor();
  assert.ok(c1, 'baseline cursor established');
  // A concurrent remote update to chat B lands on another device.
  sb.server.remoteUpdate('chat-b', { title: 'B remote title' });
  // Drive the REAL rename handler for chat A end to end (real pushLocal,
  // real SyncManager.pull for the verification read, mocked fetch).
  const dlg = sb.openRenameDialog('chat-a');
  dlg.input.value = 'A new title';
  dlg.save.click();
  await tick();
  assert.ok(sb.toasts.some((t) => t.type === 'success'), 'rename confirmed via server readback');
  assert.equal(sb.server.rows.get('chat-a').title, 'A new title', 'server applied the rename');
  // THE regression assertion: the verification read must not move the cursor.
  assert.equal(sb.cursor(), c1, 'verification read did not advance the merge cursor');
  // The concurrent update to B is still discoverable by incremental sync.
  const inc = await sb.window.SyncManager.pull(null, { full: false });
  assert.ok(inc.success, 'incremental pull succeeded');
  const bRow = (inc.data.chats || []).find((r) => String(r.chat_id || r.id) === 'chat-b');
  assert.ok(bRow, 'concurrent B update returned by the incremental pull');
  assert.equal(bRow.title, 'B remote title', 'concurrent B update not skipped');
  assert.ok(sb.fetchCalls.some((c) => c.startsWith('GET /api/sync/pull?since=')), 'incremental pull used since=');
});

test('legacy non-peek full read advances the cursor and hides the concurrent update', async () => {
  // Negative control: this is what the pre-fix handler did. It must fail the
  // discoverability assertion, proving the regression test above is sensitive
  // to the cursor behavior.
  const sb = buildSandbox();
  sb.seedLocal([{ ...CHAT_A }, { ...CHAT_B }]);
  await sb.window.SyncManager.pull();
  const c1 = sb.cursor();
  sb.server.remoteUpdate('chat-b', { title: 'B remote title' });
  // The old handler's verification read: full pull WITHOUT peek.
  await sb.window.SyncManager.pull(null, { full: true });
  assert.notEqual(sb.cursor(), c1, 'legacy read advanced the cursor');
  const inc = await sb.window.SyncManager.pull(null, { full: false });
  const bRow = (inc.data.chats || []).find((r) => String(r.chat_id || r.id) === 'chat-b');
  assert.ok(!bRow, 'concurrent B update skipped after the cursor jumped (the bug)');
});

let failed = 0;
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
console.log(failed === 0 ? `\n${tests.length} passed` : `\n${failed} of ${tests.length} failed`);
process.exit(failed === 0 ? 0 : 1);
