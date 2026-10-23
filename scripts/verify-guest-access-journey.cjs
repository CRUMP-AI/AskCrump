'use strict';

const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const fixturePath = '/tests/fixtures/guest-access-journey.html';
const staticFiles = new Map([
  [fixturePath, path.join(root, 'tests', 'fixtures', 'guest-access-journey.html')],
  ...[
    'safe-storage.js',
    'auth-resilience.js',
    'device-auth.js',
    'chat-resilience.js',
    'ui-functions.js',
    'app.js',
    'crump-4.3.js',
    'crump-5.0.js',
    'crump-v1-body.js',
    'auth-controller.js',
  ].map(name => [`/${name}`, path.join(root, 'public', name)]),
]);
const fixedNow = '2026-10-22T20:00:00.000Z';
const nextAvailableAt = '2026-10-23T20:00:00.000Z';

function loadPlaywright() {
  const moduleId = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
  try {
    return require(moduleId);
  } catch (error) {
    throw new Error(
      `Playwright could not be loaded from ${JSON.stringify(moduleId)}. `
      + 'Set ASKCRUMP_PLAYWRIGHT_MODULE to the existing Playwright module directory; do not install dependencies.\n'
      + error.message,
    );
  }
}

function parseCookies(header) {
  const cookies = {};
  for (const part of String(header || '').split(';')) {
    const separator = part.indexOf('=');
    if (separator < 0) continue;
    const key = part.slice(0, separator).trim();
    const raw = part.slice(separator + 1).trim();
    if (!key) continue;
    try { cookies[key] = decodeURIComponent(raw); }
    catch (_) { cookies[key] = raw; }
  }
  return cookies;
}

