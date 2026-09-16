const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');
const axePath = require.resolve('axe-core/axe.min.js');

const publicDirectory = path.resolve(process.cwd(), 'public');
const featurePayload = Object.freeze({
  success: true,
  internalAccess: false,
  features: {code_workspace: {configured: true, entitled: true, includedDaily: 3, standardOverflowCredits: 12}},
  providers: {code: {configured: true, maxDurationSeconds: 180}},
});

function completedTask(
  status = 'completed',
  id = 'task-preview',
  projectId = 'project-preview',
  objective = 'Repair the retry boundary and prove the result.',
) {
  const active = status !== 'completed';
  return {
    id,
    project_id: projectId,
    objective,
    mode: 'implement',
    source_repo_url: 'https://github.com/example/project.git',
    source_ref: 'main',
    status,
    network_policy: 'deny_all',
    max_duration_seconds: 180,
    payment_source: 'included',
    credits_spent: 0,
    result_summary: active ? '' : 'Repaired the retry boundary and added focused coverage.',
    result_patch: active ? '' : [
      'diff --git a/src/retry.js b/src/retry.js',
      '--- a/src/retry.js',
      '+++ b/src/retry.js',
      '@@ -1 +1,2 @@',
      '-run()',
      '+run({retries: 1})',
      '+recordAttempt()',
      'diff --git a/tests/retry.test.js b/tests/retry.test.js',
      'new file mode 100644',
      '--- /dev/null',
      '+++ b/tests/retry.test.js',
      '@@ -0,0 +1 @@',
      '+testRetryBoundary()',
    ].join('\n'),
    verification: active ? [] : [{
      command: 'python3 -m pytest -q tests/test_retry.py',
      returnCode: 0,
      stdout: '1 passed in 0.04s',
      stderr: '',
    }],
    events: active ? [
      {id: 1, event_type: 'task.created', payload: {mode: 'implement'}, created_at: '2026-09-16T20:00:00Z'},
      {id: 2, event_type: 'agent.started', payload: {status: 'running'}, created_at: '2026-09-16T20:00:02Z'},
      {id: 3, event_type: 'tool.requested', payload: {tool: 'read_file', path: 'src/retry.js'}, created_at: '2026-09-16T20:00:03Z'},
    ] : [
      {id: 1, event_type: 'task.created', payload: {mode: 'implement'}, created_at: '2026-09-16T20:00:00Z'},
      {id: 2, event_type: 'verification.completed', payload: {verificationCount: 1}, created_at: '2026-09-16T20:00:05Z'},
      {id: 3, event_type: 'task.completed', payload: {status: 'completed'}, created_at: '2026-09-16T20:00:06Z'},
    ],
    approvals: [],
    created_at: '2026-09-16T20:00:00Z',
    updated_at: '2026-09-16T20:00:06Z',
    expires_at: '2999-09-16T20:00:00Z',
  };
}

function failedVerificationTask() {
  const task = completedTask('completed');
  return {
    ...task,
    status: 'failed',
    failure_code: 'CODE_VERIFICATION_FAILED',
    result_summary: 'Verification failed. Review the recorded checks and patch before retrying.',
    verification: [{
      command: 'python3 -m pytest -q tests/test_retry.py',
      returnCode: 1,
      stdout: '1 failed in 0.04s',
      stderr: 'assertion failed',
    }],
    events: [
      {id: 1, event_type: 'verification.completed', payload: {status: 'failed'}, created_at: '2026-09-16T20:00:05Z'},
      {id: 2, event_type: 'task.failed', payload: {failureCode: 'CODE_VERIFICATION_FAILED'}, created_at: '2026-09-16T20:00:06Z'},
    ],
  };
}

