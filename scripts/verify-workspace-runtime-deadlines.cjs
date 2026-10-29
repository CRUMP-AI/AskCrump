const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../public/runtime-body-v1.js'), 'utf8');
const nativeBuild = fs.readFileSync(path.join(__dirname, 'build-native.mjs'), 'utf8');
const templateStart = nativeBuild.indexOf('const loader = `');
const templateEnd = nativeBuild.indexOf('\nconst runtime = ', templateStart);
assert.ok(templateStart >= 0 && templateEnd > templateStart, 'native loader template must be discoverable');
const nativeSource = vm.runInNewContext(`${nativeBuild.slice(templateStart, templateEnd)}\nloader;`);
assert.equal(nativeSource.trim(), source.slice(source.indexOf('(() => {')).trim(), 'native and web must run the same bounded loader');
const flush = async () => { for (let index = 0; index < 100; index += 1) await Promise.resolve(); };

function harness(behavior = () => ({event: 'load', delay: 1}), runtimeSource = source) {
  let now = 0;
  let nextTimer = 0;
  const timers = new Map();
  const nodes = [];
  const attempts = [];
  const executed = [];
  const events = [];
  let choose = behavior;
  const document = {
    documentElement: {dataset: {}},
    querySelector(selector) {
      return nodes.find(node => {
        if (!node.connected) return false;
        const href = selector.match(/^link\[href="(.+)"\]$/);
        if (href) return node.tagName === 'LINK' && node.href === href[1];
        const data = selector.match(/^(link|script)\[data-([^=\]]+)(?:="([^\"]+)")?\]$/);
        if (!data || node.tagName.toLowerCase() !== data[1]) return false;
        const key = data[2].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        return data[3] ? node.dataset[key] === data[3] : key in node.dataset;
      }) || null;
    },
    createElement(tag) {
      const listeners = new Map();
      return {
        tagName: tag.toUpperCase(), dataset: {}, connected: false,
        addEventListener(type, callback) { listeners.set(type, callback); },
        removeEventListener(type, callback) { if (listeners.get(type) === callback) listeners.delete(type); },
        remove() { this.connected = false; },
        cloneNode() { const node = document.createElement(tag); node.href = this.href; node.rel = this.rel; return node; },
        fire(type) { listeners.get(type)?.(); },
        listenerCount() { return listeners.size; },
      };
    },
    head: {
      appendChild(node) {
        node.connected = true;
        nodes.push(node);
        if (node.rel === 'preload') return node;
        const kind = node.tagName === 'SCRIPT' ? 'script' : 'style';
        const url = node.src || node.href;
        const attempt = {node, kind, url, number: attempts.filter(item => item.url === url).length + 1};
        attempts.push(attempt);
        const result = choose(attempt) || {};
        if (result.event) {
          window.setTimeout(() => {
            if (result.event === 'load' && kind === 'script') executed.push(url);
            node.fire(result.event);
          }, result.delay ?? 1);
        }
        return node;
      },
    },
  };
  const window = {
    setTimeout(callback, delay) { const id = ++nextTimer; timers.set(id, {at: now + delay, callback}); return id; },
    clearTimeout(id) { timers.delete(id); },
    addEventListener() {},
    dispatchEvent(event) { events.push(event.type); },
  };
  const context = vm.createContext({window, document, CustomEvent: class { constructor(type) { this.type = type; } }});
  vm.runInContext(runtimeSource, context);
  return {
    window, document, attempts, executed, events, nodes, timers,
    setBehavior(next) { choose = next; },
    state() { return document.documentElement.dataset.crumpBodyRuntime; },
    load() {
      const result = {settled: false, error: null, promise: window.CrumpWorkspaceRuntime.load()};
      result.promise.then(() => { result.settled = true; }, error => { result.settled = true; result.error = error; });
      return result;
    },
    async advance(duration) {
      const target = now + duration;
      await flush();
      for (;;) {
        const next = [...timers].filter(([, timer]) => timer.at <= target).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
        if (!next) break;
        now = next[1].at;
        timers.delete(next[0]);
        next[1].callback();
        await flush();
      }
      now = target;
      await flush();
    },
  };
}

