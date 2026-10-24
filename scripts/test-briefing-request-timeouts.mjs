// scripts/test-briefing-request-timeouts.mjs
//
// Regression tests for the Home/Library briefing-request timeout hardening.
//
// Defects covered:
//  1. Library: a stall AFTER HTTP 200 headers arrived (body never completes)
//     aborted mid-response.json(), but the blanket catch substituted {} —
//     resolving as success instead of REQUEST_TIMEOUT with retry.
//     (Caught in pre-merge review.)
//  2. Home: an HTTP 200 response carrying {success:false} was swallowed by the
//     inner catch and resolved as {} — defeating the honest failure state.
//     (Caught in pre-merge review; preexisting behavior.)
//  3. Home/Library: a never-settling request hung forever — no timeout at all.
//     (The original defect.)
//
// These tests load the REAL production api() helpers:
//   - public/crump-vision-home-1.0.js    -> briefing api(path)
//   - public/crump-vision-library-1.0.js -> library api(path, timeoutMs)
// by extracting the contiguous block from the timeout constant through the
// end of api() and evaluating it in a node:vm sandbox with a stubbed fetch.
// The timeout constant is shortened from 15000ms to 120ms for test speed;
// the abort wiring under test is the production code path.
//
// Run: node scripts/test-briefing-request-timeouts.mjs

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const FAST_TIMEOUT_MS = 120;
const HOME_OWNER_ID = '11111111-1111-4111-8111-111111111111';
const HOME_AUTH_BOUNDARY = Object.freeze({ ownerId: HOME_OWNER_ID, revision: 7 });

function extractApiBlock(source, constName) {
  const start = source.indexOf(`var ${constName}`);
  if (start < 0) throw new Error(`timeout constant ${constName} not found`);
  const fnAt = source.indexOf('function api(', start);
  if (fnAt < 0) throw new Error('api() not found after ' + constName);
  let i = source.indexOf('{', fnAt);
  let depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) break;
    }
  }
  if (depth !== 0) throw new Error('unbalanced braces extracting api()');
  return source.slice(start, i + 1).replaceAll('15000', String(FAST_TIMEOUT_MS));
}

function loadApi(relPath, constName, authBoundary = null) {
  const src = readFileSync(path.join(ROOT, relPath), 'utf8');
  const block = extractApiBlock(src, constName);
  const sandbox = { fetch: null, AbortController, setTimeout, clearTimeout, Error };
  sandbox.globalThis = sandbox;
  // The production helpers run in a browser and intentionally resolve their
  // auth boundary through window. Keep this VM fixture browser-faithful rather
  // than weakening the production fail-closed owner check for Node.
  sandbox.window = sandbox;
  if (authBoundary) {
    sandbox.currentUser = { id: authBoundary.ownerId };
    sandbox.CrumpAuthBoundary = {
      authenticatedUserId: () => authBoundary.ownerId,
      revision: () => authBoundary.revision,
    };
  }
  vm.createContext(sandbox);
  vm.runInContext(`${block}\nglobalThis.__api = api;`, sandbox);
  return {
    setFetch(fn) { sandbox.fetch = fn; },
    call: (...args) => sandbox.__api(...args),
  };
}

function abortError() {
  const e = new Error('The operation was aborted.');
  e.name = 'AbortError';
  return e;
}

// A fetch stub whose promise never settles on its own; rejects with
// AbortError when the passed signal aborts (like a real hung fetch).
function hangingFetch() {
  return (_url, opts = {}) =>
    new Promise((_, reject) => {
      const signal = opts.signal;
      if (!signal) return; // never settles: simulates a pre-timeout world
      if (signal.aborted) return reject(abortError());
      signal.addEventListener('abort', () => reject(abortError()), { once: true });
    });
}

// A fetch stub whose headers resolve (HTTP 200) but whose body never
// completes; rejects the body read with AbortError on abort.
function stalledBodyFetch() {
  return (_url, opts = {}) => {
    const signal = opts.signal;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        new Promise((_, reject) => {
          if (!signal) return;
          if (signal.aborted) return reject(abortError());
          signal.addEventListener('abort', () => reject(abortError()), { once: true });
        }),
    });
  };
}

