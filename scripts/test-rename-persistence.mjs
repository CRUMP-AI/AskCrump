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
// normalization -> Save, asserting on the canonical window.chats array, the
// pushed payload, and truthful toast states (pending/success/conflict/
// offline/error). No reimplementation of the production behavior under test.
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

function buildSandbox() {
  const toasts = [];
  const store = new Map();
  const docListeners = new Map();
  const bodyChildren = [];
  const pushedPayloads = [];
  let syncBehavior = () => Promise.resolve({ success: true, accepted: [], ignored: [] });
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
    syncChatsToServer: null, // assigned per test via setSyncBehavior
  };

  const sandbox = {
    window: windowStub,
    document: documentStub,
    navigator: { onLine: true },
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

  const api = {
    sandbox, toasts, store, docListeners, bodyChildren, pushedPayloads,
    makeElement,
    window: windowStub,
    setSyncBehavior(fn) {
      syncBehavior = fn;
      syncCalls = 0;
      windowStub.syncChatsToServer = () => {
        syncCalls += 1;
        pushedPayloads.push(JSON.parse(JSON.stringify(windowStub.chats)));
        return syncBehavior();
      };
    },
    syncCalls: () => syncCalls,
    seedChat(chat) {
      windowStub.replaceChats([chat]);
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
  api.setSyncBehavior(() => Promise.resolve({ success: true, accepted: [], ignored: [] }));
  return api;
}

const tick = async (n = 6) => { for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r)); };
const CHAT = {
  chat_id: 'chat-qa-1',
  id: 'chat-qa-1',
  title: 'Reply with exactly QA_OK_20261018',
  messages: [
    { role: 'user', content: 'Reply with exactly: QA_OK_20261018' },
    { role: 'assistant', content: 'QA_OK_20261018' },
  ],
  revision: 1,
};

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('rename persists across an intervening saveChats normalization', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  // The real production saveChats() replaces every chat object with a
  // normalized copy, orphaning the dialog-open capture (the reported defect).
  sb.window.saveChats();
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.resolve({ success: true, accepted: ['chat-qa-1'], ignored: [] }));
  dlg.save.click();
  await tick();
  const current = sb.canonical('chat-qa-1');
  assert.equal(current.title, 'QA readiness 2026-10-18', 'canonical title updated');
  assert.ok(current.revision >= 2, 'revision advanced for the sync gate');
  assert.ok(new Date(current.updatedAt).getTime() > 0, 'updatedAt advanced');
  assert.equal(current.messages.length, 2, 'messages preserved');
  // The intervening saveChats() also fires its own debounced production push
  // (immediate under the test's setTimeout stub); the rename's explicit push is
  // the last one and must carry the new title.
  assert.ok(sb.pushedPayloads.length >= 1, 'at least one push');
  const lastPush = sb.pushedPayloads.at(-1);
  assert.equal(lastPush[0].title, 'QA readiness 2026-10-18', 'pushed payload carries the new title');
  const success = sb.toasts.filter((t) => t.type === 'success');
  assert.equal(success.length, 1, 'exactly one success toast');
  assert.match(success[0].message, /renamed/i);
  assert.ok(!sb.toasts.some((t) => t.type === 'error'), 'no error toast');
  assert.ok(dlg.overlay.removed, 'dialog closed on success');
});

test('rename works without an intervening save (control)', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.resolve({ success: true, accepted: ['chat-qa-1'], ignored: [] }));
  dlg.save.click();
  await tick();
  assert.equal(sb.canonical('chat-qa-1').title, 'QA readiness 2026-10-18');
  assert.equal(sb.toasts.filter((t) => t.type === 'success').length, 1);
});

test('a message arriving while the dialog is open is preserved', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  // Simulate an incoming message landing while the dialog is open, then a
  // production save (which also replaces object identities).
  const live = sb.canonical('chat-qa-1');
  live.messages = [...live.messages, { role: 'user', content: 'follow-up while renaming' }];
  sb.window.saveChats();
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.resolve({ success: true, accepted: ['chat-qa-1'], ignored: [] }));
  dlg.save.click();
  await tick();
  const current = sb.canonical('chat-qa-1');
  assert.equal(current.title, 'QA readiness 2026-10-18', 'title applied');
  assert.equal(current.messages.length, 3, 'late-arriving message not clobbered');
  assert.equal(current.messages[2].content, 'follow-up while renaming');
});

test('renaming a deleted chat shows an error and does not resurrect it', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  sb.window.replaceChats([]);
  dlg.input.value = 'QA readiness 2026-10-18';
  let syncCalled = false;
  sb.setSyncBehavior(() => { syncCalled = true; return Promise.resolve({ success: true, accepted: [], ignored: [] }); });
  dlg.save.click();
  await tick();
  assert.equal(sb.window.chats.length, 0, 'chat stays deleted');
  assert.equal(syncCalled, false, 'no push for a missing chat');
  assert.ok(sb.toasts.some((t) => t.type === 'error'), 'error toast shown');
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success toast');
});

test('an ignored push yields conflict, not success', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.resolve({ success: true, accepted: [], ignored: ['chat-qa-1'] }));
  dlg.save.click();
  await tick();
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no success toast on ignored push');
  assert.ok(sb.toasts.some((t) => t.type === 'error' && /elsewhere|confirm|again/i.test(t.message)), 'conflict toast shown');
  assert.ok(!dlg.overlay.removed, 'dialog stays open for retry');
  assert.equal(dlg.save.disabled, false, 'save re-enabled for retry');
});

test('an offline queued push yields info and keeps the local title', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.resolve({ success: false, queued: true }));
  dlg.save.click();
  await tick();
  assert.equal(sb.canonical('chat-qa-1').title, 'QA readiness 2026-10-18', 'local title saved');
  assert.ok(sb.toasts.some((t) => t.type === 'info' && /sync|online/i.test(t.message)), 'offline info toast shown');
  assert.ok(!sb.toasts.some((t) => t.type === 'success'), 'no premature success toast');
  assert.ok(dlg.overlay.removed, 'dialog closed');
});

test('a rejected push yields an error, not success', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.reject(new Error('network down')));
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
  sb.setSyncBehavior(() => Promise.resolve({ success: true, accepted: ['chat-qa-1'], ignored: [] }));
  dlg.save.click();
  dlg.save.click();
  await tick();
  assert.equal(sb.syncCalls(), 1, 'exactly one sync push');
  assert.equal(sb.toasts.filter((t) => t.type === 'success').length, 1, 'exactly one success toast');
});

test('reload round-trip keeps the renamed title, version and messages', async () => {
  const sb = buildSandbox();
  sb.seedChat({ ...CHAT });
  const dlg = sb.openRenameDialog('chat-qa-1');
  dlg.input.value = 'QA readiness 2026-10-18';
  sb.setSyncBehavior(() => Promise.resolve({ success: true, accepted: ['chat-qa-1'], ignored: [] }));
  dlg.save.click();
  await tick();
  // Simulate a reload: re-read the persisted canonical array from storage.
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