async function readJson(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 64 * 1024) throw new Error('Fixture request body exceeded 64 KiB.');
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function startFixtureServer() {
  const sessions = new Map();
  let sequence = 0;
  const records = {
    requests: [],
    guestAttempts: [],
    guestMints: [],
    sessionChecks: [],
    usageChecks: [],
    acknowledgements: [],
    chats: [],
    registrations: [],
    verifications: [],
    verificationReplays: [],
    termsAcceptances: [],
    unexpectedApi: [],
  };

  const allowance = session => ({
    limit: 5,
    used: session.used,
    remaining: Math.max(0, 5 - session.used),
    windowKind: 'rolling_24h',
    windowSeconds: 86400,
    nextAvailableAt: session.used >= 5 ? nextAvailableAt : null,
  });

  const publicUser = session => ({
    id: session.userId,
    email: session.email || null,
    fullName: session.fullName || '',
    isVerified: session.kind === 'registered',
    isGuest: session.kind === 'guest',
    subscriptionTier: 'free',
    tier: 'free',
    termsAcceptedAt: session.termsAcceptedAt,
    termsVersion: session.termsAcceptedAt ? '2026-08-01' : null,
    freeMessageLimit: 5,
    freeMessageWindowKind: 'rolling_24h',
    freeMessageWindowSeconds: 86400,
    guestMessageLimit: 5,
  });

  const makeSession = ({
    kind,
    caseName,
    used = 0,
    email = '',
    fullName = '',
    userId = '',
    termsAccepted = kind === 'registered',
  }) => {
    sequence += 1;
    const sessionId = `fixture-session-${sequence}`;
    const resolvedUserId = userId || `fixture-user-${sequence}`;
    const session = {
      sessionId,
      userId: resolvedUserId,
      kind,
      caseName,
      used,
      email: email || (kind === 'guest' ? `guest-${resolvedUserId}@guest.askcrump.local` : ''),
      fullName,
      pendingVerification: false,
      verificationToken: '',
      verifiedSessionId: '',
      revokedAt: null,
      deviceInfo: {},
      termsAcceptedAt: termsAccepted ? fixedNow : null,
    };
    sessions.set(sessionId, session);
    return session;
  };

  const createRegisteredSession = (caseName, used = 0) => makeSession({
    kind: 'registered',
    caseName,
    used,
    email: `${caseName}@fixture.invalid`,
    fullName: 'Registered Fixture',
  });

  const revokeGuestByControl = sessionId => {
    const session = sessions.get(sessionId);
    assert.ok(session, `fixture session ${sessionId} does not exist`);
    assert.equal(session.kind, 'guest', 'only a guest fixture session can be control-revoked');
    const revokedAt = `2026-10-22T20:00:${String(sequence).padStart(2, '0')}.000Z`;
    session.revokedAt = revokedAt;
    session.deviceInfo.guestControlRevokedAt = revokedAt;
    return session;
  };

  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const cookies = parseCookies(request.headers.cookie);
    const caseName = cookies.fixture_case || 'unlabelled';
    const mode = cookies.fixture_mode === 'disabled' ? 'disabled' : 'enabled';
    const storedSession = sessions.get(cookies.fixture_session) || null;
    const session = storedSession && !storedSession.revokedAt ? storedSession : null;
    records.requests.push({method: request.method, pathname: url.pathname, caseName, mode});

    const commonHeaders = {
      'Cache-Control': 'no-store',
      'Content-Security-Policy': "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; object-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; worker-src 'none'",
      'X-Content-Type-Options': 'nosniff',
    };
    const json = (status, body, headers = {}) => {
      response.writeHead(status, {
        ...commonHeaders,
        'Content-Type': 'application/json; charset=utf-8',
        ...headers,
      });
      response.end(JSON.stringify(body));
    };
    const rejectGuestWhenDisabled = () => {
      if (mode !== 'disabled' || session?.kind !== 'guest') return false;
      json(503, {
        success: false,
        code: 'GUEST_MODE_DISABLED',
        error: 'Guest mode is disabled.',
      });
      return true;
    };

    try {
      if (request.method === 'GET' && staticFiles.has(url.pathname)) {
        const body = await readFile(staticFiles.get(url.pathname));
        response.writeHead(200, {
          ...commonHeaders,
          'Content-Type': url.pathname.endsWith('.html')
            ? 'text/html; charset=utf-8'
            : 'text/javascript; charset=utf-8',
        });
        response.end(body);
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/auth/check-session') {
        const check = {
          caseName,
          mode,
          sessionId: storedSession?.sessionId || null,
          kind: storedSession?.kind || null,
          revoked: Boolean(storedSession?.revokedAt),
          status: 200,
          authenticated: false,
        };
        records.sessionChecks.push(check);
        // Production check-session converts every AuthenticationError, including
        // a disabled/revoked guest token, into a definitive HTTP 200 signed-out
        // response. The browser may then clear only its local identity state.
        if (mode === 'disabled' && storedSession?.kind === 'guest') {
          json(200, {success: true, authenticated: false});
          return;
        }
        if (!session) {
          json(200, {success: true, authenticated: false});
          return;
        }
        check.authenticated = true;
        json(200, {
          success: true,
          authenticated: true,
          data: {
            user: publicUser(session),
            settings: {},
            expiresAt: '2026-10-24T20:00:00.000Z',
          },
        });
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/auth/guest') {
        records.guestAttempts.push({caseName, mode, existingKind: storedSession?.kind || null});
        if (session?.kind === 'registered') {
          json(200, {
            success: true,
            data: {user: publicUser(session), guest: false},
          });
          return;
        }
        if (mode === 'disabled') {
          json(503, {success: false, code: 'GUEST_MODE_DISABLED', error: 'Guest mode is disabled.'});
          return;
        }
        const active = session || makeSession({kind: 'guest', caseName});
        if (!session) records.guestMints.push({caseName, sessionId: active.sessionId, userId: active.userId});
        json(200, {
          success: true,
          message: 'Guest session started.',
          data: {
            user: publicUser(active),
            guest: true,
            expiresAt: '2026-10-24T20:00:00.000Z',
          },
        }, {
          'Set-Cookie': `fixture_session=${encodeURIComponent(active.sessionId)}; Path=/; HttpOnly; SameSite=Lax`,
        });
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/usage/check') {
        records.usageChecks.push({caseName, sessionId: session?.sessionId || null, used: session?.used ?? null});
        if (rejectGuestWhenDisabled()) return;
        if (!session) {
          json(401, {success: false, error: 'Authentication required.'});
          return;
        }
        const freeAllowance = allowance(session);
        json(200, {
          success: true,
          tier: 'free',
          usage: {messages: session.used},
          limits: {messages: 5},
          daily: {
            tier: 'free',
            used: session.used,
            limit: 5,
            remaining: freeAllowance.remaining,
          },
          freeMessageAllowance: freeAllowance,
          credits: {balance: 0},
          requiresPurchase: freeAllowance.remaining <= 0,
          upgradeRequired: freeAllowance.remaining <= 0,
          requiredTier: freeAllowance.remaining <= 0 ? 'professional' : null,
          nextRequestSource: freeAllowance.remaining > 0 ? 'included' : 'subscription',
        });
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/account/accept-terms') {
        if (rejectGuestWhenDisabled()) return;
        if (!session) {
          json(401, {success: false, error: 'Authentication required.'});
          return;
        }
        const body = await readJson(request);
        const version = String(body.version || '');
        if (version !== '2026-08-01') {
          json(400, {
            success: false,
            error: 'Accept the current Terms and Privacy Policy version.',
          });
          return;
        }
        session.termsAcceptedAt = fixedNow;
        records.termsAcceptances.push({
          caseName,
          sessionId: session.sessionId,
          version,
        });
        json(200, {success: true, user: publicUser(session)});
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/chat/ack') {
        if (rejectGuestWhenDisabled()) return;
        if (!session) {
          json(401, {success: false, error: 'Authentication required.'});
          return;
        }
        const body = await readJson(request);
        records.acknowledgements.push({
          caseName,
          sessionId: session.sessionId,
          chatId: String(body.chatId || ''),
          messageId: String(body.messageId || ''),
        });
        json(200, {
          success: true,
          deliveredAt: fixedNow,
          seenAt: fixedNow,
          activity: 'thinking',
        });
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/chat') {
        if (rejectGuestWhenDisabled()) return;
        if (!session) {
          json(401, {success: false, error: 'Authentication required.'});
          return;
        }
        const body = await readJson(request);
        const submittedHistory = Array.isArray(body.history)
          ? body.history.map(item => ({
            role: String(item?.role || ''),
            content: String(item?.content || ''),
          }))
          : null;
        if (session.used >= 5) {
          json(403, {
            success: false,
            code: 'FREE_TEXT_LIMIT_REACHED',
            error: 'Your five free text messages in the rolling 24-hour window have been used.',
            accountRequired: session.kind === 'guest',
            upgradeRequired: true,
            requiredTier: 'professional',
            freeMessageAllowance: allowance(session),
          });
          return;
        }
        session.used += 1;
        const ordinal = session.used;
        records.chats.push({
          caseName,
          sessionId: session.sessionId,
          chatId: String(body.chatId || ''),
          messageId: String(body.messageId || ''),
          message: String(body.message || ''),
          historyLength: submittedHistory?.length ?? -1,
          history: submittedHistory,
        });
        json(200, {
          success: true,
          response: `Fixture reply ${ordinal}`,
          assistantMessage: {
            id: `fixture-assistant-${session.sessionId}-${ordinal}`,
            role: 'assistant',
            content: `Fixture reply ${ordinal}`,
            timestamp: fixedNow,
          },
          conversationRevision: ordinal,
          dailyUsage: {
            tier: 'free',
            used: session.used,
            limit: 5,
            remaining: Math.max(0, 5 - session.used),
            freeMessageAllowance: allowance(session),
          },
        });
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/auth/register') {
        // This fixture endpoint intentionally exercises only the guest-conversion
        // branch. It is not evidence for the production route's separate
        // signed-out new-account behavior.
        const controlRevokedGuest = Boolean(
          storedSession?.kind === 'guest'
          && storedSession.revokedAt
          && storedSession.deviceInfo?.guestControlRevokedAt === storedSession.revokedAt
        );
        const registrationSession = (
          storedSession?.kind === 'guest'
          && (!storedSession.revokedAt || controlRevokedGuest)
        ) ? storedSession : null;
        if (!registrationSession) {
          json(401, {success: false, error: 'A guest session is required for this fixture conversion.'});
          return;
        }
        const body = await readJson(request);
        if (body.termsAccepted !== true || String(body.termsVersion || '') !== '2026-08-01') {
          json(400, {
            success: false,
            error: 'Accept the current Terms and Privacy Policy version.',
          });
          return;
        }
        const registrationResponse = {
          success: true,
          message: 'Account created. Check your email to verify it.',
          emailSent: true,
        };
        records.registrations.push({
          caseName,
          sessionId: registrationSession.sessionId,
          userId: registrationSession.userId,
          usedBefore: registrationSession.used,
          recoveredControlRevoked: controlRevokedGuest,
          email: String(body.email || ''),
          fullName: String(body.fullName || ''),
          hasPassword: Boolean(body.password),
          termsAccepted: body.termsAccepted === true,
          termsVersion: String(body.termsVersion || ''),
          response: registrationResponse,
        });
        // Registration updates the guest row but intentionally leaves it a guest
        // until inbox possession is proven. No full account capability is granted
        // and no cookie is rotated by this endpoint.
        registrationSession.email = String(body.email || 'registered@fixture.invalid');
        registrationSession.fullName = String(body.fullName || '');
        registrationSession.pendingVerification = true;
        registrationSession.verificationToken = `fixture-verification-${registrationSession.sessionId}`;
        if (body.termsAccepted === true) registrationSession.termsAcceptedAt = fixedNow;
        json(200, registrationResponse);
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/auth/verify-email') {
        const token = String(url.searchParams.get('token') || '');
        const verificationOwner = [...sessions.values()].find(candidate => (
          candidate.kind === 'guest'
          && candidate.verificationToken === token
        ));
        if (!verificationOwner) {
          response.writeHead(303, {
            ...commonHeaders,
            Location: `${fixturePath}?verification=failed`,
          });
          response.end();
          return;
        }
        if (!verificationOwner.pendingVerification && verificationOwner.verifiedSessionId) {
          records.verificationReplays.push({
            caseName: verificationOwner.caseName,
            userId: verificationOwner.userId,
            verifiedSessionId: verificationOwner.verifiedSessionId,
          });
          response.writeHead(303, {
            ...commonHeaders,
            Location: `${fixturePath}?verification=already_verified`,
          });
          response.end();
          return;
        }
        const pendingSession = verificationOwner;

        const revokedSessionIds = [];
        for (const candidate of sessions.values()) {
          if (candidate.userId !== pendingSession.userId || candidate.revokedAt) continue;
          candidate.revokedAt = fixedNow;
          candidate.deviceInfo.guestVerificationRevokedAt = fixedNow;
          revokedSessionIds.push(candidate.sessionId);
        }
        const verifiedSession = makeSession({
          kind: 'registered',
          caseName: pendingSession.caseName,
          used: pendingSession.used,
          email: pendingSession.email,
          fullName: pendingSession.fullName,
          userId: pendingSession.userId,
        });
        pendingSession.pendingVerification = false;
        pendingSession.verifiedSessionId = verifiedSession.sessionId;
        records.verifications.push({
          caseName: pendingSession.caseName,
          userId: pendingSession.userId,
          oldSessionId: pendingSession.sessionId,
          newSessionId: verifiedSession.sessionId,
          revokedSessionIds,
          used: verifiedSession.used,
        });
        response.writeHead(303, {
          ...commonHeaders,
          Location: `${fixturePath}?verification=success`,
          'Set-Cookie': `fixture_session=${encodeURIComponent(verifiedSession.sessionId)}; Path=/; HttpOnly; SameSite=Lax`,
        });
        response.end();
        return;
      }

      if (url.pathname.startsWith('/api/')) {
        records.unexpectedApi.push({method: request.method, pathname: url.pathname, caseName});
        json(404, {success: false, error: 'Unexpected fixture API request.'});
        return;
      }

      response.writeHead(404, {...commonHeaders, 'Content-Type': 'text/plain; charset=utf-8'});
      response.end('Not found');
    } catch (error) {
      json(500, {success: false, error: `Fixture failure: ${error.message}`});
    }
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      resolve({
        server,
        baseUrl: `http://127.0.0.1:${address.port}`,
        sessions,
        records,
        createRegisteredSession,
        revokeGuestByControl,
      });
    });
  });
}

