const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public', 'presence-manager.js'), 'utf8');
const listeners = new Map();
const scrubbers = [];
const providerRegistrations = [];
const serverRegistrations = [];
let ownerId = '11111111-1111-4111-8111-111111111111';
let revision = 1;
let resolveOwnerAPreferences;

function addEventListener(type, callback) {
  const callbacks = listeners.get(type) || [];
  callbacks.push(callback);
  listeners.set(type, callbacks);
}

function dispatch(type, detail = {}) {
  for (const callback of listeners.get(type) || []) callback({type, detail});
}

const windowObject = {
  currentUser: {id: ownerId},
  chats: [],
  currentChatId: null,
  addEventListener,
  dispatchEvent(event) {
    dispatch(event.type, event.detail);
  },
  CrumpAPI: {
    isNative: true,
    installationId: () => 'installation-auth-boundary-fixture',
  },
  CrumpAuthBoundary: {
    authenticatedUserId: () => ownerId,
    revision: () => revision,
    register(_name, callback) {
      scrubbers.push(callback);
      return () => {};
    },
  },
  CrumpNative: {
    Capacitor: {getPlatform: () => 'ios'},
    PushNotifications: {
      async checkPermissions() {
        return {receive: 'granted'};
      },
      async requestPermissions() {
        return {receive: 'granted'};
      },
      async register() {
        const registrationOwner = ownerId;
        providerRegistrations.push(registrationOwner);
        dispatch('crump:push-registration', {value: `token-${registrationOwner}`});
      },
    },
  },
};

const documentObject = {
  hidden: false,
  documentElement: {dataset: {crumpBodyRuntime: 'loading'}},
  addEventListener() {},
  getElementById() { return null; },
  querySelector() { return null; },
};

async function fetchMock(input, init = {}) {
  const url = String(input);
  const headers = new Headers(init.headers || {});
  const requestOwner = headers.get('X-Ask-Crump-Expected-Owner') || '';
  if (url === '/api/presence/preferences') {
    if (requestOwner === '11111111-1111-4111-8111-111111111111') {
      return new Promise(resolve => { resolveOwnerAPreferences = resolve; });
    }
    return new Response(JSON.stringify({preferences: {notifications_enabled: true}}), {
      status: 200,
      headers: {'Content-Type': 'application/json'},
    });
  }
  if (url === '/api/notifications/register') {
    serverRegistrations.push({
      ownerId: requestOwner,
      body: JSON.parse(String(init.body || '{}')),
    });
    return new Response(JSON.stringify({success: true}), {
      status: 200,
      headers: {'Content-Type': 'application/json'},
    });
  }
  throw new Error(`Unexpected request: ${url}`);
}

vm.runInNewContext(source, {
  AbortController,
  Headers,
  Intl,
  Response,
  SafeStorage: {getItem: () => null},
  console,
  document: documentObject,
  fetch: fetchMock,
  navigator: {onLine: true},
  queueMicrotask,
  sessionStorage: {getItem: () => null, removeItem() {}, setItem() {}},
  setInterval,
  clearInterval,
  setTimeout,
  clearTimeout,
  window: windowObject,
}, {filename: 'public/presence-manager.js'});

async function settle() {
  for (let index = 0; index < 8; index += 1) await new Promise(setImmediate);
}

(async () => {
  await settle();
  assert.equal(typeof resolveOwnerAPreferences, 'function');

  for (const scrub of scrubbers) scrub();
  ownerId = '22222222-2222-4222-8222-222222222222';
  revision += 1;
  windowObject.currentUser = {id: ownerId};
  dispatch('crump:authenticated-ready');
  await settle();

  resolveOwnerAPreferences(new Response(JSON.stringify({
    preferences: {notifications_enabled: true},
  }), {
    status: 200,
    headers: {'Content-Type': 'application/json'},
  }));
  await settle();

  assert.deepEqual(providerRegistrations, [ownerId]);
  assert.equal(serverRegistrations.length, 1);
  assert.equal(serverRegistrations[0].ownerId, ownerId);
  assert.equal(serverRegistrations[0].body.token, `token-${ownerId}`);
  assert.equal(
    serverRegistrations[0].body.installationId,
    'installation-auth-boundary-fixture',
  );
  process.stdout.write(JSON.stringify({
    staleOwnerIgnored: true,
    currentOwnerReregistered: true,
    ownerId,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
