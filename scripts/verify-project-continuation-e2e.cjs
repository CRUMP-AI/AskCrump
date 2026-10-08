const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');

const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const ROOT = path.resolve(__dirname, '..');
const FIXTURE_PATH = '/tests/fixtures/project-continuation-e2e.html';
const OWNER_A = 'fixture-owner-a';
const OWNER_B = 'fixture-owner-b';
const CHAT_A = '10000000-0000-4000-8000-000000000101';
const CHAT_B = '20000000-0000-4000-8000-000000000201';
const PROJECT_A = '10000000-0000-4000-8000-000000000102';
const PROJECT_B = '20000000-0000-4000-8000-000000000202';
const MESSAGE_A = '10000000-0000-4000-8000-000000000103';
const FOREIGN_SENTINEL = 'FOREIGN-OWNER-PRIVATE-SENTINEL';

function json(response, status, body) {
  response.writeHead(status, {
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json; charset=utf-8',
  });
  response.end(JSON.stringify(body));
}

function parseCookies(header = '') {
  return Object.fromEntries(String(header).split(';').map(value => value.trim()).filter(Boolean).map(value => {
    const separator = value.indexOf('=');
    if (separator < 0) return [decodeURIComponent(value), ''];
    return [decodeURIComponent(value.slice(0, separator)), decodeURIComponent(value.slice(separator + 1))];
  }));
}

async function requestJson(request) {
  let raw = '';
  for await (const chunk of request) {
    raw += chunk;
    if (raw.length > 1_000_000) throw new Error('Fixture request body exceeded the limit.');
  }
  return raw ? JSON.parse(raw) : {};
}

function publicProject(project) {
  return {
    id: project.id,
    name: project.name,
    description: project.description,
    instructions: project.instructions,
    created_at: project.created_at,
    updated_at: project.updated_at,
  };
}

function createStore(label) {
  const now = '2026-10-07T12:00:00.000Z';
  const chats = new Map([
    [OWNER_A, new Map([[CHAT_A, {
      chat_id: CHAT_A,
      title: `Launch continuity ${label}`,
      messages: [{
        id: MESSAGE_A,
        role: 'user',
        content: 'Continue the approved launch plan.',
        timestamp: now,
      }],
      created_at: now,
      updated_at: now,
      revision: 1,
    }]])],
    [OWNER_B, new Map([[CHAT_B, {
      chat_id: CHAT_B,
      title: FOREIGN_SENTINEL,
      messages: [{
        id: '20000000-0000-4000-8000-000000000203',
        role: 'user',
        content: FOREIGN_SENTINEL,
        timestamp: now,
      }],
      created_at: now,
      updated_at: now,
      revision: 1,
    }]])],
  ]);
  const projects = new Map([
    [OWNER_A, new Map()],
    [OWNER_B, new Map([[PROJECT_B, {
      id: PROJECT_B,
      name: FOREIGN_SENTINEL,
      description: FOREIGN_SENTINEL,
      instructions: FOREIGN_SENTINEL,
      created_at: now,
      updated_at: now,
    }]])],
  ]);
  const projectChats = new Map([[`${OWNER_B}:${PROJECT_B}`, new Set([CHAT_B])]]);
  const heldPulls = new Map();
  return {
    label,
    chats,
    projects,
    projectChats,
    analytics: [],
    pullCounts: new Map(),
    requests: [],
    heldPulls,
    holdFirstPull(session) {
      let release;
      const promise = new Promise(resolve => { release = resolve; });
      heldPulls.set(session, {
        promise,
        entered: false,
        released: false,
        release() {
          if (this.released) return;
          this.released = true;
          release();
        },
      });
    },
    releasePull(session) {
      const held = heldPulls.get(session);
      assert.ok(held, `No held sync pull for ${session}.`);
      held.release();
    },
  };
}

function ownedProject(store, owner, projectId) {
  return store.projects.get(owner)?.get(projectId) || null;
}

function projectForChat(store, owner, chatId) {
  for (const project of store.projects.get(owner)?.values() || []) {
    if (store.projectChats.get(`${owner}:${project.id}`)?.has(chatId)) return project;
  }
  return null;
}

