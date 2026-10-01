const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {existsSync} = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const localPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const pythonExecutable = process.env.ASKCRUMP_PYTHON
  || (existsSync(localPython) ? localPython : (process.platform === 'win32' ? 'python' : 'python3'));
const serverScript = path.join(root, 'scripts', 'serve-conversational-document-delivery-fixture.py');
const readyPrefix = 'ASKCRUMP_DOCUMENT_FIXTURE_READY=';
const owner = 'fixture-owner';
const otherOwner = 'fixture-other-owner';

function startFixtureServer() {
  return new Promise((resolve, reject) => {
    const safeEnvironment = {};
    for (const key of [
      'PATH', 'Path', 'PATHEXT', 'SystemRoot', 'SYSTEMROOT', 'WINDIR',
      'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'VIRTUAL_ENV',
    ]) {
      if (process.env[key]) safeEnvironment[key] = process.env[key];
    }
    const child = spawn(pythonExecutable, [serverScript], {
      cwd: root,
      env: {
        ...safeEnvironment,
        APP_ENV: 'test',
        APP_URL: 'http://127.0.0.1',
        COOKIE_SECURE: 'false',
        SUPABASE_URL: 'http://127.0.0.1:9',
        SUPABASE_SERVICE_KEY: 'fixture-service-key',
        NO_PROXY: '*',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    let settled = false;
    let timeout = null;
    const rejectStart = (error, {stop = false} = {}) => {
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      if (!stop) {
        reject(error);
        return;
      }
      void stopFixtureServer(child).then(
        () => reject(error),
        cleanupError => reject(new Error(`${error.message}\nFixture cleanup failed: ${cleanupError.message}`)),
      );
    };
    timeout = setTimeout(() => {
      rejectStart(new Error(`FastAPI fixture did not become ready.\n${stderr || stdout}`), {stop: true});
    }, 20_000);

    const inspect = () => {
      const line = stdout.split(/\r?\n/).find(value => value.startsWith(readyPrefix));
      if (!line || settled) return;
      const baseUrl = line.slice(readyPrefix.length).trim();
      if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(baseUrl)) {
        rejectStart(new Error(`FastAPI fixture emitted an invalid readiness URL: ${baseUrl}`), {stop: true});
        return;
      }
      settled = true;
      clearTimeout(timeout);
      resolve({child, baseUrl, logs: () => ({stdout, stderr})});
    };

    child.stdout.on('data', chunk => {
      stdout = `${stdout}${chunk}`.slice(-24_000);
      inspect();
    });
    child.stderr.on('data', chunk => {
      stderr = `${stderr}${chunk}`.slice(-24_000);
    });
    child.once('error', error => {
      rejectStart(new Error(`FastAPI fixture could not start: ${error.message}`));
    });
    child.once('exit', code => {
      rejectStart(new Error(`FastAPI fixture exited with ${code}.\n${stderr || stdout}`));
    });
  });
}

function waitForExit(child, timeoutMs) {
  return new Promise(resolve => {
    if (!child || child.exitCode !== null || child.signalCode !== null) return resolve(true);
    const timeout = setTimeout(() => {
      child.removeListener('exit', exited);
      resolve(false);
    }, timeoutMs);
    const exited = () => {
      clearTimeout(timeout);
      resolve(true);
    };
    child.once('exit', exited);
  });
}

async function stopFixtureServer(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  child.kill();
  if (await waitForExit(child, 5_000)) return;
  child.kill('SIGKILL');
  if (!await waitForExit(child, 5_000)) {
    throw new Error(`FastAPI fixture process ${child.pid} did not stop.`);
  }
}

(async () => {
  const fixture = await startFixtureServer();
  let browser = null;
  let signalCleanupStarted = false;
  const terminateFixtureOnSignal = async exitCode => {
    if (signalCleanupStarted) return;
    signalCleanupStarted = true;
    const cleanup = [stopFixtureServer(fixture.child)];
    if (browser) cleanup.push(browser.close());
    await Promise.allSettled(cleanup);
    process.exit(exitCode);
  };
  const handleSigint = () => { void terminateFixtureOnSignal(130); };
  const handleSigterm = () => { void terminateFixtureOnSignal(143); };
  process.once('SIGINT', handleSigint);
  process.once('SIGTERM', handleSigterm);
  const requestedExecutable = process.env.ASKCRUMP_BROWSER_EXECUTABLE
    || process.env.ASK_CRUMP_BROWSER_PATH
    || process.env.CODEX_BROWSER_EXECUTABLE
    || '';
  const browserErrors = [];
  const blockedRequests = [];
  const chatRequests = [];

  try {
    browser = await chromium.launch({
      headless: true,
      ...(requestedExecutable ? {executablePath: requestedExecutable} : {}),
    });
    const context = await browser.newContext({
      viewport: {width: 1280, height: 820},
      acceptDownloads: true,
    });
    await context.addCookies([{
      name: 'fixture_owner',
      value: owner,
      url: fixture.baseUrl,
      sameSite: 'Lax',
    }]);
    const page = await context.newPage();
    const fixtureOrigin = new URL(fixture.baseUrl).origin;
    const recordBlockedRequest = requestUrl => {
      if (!blockedRequests.includes(requestUrl.href)) blockedRequests.push(requestUrl.href);
    };
    const guardLoopbackRequest = async route => {
      const requestUrl = new URL(route.request().url());
      if (requestUrl.protocol === 'http:' && requestUrl.origin === fixtureOrigin) {
        await route.continue();
        return;
      }
      recordBlockedRequest(requestUrl);
      await route.abort();
    };
    await page.route('**/*', guardLoopbackRequest);
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });
    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('request', request => {
      const requestUrl = new URL(request.url());
      if (requestUrl.protocol !== 'http:' || requestUrl.origin !== fixtureOrigin) {
        recordBlockedRequest(requestUrl);
      }
      if (request.method() === 'POST' && requestUrl.pathname === '/api/chat') {
        chatRequests.push(request.postDataJSON());
      }
    });

    await page.goto(`${fixture.baseUrl}/fixture`, {waitUntil: 'networkidle'});
    await page.waitForFunction(() => typeof window.CrumpDocumentStudio?.open === 'function');
    await page.getByRole('button', {name: 'Create document'}).click();
    const wordChoice = page.locator('.crump50-format-grid button').filter({hasText: 'Word'});
    await wordChoice.waitFor({state: 'visible'});
    await wordChoice.click();
    await page.locator('#userInput').fill('Write a decision memo and deliver it as a Word document.');

    const chatResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url());
      return response.request().method() === 'POST' && url.pathname === '/api/chat';
    });
    await page.locator('#sendButton').click();
    const chatResponse = await chatResponsePromise;
    assert.equal(chatResponse.status(), 200);
    const chatBody = await chatResponse.json();
    assert.equal(chatBody.success, true);
    assert.equal(chatBody.artifact?.format, 'docx');
    assert.equal(chatRequests.length, 1);
    assert.equal(chatRequests[0].artifactFormat, 'docx');
    assert.equal(chatRequests[0].message, 'Write a decision memo and deliver it as a Word document.');

    const artifactCard = page.locator('#chatContainer .crump50-artifact').filter({hasText: 'DOCX'});
    await artifactCard.waitFor({state: 'visible'});
    assert.equal(await artifactCard.locator('[data-artifact-open]').count(), 1);
    assert.equal(await artifactCard.locator('[data-artifact-download]').count(), 1);
    assert.equal(await artifactCard.locator('[data-artifact-project]').count(), 1);

    const listing = await context.request.get(`${fixture.baseUrl}/api/files`);
    assert.equal(listing.status(), 200);
    const listedFiles = (await listing.json()).files;
    assert.equal(listedFiles.length, 1);
    assert.equal(listedFiles[0].id, chatBody.artifact.id);
    assert.equal(listedFiles[0].type, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');

    const contentPath = `/api/files/${encodeURIComponent(chatBody.artifact.id)}/content?download=1`;
    // Playwright cancels streamed downloads that remain under route interception on Windows.
    // Remove the guard only for this exact, asserted loopback handoff, then restore it immediately.
    await page.unroute('**/*', guardLoopbackRequest);
    const downloadPromise = page.waitForEvent('download');
    await artifactCard.locator('[data-artifact-download]').click();
    const browserDownload = await downloadPromise;
    assert.equal(browserDownload.url(), `${fixture.baseUrl}${contentPath}`);
    assert.equal(browserDownload.suggestedFilename(), chatBody.artifact.name);
    const browserDownloadFailure = await browserDownload.failure();
    if (browserDownloadFailure) {
      const failedDownloadState = await context.request.get(`${fixture.baseUrl}/fixture-state`);
      throw new Error(
        `Browser download failed: ${browserDownloadFailure}; fixture state: ${await failedDownloadState.text()}`,
      );
    }
    const downloadStream = await browserDownload.createReadStream();
    const browserDownloadChunks = [];
    for await (const chunk of downloadStream) browserDownloadChunks.push(chunk);
    const browserDownloadedBytes = Buffer.concat(browserDownloadChunks);
    assert.equal(browserDownloadedBytes.subarray(0, 2).toString('ascii'), 'PK');
    assert.ok(browserDownloadedBytes.includes(Buffer.from('word/document.xml')));
    await page.waitForFunction(() => window.__fixture.downloadLinks.length === 1);
    const downloadLink = await page.evaluate(() => window.__fixture.downloadLinks[0]);
    assert.deepEqual(downloadLink, {
      href: contentPath,
      target: '_self',
      download: chatBody.artifact.name,
    });
    await page.route('**/*', guardLoopbackRequest);

    const downloadResponse = await context.request.get(`${fixture.baseUrl}${contentPath}`);
    assert.equal(downloadResponse.status(), 200);
    assert.equal(
      downloadResponse.headers()['content-type'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    );
    assert.match(downloadResponse.headers()['content-disposition'] || '', /^attachment; filename=".+\.docx"$/i);
    const downloadedBytes = await downloadResponse.body();
    assert.deepEqual(downloadedBytes, browserDownloadedBytes);

    const retry = await page.evaluate(async payload => {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      return {status: response.status, body: await response.json()};
    }, chatRequests[0]);
    assert.equal(retry.status, 200);
    assert.equal(retry.body.cached, true);
    assert.equal(retry.body.artifact.id, chatBody.artifact.id);
    const afterRetryListing = await context.request.get(`${fixture.baseUrl}/api/files`);
    assert.equal((await afterRetryListing.json()).files.length, 1);

    await page.reload({waitUntil: 'networkidle'});
    await page.waitForFunction(() => typeof window.CrumpChatTransport?.send === 'function');
    const reconciled = await page.evaluate(async payload => {
      const data = await window.CrumpChatTransport.send(payload);
      window.chats[0].messages = [{
        id: payload.messageId,
        role: 'user',
        content: payload.message,
      }, data.assistantMessage];
      window.renderMessages(window.chats[0].messages);
      return data;
    }, chatRequests[0]);
    assert.equal(reconciled.cached, true);
    assert.equal(reconciled.artifact.id, chatBody.artifact.id);
    await page.locator('#chatContainer .crump50-artifact').filter({hasText: 'DOCX'}).waitFor({state: 'visible'});

    const unauthenticated = await browser.newContext();
    const unauthenticatedContent = await unauthenticated.request.get(`${fixture.baseUrl}${contentPath}`);
    assert.equal(unauthenticatedContent.status(), 401);
    await unauthenticated.close();

    const otherContext = await browser.newContext();
    await otherContext.addCookies([{
      name: 'fixture_owner',
      value: otherOwner,
      url: fixture.baseUrl,
      sameSite: 'Lax',
    }]);
    const otherContent = await otherContext.request.get(`${fixture.baseUrl}${contentPath}`);
    assert.equal(otherContent.status(), 404);
    const otherListing = await otherContext.request.get(`${fixture.baseUrl}/api/files`);
    assert.equal(otherListing.status(), 200);
    assert.deepEqual((await otherListing.json()).files, []);
    await otherContext.close();

    const fixtureStateResponse = await context.request.get(`${fixture.baseUrl}/fixture-state`);
    assert.equal(fixtureStateResponse.status(), 200);
    const fixtureState = await fixtureStateResponse.json();
    assert.equal(fixtureState.files.length, 1);
    assert.equal(fixtureState.jobs, 1);
    assert.deepEqual(fixtureState.jobStatuses, ['completed']);
    assert.equal(fixtureState.activeClaims, 0);
    const contentRequestPath = contentPath.split('?')[0];
    const contentAttemptIdentities = fixtureState.authAttempts
      .filter(([requestPath]) => requestPath === contentRequestPath)
      .map(([, identity]) => identity);
    assert.deepEqual(contentAttemptIdentities, [owner, owner, null, otherOwner]);
    assert.ok(fixtureState.events.some(([eventName]) => eventName === 'ArtifactPackaged'));
    assert.ok(fixtureState.events.some(([eventName]) => eventName === 'ArtifactDownloaded'));
    assert.deepEqual(blockedRequests, []);
    assert.deepEqual(browserErrors, []);
    await context.close();

    process.stdout.write(`${JSON.stringify({
      fileName: chatBody.artifact.name,
      cachedRetry: retry.body.cached,
      cachedRerender: reconciled.cached,
      ownerFiles: fixtureState.files.length,
      blockedRequests,
      browserErrors,
    })}\n`);
  } catch (error) {
    const logs = fixture.logs();
    error.message = `${error.message}\nFixture stdout:\n${logs.stdout}\nFixture stderr:\n${logs.stderr}`;
    throw error;
  } finally {
    process.removeListener('SIGINT', handleSigint);
    process.removeListener('SIGTERM', handleSigterm);
    if (browser) {
      try {
        await browser.close();
      } finally {
        await stopFixtureServer(fixture.child);
      }
    } else {
      await stopFixtureServer(fixture.child);
    }
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
