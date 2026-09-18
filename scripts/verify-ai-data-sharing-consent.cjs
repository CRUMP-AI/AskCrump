const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless:true, ...(executablePath ? {executablePath} : {})});
  try {
    const page = await browser.newPage({viewport:{width:390, height:844}});
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765/tests/fixtures/ai-data-sharing-consent.html', {waitUntil:'load'});
    await page.waitForFunction(() => Boolean(window.CrumpAIDataSharingConsent));

    const routeMatrix = await page.evaluate(() => {
      const matcher = window.CrumpAIDataSharingConsent.isProviderBoundAction;
      const serverMatcher = window.CrumpAIDataSharingConsent.isServerAuthoritativeConsentAction;
      const guarded = [
        '/api/chat',
        '/api/voice/synthesize',
        '/api/media/video',
        '/api/media/video/job-1/continue',
        '/api/code/tasks/task-1/run',
        '/api/manuscripts/manuscript-1/blueprint',
        '/api/manuscripts/manuscript-1/draft-next',
        '/api/manuscripts/manuscript-1/sections/section-1/draft',
      ];
      const serverAuthoritative = [
        '/api/manuscripts/manuscript-1/runs',
        '/api/manuscript-runs/run-1/resume',
      ];
      return {
        guarded: guarded.map(path => matcher(path, {method:'POST'})),
        serverAuthoritative: serverAuthoritative.map(path => serverMatcher(path, {method:'POST'})),
        approvedRetry: serverMatcher('/api/code/tasks/task-1/approvals/approval-1', {
          method:'POST',
          body:JSON.stringify({decision:' APPROVED '}),
        }),
        deniedRetry: serverMatcher('/api/code/tasks/task-1/approvals/approval-1', {
          method:'POST',
          body:JSON.stringify({decision:'denied'}),
        }),
        taskCreation: matcher('/api/projects/project-1/code/tasks', {
          method:'POST',
          body:JSON.stringify({objective:'Save only'}),
        }),
        trailingSlash: matcher('/api/chat/?fixture=1', {method:'POST'}),
        polling: matcher('/api/media/video/job-1', {method:'GET'}),
        accountPost: matcher('/api/account/ai-data-sharing-consent', {method:'POST'}),
      };
    });
    assert.deepEqual(routeMatrix.guarded, Array(8).fill(true));
    assert.deepEqual(routeMatrix.serverAuthoritative, Array(2).fill(true));
    assert.equal(routeMatrix.approvedRetry, true);
    assert.equal(routeMatrix.deniedRetry, true);
    assert.equal(routeMatrix.taskCreation, false);
    assert.equal(routeMatrix.trailingSlash, true);
    assert.equal(routeMatrix.polling, false);
    assert.equal(routeMatrix.accountPost, false);

    await page.evaluate(() => {
      window.__fixture.firstRequest = window.fetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:'fixture prompt'}),
      }).then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    await page.waitForTimeout(75);
    let evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.providerRequests, 0, 'provider request escaped before a decision');
    assert.equal(evidence.consentPosts, 0, 'opening the modal must not imply permission');

    await page.click('#aiConsentAllow');
    const allowed = await page.evaluate(() => window.__fixture.firstRequest);
    assert.equal(allowed.status, 200);
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.consentPosts, 1);
    assert.equal(evidence.providerRequests, 1);
    assert.equal(await page.locator('#aiDataSharingConsentStatus').textContent(), 'Allowed');

    await page.click('#aiDataSharingConsentBtn');
    await page.waitForSelector('#aiConsentReviewActions:not([hidden])');
    await page.click('#aiConsentWithdraw');
    await page.waitForFunction(() => window.__fixture.consentDeletes === 1);
    await page.waitForFunction(() => document.querySelector('#aiDataSharingConsentModal')?.hidden === true);
    const revokedUser = await page.evaluate(() => ({...window.currentUser}));
    assert.equal(revokedUser.aiDataSharingConsentVersion, '2026-09-17');
    assert.ok(revokedUser.aiDataSharingConsentAt);
    assert.ok(revokedUser.aiDataSharingConsentRevokedAt);
    assert.equal(await page.locator('#aiDataSharingConsentStatus').textContent(), 'Not allowed');

    const exportOnly = await page.evaluate(async () => {
      const response = await window.fetch('/api/manuscripts/export-only/runs', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mode:'autopilot'}),
      });
      return {status:response.status, body:await response.json()};
    });
    assert.equal(exportOnly.status, 200);
    assert.equal(exportOnly.body.run.stage, 'export');
    assert.equal(await page.locator('#aiDataSharingConsentModal:not([hidden])').count(), 0);
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.conditionalRequests, 1, 'export-only work must reach the first-party stage check');
    assert.equal(evidence.consentPosts, 1, 'export-only work must not request AI permission');

    await page.evaluate(() => {
      window.__fixture.conditionalStart = window.fetch(
        '/api/manuscripts/provider-start/runs',
        {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({mode:'outline'}),
        },
      ).then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.conditionalRequests, 2, 'provider manuscript start must ask the first-party server which stage is next');
    await page.click('#aiConsentAllow');
    const conditionalStart = await page.evaluate(() => window.__fixture.conditionalStart);
    assert.equal(conditionalStart.status, 200);
    assert.equal(conditionalStart.body.run.stage, 'blueprint');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.conditionalRequests, 3, 'allowed provider manuscript start must retry exactly once');
    assert.equal(evidence.consentPosts, 2);

    await page.click('#aiDataSharingConsentBtn');
    await page.waitForSelector('#aiConsentReviewActions:not([hidden])');
    await page.click('#aiConsentWithdraw');
    await page.waitForFunction(() => window.__fixture.consentDeletes === 2);
    await page.waitForFunction(() => document.querySelector('#aiDataSharingConsentModal')?.hidden === true);

    await page.evaluate(() => {
      window.__fixture.conditionalResume = window.fetch(
        '/api/manuscript-runs/provider-resume/resume',
        {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'},
      ).then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.conditionalRequests, 4, 'provider resume must ask the server which stage is next');
    await page.click('#aiConsentAllow');
    const conditionalResume = await page.evaluate(() => window.__fixture.conditionalResume);
    assert.equal(conditionalResume.status, 200);
    assert.equal(conditionalResume.body.run.stage, 'drafting');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.conditionalRequests, 5, 'allowed provider resume must retry exactly once');
    assert.equal(evidence.consentPosts, 3);

    await page.evaluate(() => {
      window.__fixture.forceServerConsent428 = true;
      window.__fixture.crossDeviceRequest = window.fetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:'recover after another device withdrew'}),
      }).then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.providerEndpointRequests, 2);
    assert.equal(evidence.providerRequests, 1, 'authoritative 428 must occur before provider work');
    await page.click('#aiConsentAllow');
    const crossDevice = await page.evaluate(() => window.__fixture.crossDeviceRequest);
    assert.equal(crossDevice.status, 200);
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.providerEndpointRequests, 3, 'cross-device recovery must retry once');
    assert.equal(evidence.providerRequests, 2);
    assert.equal(evidence.consentPosts, 4);
    const crossDeviceRecovered = evidence.providerEndpointRequests === 3;

    await page.evaluate(() => {
      window.__fixture.forceServerConsent428 = true;
      window.__fixture.serverDeclinedRequest = window.fetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:'decline after an authoritative permission change'}),
      }).then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.providerEndpointRequests, 4);
    await page.click('#aiConsentNotNow');
    const serverDeclined = await page.evaluate(() => window.__fixture.serverDeclinedRequest);
    assert.equal(serverDeclined.status, 428);
    assert.equal(serverDeclined.body.code, 'AI_DATA_SHARING_CONSENT_REQUIRED');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.providerEndpointRequests, 4, 'Not now after server 428 must not replay');
    assert.equal(evidence.consentPosts, 4, 'Not now after server 428 must not POST consent');

    await page.evaluate(() => {
      window.__fixture.declinedRequest = window.fetch('/api/media/video', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({prompt:'fixture video'}),
      }).then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    await page.click('#aiConsentNotNow');
    const declined = await page.evaluate(() => window.__fixture.declinedRequest);
    assert.equal(declined.status, 428);
    assert.equal(declined.body.code, 'AI_DATA_SHARING_CONSENT_REQUIRED');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.consentPosts, 4, 'Not now must not POST consent');
    assert.equal(evidence.providerRequests, 2, 'Not now must not send the provider request');

    await page.evaluate(() => {
      const approvalBody = JSON.stringify({decision:'approved', nonce:'preserve-body-1'});
      window.__fixture.expectedApprovalBody = approvalBody;
      const request = new Request(
        new URL('/api/code/tasks/task-1/approvals/always-428', location.href),
        {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:approvalBody,
        },
      );
      window.__fixture.requestObjectApproval = window.fetch(request)
        .then(async response => ({status:response.status, body:await response.json()}));
    });
    await page.waitForSelector('#aiDataSharingConsentModal:not([hidden])');
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.codeApprovalRequests, 1, 'Request-object approval must reach only the first-party consent check');
    await page.click('#aiConsentAllow');
    const requestObjectApproval = await page.evaluate(() => window.__fixture.requestObjectApproval);
    assert.equal(requestObjectApproval.status, 428);
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.codeApprovalRequests, 2, 'consecutive 428 responses must stop after one Request-object replay');
    assert.equal(evidence.consentPosts, 5);
    assert.deepEqual(
      evidence.codeApprovalBodies,
      [evidence.expectedApprovalBody, evidence.expectedApprovalBody],
      'Request-object replay must preserve the exact JSON body bytes',
    );

    const getStatus = await page.evaluate(async () => {
      const response = await window.fetch('/api/media/video/job-fixture');
      return response.status;
    });
    assert.equal(getStatus, 200);
    evidence = await page.evaluate(() => ({...window.__fixture}));
    assert.equal(evidence.getRequests, 1, 'GET polling must remain outside the permission gate');

    const modalText = await page.locator('#aiDataSharingConsentModal').textContent();
    for (const provider of ['Anthropic', 'OpenAI', 'Vercel AI Gateway and Groq', 'Google Gemini and Veo', 'Runway', 'ElevenLabs', 'Brave Search', 'OpenWeather', 'Vercel Sandbox']) {
      assert.ok(modalText.includes(provider));
    }
    assert.ok(modalText.includes('Nothing is sent until you choose Allow and continue.'));
    assert.ok(modalText.includes('does not undo processing already completed at your direction.'));
    assert.equal(await page.locator('a[href="/legal.html#ai-data-sharing"]').count(), 1);
    assert.deepEqual(errors, []);
    process.stdout.write(JSON.stringify({
      pausedBeforeAllow:true,
      consentPosts:evidence.consentPosts,
      consentDeletes:evidence.consentDeletes,
      providerRequests:evidence.providerRequests,
      declineStatus:declined.status,
      getRequests:evidence.getRequests,
      guardedRoutes:routeMatrix.guarded.length
        + routeMatrix.serverAuthoritative.length
        + Number(routeMatrix.approvedRetry),
      conditionalRequests:evidence.conditionalRequests,
      crossDeviceRecovered,
      serverDeclineDidNotReplay:evidence.providerEndpointRequests === 4,
      manuscriptStartRecovered:evidence.conditionalRequests === 5,
      requestObjectReplayBounded:evidence.codeApprovalRequests === 2,
      requestObjectBodyPreserved:evidence.codeApprovalBodies.every(body => body === evidence.expectedApprovalBody),
      errors,
    }));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