function stopServer(server) {
  return new Promise((resolve, reject) => {
    if (!server?.listening) return resolve();
    server.close(error => error ? reject(error) : resolve());
  });
}

async function sessionCookie(context) {
  const cookies = await context.cookies();
  return cookies.find(cookie => cookie.name === 'fixture_session')?.value || '';
}

async function createHarness(browser, fixture, {
  caseName,
  mode = 'enabled',
  sessionId = '',
  viewport = {width: 1440, height: 900},
} = {}) {
  const context = await browser.newContext({
    viewport,
    serviceWorkers: 'block',
  });
  await context.addInitScript(() => {
    window.__guestJourneySignals = {authenticatedReady: []};
    window.addEventListener('crump:authenticated-ready', () => {
      window.__guestJourneySignals.authenticatedReady.push({
        userId: window.currentUser?.id || null,
        isGuest: window.currentUser?.isGuest,
      });
    });
  });
  const cookies = [
    {name: 'fixture_case', value: caseName, url: fixture.baseUrl, sameSite: 'Lax'},
    {name: 'fixture_mode', value: mode, url: fixture.baseUrl, sameSite: 'Lax'},
  ];
  if (sessionId) {
    cookies.push({
      name: 'fixture_session',
      value: sessionId,
      url: fixture.baseUrl,
      sameSite: 'Lax',
      httpOnly: true,
    });
  }
  await context.addCookies(cookies);

  const origin = new URL(fixture.baseUrl).origin;
  const blocked = [];
  const requests = [];
  await context.route('**/*', async route => {
    let requestUrl;
    try { requestUrl = new URL(route.request().url()); }
    catch (_) {
      blocked.push(route.request().url());
      await route.abort();
      return;
    }
    if (requestUrl.protocol === 'http:' && requestUrl.origin === origin) {
      await route.continue();
      return;
    }
    blocked.push(requestUrl.href);
    await route.abort();
  });
  context.on('request', request => {
    const url = new URL(request.url());
    requests.push({method: request.method(), url: url.href, pathname: url.pathname});
  });

  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  return {caseName, context, page, blocked, requests, pageErrors, consoleErrors};
}

function assertIsolated(harness, {allowConsole = []} = {}) {
  assert.deepEqual(harness.blocked, [], 'the fixture attempted an external request');
  assert.deepEqual(harness.pageErrors, [], 'the browser raised an uncaught page error');
  const unexpectedConsole = harness.consoleErrors.filter(message =>
    !allowConsole.some(pattern => pattern.test(message))
  );
  assert.deepEqual(unexpectedConsole, [], 'the browser emitted an unexpected console error');
}

async function openFixture(harness, fixture, suffix = '') {
  await harness.page.goto(`${fixture.baseUrl}${fixturePath}${suffix}`, {waitUntil: 'load'});
}

async function waitForApp(page, {guest}) {
  await page.waitForFunction(expectedGuest => {
    const app = document.getElementById('appContainer');
    const terms = document.getElementById('tosModal');
    return Boolean(
      window.CrumpAccess
      && window.currentUser?.id
      && window.currentUser.isGuest === expectedGuest
      && (
        (app && getComputedStyle(app).display !== 'none')
        || (terms && getComputedStyle(terms).display !== 'none')
      )
    );
  }, guest);
  const termsVisible = await page.locator('#tosModal').evaluate(node => getComputedStyle(node).display !== 'none');
  if (termsVisible) {
    await page.locator('#tosAccept').check();
    await page.locator('#tosAcceptBtn').click();
  }
  await page.waitForFunction(() => {
    const app = document.getElementById('appContainer');
    const shell = document.querySelector('.v1-shell');
    const send = document.getElementById('sendButton');
    const readySignals = window.__guestJourneySignals?.authenticatedReady || [];
    return Boolean(
      app
      && getComputedStyle(app).display !== 'none'
      && app.getAttribute('aria-busy') !== 'true'
      && !shell?.hasAttribute('inert')
      && document.documentElement.dataset.crump50Booted === 'true'
      && send?.dataset.crump50 === 'true'
      && window.sendMessage?.name === 'studioSendMessage'
      && readySignals.some(signal => signal.userId === window.currentUser?.id)
    );
  });
  await page.locator('#freeTextAllowancePill').waitFor({state: 'visible'});
}

