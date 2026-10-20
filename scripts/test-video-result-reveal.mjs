#!/usr/bin/env node
// Regression coverage for the Video Studio player placement fix:
// renderReadyVideo renders into #crump53VideoResult, the LAST element of a
// tall studio dialog (after the create form AND the recent-videos list). On a
// phone the player landed below the fold — tapping a saved video appeared to
// do nothing until the user scrolled to the very bottom. renderReadyVideo now
// calls revealVideoResult() after paint, which scrolls the player to the top
// of the view when it is actually rendered, and stays out of the way when the
// studio is closed or on another section (no layout boxes → no scroll).
// These tests drive the REAL revealVideoResult extracted from the production
// source with stubbed DOM nodes.

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const sourcePath = resolve(process.env.PRODUCT53_SOURCE || 'public/crump-product-5.3.js');
const source = readFileSync(sourcePath, 'utf8');

function extractFunction(name) {
  const start = source.indexOf(`function ${name}`);
  if (start < 0) throw new Error(`function ${name} not found`);
  const open = source.indexOf('{', start);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error('unbalanced braces');
}

const fn = extractFunction('revealVideoResult');

let passed = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    console.error(`FAIL: ${name}\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`);
    process.exit(1);
  }
  passed += 1;
}

function makeNode({ connected = true, rects = [{}], withScroll = true } = {}) {
  const calls = [];
  const node = {
    isConnected: connected,
    getClientRects: () => rects,
  };
  if (withScroll) node.scrollIntoView = (options) => calls.push(options);
  return { node, calls };
}

function run(node) {
  const sandbox = { byId: () => node };
  vm.createContext(sandbox);
  vm.runInContext(`${fn}; this.__reveal = revealVideoResult;`, sandbox);
  sandbox.__reveal();
}

// A rendered (visible) player is scrolled to the top of the view.
{
  const { node, calls } = makeNode();
  run(node);
  check('visible node scrolls into view at top', calls, [{ behavior: 'smooth', block: 'start' }]);
}

// A hidden player (studio closed / another section: no layout boxes) is left alone.
{
  const { node, calls } = makeNode({ rects: [] });
  run(node);
  check('hidden node is not scrolled', calls, []);
}

// A detached node is left alone.
{
  const { node, calls } = makeNode({ connected: false });
  run(node);
  check('detached node is not scrolled', calls, []);
}

// A missing node is a no-op, not a throw.
{
  run(null);
  check('missing node does not throw', true, true);
}

// A node without scrollIntoView is a no-op, not a throw.
{
  const { node } = makeNode({ withScroll: false });
  run(node);
  check('node without scrollIntoView does not throw', true, true);
}

// Wiring: renderReadyVideo must actually schedule the reveal.
check(
  'renderReadyVideo schedules revealVideoResult',
  source.includes('requestAnimationFrame(() => revealVideoResult());'),
  true
);

console.log(`PASS: video-result-reveal (${passed}/${passed})`);