function fixtureHtml(mode) {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><link rel="stylesheet" href="/crump-code-5.9.35.css"><title>Autonomous Crump review proof</title></head>
<body style="margin:0;background:#080a0d;color:#fff">
<button type="button" data-crump-code-destination hidden>Autonomous</button>
<script>
  window.__fixtureMode = ${JSON.stringify(mode)};
  window.__taskReads = 0;
  window.__taskMutations = [];
  const fixtureWait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  window.fetch = async input => {
    const requestPath = String(input);
    if (requestPath.includes('/api/features')) return Response.json(${JSON.stringify(featurePayload)});
    if (requestPath.endsWith('/api/projects')) {
      const projects = window.__fixtureMode === 'ownership'
        ? [{id:'project-a',name:'Slow Project A'},{id:'project-b',name:'Current Project B'}]
        : [{id:'project-preview',name:'Reliability'}];
      return Response.json({success:true,projects});
    }
    if (window.__fixtureMode === 'ownership' && requestPath.includes('/api/projects/project-a/code/tasks')) {
      await fixtureWait(350);
      return Response.json({success:true,tasks:[
        (${completedTask.toString()})('completed','task-project-a','project-a','Late Project A task'),
      ]});
    }
    if (window.__fixtureMode === 'ownership' && requestPath.includes('/api/projects/project-b/code/tasks')) {
      await fixtureWait(15);
      return Response.json({success:true,tasks:[
        (${completedTask.toString()})('completed','task-slow','project-b','Slow Task A'),
        (${completedTask.toString()})('queued','task-fast','project-b','Fast Task B'),
      ]});
    }
    if (requestPath.includes('/api/projects/project-preview/code/tasks')) {
      const task = window.__fixtureMode === 'failed'
        ? ${JSON.stringify(failedVerificationTask())}
        : (${completedTask.toString()})(window.__fixtureMode === 'durable' ? 'running' : 'completed');
      return Response.json({success:true,configured:true,tasks:[task]});
    }
    if (window.__fixtureMode === 'ownership' && requestPath.includes('/api/code/tasks/task-fast/run')) {
      window.__taskMutations.push(requestPath);
      return Response.json({success:true,task:(${completedTask.toString()})('running','task-fast','project-b','Fast Task B')});
    }
    if (window.__fixtureMode === 'ownership' && requestPath.includes('/api/code/tasks/task-fast/cancel')) {
      window.__taskMutations.push(requestPath);
      return Response.json({success:true,task:(${completedTask.toString()})('cancelled','task-fast','project-b','Fast Task B')});
    }
    if (window.__fixtureMode === 'ownership' && requestPath.endsWith('/api/code/tasks/task-slow')) {
      await fixtureWait(300);
      return Response.json({success:true,task:(${completedTask.toString()})('completed','task-slow','project-b','Slow Task A')});
    }
    if (window.__fixtureMode === 'ownership' && requestPath.endsWith('/api/code/tasks/task-fast')) {
      await fixtureWait(10);
      return Response.json({success:true,task:(${completedTask.toString()})('queued','task-fast','project-b','Fast Task B')});
    }
    if (requestPath.includes('/api/code/tasks/task-preview')) {
      window.__taskReads += 1;
      if (window.__fixtureMode === 'durable' && window.__taskReads === 2) throw new TypeError('fixture offline');
      if (window.__fixtureMode === 'failed') {
        return Response.json({success:true,task:${JSON.stringify(failedVerificationTask())}});
      }
      const status = window.__fixtureMode !== 'durable' || window.__taskReads >= 4
        ? 'completed' : window.__taskReads >= 3 ? 'verifying' : 'running';
      return Response.json({success:true,task:(${completedTask.toString()})(status)});
    }
    return Response.json({success:false,error:'Unexpected fixture request'}, {status:404});
  };
</script>
<script src="/crump-code-5.9.35.js"></script>
<script>window.addEventListener('load', () => window.CrumpCodeWorkspace.open(), {once:true});</script>
</body></html>`;
}

async function startServer() {
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    response.setHeader('Cache-Control', 'no-store');
    if (url.pathname === '/fixture') {
      response.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
      const mode = ['durable', 'ownership', 'failed'].includes(url.searchParams.get('mode'))
        ? url.searchParams.get('mode') : 'completed';
      response.end(fixtureHtml(mode));
      return;
    }
    const relative = url.pathname.replace(/^\/+/, '');
    const filePath = path.resolve(publicDirectory, relative);
    if (!filePath.startsWith(`${publicDirectory}${path.sep}`)) {
      response.writeHead(404).end();
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, {'Content-Type': path.extname(filePath) === '.css' ? 'text/css' : 'text/javascript'});
      response.end(body);
    } catch (_) {
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return {server, port: server.address().port};
}

async function inspectCompleted(browser, baseUrl, viewport) {
  const context = await browser.newContext({viewport});
  const page = await context.newPage();
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${baseUrl}/fixture?mode=completed`, {waitUntil: 'networkidle'});
  await page.waitForSelector('.crump-code-diff-file');
  await page.addScriptTag({path: axePath});
  const accessibility = await page.evaluate(async () => {
    const result = await axe.run(document.querySelector('#crumpCodeWorkspace'), {
      rules: {'color-contrast': {enabled: false}},
    });
    return result.violations.map(violation => ({id: violation.id, nodes: violation.nodes.length}));
  });
  const initial = await page.evaluate(() => ({
    kicker: document.querySelector('.crump-code-kicker')?.textContent,
    stages: document.querySelectorAll('.crump-code-progress-stages li').length,
    saved: document.querySelector('.crump-code-connection')?.textContent,
    files: [...document.querySelectorAll('.crump-code-diff-file')].map(button => button.textContent.trim()),
    selected: document.querySelector('.crump-code-diff-viewer strong')?.textContent,
    totals: document.querySelector('.crump-code-diff-totals')?.textContent,
    check: document.querySelector('.crump-code-check summary')?.textContent,
    overflow: document.querySelector('.crump-code-shell').scrollWidth > window.innerWidth,
  }));
  assert.equal(initial.kicker, 'AUTONOMOUS CRUMP · PRIVATE PREVIEW');
  assert.equal(initial.stages, 5);
  assert.equal(initial.saved, 'Saved to Project');
  assert.equal(initial.files.length, 2);
  assert.equal(initial.selected, 'src/retry.js');
  assert.match(initial.totals, /\+3.*−1/);
  assert.match(initial.check, /Passed/);
  assert.equal(initial.overflow, false);
  assert.deepEqual(accessibility, []);
  await page.locator('.crump-code-diff-file').nth(1).click();
  assert.equal(await page.locator('.crump-code-diff-viewer strong').textContent(), 'tests/retry.test.js');
  await page.locator('.crump-code-check').first().click();
  assert.match(await page.locator('.crump-code-check pre').textContent(), /1 passed/);
  assert.deepEqual(errors, []);
  await context.close();
  return {...initial, accessibility};
}