function createFixtureServer(activeStore) {
  return http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    const cookies = parseCookies(request.headers.cookie);
    const owner = cookies.fixture_user || '';
    const session = cookies.fixture_session || '';
    const method = String(request.method || 'GET').toUpperCase();
    const store = activeStore.current;
    store.requests.push({method, path: url.pathname, owner, session});

    try {
      if (url.pathname === '/favicon.ico') {
        response.writeHead(204);
        response.end();
        return;
      }

      if (url.pathname === FIXTURE_PATH || url.pathname.startsWith('/public/')) {
        const relative = url.pathname.slice(1).replaceAll('/', path.sep);
        const filePath = path.resolve(ROOT, relative);
        if (!(filePath === ROOT || filePath.startsWith(`${ROOT}${path.sep}`))) {
          json(response, 404, {success: false, error: 'Not found.'});
          return;
        }
        const body = await fs.readFile(filePath);
        const extension = path.extname(filePath).toLowerCase();
        const contentType = extension === '.html'
          ? 'text/html; charset=utf-8'
          : (extension === '.js' ? 'text/javascript; charset=utf-8' : 'application/octet-stream');
        response.writeHead(200, {'Cache-Control': 'no-store', 'Content-Type': contentType});
        response.end(body);
        return;
      }

      if (!url.pathname.startsWith('/api/')) {
        json(response, 404, {success: false, error: 'Not found.'});
        return;
      }
      if (!store.chats.has(owner)) {
        json(response, 401, {success: false, error: 'Authentication required.'});
        return;
      }

      if (method === 'GET' && url.pathname === '/api/sync/pull') {
        const pullKey = `${owner}:${session}`;
        const count = (store.pullCounts.get(pullKey) || 0) + 1;
        store.pullCounts.set(pullKey, count);
        const held = store.heldPulls.get(session);
        if (count === 1 && held) {
          held.entered = true;
          await held.promise;
        }
        json(response, 200, {
          success: true,
          data: {
            chats: [...store.chats.get(owner).values()],
            settings: null,
          },
          serverTime: '2026-10-07T12:01:00.000Z',
        });
        return;
      }

      if (method === 'POST' && url.pathname === '/api/sync/push') {
        const body = await requestJson(request);
        const ownedChats = store.chats.get(owner);
        for (const chat of Array.isArray(body.chats) ? body.chats : []) {
          const chatId = String(chat?.chat_id || chat?.id || '').trim();
          if (chatId) ownedChats.set(chatId, {...chat, chat_id: chatId});
        }
        for (const deleted of Array.isArray(body.deletedChats) ? body.deletedChats : []) {
          const chatId = String(deleted?.chat_id || deleted?.id || deleted || '').trim();
          if (chatId) ownedChats.delete(chatId);
        }
        json(response, 200, {
          success: true,
          accepted: [...ownedChats.keys()],
          ignored: [],
          serverTime: '2026-10-07T12:01:01.000Z',
        });
        return;
      }

      if (method === 'GET' && url.pathname === '/api/features') {
        json(response, 200, {success: true, projectLimit: 3, features: {}});
        return;
      }

      if (method === 'GET' && url.pathname === '/api/projects') {
        json(response, 200, {
          success: true,
          projects: [...store.projects.get(owner).values()].map(publicProject),
          limit: 3,
        });
        return;
      }

      if (method === 'POST' && url.pathname === '/api/projects') {
        const body = await requestJson(request);
        const chatId = String(body.chatId || '').trim();
        if (!chatId || !store.chats.get(owner).has(chatId)) {
          json(response, 404, {success: false, error: 'Conversation not found.'});
          return;
        }
        const project = {
          id: PROJECT_A,
          name: String(body.name || 'Continued work').slice(0, 100),
          description: String(body.description || ''),
          instructions: '',
          created_at: '2026-10-07T12:02:00.000Z',
          updated_at: '2026-10-07T12:02:00.000Z',
        };
        store.projects.get(owner).set(project.id, project);
        store.projectChats.set(`${owner}:${project.id}`, new Set([chatId]));
        json(response, 200, {success: true, project: publicProject(project), conversationSaved: true});
        return;
      }

      const forChatMatch = url.pathname.match(/^\/api\/projects\/for-chat\/([^/]+)$/);
      if (method === 'GET' && forChatMatch) {
        const chatId = decodeURIComponent(forChatMatch[1]);
        const project = store.chats.get(owner).has(chatId) ? projectForChat(store, owner, chatId) : null;
        json(response, 200, {
          success: true,
          project: project ? {id: project.id, name: project.name} : null,
        });
        return;
      }

      const targetMatch = url.pathname.match(/^\/api\/projects\/target\/([^/]+)$/);
      if (method === 'GET' && targetMatch) {
        const project = ownedProject(store, owner, decodeURIComponent(targetMatch[1]));
        if (!project) {
          json(response, 404, {success: false, error: 'Project not found.'});
          return;
        }
        json(response, 200, {success: true, project: {id: project.id, name: project.name}});
        return;
      }

      const projectChatsMatch = url.pathname.match(/^\/api\/projects\/([^/]+)\/chats$/);
      if (projectChatsMatch) {
        const projectId = decodeURIComponent(projectChatsMatch[1]);
        const project = ownedProject(store, owner, projectId);
        if (!project) {
          json(response, 404, {success: false, error: 'Project not found.'});
          return;
        }
        if (method === 'GET') {
          const ids = [...(store.projectChats.get(`${owner}:${projectId}`) || [])];
          const conversations = ids.map(chatId => store.chats.get(owner).get(chatId)).filter(Boolean).map(chat => ({
            chatId: chat.chat_id,
            title: chat.title,
            createdAt: chat.created_at || chat.createdAt,
            updatedAt: chat.updated_at || chat.updatedAt,
          }));
          json(response, 200, {success: true, conversations});
          return;
        }
        if (method === 'POST') {
          const body = await requestJson(request);
          const chatId = String(body.chatId || '').trim();
          if (!store.chats.get(owner).has(chatId)) {
            json(response, 404, {success: false, error: 'Conversation not found.'});
            return;
          }
          const links = store.projectChats.get(`${owner}:${projectId}`) || new Set();
          links.add(chatId);
          store.projectChats.set(`${owner}:${projectId}`, links);
          json(response, 200, {success: true, project: publicProject(project), conversationSaved: true});
          return;
        }
      }

      const filesMatch = url.pathname.match(/^\/api\/projects\/([^/]+)\/files$/);
      if (method === 'GET' && filesMatch) {
        const project = ownedProject(store, owner, decodeURIComponent(filesMatch[1]));
        if (!project) {
          json(response, 404, {success: false, error: 'Project not found.'});
          return;
        }
        json(response, 200, {success: true, files: []});
        return;
      }

      const manuscriptsMatch = url.pathname.match(/^\/api\/projects\/([^/]+)\/manuscripts$/);
      if (method === 'GET' && manuscriptsMatch) {
        const project = ownedProject(store, owner, decodeURIComponent(manuscriptsMatch[1]));
        if (!project) {
          json(response, 404, {success: false, error: 'Project not found.'});
          return;
        }
        json(response, 200, {success: true, manuscripts: []});
        return;
      }

      const projectMatch = url.pathname.match(/^\/api\/projects\/([^/]+)$/);
      if (method === 'GET' && projectMatch) {
        const project = ownedProject(store, owner, decodeURIComponent(projectMatch[1]));
        if (!project) {
          json(response, 404, {success: false, error: 'Project not found.'});
          return;
        }
        json(response, 200, {success: true, project: publicProject(project), context: {canon: []}});
        return;
      }

      if (method === 'POST' && url.pathname === '/api/analytics/events') {
        const body = await requestJson(request);
        const keys = Object.keys(body).sort();
        if (
          JSON.stringify(keys) !== JSON.stringify(['eventKey', 'eventName', 'source'])
          || body.eventName !== 'RecentWorkResumed'
          || body.eventKey !== 'recent-work-resumed'
          || body.source !== 'project'
        ) {
          json(response, 400, {success: false, error: 'Unsafe fixture analytics payload.'});
          return;
        }
        store.analytics.push({owner, session, body});
        json(response, 200, {success: true, recorded: true});
        return;
      }

      json(response, 500, {success: false, error: `Unexpected fixture request: ${method} ${url.pathname}`});
    } catch (error) {
      json(response, 500, {success: false, error: error.message || 'Fixture server failed.'});
    }
  });
}