function assertClean(fixture) {
  assert.equal(fixture.timers.size, 0, 'settled runs must release all deadline timers');
  assert.equal(fixture.nodes.reduce((count, node) => count + node.listenerCount(), 0), 0, 'settled runs must remove all asset listeners');
}

(async () => {
  const successful = harness();
  const first = successful.load();
  assert.equal(first.promise, successful.window.CrumpWorkspaceRuntime.load(), 'concurrent calls must share the boot');
  await successful.advance(100);
  assert.equal(first.error, null);
  assert.equal(first.settled, true);
  assert.equal(successful.state(), 'ready');
  assert.equal(successful.attempts.filter(item => item.kind === 'style').length, 21);
  assert.equal(successful.executed.length, 35);
  assert.equal(new Set(successful.executed).size, 35, 'each ordered script must execute once');
  assert.match(successful.executed[0], /^\/onboarding\.js/);
  assert.match(successful.executed.at(-1), /^\/crump-activity-center-1\.0\.js/);
  assert.equal(successful.nodes.filter(node => node.rel === 'preload').length, 35);
  assert.match(successful.attempts.filter(item => item.kind === 'style').at(-1).url, /^\/crump-motion-system\.css/);
  const count = successful.attempts.length;
  await successful.window.CrumpWorkspaceRuntime.load();
  assert.equal(successful.attempts.length, count, 'ready runtime must reuse loaded assets');
  assert.deepEqual(successful.events, ['crump:body-runtime-ready']);
  assertClean(successful);

  const style = harness(attempt => attempt.url === '/billing.css' ? {} : {event: 'load'});
  const styleFailure = style.load();
  await style.advance(25_000);
  assert.equal(styleFailure.settled, true, 'two missing style events must settle');
  assert.equal(styleFailure.error.code, 'WORKSPACE_ASSET_TIMEOUT');
  assert.equal(styleFailure.error.reloadRequired, false);
  assert.equal(style.state(), 'failed');
  assert.equal(style.attempts.filter(item => item.url === '/billing.css').length, 2, 'style timeout gets one safe retry');
  assert.equal(style.executed.length, 0);
  for (const attempt of style.attempts.filter(item => item.url === '/billing.css')) {
    assert.equal(attempt.node.connected, false);
    attempt.node.fire('load');
  }
  await flush();
  assert.equal(style.state(), 'failed', 'late events cannot declare an abandoned boot ready');
  assertClean(style);
  style.setBehavior(() => ({event: 'load'}));
  const recovered = style.load();
  await style.advance(100);
  assert.equal(recovered.error, null);
  assert.equal(style.state(), 'ready');
  assert.equal(style.attempts.filter(item => item.url === '/billing.css').length, 3);
  assert.equal(style.attempts.filter(item => item.url === '/conversation.css?v=5.9.76-muse-release-repair-1').length, 1, 'successful styles survive asset-only recovery');
  assert.equal(style.executed.length, 35);
  assert.deepEqual(style.events, ['crump:body-runtime-ready']);
  assertClean(style);

  const definitive = harness(attempt => ({event: attempt.kind === 'script' && /profile-manager/.test(attempt.url) && attempt.number === 1 ? 'error' : 'load'}));
  const definitiveResult = definitive.load();
  await definitive.advance(100);
  assert.equal(definitiveResult.error, null);
  assert.equal(definitive.state(), 'ready');
  assert.equal(definitive.attempts.filter(item => item.kind === 'script').length, 36, 'a definitive network error gets exactly one retry');
  assert.equal(definitive.executed.length, 35);
  assert.equal(new Set(definitive.executed).size, 35);
  assertClean(definitive);

  const script = harness(attempt => attempt.kind === 'script' && /profile-manager/.test(attempt.url) ? {} : {event: 'load'});
  const scriptFailure = script.load();
  await script.advance(13_000);
  assert.equal(scriptFailure.settled, true);
  assert.equal(scriptFailure.error.code, 'WORKSPACE_ASSET_TIMEOUT');
  assert.equal(scriptFailure.error.reloadRequired, true);
  assert.equal(script.state(), 'failed');
  assert.equal(script.executed.length, 2, 'nothing after the missing third script executes');
  assert.equal(script.attempts.filter(item => item.kind === 'script').length, 3);
  const beforeRetry = script.attempts.length;
  const refused = script.load();
  await flush();
  assert.equal(refused.error, scriptFailure.error);
  assert.equal(script.attempts.length, beforeRetry, 'ambiguous scripts must never be inserted again in the same document');
  script.attempts.at(-1).node.fire('load');
  await script.advance(100);
  assert.equal(script.state(), 'failed');
  assert.equal(script.events.length, 0, 'late script load must not continue boot or announce ready');
  assertClean(script);

  const overall = harness(attempt => ({event: 'load', delay: attempt.kind === 'style' ? 10_000 : 1}));
  const overallFailure = overall.load();
  await overall.advance(35_001);
  assert.equal(overallFailure.settled, true, 'the whole boot must settle at its total budget');
  assert.equal(overallFailure.error.code, 'WORKSPACE_BOOT_TIMEOUT');
  assert.equal(overallFailure.error.reloadRequired, false);
  assert.equal(overall.state(), 'failed');
  assert.equal(overall.executed.length, 0);
  overall.setBehavior(() => ({event: 'load'}));
  const overallRecovery = overall.load();
  await overall.advance(100);
  assert.equal(overallRecovery.error, null);
  assert.equal(overall.state(), 'ready');
  assert.equal(overall.executed.length, 35);
  assert.equal(new Set(overall.executed).size, 35);
  await overall.advance(5_000); // Deliver the abandoned stylesheet's old event.
  assert.deepEqual(overall.events, ['crump:body-runtime-ready']);
  assertClean(overall);

  const scriptBudget = harness(attempt => ({event: 'load', delay: attempt.kind === 'script' ? 1_100 : 1}));
  const scriptBudgetFailure = scriptBudget.load();
  await scriptBudget.advance(35_001);
  assert.equal(scriptBudgetFailure.error.code, 'WORKSPACE_BOOT_TIMEOUT');
  assert.equal(scriptBudgetFailure.error.reloadRequired, true, 'total deadline must quarantine a script pending at cancellation');
  const budgetAttempts = scriptBudget.attempts.length;
  scriptBudget.load();
  await scriptBudget.advance(2_000);
  assert.equal(scriptBudget.state(), 'failed');
  assert.equal(scriptBudget.attempts.length, budgetAttempts);
  assert.equal(scriptBudget.events.length, 0);
  assertClean(scriptBudget);

  const native = harness(attempt => attempt.url === '/billing.css' ? {} : {event: 'load'}, nativeSource);
  const nativeFailure = native.load();
  await native.advance(25_000);
  assert.equal(nativeFailure.error.code, 'WORKSPACE_ASSET_TIMEOUT');
  native.setBehavior(() => ({event: 'load'}));
  const nativeRecovery = native.load();
  await native.advance(100);
  assert.equal(nativeRecovery.error, null);
  assert.equal(native.state(), 'ready');
  assert.equal(native.executed.length, 35);
  assertClean(native);

  console.log(JSON.stringify({success: true, nativeParity: true, cases: ['ordered cached success', 'style timeout and asset-only recovery', 'definitive script error retry', 'script timeout quarantine', 'total budget and style recovery', 'total budget script quarantine', 'native timeout and recovery']}));
})().catch(error => { console.error(error); process.exitCode = 1; });