async function waitForLogin(page) {
  await page.waitForFunction(() => {
    const auth = document.getElementById('authContainer');
    const login = document.getElementById('loginForm');
    const app = document.getElementById('appContainer');
    return auth && login && app
      && getComputedStyle(auth).display !== 'none'
      && getComputedStyle(login).display !== 'none'
      && getComputedStyle(app).display === 'none';
  });
}

async function sendText(harness, fixture, text, expectedMessages, expectedRemaining) {
  const {page} = harness;
  let phase = 'fill-draft';
  try {
    await page.locator('#userInput').fill(text);
    phase = 'wait-for-production-composer';
    await page.waitForFunction(() => {
      const button = document.getElementById('sendButton');
      return button?.dataset.crump50 === 'true'
        && window.sendMessage?.name === 'studioSendMessage'
        && !button.disabled
        && button.getAttribute('aria-disabled') !== 'true';
    });
    phase = 'click-production-composer';
    await page.locator('#sendButton').click();
    phase = 'wait-for-completed-reply';
    await page.waitForFunction(expected => {
      const messages = (window.chats || []).flatMap(chat => chat.messages || []);
      return messages.length === expected && messages.at(-1)?.role === 'assistant';
    }, expectedMessages);
    phase = 'wait-for-allowance-update';
    await page.waitForFunction(expected =>
      document.getElementById('freeTextAllowancePill')?.textContent.includes(`${expected} of 5`),
    expectedRemaining);
  } catch (error) {
    const state = await page.evaluate(() => ({
      appDisplay: getComputedStyle(document.getElementById('appContainer')).display,
      appAriaBusy: document.getElementById('appContainer')?.getAttribute('aria-busy'),
      shellInert: document.querySelector('.v1-shell')?.hasAttribute('inert'),
      authDisplay: getComputedStyle(document.getElementById('authContainer')).display,
      currentUser: window.currentUser,
      currentChatId: window.currentChatId,
      authenticatedReady: window.__guestJourneySignals?.authenticatedReady || [],
      crump50Loaded: window.__crump50Loaded === true,
      crump50Booted: document.documentElement.dataset.crump50Booted,
      sendMessageName: window.sendMessage?.name,
      draft: document.getElementById('userInput')?.value,
      sendButton: (() => {
        const button = document.getElementById('sendButton');
        return button ? {
          crump50: button.dataset.crump50,
          disabled: button.disabled,
          ariaDisabled: button.getAttribute('aria-disabled'),
        } : null;
      })(),
      messages: (window.chats || []).flatMap(chat => chat.messages || []).map(message => ({
        role: message.role,
        content: message.content,
        deliveryStatus: message.deliveryStatus,
        replyStatus: message.replyStatus,
        replyError: message.replyError,
      })),
      domMessages: [...document.querySelectorAll('#chatContainer .message')].map(node => ({
        classes: node.className,
        text: node.textContent,
      })),
      storedChats: (() => {
        try {
          return JSON.parse(localStorage.getItem(window.STORAGE_KEYS?.CHATS) || '[]');
        } catch (storageError) {
          return {parseError: storageError.message};
        }
      })(),
      toasts: [...document.querySelectorAll('.toast__message')].map(node => node.textContent),
    }));
    const fixtureState = {
      requests: fixture.records.requests.filter(row => row.caseName === harness.caseName).slice(-25),
      acknowledgements: fixture.records.acknowledgements.filter(row => row.caseName === harness.caseName),
      chats: fixture.records.chats.filter(row => row.caseName === harness.caseName),
      unexpectedApi: fixture.records.unexpectedApi.filter(row => row.caseName === harness.caseName),
      browserRequests: harness.requests.slice(-25),
      blockedRequests: harness.blocked,
      pageErrors: harness.pageErrors,
      consoleErrors: harness.consoleErrors,
    };
    throw new Error(
      `Guest send failed during ${phase}: ${JSON.stringify({page: state, fixture: fixtureState})}`,
      {cause: error},
    );
  }
}

