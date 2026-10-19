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

function loadApi(relPath, constName) {
  const src = readFileSync(path.join(ROOT, relPath), 'utf8');
  const block = extractApiBlock(src, constName);
  const sandbox = { fetch: null, AbortController, setTimeout, clearTimeout, Error };
  sandbox.globalThis = sandbox;
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

const home = loadApi('public/crump-vision-home-1.0.js', 'BRIEFING_TIMEOUT_MS');
const library = loadApi('public/crump-vision-library-1.0.js', 'LIBRARY_TIMEOUT_MS');

// --- Home api() ---

await check('home: hanging request rejects with REQUEST_TIMEOUT', async () => {
  home.setFetch(hangingFetch());
  const t0 = Date.now();
  try {
    await home.call('/api/projects');
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
    await home.call('/api/projects');
    assert(false, 'resolved as {} instead of rejecting');
  } catch (e) {
    assert(e.code !== 'REQUEST_TIMEOUT', 'wrong error kind');
    assert(/Workspace unavailable/.test(e.message), `error message lost: ${e.message}`);
  }
});

await check('home: HTTP 500 rejects with status error', async () => {
  home.setFetch(async () => ({ ok: false, status: 500, json: async () => ({}) }));
  try {
    await home.call('/api/projects');
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.message === 'Request failed (500)', `unexpected message: ${e.message}`);
  }
});

await check('home: stalled body after 200 headers rejects REQUEST_TIMEOUT', async () => {
  home.setFetch(stalledBodyFetch());
  try {
    await home.call('/api/projects');
    assert(false, 'resolved instead of rejecting');
  } catch (e) {
    assert(e.code === 'REQUEST_TIMEOUT', `expected REQUEST_TIMEOUT, got ${e.code || e.message}`);
  }
});

await check('home: fast success still resolves data', async () => {
  home.setFetch(async () => ({ ok: true, status: 200, json: async () => ({ projects: [1] }) }));
  const data = await home.call('/api/projects');
  assert(Array.isArray(data.projects) && data.projects.length === 1, 'data lost');
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
process.exit(fail ? 1 : 0);
