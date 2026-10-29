'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const transport = fs.readFileSync(path.join(root, 'public/auth-resilience.js'), 'utf8');
const device = fs.readFileSync(path.join(root, 'public/device-auth.js'), 'utf8');

function harness(fetcher, cached = {id: 'account-a', email: 'a@example.test'}) {
  const values = new Map(cached ? [['crump_user_cache_v4', JSON.stringify(cached)]] : []);
  const window = {setTimeout, clearTimeout, addEventListener() {}, dispatchEvent() {}};
  const context = vm.createContext({window, fetch: fetcher, AbortController, setTimeout, clearTimeout,
    localStorage: {getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k)},
    navigator: {onLine: true, userAgent: 'synthetic-loopback-verifier'}, console: {warn() {}},
    CustomEvent: class {}, document: {querySelectorAll: () => []}});
  vm.runInContext(transport, context);
  vm.runInContext(device, context);
  return {window, values};
}
const response = data => ({ok: true, status: 200, json: async () => data});
const watchdog = p => Promise.race([p, new Promise((_,reject) => {
  const timer = setTimeout(() => reject(new Error('test exceeded settlement watchdog')), 1000);
  timer.unref();
})]);

(async () => {
  let signal;
  const blocked = harness(async (_url, init) => {signal = init.signal; return new Promise(() => {});});
  await assert.rejects(watchdog(blocked.window.CrumpAuthTransport.request('/api/auth/login', {}, {timeoutMs: 15})), {code: 'AUTH_REQUEST_TIMEOUT'});
  assert.equal(signal.aborted, true);
  const bodyBlocked = harness(async () => ({ok:true, json: () => new Promise(() => {})}));
  await assert.rejects(watchdog(bodyBlocked.window.CrumpAuthTransport.request('/api/auth/check-session', {}, {timeoutMs:15})), {code:'AUTH_REQUEST_TIMEOUT'});

  for (const malformed of [null, [], {}, {success:true}, {success:true, authenticated:true}, {success:false, authenticated:false}, {success:true, authenticated:true, data:{user:{id:''}}}]) {
    const h = harness(async () => response(malformed));
    const result = await h.window.deviceAuth.checkSession();
    assert.equal(result.unavailable, true, JSON.stringify(malformed));
    assert.ok(h.values.has('crump_user_cache_v4'), 'malformed response cleared saved identity');
    assert.equal((await h.window.deviceAuth.confirmIssuedSession()).status, 'unavailable');
  }
  const invalidJson = harness(async () => ({ok:true, status:200, json: async () => {throw new SyntaxError('bad JSON');}}));
  assert.equal((await invalidJson.window.deviceAuth.checkSession()).unavailable, true);
  assert.ok(invalidJson.values.has('crump_user_cache_v4'));
  const unavailable = harness(async () => ({ok:false,status:503,json:async () => ({success:false,authenticated:false,code:'AUTH_REQUIRED'})}));
  let unavailableClears = 0;
  unavailable.window.deviceAuth.clearLocalState = () => {unavailableClears++; return true;};
  assert.equal((await unavailable.window.deviceAuth.checkSession()).unavailable, true);
  assert.equal(unavailableClears, 0);
  assert.ok(unavailable.values.has('crump_user_cache_v4'));
  for (const user of [null, {}, {id:''}, {id:'   '}]) {
    const malformedLogin = harness(async () => response({success:true,data:{user}}));
    await assert.rejects(malformedLogin.window.deviceAuth.login('a@example.test','synthetic-password-only'), {code:'AUTH_INVALID_RESPONSE'});
    assert.equal(malformedLogin.window.deviceAuth.session, null);
  }

  const signedOut = harness(async () => response({success:true,authenticated:false}));
  let clearCalls = 0;
  signedOut.window.deviceAuth.clearLocalState = () => {clearCalls++; return true;};
  assert.equal((await signedOut.window.deviceAuth.checkSession()).authenticated, false);
  assert.equal(clearCalls, 1, 'explicit unauthenticated response must still clear identity');

  const ownerChanged = harness(async url => response(url.endsWith('/login')
    ? {success:true,data:{user:{id:'account-a', email:'a@example.test'}}}
    : {success:true,authenticated:true,data:{user:{id:'account-b',email:'b@example.test'}}}));
  assert.equal((await ownerChanged.window.deviceAuth.login('a@example.test','synthetic-password-only')).code, 'SESSION_OWNER_MISMATCH');
  assert.equal(ownerChanged.window.deviceAuth.session, null);

  const good = harness(async url => response(url.endsWith('/login')
    ? {success:true,data:{user:{id:'account-a',email:'a@example.test'}}}
    : {success:true,authenticated:true,data:{user:{id:'account-a',email:'a@example.test'}}}));
  const result = await good.window.deviceAuth.login('a@example.test','synthetic-password-only');
  assert.equal(result.success, true);
  assert.equal(good.window.deviceAuth.session.user.id, 'account-a');
  let posts = 0;
  let reads = 0;
  const committedResponseLoss = harness(async url => {
    if (url.endsWith('/login')) {
      posts++;
      return {ok:true,status:200,json:async () => {throw new SyntaxError('truncated after cookie committed');}};
    }
    reads++;
    return response({success:true,authenticated:true,data:{user:{id:'account-a',email:'a@example.test'}}});
  });
  const recovered = await committedResponseLoss.window.deviceAuth.login('a@example.test','synthetic-password-only');
  assert.equal(recovered.success, true);
  assert.equal(recovered.recovered, true);
  assert.equal(posts, 1);
  assert.equal(reads, 1);
  for (const incompleteUser of [null, {}, {id:''}, {id:'   '}]) {
    let shapePosts = 0;
    let shapeReads = 0;
    const shapeLoss = harness(async url => {
      if (url.endsWith('/login')) {
        shapePosts++;
        return response({success:true,data:{user:incompleteUser}});
      }
      shapeReads++;
      return response({success:true,authenticated:true,data:{user:{id:'account-a',email:'a@example.test'}}});
    });
    assert.equal((await shapeLoss.window.deviceAuth.login('a@example.test','synthetic-password-only')).recovered, true);
    assert.equal(shapePosts, 1);
    assert.equal(shapeReads, 1);
  }
  console.log('Auth transport settlement, malformed-response preservation, explicit sign-out and owner isolation passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