async function desktopJourney(browser, fixture) {
  const caseName = 'desktop-full';
  const harness = await createHarness(browser, fixture, {caseName});
  try {
    await openFixture(harness, fixture);
    await waitForApp(harness.page, {guest: true});
    const desktopTerms = fixture.records.termsAcceptances.filter(row => row.caseName === caseName);
    assert.equal(desktopTerms.length, 1);
    assert.equal(desktopTerms[0].version, '2026-08-01');
    assert.match(await harness.page.locator('#freeTextAllowancePill').textContent(), /Guest · 5 of 5 free text messages left/);
    assert.equal(fixture.records.guestMints.filter(row => row.caseName === caseName).length, 1);

    const originalSessionId = await sessionCookie(harness.context);
    const originalSession = fixture.sessions.get(originalSessionId);
    assert.ok(originalSession, 'guest cookie did not resolve to the stateful fixture session');
    const originalUserId = originalSession.userId;

    for (let index = 1; index <= 5; index += 1) {
      await sendText(harness, fixture, `Desktop guest message ${index}`, index * 2, 5 - index);
    }
    assert.equal(fixture.records.acknowledgements.filter(row => row.caseName === caseName).length, 5);
    const desktopChats = fixture.records.chats.filter(row => row.caseName === caseName);
    assert.equal(desktopChats.length, 5);
    assert.deepEqual(
      desktopChats.map(row => row.historyLength),
      [1, 3, 5, 7, 9],
      'each chat request must carry the real client history through the new user message',
    );
    const expectedDesktopHistory = [];
    desktopChats.forEach((row, index) => {
      const ordinal = index + 1;
      expectedDesktopHistory.push({role: 'user', content: `Desktop guest message ${ordinal}`});
      assert.deepEqual(
        row.history,
        expectedDesktopHistory,
        `desktop chat ${ordinal} did not submit the exact restored role/content order`,
      );
      expectedDesktopHistory.push({role: 'assistant', content: `Fixture reply ${ordinal}`});
    });
    assert.equal(originalSession.used, 5);
    assert.equal(await harness.page.locator('.user-message').count(), 5);
    assert.equal(await harness.page.locator('.assistant-message').count(), 5);

    const sixthDraft = 'Desktop guest message 6 must remain an unsent draft';
    await harness.page.locator('#userInput').fill(sixthDraft);
    await harness.page.locator('#sendButton').click();
    await harness.page.locator('#registerForm').waitFor({state: 'visible'});
    await harness.page.locator('#guestWallNote').waitFor({state: 'visible'});
    assert.equal(await harness.page.locator('#userInput').inputValue(), sixthDraft);
    assert.equal(fixture.records.acknowledgements.filter(row => row.caseName === caseName).length, 5);
    assert.equal(fixture.records.chats.filter(row => row.caseName === caseName).length, 5);
    assert.equal(await harness.page.evaluate(() => (window.chats || []).flatMap(chat => chat.messages || []).length), 10);
    assert.match(await harness.page.locator('#guestWallNote').textContent(), /preserve this conversation and your remaining allowance/i);
    assert.match(await harness.page.locator('#guestWallNote').textContent(), /does not add another five messages/i);

    const storageBefore = await harness.page.evaluate(() => ({
      key: window.STORAGE_KEYS.CHATS,
      chats: JSON.parse(localStorage.getItem(window.STORAGE_KEYS.CHATS) || '[]'),
    }));
    assert.equal(storageBefore.key, `crump_chats:${originalUserId}`);
    assert.equal(storageBefore.chats[0].messages.length, 10);

    await harness.page.locator('#registerEmail').fill('owner@fixture.invalid');
    await harness.page.locator('#registerPassword').fill('FixturePass123!');
    await harness.page.locator('#registerTerms').check();
    await harness.page.locator('#registrationSubmitBtn').click();
    await harness.page.locator('#registrationPending').waitFor({state: 'visible'});
    assert.equal(fixture.records.registrations.filter(row => row.caseName === caseName).length, 1);
    const registration = fixture.records.registrations.find(row => row.caseName === caseName);
    assert.equal(registration.sessionId, originalSessionId);
    assert.equal(registration.userId, originalUserId);
    assert.equal(registration.usedBefore, 5);
    assert.equal(registration.hasPassword, true);
    assert.equal(registration.termsAccepted, true);
    assert.equal(registration.termsVersion, '2026-08-01');
    assert.equal(registration.fullName, '', 'registration must match production and omit profile name');
    assert.deepEqual(registration.response, {
      success: true,
      message: 'Account created. Check your email to verify it.',
      emailSent: true,
    });
    assert.equal(registration.recoveredControlRevoked, false);
    assert.equal(originalSession.kind, 'guest', 'registration alone must not promote the guest');
    assert.equal(originalSession.pendingVerification, true);
    assert.equal(originalSession.used, 5);
    assert.equal(await sessionCookie(harness.context), originalSessionId, 'registration must not rotate the guest cookie');

    await harness.page.goto(
      `${fixture.baseUrl}/api/auth/verify-email?token=${encodeURIComponent(originalSession.verificationToken)}`,
      {waitUntil: 'load'},
    );
    await waitForApp(harness.page, {guest: false});
    const verifiedSessionId = await sessionCookie(harness.context);
    assert.notEqual(verifiedSessionId, originalSessionId, 'verification must rotate to a new session cookie');
    const verifiedSession = fixture.sessions.get(verifiedSessionId);
    assert.ok(verifiedSession, 'rotated verification cookie did not resolve to a fixture session');
    assert.equal(verifiedSession.userId, originalUserId);
    assert.equal(verifiedSession.kind, 'registered');
    assert.equal(verifiedSession.used, 5);
    assert.ok(originalSession.revokedAt, 'verification must revoke the original guest session');
    assert.equal(originalSession.deviceInfo.guestVerificationRevokedAt, originalSession.revokedAt);
    const verification = fixture.records.verifications.find(row => row.caseName === caseName);
    assert.ok(verification, 'verification endpoint was not exercised');
    assert.equal(verification.oldSessionId, originalSessionId);
    assert.equal(verification.newSessionId, verifiedSessionId);
    assert.ok(verification.revokedSessionIds.includes(originalSessionId));
    assert.match(await harness.page.locator('#freeTextAllowancePill').textContent(), /Free · 0 of 5 free text messages left/);

    const setSessionCookieForProbe = value => harness.context.addCookies([{
      name: 'fixture_session',
      value,
      url: fixture.baseUrl,
      sameSite: 'Lax',
      httpOnly: true,
    }]);
    const probeSession = () => harness.page.evaluate(async () => {
      const response = await fetch('/api/auth/check-session', {cache: 'no-store'});
      return {status: response.status, body: await response.json()};
    });
    await setSessionCookieForProbe(originalSessionId);
    const revokedGuestProbe = await probeSession();
    assert.equal(revokedGuestProbe.status, 200);
    assert.equal(
      revokedGuestProbe.body.authenticated,
      false,
      'the original guest credential must be invalid after verification',
    );
    await setSessionCookieForProbe(verifiedSessionId);
    const verifiedAccountProbe = await probeSession();
    assert.equal(verifiedAccountProbe.status, 200);
    assert.equal(verifiedAccountProbe.body.authenticated, true);
    assert.equal(verifiedAccountProbe.body.data.user.id, originalUserId);
    assert.equal(verifiedAccountProbe.body.data.user.isGuest, false);

    await harness.page.goto(
      `${fixture.baseUrl}/api/auth/verify-email?token=${encodeURIComponent(originalSession.verificationToken)}`,
      {waitUntil: 'load'},
    );
    await waitForApp(harness.page, {guest: false});
    assert.equal(await sessionCookie(harness.context), verifiedSessionId, 'verification replay must not rotate the account cookie');
    assert.equal(fixture.records.verifications.filter(row => row.caseName === caseName).length, 1);
    assert.equal(fixture.records.verificationReplays.filter(row => row.caseName === caseName).length, 1);

    await harness.page.waitForFunction(() => document.querySelectorAll('#chatsList .chat-item').length === 1);
    await harness.page.locator('#menuBtn').click();
    await harness.page.waitForFunction(() => !document.getElementById('sidebar')?.hasAttribute('inert'));
    await harness.page.locator('#chatsList .chat-item').click();
    assert.equal(await harness.page.locator('.user-message').count(), 5);
    assert.equal(await harness.page.locator('.assistant-message').count(), 5);
    const storageAfter = await harness.page.evaluate(() => ({
      key: window.STORAGE_KEYS.CHATS,
      messages: (window.chats || []).flatMap(chat => chat.messages || []).length,
      currentUser: window.currentUser,
    }));
    assert.equal(storageAfter.key, storageBefore.key);
    assert.equal(storageAfter.messages, 10);
    assert.equal(storageAfter.currentUser.id, originalUserId);
    assert.equal(storageAfter.currentUser.isGuest, false);
    assert.equal(storageAfter.currentUser.fullName, '');
    assert.equal(storageAfter.currentUser.freeMessagesUsed, 5);
    assert.equal(
      await harness.page.locator('#v1ProfileNudge').evaluate(node => node.hidden),
      false,
      'post-verification profile setup path did not remain available',
    );
    assert.equal(fixture.records.guestMints.filter(row => row.caseName === caseName).length, 1);

    assertIsolated(harness, {
      allowConsole: [
        /Your five free text messages/i,
        /Failed to load resource: the server responded with a status of 403/i,
      ],
    });
    return {
      originalSessionId,
      verifiedSessionId,
      userId: originalUserId,
      chatCalls: 5,
      continuityScope: 'localStorage-only; this fixture does not exercise cloud sync',
      preservedLocalMessages: storageAfter.messages,
      preservedRemaining: 0,
    };
  } finally {
    await harness.context.close();
  }
}

