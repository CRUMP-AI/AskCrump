const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

const publicDirectory = path.resolve(process.cwd(), 'public');
const featurePayload = Object.freeze({
  success: true,
  internalAccess: false,
  features: {code_workspace: {configured: true, entitled: true, includedDaily: 3, standardOverflowCredits: 12}},
  providers: {code: {configured: true, maxDurationSeconds: 180}},
});

function completedTask(status = 'completed') {
  const active = status !== 'completed';
  return {
    id: 'task-preview',
    project_id: 'project-preview',
    objective: 'Repair the retry boundary and prove the result.',
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

function fixtureHtml(mode) {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><link rel="stylesheet" href="/crump-code-5.9.35.css"><title>Autonomous Crump review proof</title></head>
<body style="margin:0;background:#080a0d;color:#fff">
<button type="button" data-crump-code-destination hidden>Autonomous</button>
<script>
  window.__fixtureMode = ${JSON.stringify(mode)};
  window.__taskReads = 0;
  window.fetch = async input => {
    const requestPath = String(input);
    if (requestPath.includes('/api/features')) return Response.json(${JSON.stringify(featurePayload)});
    if (requestPath.endsWith('/api/projects')) return Response.json({success:true,projects:[{id:'project-preview',name:'Reliability'}]});
    if (requestPath.includes('/api/projects/project-preview/code/tasks')) {
      const task = (${completedTask.toString()})(window.__fixtureMode === 'durable' ? 'running' : 'completed');
      return Response.json({success:true,configured:true,tasks:[task]});
    }
    if (requestPath.includes('/api/code/tasks/task-preview')) {
      window.__taskReads += 1;
      if (window.__fixtureMode === 'durable' && window.__taskReads === 2) throw new TypeError('fixture offline');
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
      response.end(fixtureHtml(url.searchParams.get('mode') === 'durable' ? 'durable' : 'completed'));
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
  await page.locator('.crump-code-diff-file').nth(1).click();
  assert.equal(await page.locator('.crump-code-diff-viewer strong').textContent(), 'tests/retry.test.js');
  await page.locator('.crump-code-check').first().click();
  assert.match(await page.locator('.crump-code-check pre').textContent(), /1 passed/);
  assert.deepEqual(errors, []);
  await context.close();
  return initial;
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

(async () => {
  const {server, port} = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const baseUrl = `http://127.0.0.1:${port}`;
    const desktop = await inspectCompleted(browser, baseUrl, {width: 1280, height: 760});
    const phone = await inspectCompleted(browser, baseUrl, {width: 390, height: 844});
    const durable = await inspectDurableRecovery(browser, baseUrl);
    process.stdout.write(JSON.stringify({desktop, phone, durable}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