async function inspectSelectionOwnership(browser, baseUrl) {
  const context = await browser.newContext({viewport: {width: 1280, height: 760}});
  const page = await context.newPage();
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${baseUrl}/fixture?mode=ownership`, {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => document.querySelectorAll('#crumpCodeProject option').length === 2);
  await page.selectOption('#crumpCodeProject', 'project-b');
  await page.waitForFunction(() => document.querySelectorAll('[data-crump-code-task]').length === 2);
  await page.getByRole('button', {name: /Fast Task B/}).click();
  await page.waitForFunction(() => document.querySelector('#crumpCodeDetail h3')?.textContent === 'Fast Task B');
  await page.waitForTimeout(500);
  const selection = await page.evaluate(() => ({
    project: document.querySelector('#crumpCodeProject')?.value,
    title: document.querySelector('#crumpCodeDetail h3')?.textContent,
    activeTask: document.querySelector('.crump-code-task.is-active')?.dataset.crumpCodeTask,
    listedTasks: [...document.querySelectorAll('[data-crump-code-task]')].map(node => node.dataset.crumpCodeTask),
  }));
  assert.deepEqual(selection, {
    project: 'project-b',
    title: 'Fast Task B',
    activeTask: 'task-fast',
    listedTasks: ['task-slow', 'task-fast'],
  });
  await page.check('#crumpCodeRunConfirmed');
  await page.click('#crumpCodeRun');
  await page.waitForSelector('[data-code-action="cancel"]');
  await page.click('[data-code-action="cancel"]');
  await page.waitForFunction(() => window.__taskMutations.length === 2);
  const mutations = await page.evaluate(() => window.__taskMutations);
  assert.deepEqual(mutations, [
    '/api/code/tasks/task-fast/run',
    '/api/code/tasks/task-fast/cancel',
  ]);
  assert.deepEqual(errors, []);
  await context.close();
  return {selection, mutations};
}

async function inspectDurableRecovery(browser, baseUrl) {
  const context = await browser.newContext({viewport: {width: 1280, height: 760}});
  const page = await context.newPage();
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${baseUrl}/fixture?mode=durable`, {waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.querySelector('#crumpCodeNotice')?.textContent.includes('Connection paused'));
  const paused = await page.evaluate(() => ({
    notice: document.querySelector('#crumpCodeNotice')?.textContent,
    connection: document.querySelector('.crump-code-connection')?.textContent,
    latest: document.querySelector('.crump-code-progress-latest')?.textContent,
  }));
  assert.match(paused.notice, /private worker continues safely/);
  assert.equal(paused.connection, 'Reconnecting');
  assert.match(paused.latest, /Inspecting src\/retry\.js/);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.waitForFunction(() => document.querySelector('.crump-code-status')?.dataset.status === 'verifying');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.waitForSelector('.crump-code-diff-file');
  assert.match(await page.locator('#crumpCodeNotice').textContent(), /Autonomous Crump finished/);
  assert.equal(await page.locator('.crump-code-connection').textContent(), 'Saved to Project');
  assert.deepEqual(errors, []);
  await context.close();
  return paused;
}