async function paidToolGuard(browser, fixture) {
  const caseName = 'paid-tool-guard';
  const harness = await createHarness(browser, fixture, {caseName});
  try {
    await openFixture(harness, fixture);
    await waitForApp(harness.page, {guest: true});
    await harness.page.locator('#imageTool').click();
    await harness.page.locator('#registerForm').waitFor({state: 'visible'});
    assert.match(await harness.page.locator('#guestWallNote').textContent(), /Image Studio requires a paid plan/i);
    assert.equal(await harness.page.evaluate(() => window.__fixture.imageOpens), 0);
    assert.equal(await harness.page.evaluate(() => window.__fixture.upgradePrompts.length), 0);
    assert.equal(fixture.records.chats.filter(row => row.caseName === caseName).length, 0);
    assertIsolated(harness);
    return {guardedTool: 'Image Studio', downstreamOpens: 0};
  } finally {
    await harness.context.close();
  }
}

async function disabledMint(browser, fixture) {
  const caseName = 'disabled-mint';
  const harness = await createHarness(browser, fixture, {caseName, mode: 'disabled'});
  try {
    await openFixture(harness, fixture);
    await waitForLogin(harness.page);
    assert.equal(await harness.page.evaluate(() => window.currentUser), null);
    assert.equal(await sessionCookie(harness.context), '');
    assert.equal(fixture.records.guestAttempts.filter(row => row.caseName === caseName).length, 1);
    assert.equal(fixture.records.guestMints.filter(row => row.caseName === caseName).length, 0);
    assertIsolated(harness, {allowConsole: [/Failed to load resource: the server responded with a status of 503/i]});
    return {mintAttempts: 1, mintedSessions: 0, failClosed: true};
  } finally {
    await harness.context.close();
  }
}

async function capturedGuestToken(browser, fixture) {
  const caseName = 'captured-guest-token';
  const harness = await createHarness(browser, fixture, {caseName});
  try {
    await openFixture(harness, fixture);
    await waitForApp(harness.page, {guest: true});
    const capturedSessionId = await sessionCookie(harness.context);
    assert.ok(capturedSessionId);
    const cachedBeforeDisable = await harness.page.evaluate(() => window.deviceAuth.cachedUser());
    assert.equal(cachedBeforeDisable?.isGuest, true, 'guest identity was not cached before disablement');
    fixture.revokeGuestByControl(capturedSessionId);
    await harness.context.addCookies([{
      name: 'fixture_mode',
      value: 'disabled',
      url: fixture.baseUrl,
      sameSite: 'Lax',
    }]);
    await harness.page.reload({waitUntil: 'load'});
    await waitForLogin(harness.page);
    const clearedState = await harness.page.evaluate(() => ({
      currentUser: window.currentUser,
      cachedUser: window.deviceAuth.cachedUser(),
      deviceSession: window.deviceAuth.session,
      storageRemovals: window.__fixture.storageRemovals,
      appVisible: getComputedStyle(document.getElementById('appContainer')).display !== 'none',
    }));
    assert.equal(clearedState.currentUser, null);
    assert.equal(clearedState.cachedUser, null, 'a definitive 200/false session check must clear cached identity');
    assert.equal(clearedState.deviceSession, null, 'a definitive 200/false session check must clear device identity');
    assert.ok(
      clearedState.storageRemovals.includes('crump_user_cache_v4'),
      'deviceAuth.clearLocalState did not remove the cached identity key',
    );
    assert.equal(clearedState.appVisible, false);
    assert.equal(await sessionCookie(harness.context), capturedSessionId);
    assert.equal(
      fixture.records.guestAttempts.filter(row => row.caseName === caseName && row.mode === 'disabled').length,
      0,
      'the first reload retains the returning-device hint long enough to show login without minting',
    );

    // On the next navigation there is no longer a returning identity hint. The
    // inert cookie is checked again, then bootstrap makes exactly one ordinary
    // guest-start attempt; the disabled control rejects it without a remint.
    await harness.page.reload({waitUntil: 'load'});
    await waitForLogin(harness.page);
    const disabledChecks = fixture.records.sessionChecks.filter(row => (
      row.caseName === caseName && row.mode === 'disabled'
    ));
    assert.equal(disabledChecks.length, 2);
    for (const check of disabledChecks) {
      assert.equal(check.status, 200);
      assert.equal(check.authenticated, false);
      assert.equal(check.sessionId, capturedSessionId);
      assert.equal(check.revoked, true);
    }
    assert.equal(
      fixture.records.guestAttempts.filter(row => row.caseName === caseName && row.mode === 'disabled').length,
      1,
      'bootstrap must make only one failed mint attempt after the local identity hint is gone',
    );
    assert.equal(fixture.records.guestMints.filter(row => row.caseName === caseName).length, 1);
    const disabledCheck = fixture.records.sessionChecks.find(row =>
      row.caseName === caseName && row.mode === 'disabled' && row.sessionId === capturedSessionId
    );
    assert.ok(disabledCheck, 'captured guest token was not rechecked after guest mode was disabled');
    assertIsolated(harness, {allowConsole: [/Failed to load resource: the server responded with a status of 503/i]});
    return {
      capturedSessionId,
      sessionCheckStatus: 200,
      identityCleared: true,
      failedMintAttempts: 1,
      reminted: false,
      failClosed: true,
    };
  } finally {
    await harness.context.close();
  }
}