let pass = 0;
let fail = 0;
async function check(name, fn) {
  try {
    await fn();
    pass++;
    console.log(`PASS ${name}`);
  } catch (e) {
    fail++;
    console.log(`FAIL ${name} — ${e.message}`);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const home = loadApi(
  'public/crump-vision-home-1.0.js',
  'BRIEFING_TIMEOUT_MS',
  HOME_AUTH_BOUNDARY,
);
const library = loadApi('public/crump-vision-library-1.0.js', 'LIBRARY_TIMEOUT_MS');

// --- Home api() ---

await check('home: hanging request rejects with REQUEST_TIMEOUT', async () => {
  home.setFetch(hangingFetch());
  const t0 = Date.now();
  try {
    await home.call('/api/projects', HOME_AUTH_BOUNDARY);
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.code === 'REQUEST_TIMEOUT', `expected REQUEST_TIMEOUT, got ${e.code}`);
    assert(Date.now() - t0 < 5000, 'took too long — timeout did not fire');
  }
});

await check('home: HTTP 200 success:false rejects (not silent {})', async () => {
  home.setFetch(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ success: false, error: 'Workspace unavailable' }),
  }));
  try {
    await home.call('/api/projects', HOME_AUTH_BOUNDARY);
    assert(false, 'resolved as {} instead of rejecting');
  } catch (e) {
    assert(e.code !== 'REQUEST_TIMEOUT', 'wrong error kind');
    assert(/Workspace unavailable/.test(e.message), `error message lost: ${e.message}`);
  }
});

await check('home: HTTP 500 rejects with status error', async () => {
  home.setFetch(async () => ({ ok: false, status: 500, json: async () => ({}) }));
  try {
    await home.call('/api/projects', HOME_AUTH_BOUNDARY);
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.message === 'Request failed (500)', `unexpected message: ${e.message}`);
  }
});

await check('home: stalled body after 200 headers rejects REQUEST_TIMEOUT', async () => {
  home.setFetch(stalledBodyFetch());
  try {
    await home.call('/api/projects', HOME_AUTH_BOUNDARY);
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.code === 'REQUEST_TIMEOUT', `expected REQUEST_TIMEOUT, got ${e.code || e.message}`);
  }
});

await check('home: fast success still resolves data', async () => {
  let expectedOwner = '';
  home.setFetch(async (_url, options = {}) => {
    expectedOwner = options.headers?.['X-Ask-Crump-Expected-Owner'] || '';
    return { ok: true, status: 200, json: async () => ({ projects: [1] }) };
  });
  const data = await home.call('/api/projects', HOME_AUTH_BOUNDARY);
  assert(Array.isArray(data.projects) && data.projects.length === 1, 'data lost');
  assert(expectedOwner === HOME_OWNER_ID, 'authenticated Home request omitted its owner claim');
});

// --- Library api() ---

await check('library: stalled body after 200 headers rejects REQUEST_TIMEOUT (not {})', async () => {
  library.setFetch(stalledBodyFetch());
  try {
    await library.call('/api/library/books');
    assert(false, 'resolved as {} instead of rejecting — regression present');
  } catch (e) {
    assert(e.code === 'REQUEST_TIMEOUT', `expected REQUEST_TIMEOUT, got ${e.code || e.message}`);
  }
});

await check('library: hanging request rejects with REQUEST_TIMEOUT', async () => {
  library.setFetch(hangingFetch());
  try {
    await library.call('/api/library/books');
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.code === 'REQUEST_TIMEOUT', `expected REQUEST_TIMEOUT, got ${e.code}`);
  }
});

await check('library: explicit timeoutMs override is honored (distinguishable from default)', async () => {
  // Default is rewritten to 120ms for test speed; the override is 2000ms.
  // If the implementation ignored timeoutMs, this would reject at ~120ms.
  library.setFetch(hangingFetch());
  const t0 = Date.now();
  try {
    await library.call('/api/library/books', 2000);
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    const elapsed = Date.now() - t0;
    assert(e.code === 'REQUEST_TIMEOUT', `expected REQUEST_TIMEOUT, got ${e.code}`);
    assert(elapsed >= 1500, `override ignored: rejected after ${elapsed}ms (default is 120ms)`);
  }
});

await check('library: HTTP 200 success:false rejects', async () => {
  library.setFetch(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ success: false, error: 'Shelf unavailable' }),
  }));
  try {
    await library.call('/api/library/books');
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(/Shelf unavailable/.test(e.message), `error message lost: ${e.message}`);
  }
});

await check('library: HTTP 500 rejects with status error', async () => {
  library.setFetch(async () => ({ ok: false, status: 500, json: async () => ({}) }));
  try {
    await library.call('/api/library/books');
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.message === 'Request failed (500)', `unexpected message: ${e.message}`);
  }
});

await check('library: fast success still resolves data', async () => {
  library.setFetch(async () => ({ ok: true, status: 200, json: async () => ({ books: [1, 2] }) }));
  const data = await library.call('/api/library/books');
  assert(Array.isArray(data.books) && data.books.length === 2, 'data lost');
});

console.log(`\n${pass} passed, ${fail} failed`);

