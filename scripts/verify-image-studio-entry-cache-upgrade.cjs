const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const root = path.resolve(__dirname, '..');
const publicDirectory = path.join(root, 'public');
const frozenWorkerFile = path.join(root, 'tests', 'fixtures', 'sw-r272-project-resume.js');
const oldWorkerPath = '/__frozen-r272-project-resume-sw.js';
const controlPath = '/__project-resume-cache-upgrade-control.html';
const installGatePath = '/delete-account.html';
const immediatePredecessor = Object.freeze({
  cache: 'ask-crump-new-body-v1-r273-account-owner-boundary-1',
  runtime: '/runtime-body-v1.js?v=5.9.76-account-owner-boundary-1',
  billing52: '/crump-5.2.js?v=5.9.76-private-owner-boundary-1&workspaceRelease=guest-free-contract-2',
});
const contentTypes = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
});

function matchOne(source, pattern, label) {
  const match = source.match(pattern);
  assert.ok(match?.[1], `Could not resolve ${label}.`);
  return match[1];
}

function resolveRelease(swSource, shellSource, runtimeSource, frozenSource) {
  const current = Object.freeze({
    cache: matchOne(swSource, /const CACHE_NAME = '([^']+)'/, 'current cache name'),
    runtime: matchOne(shellSource, /src="([^"]*\/runtime-body-v1\.js\?[^"]+)"/, 'runtime URL'),
    mobileBridge: matchOne(shellSource, /src="([^"]*\/mobile-bridge\.js\?[^"]+)"/, 'mobile bridge URL'),
    projectsCss: matchOne(shellSource, /href="([^"]*\/crump-vision-projects-1\.0\.css\?[^"]+)"/, 'Projects CSS URL'),
    projectsJs: matchOne(shellSource, /src="([^"]*\/crump-vision-projects-1\.0\.js\?[^"]+)"/, 'Projects JS URL'),
    libraryCss: matchOne(shellSource, /href="([^"]*\/crump-vision-library-1\.0\.css\?[^"]+)"/, 'Library CSS URL'),
    libraryJs: matchOne(shellSource, /src="([^"]*\/crump-vision-library-1\.0\.js\?[^"]+)"/, 'Library JS URL'),
    authController: matchOne(shellSource, /src="([^"]*\/auth-controller\.js\?[^"]+)"/, 'auth controller URL'),
    deviceAuth: matchOne(shellSource, /src="([^"]*\/device-auth\.js\?[^"]+)"/, 'device auth URL'),
    chatTransport: matchOne(runtimeSource, /\['([^']*\/chat-resilience\.js\?[^']+)'\s*,\s*'workspacechatresilience'\]/, 'chat transport URL'),
    billingManager: matchOne(runtimeSource, /\['([^']*\/billing-manager\.js\?[^']+)'\s*,\s*'workspacebilling'\]/, 'billing manager URL'),
    subscriptionUi: matchOne(runtimeSource, /\['([^']*\/subscription-ui\.js\?[^']+)'\s*,\s*'workspacesubscription'\]/, 'subscription UI URL'),
    creditConfirmation: matchOne(runtimeSource, /\['([^']*\/credit-confirmation\.js\?[^']+)'\s*,\s*'workspacecreditconfirmation'\]/, 'credit confirmation URL'),
    uiFunctions: matchOne(runtimeSource, /\['([^']*\/ui-functions\.js\?[^']+)'\s*,\s*'workspaceui'\]/, 'UI functions URL'),
    composer: matchOne(runtimeSource, /\['([^']*\/crump-5\.0\.js\?[^']+)'\s*,\s*'crump50'\]/, 'composer URL'),
    sync: matchOne(runtimeSource, /\['([^']*\/sync-manager\.js\?[^']+)'\s*,\s*'workspacesync'\]/, 'sync manager URL'),
    chat: matchOne(runtimeSource, /\['([^']*\/chat-sync\.js\?[^']+)'\s*,\s*'workspacechatsync'\]/, 'chat sync URL'),
    profile: matchOne(runtimeSource, /\['([^']*\/profile-manager\.js\?[^']+)'\s*,\s*'workspaceprofile'\]/, 'profile manager URL'),
    presence: matchOne(runtimeSource, /\['([^']*\/presence-manager\.js\?[^']+)'\s*,\s*'workspacepresence'\]/, 'presence manager URL'),
    account: matchOne(runtimeSource, /\['([^']*\/account-manager\.js\?[^']+)'\s*,\s*'workspaceaccount'\]/, 'account manager URL'),
    app: matchOne(runtimeSource, /\['([^']*\/app\.js\?[^']+)'\s*,\s*'workspaceapp'\]/, 'app URL'),
    productAnalytics: matchOne(runtimeSource, /\['([^']*\/product-analytics\.js\?[^']+)'\s*,\s*'workspaceanalytics'\]/, 'product analytics URL'),
    intelligence: matchOne(runtimeSource, /\['([^']*\/crump-4\.4\.js\?[^']+)'\s*,\s*'crump44'\]/, 'intelligence URL'),
    billing51: matchOne(runtimeSource, /\['([^']*\/crump-billing-5\.1\.js\?[^']+)'\s*,\s*'billing51'\]/, 'billing 5.1 URL'),
    billing52: matchOne(runtimeSource, /\['([^']*\/crump-5\.2\.js\?[^']+)'\s*,\s*'crump52'\]/, 'billing 5.2 URL'),
    billing522: matchOne(runtimeSource, /\['([^']*\/crump-5\.2\.2\.js\?[^']+)'\s*,\s*'crump522'\]/, 'billing 5.2.2 URL'),
    subscriptions: matchOne(runtimeSource, /\['([^']*\/crump-subscriptions-5\.3\.2\.js\?[^']+)'\s*,\s*'crumpsubscriptions532'\]/, 'subscriptions URL'),
    activity: matchOne(runtimeSource, /\['([^']*\/crump-activity-center-1\.0\.js\?[^']+)'\s*,\s*'crumpactivitycenter10'\]/, 'activity center URL'),
    codeLoader: matchOne(runtimeSource, /\['([^']*\/crump-code-loader\.js\?[^']+)'\s*,\s*'crumpcodeloader'\]/, 'Code loader URL'),
    productLoader: matchOne(runtimeSource, /\['([^']*\/crump-product-loader\.js\?[^']+)'\s*,\s*'crumpproductloader'\]/, 'Product loader URL'),
    libraryLoader: matchOne(runtimeSource, /\['([^']*\/crump-library-loader\.js\?[^']+)'\s*,\s*'crumplibraryloader'\]/, 'Library loader URL'),
  });
  const previous = Object.freeze({
    cache: matchOne(frozenSource, /const CACHE_NAME = '([^']+)'/, 'frozen cache name'),
    runtime: matchOne(frozenSource, /'([^']*\/runtime-body-v1\.js\?[^']+)'/, 'frozen runtime URL'),
    mobileBridge: matchOne(frozenSource, /'([^']*\/mobile-bridge\.js(?:\?[^']+)?)'/, 'frozen mobile bridge URL'),
    projectsCss: matchOne(frozenSource, /'([^']*\/crump-vision-projects-1\.0\.css\?[^']+)'/, 'frozen Projects CSS URL'),
    projectsJs: matchOne(frozenSource, /'([^']*\/crump-vision-projects-1\.0\.js\?[^']+)'/, 'frozen Projects JS URL'),
    libraryCss: matchOne(frozenSource, /'([^']*\/crump-vision-library-1\.0\.css\?[^']+)'/, 'frozen Library CSS URL'),
    libraryJs: matchOne(frozenSource, /'([^']*\/crump-vision-library-1\.0\.js\?[^']+)'/, 'frozen Library JS URL'),
    authController: matchOne(frozenSource, /'([^']*\/auth-controller\.js\?[^']+)'/, 'frozen auth controller URL'),
    deviceAuth: matchOne(frozenSource, /'([^']*\/device-auth\.js\?[^']+)'/, 'frozen device auth URL'),
    chatTransport: matchOne(frozenSource, /'([^']*\/chat-resilience\.js\?[^']+)'/, 'frozen chat transport URL'),
    billingManager: matchOne(frozenSource, /'([^']*\/billing-manager\.js\?[^']+)'/, 'frozen billing manager URL'),
    subscriptionUi: matchOne(frozenSource, /'([^']*\/subscription-ui\.js\?[^']+)'/, 'frozen subscription UI URL'),
    creditConfirmation: matchOne(frozenSource, /'([^']*\/credit-confirmation\.js\?[^']+)'/, 'frozen credit confirmation URL'),
    uiFunctions: matchOne(frozenSource, /'([^']*\/ui-functions\.js\?[^']+)'/, 'frozen UI functions URL'),
    composer: matchOne(frozenSource, /'([^']*\/crump-5\.0\.js\?[^']+)'/, 'frozen composer URL'),
    sync: matchOne(frozenSource, /'([^']*\/sync-manager\.js\?[^']+)'/, 'frozen sync manager URL'),
    chat: matchOne(frozenSource, /'([^']*\/chat-sync\.js\?[^']+)'/, 'frozen chat sync URL'),
    profile: matchOne(frozenSource, /'([^']*\/profile-manager\.js(?:\?[^']+)?)'/, 'frozen profile manager URL'),
    presence: matchOne(frozenSource, /'([^']*\/presence-manager\.js\?[^']+)'/, 'frozen presence manager URL'),
    account: matchOne(frozenSource, /'([^']*\/account-manager\.js\?[^']+)'/, 'frozen account manager URL'),
    app: matchOne(frozenSource, /'([^']*\/app\.js\?[^']+)'/, 'frozen app URL'),
    productAnalytics: matchOne(frozenSource, /'([^']*\/product-analytics\.js\?[^']+)'/, 'frozen product analytics URL'),
    intelligence: matchOne(frozenSource, /'([^']*\/crump-4\.4\.js\?[^']+)'/, 'frozen intelligence URL'),
    billing51: matchOne(frozenSource, /'([^']*\/crump-billing-5\.1\.js\?[^']+)'/, 'frozen billing 5.1 URL'),
    billing52: matchOne(frozenSource, /'([^']*\/crump-5\.2\.js\?[^']+)'/, 'frozen billing 5.2 URL'),
    billing522: matchOne(frozenSource, /'([^']*\/crump-5\.2\.2\.js\?[^']+)'/, 'frozen billing 5.2.2 URL'),
    subscriptions: matchOne(frozenSource, /'([^']*\/crump-subscriptions-5\.3\.2\.js\?[^']+)'/, 'frozen subscriptions URL'),
    activity: matchOne(frozenSource, /'([^']*\/crump-activity-center-1\.0\.js\?[^']+)'/, 'frozen activity center URL'),
    codeLoader: matchOne(frozenSource, /'([^']*\/crump-code-loader\.js\?[^']+)'/, 'frozen Code loader URL'),
    productLoader: matchOne(frozenSource, /'([^']*\/crump-product-loader\.js\?[^']+)'/, 'frozen Product loader URL'),
    libraryLoader: matchOne(frozenSource, /'([^']*\/crump-library-loader\.js\?[^']+)'/, 'frozen Library loader URL'),
  });
  assert.equal(previous.cache, 'ask-crump-new-body-v1-r272-project-resume-auth-boundary-1');
  assert.equal(current.cache, 'ask-crump-new-body-v1-r277-guest-network-budget-1');
  assert.notEqual(current.cache, immediatePredecessor.cache);
  assert.notEqual(current.runtime, immediatePredecessor.runtime);
  assert.notEqual(current.billing52, immediatePredecessor.billing52);
  assert.ok(current.profile.includes('/profile-manager.js?v='));
  assert.ok(current.presence.includes('/presence-manager.js?v='));
  assert.ok(current.account.includes('/account-manager.js?v='));
  for (const url of Object.values(current).filter(value => value.startsWith('/'))) {
    assert.ok(swSource.includes(`'${url}'`), `Current precache omitted ${url}.`);
  }
  return {current, previous};
}