async function controlRevokedRegistrationRecovery(browser, fixture) {
  const caseName = 'control-revoked-registration';
  const harness = await createHarness(browser, fixture, {caseName});
  try {
    await openFixture(harness, fixture);
    await waitForApp(harness.page, {guest: true});
    await sendText(harness, fixture, 'Preserve this guest work through control rollback', 2, 4);
    const originalSessionId = await sessionCookie(harness.context);
    const originalSession = fixture.sessions.get(originalSessionId);
    assert.ok(originalSession);
    assert.equal(originalSession.used, 1);
    const localContinuityBefore = await harness.page.evaluate(() => ({
      key: window.STORAGE_KEYS.CHATS,
      messages: JSON.parse(localStorage.getItem(window.STORAGE_KEYS.CHATS) || '[]')
        .flatMap(chat => chat.messages || []).length,
    }));
    assert.equal(localContinuityBefore.key, `crump_chats:${originalSession.userId}`);
    assert.equal(localContinuityBefore.messages, 2);
    assert.deepEqual(
      fixture.records.chats.filter(row => row.caseName === caseName).map(row => row.historyLength),
      [1],
    );
    assert.deepEqual(
      fixture.records.chats.find(row => row.caseName === caseName).history,
      [{role: 'user', content: 'Preserve this guest work through control rollback'}],
    );

    fixture.revokeGuestByControl(originalSessionId);
    await harness.context.addCookies([{
      name: 'fixture_mode',
      value: 'disabled',
      url: fixture.baseUrl,
      sameSite: 'Lax',
    }]);

    const blockedStatuses = await harness.page.evaluate(async () => {
      const request = async (url, init) => (await fetch(url, init)).status;
      return {
        usage: await request('/api/usage/check'),
        chat: await request('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({message: 'must stay blocked'}),
        }),
        guestMint: await request('/api/auth/guest', {method: 'POST'}),
      };
    });
    assert.deepEqual(blockedStatuses, {usage: 401, chat: 401, guestMint: 503});
    assert.equal(
      fixture.records.guestAttempts.filter(row => row.caseName === caseName && row.mode === 'disabled').length,
      1,
    );
    assert.equal(fixture.records.guestMints.filter(row => row.caseName === caseName).length, 1);

    await harness.page.locator('#imageTool').click();
    await harness.page.locator('#registerForm').waitFor({state: 'visible'});
    await harness.page.locator('#registerEmail').fill('rollback-owner@fixture.invalid');
    await harness.page.locator('#registerPassword').fill('FixturePass123!');
    await harness.page.locator('#registerTerms').check();
    await harness.page.locator('#registrationSubmitBtn').click();
    await harness.page.locator('#registrationPending').waitFor({state: 'visible'});

    const registration = fixture.records.registrations.find(row => row.caseName === caseName);
    assert.ok(registration, 'control-revoked registration did not reach the recovery endpoint');
    assert.equal(registration.sessionId, originalSessionId);
    assert.equal(registration.userId, originalSession.userId);
    assert.equal(registration.usedBefore, 1);
    assert.equal(registration.recoveredControlRevoked, true);
    assert.equal(registration.termsAccepted, true);
    assert.equal(registration.termsVersion, '2026-08-01');
    assert.equal(registration.fullName, '', 'registration must match production and omit profile name');
    assert.deepEqual(registration.response, {
      success: true,
      message: 'Account created. Check your email to verify it.',
      emailSent: true,
    });
    assert.equal(originalSession.kind, 'guest');
    assert.equal(originalSession.pendingVerification, true);
    assert.equal(originalSession.used, 1);
    assert.equal(await sessionCookie(harness.context), originalSessionId, 'registration must keep the revoked guest credential until verification');
    const localContinuityPending = await harness.page.evaluate(() => ({
      key: window.STORAGE_KEYS.CHATS,
      messages: JSON.parse(localStorage.getItem(window.STORAGE_KEYS.CHATS) || '[]')
        .flatMap(chat => chat.messages || []).length,
    }));
    assert.deepEqual(localContinuityPending, localContinuityBefore);

    await harness.page.goto(
      `${fixture.baseUrl}/api/auth/verify-email?token=${encodeURIComponent(originalSession.verificationToken)}`,
      {waitUntil: 'load'},
    );
    await waitForApp(harness.page, {guest: false});
    const verifiedSessionId = await sessionCookie(harness.context);
    const verifiedSession = fixture.sessions.get(verifiedSessionId);
    assert.notEqual(verifiedSessionId, originalSessionId);
    assert.equal(verifiedSession?.userId, originalSession.userId);
    assert.equal(verifiedSession?.used, 1);
    assert.equal(verifiedSession?.kind, 'registered');
    assert.equal(verifiedSession?.fullName, '');
    assert.match(await harness.page.locator('#freeTextAllowancePill').textContent(), /Free · 4 of 5 free text messages left/);
    assert.equal(
      await harness.page.locator('#v1ProfileNudge').evaluate(node => node.hidden),
      false,
      'profile setup path must not hide the restored workspace',
    );
    assert.equal(
      await harness.page.evaluate(() => (window.chats || []).flatMap(chat => chat.messages || []).length),
      2,
    );
    // Production intentionally opens every reload on a clean desk while keeping
    // prior conversations in Chats. Reopen the preserved conversation before
    // proving that a verified follow-up carries its restored history.
    await harness.page.waitForFunction(() => document.querySelectorAll('#chatsList .chat-item').length === 1);
    const restoredChatId = await harness.page.evaluate(() => window.chats?.[0]?.id || '');
    assert.ok(restoredChatId, 'the preserved conversation did not expose a restorable chat id');
    await harness.page.locator('#menuBtn').click();
    await harness.page.waitForFunction(() => !document.getElementById('sidebar')?.hasAttribute('inert'));
    await harness.page.locator(`#chatsList .chat-item[data-chat-id="${restoredChatId}"]`).click();
    await harness.page.waitForFunction(expected => {
      const chat = (window.chats || []).find(candidate => candidate.id === expected.id);
      return window.currentChatId === expected.id && chat?.messages?.length === expected.messages;
    }, {id: restoredChatId, messages: 2});
    await sendText(
      harness,
      fixture,
      'Continue the restored conversation after verification',
      4,
      3,
    );
    const recoveryChats = fixture.records.chats.filter(row => row.caseName === caseName);
    assert.equal(recoveryChats.length, 2);
    assert.equal(recoveryChats[1].historyLength, 3);
    assert.deepEqual(recoveryChats[1].history, [
      {role: 'user', content: 'Preserve this guest work through control rollback'},
      {role: 'assistant', content: 'Fixture reply 1'},
      {role: 'user', content: 'Continue the restored conversation after verification'},
    ]);
    assert.equal(
      verifiedSession.used,
      2,
      'post-verification usage did not continue from the preserved count of one',
    );
    assert.equal(
      await harness.page.evaluate(() => (window.chats || []).flatMap(chat => chat.messages || []).length),
      4,
    );

    assertIsolated(harness, {
      allowConsole: [
        /Failed to load resource: the server responded with a status of 401/i,
        /Failed to load resource: the server responded with a status of 503/i,
      ],
    });
    return {
      originalSessionId,
      verifiedSessionId,
      blockedStatuses,
      recoveredControlRevoked: true,
      continuityScope: 'localStorage-only; this fixture does not exercise cloud sync',
      restoredLocalMessagesBeforeFollowUp: 2,
      localMessagesAfterFollowUp: 4,
      remainingAtVerification: 4,
      remainingAfterFollowUp: 3,
      allowanceReset: false,
    };
  } finally {
    await harness.context.close();
  }
}