async function inspectFailedVerification(browser, baseUrl) {
  const context = await browser.newContext({viewport: {width: 1280, height: 760}});
  const page = await context.newPage();
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${baseUrl}/fixture?mode=failed`, {waitUntil: 'networkidle'});
  await page.waitForSelector('.crump-code-check[data-status="failed"]');
  const state = await page.evaluate(() => ({
    badge: document.querySelector('.crump-code-status')?.textContent,
    badgeStatus: document.querySelector('.crump-code-status')?.dataset.status,
    progressHeading: document.querySelector('.crump-code-progress h4')?.textContent,
    readyStageState: document.querySelector('.crump-code-progress-stages li:last-child')?.dataset.state,
    verification: document.querySelector('.crump-code-check summary')?.textContent,
    failure: document.querySelector('.crump-code-failure')?.textContent,
  }));
  assert.equal(state.badge, 'Failed safely');
  assert.equal(state.badgeStatus, 'failed');
  assert.equal(state.progressHeading, 'Failed safely');
  assert.equal(state.readyStageState, 'pending');
  assert.match(state.verification, /Exited 1/);
  assert.match(state.failure, /code verification failed/);
  assert.deepEqual(errors, []);
  await context.close();
  return state;
}

(async () => {
  const {server, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const baseUrl = `http://127.0.0.1:${port}`;
    const desktop = await inspectCompleted(browser, baseUrl, {width: 1280, height: 760});
    const phone = await inspectCompleted(browser, baseUrl, {width: 390, height: 844});
    const durable = await inspectDurableRecovery(browser, baseUrl);
    const ownership = await inspectSelectionOwnership(browser, baseUrl);
    const failedVerification = await inspectFailedVerification(browser, baseUrl);
    process.stdout.write(JSON.stringify({desktop, phone, durable, ownership, failedVerification}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
