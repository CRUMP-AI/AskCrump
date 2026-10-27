import { access, readdir, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createContext, runInContext } from 'node:vm';

const expectedFiles = new Set([
  'account-manager.js', 'app.js', 'appearance-theme.js', 'auth-controller.js', 'auth-resilience.js', 'billing-manager.js', 'chat-resilience.js', 'chat-sync.js',
  'crump-4.3.js', 'crump-4.4.js', 'crump-5.0.js', 'crump-billing-5.1.js',
  'crump-precision-image-edit.js', 'crump-precision-image-edit-loader.js',
  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-navigation-5.2.5.js',
  'crump-navigation-5.9.30.js',
  'crump-code-5.9.35.js', 'crump-code-loader.js',
  'credit-confirmation.js',
  'crump-v1.js', 'crump-v1-body.js', 'crump-v1-stability.js', 'crump-product-5.3.js', 'crump-product-loader.js',
  'crump-product-5.3.1.js', 'crump-subscriptions-5.3.2.js', 'crump-polish-5.6.js',
  'crump-library-5.7.js', 'crump-library-loader.js', 'crump-media-save.js',
  'crump-vision-chats-1.0.js',
  'crump-vision-home-1.0.js',
  'crump-vision-shell-1.0.js',
  'crump-vision-library-1.0.js', 'crump-vision-projects-1.0.js',
  'crump-vision-studios-1.0.js', 'crump-vision-you-1.0.js',
  'crump-vision-demo-1.0.js',
  'crump-activity-center-1.0.js',
  'device-auth.js', 'home-document-entry.js', 'install-prompt.js', 'landing.js', 'mobile-bridge.js', 'native-entry.js',
  'native-runtime.js', 'onboarding.js', 'presence-manager.js', 'profile-manager.js',
  'runtime-config.js', 'runtime-config-v1.js', 'runtime-body-v1.js', 'safe-storage.js',
  'scroll-manager.js', 'subscription-ui.js', 'sw.js', 'sync-manager.js', 'telemetry-config.js', 'ui-functions.js',
  'product-analytics.js', 'lifecycle-manager.js', 'lifecycle-share.js',
]);

const publicDirectory = new URL('../public/', import.meta.url);
const files = (await readdir(publicDirectory)).filter(name => name.endsWith('.js')).sort();

const unexpected = files.filter(name => !expectedFiles.has(name));
const missing = [...expectedFiles].filter(name => !files.includes(name));

if (unexpected.length || missing.length) {
  if (unexpected.length) console.error(`Unexpected JavaScript files: ${unexpected.join(', ')}`);
  if (missing.length) console.error(`Missing JavaScript files: ${missing.join(', ')}`);
  process.exit(1);
}