function focusedShell(urls) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Projects returning-client cache proof</title>
  <link id="projectsStyles" rel="stylesheet" href="${urls.projectsCss}">
  <link id="libraryStyles" rel="stylesheet" href="${urls.libraryCss}">
  <link id="authControllerPreload" rel="preload" as="script" href="${urls.authController}">
  <script>
    window.currentUser = {id: '11111111-1111-4111-8111-111111111111'};
    window.SafeStorage = {
      getItem: key => localStorage.getItem(key),
      setItem: (key, value) => localStorage.setItem(key, value),
      removeItem: key => localStorage.removeItem(key),
    };
    window.renderMessages = messages => {
      document.getElementById('chatContainer')?.replaceChildren();
      window.__renderedMessages = Array.isArray(messages) ? messages.length : -1;
    };
    window.showToast = () => {};
    window.CrumpAuthBoundary = Object.freeze({
      authenticatedUserId: () => window.currentUser.id,
      revision: () => 0,
      register: () => () => {},
    });
    window.CrumpVision = {
      current: () => 'projects',
      navigate: () => {},
      registerView(id, view) {
        if (id === 'projects') {
          window.__cvProjectsRegistered = true;
          window.__cvProjectsView = view;
        }
        if (id === 'library') {
          window.__cvLibraryRegistered = true;
          window.__cvLibraryView = view;
        }
      },
    };
    window.CrumpAPI = {ready: Promise.resolve(), isNative: false};
    window.CrumpAuthTransport = {
      SESSION_TIMEOUT_MS: 1000,
      request: async () => ({
        response: new Response(JSON.stringify({authenticated: true}), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }),
        data: {
          authenticated: true,
          data: {user: {id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'}},
        },
      }),
    };
    localStorage.setItem('crump_user_cache_v4', JSON.stringify({
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    }));
  </script>
  <script defer src="${urls.mobileBridge}"></script>
  <script defer src="${urls.deviceAuth}"></script>
  <script defer src="${urls.runtime}"></script>
  <script defer src="${urls.projectsJs}"></script>
  <script defer src="${urls.libraryJs}"></script>
</head>
<body>
  <main id="projectsRoot"></main>
  <aside id="chatsList"></aside>
  <section id="chatContainer"></section>
  <textarea id="userInput"></textarea>
  <button id="sendButton" type="button">Send</button>
  <button id="newChatBtn" type="button">New</button>
  <input id="fileInput" type="file">
</body>
</html>`;
}

function oldShell(urls) {
  return `<!doctype html><meta charset="utf-8"><title>Frozen r272 shell</title>
<link rel="stylesheet" href="${urls.projectsCss}">
<link rel="stylesheet" href="${urls.libraryCss}">
<script defer src="${urls.mobileBridge}"></script>
<script defer src="${urls.runtime}"></script>
<script defer src="${urls.projectsJs}"></script>
<script defer src="${urls.libraryJs}"></script>`;
}

function safePublicPath(pathname) {
  const relative = pathname.replace(/^\/+/, '');
  const resolved = path.resolve(publicDirectory, relative);
  return resolved.startsWith(publicDirectory + path.sep) ? resolved : null;
}

async function startServer({current, previous, frozenSource}) {
  let phase = 'old';
  let gateEnabled = false;
  let heldResponses = [];
  let gateObservedResolve = null;
  let gateObserved = Promise.resolve();
  const requests = [];
  const currentTargets = new Set(Object.values(current).filter(value => value.startsWith('/')));
  const previousTargets = new Set(Object.values(previous).filter(value => value.startsWith('/')));
  const sharedTargets = new Set(
    Object.keys(current)
      .filter(name => name !== 'cache' && current[name] === previous[name])
      .map(name => current[name]),
  );

  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const target = `${url.pathname}${url.search}`;
    requests.push({phase, target, destination: String(request.headers['sec-fetch-dest'] || '')});
    response.setHeader('Cache-Control', 'no-store');

    if (gateEnabled && url.pathname === installGatePath) {
      heldResponses.push(response);
      gateObservedResolve?.();
      gateObservedResolve = null;
      return;
    }
    if (url.pathname === controlPath) {
      response.writeHead(200, {'Content-Type': contentTypes['.html']});
      response.end('<!doctype html><meta charset="utf-8"><title>Cache upgrade control</title>');
      return;
    }
    if (url.pathname === '/favicon.ico') {
      response.writeHead(204);
      response.end();
      return;
    }
    if (url.pathname === oldWorkerPath) {
      response.writeHead(200, {
        'Content-Type': contentTypes['.js'],
        'Service-Worker-Allowed': '/',
      });
      response.end(frozenSource);
      return;
    }
    if (url.pathname === '/sw.js') {
      const body = await readFile(path.join(publicDirectory, 'sw.js'));
      response.writeHead(200, {
        'Content-Type': contentTypes['.js'],
        'Service-Worker-Allowed': '/',
      });
      response.end(body);
      return;
    }
    if (url.pathname === '/app' || url.pathname === '/app.html') {
      response.writeHead(200, {'Content-Type': contentTypes['.html']});
      response.end(phase === 'old' ? oldShell(previous) : focusedShell(current));
      return;
    }
    if (url.pathname === '/api/projects') {
      response.writeHead(200, {'Content-Type': contentTypes['.json']});
      response.end(JSON.stringify({success: true, projects: []}));
      return;
    }
    if (url.pathname === '/api/library/books') {
      response.writeHead(200, {'Content-Type': contentTypes['.json']});
      response.end(JSON.stringify({success: true, books: []}));
      return;
    }
    if (phase === 'old' && previousTargets.has(target)) {
      const type = url.pathname.endsWith('.css') ? contentTypes['.css'] : contentTypes['.js'];
      if (sharedTargets.has(target)) {
        const filePath = safePublicPath(url.pathname);
        const body = filePath ? await readFile(filePath) : null;
        if (body) {
          response.writeHead(200, {'Content-Type': type});
          response.end(body);
          return;
        }
      }
      response.writeHead(200, {'Content-Type': type});
      response.end(`${url.pathname.endsWith('.css') ? '/*' : '//'} stale-r272:${target}`);
      return;
    }
    if (currentTargets.has(target)) {
      const filePath = safePublicPath(url.pathname);
      const body = filePath ? await readFile(filePath) : null;
      if (body) {
        response.writeHead(200, {
          'Content-Type': contentTypes[path.extname(filePath)] || 'application/octet-stream',
        });
        response.end(body);
        return;
      }
    }

    const filePath = safePublicPath(url.pathname);
    const extension = filePath ? path.extname(filePath).toLowerCase() : '';
    if (extension === '.js') {
      response.writeHead(200, {'Content-Type': contentTypes['.js']});
      response.end('/* intentionally neutralized by the focused cache verifier */');
      return;
    }
    if (extension === '.css') {
      response.writeHead(200, {'Content-Type': contentTypes['.css']});
      response.end('/* intentionally neutralized by the focused cache verifier */');
      return;
    }
    if (extension === '.json') {
      response.writeHead(200, {'Content-Type': contentTypes['.json']});
      response.end('{}');
      return;
    }
    response.writeHead(200, {
      'Content-Type': contentTypes[extension] || 'application/octet-stream',
    });
    response.end('fixture');
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return {
    server,
    port: server.address().port,
    requests,
    useCurrentRelease() { phase = 'current'; },
    holdInstall() {
      gateEnabled = true;
      gateObserved = new Promise(resolve => { gateObservedResolve = resolve; });
      return gateObserved;
    },
    releaseInstall() {
      gateEnabled = false;
      for (const response of heldResponses) {
        response.writeHead(200, {'Content-Type': contentTypes['.html']});
        response.end('<!doctype html><title>Delete account</title>');
      }
      heldResponses = [];
    },
  };
}

async function waitFor(page, predicate, message, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await page.waitForTimeout(50);
  }
  throw new Error(message);
}

async function assertRuntimeExecuted(page, expectedControllerSuffix) {
  const result = await page.evaluate(async expectedSuffix => {
    const identityCacheBefore = localStorage.getItem('crump_user_cache_v4');
    const sessionBefore = window.deviceAuth?.session || null;
    const nonCommittingSession = await window.deviceAuth.checkSession({commit: false});
    await window.CrumpWorkspaceRuntime.load();
    let chatOwnerClaim = '';
    const nativeFetch = window.fetch;
    window.fetch = async (input, options = {}) => {
      const url = new URL(String(input), window.location.href);
      if (url.pathname === '/api/usage/check') {
        chatOwnerClaim = new Headers(options.headers || {}).get('X-Ask-Crump-Expected-Owner') || '';
        return new Response(JSON.stringify({
          success: true,
          usage: {messages: 0},
          limits: {messages: 5},
          freeMessageAllowance: {limit: 5, used: 0, remaining: 5},
        }), {status: 200, headers: {'Content-Type': 'application/json'}});
      }
      return nativeFetch(input, options);
    };
    await window.CrumpChatTransport.ensureUsage({
      expectedOwnerId: window.CrumpAuthBoundary.authenticatedUserId(),
    });
    window.fetch = nativeFetch;
    const button = document.createElement('button');
    button.className = 'cvp-chat-continue';
    document.body.appendChild(button);
    const minHeight = getComputedStyle(button).minHeight;
    button.remove();
    return {
      controller: new URL(navigator.serviceWorker.controller.scriptURL).pathname,
      controllerChanges: window.__controllerChanges,
      projectsRegistered: window.__cvProjectsRegistered === true,
      libraryRegistered: window.__cvLibraryRegistered === true,
      projectsStyle: document.getElementById('projectsStyles')?.getAttribute('href') || '',
      libraryStyle: document.getElementById('libraryStyles')?.getAttribute('href') || '',
      authControllerPreload: document.getElementById('authControllerPreload')?.getAttribute('href') || '',
      minHeight,
      runtime: typeof window.CrumpWorkspaceRuntime?.load === 'function',
      sync: typeof window.SyncManager?.pull === 'function',
      chat: typeof window.syncChatsFromServer === 'function',
      profile: typeof window.ProfileManager === 'function',
      presence: typeof window.CrumpPresence?.scrubAuthBoundary === 'function',
      account: typeof window.CrumpAccountBoundary?.scrubAuthBoundary === 'function',
      appScrub: typeof window.CrumpConversationState?.scrubAuthBoundary === 'function',
      billingBoundary: typeof window.BillingManager?.purchase === 'function',
      creditBoundary: typeof window.CrumpCreditConfirmation?.scrubAuthBoundary === 'function',
      analyticsBoundary: window.CrumpAnalytics?.track?.toString().includes('suppliedBoundary'),
      deviceAuthSupportsNonCommit: window.deviceAuth.checkSession.toString().includes('{commit = true}'),
      deviceAuthProbeAuthenticated: nonCommittingSession?.authenticated === true,
      deviceAuthSessionUnchanged: window.deviceAuth.session === sessionBefore,
      deviceAuthCacheUnchanged: localStorage.getItem('crump_user_cache_v4') === identityCacheBefore,
      chatTransportOwnerClaim: chatOwnerClaim,
      chatTransportOwnerFence: window.CrumpChatTransport.ensureUsage.toString().includes('expectedOwnerId'),
      mobileBridgeCas: window.CrumpAPI.clearSessionToken.toString().includes('expectedToken'),
      expectedController: expectedSuffix,
    };
  }, expectedControllerSuffix);
  assert.equal(result.controller, expectedControllerSuffix);
  assert.equal(result.projectsRegistered, true);
  assert.equal(result.libraryRegistered, true);
  assert.equal(result.minHeight, '44px');
  assert.equal(result.runtime, true);
  assert.equal(result.sync, true);
  assert.equal(result.chat, true);
  assert.equal(result.profile, true);
  assert.equal(result.presence, true);
  assert.equal(result.account, true);
  assert.equal(result.appScrub, true);
  assert.equal(result.billingBoundary, true);
  assert.equal(result.creditBoundary, true);
  assert.equal(result.analyticsBoundary, true);
  assert.equal(result.deviceAuthSupportsNonCommit, true);
  assert.equal(result.deviceAuthProbeAuthenticated, true);
  assert.equal(result.deviceAuthSessionUnchanged, true);
  assert.equal(result.deviceAuthCacheUnchanged, true);
  assert.equal(result.chatTransportOwnerClaim, '11111111-1111-4111-8111-111111111111');
  assert.equal(result.chatTransportOwnerFence, true);
  assert.equal(result.mobileBridgeCas, true);
  return result;
}

(async () => {
  const [swSource, shellSource, runtimeSource, frozenSource] = await Promise.all([
    readFile(path.join(publicDirectory, 'sw.js'), 'utf8'),
    readFile(path.join(publicDirectory, 'app.html'), 'utf8'),
    readFile(path.join(publicDirectory, 'runtime-body-v1.js'), 'utf8'),
    readFile(frozenWorkerFile, 'utf8'),
  ]);
  const {current, previous} = resolveRelease(swSource, shellSource, runtimeSource, frozenSource);
  const fixture = await startServer({current, previous, frozenSource});
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  let context;
  try {
    context = await browser.newContext({serviceWorkers: 'allow'});
    const page = await context.newPage();
    const errors = [];
    const expectedOfflineNetworkFailures = [];
    let offlineExpected = false;
    page.on('console', message => {
      if (message.type() !== 'error') return;
      const messageText = message.text();
      if (offlineExpected && messageText.includes('net::ERR_FAILED')) {
        expectedOfflineNetworkFailures.push(messageText);
        return;
      }
      errors.push(messageText);
    });
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.__controllerChanges = 0;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        window.__controllerChanges += 1;
      });
    });
    const origin = `http://127.0.0.1:${fixture.port}`;
    await page.goto(`${origin}${controlPath}`, {waitUntil: 'load'});
    await page.evaluate(async workerPath => {
      await navigator.serviceWorker.register(workerPath, {scope: '/'});
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise(resolve => navigator.serviceWorker.addEventListener(
          'controllerchange', resolve, {once: true},
        ));
      }
      window.__controllerChanges = 0;
    }, oldWorkerPath);

    const seeded = await page.evaluate(async ({cacheName, urls}) => {
      const cache = await caches.open(cacheName);
      const values = {};
      for (const [name, url] of Object.entries(urls)) {
        if (name === 'cache') continue;
        values[name] = await cache.match(url).then(async response => response?.text() || '');
      }
      return {
        controller: new URL(navigator.serviceWorker.controller.scriptURL).pathname,
        cachePresent: (await caches.keys()).includes(cacheName),
        values,
      };
    }, {cacheName: previous.cache, urls: previous});
    assert.equal(seeded.controller, oldWorkerPath);
    assert.equal(seeded.cachePresent, true);
    for (const [name, value] of Object.entries(seeded.values)) {
      if (current[name] === previous[name]) {
        assert.equal(value.includes('stale-r272:'), false, `Shared ${name} asset was not seeded with its real body.`);
      } else {
        assert.ok(value.includes('stale-r272:'), `Frozen ${name} asset was not seeded.`);
      }
    }

    fixture.useCurrentRelease();
    const firstLoadRequestStart = fixture.requests.length;
    await page.goto(`${origin}/app`, {waitUntil: 'load'});
    const firstControlled = await assertRuntimeExecuted(page, oldWorkerPath);
    assert.equal(firstControlled.controllerChanges, 0);
    assert.equal(firstControlled.projectsStyle, current.projectsCss);
    assert.equal(firstControlled.libraryStyle, current.libraryCss);
    assert.equal(firstControlled.authControllerPreload, current.authController);
    const firstLoadRequests = fixture.requests.slice(firstLoadRequestStart);
    for (const [name, url] of Object.entries(current)) {
      if (!url.startsWith('/') || previous[name] === url) continue;
      assert.ok(
        firstLoadRequests.some(entry => entry.phase === 'current' && entry.target === url),
        `Frozen r272 did not fetch the changed current ${name} asset (${url}) on first load.`,
      );
    }

    // Only after the old r272 controller has delivered and executed the first
    // current shell do we allow r273 to install. This prevents install-time
    // precache requests from masquerading as first-load delivery proof.
    const gateObserved = fixture.holdInstall();
    await page.evaluate(() => { void navigator.serviceWorker.register('/sw.js', {scope: '/'}); });
    await Promise.race([
      gateObserved,
      new Promise((_, reject) => setTimeout(() => reject(new Error('Current worker install gate was not reached.')), 30_000)),
    ]);

    fixture.releaseInstall();
    await waitFor(
      page,
      async () => page.evaluate(async ({oldName, currentName}) => {
        const keys = await caches.keys();
        return navigator.serviceWorker.controller?.scriptURL.endsWith('/sw.js')
          && keys.includes(currentName)
          && !keys.includes(oldName);
      }, {oldName: previous.cache, currentName: current.cache}),
      'Current service worker did not take control and retire r272.',
    );

    const cached = await page.evaluate(async ({cacheName, urls}) => {
      const cache = await caches.open(cacheName);
      const values = {};
      for (const [name, url] of Object.entries(urls)) {
        if (name === 'cache') continue;
        values[name] = await cache.match(url).then(async response => response?.text() || '');
      }
      return values;
    }, {cacheName: current.cache, urls: current});
    assert.ok(cached.projectsCss.includes('.cvp-chat-continue'));
    assert.ok(cached.projectsJs.includes('captureProjectsAuthBoundary'));
    assert.ok(cached.projectsJs.includes("track('RecentWorkResumed'"));
    assert.ok(cached.libraryJs.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.libraryJs.includes('authBoundaryIsCurrent(authBoundary)'));
    assert.ok(cached.libraryJs.includes("api('/api/manuscripts/' + encodeURIComponent(book.id), null, authBoundary)"));
    assert.ok(cached.authController.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.deviceAuth.includes('async checkSession({commit = true} = {})'));
    assert.ok(cached.mobileBridge.includes('tokenMutation'));
    assert.ok(cached.mobileBridge.includes('clearSessionToken(expectedToken)'));
    assert.ok(cached.mobileBridge.includes('clearSessionToken(requestToken)'));
    assert.ok(cached.chatTransport.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.chatTransport.includes('assertOwnerCurrent(expectedOwnerId)'));
    assert.ok(cached.billingManager.includes('suppliedBoundary'));
    assert.ok(cached.billingManager.includes('assertBillingBoundary'));
    assert.ok(cached.subscriptionUi.includes('scrubBillingBoundary'));
    assert.ok(cached.subscriptionUi.includes('promptBoundary'));
    assert.ok(cached.creditConfirmation.includes('scrubAuthBoundary'));
    assert.ok(cached.creditConfirmation.includes('activeDialog'));
    assert.ok(cached.uiFunctions.includes('scrubReportDialogs'));
    assert.ok(cached.uiFunctions.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.composer.includes('currentComposerOwnerId'));
    assert.ok(cached.composer.includes('{expectedOwnerId}'));
    assert.ok(cached.runtime.includes(current.sync));
    assert.ok(cached.runtime.includes(current.chat));
    assert.ok(cached.runtime.includes(current.app));
    assert.ok(cached.sync.includes('X-Ask-Crump-Sync-Owner'));
    assert.ok(cached.chat.includes('activeSynchronization'));
    assert.ok(cached.profile.includes('bindOwner(nextOwnerId)'));
    assert.ok(cached.presence.includes('scrubAuthBoundary'));
    assert.ok(cached.account.includes('scrubAuthBoundary'));
    assert.ok(cached.app.includes('CrumpConversationState'));
    assert.ok(cached.productAnalytics.includes('suppliedBoundary'));
    assert.ok(cached.productAnalytics.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.intelligence.includes('scrubIntelligenceAuthBoundary'));
    assert.ok(cached.intelligence.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.billing51.includes('scrubBillingBoundary'));
    assert.ok(cached.billing52.includes('scrubBilling52Boundary'));
    assert.ok(cached.billing522.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.subscriptions.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.activity.includes('currentUserId() !== ownerUserId'));
    assert.ok(cached.activity.includes('X-Ask-Crump-Expected-Owner'));
    assert.ok(cached.productLoader.includes('/crump-product-5.3.js?v=5.9.76-legacy-project-resume-truth-1'));
    assert.ok(cached.libraryLoader.includes('/crump-library-5.7.js?v=5.9.76-account-owner-boundary-1'));
    assert.ok(cached.codeLoader.includes('/crump-code-5.9.35.js?v=5.9.76-account-owner-boundary-1'));
    assert.equal(Object.values(cached).some(value => value.includes('stale-r272:')), false);

    assert.deepEqual(errors, []);
    offlineExpected = true;
    await context.setOffline(true);
    await page.reload({waitUntil: 'load'});
    const offlineReturn = await assertRuntimeExecuted(page, '/sw.js');
    assert.equal(offlineReturn.projectsStyle, current.projectsCss);
    assert.equal(offlineReturn.libraryStyle, current.libraryCss);
    assert.equal(offlineReturn.authControllerPreload, current.authController);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      legacyCache: previous.cache,
      activeCache: current.cache,
      firstControlled,
      offlineReturn,
      currentAssetsExecutedBeforeControllerChange: true,
      currentAssetsReturnedOffline: true,
      expectedOfflineNetworkFailures: expectedOfflineNetworkFailures.length,
      errors,
    }));
  } finally {
    fixture.releaseInstall();
    if (context) await context.setOffline(false).catch(() => {});
    await browser.close();
    await new Promise(resolve => fixture.server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