// --- Render-level regressions: the greeting summary must be failure-aware ---
//
// These drive the REAL render() from public/crump-vision-home-1.0.js in a
// node:vm sandbox with stubbed CrumpVision/document/fetch. The defect: on a
// one-endpoint failure the summary substituted [] for the failed section and
// still called greetingSub(projects, books), so a failed Projects request
// falsely read "0 projects in motion" and a failed Library request falsely
// read "nothing waiting on you".

function fakeNode() {
  return {
    children: [],
    innerHTML: '',
    textContent: '',
    className: '',
    _sel: {},
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) { return this._sel[sel] || null; },
    querySelectorAll() { return []; },
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {},
    getAttribute() { return null; },
  };
}

function loadHomeView() {
  const src = readFileSync(path.join(ROOT, 'public/crump-vision-home-1.0.js'), 'utf8')
    .replaceAll('15000', String(FAST_TIMEOUT_MS));
  const created = [];
  const cards = [];
  const win = {
    __crumpVisionShellLoaded: true,
    currentUser: { id: 'u1' },
    __crumpVisionDemo: false,
  };
  win.CrumpVision = {
    el: () => fakeNode(),
    eyebrow: () => fakeNode(),
    navigate: () => {},
    esc: (s) => String(s == null ? '' : s),
    card() {
      const card = fakeNode();
      const body = fakeNode();
      card._sel['.cv-card-copy'] = body;
      cards.push({ card, body });
      return card;
    },
    registerView(name, view) { win.__view = view; },
  };
  const sandbox = {
    fetch: null,
    AbortController, setTimeout, clearTimeout, Error,
    window: win,
    document: {
      createElement(tag) {
        const el = fakeNode();
        el.tagName = String(tag).toUpperCase();
        created.push(el);
        return el;
      },
      addEventListener() {},
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  if (!win.__view) throw new Error('home view was not registered');
  return {
    view: win.__view,
    setFetch(fn) { sandbox.fetch = fn; },
    findSub() {
      const el = created.find((e) => /cv-home-sub/.test(e.className));
      if (!el) throw new Error('greeting sub element not found');
      return el;
    },
    plateBody: () => cards[0].body,
    nudgeBody: () => cards[1].body,
  };
}

async function renderHome(fetchImpl) {
  const h = loadHomeView();
  h.setFetch(fetchImpl);
  const container = fakeNode();
  container.isConnected = true;
  h.view.render(container);
  await new Promise((r) => setTimeout(r, 100));
  return h;
}

const okProjectsFetch = async () => ({
  ok: true, status: 200,
  json: async () => ({ projects: [
    { name: 'Alpha', description: 'First', updated_at: '2026-10-18T00:00:00Z' },
    { name: 'Beta', description: 'Second', updated_at: '2026-10-17T00:00:00Z' },
  ] }),
});
const okBooksFetch = async () => ({
  ok: true, status: 200,
  json: async () => ({ books: [{ title: 'Keepsake' }] }),
});
const failFetch = async () => { throw new Error('boom'); };

await check('render: projects-only failure keeps an honest summary', async () => {
  const h = await renderHome((url) => (url.includes('/api/projects') ? failFetch(url) : okBooksFetch(url)));
  const sub = h.findSub().textContent;
  assert(!/0 projects in motion/.test(sub), `false empty claim in summary: "${sub}"`);
  assert(/couldn’t check your projects just now/i.test(sub), `missing honest projects state: "${sub}"`);
  assert(/keepsake is waiting/.test(sub), `library success lost from summary: "${sub}"`);
  assert(/Projects couldn’t load/.test(h.plateBody().innerHTML), 'plate missing honest error');
  assert(!/couldn’t load/i.test(h.nudgeBody().innerHTML), 'library section wrongly shows error');
});

await check('render: library-only failure keeps an honest summary', async () => {
  const h = await renderHome((url) => (url.includes('/api/library/books') ? failFetch(url) : okProjectsFetch(url)));
  const sub = h.findSub().textContent;
  assert(!/nothing waiting on you/.test(sub), `false empty claim in summary: "${sub}"`);
  assert(/couldn’t check your library just now/i.test(sub), `missing honest library state: "${sub}"`);
  assert(/2 projects in motion/.test(sub), `projects success lost from summary: "${sub}"`);
  assert(/Library couldn’t load/.test(h.nudgeBody().innerHTML), 'nudges missing honest error');
});

await check('render: both failed keeps the unreachable state', async () => {
  const h = await renderHome(() => failFetch());
  const sub = h.findSub().textContent;
  assert(/Couldn’t reach your workspace just now/.test(sub), `unexpected summary: "${sub}"`);
});

console.log(`render: ${pass} passed total, ${fail} failed total`);
process.exit(fail ? 1 : 0);