for (const name of files) {
  const path = new URL(name, publicDirectory);
  const source = await readFile(path, 'utf8');

  if (/console\.(log|debug|info)\s*\(/.test(source)) {
    console.error(`${name} contains a development console statement.`);
    process.exit(1);
  }

  // A later function declaration at the same lexical indentation silently
  // wins through hoisting. That made the Projects request wrapper shadow its
  // low-level transport while still passing syntax and handler-ownership
  // checks. Keep helper declarations unambiguous inside every browser asset.
  const namedFunctions = new Map();
  for (const match of source.matchAll(/^([ \t]*)(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/gm)) {
    const indentation = match[1].replaceAll('\t', '  ').length;
    const functionName = match[2];
    const key = `${indentation}:${functionName}`;
    const line = source.slice(0, match.index).split('\n').length;
    if (namedFunctions.has(key)) {
      console.error(
        `${name} redeclares function ${functionName} at the same lexical indentation `
        + `(lines ${namedFunctions.get(key)} and ${line}).`,
      );
      process.exit(1);
    }
    namedFunctions.set(key, line);
  }

  const result = spawnSync(process.execPath, ['--check', fileURLToPath(path)], { stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const syncManagerRuntimeSource = await readFile(new URL('sync-manager.js', publicDirectory), 'utf8');

async function exerciseSyncCursorRace() {
  const values = new Map();
  const requests = [];
  const localStorage = {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
  const syncWindow = {
    currentUser: {id: 'fixture-user'},
    addEventListener() {},
    setTimeout,
    clearTimeout,
  };
  const fixtureFetch = async (input, options = {}) => {
    const url = new URL(String(input), 'https://fixture.invalid');
    const method = String(options.method || 'GET').toUpperCase();
    requests.push({method, url});
    if (method === 'POST') {
      return new Response(JSON.stringify({
        success: true,
        serverTime: '2026-09-09T12:00:02.000Z',
        accepted: ['local-chat'],
        ignored: [],
      }), {status: 200, headers: {'Content-Type': 'application/json'}});
    }
    const hasUnsafePushCursor = url.searchParams.has('since');
    return new Response(JSON.stringify({
      success: true,
      serverTime: '2026-09-09T12:00:03.000Z',
      data: {
        chats: hasUnsafePushCursor ? [] : [{chat_id: 'concurrent-chat'}],
      },
    }), {status: 200, headers: {'Content-Type': 'application/json'}});
  };
  runInContext(syncManagerRuntimeSource, createContext({
    AbortController,
    Date,
    JSON,
    Math,
    Promise,
    Response,
    URL,
    crypto: {randomUUID: () => 'fixture-queue-entry'},
    fetch: fixtureFetch,
    localStorage,
    navigator: {onLine: true},
    window: syncWindow,
  }));

  await syncWindow.SyncManager.push(null, {
    chats: [{chat_id: 'local-chat'}],
    deletedChats: [],
  });
  const firstPull = await syncWindow.SyncManager.pull(null, {full: false});
  const firstGet = requests.find(request => request.method === 'GET');
  if (!firstGet || firstGet.url.searchParams.has('since') ||
      firstPull.data?.chats?.[0]?.chat_id !== 'concurrent-chat') {
    throw new Error('A push advanced the unread sync cursor and skipped a concurrent chat.');
  }

  await syncWindow.SyncManager.pull(null, {full: false});
  const gets = requests.filter(request => request.method === 'GET');
  if (gets[1]?.url.searchParams.get('since') !== '2026-09-09T12:00:03.000Z') {
    throw new Error('A completed pull did not advance the incremental sync cursor.');
  }
}

await exerciseSyncCursorRace();

async function exerciseSyncBatchDrain() {
  const values = new Map();
  const requests = [];
  const localStorage = {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
  const syncWindow = {
    currentUser: {id: 'batch-fixture-user', isGuest: true},
    addEventListener() {},
    setTimeout,
    clearTimeout,
  };
  const fixtureFetch = async (_input, options = {}) => {
    const body = JSON.parse(String(options.body || '{}'));
    requests.push(body);
    if (requests.length === 2) {
      return new Response(JSON.stringify({
        success: false,
        code: 'DATABASE_ERROR',
        error: 'Temporary fixture failure.',
      }), {status: 503, headers: {'Content-Type': 'application/json'}});
    }
    return new Response(JSON.stringify({
      success: true,
      serverTime: '2026-10-22T22:00:00.000Z',
      accepted: (body.chats || []).map(chat => chat.chat_id),
      ignored: (body.deletedChats || []).map(tombstone => tombstone.id),
    }), {status: 200, headers: {'Content-Type': 'application/json'}});
  };
  runInContext(syncManagerRuntimeSource, createContext({
    AbortController,
    Date,
    JSON,
    Math,
    Promise,
    Response,
    crypto: {randomUUID: () => 'batch-fixture-entry'},
    fetch: fixtureFetch,
    localStorage,
    navigator: {onLine: true},
    window: syncWindow,
  }));

  const chats = Array.from({length: 45}, (_, index) => ({chat_id: `chat-${index}`}));
  const deletedChats = Array.from({length: 23}, (_, index) => ({id: `deleted-${index}`}));
  const firstResult = await syncWindow.SyncManager.push(null, {
    chats,
    deletedChats,
    settings: {assistant_name: 'Crump'},
  });
  const queuedAfterFailure = JSON.parse(
    localStorage.getItem('crump_sync_queue_v4:batch-fixture-user') || '[]',
  );
  const result = await syncWindow.SyncManager.flush();
  const remaining = JSON.parse(
    localStorage.getItem('crump_sync_queue_v4:batch-fixture-user') || '[]',
  );
  if (firstResult.success !== false || firstResult.flushed !== true ||
      queuedAfterFailure.length !== 2 || !result.success || requests.length !== 4 ||
      remaining.length !== 0) {
    throw new Error('Bounded sync batches did not drain the complete local queue.');
  }
  if (requests.some(request => request.chats.length > 20 || request.deletedChats.length > 20)) {
    throw new Error('A sync request exceeded the server-authoritative guest batch bounds.');
  }
  if (JSON.stringify(requests[1]) !== JSON.stringify(requests[2])) {
    throw new Error('A failed bounded sync batch was not retained exactly for retry.');
  }
  const successfulRequests = [requests[0], requests[2], requests[3]];
  const sentChats = successfulRequests.flatMap(request => request.chats).map(chat => chat.chat_id);
  const sentTombstones = successfulRequests.flatMap(request => request.deletedChats).map(item => item.id);
  if (JSON.stringify(sentChats) !== JSON.stringify(chats.map(chat => chat.chat_id)) ||
      JSON.stringify(sentTombstones) !== JSON.stringify(deletedChats.map(item => item.id))) {
    throw new Error('A queued chat or tombstone was lost while draining bounded batches.');
  }
  if (successfulRequests[0].settings?.assistant_name !== 'Crump' ||
      successfulRequests.slice(1).some(request => request.settings !== null)) {
    throw new Error('Settings were not attached exactly once to the bounded sync sequence.');
  }
}

await exerciseSyncBatchDrain();

async function exerciseConcurrentSyncSnapshotMerge() {
  const values = new Map();
  const requests = [];
  const network = {onLine: false};
  const localStorage = {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
  const fixtureFetch = async (_input, options = {}) => {
    const body = JSON.parse(String(options.body || '{}'));
    requests.push(body);
    return new Response(JSON.stringify({
      success: true,
      accepted: (body.chats || []).map(chat => chat.chat_id),
      ignored: (body.deletedChats || []).map(item => item.id),
    }), {status: 200, headers: {'Content-Type': 'application/json'}});
  };
  const createTab = id => {
    const syncWindow = {
      currentUser: {id: 'concurrent-fixture-user'},
      addEventListener() {},
      setTimeout,
      clearTimeout,
    };
    runInContext(syncManagerRuntimeSource, createContext({
      AbortController,
      Date,
      JSON,
      Math,
      Number,
      Promise,
      Response,
      crypto: {randomUUID: () => `concurrent-entry-${id}`},
      fetch: fixtureFetch,
      localStorage,
      navigator: network,
      window: syncWindow,
    }));
    return syncWindow;
  };
  const firstTab = createTab('first');
  const secondTab = createTab('second');
  const chatId = '00000000-0000-4000-8000-000000000091';

  await firstTab.SyncManager.push(null, {
    chats: [{
      chat_id: chatId,
      title: 'Current title',
      messages: [
        {id: 'message-1', role: 'user', content: 'first', timestamp: '2026-10-22T20:00:00Z', metadata: {first: true}},
        {id: 'message-2', role: 'assistant', content: 'second', timestamp: '2026-10-22T20:00:01Z'},
      ],
      metadata: {firstTab: true},
      revision: 8,
      created_at: '2026-10-22T19:00:00Z',
      updated_at: '2026-10-22T20:00:02Z',
    }],
    deletedChats: [],
    settings: {preferences: {firstTab: true}},
  });
  await secondTab.SyncManager.push(null, {
    chats: [{
      chat_id: chatId,
      title: 'Stale title',
      messages: [
        {id: 'message-1', role: 'user', content: 'first', timestamp: '2026-10-22T20:00:00Z', metadata: {secondTab: true}},
        {id: 'message-3', role: 'user', content: 'parallel', timestamp: '2026-10-22T20:00:01.500Z'},
      ],
      metadata: {secondTab: true},
      revision: 7,
      created_at: '2026-10-22T19:00:00Z',
      updated_at: '2026-10-22T19:59:59Z',
    }],
    deletedChats: [],
    settings: {preferences: {secondTab: true}},
  });

  const mergedQueue = JSON.parse(
    localStorage.getItem('crump_sync_queue_v4:concurrent-fixture-user') || '[]',
  );
  const mergedChat = mergedQueue[0]?.payload?.chats?.[0];
  const messageIds = (mergedChat?.messages || []).map(message => message.id);
  if (mergedQueue.length !== 1 || mergedChat?.title !== 'Current title' ||
      mergedChat?.revision !== 8 || JSON.stringify(messageIds) !== JSON.stringify([
        'message-1', 'message-2', 'message-3',
      ]) || mergedChat?.metadata?.firstTab !== true || mergedChat?.metadata?.secondTab !== true ||
      mergedChat?.messages?.[0]?.metadata?.first !== true ||
      mergedChat?.messages?.[0]?.metadata?.secondTab !== true ||
      mergedQueue[0]?.payload?.settings?.preferences?.firstTab !== true ||
      mergedQueue[0]?.payload?.settings?.preferences?.secondTab !== true) {
    throw new Error('Concurrent stale same-chat snapshots were not merged without loss or duplicate IDs.');
  }

  network.onLine = true;
  await secondTab.SyncManager.flush();
  network.onLine = false;
  await firstTab.SyncManager.push(null, {
    chats: [],
    deletedChats: [{id: chatId, revision: 9, deleted_at: '2026-10-22T20:01:00Z'}],
  });
  await secondTab.SyncManager.push(null, {
    chats: [{
      chat_id: chatId,
      title: 'Stale resurrection',
      messages: [{id: 'message-4', role: 'user', content: 'late stale copy'}],
      revision: 7,
      updated_at: '2026-10-22T19:59:58Z',
    }],
    deletedChats: [],
  });
  const tombstoneQueue = JSON.parse(
    localStorage.getItem('crump_sync_queue_v4:concurrent-fixture-user') || '[]',
  );
  if (tombstoneQueue[0]?.payload?.chats?.length !== 0 ||
      tombstoneQueue[0]?.payload?.deletedChats?.[0]?.id !== chatId) {
    throw new Error('A stale concurrent snapshot displaced or resurrected a queued tombstone.');
  }
  network.onLine = true;
  await firstTab.SyncManager.flush();
  if (requests.length !== 2 || requests[0]?.chats?.[0]?.messages?.length !== 3 ||
      requests[1]?.chats?.length !== 0 || requests[1]?.deletedChats?.[0]?.id !== chatId ||
      JSON.parse(localStorage.getItem('crump_sync_queue_v4:concurrent-fixture-user') || '[]').length !== 0) {
    throw new Error('Merged snapshots or concurrent tombstones did not retain batch acknowledgement semantics.');
  }
}

await exerciseConcurrentSyncSnapshotMerge();

const landingRuntimeSource = await readFile(new URL('landing.js', publicDirectory), 'utf8');

function runLandingAttribution(
  url,
  storageValues,
  linkHref = '/app?signup=1&intent=projects',
  referrer = '',
  options = {},
) {
  const pageUrl = new URL(url);
  const listeners = new Map();
  const events = [];
  const link = {
    dataset: {cta: 'fixture', plan: 'free'},
    href: linkHref,
    getAttribute(name) { return name === 'href' ? this.href : null; },
    setAttribute(name, value) { if (name === 'href') this.href = value; },
    addEventListener(name, handler) { listeners.set(name, handler); },
  };
  const sessionStorage = {
    getItem(key) { return storageValues.has(key) ? storageValues.get(key) : null; },
    setItem(key, value) { storageValues.set(key, String(value)); },
    removeItem(key) { storageValues.delete(key); },
  };
  const document = {
    referrer,
    querySelectorAll(selector) { return selector === '[data-cta]' ? [link] : []; },
    querySelector() { return null; },
  };
  const location = {
    href: pageUrl.href,
    origin: pageUrl.origin,
    hostname: pageUrl.hostname,
    pathname: pageUrl.pathname,
    search: pageUrl.search,
    hash: pageUrl.hash,
  };
  const window = {};
  if (options.analytics !== 'queue') {
    window.va = options.analytics === 'throw'
      ? () => { throw new Error('Analytics unavailable'); }
      : (command, payload) => { events.push({command, payload}); };
  }
  runInContext(landingRuntimeSource, createContext({
    window,
    document,
    location,
    sessionStorage,
    URL,
    URLSearchParams,
    Date,
  }));
  if (options.click !== false) listeners.get('click')?.();
  const queuedEvents = (window.vaq || []).map(args => ({
    command: args[0],
    payload: args[1],
  }));
  return {link, events, queuedEvents};
}

function storedAttribution(storageValues) {
  const value = JSON.parse(storageValues.get('askcrump.first-touch-attribution') || 'null');
  if (value) {
    delete value.capturedAt;
    delete value.marketingLandingKind;
  }
  return value;
}

function assertAttribution(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    console.error(`${label} attribution mismatch.`, {actual, expected});
    process.exit(1);
  }
}

function marketingLandingEvents(result) {
  return [...result.events, ...result.queuedEvents]
    .filter(event => event.payload?.name === 'MarketingLanding');
}

function assertMarketingLanding(result, expected, label) {
  const events = marketingLandingEvents(result);
  const actual = events[0]?.payload?.data;
  const keys = actual ? Object.keys(actual).sort() : [];
  if (
    events.length !== 1
    || JSON.stringify(actual) !== JSON.stringify(expected)
    || JSON.stringify(keys) !== JSON.stringify(['intent', 'touchpoint'])
  ) {
    console.error(`${label} MarketingLanding mismatch.`, {events, expected});
    process.exit(1);
  }
}

function assertNoMarketingLanding(result, label) {
  const events = marketingLandingEvents(result);
  if (events.length) {
    console.error(`${label} unexpectedly emitted MarketingLanding.`, events);
    process.exit(1);
  }
}

const presentationTouch = {
  acquisition: 'instagram',
  placement: 'profile-link',
  campaign: 'presentation-proof-current',
  creative: null,
  intent: 'presentation',
};
const validPathStore = new Map();
const validPath = runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link&campaign=presentation-proof-current&intent=presentation',
  validPathStore,
  '/app?signup=1&intent=presentation',
);
assertAttribution(storedAttribution(validPathStore), presentationTouch, 'Valid campaign path');
assertMarketingLanding(validPath, {
  touchpoint: 'instagram.profile-link.presentation-proof-current',
  intent: 'presentation',
}, 'Valid campaign path');
const validDestination = new URL(validPath.link.href, 'https://askcrump.com');
const validCtaEvent = validPath.events.find(event => event.payload?.name === 'MarketingCTA');
if (validDestination.searchParams.get('campaign') !== 'presentation-proof-current' ||
    validDestination.searchParams.has('creative') ||
    validCtaEvent?.payload?.data?.campaign !== 'presentation-proof-current') {
  console.error('Valid campaign path did not reach the CTA and anonymous event.');
  process.exit(1);
}

const attributedSigninStore = new Map();
const attributedSignin = runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link&campaign=presentation-proof-current&intent=presentation',
  attributedSigninStore,
  '/app?source=presentation-nav-signin&plan=free&intent=presentation',
);
const attributedSigninDestination = new URL(attributedSignin.link.href, 'https://askcrump.com');
const attributedSigninEvent = attributedSignin.events.find(event => event.payload?.name === 'MarketingSignin');
if (attributedSigninDestination.searchParams.get('source') !== 'presentation-nav-signin' ||
    attributedSigninDestination.searchParams.get('acquisition') !== 'instagram' ||
    attributedSigninDestination.searchParams.get('campaign') !== 'presentation-proof-current' ||
    attributedSigninEvent?.payload?.data?.campaign !== 'presentation-proof-current' ||
    storedAttribution(attributedSigninStore)?.placement !== 'profile-link') {
  console.error('Attributed sign-in lost login intent or privacy-safe campaign context.');
  process.exit(1);
}

const profileLandingStore = new Map();
const profileLanding = runLandingAttribution(
  'https://askcrump.com/ai-project-workspace?acquisition=facebook&source=profile-link&campaign=real-product-continuity&intent=projects',
  profileLandingStore,
  '/app?signup=1&intent=projects',
  '',
  {click: false},
);
assertAttribution(storedAttribution(profileLandingStore), {
  acquisition: 'facebook',
  placement: 'profile-link',
  campaign: 'real-product-continuity',
  creative: null,
  intent: 'projects',
}, 'Creative-free profile campaign');
assertMarketingLanding(profileLanding, {
  touchpoint: 'facebook.profile-link.real-product-continuity',
  intent: 'projects',
}, 'Creative-free profile campaign');

const referralLanding = runLandingAttribution(
  'https://askcrump.com/?acquisition=referral&source=response-share',
  new Map(),
  '/app?signup=1',
  '',
  {click: false},
);
assertMarketingLanding(referralLanding, {
  touchpoint: 'referral.response-share',
  intent: 'unspecified',
}, 'Exact response-share referral');

const invalidMarketingUrls = [
  'https://askcrump.com/ai-project-workspace?acquisition=facebook&source=profile-link&campaign=real-product-continuity&creative=not-allowed&intent=projects',
  'https://askcrump.com/ai-project-workspace?acquisition=facebook&source=profile-link&campaign=not-registered&intent=projects',
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=not-registered&creative=continuity-feed',
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity',
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=presentation-feed',
  `https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=${'x'.repeat(33)}&creative=continuity-feed`,
  'https://askcrump.com/?acquisition=referral&source=response-share&campaign=not-registered&creative=anything',
  'https://askcrump.com/?acquisition=referral&source=response-share&campaign=real-product-continuity',
  'https://askcrump.com/?acquisition=referral&source=response-share&creative=continuity-feed',
  'https://askcrump.com/?acquisition=referral&source=response-share&campaign=real-product-continuity&creative=presentation-feed&intent=projects',
  `https://askcrump.com/?acquisition=referral&source=response-share&campaign=${'x'.repeat(33)}&creative=${'y'.repeat(33)}`,
  'https://askcrump.com/?acquisition=referral&source=response-share&campaign=&creative=',
  'https://askcrump.com/?acquisition=referral&source=response-share&intent=not-allowed',
  `https://askcrump.com/?acquisition=referral&source=response-share&intent=${'z'.repeat(33)}`,
  'https://askcrump.com/?acquisition=referral&source=response-share&intent=',
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=not-allowed',
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=',
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=organic-search&source=not-allowed&campaign=rough-idea-launch-plan&creative=search-article',
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=organic-search&source=&campaign=rough-idea-launch-plan&creative=search-article',
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=&utm_source=organic-search&source=workflow-guide&campaign=rough-idea-launch-plan&creative=search-article',
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=organic-search&utm_source=&source=workflow-guide&campaign=rough-idea-launch-plan&creative=search-article',
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=organic-search&source=workflow-guide&campaign=&creative=',
];
for (const [index, url] of invalidMarketingUrls.entries()) {
  const result = runLandingAttribution(url, new Map(), '/app?signup=1', '', {click: false});
  assertNoMarketingLanding(result, `Invalid marketing tuple ${index + 1}`);
}

const directLanding = runLandingAttribution(
  'https://askcrump.com/',
  new Map(),
  '/app?signup=1',
  '',
  {click: false},
);
assertNoMarketingLanding(directLanding, 'Direct landing');

const oncePerTabStore = new Map();
const firstLanding = runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=organic-social&campaign=presentation-proof-current&creative=ig-story',
  oncePerTabStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertMarketingLanding(firstLanding, {
  touchpoint: 'instagram.organic-social.presentation-proof-current.ig-story',
  intent: 'presentation',
}, 'First marketing URL in tab');
const secondLanding = runLandingAttribution(
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-story',
  oncePerTabStore,
  '/app?signup=1&intent=projects',
  '',
  {click: false},
);
assertNoMarketingLanding(secondLanding, 'Second marketing URL in same tab');
const sameTabNavigation = runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker',
  oncePerTabStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertNoMarketingLanding(sameTabNavigation, 'Same-tab navigation');

const queuedLanding = runLandingAttribution(
  'https://askcrump.com/ai-project-workspace?acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed',
  new Map(),
  '/app?signup=1&intent=projects',
  '',
  {analytics: 'queue', click: false},
);
assertMarketingLanding(queuedLanding, {
  touchpoint: 'facebook.organic-social.real-product-continuity.continuity-feed',
  intent: 'projects',
}, 'Queued analytics boundary');

const failedAnalyticsStore = new Map();
runLandingAttribution(
  'https://askcrump.com/ai-project-workspace?acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed',
  failedAnalyticsStore,
  '/app?signup=1&intent=projects',
  '',
  {analytics: 'throw', click: false},
);
if (failedAnalyticsStore.has('askcrump.marketing-landing-emitted')) {
  console.error('Analytics failure incorrectly marked a landing event as queued.');
  process.exit(1);
}

const profileChainStore = new Map();
runLandingAttribution(
  'https://askcrump.com/?acquisition=facebook&source=profile-link&campaign=presentation-proof-current&intent=presentation',
  profileChainStore,
  '/app?signup=1&intent=presentation',
);
const profileCapability = runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker',
  profileChainStore,
  '/app?signup=1&intent=presentation',
);
assertAttribution(storedAttribution(profileChainStore), {
  acquisition: 'facebook',
  placement: 'profile-link',
  campaign: 'presentation-proof-current',
  creative: null,
  intent: 'presentation',
}, 'Profile link to capability');
if (!profileCapability.link.href.includes('campaign=presentation-proof-current')) {
  console.error('Profile-link attribution did not survive the capability handoff.');
  process.exit(1);
}

const guideChainStore = new Map();
runLandingAttribution(
  'https://askcrump.com/guides/what-ai-project-should-remember?acquisition=instagram&source=organic-social&campaign=project-memory-boundaries&creative=project-memory-feed',
  guideChainStore,
);
const guideCapability = runLandingAttribution(
  'https://askcrump.com/ai-project-workspace',
  guideChainStore,
);
assertAttribution(storedAttribution(guideChainStore), {
  acquisition: 'instagram',
  placement: 'organic-social',
  campaign: 'project-memory-boundaries',
  creative: 'project-memory-feed',
  intent: 'projects',
}, 'Organic social to guide to capability');
if (!guideCapability.link.href.includes('campaign=project-memory-boundaries')) {
  console.error('Guide attribution did not survive the capability handoff.');
  process.exit(1);
}

const organicGuideStore = new Map();
runLandingAttribution(
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan',
  organicGuideStore,
  '/ai-project-workspace?acquisition=organic-search&source=workflow-guide&campaign=rough-idea-launch-plan&creative=search-article',
  'https://www.google.com/search?q=ai+project+launch+plan',
);
assertAttribution(storedAttribution(organicGuideStore), {
  acquisition: 'organic-search',
  placement: 'workflow-guide',
  campaign: 'rough-idea-launch-plan',
  creative: 'search-article',
  intent: 'projects',
}, 'Canonical organic-search guide entry');

const roughToUsefulTouch = {
  acquisition: 'facebook',
  placement: 'organic-social',
  campaign: 'rough-to-useful-v2',
  creative: 'rough-to-useful-current-feed',
  intent: 'projects',
};
let roughToUsefulRuntimeCases = 0;
const roughToUsefulStore = new Map();
const roughToUsefulValid = runLandingAttribution(
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=facebook&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  roughToUsefulStore,
  '/app?signup=1&intent=projects',
  '',
  {click: false},
);
assertAttribution(storedAttribution(roughToUsefulStore), roughToUsefulTouch, 'Rough-to-useful Facebook feed');
assertMarketingLanding(roughToUsefulValid, {
  touchpoint: 'facebook.organic-social.rough-to-useful-v2.rough-to-useful-current-feed',
  intent: 'projects',
}, 'Rough-to-useful Facebook feed');
roughToUsefulRuntimeCases += 1;

const roughToUsefulReelTouch = {
  acquisition: 'facebook',
  placement: 'organic-social',
  campaign: 'rough-to-useful-v2',
  creative: 'rough-to-useful-current-reel',
  intent: 'projects',
};
const roughToUsefulReelStore = new Map();
const roughToUsefulReelValid = runLandingAttribution(
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=facebook&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-reel',
  roughToUsefulReelStore,
  '/app?signup=1&intent=projects',
  '',
  {click: false},
);
assertAttribution(
  storedAttribution(roughToUsefulReelStore),
  roughToUsefulReelTouch,
  'Rough-to-useful Facebook Reel',
);
assertMarketingLanding(roughToUsefulReelValid, {
  touchpoint: 'facebook.organic-social.rough-to-useful-v2.rough-to-useful-current-reel',
  intent: 'projects',
}, 'Rough-to-useful Facebook Reel');
roughToUsefulRuntimeCases += 1;

runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=organic-social&campaign=presentation-proof-current&creative=ig-story',
  roughToUsefulReelStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertAttribution(
  storedAttribution(roughToUsefulReelStore),
  roughToUsefulReelTouch,
  'Rough-to-useful Reel second campaign in the same tab',
);
roughToUsefulRuntimeCases += 1;

const roughToUsefulInstagramStore = new Map();
const roughToUsefulInstagramValid = runLandingAttribution(
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=instagram&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  roughToUsefulInstagramStore,
  '/app?signup=1&intent=projects',
  '',
  {click: false},
);
assertAttribution(storedAttribution(roughToUsefulInstagramStore), {
  ...roughToUsefulTouch,
  acquisition: 'instagram',
}, 'Rough-to-useful Instagram feed');
assertMarketingLanding(roughToUsefulInstagramValid, {
  touchpoint: 'instagram.organic-social.rough-to-useful-v2.rough-to-useful-current-feed',
  intent: 'projects',
}, 'Rough-to-useful Instagram feed');
roughToUsefulRuntimeCases += 1;

for (const [label, invalidUrl] of [
  [
    'Rough-to-useful Facebook Story',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=facebook&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-story',
  ],
  [
    'Rough-to-useful Instagram Story',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=instagram&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-story',
  ],
]) {
  const rejected = runLandingAttribution(invalidUrl, new Map(), '/app?signup=1&intent=projects', '', {click: false});
  assertNoMarketingLanding(rejected, label);
  roughToUsefulRuntimeCases += 1;
}

runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=organic-social&campaign=presentation-proof-current&creative=ig-story',
  roughToUsefulStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertAttribution(storedAttribution(roughToUsefulStore), roughToUsefulTouch, 'Rough-to-useful second campaign');
roughToUsefulRuntimeCases += 1;
runLandingAttribution('https://askcrump.com/app?verified=1', roughToUsefulStore, '/app', '', {click: false});
assertAttribution(storedAttribution(roughToUsefulStore), roughToUsefulTouch, 'Rough-to-useful verification return');
roughToUsefulRuntimeCases += 1;
runLandingAttribution(
  'https://askcrump.com/app?signin=1&acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-story&intent=projects',
  roughToUsefulStore,
  '/app',
  '',
  {click: false},
);
assertAttribution(storedAttribution(roughToUsefulStore), roughToUsefulTouch, 'Rough-to-useful existing-account sign-in');
roughToUsefulRuntimeCases += 1;

const paidRoughToUsefulTouch = {
  acquisition: 'paid-social',
  placement: 'facebook-paid',
  campaign: 'rough-to-useful-v2',
  creative: 'rough-to-useful-current-feed',
  intent: 'projects',
};
const paidRoughToUsefulStore = new Map();
const paidRoughToUsefulGuide = runLandingAttribution(
  'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=facebook-paid&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  paidRoughToUsefulStore,
  '/ai-project-workspace',
  '',
  {click: false},
);
assertAttribution(
  storedAttribution(paidRoughToUsefulStore),
  paidRoughToUsefulTouch,
  'Paid rough-to-useful guide',
);
assertMarketingLanding(paidRoughToUsefulGuide, {
  touchpoint: 'paid-social.facebook-paid.rough-to-useful-v2.rough-to-useful-current-feed',
  intent: 'projects',
}, 'Paid rough-to-useful guide');
roughToUsefulRuntimeCases += 1;

const paidGuideDestination = new URL(paidRoughToUsefulGuide.link.href, 'https://askcrump.com');
const paidRoughToUsefulCapability = runLandingAttribution(
  paidGuideDestination.href,
  paidRoughToUsefulStore,
  '/app?signup=1&intent=projects',
  '',
  {click: false},
);
assertAttribution(
  storedAttribution(paidRoughToUsefulStore),
  paidRoughToUsefulTouch,
  'Paid rough-to-useful capability',
);
if (!paidRoughToUsefulCapability.link.href.includes('campaign=rough-to-useful-v2')) {
  console.error('Paid rough-to-useful attribution did not survive the capability handoff.');
  process.exit(1);
}
roughToUsefulRuntimeCases += 1;

for (const [label, invalidUrl] of [
  [
    'Paid acquisition with organic placement',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  ],
  [
    'Organic acquisition with paid placement',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=facebook&source=facebook-paid&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  ],
  [
    'Paid Story creative',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=facebook-paid&campaign=rough-to-useful-v2&creative=rough-to-useful-current-story',
  ],
  [
    'Paid Reel creative',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=facebook-paid&campaign=rough-to-useful-v2&creative=rough-to-useful-current-reel',
  ],
  [
    'Instagram paid cross-product',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=instagram&source=facebook-paid&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  ],
  [
    'Paid profile placement',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=profile-link&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  ],
  [
    'Paid workflow placement',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=workflow-guide&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
  ],
  [
    'Paid missing creative',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=facebook-paid&campaign=rough-to-useful-v2',
  ],
  [
    'Paid wrong campaign',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=paid-social&source=facebook-paid&campaign=presentation-proof-current&creative=rough-to-useful-current-feed',
  ],
  [
    'Paid wrong intent',
    'https://askcrump.com/ai-presentation-maker?acquisition=paid-social&source=facebook-paid&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed&intent=presentation',
  ],
]) {
  const rejected = runLandingAttribution(
    invalidUrl,
    new Map(),
    '/app?signup=1&intent=projects',
    '',
    {click: false},
  );
  assertNoMarketingLanding(rejected, label);
  roughToUsefulRuntimeCases += 1;
}

runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=organic-social&campaign=presentation-proof-current&creative=ig-story',
  paidRoughToUsefulStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertAttribution(
  storedAttribution(paidRoughToUsefulStore),
  paidRoughToUsefulTouch,
  'Paid rough-to-useful second campaign',
);
roughToUsefulRuntimeCases += 1;
runLandingAttribution('https://askcrump.com/app?verified=1', paidRoughToUsefulStore, '/app', '', {click: false});
assertAttribution(
  storedAttribution(paidRoughToUsefulStore),
  paidRoughToUsefulTouch,
  'Paid rough-to-useful verification return',
);
roughToUsefulRuntimeCases += 1;
runLandingAttribution(
  'https://askcrump.com/app?signin=1&acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=projects',
  paidRoughToUsefulStore,
  '/app',
  '',
  {click: false},
);
assertAttribution(
  storedAttribution(paidRoughToUsefulStore),
  paidRoughToUsefulTouch,
  'Paid rough-to-useful existing-account sign-in',
);
roughToUsefulRuntimeCases += 1;
if (roughToUsefulRuntimeCases !== 24) {
  console.error(`Expected 24 rough-to-useful runtime cases, got ${roughToUsefulRuntimeCases}.`);
  process.exit(1);
}

const wordPdfSearchTouch = {
  acquisition: 'organic-search',
  placement: 'workflow-guide',
  campaign: 'word-or-pdf-decision',
  creative: 'search-article',
  intent: 'document',
};
let wordPdfRuntimeCases = 0;
const wordPdfDirectStore = new Map();
const wordPdfDirect = runLandingAttribution(
  'https://askcrump.com/guides/word-or-pdf-ai-document-output',
  wordPdfDirectStore,
  '/app?signup=1&source=word-pdf-start&plan=professional&intent=document&acquisition=direct',
  '',
  {click: false},
);
assertAttribution(storedAttribution(wordPdfDirectStore), {
  acquisition: 'direct',
  placement: null,
  campaign: null,
  creative: null,
  intent: 'document',
}, 'Word/PDF direct guide entry');
assertNoMarketingLanding(wordPdfDirect, 'Word/PDF direct guide entry');
const wordPdfDirectDestination = new URL(wordPdfDirect.link.href, 'https://askcrump.com');
if (wordPdfDirectDestination.pathname !== '/app' ||
    wordPdfDirectDestination.searchParams.get('signup') !== '1' ||
    wordPdfDirectDestination.searchParams.get('plan') !== 'professional' ||
    wordPdfDirectDestination.searchParams.get('source') !== 'word-pdf-start' ||
    wordPdfDirectDestination.searchParams.get('intent') !== 'document' ||
    wordPdfDirectDestination.searchParams.get('acquisition') !== 'direct' ||
    wordPdfDirectDestination.searchParams.has('campaign') ||
    wordPdfDirectDestination.searchParams.has('creative')) {
  console.error('Word/PDF direct CTA did not remain campaign-free.');
  process.exit(1);
}
wordPdfRuntimeCases += 1;

const wordPdfSearchStore = new Map();
const wordPdfSearch = runLandingAttribution(
  'https://askcrump.com/guides/word-or-pdf-ai-document-output',
  wordPdfSearchStore,
  '/app?signup=1&source=word-pdf-start&plan=professional&intent=document&acquisition=direct',
  'https://www.google.com/search?q=word+or+pdf+ai+document',
  {click: false},
);
assertAttribution(storedAttribution(wordPdfSearchStore), wordPdfSearchTouch, 'Word/PDF canonical organic-search guide entry');
assertMarketingLanding(wordPdfSearch, {
  touchpoint: 'organic-search.workflow-guide.word-or-pdf-decision.search-article',
  intent: 'document',
}, 'Word/PDF canonical organic-search guide entry');
const wordPdfGuideDestination = new URL(wordPdfSearch.link.href, 'https://askcrump.com');
if (wordPdfGuideDestination.pathname !== '/app' ||
    wordPdfGuideDestination.searchParams.get('signup') !== '1' ||
    wordPdfGuideDestination.searchParams.get('plan') !== 'professional' ||
    wordPdfGuideDestination.searchParams.get('acquisition') !== 'organic-search' ||
    wordPdfGuideDestination.searchParams.get('source') !== 'workflow-guide' ||
    wordPdfGuideDestination.searchParams.get('campaign') !== 'word-or-pdf-decision' ||
    wordPdfGuideDestination.searchParams.get('creative') !== 'search-article') {
  console.error('Word/PDF guide CTA did not preserve the exact search tuple.');
  process.exit(1);
}
wordPdfRuntimeCases += 1;

for (const [label, url, expected] of [
  [
    'Word/PDF search Facebook rejection',
    'https://askcrump.com/guides/word-or-pdf-ai-document-output?acquisition=facebook&source=workflow-guide&campaign=word-or-pdf-decision&creative=search-article&intent=document',
    {acquisition: 'facebook', placement: 'workflow-guide', campaign: null, creative: null, intent: 'document'},
  ],
  [
    'Word/PDF search organic-social rejection',
    'https://askcrump.com/guides/word-or-pdf-ai-document-output?acquisition=organic-search&source=organic-social&campaign=word-or-pdf-decision&creative=search-article&intent=document',
    {acquisition: 'organic-search', placement: 'organic-social', campaign: null, creative: null, intent: 'document'},
  ],
  [
    'Word/PDF search social-campaign rejection',
    'https://askcrump.com/guides/word-or-pdf-ai-document-output?acquisition=organic-search&source=workflow-guide&campaign=word-or-pdf-social&creative=search-article&intent=document',
    {acquisition: 'organic-search', placement: 'workflow-guide', campaign: null, creative: null, intent: 'document'},
  ],
  [
    'Word/PDF search wrong-creative rejection',
    'https://askcrump.com/guides/word-or-pdf-ai-document-output?acquisition=organic-search&source=workflow-guide&campaign=word-or-pdf-decision&creative=word-pdf-feed&intent=document',
    {acquisition: 'organic-search', placement: 'workflow-guide', campaign: null, creative: null, intent: 'document'},
  ],
  [
    'Word/PDF search wrong-intent rejection',
    'https://askcrump.com/guides/word-or-pdf-ai-document-output?acquisition=organic-search&source=workflow-guide&campaign=word-or-pdf-decision&creative=search-article&intent=presentation',
    {acquisition: 'organic-search', placement: 'workflow-guide', campaign: null, creative: null, intent: 'presentation'},
  ],
]) {
  const rejectedStore = new Map();
  const rejected = runLandingAttribution(url, rejectedStore, '/app?signup=1&intent=document', '', {click: false});
  assertAttribution(storedAttribution(rejectedStore), expected, label);
  assertNoMarketingLanding(rejected, label);
  wordPdfRuntimeCases += 1;
}

runLandingAttribution(
  'https://askcrump.com/guides/editable-ai-powerpoint-review?acquisition=instagram&source=organic-social&campaign=editable-powerpoint-review&creative=presentation-story&intent=presentation',
  wordPdfSearchStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertAttribution(storedAttribution(wordPdfSearchStore), wordPdfSearchTouch, 'Word/PDF search second campaign in the same tab');
wordPdfRuntimeCases += 1;
runLandingAttribution('https://askcrump.com/app?verified=1', wordPdfSearchStore, '/app', '', {click: false});
assertAttribution(storedAttribution(wordPdfSearchStore), wordPdfSearchTouch, 'Word/PDF search verification return');
wordPdfRuntimeCases += 1;
runLandingAttribution(
  'https://askcrump.com/app?signin=1&acquisition=organic-search&source=workflow-guide&campaign=word-or-pdf-decision&creative=search-article&intent=document',
  wordPdfSearchStore,
  '/app',
  '',
  {click: false},
);
assertAttribution(storedAttribution(wordPdfSearchStore), wordPdfSearchTouch, 'Word/PDF search existing-account sign-in');
wordPdfRuntimeCases += 1;

if (wordPdfRuntimeCases !== 10) {
  console.error(`Expected ten Word/PDF attribution runtime cases, got ${wordPdfRuntimeCases}.`);
  process.exit(1);
}

const resumeAuditSearchTouch = {
  acquisition: 'organic-search',
  placement: 'workflow-guide',
  campaign: 'resume-bullet-truth-audit',
  creative: 'search-article',
  intent: 'resume',
};
let resumeAuditRuntimeCases = 0;
const resumeAuditDirectStore = new Map();
const resumeAuditDirect = runLandingAttribution(
  'https://askcrump.com/guides/audit-ai-resume-bullets',
  resumeAuditDirectStore,
  '/app?signup=1&source=resume-audit-start&plan=professional&intent=resume&acquisition=direct',
  '',
  {click: false},
);
assertAttribution(storedAttribution(resumeAuditDirectStore), {
  acquisition: 'direct',
  placement: null,
  campaign: null,
  creative: null,
  intent: 'resume',
}, 'Résumé audit direct guide entry');
assertNoMarketingLanding(resumeAuditDirect, 'Résumé audit direct guide entry');
const resumeAuditDirectDestination = new URL(resumeAuditDirect.link.href, 'https://askcrump.com');
if (resumeAuditDirectDestination.pathname !== '/app' ||
    resumeAuditDirectDestination.searchParams.get('signup') !== '1' ||
    resumeAuditDirectDestination.searchParams.get('plan') !== 'professional' ||
    resumeAuditDirectDestination.searchParams.get('source') !== 'resume-audit-start' ||
    resumeAuditDirectDestination.searchParams.get('intent') !== 'resume' ||
    resumeAuditDirectDestination.searchParams.get('acquisition') !== 'direct' ||
    resumeAuditDirectDestination.searchParams.has('campaign') ||
    resumeAuditDirectDestination.searchParams.has('creative')) {
  console.error('Résumé audit direct CTA did not remain campaign-free.');
  process.exit(1);
}
resumeAuditRuntimeCases += 1;

const resumeAuditSearchStore = new Map();
const resumeAuditSearch = runLandingAttribution(
  'https://askcrump.com/guides/audit-ai-resume-bullets',
  resumeAuditSearchStore,
  '/app?signup=1&source=resume-audit-start&plan=professional&intent=resume&acquisition=direct',
  'https://www.google.com/search?q=fact+check+ai+resume+bullets',
  {click: false},
);
assertAttribution(storedAttribution(resumeAuditSearchStore), resumeAuditSearchTouch, 'Résumé audit canonical organic-search guide entry');
assertMarketingLanding(resumeAuditSearch, {
  touchpoint: 'organic-search.workflow-guide.resume-bullet-truth-audit.search-article',
  intent: 'resume',
}, 'Résumé audit canonical organic-search guide entry');
const resumeAuditGuideDestination = new URL(resumeAuditSearch.link.href, 'https://askcrump.com');
if (resumeAuditGuideDestination.pathname !== '/app' ||
    resumeAuditGuideDestination.searchParams.get('signup') !== '1' ||
    resumeAuditGuideDestination.searchParams.get('plan') !== 'professional' ||
    resumeAuditGuideDestination.searchParams.get('acquisition') !== 'organic-search' ||
    resumeAuditGuideDestination.searchParams.get('source') !== 'workflow-guide' ||
    resumeAuditGuideDestination.searchParams.get('campaign') !== 'resume-bullet-truth-audit' ||
    resumeAuditGuideDestination.searchParams.get('creative') !== 'search-article' ||
    resumeAuditGuideDestination.searchParams.get('intent') !== 'resume') {
  console.error('Résumé audit guide CTA did not preserve the exact search tuple.');
  process.exit(1);
}
resumeAuditRuntimeCases += 1;

for (const [label, url, expected] of [
  [
    'Résumé audit Facebook rejection',
    'https://askcrump.com/guides/audit-ai-resume-bullets?acquisition=facebook&source=workflow-guide&campaign=resume-bullet-truth-audit&creative=search-article&intent=resume',
    {acquisition: 'facebook', placement: 'workflow-guide', campaign: null, creative: null, intent: 'resume'},
  ],
  [
    'Résumé audit organic-social rejection',
    'https://askcrump.com/guides/audit-ai-resume-bullets?acquisition=organic-search&source=organic-social&campaign=resume-bullet-truth-audit&creative=search-article&intent=resume',
    {acquisition: 'organic-search', placement: 'organic-social', campaign: null, creative: null, intent: 'resume'},
  ],
  [
    'Résumé audit social-campaign rejection',
    'https://askcrump.com/guides/audit-ai-resume-bullets?acquisition=organic-search&source=workflow-guide&campaign=resume-bullet-truth-audit-social&creative=search-article&intent=resume',
    {acquisition: 'organic-search', placement: 'workflow-guide', campaign: null, creative: null, intent: 'resume'},
  ],
  [
    'Résumé audit wrong-creative rejection',
    'https://askcrump.com/guides/audit-ai-resume-bullets?acquisition=organic-search&source=workflow-guide&campaign=resume-bullet-truth-audit&creative=resume-feed&intent=resume',
    {acquisition: 'organic-search', placement: 'workflow-guide', campaign: null, creative: null, intent: 'resume'},
  ],
  [
    'Résumé audit wrong-intent rejection',
    'https://askcrump.com/guides/audit-ai-resume-bullets?acquisition=organic-search&source=workflow-guide&campaign=resume-bullet-truth-audit&creative=search-article&intent=document',
    {acquisition: 'organic-search', placement: 'workflow-guide', campaign: null, creative: null, intent: 'document'},
  ],
]) {
  const rejectedStore = new Map();
  const rejected = runLandingAttribution(url, rejectedStore, '/app?signup=1&intent=resume', '', {click: false});
  assertAttribution(storedAttribution(rejectedStore), expected, label);
  assertNoMarketingLanding(rejected, label);
  resumeAuditRuntimeCases += 1;
}

runLandingAttribution(
  'https://askcrump.com/guides/word-or-pdf-ai-document-output?acquisition=organic-search&source=workflow-guide&campaign=word-or-pdf-decision&creative=search-article&intent=document',
  resumeAuditSearchStore,
  '/app?signup=1&intent=document',
  '',
  {click: false},
);
assertAttribution(storedAttribution(resumeAuditSearchStore), resumeAuditSearchTouch, 'Résumé audit second campaign in the same tab');
resumeAuditRuntimeCases += 1;
runLandingAttribution('https://askcrump.com/app?verified=1', resumeAuditSearchStore, '/app', '', {click: false});
assertAttribution(storedAttribution(resumeAuditSearchStore), resumeAuditSearchTouch, 'Résumé audit verification return');
resumeAuditRuntimeCases += 1;
runLandingAttribution(
  'https://askcrump.com/app?signin=1&acquisition=organic-search&source=workflow-guide&campaign=resume-bullet-truth-audit&creative=search-article&intent=resume',
  resumeAuditSearchStore,
  '/app',
  '',
  {click: false},
);
assertAttribution(storedAttribution(resumeAuditSearchStore), resumeAuditSearchTouch, 'Résumé audit existing-account sign-in');
resumeAuditRuntimeCases += 1;

if (resumeAuditRuntimeCases !== 10) {
  console.error(`Expected ten résumé audit attribution runtime cases, got ${resumeAuditRuntimeCases}.`);
  process.exit(1);
}

const immutableStore = new Map();
runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link&campaign=presentation-proof-current',
  immutableStore,
  '/app?signup=1&intent=presentation',
);
runLandingAttribution(
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-story',
  immutableStore,
);
assertAttribution(storedAttribution(immutableStore), {
  ...presentationTouch,
}, 'Second campaign in the same tab');

runLandingAttribution('https://askcrump.com/app?verified=1', immutableStore);
assertAttribution(storedAttribution(immutableStore), {
  ...presentationTouch,
}, 'Verification return');

runLandingAttribution(
  'https://askcrump.com/app?signin=1&acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=projects',
  immutableStore,
);
assertAttribution(storedAttribution(immutableStore), {
  ...presentationTouch,
}, 'Existing-account sign-in');

const repoRoot = new URL('../', import.meta.url);
const packageJson = JSON.parse(await readFile(new URL('package.json', repoRoot), 'utf8'));
const releaseVersion = String(packageJson.version || '');
const landingVersion = `${releaseVersion}-free-guest-entry-1`;
const planRendererVersion = `${releaseVersion}-credit-pack-accessibility-1`;
const commerceRecoveryVersion = `${releaseVersion}-commerce-recovery-1`;
const creditEntitlementSyncVersion = `${releaseVersion}-credit-entitlement-sync-1`;
const planStatusLineVersion = `${releaseVersion}-plan-status-line-1`;
const checkoutDestinationLabelVersion = `${releaseVersion}-checkout-destination-label-1`;
const creditPackTruthVersion = `${releaseVersion}-credit-pack-truth-1`;
const creditTruthVersion = `${releaseVersion}-credit-truth-1`;
const brandDeliveryVersion = `${releaseVersion}-brand-retina-1`;
const attachCreationRoutingVersion = `${releaseVersion}-explicit-button-types-1`;
const creditConfirmationVersion = `${releaseVersion}-credit-confirmation-1`;
const chatOwnerBoundaryVersion = `${releaseVersion}-chat-owner-boundary-1`;
const chatComposerOwnerBoundaryVersion = chatOwnerBoundaryVersion;
const settingsSaveIsolationVersion = `${releaseVersion}-settings-save-isolation-1`;
const outputProjectActionVersion = `${releaseVersion}-output-project-action-1`;
const studioActionLabelsVersion = `${releaseVersion}-studio-action-labels-1`;
const productStudioLazyLoadVersion = `${releaseVersion}-product-studio-lazy-load-2`;
const visibleWorkspaceReturnVersion = `${releaseVersion}-visible-workspace-return-1`;
const guestFreeContractVersion = `${releaseVersion}-guest-free-contract-2`;
const guestFreeWorkspaceRelease = 'workspaceRelease=guest-free-contract-2';
const releasedWorkspaceAsset = url => `${url}&${guestFreeWorkspaceRelease}`;
const accountOwnerBoundaryVersion = `${releaseVersion}-account-owner-boundary-1`;
const privateOwnerBoundaryVersion = `${releaseVersion}-private-owner-boundary-1`;
const legacyAttachmentOwnerBoundaryVersion = `${releaseVersion}-legacy-attachment-owner-fence-1`;
const workspaceOpenedRetryVersion = `${releaseVersion}-workspace-opened-retry-1`;
const authControllerVersion = `${releaseVersion}-free-capability-guest-entry-2`;
const continuityHandoffVersion = `${releaseVersion}-continuity-handoff-1`;
const composerModeResetVersion = `${releaseVersion}-composer-mode-reset-1`;
const accountDeletionStorageVersion = `${releaseVersion}-account-storage-deletion-1`;
const intelligenceReceiptVersion = `${releaseVersion}-intelligence-receipt-1`;
const intelligenceArchitectureVersion = `${releaseVersion}-intelligence-architecture-1`;
const composerActionabilityVersion = `${releaseVersion}-composer-actionability-1`;
const coreReliabilityVersion = `${releaseVersion}-core-reliability-1`;
const settingsProfileTrustVersion = `${releaseVersion}-settings-profile-trust-8`;
const precisionEditGuideLoaderVersion = `${releaseVersion}-live-image-preview-loader-1`;
const fileLibraryWindowVersion = `${releaseVersion}-file-library-window-1`;
const imageReferenceRecoveryVersion = `${releaseVersion}-image-reference-recovery-1`;
const liveImagePreviewVersion = `${releaseVersion}-precision-studio-1`;
const authBoundarySyncVersion = `${releaseVersion}-auth-boundary-sync-1`;
const initialChatOwnerReconciliationVersion = `${releaseVersion}-initial-chat-owner-reconciliation-1`;
const profileSettingsBoundaryVersion = accountOwnerBoundaryVersion;
const chatSyncVersion = initialChatOwnerReconciliationVersion;
const syncQueueVersion = authBoundarySyncVersion;
const imageNodeStabilityVersion = `${releaseVersion}-image-node-stability-1`;
const uploadedImageNodeStabilityVersion = `${releaseVersion}-uploaded-image-node-stability-1`;
const projectSaveMeasurementVersion = `${releaseVersion}-project-save-measurement-1`;
const outcomeIssueCategoriesVersion = `${releaseVersion}-outcome-issue-categories-1`;
const projectSaveOfferVersion = `${releaseVersion}-project-save-offer-1`;
const navigationDiscoveryVersion = `${releaseVersion}-navigation-discovery-1`;
const imageStudioEntryVersion = `${releaseVersion}-image-studio-entry-1`;
const museReleaseRepairVersion = `${releaseVersion}-muse-release-repair-1`;
const nativePushHandoffVersion = `${releaseVersion}-native-push-handoff-1`;
const nativePushOwnerFenceVersion = `${releaseVersion}-native-push-owner-fence-1`;
const cacheIntegrityVersion = `${releaseVersion}-friendly-workspace-1`;
const ownedWorkspaceAccessVersion = `${releaseVersion}-owned-workspace-access-1`;
const shellNoTaglineVersion = `${releaseVersion}-shell-no-tagline-1`;
const atelierWorkspaceVersion = `${releaseVersion}-atelier-workspace-1`;
const projectResumeVersion = `${releaseVersion}-project-resume-1`;
const projectResumeOwnerBoundaryVersion = `${releaseVersion}-project-resume-owner-boundary-1`;
const legacyProjectResumeTruthVersion = `${releaseVersion}-legacy-project-resume-truth-1`;
const responseContinuityCleanupVersion = `${releaseVersion}-response-continuity-cleanup-1`;
const manuscriptExportDeliveryVersion = `${releaseVersion}-manuscript-export-delivery-1`;
const libraryCrudPrivacyVersion = `${releaseVersion}-library-crud-privacy-1`;
const libraryReconciliationVersion = `${releaseVersion}-library-reconciliation-1`;
const homeDocumentEntryVersion = `${releaseVersion}-home-document-entry-1`;
const autonomousContinuityVersion = `${releaseVersion}-autonomous-continuity-1`;
const precisionAiPersistenceVersion = `${releaseVersion}-precision-ai-persistence-1`;
const runtimeBodyVersion = legacyProjectResumeTruthVersion;
const appearanceChoiceVersion = `${releaseVersion}-appearance-choice-3`;
const uiReleaseAuditVersion = `${releaseVersion}-ui-release-audit-2`;
const activityCenterVersion = autonomousContinuityVersion;
const uiGuardrailsVersion = `${releaseVersion}-ui-guardrails-1`;
const motionSystemVersion = `${releaseVersion}-motion-system-2`;
const documentDeliveryFocusedVersion = `${releaseVersion}-reference-fidelity-hard-contract-1`;
const outcomeRefinementRecoveryVersion = `${releaseVersion}-outcome-refinement-recovery-1`;
const authUpdateGuardVersion = `${releaseVersion}-update-work-guard-1`;
const userControlledScrollVersion = `${releaseVersion}-user-controlled-scroll-1`;
const newResponseCueVersion = `${releaseVersion}-new-response-cue-1`;
const videoDestinationVersion = `${releaseVersion}-video-destination-1`;
const navFocusVisibilityVersion = `${releaseVersion}-nav-focus-visibility-1`;
const destinationBackgroundGuardVersion = `${releaseVersion}-destination-background-guard-1`;
const codeLazyLoadVersion = `${releaseVersion}-code-lazy-load-1`;
const precisionLazyLoadVersion = `${releaseVersion}-precision-lazy-load-1`;
const libraryFirstRunVersion = `${releaseVersion}-library-first-run-1`;
const conversationActionLabelsVersion = `${releaseVersion}-conversation-action-labels-2`;
const lifecycleIdleSendVersion = `${releaseVersion}-lifecycle-idle-send-1`;
const settingsInviteVersion = `${releaseVersion}-settings-invite-1`;
const precisionEditEntryVersion = `${releaseVersion}-precision-edit-entry-1`;
const precisionEditStudioVersion = `${releaseVersion}-precision-studio-1`;
const creationSheetContainmentVersion = `${releaseVersion}-creation-sheet-containment-1`;
const referenceFidelityVersion = `${releaseVersion}-reference-fidelity-hard-contract-1`;
const groundedResearchVersion = `${releaseVersion}-grounded-research-1`;
const appOwnerBoundaryVersion = nativePushOwnerFenceVersion;
const presenceManagerVersion = nativePushOwnerFenceVersion;
const productOwnerBoundaryVersion = legacyProjectResumeTruthVersion;
const libraryOwnerBoundaryVersion = accountOwnerBoundaryVersion;
const codeOwnerBoundaryVersion = accountOwnerBoundaryVersion;
const projectsEmptyStateVersion = `${releaseVersion}-projects-empty-state-1`;
const requiredBodyFiles = [
  'public/appearance-controls.css',
  'public/appearance-theme.js',
  'public/crump-v1-body.css',
  'public/crump-v1-body.js',
  'public/crump-design-pass.css',
  'public/crump-activity-center-1.0.css',
  'public/crump-activity-center-1.0.js',
  'public/crump-ui-guardrails.css',
  'public/crump-motion-system.css',
  'public/crump-product-5.3.css',
  'public/crump-product-5.3.js',
  'public/crump-product-loader.js',
  'public/crump-product-5.3.1.css',
  'public/crump-product-5.3.1.js',
  'public/crump-subscriptions-5.3.2.js',
  'public/crump-polish-5.6.css',
  'public/crump-polish-5.6.js',
  'public/crump-library-5.7.css',
  'public/crump-library-5.7.js',
  'public/crump-library-loader.js',
  'public/crump-media-save.js',
  'public/crump-navigation-5.9.30.css',
  'public/crump-navigation-5.9.30.js',
  'public/crump-precision-image-edit.css',
  'public/crump-precision-image-edit.js',
  'public/crump-precision-image-edit-loader.js',
  'public/credit-confirmation.css',
  'public/credit-confirmation.js',
  'public/crump-code-5.9.35.css',
  'public/crump-code-5.9.35.js',
  'public/crump-code-loader.js',
  'public/runtime-body-v1.js',
  'public/lifecycle.css',
  'public/lifecycle-manager.js',
  'public/lifecycle-share.js',
  'public/auth-resilience.js',
  'public/chat-resilience.js',
  'public/assets/brand/crump-mark.png',
  'public/assets/brand/crump-mark.webp',
  'public/assets/brand/crump-mark-320.webp',
  'public/assets/brand/crump-horizontal-light.png',
  'public/assets/brand/crump-shell-lockup-light.png',
  'public/assets/brand/crump-shell-lockup-light.webp',
  'public/assets/brand/crump-horizontal-dark.png',
  'public/assets/brand/crump-mark-master.png',
  'public/assets/brand/crump-horizontal-light-master.png',
  'public/assets/brand/crump-horizontal-dark-master.png',
];

for (const relative of requiredBodyFiles) {
  try {
    await access(new URL(relative, repoRoot));
  } catch (_) {
    console.error(`Missing Ask Crump new-body file: ${relative}`);
    process.exit(1);
  }
}

const appHtml = await readFile(new URL('public/app.html', repoRoot), 'utf8');
const landingHtml = await readFile(new URL('public/ask-crump.html', repoRoot), 'utf8');
const authController = await readFile(new URL('public/auth-controller.js', repoRoot), 'utf8');
const desktopDestinationIds = Object.freeze(['ask', 'projects', 'files', 'library', 'video', 'autonomous']);
const desktopDestinationLabels = Object.freeze(['Ask', 'Projects', 'Files', 'Library', 'Video', 'Autonomous', 'Profile']);
const mobileDestinationIds = Object.freeze(['ask', 'projects', 'library', 'video', 'more']);
const mobileDestinationLabels = Object.freeze(['Ask', 'Projects', 'Library', 'Video', 'More']);
const moreDestinationIds = Object.freeze(['files', 'autonomous', 'profile']);
const moreDestinationLabels = Object.freeze(['Files', 'Autonomous', 'Profile']);
const legacyOwnerMap = Object.freeze({
  ask: 'ask', projects: 'projects', library: 'library', video: 'video', autonomous: 'code', profile: 'you',
});
const analyticsDestinationMap = Object.freeze({
  ask: 'ask', projects: 'projects', files: 'projects', library: 'library', video: 'video', autonomous: 'code', profile: 'you',
});
const onboardingSource = await readFile(new URL('public/onboarding.js', repoRoot), 'utf8');
const navigationSource = await readFile(new URL('public/crump-navigation-5.9.30.js', repoRoot), 'utf8');
const visionShellSource = await readFile(new URL('public/crump-vision-shell-1.0.js', repoRoot), 'utf8');
const listingSource = JSON.parse(await readFile(new URL('store/listing.en-US.json', repoRoot), 'utf8'));
const screenshotPlanSource = await readFile(new URL('store/screenshots/README.md', repoRoot), 'utf8');
const listingCopySource = await readFile(new URL('docs/STORE_LISTING_COPY.md', repoRoot), 'utf8');
const expectedScreenshotLabels = Object.freeze([
  'Ask', 'Projects', 'Files', 'Video', 'Research in Ask', 'Editable work', 'Library', 'Profile',
]);
const stringArray = (source, pattern) => {
  const match = source.match(pattern);
  return match ? [...match[1].matchAll(/'([^']+)'/g)].map(item => item[1]) : [];
};
const stringObject = (source, name) => {
  const match = source.match(new RegExp(`var ${name} = \\{([\\s\\S]*?)\\n\\s*\\};`));
  return match
    ? Object.fromEntries([...match[1].matchAll(/([a-z]+):\s*'([^']+)'/g)].map(item => [item[1], item[2]]))
    : {};
};
const shellDesktopDestinations = stringArray(visionShellSource, /var ORDER = \[([^\]]+)\];/);
const shellMobileDestinations = stringArray(visionShellSource, /var MOBILE_ORDER = \[([^\]]+)\];/);
const shellMoreDestinations = stringArray(visionShellSource, /var MORE_DESTINATIONS = \[([^\]]+)\];/);
const shellLegacyOwnerMap = stringObject(visionShellSource, 'NEW_TO_OLD');
const shellAnalyticsMap = stringObject(visionShellSource, 'ANALYTICS_SOURCE');
const tutorialDesktopDestinations = stringArray(
  onboardingSource,
  /const DESKTOP_DESTINATIONS = Object\.freeze\(\[([^\]]+)\]\);/,
);
const tutorialMobileDestinations = stringArray(
  onboardingSource,
  /const MOBILE_DESTINATIONS = Object\.freeze\(\[([^\]]+)\]\);/,
);
const tutorialMoreDestinations = stringArray(
  onboardingSource,
  /const MOBILE_MORE_DESTINATIONS = Object\.freeze\(\[([^\]]+)\]\);/,
);
const screenshotLabels = plan => Array.isArray(plan)
  ? plan.map(item => String(item || '').split(' —')[0].trim())
  : [];
