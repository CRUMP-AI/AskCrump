import { access, readdir, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createContext, runInContext } from 'node:vm';

const expectedFiles = new Set([
  'account-manager.js', 'app.js', 'auth-controller.js', 'auth-resilience.js', 'billing-manager.js', 'chat-resilience.js', 'chat-sync.js',
  'crump-4.3.js', 'crump-4.4.js', 'crump-5.0.js', 'crump-billing-5.1.js',
  'crump-precision-image-edit.js',
  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-navigation-5.2.5.js',
  'crump-navigation-5.9.30.js',
  'crump-code-5.9.35.js',
  'credit-confirmation.js',
  'crump-v1.js', 'crump-v1-body.js', 'crump-v1-stability.js', 'crump-product-5.3.js',
  'crump-product-5.3.1.js', 'crump-subscriptions-5.3.2.js', 'crump-polish-5.6.js',
  'crump-library-5.7.js',
  'device-auth.js', 'install-prompt.js', 'landing.js', 'mobile-bridge.js', 'native-entry.js',
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

for (const [label, invalidUrl] of [
  [
    'Rough-to-useful Facebook Story',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=facebook&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-story',
  ],
  [
    'Rough-to-useful Instagram cross-product',
    'https://askcrump.com/guides/rough-idea-six-week-launch-plan?acquisition=instagram&source=organic-social&campaign=rough-to-useful-v2&creative=rough-to-useful-current-feed',
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
if (roughToUsefulRuntimeCases !== 21) {
  console.error(`Expected 21 rough-to-useful runtime cases, got ${roughToUsefulRuntimeCases}.`);
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
  '/app?signup=1&source=word-pdf-start&plan=free&intent=document&acquisition=direct',
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
    wordPdfDirectDestination.searchParams.get('plan') !== 'free' ||
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
  '/app?signup=1&source=word-pdf-start&plan=free&intent=document&acquisition=direct',
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
    wordPdfGuideDestination.searchParams.get('plan') !== 'free' ||
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
const landingVersion = `${releaseVersion}-paid-attribution-1`;
const attributionVersion = `${releaseVersion}-paid-attribution-1`;
const planRendererVersion = `${releaseVersion}-credit-pack-accessibility-1`;
const commerceRecoveryVersion = `${releaseVersion}-commerce-recovery-1`;
const nativeBillingIdentityVersion = `${releaseVersion}-native-billing-identity-1`;
const creditCheckoutIdempotencyVersion = `${releaseVersion}-credit-checkout-idempotency-1`;
const checkoutSessionRecoveryVersion = `${releaseVersion}-checkout-session-recovery-1`;
const creditPackTruthVersion = `${releaseVersion}-credit-pack-truth-1`;
const creditTruthVersion = `${releaseVersion}-credit-truth-1`;
const attachCreationRoutingVersion = `${releaseVersion}-explicit-button-types-1`;
const creditConfirmationVersion = `${releaseVersion}-credit-confirmation-1`;
const settingsSaveIsolationVersion = `${releaseVersion}-settings-save-isolation-1`;
const outputProjectActionVersion = `${releaseVersion}-output-project-action-1`;
const productButtonOwnershipVersion = `${releaseVersion}-button-ownership-1`;
const composerModeResetVersion = `${releaseVersion}-composer-mode-reset-1`;
const accountDeletionBillingVersion = `${releaseVersion}-account-deletion-billing-1`;
const intelligenceReceiptVersion = `${releaseVersion}-intelligence-receipt-1`;
const intelligenceArchitectureVersion = `${releaseVersion}-intelligence-architecture-1`;
const coreReliabilityVersion = `${releaseVersion}-core-reliability-1`;
const settingsProfileTrustVersion = `${releaseVersion}-settings-profile-trust-8`;
const precisionEditGuideLoaderVersion = `${releaseVersion}-live-image-preview-loader-1`;
const precisionEditGuideVersion = `${releaseVersion}-button-integrity-1`;
const fileLibraryWindowVersion = `${releaseVersion}-file-library-window-1`;
const imageReferenceRecoveryVersion = `${releaseVersion}-image-reference-recovery-1`;
const liveImagePreviewVersion = `${releaseVersion}-precision-studio-1`;
const settingsSyncVersion = `${releaseVersion}-settings-sync-1`;
const syncCursorVersion = `${releaseVersion}-sync-cursor-1`;
const imageNodeStabilityVersion = `${releaseVersion}-image-node-stability-1`;
const uploadedImageNodeStabilityVersion = `${releaseVersion}-uploaded-image-node-stability-1`;
const projectSaveMeasurementVersion = `${releaseVersion}-project-save-measurement-1`;
const outcomeIssueCategoriesVersion = `${releaseVersion}-outcome-issue-categories-1`;
const outcomeRefinementRecoveryVersion = `${releaseVersion}-outcome-refinement-recovery-1`;
const authUpdateGuardVersion = `${releaseVersion}-update-work-guard-1`;
const userControlledScrollVersion = `${releaseVersion}-user-controlled-scroll-1`;
const newResponseCueVersion = `${releaseVersion}-new-response-cue-1`;
const videoDestinationVersion = `${releaseVersion}-video-destination-1`;
const mobileDrawerDestinationsVersion = `${releaseVersion}-mobile-drawer-destinations-1`;
const destinationBackgroundGuardVersion = `${releaseVersion}-destination-background-guard-1`;
const controlFocusIntegrityVersion = `${releaseVersion}-control-focus-integrity-1`;
const referralCancelRecoveryVersion = `${releaseVersion}-referral-cancel-recovery-1`;
const precisionEditEntryVersion = `${releaseVersion}-precision-edit-entry-1`;
const precisionEditStudioVersion = `${releaseVersion}-precision-studio-1`;
const creationSheetContainmentVersion = `${releaseVersion}-creation-sheet-containment-1`;
const requiredBodyFiles = [
  'public/crump-v1-body.css',
  'public/crump-v1-body.js',
  'public/crump-product-5.3.css',
  'public/crump-product-5.3.js',
  'public/crump-product-5.3.1.css',
  'public/crump-product-5.3.1.js',
  'public/crump-subscriptions-5.3.2.js',
  'public/crump-polish-5.6.css',
  'public/crump-polish-5.6.js',
  'public/crump-library-5.7.css',
  'public/crump-library-5.7.js',
  'public/crump-navigation-5.9.30.css',
  'public/crump-navigation-5.9.30.js',
  'public/crump-precision-image-edit.css',
  'public/crump-precision-image-edit.js',
  'public/credit-confirmation.css',
  'public/credit-confirmation.js',
  'public/crump-code-5.9.35.css',
  'public/crump-code-5.9.35.js',
  'public/runtime-body-v1.js',
  'public/lifecycle.css',
  'public/lifecycle-manager.js',
  'public/lifecycle-share.js',
  'public/auth-resilience.js',
  'public/chat-resilience.js',
  'public/assets/brand/crump-mark.png',
  'public/assets/brand/crump-horizontal-light.png',
  'public/assets/brand/crump-shell-lockup-light.png',
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
const destinationLabels = Object.freeze(['Ask', 'Projects', 'Create', 'Video', 'Library', 'You']);
const destinationIds = Object.freeze(destinationLabels.map(label => label.toLowerCase()));
const internalNavigationLabels = Object.freeze(['Ask', 'Projects', 'Code', 'Create', 'Video', 'Library', 'You']);
const onboardingSource = await readFile(new URL('public/onboarding.js', repoRoot), 'utf8');
const navigationSource = await readFile(new URL('public/crump-navigation-5.9.30.js', repoRoot), 'utf8');
const listingSource = JSON.parse(await readFile(new URL('store/listing.en-US.json', repoRoot), 'utf8'));
const screenshotPlanSource = await readFile(new URL('store/screenshots/README.md', repoRoot), 'utf8');
const listingCopySource = await readFile(new URL('docs/STORE_LISTING_COPY.md', repoRoot), 'utf8');
const expectedScreenshotLabels = Object.freeze([
  'Ask', 'Projects', 'Create', 'Video', 'Research in Ask', 'Editable work', 'Library', 'You',
]);
const navigationBlockStart = navigationSource.indexOf('const destinations = Object.freeze([');
const navigationBlockEnd = navigationSource.indexOf(']);', navigationBlockStart);
const navigationLabels = navigationBlockStart >= 0 && navigationBlockEnd > navigationBlockStart
  ? [...navigationSource.slice(navigationBlockStart, navigationBlockEnd).matchAll(/label: '([^']+)'/g)].map(match => match[1])
  : [];
const tutorialDestinationMatch = onboardingSource.match(/const DESTINATIONS = Object\.freeze\(\[([^\]]+)\]\);/);
const tutorialDestinations = tutorialDestinationMatch
  ? [...tutorialDestinationMatch[1].matchAll(/'([^']+)'/g)].map(match => match[1])
  : [];
const screenshotLabels = plan => Array.isArray(plan)
  ? plan.map(item => String(item || '').split(' —')[0].trim())
  : [];
const readmeScreenshotLabels = [...screenshotPlanSource.matchAll(/^\d+\.\s+([^\n—]+?)\s+—/gm)]
  .map(match => match[1].trim());
const destinationCsv = `${destinationLabels.slice(0, -1).join(', ')}, and ${destinationLabels.at(-1)}`;
if (JSON.stringify(navigationLabels) !== JSON.stringify(internalNavigationLabels) ||
    !navigationSource.includes("destination.id === 'code' ? ' data-crump-code-destination hidden' : ''") ||
    JSON.stringify(tutorialDestinations) !== JSON.stringify(destinationLabels) ||
    JSON.stringify(screenshotLabels(listingSource.apple?.screenshotPlan)) !== JSON.stringify(expectedScreenshotLabels) ||
    JSON.stringify(screenshotLabels(listingSource.google?.screenshotPlan)) !== JSON.stringify(expectedScreenshotLabels) ||
    JSON.stringify(readmeScreenshotLabels) !== JSON.stringify(expectedScreenshotLabels) ||
    !listingSource.apple?.description?.includes(`six destinations: ${destinationCsv}`) ||
    !listingSource.google?.fullDescription?.includes(`six clear destinations: ${destinationCsv}`) ||
    !listingCopySource.includes(`Ask, Projects, Create, Video, Library, and You`) ||
    !destinationIds.every(id => onboardingSource.includes(`action: '${id}'`))) {
  console.error('Navigation, workspace guide, and store-release sources disagree on the current six-destination product.');
  process.exit(1);
}
if (!releaseVersion || !landingHtml.includes(`/landing.js?v=${landingVersion}`)) {
  console.error('Ask Crump marketing page is missing its release-versioned script.');
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
  `/runtime-body-v1.js?v=${checkoutSessionRecoveryVersion}`,
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
  '<div class="v1-launchpad-foot" aria-label="Ask Crump destinations">',
  '<span>Ask</span><i></i><span>Projects</span><i></i><span>Create</span><i></i><span>Video</span><i></i><span>Library</span><i></i><span>You</span>',
];

for (const signal of requiredHtmlSignals) {
  if (!appHtml.includes(signal)) {
    console.error(`Ask Crump new body is incomplete: missing ${signal}`);
    process.exit(1);
  }
}

if (appHtml.includes('fonts.googleapis.com') || appHtml.includes('fonts.gstatic.com')) {
  console.error('Ask Crump application shell must not depend on Google Fonts.');
  process.exit(1);
}
if (appHtml.includes('<span>Saved</span>')) {
  console.error('The retired Saved destination must not return to the authenticated launchpad.');
  process.exit(1);
}

const runtime = await readFile(new URL('public/runtime-body-v1.js', repoRoot), 'utf8');
if (!runtime.includes('/billing.css') ||
    !runtime.includes(`/billing-manager.js?v=${checkoutSessionRecoveryVersion}`) ||
    !runtime.includes(`/onboarding.css?v=${videoDestinationVersion}`) ||
    !runtime.includes(`/onboarding.js?v=${precisionEditGuideVersion}`) ||
    !runtime.includes(`/conversation.css?v=${intelligenceReceiptVersion}`) ||
    !runtime.includes(`/credit-confirmation.css?v=${creditConfirmationVersion}`) ||
    !runtime.includes(`/credit-confirmation.js?v=${creditConfirmationVersion}`) ||
    !runtime.includes(`/chat-resilience.js?v=${creditConfirmationVersion}`) ||
    !runtime.includes(`/account-manager.js?v=${accountDeletionBillingVersion}`) ||
    !runtime.includes(`/scroll-manager.js?v=${userControlledScrollVersion}`) ||
    !runtime.includes(`/ui-functions.js?v=${outcomeRefinementRecoveryVersion}`) ||
    !runtime.includes(`/lifecycle.css?v=${releaseVersion}-lifecycle-activation-1`) ||
    !runtime.includes(`/lifecycle-share.js?v=${referralCancelRecoveryVersion}`) ||
    !runtime.includes(`/lifecycle-manager.js?v=${referralCancelRecoveryVersion}`) ||
    !runtime.includes(`/chat-sync.js?v=${settingsSyncVersion}`) ||
    !runtime.includes(`/product-analytics.js?v=${outcomeIssueCategoriesVersion}`) ||
    !runtime.includes(`/app.js?v=${settingsSaveIsolationVersion}`) ||
    !runtime.includes(`/crump-v1-body.js?v=${controlFocusIntegrityVersion}`) ||
    !runtime.includes(`/crump-v1-body.css?v=${creditTruthVersion}`) ||
    !runtime.includes(`/crump-5.0.css?v=${precisionEditEntryVersion}`) ||
    !runtime.includes(`/crump-5.0.js?v=${composerModeResetVersion}`) ||
    !runtime.includes(`/crump-precision-image-edit.css?v=${precisionEditStudioVersion}`) ||
    !runtime.includes(`/crump-precision-image-edit.js?v=${liveImagePreviewVersion}`) ||
    !runtime.includes(`/crump-billing-5.1.js?v=${creditCheckoutIdempotencyVersion}`) ||
    !runtime.includes(`/crump-5.2.js?v=${creditCheckoutIdempotencyVersion}`) ||
    !runtime.includes(`/crump-5.2.2.css?v=${newResponseCueVersion}`) ||
    !runtime.includes(`/crump-5.2.2.js?v=${checkoutSessionRecoveryVersion}`) ||
    !runtime.includes(`/crump-4.3.js?v=${intelligenceArchitectureVersion}`) ||
    !runtime.includes(`/crump-4.4.js?v=${coreReliabilityVersion}`) ||
    !runtime.includes(`/crump-v1-stability.js?v=${intelligenceArchitectureVersion}`) ||
    !runtime.includes(`/crump-product-5.3.js?v=${productButtonOwnershipVersion}`) ||
    !runtime.includes(`/crump-product-5.3.css?v=${fileLibraryWindowVersion}`) ||
    !runtime.includes(`/crump-product-5.3.1.js?v=${coreReliabilityVersion}`) || !runtime.includes('/crump-product-5.3.1.css') ||
    !runtime.includes('/crump-subscriptions-5.3.2.js') ||
    !runtime.includes(`/crump-polish-5.6.js?v=${videoDestinationVersion}`) || !runtime.includes('/crump-polish-5.6.css') ||
    !runtime.includes('/crump-library-5.7.js') || !runtime.includes('/crump-library-5.7.css') ||
    !runtime.includes(`/crump-navigation-5.9.30.js?v=${destinationBackgroundGuardVersion}`) ||
    !runtime.includes(`/crump-navigation-5.9.30.css?v=${mobileDrawerDestinationsVersion}`) ||
    !runtime.includes(`/crump-code-5.9.35.js?v=${creditConfirmationVersion}`) ||
    !runtime.includes(`/crump-code-5.9.35.css?v=${intelligenceArchitectureVersion}`)) {
  console.error('New-body runtime is missing the canonical shell.');
  process.exit(1);
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
    preloadedRuntimeScripts.length !== 33 ||
    loadedRuntimeScripts.length !== 33 ||
    !loadedRuntimeScripts.every(asset => preloadedRuntimeScripts.includes(asset)) ||
    loadedRuntimeScripts.indexOf(`/credit-confirmation.js?v=${creditConfirmationVersion}`) > loadedRuntimeScripts.indexOf(`/app.js?v=${settingsSaveIsolationVersion}`) ||
    loadedRuntimeScripts.indexOf(`/app.js?v=${settingsSaveIsolationVersion}`) > loadedRuntimeScripts.indexOf(`/crump-4.3.js?v=${intelligenceArchitectureVersion}`) ||
    loadedRuntimeScripts.at(-1) !== `/lifecycle-manager.js?v=${referralCancelRecoveryVersion}`) {
  console.error('Authenticated workspace runtime load order or completion contract failed.');
  process.exit(1);
}

const crump43 = await readFile(new URL('public/crump-4.3.js', repoRoot), 'utf8');
const v1Body = await readFile(new URL('public/crump-v1-body.js', repoRoot), 'utf8');
const appRuntime = await readFile(new URL('public/app.js', repoRoot), 'utf8');
const product53 = await readFile(new URL('public/crump-product-5.3.js', repoRoot), 'utf8');
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
if (!serviceWorker.includes('ask-crump-new-body-v1-r227') ||
    !serviceWorker.includes(`/landing.js?v=${landingVersion}`) ||
    !serviceWorker.includes(`/runtime-body-v1.js?v=${checkoutSessionRecoveryVersion}`) ||
    !serviceWorker.includes(`/conversation.css?v=${intelligenceReceiptVersion}`) ||
    !serviceWorker.includes(`/credit-confirmation.css?v=${creditConfirmationVersion}`) ||
    !serviceWorker.includes(`/credit-confirmation.js?v=${creditConfirmationVersion}`) ||
    !serviceWorker.includes(`/chat-resilience.js?v=${creditConfirmationVersion}`) ||
    !serviceWorker.includes(`/account-manager.js?v=${accountDeletionBillingVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.css?v=${precisionEditEntryVersion}`) ||
    !serviceWorker.includes(`/scroll-manager.js?v=${userControlledScrollVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.js?v=${composerModeResetVersion}`) ||
    !serviceWorker.includes(`/crump-precision-image-edit.css?v=${precisionEditStudioVersion}`) ||
    !serviceWorker.includes(`/crump-precision-image-edit.js?v=${liveImagePreviewVersion}`) ||
    !serviceWorker.includes(`/ui-functions.js?v=${outcomeRefinementRecoveryVersion}`) ||
    !serviceWorker.includes(`/app.js?v=${settingsSaveIsolationVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.2.css?v=${newResponseCueVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.2.js?v=${checkoutSessionRecoveryVersion}`) ||
    !serviceWorker.includes(`/onboarding.css?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/onboarding.js?v=${precisionEditGuideVersion}`) ||
    !serviceWorker.includes(`/crump-polish-5.6.js?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.css?v=${mobileDrawerDestinationsVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.js?v=${destinationBackgroundGuardVersion}`) ||
    !serviceWorker.includes(`/lifecycle.css?v=${releaseVersion}-lifecycle-activation-1`) ||
    !serviceWorker.includes(`/lifecycle-share.js?v=${referralCancelRecoveryVersion}`) ||
    !serviceWorker.includes(`/lifecycle-manager.js?v=${referralCancelRecoveryVersion}`) ||
    !serviceWorker.includes(`/auth-resilience.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/install-prompt.js?v=${authUpdateGuardVersion}`) ||
    !serviceWorker.includes(`/install-prompt.css?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/device-auth.js?v=${nativeBillingIdentityVersion}`) ||
    !serviceWorker.includes(`/sync-manager.js?v=${syncCursorVersion}`) ||
    !serviceWorker.includes(`/chat-sync.js?v=${settingsSyncVersion}`) ||
    !serviceWorker.includes(`/product-analytics.js?v=${outcomeIssueCategoriesVersion}`) ||
    !serviceWorker.includes(`/auth-controller.js?v=${attributionVersion}`) ||
    !serviceWorker.includes(`/crump-v1-body.css?v=${creditTruthVersion}`) ||
    !serviceWorker.includes(`/crump-4.3.js?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-4.4.js?v=${coreReliabilityVersion}`) ||
    !serviceWorker.includes(`/crump-v1-stability.js?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.js?v=${productButtonOwnershipVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.1.js?v=${coreReliabilityVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.css?v=${fileLibraryWindowVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.js?v=${destinationBackgroundGuardVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.css?v=${mobileDrawerDestinationsVersion}`) ||
    !serviceWorker.includes(`/crump-code-5.9.35.js?v=${creditConfirmationVersion}`) ||
    !serviceWorker.includes(`/crump-code-5.9.35.css?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes("url.pathname === '/conversation.css'") ||
    !serviceWorker.includes("url.pathname === '/credit-confirmation.css'") ||
    !serviceWorker.includes("url.pathname === '/credit-confirmation.js'") ||
    !serviceWorker.includes("url.pathname === '/chat-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-precision-image-edit.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-precision-image-edit.css'") ||
    !serviceWorker.includes("url.pathname === '/ui-functions.js'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle.css'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle-share.js'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.css'") ||
    !serviceWorker.includes("url.pathname === '/sync-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-controller.js'") ||
    !serviceWorker.includes(`/crump-v1-body.js?v=${controlFocusIntegrityVersion}`) ||
    !serviceWorker.includes('/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1') ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-5.9.35.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-5.9.35.css'") ||
    !serviceWorker.includes(`/billing-manager.js?v=${checkoutSessionRecoveryVersion}`) ||
    !serviceWorker.includes(`/subscription-ui.js?v=${commerceRecoveryVersion}`) ||
    !serviceWorker.includes(`/crump-billing-5.1.css?v=${creditTruthVersion}`) ||
    !serviceWorker.includes(`/crump-billing-5.1.js?v=${creditCheckoutIdempotencyVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.js?v=${creditCheckoutIdempotencyVersion}`) ||
    !serviceWorker.includes(`/crump-subscriptions-5.3.2.js?v=${checkoutSessionRecoveryVersion}`) ||
    !serviceWorker.includes('/crump-library-5.7.js') ||
    !serviceWorker.includes('/crump-library-5.7.css')) {
  console.error('New-body service-worker contract is incomplete.');
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
const nativeLogoutSource = deviceAuthSource.slice(
  deviceAuthSource.indexOf('  async logout('),
  deviceAuthSource.indexOf('\n  clearLocalState()', deviceAuthSource.indexOf('  async logout(')),
);
if (!nativeLogoutSource.includes('await window.BillingManager?.disconnect?.().catch(() => {});') ||
    nativeLogoutSource.indexOf('this.clearLocalState();') >
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
    !projectSaveActivationGuard.includes("continuityPrompt.textContent = 'Saving this conversation privately…';") ||
    !projectSaveActivationGuard.includes("continuityPrompt.textContent = 'Couldn’t save yet. Your conversation is still here.';") ||
    !uiFunctions.includes('Saved privately to "${projectName}".')) {
  console.error('Project save activation must expose pending, recovery, success, and content-free intent states.');
  process.exit(1);
}
const composer50 = await readFile(new URL('public/crump-5.0.js', repoRoot), 'utf8');
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
    uiFunctions.includes("window.crumpScrollManager.scrollToBottom('auto')")) {
  console.error('Conversation rendering must preserve the user-selected viewport without automatic movement.');
  process.exit(1);
}
if (!scroll522.includes('function jumpToNewest()') ||
    !scroll522.includes("button.addEventListener('click'") ||
    !scroll522.includes('scrollToBottom: () => undefined') ||
    !scroll522.includes('autoScrollToBottom: () => undefined') ||
    !scroll522.includes('scrollToMessageTop: () => undefined') ||
    scroll522.includes('anchorNewReply') ||
    scroll522.includes('activeReplyShouldHold') ||
    (scroll522.match(/\.scrollTo\(/g) || []).length !== 1) {
  console.error('Only the explicit newest-message control may move the enhanced conversation feed.');
  process.exit(1);
}
if (!baseScroll.includes('function jumpToNewest(event)') ||
    !baseScroll.includes('scrollToBottom: () => undefined') ||
    !baseScroll.includes('autoScrollToBottom: () => undefined') ||
    !baseScroll.includes('scrollToMessageTop: () => undefined') ||
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
console.log(`Validated ${roughToUsefulRuntimeCases}/21 rough-to-useful attribution runtime cases.`);
console.log(`Validated ${wordPdfRuntimeCases}/10 Word/PDF attribution runtime cases.`);
console.log(`Validated ${files.length} JavaScript files.`);