async function waitFor(predicate, message, timeoutMs = 5_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error(message);
}

async function openSession(browser, origin, viewport, session) {
  const context = await browser.newContext({viewport});
  await context.addCookies([
    {name: 'fixture_user', value: OWNER_A, url: origin, httpOnly: true, sameSite: 'Lax'},
    {name: 'fixture_session', value: session, url: origin, httpOnly: true, sameSite: 'Lax'},
  ]);
  const page = await context.newPage();
  const errors = [];
  const networkViolations = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    const requestUrl = new URL(request.url());
    if (requestUrl.origin !== origin) networkViolations.push(request.url());
  });
  await page.goto(`${origin}${FIXTURE_PATH}?fixtureUser=${encodeURIComponent(OWNER_A)}`, {
    waitUntil: 'load',
  });
  await page.waitForFunction(() => document.documentElement.dataset.fixtureReady === 'true');
  return {context, page, errors, networkViolations};
}

async function verifyViewport(browser, origin, activeStore, name, viewport) {
  const store = createStore(name);
  activeStore.current = store;

  const first = await openSession(browser, origin, viewport, `session-a-${name}`);
  try {
    await first.page.waitForFunction(expected => (
      Array.isArray(window.chats)
      && window.chats.length === 1
      && window.chats[0]?.id === expected
    ), CHAT_A);
    assert.deepEqual(await first.page.evaluate(() => window.__fixture.initialStorageKeys), []);
    await first.page.locator(`[data-chat-id="${CHAT_A}"]`).click();
    await first.page.waitForFunction(expected => window.currentChatId === expected, CHAT_A);
    const saved = await first.page.evaluate(() => window.CrumpProduct53.keepConversation({
      notify: false,
      refresh: false,
      continuitySource: 'result_action',
    }));
    assert.equal(saved.success, true);
    assert.equal(saved.project.id, PROJECT_A);
    const firstState = await first.page.evaluate(() => ({
      chatIds: window.chats.map(chat => chat.id),
      blankCount: window.chats.filter(chat => !Array.isArray(chat.messages) || chat.messages.length === 0).length,
      currentChatId: window.currentChatId,
      errors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
    }));
    assert.deepEqual(firstState.chatIds, [CHAT_A]);
    assert.equal(firstState.blankCount, 0);
    assert.equal(firstState.currentChatId, CHAT_A);
    assert.equal(firstState.errors, 0);
    assert.deepEqual(first.errors, []);
    assert.deepEqual(first.networkViolations, []);
  } finally {
    await first.context.close();
  }

  assert.equal(store.projects.get(OWNER_A).size, 1);
  assert.deepEqual([...store.projectChats.get(`${OWNER_A}:${PROJECT_A}`)], [CHAT_A]);

  const secondSession = `session-b-${name}`;
  store.holdFirstPull(secondSession);
  const second = await openSession(browser, origin, viewport, secondSession);
  try {
    await waitFor(
      () => store.heldPulls.get(secondSession)?.entered === true,
      `Session B did not start its held server sync (${name}).`,
    );
    assert.deepEqual(await second.page.evaluate(() => window.__fixture.initialStorageKeys), []);
    await second.page.evaluate(() => window.CrumpProduct53.open('projects'));
    const projectLink = second.page.locator(`[data-project-id="${PROJECT_A}"]`);
    await projectLink.waitFor({state: 'visible'});
    await projectLink.click();
    const resumeButton = second.page.locator(`[data-project-chat-id="${CHAT_A}"]`);
    await resumeButton.waitFor({state: 'visible'});
    assert.deepEqual(await second.page.evaluate(() => window.chats.map(chat => chat.id)), []);

    await resumeButton.click();
    await second.page.waitForTimeout(40);
    assert.equal(await second.page.evaluate(() => window.currentChatId), null);
    assert.equal(store.analytics.length, 0);
    store.releasePull(secondSession);

    await second.page.waitForFunction(expected => window.currentChatId === expected, CHAT_A);
    await waitFor(() => store.analytics.length === 1, `Resume analytics did not arrive (${name}).`);
    const resumed = await second.page.evaluate(() => ({
      chatIds: window.chats.map(chat => chat.id),
      blankCount: window.chats.filter(chat => !Array.isArray(chat.messages) || chat.messages.length === 0).length,
      currentChatId: window.currentChatId,
      renderedMessages: window.__fixture.renderedMessages,
      toasts: window.__fixture.toasts,
      destinations: window.__fixture.destinations,
      errors: Number(document.getElementById('fixtureErrors')?.textContent || 0),
    }));
    assert.deepEqual(resumed.chatIds, [CHAT_A]);
    assert.equal(resumed.blankCount, 0);
    assert.equal(resumed.currentChatId, CHAT_A);
    assert.equal(resumed.renderedMessages.length, 1);
    assert.equal(resumed.renderedMessages[0].id, MESSAGE_A);
    assert.equal(resumed.destinations.filter(destination => destination === 'ask').length, 1);
    assert.equal(resumed.toasts.some(toast => toast.tone === 'error'), false, JSON.stringify(resumed));
    assert.equal(resumed.errors, 0);

    const [projectsResponse, syncResponse, foreignResponse] = await Promise.all([
      second.context.request.get(`${origin}/api/projects`),
      second.context.request.get(`${origin}/api/sync/pull`),
      second.context.request.get(`${origin}/api/projects/${encodeURIComponent(PROJECT_B)}/chats`),
    ]);
    const isolation = {
      projectsStatus: projectsResponse.status(),
      projects: await projectsResponse.json(),
      syncStatus: syncResponse.status(),
      sync: await syncResponse.json(),
      foreignStatus: foreignResponse.status(),
      foreign: await foreignResponse.json(),
    };
    assert.equal(isolation.projectsStatus, 200);
    assert.equal(isolation.syncStatus, 200);
    assert.equal(isolation.foreignStatus, 404);
    assert.equal(JSON.stringify(isolation).includes(FOREIGN_SENTINEL), false);
    assert.deepEqual(isolation.projects.projects.map(project => project.id), [PROJECT_A]);
    assert.deepEqual(isolation.sync.data.chats.map(chat => chat.chat_id), [CHAT_A]);

    assert.equal(store.analytics.length, 1);
    assert.deepEqual(store.analytics[0], {
      owner: OWNER_A,
      session: secondSession,
      body: {
        eventName: 'RecentWorkResumed',
        eventKey: 'recent-work-resumed',
        source: 'project',
      },
    });
    assert.deepEqual([...store.chats.get(OWNER_A).keys()], [CHAT_A]);
    assert.equal([...store.chats.get(OWNER_A).values()].filter(chat => !chat.messages?.length).length, 0);
    assert.deepEqual(second.errors, []);
    assert.deepEqual(second.networkViolations, []);

    return {
      viewport: name,
      sessionAProject: PROJECT_A,
      resumedChat: resumed.currentChatId,
      analyticsEvents: store.analytics.length,
      localBlankDuplicates: resumed.blankCount,
      serverBlankDuplicates: [...store.chats.get(OWNER_A).values()].filter(chat => !chat.messages?.length).length,
      crossOwnerStatus: isolation.foreignStatus,
    };
  } finally {
    const held = store.heldPulls.get(secondSession);
    if (held && !held.released) store.releasePull(secondSession);
    await second.context.close();
  }
}

(async () => {
  const activeStore = {current: createStore('bootstrap')};
  const server = createFixtureServer(activeStore);
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  const origin = `http://127.0.0.1:${address.port}`;
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  try {
    const evidence = {
      desktop: await verifyViewport(browser, origin, activeStore, 'desktop', {width: 1440, height: 900}),
      phone: await verifyViewport(browser, origin, activeStore, 'phone', {width: 390, height: 844}),
    };
    process.stdout.write(`Project continuation end-to-end proof passed. ${JSON.stringify(evidence)}\n`);
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