const readmeScreenshotLabels = [...screenshotPlanSource.matchAll(/^\d+\.\s+([^\n—]+?)\s+—/gm)]
  .map(match => match[1].trim());
const releasedDesktopListingCopy = 'Ask, Projects, Files, Library, and Video';
const releasedStoreCopy = Object.freeze([
  listingSource.apple?.description || '',
  listingSource.google?.fullDescription || '',
  listingCopySource,
]);
const unreleasedStoreClaim = /\bAutonomous\b|professional beta/i;
if (JSON.stringify(shellDesktopDestinations) !== JSON.stringify(desktopDestinationIds) ||
    JSON.stringify(shellMobileDestinations) !== JSON.stringify(mobileDestinationIds) ||
    JSON.stringify(shellMoreDestinations) !== JSON.stringify(moreDestinationIds) ||
    JSON.stringify(shellLegacyOwnerMap) !== JSON.stringify(legacyOwnerMap) ||
    JSON.stringify(shellAnalyticsMap) !== JSON.stringify(analyticsDestinationMap) ||
    JSON.stringify(tutorialDesktopDestinations) !== JSON.stringify(desktopDestinationLabels) ||
    JSON.stringify(tutorialMobileDestinations) !== JSON.stringify(mobileDestinationLabels) ||
    JSON.stringify(tutorialMoreDestinations) !== JSON.stringify(moreDestinationLabels) ||
    JSON.stringify(screenshotLabels(listingSource.apple?.screenshotPlan)) !== JSON.stringify(expectedScreenshotLabels) ||
    JSON.stringify(screenshotLabels(listingSource.google?.screenshotPlan)) !== JSON.stringify(expectedScreenshotLabels) ||
    JSON.stringify(readmeScreenshotLabels) !== JSON.stringify(expectedScreenshotLabels) ||
    !releasedStoreCopy.every(source => source.includes(releasedDesktopListingCopy)) ||
    releasedStoreCopy.some(source => unreleasedStoreClaim.test(source)) ||
    !desktopDestinationLabels.every(label => onboardingSource.includes(`destination: '${label}'`)) ||
    !visionShellSource.includes("sourceKey === 'home' || sourceKey === 'studios' || sourceKey === 'you'") ||
    !visionShellSource.includes('data-cv-destination="profile"') ||
    !visionShellSource.includes('aria-haspopup="dialog" aria-controls="cvMoreMenu" aria-expanded="false"')) {
  console.error('Navigation, workspace guide, and store-release sources disagree on the friendly workspace contract.');
  process.exit(1);
}
if (!releaseVersion || !landingHtml.includes(`/landing.js?v=${landingVersion}`)) {
  console.error('Ask Crump marketing page is missing its release-versioned script.');
  process.exit(1);
}

