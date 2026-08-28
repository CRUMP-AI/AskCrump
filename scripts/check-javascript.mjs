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
  'scroll-manager.js', 'subscription-ui.js', 'sw.js', 'sync-manager.js', 'ui-functions.js',
  'product-analytics.js',
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

const repoRoot = new URL('../', import.meta.url);
const packageJson = JSON.parse(await readFile(new URL('package.json', repoRoot), 'utf8'));
const releaseVersion = String(packageJson.version || '');
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
  'public/auth-resilience.js',
  'public/chat-resilience.js',
  'public/assets/brand/crump-mark.png',
  'public/assets/brand/crump-horizontal-light.png',
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
const landingHtml = await readFile(new URL('public/index.html', repoRoot), 'utf8');
if (!releaseVersion || !landingHtml.includes(`/landing.js?v=${releaseVersion}`)) {
  console.error('Ask Crump marketing page is missing its release-versioned script.');
  process.exit(1);
}
const requiredHtmlSignals = [
  '/runtime-body-v1.js',
  `/auth-resilience.js?v=${releaseVersion}`,
  `/install-prompt.js?v=${releaseVersion}`,
  `/chat-resilience.js?v=${releaseVersion}`,
  `/product-analytics.js?v=${releaseVersion}`,
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

const runtime = await readFile(new URL('public/runtime-body-v1.js', repoRoot), 'utf8');
if (!runtime.includes('/crump-v1-body.js') || !runtime.includes('/crump-v1-body.css') ||
    !runtime.includes(`/crump-5.0.js?v=${releaseVersion}`) ||
    !runtime.includes('/crump-product-5.3.js') || !runtime.includes('/crump-product-5.3.css') ||
    !runtime.includes('/crump-product-5.3.1.js') || !runtime.includes('/crump-product-5.3.1.css') ||
    !runtime.includes('/crump-subscriptions-5.3.2.js') ||
    !runtime.includes('/crump-polish-5.6.js') || !runtime.includes('/crump-polish-5.6.css') ||
    !runtime.includes('/crump-library-5.7.js') || !runtime.includes('/crump-library-5.7.css') ||
    !runtime.includes('/crump-navigation-5.9.30.js') || !runtime.includes('/crump-navigation-5.9.30.css') ||
    !runtime.includes('/crump-code-5.9.35.js') || !runtime.includes('/crump-code-5.9.35.css')) {
  console.error('New-body runtime is missing the canonical shell.');
  process.exit(1);
}
if (runtime.includes('/crump-5.2.4.js') || runtime.includes('/crump-5.2.4.css')) {
  console.error('Retired 5.2.4 branding must not load inside the new-body runtime.');
  process.exit(1);
}

const crump43 = await readFile(new URL('public/crump-4.3.js', repoRoot), 'utf8');
const v1Body = await readFile(new URL('public/crump-v1-body.js', repoRoot), 'utf8');
if (!crump43.includes('v1OwnsEmptyState') || !crump43.includes("classList.contains('crump-v1-body')")) {
  console.error('Legacy 4.3 empty-state guard for the V1 body is missing.');
  process.exit(1);
}
if (!v1Body.includes('removeLegacyEmptyState(container)')) {
  console.error('V1 must remove stale legacy empty-state nodes.');
  process.exit(1);
}

const serviceWorker = await readFile(new URL('public/sw.js', repoRoot), 'utf8');
if (!serviceWorker.includes('ask-crump-new-body-v1-r90') ||
    !serviceWorker.includes(`/landing.js?v=${releaseVersion}`) ||
    !serviceWorker.includes('/runtime-body-v1.js') ||
    !serviceWorker.includes(`/conversation.css?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/chat-resilience.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/crump-5.0.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/ui-functions.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/auth-resilience.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/install-prompt.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/install-prompt.css?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/device-auth.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/sync-manager.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/product-analytics.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/auth-controller.js?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/crump-v1-body.css?v=${releaseVersion}`) ||
    !serviceWorker.includes(`/crump-4.3.js?v=${releaseVersion}`) ||
    !serviceWorker.includes("url.pathname === '/conversation.css'") ||
    !serviceWorker.includes("url.pathname === '/chat-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-5.0.js'") ||
    !serviceWorker.includes("url.pathname === '/ui-functions.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-resilience.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.js'") ||
    !serviceWorker.includes("url.pathname === '/install-prompt.css'") ||
    !serviceWorker.includes("url.pathname === '/sync-manager.js'") ||
    !serviceWorker.includes("url.pathname === '/auth-controller.js'") ||
    !serviceWorker.includes('/crump-v1-body.js') ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.2.5.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-navigation-5.9.30.css'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-5.9.35.js'") ||
    !serviceWorker.includes("url.pathname === '/crump-code-5.9.35.css'") ||
    !serviceWorker.includes('/crump-subscriptions-5.3.2.js') ||
    !serviceWorker.includes('/crump-library-5.7.js') ||
    !serviceWorker.includes('/crump-library-5.7.css')) {
  console.error('New-body service-worker contract is incomplete.');
  process.exit(1);
}

const uiFunctions = await readFile(new URL('public/ui-functions.js', repoRoot), 'utf8');
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
