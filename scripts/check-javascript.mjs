import { access, readdir, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createContext, runInContext } from 'node:vm';

const expectedFiles = new Set([
  'account-manager.js', 'app.js', 'auth-controller.js', 'auth-resilience.js', 'billing-manager.js', 'chat-resilience.js', 'chat-sync.js',
  'crump-4.3.js', 'crump-4.4.js', 'crump-5.0.js', 'crump-billing-5.1.js',
  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-navigation-5.2.5.js',
  'crump-navigation-5.9.30.js',
  'crump-code-5.9.35.js',
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

  const result = spawnSync(process.execPath, ['--check', fileURLToPath(path)], { stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

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
  creative: 'ig-feed',
  intent: 'presentation',
};
const validPathStore = new Map();
const validPath = runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link&campaign=presentation-proof-current&creative=ig-feed&intent=presentation',
  validPathStore,
  '/app?signup=1&intent=presentation',
);
assertAttribution(storedAttribution(validPathStore), presentationTouch, 'Valid campaign path');
assertMarketingLanding(validPath, {
  touchpoint: 'instagram.profile-link.presentation-proof-current.ig-feed',
  intent: 'presentation',
}, 'Valid campaign path');
const validDestination = new URL(validPath.link.href, 'https://askcrump.com');
const validCtaEvent = validPath.events.find(event => event.payload?.name === 'MarketingCTA');
if (validDestination.searchParams.get('campaign') !== 'presentation-proof-current' ||
    validDestination.searchParams.get('creative') !== 'ig-feed' ||
    validCtaEvent?.payload?.data?.campaign !== 'presentation-proof-current') {
  console.error('Valid campaign path did not reach the CTA and anonymous event.');
  process.exit(1);
}

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
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link&campaign=presentation-proof-current&creative=ig-story',
  oncePerTabStore,
  '/app?signup=1&intent=presentation',
  '',
  {click: false},
);
assertMarketingLanding(firstLanding, {
  touchpoint: 'instagram.profile-link.presentation-proof-current.ig-story',
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
if (failedAnalyticsStore.get('askcrump.marketing-landing-emitted') !== '1') {
  console.error('Analytics failure did not preserve the once-per-tab marker.');
  process.exit(1);
}

const profileChainStore = new Map();
runLandingAttribution(
  'https://askcrump.com/?acquisition=facebook&source=profile-link&campaign=presentation-proof-current&creative=fb-static&intent=presentation',
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
  creative: 'fb-static',
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

const immutableStore = new Map();
runLandingAttribution(
  'https://askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link&campaign=presentation-proof-current&creative=ig-story',
  immutableStore,
  '/app?signup=1&intent=presentation',
);
runLandingAttribution(
  'https://askcrump.com/ai-project-workspace?acquisition=instagram&source=organic-social&campaign=real-product-continuity&creative=continuity-story',
  immutableStore,
);
assertAttribution(storedAttribution(immutableStore), {
  ...presentationTouch,
  creative: 'ig-story',
}, 'Second campaign in the same tab');

runLandingAttribution('https://askcrump.com/app?verified=1', immutableStore);
assertAttribution(storedAttribution(immutableStore), {
  ...presentationTouch,
  creative: 'ig-story',
}, 'Verification return');

runLandingAttribution(
  'https://askcrump.com/app?signin=1&acquisition=facebook&source=organic-social&campaign=real-product-continuity&creative=continuity-feed&intent=projects',
  immutableStore,
);
assertAttribution(storedAttribution(immutableStore), {
  ...presentationTouch,
  creative: 'ig-story',
}, 'Existing-account sign-in');

const repoRoot = new URL('../', import.meta.url);
const packageJson = JSON.parse(await readFile(new URL('package.json', repoRoot), 'utf8'));
const releaseVersion = String(packageJson.version || '');
const landingVersion = `${releaseVersion}-marketing-landing-1`;
const authControllerVersion = `${releaseVersion}-plan-intent-delivery-1`;
const planIntentDeliveryVersion = `${releaseVersion}-plan-intent-delivery-1`;
const intelligenceReceiptVersion = `${releaseVersion}-intelligence-receipt-1`;
const intelligenceArchitectureVersion = `${releaseVersion}-intelligence-architecture-1`;
const coreReliabilityVersion = `${releaseVersion}-core-reliability-1`;
const visualMediaReliabilityVersion = `${releaseVersion}-visual-media-reliability-2`;
const imageSafetyRecoveryVersion = `${releaseVersion}-image-safety-recovery-1`;
const imageScrollStabilityVersion = `${releaseVersion}-image-scroll-stability-1`;
const videoDestinationVersion = `${releaseVersion}-video-destination-1`;
const continuityActionVersion = `${releaseVersion}-continuity-action-1`;
const fileDeliveryVersion = `${releaseVersion}-file-delivery-2`;
const desktopChatsVersion = `${releaseVersion}-desktop-chats-default-1`;
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
  `/runtime-body-v1.js?v=${continuityActionVersion}`,
  `/telemetry-config.js?v=${releaseVersion}`,
  '/_vercel/speed-insights/script.js',
  `/auth-resilience.js?v=${releaseVersion}`,
  `/install-prompt.js?v=${releaseVersion}`,
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
    !runtime.includes(`/onboarding.css?v=${videoDestinationVersion}`) ||
    !runtime.includes(`/onboarding.js?v=${videoDestinationVersion}`) ||
    !runtime.includes(`/conversation.css?v=${intelligenceReceiptVersion}`) ||
    !runtime.includes(`/chat-resilience.js?v=${imageSafetyRecoveryVersion}`) ||
    !runtime.includes(`/ui-functions.js?v=${continuityActionVersion}`) ||
    !runtime.includes(`/lifecycle.css?v=${releaseVersion}-lifecycle-activation-1`) ||
    !runtime.includes(`/lifecycle-share.js?v=${releaseVersion}-lifecycle-activation-1`) ||
    !runtime.includes(`/lifecycle-manager.js?v=${continuityActionVersion}`) ||
    !runtime.includes(`/product-analytics.js?v=${releaseVersion}`) ||
    !runtime.includes(`/app.js?v=${coreReliabilityVersion}`) ||
    !runtime.includes(`/crump-v1-body.js?v=${desktopChatsVersion}`) ||
    !runtime.includes(`/crump-v1-body.css?v=${intelligenceArchitectureVersion}`) ||
    !runtime.includes(`/crump-5.0.css?v=${fileDeliveryVersion}`) ||
    !runtime.includes(`/crump-5.0.js?v=${fileDeliveryVersion}`) ||
    !runtime.includes(`/crump-5.2.2.js?v=${imageScrollStabilityVersion}`) ||
    !runtime.includes(`/crump-4.3.js?v=${intelligenceArchitectureVersion}`) ||
    !runtime.includes(`/crump-4.4.js?v=${coreReliabilityVersion}`) ||
    !runtime.includes(`/crump-v1-stability.js?v=${intelligenceArchitectureVersion}`) ||
    !runtime.includes(`/crump-product-5.3.js?v=${visualMediaReliabilityVersion}`) ||
    !runtime.includes(`/crump-product-5.3.css?v=${visualMediaReliabilityVersion}`) ||
    !runtime.includes(`/crump-product-5.3.1.js?v=${coreReliabilityVersion}`) || !runtime.includes('/crump-product-5.3.1.css') ||
    !runtime.includes('/crump-subscriptions-5.3.2.js') ||
    !runtime.includes(`/crump-polish-5.6.js?v=${videoDestinationVersion}`) || !runtime.includes('/crump-polish-5.6.css') ||
    !runtime.includes('/crump-library-5.7.js') || !runtime.includes('/crump-library-5.7.css') ||
    !runtime.includes(`/crump-navigation-5.9.30.js?v=${videoDestinationVersion}`) ||
    !runtime.includes(`/crump-navigation-5.9.30.css?v=${videoDestinationVersion}`) ||
    !runtime.includes(`/crump-code-5.9.35.js?v=${intelligenceArchitectureVersion}`) ||
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
    loadedRuntimeStyles.length !== 19 ||
    preloadedRuntimeScripts.length !== 31 ||
    loadedRuntimeScripts.length !== 31 ||
    !loadedRuntimeScripts.every(asset => preloadedRuntimeScripts.includes(asset)) ||
    loadedRuntimeScripts.indexOf(`/app.js?v=${coreReliabilityVersion}`) > loadedRuntimeScripts.indexOf(`/crump-4.3.js?v=${intelligenceArchitectureVersion}`) ||
    loadedRuntimeScripts.at(-1) !== `/lifecycle-manager.js?v=${continuityActionVersion}`) {
  console.error('Authenticated workspace runtime load order or completion contract failed.');
  process.exit(1);
}

const crump43 = await readFile(new URL('public/crump-4.3.js', repoRoot), 'utf8');
const v1Body = await readFile(new URL('public/crump-v1-body.js', repoRoot), 'utf8');
const product53 = await readFile(new URL('public/crump-product-5.3.js', repoRoot), 'utf8');
if (!crump43.includes('v1OwnsEmptyState') || !crump43.includes("classList.contains('crump-v1-body')")) {
  console.error('Legacy 4.3 empty-state guard for the V1 body is missing.');
  process.exit(1);
}
if (!v1Body.includes('removeLegacyEmptyState(container)')) {
  console.error('V1 must remove stale legacy empty-state nodes.');
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
if (!serviceWorker.includes('ask-crump-new-body-v1-r174') ||
    !serviceWorker.includes(`/landing.js?v=${landingVersion}`) ||
    !serviceWorker.includes(`/runtime-body-v1.js?v=${continuityActionVersion}`) ||
    !serviceWorker.includes(`/conversation.css?v=${intelligenceReceiptVersion}`) ||
    !serviceWorker.includes(`/chat-resilience.js?v=${imageSafetyRecoveryVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.css?v=${fileDeliveryVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.js?v=${fileDeliveryVersion}`) ||
    !serviceWorker.includes(`/ui-functions.js?v=${continuityActionVersion}`) ||
    !serviceWorker.includes(`/crump-5.2.2.js?v=${imageScrollStabilityVersion}`) ||
    !serviceWorker.includes(`/onboarding.css?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/onboarding.js?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/crump-polish-5.6.js?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.css?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.js?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/lifecycle.css?v=${releaseVersion}-lifecycle-activation-1`) ||
    !serviceWorker.includes(`/lifecycle-share.js?v=${releaseVersion}-lifecycle-activation-1`) ||
    !serviceWorker.includes(`/lifecycle-manager.js?v=${continuityActionVersion}`) ||
    !serviceWorker.includes(`/auth-resilience.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/install-prompt.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/install-prompt.css?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/device-auth.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/sync-manager.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/chat-sync.js?v=${releaseVersion}-sync-cadence-1`) ||
    !serviceWorker.includes(`/product-analytics.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/app.js?v=${coreReliabilityVersion}`) ||
    !serviceWorker.includes(`/auth-controller.js?v=${authControllerVersion}`) ||
    !serviceWorker.includes(`/crump-v1-body.css?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-4.3.js?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-4.4.js?v=${coreReliabilityVersion}`) ||
    !serviceWorker.includes(`/crump-v1-stability.js?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.js?v=${visualMediaReliabilityVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.1.js?v=${coreReliabilityVersion}`) ||
    !serviceWorker.includes(`/crump-product-5.3.css?v=${visualMediaReliabilityVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.js?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/crump-navigation-5.9.30.css?v=${videoDestinationVersion}`) ||
    !serviceWorker.includes(`/crump-code-5.9.35.js?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes(`/crump-code-5.9.35.css?v=${intelligenceArchitectureVersion}`) ||
    !serviceWorker.includes("url.pathname === '/conversation.css'") ||
    !serviceWorker.includes("url.pathname === '/chat-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.css'") ||
    !serviceWorker.includes("url.pathname === '/ui-functions.js'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle.css'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle-share.js'") ||
    !serviceWorker.includes("url.pathname === '/lifecycle-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.css'") ||
    !serviceWorker.includes("url.pathname === '/sync-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-controller.js'") ||
    !serviceWorker.includes(`/crump-v1-body.js?v=${desktopChatsVersion}`) ||
    !serviceWorker.includes('/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1') ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-5.9.35.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-5.9.35.css'") ||
    !serviceWorker.includes(`/crump-subscriptions-5.3.2.js?v=${planIntentDeliveryVersion}`) ||
    !serviceWorker.includes('/crump-library-5.7.js') ||
    !serviceWorker.includes('/crump-library-5.7.css')) {
  console.error('New-body service-worker contract is incomplete.');
  process.exit(1);
}

const installPromptSource = await readFile(new URL('public/install-prompt.js', repoRoot), 'utf8');
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
const scroll522Css = await readFile(new URL('public/crump-5.2.2.css', repoRoot), 'utf8');
if (!uiFunctions.includes("typeof window.crumpScrollManager?.scrollToBottom === 'function'") ||
    !uiFunctions.includes("window.crumpScrollManager.scrollToBottom('auto')")) {
  console.error('Conversation renderer must delegate automatic bottom movement to the scroll manager.');
  process.exit(1);
}
if (uiFunctions.includes("if (shouldStick || presence) requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });")) {
  console.error('Legacy direct bottom-scroll bypass must not return.');
  process.exit(1);
}
if (!scroll522.includes('state.scroll.suppressLegacyBottomUntil = Date.now() + 3200') ||
    !scroll522.includes('if (!force && Date.now() < state.scroll.suppressLegacyBottomUntil) return;')) {
  console.error('5.2.2 new-reply reading lock is missing.');
  process.exit(1);
}
if (!scroll522.includes('if (!force && state.scroll.userReviewingHistory) return;') ||
    !scroll522.includes('state.scroll.userReviewingHistory = distanceFromBottom() > 100;') ||
    !uiFunctions.includes('function imageAspectForMessage(message, messages)') ||
    !uiFunctions.includes('image.width = aspect.width;') ||
    !uiFunctions.includes('image.height = aspect.height;')) {
  console.error('Generated-image scroll and layout stability contract is missing.');
  process.exit(1);
}
if (!scroll522.includes('activeReplyShouldHold') ||
    !scroll522.includes('cancelActiveReplyAnchor') ||
    !scroll522.includes('shouldPreserveAnchor') ||
    !scroll522.includes('if (row) anchorElementTop(row);')) {
  console.error('5.2.2 must preserve the anchored new reply across same-message rerenders.');
  process.exit(1);
}
if (scroll522.includes('requestAnimationFrame(() => {\n      requestAnimationFrame(() => {')) {
  console.error('New assistant replies must anchor synchronously before paint, not after two animation frames.');
  process.exit(1);
}
if (!scroll522Css.includes('overflow-anchor: none !important;')) {
  console.error('Conversation viewport must disable browser-native scroll anchoring.');
  process.exit(1);
}

console.log('Ask Crump V1 new-body integration contract validated.');
console.log(`Validated ${files.length} JavaScript files.`);