const appearanceThemeUrl = `/appearance-theme.js?v=${appearanceChoiceVersion}`;
const appearanceControlsUrl = `/appearance-controls.css?v=${appearanceChoiceVersion}`;
if (!appHtml.includes(`src="${appearanceThemeUrl}"`) ||
    !appHtml.includes(`href="${appearanceControlsUrl}"`) ||
    appHtml.indexOf(appearanceThemeUrl) > appHtml.indexOf('/crump-v1-body.css') ||
    !appHtml.includes('<html lang="en" data-theme="light">')) {
  console.error('Ask Crump appearance assets must load before the workspace cascade with Light as the stable default.');
  process.exit(1);
}

const speedInsightPages = [
  ['public/ask-crump.html', '/'],
  ['public/ai-presentation-maker.html', '/ai-presentation-maker'],
  ['public/ai-document-generator.html', '/ai-document-generator'],
  ['public/ai-resume-builder.html', '/ai-resume-builder'],
  ['public/ai-video-generator.html', '/ai-video-generator'],
  ['public/ai-project-workspace.html', '/ai-project-workspace'],
  ['public/guides/rough-idea-six-week-launch-plan.html', '/guides/rough-idea-six-week-launch-plan'],
  ['public/guides/what-ai-project-should-remember.html', '/guides/what-ai-project-should-remember'],
  ['public/guides/editable-ai-powerpoint-review.html', '/guides/editable-ai-powerpoint-review'],
  ['public/guides/audit-ai-resume-bullets.html', '/guides/audit-ai-resume-bullets'],
  ['public/app.html', '/app'],
  ['public/clever-crump.html', '/clever-crump'],
];
for (const [relative, route] of speedInsightPages) {
  const page = await readFile(new URL(relative, repoRoot), 'utf8');
  const expected = `src="/_vercel/speed-insights/script.js" data-route="${route}"`;
  const privacyConfig = `src="/telemetry-config.js?v=${releaseVersion}"`;
  const webAnalytics = 'src="/_vercel/insights/script.js"';
  if (page.match(/\/telemetry-config\.js/g)?.length !== 1 ||
      page.match(/\/_vercel\/insights\/script\.js/g)?.length !== 1 ||
      page.match(/\/_vercel\/speed-insights\/script\.js/g)?.length !== 1 ||
      !page.includes(expected) ||
      page.indexOf(privacyConfig) > page.indexOf(webAnalytics) ||
      page.indexOf(privacyConfig) > page.indexOf(expected)) {
    console.error(`${relative} must redact URLs before loading either Vercel collector.`);
    process.exit(1);
  }
}

const telemetryConfig = await readFile(new URL('public/telemetry-config.js', repoRoot), 'utf8');
const telemetryWindow = {};
runInContext(telemetryConfig, createContext({window: telemetryWindow, URL}));
for (const queue of [telemetryWindow.vaq, telemetryWindow.siq]) {
  const filter = queue?.[0]?.[1];
  const filteredEvent = filter?.({
    type: 'vital',
    url: 'https://www.askcrump.com/app?token=secret&signup=1#recovery',
    route: '/app',
  });
  const filteredCustomEvent = filter?.({
    type: 'event',
    name: 'MarketingLanding',
    data: {touchpoint: 'referral.response-share', intent: 'unspecified'},
    url: 'https://www.askcrump.com/?acquisition=referral&source=response-share#shared',
  });
  if (queue?.length !== 1 ||
      queue[0][0] !== 'beforeSend' ||
      filteredEvent?.url !== 'https://www.askcrump.com/app' ||
      filteredEvent?.route !== '/app' ||
      filteredCustomEvent?.url !== 'https://www.askcrump.com/' ||
      filteredCustomEvent?.data?.touchpoint !== 'referral.response-share' ||
      filteredCustomEvent?.data?.intent !== 'unspecified' ||
      filter?.({type: 'vital', url: 'not a url'}) !== null ||
      filter?.({type: 'vital'}) !== null) {
    console.error('Vercel telemetry must remove query strings and fragments before transmission.');
    process.exit(1);
  }
}

function extractNamedFunction(source, name) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  const bodyStart = source.indexOf('{', start);
  if (start < 0 || bodyStart < 0) return '';
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  return '';
}

const referringAcquisitionSource = extractNamedFunction(authController, 'referringAcquisitionSource');
function mappedAcquisition(referrer, hostname = 'www.askcrump.com') {
  return runInContext(
    `${referringAcquisitionSource}\nreferringAcquisitionSource();`,
    createContext({document: {referrer}, location: {hostname}, URL}),
  );
}
const acquisitionMapping = new Map([
  ['', 'direct'],
  ['https://www.askcrump.com/', 'direct'],
  ['https://askcrump.com/', 'direct'],
  ['https://m.facebook.com/story.php', 'facebook'],
  ['https://l.instagram.com/', 'instagram'],
  ['https://www.google.com/search?q=assistant', 'organic'],
  ['https://news.example.org/article', 'referral'],
  ['not a url', 'direct'],
]);
if (!referringAcquisitionSource ||
    [...acquisitionMapping].some(([referrer, expected]) => mappedAcquisition(referrer) !== expected) ||
    authController.indexOf('currentAcquisition || storedAcquisition') >
      authController.indexOf(': referringAcquisitionSource()')) {
  console.error('Direct-to-app acquisition attribution is missing, unsafe, or ordered incorrectly.');
  process.exit(1);
}
const requiredHtmlSignals = [
  `/auth-styles.css?v=${guestFreeContractVersion}`,
  `/runtime-body-v1.js?v=${runtimeBodyVersion}`,
  `/auth-controller.js?v=${authControllerVersion}`,
  `/telemetry-config.js?v=${releaseVersion}`,
  '/_vercel/speed-insights/script.js',
  `/auth-resilience.js?v=${releaseVersion}`,
  `/install-prompt.js?v=${authUpdateGuardVersion}`,
  '/crump-v1-body.css',
  'class="crump-v1-body"',
  'class="v1-shell"',
  'class="v1-rail"',
  'class="sidebar v1-library"',
  'id="v1Launchpad"',
  'id="v1RecentWork"',
  'id="chatContainer"',
  'id="userInput"',
  'id="fileInput"',
  'id="deleteAccountBtn"',
  'href="/delete-account.html"',
  '<h1>What can I help you get done?</h1>',
  '<p class="v1-launchpad-actions-label">Ways to begin</p>',
  'data-v1-command="projects"',
  'data-home-document-entry',
  'data-v1-command="file"',
  'data-v1-command="image"',
  'data-v1-command="video"',
];

for (const signal of requiredHtmlSignals) {
  if (!appHtml.includes(signal)) {
    console.error(`Ask Crump new body is incomplete: missing ${signal}`);
    process.exit(1);
  }
}

const runtimeBrandSources = [
  appHtml,
  onboardingSource,
  navigationSource,
  await readFile(new URL('public/crump-v1-body.css', repoRoot), 'utf8'),
  await readFile(new URL('public/crump-v1-body.js', repoRoot), 'utf8'),
];
if (!appHtml.includes('type="image/webp" href="/assets/brand/crump-mark-320.webp"') ||
    !appHtml.includes(`type="image/webp" href="/assets/brand/crump-shell-lockup-light.webp?v=${shellNoTaglineVersion}"`) ||
    runtimeBrandSources.some(source => source.includes('/assets/brand/crump-mark.png') ||
      source.includes('/assets/brand/crump-mark.webp') ||
      source.includes('/assets/brand/crump-shell-lockup-light.png'))) {
  console.error('The active application shell must use only the lossless WebP brand derivatives.');
  process.exit(1);
}