async function registeredUnaffected(browser, fixture) {
  const caseName = 'registered-unaffected';
  const registered = fixture.createRegisteredSession(caseName, 2);
  const harness = await createHarness(browser, fixture, {
    caseName,
    mode: 'disabled',
    sessionId: registered.sessionId,
  });
  try {
    await openFixture(harness, fixture);
    await waitForApp(harness.page, {guest: false});
    const registeredCookie = await sessionCookie(harness.context);
    const registeredUser = await harness.page.evaluate(() => window.currentUser);
    assert.equal(registeredCookie, registered.sessionId);
    assert.equal(registeredUser.id, registered.userId);
    assert.equal(registeredUser.isGuest, false);
    assert.match(await harness.page.locator('#freeTextAllowancePill').textContent(), /Free · 3 of 5 free text messages left/);
    await sendText(harness, fixture, 'Registered account stays usable while guest mode is disabled', 2, 2);
    assert.equal(await sessionCookie(harness.context), registeredCookie, 'registered chat must not rotate the session');
    assert.equal((await harness.page.evaluate(() => window.currentUser)).isGuest, false);
    assert.equal(fixture.records.guestAttempts.filter(row => row.caseName === caseName).length, 0);
    assert.ok(fixture.records.usageChecks.some(row => row.caseName === caseName && row.sessionId === registered.sessionId));
    const registeredChats = fixture.records.chats.filter(row => row.caseName === caseName);
    assert.equal(registeredChats.length, 1);
    assert.equal(registeredChats[0].historyLength, 1);
    assert.deepEqual(registeredChats[0].history, [
      {role: 'user', content: 'Registered account stays usable while guest mode is disabled'},
    ]);
    assert.equal(registered.used, 3);
    assertIsolated(harness);
    return {sessionId: registered.sessionId, chatCalls: 1, remaining: 2, guestMintAttempts: 0};
  } finally {
    await harness.context.close();
  }
}

async function mobileFixtureShellCheck(browser, fixture) {
  const caseName = 'mobile-spot-check';
  const harness = await createHarness(browser, fixture, {
    caseName,
    viewport: {width: 390, height: 844},
  });
  try {
    await openFixture(harness, fixture);
    await waitForApp(harness.page, {guest: true});
    // This fixture supplies only the DOM contract required by the real client
    // scripts. Its CSS is intentionally synthetic, so geometry checks below are
    // fixture-shell sanity checks and make no claim about production styling.
    await sendText(harness, fixture, 'Mobile guest message 1', 2, 4);
    const mobileChats = fixture.records.chats.filter(row => row.caseName === caseName);
    assert.equal(mobileChats.length, 1);
    assert.equal(mobileChats[0].historyLength, 1);
    assert.deepEqual(mobileChats[0].history, [{role: 'user', content: 'Mobile guest message 1'}]);
    const appGeometry = await harness.page.evaluate(() => {
      const pill = document.getElementById('freeTextAllowancePill').getBoundingClientRect();
      const composer = document.querySelector('.input-container').getBoundingClientRect();
      return {
        viewport: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        pill: {left: pill.left, right: pill.right, width: pill.width},
        composer: {left: composer.left, right: composer.right, width: composer.width},
      };
    });
    assert.ok(appGeometry.scrollWidth <= appGeometry.viewport, 'fixture shell overflowed horizontally');
    assert.ok(appGeometry.pill.left >= 0 && appGeometry.pill.right <= appGeometry.viewport, 'fixture allowance pill left the viewport');
    assert.ok(appGeometry.composer.left >= 0 && appGeometry.composer.right <= appGeometry.viewport, 'fixture composer left the viewport');

    await harness.page.locator('#imageTool').click();
    await harness.page.locator('#registerForm').waitFor({state: 'visible'});
    const wallGeometry = await harness.page.evaluate(() => {
      const form = document.getElementById('registerForm').getBoundingClientRect();
      return {viewport: window.innerWidth, scrollWidth: document.documentElement.scrollWidth, left: form.left, right: form.right};
    });
    assert.ok(wallGeometry.scrollWidth <= wallGeometry.viewport, 'fixture registration wall overflowed horizontally');
    assert.ok(wallGeometry.left >= 0 && wallGeometry.right <= wallGeometry.viewport, 'fixture registration wall left the viewport');
    assert.match(await harness.page.locator('#guestWallNote').textContent(), /requires a paid plan/i);
    assert.equal(await harness.page.evaluate(() => window.__fixture.imageOpens), 0);
    assertIsolated(harness);
    return {
      viewport: '390x844',
      fixtureShellOnly: true,
      remaining: 4,
      fixtureShellNoHorizontalOverflow: true,
      paidToolGuarded: true,
    };
  } finally {
    await harness.context.close();
  }
}

(async () => {
  // Resolve the already-installed automation library before opening a socket.
  // A module-load failure therefore cannot strand a listening fixture server.
  const {chromium} = loadPlaywright();
  let fixture = null;
  let browser = null;
  try {
    fixture = await startFixtureServer();
    const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || '';
    browser = await chromium.launch({
      headless: true,
      ...(executablePath ? {executablePath} : {}),
    });

    const evidence = {
      desktop: await desktopJourney(browser, fixture),
      paidTool: await paidToolGuard(browser, fixture),
      disabledMint: await disabledMint(browser, fixture),
      capturedGuest: await capturedGuestToken(browser, fixture),
      controlRevokedRegistration: await controlRevokedRegistrationRecovery(browser, fixture),
      registered: await registeredUnaffected(browser, fixture),
      mobileFixtureShell: await mobileFixtureShellCheck(browser, fixture),
    };

    assert.deepEqual(fixture.records.unexpectedApi, [], 'the journey reached an API outside the explicit mock contract');
    const allBrowserRequests = fixture.records.requests.length;
    console.log(JSON.stringify({
      ok: true,
      isolation: {
        server: fixture.baseUrl.replace(/:\d+$/, ':<ephemeral>'),
        bind: '127.0.0.1',
        serviceWorkers: 'blocked',
        externalRequests: 0,
        productionCredentials: false,
        browserRequestsObservedByFixture: allBrowserRequests,
      },
      evidence,
      apiEvidence: {
        guestMints: fixture.records.guestMints.length,
        sessionChecks: fixture.records.sessionChecks.length,
        usageChecks: fixture.records.usageChecks.length,
        acknowledgements: fixture.records.acknowledgements.length,
        chats: fixture.records.chats.length,
        registrations: fixture.records.registrations.length,
        verifications: fixture.records.verifications.length,
        verificationReplays: fixture.records.verificationReplays.length,
        termsAcceptances: fixture.records.termsAcceptances.length,
        unexpectedApi: fixture.records.unexpectedApi.length,
      },
    }, null, 2));
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (fixture) await stopServer(fixture.server);
    }
  }
})().catch(error => {
  console.error(error.stack || error.message || error);
  process.exitCode = 1;
});