if (appHtml.includes('fonts.googleapis.com') || appHtml.includes('fonts.gstatic.com')) {
  console.error('Ask Crump application shell must not depend on Google Fonts.');
  process.exit(1);
}
if (appHtml.includes('<span>Saved</span>')) {
  console.error('The retired Saved destination must not return to the authenticated launchpad.');
  process.exit(1);
}
if (appHtml.includes('class="v1-launchpad-foot"') ||
    appHtml.includes('data-v1-command="focus"') ||
    (appHtml.match(/class="v1-launch-card(?:\s|\")/g) || []).length !== 5) {
  console.error('The first screen must keep exactly five focused jump cards and no duplicate destination footer.');
  process.exit(1);
}

const runtime = await readFile(new URL('public/runtime-body-v1.js', repoRoot), 'utf8');
const nativeBuildSource = await readFile(new URL('scripts/build-native.mjs', repoRoot), 'utf8');
const finalStyleUrls = source => {
  const start = source.indexOf('const finalStyles = Object.freeze([');
  const end = source.indexOf(']);', start);
  if (start < 0 || end < 0) return [];
  return [...source.slice(start, end).matchAll(/\['([^']+)'/g)].map(match => match[1]);
};
const expectedFinalStyles = [
  `/crump-design-pass.css?v=${uiReleaseAuditVersion}`,
  `/crump-activity-center-1.0.css?v=${activityCenterVersion}`,
  `/crump-ui-guardrails.css?v=${uiGuardrailsVersion}`,
  `/crump-motion-system.css?v=${motionSystemVersion}`,
];
for (const source of [runtime, nativeBuildSource]) {
  const finalStyles = finalStyleUrls(source);
  if (JSON.stringify(finalStyles) !== JSON.stringify(expectedFinalStyles) ||
      !source.includes('of finalStyles) await loadStyle')) {
    console.error('Web and native loaders must preserve the complete final stylesheet cascade after base-style retries.');
    process.exit(1);
  }
}
if (!runtime.includes('/billing.css') ||
    !runtime.includes(`/billing-manager.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/subscription-ui.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/onboarding.css?v=${cacheIntegrityVersion}`) ||
    !runtime.includes(`/onboarding.js?v=${cacheIntegrityVersion}`) ||
    !runtime.includes(`/conversation.css?v=${museReleaseRepairVersion}`) ||
    !runtime.includes(`/crump-design-pass.css?v=${uiReleaseAuditVersion}`) ||
    !runtime.includes(`/crump-activity-center-1.0.css?v=${activityCenterVersion}`) ||
    !runtime.includes(`/crump-activity-center-1.0.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-ui-guardrails.css?v=${uiGuardrailsVersion}`) ||
    !runtime.includes(`/crump-motion-system.css?v=${motionSystemVersion}`) ||
    !runtime.includes(`/credit-confirmation.css?v=${creditConfirmationVersion}`) ||
    !runtime.includes(`/credit-confirmation.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/chat-resilience.js?v=${chatOwnerBoundaryVersion}`) ||
    !runtime.includes(`/account-manager.js?v=${profileSettingsBoundaryVersion}`) ||
    !runtime.includes(`/scroll-manager.js?v=${museReleaseRepairVersion}`) ||
    !runtime.includes(`/ui-functions.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/presence-manager.js?v=${presenceManagerVersion}`) ||
    !runtime.includes(`/lifecycle.css?v=${releaseVersion}-lifecycle-activation-1`) ||
    !runtime.includes(`/lifecycle-share.js?v=${settingsInviteVersion}`) ||
    !runtime.includes(`/lifecycle-manager.js?v=${lifecycleIdleSendVersion}`) ||
    !runtime.includes(`/chat-sync.js?v=${chatSyncVersion}`) ||
    !runtime.includes(`/product-analytics.js?v=${workspaceOpenedRetryVersion}`) ||
    !runtime.includes(`/app.js?v=${appOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-v1-body.js?v=${atelierWorkspaceVersion}`) ||
    !runtime.includes(`/crump-v1-body.css?v=${ownedWorkspaceAccessVersion}`) ||
    !runtime.includes(`/crump-5.0.css?v=${referenceFidelityVersion}`) ||
    !runtime.includes(`/crump-5.0.js?v=${chatComposerOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-precision-image-edit-loader.js?v=${precisionAiPersistenceVersion}`) ||
    runtime.includes(`/crump-precision-image-edit.css?v=${precisionEditStudioVersion}`) ||
    runtime.includes(`/crump-precision-image-edit.js?v=${liveImagePreviewVersion}`) ||
    !runtime.includes(`/crump-billing-5.1.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-5.2.js?v=${legacyAttachmentOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-5.2.2.css?v=${newResponseCueVersion}`) ||
    !runtime.includes(`/crump-5.2.2.js?v=${privateOwnerBoundaryVersion}&${guestFreeWorkspaceRelease}`) ||
    !runtime.includes(`/crump-4.3.js?v=${atelierWorkspaceVersion}`) ||
    !runtime.includes(`/crump-4.4.css?v=${cacheIntegrityVersion}`) ||
    !runtime.includes(`/crump-4.4.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-v1-stability.js?v=${intelligenceArchitectureVersion}`) ||
    !runtime.includes(`/crump-product-loader.js?v=${productOwnerBoundaryVersion}`) ||
    runtime.includes(`/crump-product-5.3.js?v=${studioActionLabelsVersion}`) ||
    runtime.includes(`/crump-product-5.3.css?v=${fileLibraryWindowVersion}`) ||
    !runtime.includes(`/crump-product-5.3.1.js?v=${conversationActionLabelsVersion}`) || !runtime.includes('/crump-product-5.3.1.css') ||
    !runtime.includes(`/crump-subscriptions-5.3.2.js?v=${privateOwnerBoundaryVersion}`) ||
    !runtime.includes(`/crump-polish-5.6.js?v=${cacheIntegrityVersion}`) || !runtime.includes('/crump-polish-5.6.css') ||
    !runtime.includes(`/crump-media-save.js?v=${libraryCrudPrivacyVersion}`) ||
    !runtime.includes(`/crump-library-loader.js?v=${libraryOwnerBoundaryVersion}`) ||
    runtime.includes('/crump-library-5.7.js') || runtime.includes('/crump-library-5.7.css') ||
    !runtime.includes(`/crump-navigation-5.9.30.js?v=${atelierWorkspaceVersion}`) ||
    !runtime.includes(`/crump-navigation-5.9.30.css?v=${navFocusVisibilityVersion}`) ||
    !runtime.includes(`/crump-code-loader.js?v=${codeOwnerBoundaryVersion}`) ||
    runtime.includes(`/crump-code-5.9.35.js?v=${creditConfirmationVersion}`) ||
    runtime.includes(`/crump-code-5.9.35.css?v=${intelligenceArchitectureVersion}`)) {
  console.error('New-body runtime is missing the canonical shell.');
  process.exit(1);
}
const guestFreeRuntimeAssets = [
  `/chat-resilience.js?v=${chatOwnerBoundaryVersion}`,
  `/app.js?v=${appOwnerBoundaryVersion}`,
  `/crump-5.0.js?v=${chatComposerOwnerBoundaryVersion}`,
  `/crump-billing-5.1.js?v=${privateOwnerBoundaryVersion}`,
  `/crump-5.2.js?v=${legacyAttachmentOwnerBoundaryVersion}`,
  `/crump-v1-body.js?v=${atelierWorkspaceVersion}`,
  `/crump-product-loader.js?v=${productOwnerBoundaryVersion}`,
  `/crump-code-loader.js?v=${codeOwnerBoundaryVersion}`,
].map(releasedWorkspaceAsset);
for (const source of [runtime, nativeBuildSource]) {
  if (guestFreeRuntimeAssets.some(asset => !source.includes(asset))) {
    console.error('Guest/Free frontend assets must advance atomically in web and native runtime plans.');
    process.exit(1);
  }
}
if (runtime.includes('/crump-5.2.4.js') || runtime.includes('/crump-5.2.4.css')) {
  console.error('Retired 5.2.4 branding must not load inside the new-body runtime.');
  process.exit(1);
}

const appendedRuntimeAssets = [];
const preloadedRuntimeScripts = [];
const loadedRuntimeStyles = [];
const loadedRuntimeScripts = [];
const dispatchedRuntimeEvents = [];
const runtimeDocument = {
  documentElement: {dataset: {}},
  head: {
    appendChild(node) {
      const url = node.href || node.src;
      if (url) appendedRuntimeAssets.push(url);
      if (node.rel === 'preload' && node.as === 'script' && node.href) {
        preloadedRuntimeScripts.push(node.href);
      } else if (node.rel === 'stylesheet' && node.href) {
        loadedRuntimeStyles.push(node.href);
      } else if (node.tagName === 'script' && node.src) {
        loadedRuntimeScripts.push(node.src);
      }
      Promise.resolve().then(() => node.listeners.load?.());
      return node;
    },
  },
  querySelector() { return null; },
  createElement(tagName) {
    return {
      tagName,
      dataset: {},
      listeners: {},
      addEventListener(type, callback) { this.listeners[type] = callback; },
    };
  },
};
const runtimeWindow = {
  addEventListener() {},
  dispatchEvent(event) { dispatchedRuntimeEvents.push(event.type); },
};
class RuntimeCustomEvent {
  constructor(type) { this.type = type; }
}
runInContext(runtime, createContext({
  CustomEvent: RuntimeCustomEvent,
  document: runtimeDocument,
  Promise,
  window: runtimeWindow,
}));
if (appendedRuntimeAssets.length !== 0 || typeof runtimeWindow.CrumpWorkspaceRuntime?.load !== 'function') {
  console.error('Workspace runtime must stay idle until authentication requests it.');
  process.exit(1);
}
const firstRuntimeLoad = runtimeWindow.CrumpWorkspaceRuntime.load();
const concurrentRuntimeLoad = runtimeWindow.CrumpWorkspaceRuntime.load();
if (firstRuntimeLoad !== concurrentRuntimeLoad) {
  console.error('Concurrent workspace runtime requests must share one idempotent load.');
  process.exit(1);
}
await firstRuntimeLoad;
const loadedRuntimeAssetCount = appendedRuntimeAssets.length;
await runtimeWindow.CrumpWorkspaceRuntime.load();
if (runtimeDocument.documentElement.dataset.crumpBodyRuntime !== 'ready' ||
    dispatchedRuntimeEvents.filter(type => type === 'crump:body-runtime-ready').length !== 1 ||
    appendedRuntimeAssets.length !== loadedRuntimeAssetCount ||
    loadedRuntimeStyles.length !== 21 ||
    preloadedRuntimeScripts.length !== 35 ||
    loadedRuntimeScripts.length !== 35 ||
    !loadedRuntimeScripts.every(asset => preloadedRuntimeScripts.includes(asset)) ||
    loadedRuntimeStyles.at(-1) !== expectedFinalStyles.at(-1) ||
    loadedRuntimeScripts.indexOf(`/credit-confirmation.js?v=${privateOwnerBoundaryVersion}`) > loadedRuntimeScripts.indexOf(releasedWorkspaceAsset(`/app.js?v=${appOwnerBoundaryVersion}`)) ||
    loadedRuntimeScripts.indexOf(releasedWorkspaceAsset(`/app.js?v=${appOwnerBoundaryVersion}`)) > loadedRuntimeScripts.indexOf(`/crump-4.3.js?v=${atelierWorkspaceVersion}`) ||
    loadedRuntimeScripts.at(-1) !== `/crump-activity-center-1.0.js?v=${privateOwnerBoundaryVersion}`) {
  console.error('Authenticated workspace runtime load order or completion contract failed.');
  process.exit(1);
}

const crump43 = await readFile(new URL('public/crump-4.3.js', repoRoot), 'utf8');
const v1Body = await readFile(new URL('public/crump-v1-body.js', repoRoot), 'utf8');
const appRuntime = await readFile(new URL('public/app.js', repoRoot), 'utf8');
const product53 = await readFile(new URL('public/crump-product-5.3.js', repoRoot), 'utf8');
const precisionEditor = await readFile(new URL('public/crump-precision-image-edit.js', repoRoot), 'utf8');
const precisionLoader = await readFile(new URL('public/crump-precision-image-edit-loader.js', repoRoot), 'utf8');
const productLoader = await readFile(new URL('public/crump-product-loader.js', repoRoot), 'utf8');
const libraryLoader = await readFile(new URL('public/crump-library-loader.js', repoRoot), 'utf8');
if (!precisionLoader.includes(`/crump-precision-image-edit.css?v=${referenceFidelityVersion}`) ||
    !precisionLoader.includes(`/crump-precision-image-edit.js?v=${precisionAiPersistenceVersion}`) ||
    !productLoader.includes(`/crump-product-5.3.css?v=${projectsEmptyStateVersion}`) ||
    !productLoader.includes(releasedWorkspaceAsset(`/crump-product-5.3.js?v=${productOwnerBoundaryVersion}`)) ||
    !libraryLoader.includes(`/crump-library-5.7.css?v=${libraryFirstRunVersion}`) ||
    !libraryLoader.includes(`/crump-library-5.7.js?v=${libraryOwnerBoundaryVersion}`)) {
  console.error('Reference-fidelity lazy loaders must use the same atomic release token as the shell.');
  process.exit(1);
}
const studioSectionIsolation = product53.slice(
  product53.indexOf('function configureStudioSection'),
  product53.indexOf('function openStudio'),
);
if (!studioSectionIsolation.includes("if (section !== 'projects')") ||
    !studioSectionIsolation.includes("state.projectView = 'index';") ||
    !studioSectionIsolation.includes('projectBack.hidden = true;') ||
    !studioSectionIsolation.includes("projectsPanel?.classList.remove('is-project-open');") ||
    !studioSectionIsolation.includes("sheet.dataset.projectView = 'index';") ||
    !studioSectionIsolation.includes("writeProjectRoute('', {replace: true});")) {
  console.error('Top-level creation and library destinations must clear Project-only navigation state.');
  process.exit(1);
}
if (!crump43.includes('v1OwnsEmptyState') || !crump43.includes("classList.contains('crump-v1-body')")) {
  console.error('Legacy 4.3 empty-state guard for the V1 body is missing.');
  process.exit(1);
}
if (!v1Body.includes('removeLegacyEmptyState(container)')) {
  console.error('V1 must remove stale legacy empty-state nodes.');
  process.exit(1);
}
if (!v1Body.includes("const chips = $$('[data-starter-prompt]');") ||
    !v1Body.includes("input.dispatchEvent(new Event('input', {bubbles: true}));")) {
  console.error('Every starter prompt must have an explicit owner and update the composer action state.');
  process.exit(1);
}
const projectChatInjection = product53.slice(
  product53.indexOf('function injectProjectIntoChatRequests'),
  product53.indexOf('function injectNavigation'),
);
if (!appRuntime.includes("function announceConversationOpened") ||
    !appRuntime.includes("crump:conversation-opened") ||
    !projectChatInjection.includes('state.chatProject') ||
    projectChatInjection.includes('state.activeProject?.id') ||
    !projectChatInjection.includes('projectContextChecked = true') ||
    !product53.includes('crump53-mobile-chat-project') ||
    !product53.includes('clearChatProject({optOut: true, announce: true})')) {
  console.error('Project save destination and conversation context must remain explicit and isolated.');
  process.exit(1);
}
if (product53.includes('retireLegacyToolStrip') ||
    product53.includes('crump53ToolTrigger') ||
    product53.includes('crump53ToolMenu') ||
    product53.includes('enhanceToolMenu') ||
    appHtml.includes('v1-mode-strip')) {
  console.error('Retired Tools and composer-mode controls must not ship in the product surface.');
  process.exit(1);
}
const legacySavedBranch = v1Body.slice(v1Body.indexOf("case 'saved':"), v1Body.indexOf("case 'code':"));
const filesHandoff = product53.slice(
  product53.indexOf('function openProjectFiles'),
  product53.indexOf('function showProjectIndex'),
);
if (!legacySavedBranch.includes('window.CrumpProduct53?.openFiles') ||
    legacySavedBranch.includes("openProduct('library')") ||
    !product53.includes('openFiles: () => openProjectFiles()') ||
    !filesHandoff.includes("configureStudioSection('projects');") ||
    !filesHandoff.includes("selectStudioPanel('projects');") ||
    !filesHandoff.includes("setProjectView('files');")) {
  console.error('Legacy Saved and finished-work actions must fail forward to Projects Files.');
  process.exit(1);
}

const serviceWorker = await readFile(new URL('public/sw.js', repoRoot), 'utf8');
const characterHoldFiles = Object.freeze([
  'public/app.html',
  'public/runtime-body-v1.js',
  'public/crump-v1-body.js',
  'public/ui-functions.js',
  'public/crump-4.3.js',
  'public/crump-vision-chats-1.0.js',
  'public/crump-vision-projects-1.0.js',
  'public/crump-vision-library-1.0.js',
  'public/crump-vision-demo-1.0.js',
  'public/crump-vision-home-1.0.js',
  'public/crump-vision-shell-1.0.js',
  'public/sw.js',
]);
const characterHoldSources = new Map();
for (const relative of characterHoldFiles) {
  characterHoldSources.set(
    relative,
    relative === 'public/sw.js'
      ? serviceWorker
      : await readFile(new URL(relative, repoRoot), 'utf8'),
  );
}
const forbiddenCharacterRuntimeTokens = Object.freeze([
  '/assets/brand/crump-mascot.png',
  '/assets/brand/crump-mascot-idle.',
  'MASCOT_SRC',
  'crump-message-avatar',
  'crump-empty-mascot',
  'cvp-empty-mascot',
  'cvl-empty-mascot',
  '.mascot(',
  'mascot: mascot',
]);
for (const [relative, source] of characterHoldSources) {
  const forbidden = forbiddenCharacterRuntimeTokens.find(token => source.includes(token));
  if (forbidden) {
    console.error(`Zero-runtime-mascot contract failed in ${relative}: ${forbidden}`);
    process.exit(1);
  }
}
const characterAssetOnlyFiles = Object.freeze([
  'public/crump-v1-body.css',
]);
const forbiddenCharacterAssetTokens = Object.freeze([
  '/assets/brand/crump-mascot.png',
  '/assets/brand/crump-mascot-idle.',
]);
for (const relative of characterAssetOnlyFiles) {
  const source = await readFile(new URL(relative, repoRoot), 'utf8');
  const forbidden = forbiddenCharacterAssetTokens.find(token => source.includes(token));
  if (forbidden) {
    console.error(`Zero-runtime-mascot asset contract failed in ${relative}: ${forbidden}`);
    process.exit(1);
  }
}
for (const relative of [
  'public/ui-functions.js',
  'public/crump-4.3.js',
  'public/crump-vision-chats-1.0.js',
  'public/crump-vision-demo-1.0.js',
]) {
  if (!characterHoldSources.get(relative).includes('crump-message-status-pip')) {
    console.error(`Assistant identity must use the restrained status pip in ${relative}.`);
    process.exit(1);
  }
}
const shellBrandUrl = `/assets/brand/crump-shell-lockup-light.webp?v=${shellNoTaglineVersion}`;
for (const [label, source, expectedOccurrences] of [
  ['app shell', appHtml, 7],
  ['body runtime', v1Body, 1],
  ['service worker', serviceWorker, 1],
]) {
  const pathnameOccurrences = source.split('/assets/brand/crump-shell-lockup-light.webp').length - 1;
  const currentOccurrences = source.split(shellBrandUrl).length - 1;
  if (pathnameOccurrences !== expectedOccurrences || currentOccurrences !== expectedOccurrences) {
    console.error(`${label} must reference only the current no-tagline shell asset: ${shellBrandUrl}`);
    process.exit(1);
  }
}
const cacheAddressabilitySources = Object.freeze([
  ['web runtime', runtime],
  ['native build', nativeBuildSource],
  ['service worker', serviceWorker],
]);
for (const [pathname, expectedUrl] of [
  ['/crump-product-loader.js', releasedWorkspaceAsset(`/crump-product-loader.js?v=${productOwnerBoundaryVersion}`)],
  ['/crump-library-loader.js', `/crump-library-loader.js?v=${libraryOwnerBoundaryVersion}`],
  ['/crump-code-loader.js', releasedWorkspaceAsset(`/crump-code-loader.js?v=${codeOwnerBoundaryVersion}`)],
  ['/profile-manager.js', `/profile-manager.js?v=${profileSettingsBoundaryVersion}`],
  ['/billing-manager.js', `/billing-manager.js?v=${privateOwnerBoundaryVersion}`],
  ['/subscription-ui.js', `/subscription-ui.js?v=${privateOwnerBoundaryVersion}`],
  ['/credit-confirmation.js', `/credit-confirmation.js?v=${privateOwnerBoundaryVersion}`],
  ['/ui-functions.js', `/ui-functions.js?v=${privateOwnerBoundaryVersion}`],
  ['/product-analytics.js', `/product-analytics.js?v=${workspaceOpenedRetryVersion}`],
  ['/crump-4.4.js', `/crump-4.4.js?v=${privateOwnerBoundaryVersion}`],
  ['/crump-billing-5.1.js', releasedWorkspaceAsset(`/crump-billing-5.1.js?v=${privateOwnerBoundaryVersion}`)],
  ['/crump-5.2.js', releasedWorkspaceAsset(`/crump-5.2.js?v=${legacyAttachmentOwnerBoundaryVersion}`)],
  ['/crump-5.2.2.js', releasedWorkspaceAsset(`/crump-5.2.2.js?v=${privateOwnerBoundaryVersion}`)],
  ['/crump-subscriptions-5.3.2.js', `/crump-subscriptions-5.3.2.js?v=${privateOwnerBoundaryVersion}`],
  ['/crump-activity-center-1.0.js', `/crump-activity-center-1.0.js?v=${privateOwnerBoundaryVersion}`],
  ['/crump-navigation-5.9.30.css', `/crump-navigation-5.9.30.css?v=${navFocusVisibilityVersion}`],
  ['/crump-v1-body.js', releasedWorkspaceAsset(`/crump-v1-body.js?v=${atelierWorkspaceVersion}`)],
]) {
  for (const [label, source] of cacheAddressabilitySources) {
    const versionedOccurrences = source.split(`${pathname}?v=`).length - 1;
    const exactOccurrences = [`'${expectedUrl}'`, `"${expectedUrl}"`, `\`${expectedUrl}\``]
      .reduce((total, literal) => total + source.split(literal).length - 1, 0);
    if (versionedOccurrences !== 1 || exactOccurrences !== 1) {
      console.error(`${label} must contain exactly one current cache-addressable ${pathname}: ${expectedUrl}`);
      process.exit(1);
    }
  }
}
for (const [label, source] of [
  ['app shell', appHtml],
  ['service worker', serviceWorker],
]) {
  const pathname = '/runtime-body-v1.js';
  const expectedUrl = `/runtime-body-v1.js?v=${runtimeBodyVersion}`;
  const versionedOccurrences = source.split(`${pathname}?v=`).length - 1;
  const exactOccurrences = [`'${expectedUrl}'`, `"${expectedUrl}"`, `\`${expectedUrl}\``]
    .reduce((total, literal) => total + source.split(literal).length - 1, 0);
  if (versionedOccurrences !== 1 || exactOccurrences !== 1) {
    console.error(`${label} must contain exactly one current cache-addressable ${pathname}: ${expectedUrl}`);
    process.exit(1);
  }
}
for (const [label, source] of [
  ['app shell', appHtml],
  ['service worker', serviceWorker],
]) {
  const pathname = '/mobile-bridge.js';
  const expectedUrl = `/mobile-bridge.js?v=${privateOwnerBoundaryVersion}`;
  const versionedOccurrences = source.split(`${pathname}?v=`).length - 1;
  const exactOccurrences = [`'${expectedUrl}'`, `"${expectedUrl}"`, `\`${expectedUrl}\``]
    .reduce((total, literal) => total + source.split(literal).length - 1, 0);
  if (versionedOccurrences !== 1 || exactOccurrences !== 1) {
    console.error(`${label} must contain exactly one current cache-addressable ${pathname}: ${expectedUrl}`);
    process.exit(1);
  }
}
for (const [label, source] of [
  ['app shell', appHtml],
  ['service worker', serviceWorker],
]) {
  const pathname = '/home-document-entry.js';
  const expectedUrl = `/home-document-entry.js?v=${homeDocumentEntryVersion}`;
  const versionedOccurrences = source.split(`${pathname}?v=`).length - 1;
  const exactOccurrences = [`'${expectedUrl}'`, `"${expectedUrl}"`, `\`${expectedUrl}\``]
    .reduce((total, literal) => total + source.split(literal).length - 1, 0);
  if (versionedOccurrences !== 1 || exactOccurrences !== 1) {
    console.error(`${label} must contain exactly one current cache-addressable ${pathname}: ${expectedUrl}`);
    process.exit(1);
  }
}
for (const pathname of ['/crump-vision-projects-1.0.css', '/crump-vision-projects-1.0.js']) {
  const expectedVersion = pathname.endsWith('.js')
    ? projectResumeOwnerBoundaryVersion
    : projectResumeVersion;
  const expectedUrl = `${pathname}?v=${expectedVersion}`;
  for (const [label, source] of [
    ['app shell', appHtml],
    ['service worker', serviceWorker],
  ]) {
    const versionedOccurrences = source.split(`${pathname}?v=`).length - 1;
    const exactOccurrences = [`'${expectedUrl}'`, `"${expectedUrl}"`, `\`${expectedUrl}\``]
      .reduce((total, literal) => total + source.split(literal).length - 1, 0);
    if (versionedOccurrences !== 1 || exactOccurrences !== 1) {
      console.error(`${label} must contain exactly one current cache-addressable ${pathname}: ${expectedUrl}`);
      process.exit(1);
    }
  }
}
for (const [pathname, expectedVersion] of [
  ['/crump-vision-library-1.0.js', libraryOwnerBoundaryVersion],
  ['/auth-controller.js', authControllerVersion],
]) {
  const expectedUrl = `${pathname}?v=${expectedVersion}`;
  for (const [label, source] of [
    ['app shell', appHtml],
    ['service worker', serviceWorker],
  ]) {
    const versionedOccurrences = source.split(`${pathname}?v=`).length - 1;
    const exactOccurrences = [`'${expectedUrl}'`, `"${expectedUrl}"`, `\`${expectedUrl}\``]
      .reduce((total, literal) => total + source.split(literal).length - 1, 0);
    if (versionedOccurrences !== 1 || exactOccurrences !== 1) {
      console.error(`${label} must contain exactly one current cache-addressable ${pathname}: ${expectedUrl}`);
      process.exit(1);
    }
  }
}
if (!serviceWorker.includes('ask-crump-new-body-v1-r276-initial-chat-owner-reconciliation-1') ||
    !serviceWorker.includes(`'${shellBrandUrl}'`) ||
    serviceWorker.includes("'/assets/brand/crump-mark.webp'") ||
    serviceWorker.includes("'/assets/brand/crump-mark-320.webp'") ||
    serviceWorker.includes("'/assets/brand/crump-shell-lockup-light.png'") ||
    !serviceWorker.includes(`/landing.js?v=${landingVersion}`) ||
    !serviceWorker.includes(appearanceThemeUrl) ||
    !serviceWorker.includes(appearanceControlsUrl) ||
    !serviceWorker.includes(`/runtime-body-v1.js?v=${runtimeBodyVersion}`) ||
    !serviceWorker.includes(`/home-document-entry.js?v=${homeDocumentEntryVersion}`) ||
    !serviceWorker.includes(`/conversation.css?v=${museReleaseRepairVersion}`) ||
    !serviceWorker.includes(`/crump-design-pass.css?v=${uiReleaseAuditVersion}`) ||
    !serviceWorker.includes(`/crump-activity-center-1.0.css?v=${activityCenterVersion}`) ||
    !serviceWorker.includes(`/crump-activity-center-1.0.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-ui-guardrails.css?v=${uiGuardrailsVersion}`) ||
    !serviceWorker.includes(`/crump-motion-system.css?v=${motionSystemVersion}`) ||
    !serviceWorker.includes(`/credit-confirmation.css?v=${creditConfirmationVersion}`) ||
    !serviceWorker.includes(`/credit-confirmation.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/chat-resilience.js?v=${chatOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/account-manager.js?v=${profileSettingsBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.css?v=${referenceFidelityVersion}`) ||
    !serviceWorker.includes(`/scroll-manager.js?v=${museReleaseRepairVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.js?v=${chatComposerOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-precision-image-edit-loader.js?v=${precisionAiPersistenceVersion}`) ||
    serviceWorker.includes(`/crump-precision-image-edit.css?v=${precisionEditStudioVersion}`) ||
    serviceWorker.includes(`/crump-precision-image-edit.js?v=${liveImagePreviewVersion}`) ||
    !serviceWorker.includes(`/ui-functions.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/presence-manager.js?v=${presenceManagerVersion}`) ||
    !serviceWorker.includes(`/app.js?v=${appOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.2.css?v=${newResponseCueVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.2.js?v=${privateOwnerBoundaryVersion}&${guestFreeWorkspaceRelease}`) ||
    !serviceWorker.includes(`/onboarding.css?v=${cacheIntegrityVersion}`) ||
    !serviceWorker.includes(`/onboarding.js?v=${cacheIntegrityVersion}`) ||
    !serviceWorker.includes(`/crump-polish-5.6.js?v=${cacheIntegrityVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.css?v=${navFocusVisibilityVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.js?v=${atelierWorkspaceVersion}`) ||
    !serviceWorker.includes(`/lifecycle.css?v=${releaseVersion}-lifecycle-activation-1`) ||
    !serviceWorker.includes(`/lifecycle-share.js?v=${settingsInviteVersion}`) ||
    !serviceWorker.includes(`/lifecycle-manager.js?v=${lifecycleIdleSendVersion}`) ||
    !serviceWorker.includes(`/auth-resilience.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/install-prompt.js?v=${authUpdateGuardVersion}`) ||
    !serviceWorker.includes(`/install-prompt.css?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/device-auth.js?v=${accountOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/sync-manager.js?v=${syncQueueVersion}`) ||
    !serviceWorker.includes(`/chat-sync.js?v=${chatSyncVersion}`) ||
    !serviceWorker.includes(`/product-analytics.js?v=${workspaceOpenedRetryVersion}`) ||
    !serviceWorker.includes(`/auth-controller.js?v=${authControllerVersion}`) ||
    !serviceWorker.includes(`/crump-v1-body.css?v=${ownedWorkspaceAccessVersion}`) ||
    !serviceWorker.includes(`/crump-4.3.js?v=${atelierWorkspaceVersion}`) ||
    !serviceWorker.includes(`/crump-4.4.css?v=${cacheIntegrityVersion}`) ||
    !serviceWorker.includes(`/crump-4.4.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-v1-stability.js?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-product-loader.js?v=${productOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.1.js?v=${conversationActionLabelsVersion}`) ||
    serviceWorker.includes(`/crump-product-5.3.js?v=${studioActionLabelsVersion}`) ||
    serviceWorker.includes(`/crump-product-5.3.css?v=${fileLibraryWindowVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.js?v=${atelierWorkspaceVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.css?v=${navFocusVisibilityVersion}`) ||
    !serviceWorker.includes(`/crump-code-loader.js?v=${codeOwnerBoundaryVersion}`) ||
    serviceWorker.includes(`/crump-code-5.9.35.js?v=${creditConfirmationVersion}`) ||
    serviceWorker.includes(`/crump-code-5.9.35.css?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes("url.pathname === '/conversation.css'") ||
    !serviceWorker.includes("url.pathname === '/appearance-theme.js'") ||
    !serviceWorker.includes("url.pathname === '/appearance-controls.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-activity-center-1.0.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-activity-center-1.0.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-ui-guardrails.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-motion-system.css'") ||
    !serviceWorker.includes("url.pathname === '/credit-confirmation.css'") ||
    !serviceWorker.includes("url.pathname === '/credit-confirmation.js'") ||
    !serviceWorker.includes("url.pathname === '/chat-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-precision-image-edit-loader.js'") ||
    serviceWorker.includes("url.pathname === '/crump-precision-image-edit.js'") ||
    serviceWorker.includes("url.pathname === '/crump-precision-image-edit.css'") ||
    !serviceWorker.includes("url.pathname === '/ui-functions.js'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle.css'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle-share.js'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.css'") ||
    !serviceWorker.includes("url.pathname === '/sync-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-controller.js'") ||
    !serviceWorker.includes(`/crump-v1-body.js?v=${atelierWorkspaceVersion}`) ||
    !serviceWorker.includes('/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1') ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-loader.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-product-loader.js'") ||
    serviceWorker.includes("url.pathname === '/crump-product-5.3.js'") ||
    serviceWorker.includes("url.pathname === '/crump-product-5.3.css'") ||
    !serviceWorker.includes(`/billing-manager.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/subscription-ui.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-billing-5.1.css?v=${creditTruthVersion}`) ||
    !serviceWorker.includes(`/crump-billing-5.1.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.js?v=${legacyAttachmentOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-subscriptions-5.3.2.js?v=${privateOwnerBoundaryVersion}`) ||
    !serviceWorker.includes(`/crump-media-save.js?v=${libraryCrudPrivacyVersion}`) ||
    !serviceWorker.includes(`/crump-library-loader.js?v=${libraryOwnerBoundaryVersion}`) ||
    serviceWorker.includes('/crump-library-5.7.js') ||
    serviceWorker.includes('/crump-library-5.7.css') ||
    !serviceWorker.includes("url.pathname === '/crump-media-save.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-library-loader.js'")) {
  console.error('New-body service-worker contract is incomplete.');
  process.exit(1);
}
const guestFreeServiceWorkerAssets = [
  `/auth-styles.css?v=${guestFreeContractVersion}`,
  `/runtime-body-v1.js?v=${runtimeBodyVersion}`,
  `/auth-controller.js?v=${authControllerVersion}`,
  ...guestFreeRuntimeAssets,
];
if (guestFreeServiceWorkerAssets.some(asset => !serviceWorker.includes(asset))) {
  console.error('Service worker must precache one coherent Guest/Free frontend release.');
  process.exit(1);
}

const billingManagerSource = await readFile(new URL('public/billing-manager.js', repoRoot), 'utf8');
async function exerciseNativeBillingIdentity({rejectSecondLogin = false} = {}) {
  const calls = [];
  let loginAttempts = 0;
  const plugin = {
    async configure(payload) { calls.push(['configure', payload.appUserID || null]); },
    async logIn(payload) {
      loginAttempts += 1;
      calls.push(['login', payload.appUserID]);
      if (rejectSecondLogin && loginAttempts === 1) throw new Error('fixture identity failure');
    },
    async logOut() { calls.push(['logout']); },
    async getOfferings() {
      calls.push(['offerings']);
      return {current: {availablePackages: []}};
    },
  };
  const windowMock = {
    CRUMP_CONFIG: {revenueCatAppleApiKey: 'fixture-public-key'},
    CrumpAPI: {isNative: true, ready: Promise.resolve()},
    CrumpNative: {Capacitor: {getPlatform: () => 'ios'}, Purchases: plugin},
    currentUser: {id: 'account-a'},
  };
  runInContext(billingManagerSource, createContext({window: windowMock}));
  await Promise.all([
    windowMock.BillingManager.getProducts(),
    windowMock.BillingManager.getCreditProducts(),
  ]);
  windowMock.currentUser = {id: 'account-b'};
  let rejectedMessage = '';
  try {
    await Promise.all([
      windowMock.BillingManager.getProducts(),
      windowMock.BillingManager.getCreditProducts(),
    ]);
  } catch (error) {
    rejectedMessage = error?.message || '';
  }
  if (rejectSecondLogin) return {calls, rejectedMessage};
  await windowMock.BillingManager.getProducts();
  windowMock.currentUser = null;
  await windowMock.BillingManager.disconnect();
  windowMock.currentUser = {id: 'account-c'};
  await windowMock.BillingManager.getProducts();
  return {calls, rejectedMessage};
}

const nativeBillingIdentity = await exerciseNativeBillingIdentity();
const expectedNativeBillingIdentityCalls = [
  ['configure', 'account-a'],
  ['login', 'account-b'],
  ['logout'],
  ['login', 'account-c'],
];
const nativeBillingIdentityCalls = nativeBillingIdentity.calls.filter(([name]) => name !== 'offerings');
if (JSON.stringify(nativeBillingIdentityCalls) !== JSON.stringify(expectedNativeBillingIdentityCalls) ||
    nativeBillingIdentity.calls.filter(([name]) => name === 'offerings').length !== 6) {
  console.error('Native billing must realign exactly once whenever the signed-in account changes.');
  process.exit(1);
}
const rejectedNativeBillingIdentity = await exerciseNativeBillingIdentity({rejectSecondLogin: true});
if (rejectedNativeBillingIdentity.rejectedMessage !== 'Store billing could not confirm the signed-in account. Try again.' ||
    rejectedNativeBillingIdentity.calls.filter(([name]) => name === 'configure').length !== 1 ||
    rejectedNativeBillingIdentity.calls.filter(([name]) => name === 'login').length !== 1 ||
    rejectedNativeBillingIdentity.calls.filter(([name]) => name === 'offerings').length !== 2) {
  console.error('Native billing must fail closed before loading products when store identity alignment fails.');
  process.exit(1);
}

async function exerciseNativeBillingOperation({
  operation,
  purchaseError = null,
  rejectCreditSync = false,
} = {}) {
  const calls = [];
  const subscriptionPackage = {
    identifier: '$rc_monthly',
    product: {
      identifier: 'askcrump_professional_monthly',
      priceString: '$20.00',
    },
    presentedOfferingContext: {
      offeringIdentifier: 'default',
      placementIdentifier: null,
      targetingContext: null,
    },
  };
  const plugin = {
    async configure(payload) { calls.push(['configure', payload.appUserID || null]); },
    async getOfferings() {
      calls.push(['offerings']);
      return {current: {availablePackages: [subscriptionPackage]}};
    },
    async purchasePackage(payload) {
      calls.push(['purchase', payload.aPackage]);
      if (purchaseError) throw purchaseError;
      return {customerInfo: {entitlements: {active: {professional: {}}}}};
    },
    async restorePurchases() {
      calls.push(['restore']);
      return {customerInfo: {entitlements: {active: {professional: {}}}}};
    },
  };
  const fetch = async (input, options = {}) => {
    const path = String(input);
    calls.push(['fetch', path, String(options.method || 'GET').toUpperCase()]);
    if (rejectCreditSync && path === '/api/billing/credits/revenuecat/sync') {
      return {ok: false, async json() { return {success: false, error: 'fixture credit sync failed'}; }};
    }
    const payload = path === '/api/billing/status'
      ? {success: true, user: {id: 'account-a', tier: 'professional'}}
      : path === '/api/billing/credits/revenuecat/sync'
        ? {success: true, credits: {balance: 0}}
        : {success: true, user: {id: 'account-a', tier: 'professional'}};
    return {ok: true, async json() { return payload; }};
  };
  const windowMock = {
    CRUMP_CONFIG: {
      revenueCatAppleApiKey: 'fixture-public-key',
      revenueCatProfessionalProductId: 'askcrump_professional_monthly',
    },
    CrumpAPI: {isNative: true, ready: Promise.resolve()},
    CrumpNative: {Capacitor: {getPlatform: () => 'ios'}, Purchases: plugin},
    currentUser: {id: 'account-a'},
    dispatchEvent(event) { calls.push(['event', event.type]); },
    profileManager: {applyServerSubscription(user) { calls.push(['profile', user.tier]); }},
  };
  class FixtureCustomEvent {
    constructor(type, options = {}) {
      this.type = type;
      this.detail = options.detail;
    }
  }
  runInContext(billingManagerSource, createContext({
    window: windowMock,
    fetch,
    URL,
    CustomEvent: FixtureCustomEvent,
  }));
  let result;
  let thrown;
  try {
    result = operation === 'restore'
      ? await windowMock.BillingManager.restore()
      : await windowMock.BillingManager.purchase('professional');
  } catch (error) {
    thrown = error;
  }
  return {calls, result, thrown, subscriptionPackage};
}

const purchaseCancellation = Object.assign(new Error('Purchase cancelled by user.'), {
  code: '1',
  data: {requestId: 'fixture-cancelled-request'},
  userInfo: {NSLocalizedDescription: 'Purchase cancelled by user.'},
  readableErrorCode: 'PURCHASE_CANCELLED_ERROR',
  underlyingErrorMessage: 'fixture user cancelled',
  userCancelled: true,
});
const cancelledNativePurchase = await exerciseNativeBillingOperation({
  operation: 'purchase',
  purchaseError: purchaseCancellation,
});
if (cancelledNativePurchase.thrown !== purchaseCancellation ||
    cancelledNativePurchase.calls.filter(([name]) => name === 'purchase').length !== 1 ||
    cancelledNativePurchase.calls.some(([name]) => name === 'fetch')) {
  console.error('BillingManager must preserve cancellation errors and never sync an uncompleted native purchase.');
  process.exit(1);
}

const nativePurchaseFailure = Object.assign(new Error('Store connection failed.'), {
  code: '10',
  data: {requestId: 'fixture-request'},
  userInfo: {NSLocalizedDescription: 'Store connection failed.'},
  readableErrorCode: 'NETWORK_ERROR',
  underlyingErrorMessage: 'fixture transport unavailable',
  userCancelled: false,
});
const failedNativePurchase = await exerciseNativeBillingOperation({
  operation: 'purchase',
  purchaseError: nativePurchaseFailure,
});
if (failedNativePurchase.thrown !== nativePurchaseFailure ||
    failedNativePurchase.calls.some(([name]) => name === 'fetch')) {
  console.error('BillingManager must preserve native purchase errors and fail before server reconciliation.');
  process.exit(1);
}

const restoredNativePurchase = await exerciseNativeBillingOperation({operation: 'restore'});
const restoredFetches = restoredNativePurchase.calls
  .filter(([name]) => name === 'fetch')
  .map(([, path, method]) => [path, method]);
const expectedRestoreFetches = [
  ['/api/billing/revenuecat/sync', 'POST'],
  ['/api/billing/credits/revenuecat/sync', 'POST'],
  ['/api/billing/status', 'GET'],
];
if (restoredNativePurchase.thrown ||
    restoredNativePurchase.calls.filter(([name]) => name === 'restore').length !== 1 ||
    JSON.stringify(restoredFetches) !== JSON.stringify(expectedRestoreFetches)) {
  console.error('BillingManager restoration must reconcile subscriptions, credits, and the final account status in order.');
  process.exit(1);
}

const restoredAfterCreditSyncFailure = await exerciseNativeBillingOperation({
  operation: 'restore',
  rejectCreditSync: true,
});
const restoreAfterCreditFailureFetches = restoredAfterCreditSyncFailure.calls
  .filter(([name]) => name === 'fetch')
  .map(([, path, method]) => [path, method]);
if (restoredAfterCreditSyncFailure.thrown ||
    JSON.stringify(restoreAfterCreditFailureFetches) !== JSON.stringify(expectedRestoreFetches)) {
  console.error('BillingManager restoration must refresh final subscription status when optional credit reconciliation fails.');
  process.exit(1);
}

async function exerciseNativeBillingOwnerRotation(operation) {
  const calls = [];
  let ownerId = 'account-a';
  let revision = 1;
  let releaseStoreOperation;
  let storeOperationStartedResolve;
  const storeOperationStarted = new Promise(resolve => { storeOperationStartedResolve = resolve; });
  const subscriptionPackage = {
    identifier: '$rc_monthly',
    product: {identifier: 'askcrump_professional_monthly', priceString: '$20.00'},
  };
  const plugin = {
    async configure(payload) { calls.push(['configure', payload.appUserID || null]); },
    async logIn(payload) { calls.push(['login', payload.appUserID]); },
    async getOfferings() {
      calls.push(['offerings', ownerId]);
      return {current: {availablePackages: [subscriptionPackage]}};
    },
    async purchasePackage() {
      calls.push(['purchase-start']);
      storeOperationStartedResolve();
      await new Promise(resolve => { releaseStoreOperation = resolve; });
      calls.push(['purchase-finish']);
      return {customerInfo: {entitlements: {active: {professional: {}}}}};
    },
    async restorePurchases() {
      calls.push(['restore-start']);
      storeOperationStartedResolve();
      await new Promise(resolve => { releaseStoreOperation = resolve; });
      calls.push(['restore-finish']);
      return {customerInfo: {entitlements: {active: {professional: {}}}}};
    },
  };
  const windowMock = {
    CRUMP_CONFIG: {
      revenueCatAppleApiKey: 'fixture-public-key',
      revenueCatProfessionalProductId: 'askcrump_professional_monthly',
    },
    CrumpAPI: {isNative: true, ready: Promise.resolve()},
    CrumpNative: {Capacitor: {getPlatform: () => 'ios'}, Purchases: plugin},
    CrumpAuthBoundary: {
      authenticatedUserId: () => ownerId,
      revision: () => revision,
    },
    currentUser: {id: ownerId},
    dispatchEvent() {},
  };
  const fetch = async (input, options = {}) => {
    calls.push(['fetch', String(input), String(options.method || 'GET').toUpperCase()]);
    return {ok: true, async json() { return {success: true, user: {id: ownerId}}; }};
  };
  runInContext(billingManagerSource, createContext({window: windowMock, fetch, URL}));

  const pending = operation === 'restore'
    ? windowMock.BillingManager.restore()
    : windowMock.BillingManager.purchase('professional');
  await storeOperationStarted;
  ownerId = 'account-b';
  revision += 1;
  windowMock.currentUser = {id: ownerId};
  const alignB = windowMock.BillingManager.configure();
  await Promise.resolve();
  await Promise.resolve();
  if (calls.some(call => call[0] === 'login' && call[1] === 'account-b')) {
    throw new Error('RevenueCat identity changed while an owner-A store operation was still in flight.');
  }
  releaseStoreOperation();
  let thrown = null;
  try { await pending; } catch (error) { thrown = error; }
  await alignB;
  return {calls, thrown};
}

for (const operation of ['purchase', 'restore']) {
  const rotation = await exerciseNativeBillingOwnerRotation(operation);
  const operationFinish = rotation.calls.findIndex(call => call[0] === `${operation}-finish`);
  const loginB = rotation.calls.findIndex(call => call[0] === 'login' && call[1] === 'account-b');
  if (rotation.thrown?.code !== 'AUTH_OWNER_CHANGED' ||
      operationFinish < 0 || loginB <= operationFinish ||
      rotation.calls.some(call => call[0] === 'fetch')) {
    console.error(`Native ${operation} must hold RevenueCat identity until completion, then fail stale before server reconciliation.`);
    process.exit(1);
  }
}

{
  const calls = [];
  const windowMock = {
    CRUMP_CONFIG: {revenueCatAppleApiKey: 'fixture-public-key'},
    CrumpAPI: {isNative: true, ready: Promise.resolve()},
    CrumpNative: {
      Capacitor: {getPlatform: () => 'ios'},
      Purchases: {
        async configure() { calls.push('configure'); },
        async getOfferings() { calls.push('offerings'); return {current: {availablePackages: []}}; },
      },
    },
    currentUser: null,
  };
  runInContext(billingManagerSource, createContext({window: windowMock, fetch: async () => {
    calls.push('fetch');
    return {ok: true, async json() { return {success: true}; }};
  }, URL}));
  let ownerlessError = null;
  try { await windowMock.BillingManager.restore(); } catch (error) { ownerlessError = error; }
  if (ownerlessError?.code !== 'AUTH_OWNER_CHANGED' || calls.length !== 0) {
    console.error('Consequential native billing operations must require a concrete authenticated owner.');
    process.exit(1);
  }
}

async function exercisePersistedNativeBillingIdentity() {
  const calls = [];
  const plugin = {
    async isConfigured() { calls.push(['is-configured']); return {isConfigured: true}; },
    async getAppUserID() { calls.push(['get-user']); return {appUserID: 'account-a'}; },
    async isAnonymous() { calls.push(['is-anonymous']); return {isAnonymous: false}; },
    async configure() { calls.push(['unexpected-configure']); },
    async logIn(payload) { calls.push(['login', payload.appUserID]); },
    async getOfferings() {
      calls.push(['offerings']);
      return {current: {availablePackages: []}};
    },
  };
  const windowMock = {
    CRUMP_CONFIG: {revenueCatGoogleApiKey: 'fixture-public-key'},
    CrumpAPI: {isNative: true, ready: Promise.resolve()},
    CrumpNative: {Capacitor: {getPlatform: () => 'android'}, Purchases: plugin},
    currentUser: {id: 'account-b'},
  };
  runInContext(billingManagerSource, createContext({window: windowMock}));
  await windowMock.BillingManager.getProducts();
  return calls;
}

const persistedNativeBillingIdentity = await exercisePersistedNativeBillingIdentity();
const expectedPersistedNativeBillingIdentity = [
  ['is-configured'],
  ['get-user'],
  ['is-anonymous'],
  ['login', 'account-b'],
  ['offerings'],
];
if (JSON.stringify(persistedNativeBillingIdentity) !== JSON.stringify(expectedPersistedNativeBillingIdentity)) {
  console.error('Native billing must adopt a persisted SDK identity without configuring the singleton twice.');
  process.exit(1);
}

const deviceAuthSource = await readFile(new URL('public/device-auth.js', repoRoot), 'utf8');
const mobileBridgeSource = await readFile(new URL('public/mobile-bridge.js', repoRoot), 'utf8');

async function exerciseNativeSecureStorageAuthLifecycle() {
  const sessionKey = 'ask_crump_session_v4';
  const storedValues = new Map([[sessionKey, 'persisted-token']]);
  const storageCalls = [];
  const transportCalls = [];
  const fetchCalls = [];
  const localValues = new Map();
  let delayed401Resolve = null;
  let delayed401StartedResolve = null;
  const delayed401Started = new Promise(resolve => { delayed401StartedResolve = resolve; });
  let delayedLogoutResolve = null;
  let delayedLogoutStartedResolve = null;
  let delayLogout = false;
  let rejectLogoutOwner = false;
  let boundaryOwner = 'owner-a';
  let boundaryRevision = 1;
  const secureStorage = {
    async get(key) {
      storageCalls.push(['get', key]);
      return {value: storedValues.get(key) ?? null};
    },
    async set(key, value) {
      storageCalls.push(['set', key, value]);
      storedValues.set(key, value);
    },
    async remove(key) {
      storageCalls.push(['remove', key]);
      storedValues.delete(key);
    },
  };
  const localStorage = {
    get length() { return localValues.size; },
    getItem(key) { return localValues.get(key) ?? null; },
    key(index) { return [...localValues.keys()][index] ?? null; },
    removeItem(key) { localValues.delete(key); },
    setItem(key, value) { localValues.set(key, String(value)); },
  };
  const windowMock = {
    CRUMP_CONFIG: {apiBase: 'https://www.askcrump.com'},
    CrumpNative: {
      isNative: true,
      Capacitor: {getPlatform: () => 'ios'},
      SecureStorage: secureStorage,
    },
    addEventListener() {},
    currentUser: {id: boundaryOwner},
    CrumpAuthBoundary: {
      authenticatedUserId: () => boundaryOwner,
      revision: () => boundaryRevision,
    },
    fetch: async (input, init = {}) => {
      fetchCalls.push({input: String(input), headers: new Headers(init.headers)});
      if (String(input).includes('/api/delayed-401')) {
        delayed401StartedResolve?.();
        return new Promise(resolve => { delayed401Resolve = resolve; });
      }
      return new Response(null, {status: 401});
    },
  };
  const context = createContext({
    Headers,
    Promise,
    Response,
    URL,
    clearTimeout,
    crypto: {
      getRandomValues(target) {
        target[0] = 123;
        target[1] = 456;
        return target;
      },
      randomUUID: () => 'fixture-installation-id',
    },
    localStorage,
    navigator: {userAgent: 'Ask Crump native auth fixture'},
    setTimeout,
    window: windowMock,
  });

  runInContext(mobileBridgeSource, context);
  await windowMock.CrumpAPI.ready;
  if (windowMock.CrumpAPI.getSessionToken() !== 'persisted-token' ||
      JSON.stringify(storageCalls[0]) !== JSON.stringify(['get', sessionKey])) {
    throw new Error('The native bridge did not restore the persisted secure-storage session token.');
  }

  await windowMock.CrumpAPI.setSessionToken('fresh-token');
  if (windowMock.CrumpAPI.getSessionToken() !== 'fresh-token' ||
      storedValues.get(sessionKey) !== 'fresh-token' ||
      !storageCalls.some(call => JSON.stringify(call) === JSON.stringify(['set', sessionKey, 'fresh-token']))) {
    throw new Error('The native bridge did not persist the refreshed session token to secure storage.');
  }

  await windowMock.CrumpAPI.setSessionToken('owner-a-token');
  const delayedUnauthorized = windowMock.fetch('/api/delayed-401');
  await delayed401Started;
  await windowMock.CrumpAPI.setSessionToken('owner-b-token');
  delayed401Resolve(new Response(null, {status: 401}));
  await delayedUnauthorized;
  if (windowMock.CrumpAPI.getSessionToken() !== 'owner-b-token' ||
      storedValues.get(sessionKey) !== 'owner-b-token') {
    throw new Error('A delayed owner-A 401 cleared the newer owner-B secure-storage token.');
  }

  windowMock.CrumpAuthTransport = {
    async request(path, init = {}) {
      transportCalls.push([path, String(init.method || 'GET').toUpperCase()]);
      if (path === '/api/auth/logout' && delayLogout) {
        delayedLogoutStartedResolve?.();
        return new Promise(resolve => { delayedLogoutResolve = resolve; });
      }
      if (path === '/api/auth/logout' && rejectLogoutOwner) {
        return {
          response: {ok: false, status: 409},
          data: {success: false, code: 'AUTH_OWNER_MISMATCH', staleAuth: true},
        };
      }
      return {response: {ok: true}, data: {success: true}};
    },
  };
  windowMock.BillingManager = {async disconnect() { transportCalls.push(['billing-disconnect']); }};
  runInContext(deviceAuthSource, context);
  windowMock.deviceAuth.session = {user: {id: 'owner-a'}};
  let clearLocalStateCalls = 0;
  const clearLocalState = windowMock.deviceAuth.clearLocalState.bind(windowMock.deviceAuth);
  windowMock.deviceAuth.clearLocalState = expectedOwnerId => {
    clearLocalStateCalls += 1;
    return clearLocalState(expectedOwnerId);
  };

  await windowMock.CrumpAPI.setSessionToken('owner-a-token');
  delayLogout = true;
  const delayedLogoutStarted = new Promise(resolve => { delayedLogoutStartedResolve = resolve; });
  const staleLogout = windowMock.deviceAuth.logout();
  await delayedLogoutStarted;
  await windowMock.CrumpAPI.setSessionToken('owner-b-token');
  delayedLogoutResolve({response: {ok: true}, data: {success: true}});
  const staleLogoutResult = await staleLogout;
  if (staleLogoutResult?.stale !== true || clearLocalStateCalls !== 0 ||
      windowMock.CrumpAPI.getSessionToken() !== 'owner-b-token' ||
      storedValues.get(sessionKey) !== 'owner-b-token' ||
      transportCalls.some(call => call[0] === 'billing-disconnect')) {
    throw new Error('A delayed owner-A logout disrupted the newer owner-B native session.');
  }

  // The native token is written before the newly authenticated user is
  // published.  If an owner-A surface clicks logout in that narrow window, the
  // strict server fence returns 409.  That response must not clear owner B's
  // already-installed token or owner A's still-visible document state.
  delayLogout = false;
  rejectLogoutOwner = true;
  const mismatchedLogoutResult = await windowMock.deviceAuth.logout();
  rejectLogoutOwner = false;
  if (mismatchedLogoutResult?.stale !== true || clearLocalStateCalls !== 0 ||
      windowMock.CrumpAPI.getSessionToken() !== 'owner-b-token' ||
      storedValues.get(sessionKey) !== 'owner-b-token' ||
      transportCalls.some(call => call[0] === 'billing-disconnect')) {
    throw new Error('An owner-mismatched native logout cleared the newly installed owner-B token.');
  }

  // A delayed owner-A 401 must likewise be unable to erase a B session/cache
  // that acceptSession has already committed before the auth event is visible.
  windowMock.deviceAuth.acceptSession({user: {id: 'owner-b'}});
  if (clearLocalState('owner-a') !== false ||
      windowMock.deviceAuth.session?.user?.id !== 'owner-b' ||
      JSON.parse(localStorage.getItem('crump_user_cache_v4') || 'null')?.id !== 'owner-b') {
    throw new Error('A stale owner-A clear removed the newer owner-B DeviceAuth session/cache.');
  }

  delayLogout = false;
  boundaryOwner = 'owner-b';
  boundaryRevision += 1;
  windowMock.currentUser = {id: boundaryOwner};
  windowMock.deviceAuth.session = {user: {id: boundaryOwner}};
  await windowMock.deviceAuth.logout();
  if (windowMock.CrumpAPI.getSessionToken() !== null || storedValues.has(sessionKey) ||
      !storageCalls.some(call => JSON.stringify(call) === JSON.stringify(['remove', sessionKey])) ||
      !transportCalls.some(call => JSON.stringify(call) === JSON.stringify(['/api/auth/logout', 'POST'])) ||
      clearLocalStateCalls !== 1 ||
      !transportCalls.some(call => call[0] === 'billing-disconnect')) {
    throw new Error('Native logout did not remove the secure-storage session token.');
  }

  await windowMock.CrumpAPI.setSessionToken('expired-token');
  const unauthorized = await windowMock.fetch('/api/private-fixture');
  const lastFetch = fetchCalls.at(-1);
  if (unauthorized.status !== 401 ||
      lastFetch?.input !== 'https://www.askcrump.com/api/private-fixture' ||
      lastFetch?.headers.get('Authorization') !== 'Bearer expired-token' ||
      windowMock.CrumpAPI.getSessionToken() !== null || storedValues.has(sessionKey) ||
      storageCalls.filter(call => call[0] === 'remove' && call[1] === sessionKey).length !== 2) {
    throw new Error('A native 401 did not clear the rejected secure-storage session token.');
  }
}

await exerciseNativeSecureStorageAuthLifecycle();

const nativeLogoutSource = deviceAuthSource.slice(
  deviceAuthSource.indexOf('  async logout('),
  deviceAuthSource.indexOf(
    '\n  clearLocalState(expectedOwnerId = null)',
    deviceAuthSource.indexOf('  async logout('),
  ),
);
if (!nativeLogoutSource.includes('await window.BillingManager?.disconnect?.().catch(() => {});') ||
    !nativeLogoutSource.includes('this.clearLocalState(ownerId || null)') ||
    nativeLogoutSource.indexOf('this.clearLocalState(ownerId || null)') >
      nativeLogoutSource.indexOf('await window.BillingManager?.disconnect?.().catch(() => {});')) {
  console.error('Native sign-out must clear local auth before disconnecting the persisted billing identity.');
  process.exit(1);
}

const installPromptSource = await readFile(new URL('public/install-prompt.js', repoRoot), 'utf8');
if (!installPromptSource.includes("type === 'checkbox' || type === 'radio'") ||
    !installPromptSource.includes('input.checked === true') ||
    !installPromptSource.includes("type === 'file'") ||
    !installPromptSource.includes('Boolean(input.files?.length)') ||
    !installPromptSource.includes('.some(authInputHasWork)') ||
    installPromptSource.includes('some(input => Boolean(input.value))')) {
  console.error('Runtime updates must distinguish default control values from genuine auth-form work.');
  process.exit(1);
}
async function simulateServiceWorkerRegistration(hasExistingRegistration) {
  const windowListeners = new Map();
  const storage = {
    getItem() { return null; },
    setItem() {},
  };
  let registrationCalls = 0;
  const registration = {update: async () => {}};
  const navigatorMock = {
    standalone: false,
    serviceWorker: {
      controller: null,
      addEventListener() {},
      getRegistration: async () => hasExistingRegistration ? registration : null,
      register: async () => {
        registrationCalls += 1;
        return registration;
      },
    },
  };
  const windowMock = {
    CrumpAPI: {isNative: false},
    currentUser: null,
    localStorage: storage,
    matchMedia: () => ({matches: false}),
    navigator: navigatorMock,
    safeStorage: storage,
    addEventListener(type, callback) {
      const listeners = windowListeners.get(type) || [];
      listeners.push(callback);
      windowListeners.set(type, listeners);
    },
  };
  const documentMock = {
    hidden: false,
    readyState: 'complete',
    addEventListener() {},
    getElementById() { return null; },
    querySelector() { return null; },
  };
  runInContext(installPromptSource, createContext({
    MutationObserver: class { observe() {} },
    console,
    document: documentMock,
    navigator: navigatorMock,
    requestAnimationFrame: callback => callback(),
    setTimeout,
    window: windowMock,
  }));
  for (const callback of windowListeners.get('load') || []) await callback();
  await Promise.resolve();
  await Promise.resolve();
  const afterLoad = registrationCalls;
  for (const callback of windowListeners.get('crump:authenticated-ready') || []) await callback();
  await Promise.resolve();
  await Promise.resolve();
  return {afterLoad, afterAuthentication: registrationCalls};
}
const freshRegistrationScenario = await simulateServiceWorkerRegistration(false);
const existingRegistrationScenario = await simulateServiceWorkerRegistration(true);
if (freshRegistrationScenario.afterLoad !== 0 || freshRegistrationScenario.afterAuthentication !== 1 ||
    existingRegistrationScenario.afterLoad !== 1 || existingRegistrationScenario.afterAuthentication !== 1) {
  console.error('Service-worker registration must wait for authentication only on a genuinely new browser.');
  process.exit(1);
}

const uiFunctions = await readFile(new URL('public/ui-functions.js', repoRoot), 'utf8');
const presenceManager = await readFile(new URL('public/presence-manager.js', repoRoot), 'utf8');
const designPass = await readFile(new URL('public/crump-design-pass.css', repoRoot), 'utf8');
const projectRelationshipGuard = uiFunctions.slice(
  uiFunctions.indexOf('async function hydrateOutcomeProjectAction'),
  uiFunctions.indexOf('function syncOutcomeProjectActions'),
);
if (!projectRelationshipGuard.includes("button.dataset.projectLookup = 'pending';") ||
    !projectRelationshipGuard.includes('button.disabled = true;') ||
    !projectRelationshipGuard.includes("button.setAttribute('aria-busy', 'true');") ||
    !projectRelationshipGuard.includes("button.textContent = 'Checking Project…';") ||
    !projectRelationshipGuard.includes("if (button.dataset.saved !== 'true') syncOutcomeProjectAction(button);") ||
    !projectRelationshipGuard.includes('button.disabled = wasDisabled;') ||
    projectRelationshipGuard.indexOf('button.disabled = true;') > projectRelationshipGuard.indexOf('await lookup(chatId)')) {
  console.error('A Project continuity action must stay unavailable until its owner-scoped relationship lookup settles.');
  process.exit(1);
}
const projectSaveActivationGuard = uiFunctions.slice(
  uiFunctions.indexOf('async function performOutcomeProjectAction'),
  uiFunctions.indexOf('async function keepLatestOutcomeInProject'),
);
if (!projectSaveActivationGuard.includes("window.CrumpAnalytics?.track?.('ProjectSaveIntentReached'") ||
    !projectSaveActivationGuard.includes("eventKey: 'project-save-intent'") ||
    !projectSaveActivationGuard.includes("source: targetProjectId ? 'existing_project' : 'new_project'") ||
    !projectSaveActivationGuard.includes("continuitySource: 'result_action'") ||
    !projectSaveActivationGuard.includes("projectButton.textContent = 'Saving…';") ||
    !uiFunctions.includes("await hydrateOutcomeProjectAction(projectButton)") ||
    !projectSaveActivationGuard.includes("window.showToast?.('Couldn’t save yet. Your conversation is still here.', 'error')") ||
    uiFunctions.includes("continuity.className = 'outcome-continuity'")) {
  console.error('Project save activation must expose pending, recovery, success, and content-free intent states.');
  process.exit(1);
}
const composer50 = await readFile(new URL('public/crump-5.0.js', repoRoot), 'utf8');
if (!composer50.includes('const IMAGE_REFERENCE_LIMIT = 4;') ||
    !composer50.includes('imageReferenceContractVersion = 2') ||
    !composer50.includes('imageReferenceContractVersion:2') ||
    !composer50.includes('body.imageReferencePlan = imageReferencePlan(references);') ||
    !composer50.includes('Confirm what each reference controls before Crump uses credits.') ||
    !composer50.includes('Crump sends every confirmed reference as a numbered visual constraint') ||
    !composer50.includes('IMAGE_REFERENCE_CONFIRMATION_REQUIRED') ||
    !composer50.includes('IMAGE_REFERENCE_PLAN_INVALID') ||
    !composer50.includes('reopenImageReferencePlan') ||
    !composer50.includes('crump50-reference-receipt') ||
    !composer50.includes('Add exact logo or wordmark') ||
    !appRuntime.includes("'referencePlan', 'referenceReview'") ||
    !product53.includes('const VIDEO_REFERENCE_ROLE_OPTIONS = Object.freeze([') ||
    !product53.includes('const referencePlan = videoReferencePlan();') ||
    !product53.includes('state.videoReferencePlanConfirmation !== confirmationSignature') ||
    !product53.includes("button.textContent = 'Confirm & create video';") ||
    !product53.includes('referenceFileIds: state.videoReferenceFiles.map') ||
    !product53.includes('referencePlan,') ||
    !product53.includes('function hydrateVideoHandoffReferences') ||
    !product53.includes('state.videoReferenceHandoffInvalid = true;') ||
    !product53.includes('best-effort appearance guidance') ||
    !precisionEditor.includes("entryMode === 'overlay'") ||
    !precisionEditor.includes('Place an exact logo or wordmark.') ||
    !precisionEditor.includes('flattened PNG or WebP wordmark') ||
    !composer50.includes("form.append('cacheControl', '0')") ||
    !composer50.includes("['cacheControl', '0']") ||
    composer50.includes("form.append('cacheControl', '3600')") ||
    composer50.includes("['cacheControl', '3600']") ||
    !composer50.includes('data-artifact-open') ||
    !composer50.includes('openFile(message.artifact)')) {
  console.error('Reference plans, exact overlays, private uploads, and generated artifact cards must keep their combined delivery contract.');
  process.exit(1);
}
const outputProjectActionGuard = composer50.slice(
  composer50.indexOf('function wireOutputProjectAction'),
  composer50.indexOf('function enhanceRenderedMessages'),
);
if (!outputProjectActionGuard.includes("button.textContent = 'Saving…';") ||
    !outputProjectActionGuard.includes('Saving file and conversation privately…') ||
    !outputProjectActionGuard.includes("window.CrumpAnalytics?.track?.('ProjectSaveIntentReached'") ||
    !outputProjectActionGuard.includes("source: selectedProjectId ? 'existing_project' : 'new_project'") ||
    !outputProjectActionGuard.includes('if (selectedProjectId) options.projectId = selectedProjectId;') ||
    !outputProjectActionGuard.includes('button.textContent = previousLabel;') ||
    !product53.includes("body: {fileId, role, continuitySource: 'result_action'}")) {
  console.error('Generated-output Project controls must expose pending/recovery states and measured private continuity.');
  process.exit(1);
}
const markdownWindow = {
  crypto: { randomUUID: () => 'markdown-contract' },
  location: { origin: 'https://www.askcrump.com' },
};
runInContext(uiFunctions, createContext({
  document: {},
  URL,
  window: markdownWindow,
}));
const renderedMarkdown = markdownWindow.renderMarkdown([
  '| Category | Amount |',
  '| --- | ---: |',
  '| Venue | $600 |',
  '',
  '> Bring something unfinished.',
  '> Keep the work moving.',
  '',
  '1. Choose the goal',
  '2. Build the plan',
  '',
  '<script>alert(1)</script>',
].join('\n'));
if (!renderedMarkdown.includes('<table>') ||
    !renderedMarkdown.includes('<th scope="col">Category</th>') ||
    !renderedMarkdown.includes('<td>$600</td>') ||
    !renderedMarkdown.includes('<blockquote>Bring something unfinished.<br>Keep the work moving.</blockquote>') ||
    !renderedMarkdown.includes('<ol><li>Choose the goal</li><li>Build the plan</li></ol>') ||
    !renderedMarkdown.includes('&lt;script&gt;alert(1)&lt;/script&gt;') ||
    renderedMarkdown.includes('<script>')) {
  console.error('Safe Markdown renderer must support tables, quotations, and ordered lists without allowing HTML injection.');
  process.exit(1);
}

function shareContractEnvironment({ legacyCopyResult }) {
  const analytics = [];
  const toasts = [];
  const area = {
    style: {},
    value: '',
    select() {},
    remove() {},
  };
  const shareWindow = {
    crypto: { randomUUID: () => 'share-contract' },
    location: { origin: 'https://www.askcrump.com' },
    currentChatId: 'chat-1',
    chats: [{
      id: 'chat-1',
      messages: [{id: 'response-1', content: 'A useful answer.'}],
    }],
    CrumpAnalytics: {
      async track(eventName, values) {
        analytics.push({eventName, ...values});
        return true;
      },
    },
  };
  const shareDocument = {
    body: {appendChild() {}},
    createElement(name) {
      if (name !== 'textarea') throw new Error(`Unexpected share contract element: ${name}`);
      return area;
    },
    execCommand(command) {
      return command === 'copy' && legacyCopyResult;
    },
  };
  const context = createContext({
    document: shareDocument,
    navigator: {clipboard: {async writeText() { throw new Error('denied'); }}},
    URL,
    window: shareWindow,
  });
  runInContext(uiFunctions, context);
  shareWindow.showToast = (message, tone) => toasts.push({message, tone});
  return {analytics, shareWindow, toasts};
}

const failedShare = shareContractEnvironment({legacyCopyResult: false});
if (await failedShare.shareWindow.shareMessage(0) !== false ||
    failedShare.analytics.length !== 0 ||
    !failedShare.toasts.some(toast => toast.tone === 'error')) {
  console.error('A failed clipboard fallback must not report or record a successful share.');
  process.exit(1);
}

const copiedShare = shareContractEnvironment({legacyCopyResult: true});
if (await copiedShare.shareWindow.shareMessage(0) !== true ||
    copiedShare.analytics.length !== 1 ||
    copiedShare.analytics[0].eventName !== 'ResponseShared' ||
    copiedShare.analytics[0].source !== 'clipboard' ||
    !copiedShare.toasts.some(toast => toast.tone === 'success')) {
  console.error('A verified clipboard fallback must record exactly one successful share.');
  process.exit(1);
}
const scroll522 = await readFile(new URL('public/crump-5.2.2.js', repoRoot), 'utf8');
const baseScroll = await readFile(new URL('public/scroll-manager.js', repoRoot), 'utf8');
const chatResilience = await readFile(new URL('public/chat-resilience.js', repoRoot), 'utf8');
const scroll522Css = await readFile(new URL('public/crump-5.2.2.css', repoRoot), 'utf8');
const billing52 = await readFile(new URL('public/crump-5.2.js', repoRoot), 'utf8');
const billing52Css = await readFile(new URL('public/crump-5.2.css', repoRoot), 'utf8');
if (!chatResilience.includes("!['prompt_or_reference', 'reference'].includes(changeRequired)") ||
    !composer50.includes("'INVALID_IMAGE_EDIT_SOURCE'") ||
    !composer50.includes("'IMAGE_EDIT_SOURCE_TOO_LARGE'") ||
    !composer50.includes("if (recovery.changeRequired === 'reference')") ||
    !composer50.includes("if (replacingReference) $('#fileInput')?.click();") ||
    !uiFunctions.includes('Reference image needs replacement — Tap to replace')) {
  console.error('Image reference rejection recovery must remain allowlisted, replacement-only, and actionable.');
  process.exit(1);
}
if (!uiFunctions.includes('const preservedScrollTop = container.scrollTop;') ||
    !uiFunctions.includes('if (container.scrollTop !== preservedScrollTop) container.scrollTop = preservedScrollTop;') ||
    uiFunctions.includes("window.crumpScrollManager.scrollToBottom('auto')") ||
    uiFunctions.includes('typewriter') ||
    uiFunctions.includes('container.scrollTop = container.scrollHeight')) {
  console.error('Conversation rendering must preserve the user-selected viewport without automatic movement.');
  process.exit(1);
}
const presenceExpansionTimer = presenceManager.slice(
  presenceManager.indexOf('activityTimer = setTimeout'),
  presenceManager.indexOf('// Rotate the visible verb'),
);
const presenceRotationTimer = presenceManager.slice(
  presenceManager.indexOf('warmVerbTimer = setInterval'),
  presenceManager.indexOf('function update'),
);
if (presenceExpansionTimer.includes('rerender()') ||
    presenceRotationTimer.includes('rerender()') ||
    !presenceManager.includes('refreshVisiblePresence({ensureLabel: true});') ||
    !presenceManager.includes('refreshVisiblePresence();')) {
  console.error('Presence timers must update their visible status without rebuilding conversation nodes.');
  process.exit(1);
}
if (appHtml.includes('/crump-design-pass.css') ||
    designPass.includes('@keyframes dp-msg-in') ||
    !designPass.includes('@media (prefers-reduced-motion: reduce)') ||
    !designPass.includes('animation: none !important;')) {
  console.error('Design polish must remain authenticated, message-stable, and reduced-motion safe.');
  process.exit(1);
}
if (!scroll522.includes('function jumpToNewest()') ||
    !scroll522.includes("button.addEventListener('click'") ||
    !scroll522.includes('scrollToBottom: () => undefined') ||
    !scroll522.includes('autoScrollToBottom: () => undefined') ||
    !scroll522.includes('scrollToMessageTop: () => undefined') ||
    scroll522.includes('anchorNewReply') ||
    scroll522.includes('activeReplyShouldHold') ||
    !scroll522.includes("behavior: 'auto'") ||
    scroll522.includes("behavior: 'smooth'") ||
    (scroll522.match(/\.scrollTo\(/g) || []).length !== 1) {
  console.error('Only the explicit newest-message control may move the enhanced conversation feed.');
  process.exit(1);
}
if (!baseScroll.includes('function jumpToNewest(event)') ||
    !baseScroll.includes('scrollToBottom: () => undefined') ||
    !baseScroll.includes('autoScrollToBottom: () => undefined') ||
    !baseScroll.includes('scrollToMessageTop: () => undefined') ||
    !baseScroll.includes("behavior: 'auto'") ||
    baseScroll.includes("behavior: 'smooth'") ||
    (baseScroll.match(/\.scrollTo\(/g) || []).length !== 1) {
  console.error('Only the explicit newest-message control may move the base conversation feed.');
  process.exit(1);
}
if (composer50.includes('crumpScrollManager?.scrollToBottom') ||
    appRuntime.includes('safeScrollToBottom') ||
    !uiFunctions.includes('function imageAspectForMessage(message, messages)') ||
    !uiFunctions.includes('const reusableImages = new Map();') ||
    !uiFunctions.includes('const reusableAttachments = new Map();') ||
    !uiFunctions.includes("row.querySelector('.crump52-rich-attachments')") ||
    !uiFunctions.includes('wrapper.appendChild(reusableAttachmentBlock);') ||
    !uiFunctions.includes("reusableImage?.getAttribute('src') === safe") ||
    !billing52.includes('function attachmentSignature(files)') ||
    !billing52.includes('existing?.dataset.attachmentSignature === signature') ||
    !billing52.includes('host.dataset.attachmentSignature = signature;') ||
    !uiFunctions.includes('image.width = aspect.width;') ||
    !uiFunctions.includes('image.height = aspect.height;')) {
  console.error('Generated-image user-controlled scroll and reserved-layout contract is missing.');
  process.exit(1);
}
if (!scroll522.includes('const preservedScrollTop = container?.scrollTop ?? 0;') ||
    !scroll522.includes('if (container && container.scrollTop !== preservedScrollTop) container.scrollTop = preservedScrollTop;')) {
  console.error('5.2.2 must preserve the user-selected offset across same-message rerenders.');
  process.exit(1);
}
if (!scroll522.includes('latestCompletedAssistantId') ||
    !scroll522.includes("state.scroll.button?.setAttribute('aria-label', 'New response available. Jump to newest message')") ||
    !scroll522.includes("status.setAttribute('aria-live', 'polite')") ||
    !scroll522.includes("status.setAttribute('aria-atomic', 'true')") ||
    !scroll522.includes('if (chatId !== state.scroll.chatId)') ||
    !scroll522Css.includes("[data-new-response='true']::after")) {
  console.error('The non-moving, content-free new-response cue is missing or incomplete.');
  process.exit(1);
}
if (scroll522.includes('requestAnimationFrame(() => {\n      requestAnimationFrame(() => {')) {
  console.error('Conversation rendering must not schedule delayed viewport movement.');
  process.exit(1);
}
if (!scroll522Css.includes('overflow-anchor: none !important;')) {
  console.error('Conversation viewport must disable browser-native scroll anchoring.');
  process.exit(1);
}
if (billing52.includes("article.setAttribute('role', 'button')") ||
    billing52.includes('article.tabIndex') ||
    scroll522.includes("card.setAttribute('role', 'button')") ||
    scroll522.includes('card.tabIndex = 0')) {
  console.error('Credit packs must not expose a nested card-and-button interaction model.');
  process.exit(1);
}
if (!scroll522.includes("card.removeAttribute('role')") ||
    !scroll522.includes("card.removeAttribute('tabindex')") ||
    !scroll522.includes("button.setAttribute('aria-label', accessibleLabel)") ||
    !scroll522.includes("closest('.billing51-buy[data-crump-pack]')") ||
    !billing52.includes('Add ${Number(pack.credits) || 0} Crump Credits for') ||
    !billing52Css.includes('.billing51-pack[data-crump-pack]:focus-within')) {
  console.error('Each credit pack must expose one uniquely named, keyboard-owned purchase control.');
  process.exit(1);
}

console.log('Ask Crump V1 new-body integration contract validated.');
console.log(`Validated ${roughToUsefulRuntimeCases}/24 rough-to-useful attribution runtime cases.`);
console.log(`Validated ${wordPdfRuntimeCases}/10 Word/PDF attribution runtime cases.`);
console.log(`Validated ${resumeAuditRuntimeCases}/10 résumé audit attribution runtime cases.`);
console.log(`Validated ${files.length} JavaScript files.`);

const storeSubmissionGate = spawnSync(
  process.execPath,
  [fileURLToPath(new URL('verify-store-submission-packet.mjs', import.meta.url)), '--self-test'],
  { encoding: 'utf8', shell: false },
);
if (storeSubmissionGate.status !== 0) {
  process.stderr.write(storeSubmissionGate.stderr || storeSubmissionGate.stdout || 'Store submission packet gate self-test failed.\n');
  process.exit(storeSubmissionGate.status ?? 1);
}
process.stdout.write(storeSubmissionGate.stdout);
