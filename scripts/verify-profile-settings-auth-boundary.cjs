const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const root = path.resolve(__dirname, '..');
const contentTypes = Object.freeze({
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
});

function safePath(pathname) {
  const resolved = path.resolve(root, pathname.replace(/^\/+/, ''));
  return resolved.startsWith(`${root}${path.sep}`) ? resolved : null;
}

async function startServer() {
  const server = createServer(async (request, response) => {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const filePath = safePath(url.pathname);
    if (!filePath) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, {
        'Content-Type': contentTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
        'Cache-Control': 'no-store',
      });
      response.end(body);
    } catch (_) {
      response.writeHead(404);
      response.end('Not found');
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return {server, port: server.address().port};
}

(async () => {
  const fixture = await startServer();
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(
      `http://127.0.0.1:${fixture.port}/tests/fixtures/profile-settings-auth-boundary.html`,
      {waitUntil: 'load'},
    );
    await page.waitForFunction(() => window.__fixture.pendingIdentityCount() > 0);
    await page.evaluate(() => window.__fixture.identityResolve({
      success: true,
      authenticated: true,
      data: {
        user: {
          id: window.__fixture.ownerA,
          fullName: 'Alice Session Cache',
          subscriptionTier: 'free',
          termsAcceptedAt: '2026-10-24T00:00:00Z',
        },
        settings: {},
      },
    }));
    await page.waitForFunction(() => window.__fixture.initializeAppCalls === 1);
    const ownerAProfileBaseline = await page.evaluate(() => (
      localStorage.getItem(`crump_user_profile_v4:${window.__fixture.ownerA}`)
    ));

    await page.evaluate(() => window.__fixture.begin());
    await page.waitForFunction(() => (
      document.getElementById('saveSettingsBtn')?.dataset.settingsSaving === 'true'
      && document.getElementById('devicesModal')
      && document.getElementById('deleteAccountModal')
    ));
    const ownerABeforeSwitch = await page.evaluate(() => ({
      modalOpen: document.getElementById('settingsModal').getAttribute('aria-hidden'),
      name: document.getElementById('settingsName').value,
      assistant: document.getElementById('assistantName').value,
      backgroundInert: document.getElementById('appContainer').hasAttribute('inert'),
      profileRequest: window.__fixture.fetchCalls.some(call => (
        call.path === '/api/account/profile' && call.ownerClaim === window.__fixture.ownerA
      )),
      devicesRequest: window.__fixture.fetchCalls.some(call => (
        call.path === '/api/auth/devices' && call.ownerClaim === window.__fixture.ownerA
      )),
      presenceRequest: window.__fixture.fetchCalls.some(call => (
        call.path === '/api/presence/preferences'
        && call.method === 'PATCH'
        && call.ownerClaim === window.__fixture.ownerA
      )),
      onboardingProfileRequest: window.__fixture.fetchCalls.some(call => (
        call.path === '/api/account/profile'
        && call.fullName === 'Alice Onboarding Pending'
        && call.ownerClaim === window.__fixture.ownerA
      )),
    }));
    assert.deepEqual(ownerABeforeSwitch, {
      modalOpen: 'false',
      name: 'Alice Dirty Draft',
      assistant: 'Alice Draft Assistant',
      backgroundInert: true,
      profileRequest: true,
      devicesRequest: true,
      presenceRequest: true,
      onboardingProfileRequest: true,
    });

    await page.evaluate(() => window.__fixture.switchToOwnerB());
    const scrubbed = await page.evaluate(() => ({
      currentUser: window.currentUser,
      modalHidden: document.getElementById('settingsModal').getAttribute('aria-hidden'),
      modalDisplay: document.getElementById('settingsModal').style.display,
      settingsName: document.getElementById('settingsName').value,
      settingsEmail: document.getElementById('settingsEmail').value,
      assistantName: document.getElementById('assistantName').value,
      backgroundInert: document.getElementById('appContainer').hasAttribute('inert'),
      devicesPresent: Boolean(document.getElementById('devicesModal')),
      deletePresent: Boolean(document.getElementById('deleteAccountModal')),
      profileTab: document.querySelector('[data-v1-settings-tab].is-active')?.dataset.v1SettingsTab,
      profilePanel: document.querySelector('[data-v1-settings-panel].is-active')?.dataset.v1SettingsPanel,
      saveBusy: document.getElementById('saveSettingsBtn').hasAttribute('aria-busy'),
      scrubProfileWrites: window.__fixture.scrubWrites.filter(entry => (
        entry.key.startsWith('crump_user_profile_v4:')
      )),
      manager: {
        ownerId: window.profileManager.ownerId,
        profile: window.profileManager.getProfile(),
      },
      assistantLabel: document.querySelector('.assistant-name').textContent,
      greeting: document.getElementById('v1Greeting').textContent,
      initializeAppCalls: window.__fixture.initializeAppCalls,
      refusedRequests: window.__fixture.refusedRequests.map(call => ({
        path: call.path,
        method: call.method,
        ownerClaim: call.ownerClaim,
        serverOwner: call.serverOwner,
      })),
      serverMutations: window.__fixture.serverMutations,
      onboardingModalDisplay: document.getElementById('onboardingModal').style.display,
      onboardingName: document.getElementById('onboardingName').value,
      onboardingBusy: document.getElementById('onboardingContinueBtn').hasAttribute('aria-busy'),
      bPresenceRequest: window.__fixture.fetchCalls.some(call => (
        call.path === '/api/presence/preferences'
        && call.method === 'GET'
        && call.ownerClaim === window.__fixture.ownerB
      )),
    }));
    assert.equal(scrubbed.currentUser.id, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    assert.equal(scrubbed.modalHidden, 'true');
    assert.equal(scrubbed.modalDisplay, 'none');
    assert.equal(scrubbed.settingsName, '');
    assert.equal(scrubbed.settingsEmail, '');
    assert.equal(scrubbed.assistantName, '');
    assert.equal(scrubbed.backgroundInert, false);
    assert.equal(scrubbed.devicesPresent, false);
    assert.equal(scrubbed.deletePresent, false);
    assert.equal(scrubbed.profileTab, 'profile');
    assert.equal(scrubbed.profilePanel, 'profile');
    assert.equal(scrubbed.saveBusy, false);
    assert.deepEqual(scrubbed.scrubProfileWrites, []);
    assert.equal(scrubbed.manager.ownerId, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    assert.equal(scrubbed.manager.profile.name, 'Bob Cached');
    assert.equal(scrubbed.manager.profile.email, 'bob@example.test');
    assert.equal(scrubbed.assistantLabel, 'Bravo');
    assert.equal(scrubbed.greeting.includes('Alice'), false);
    assert.equal(scrubbed.initializeAppCalls, 1);
    assert.ok(scrubbed.refusedRequests.some(call => (
      call.path === '/api/account'
      && call.method === 'DELETE'
      && call.ownerClaim === '11111111-1111-4111-8111-111111111111'
      && call.serverOwner === 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    )));
    assert.ok(scrubbed.refusedRequests.some(call => (
      call.path === '/api/presence/preferences'
      && call.method === 'PATCH'
      && call.ownerClaim === '11111111-1111-4111-8111-111111111111'
      && call.serverOwner === 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    )));
    assert.ok(scrubbed.refusedRequests.some(call => (
      call.path === '/api/auth/devices'
      && call.method === 'GET'
      && call.ownerClaim === '11111111-1111-4111-8111-111111111111'
      && call.serverOwner === 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    )));
    assert.deepEqual(scrubbed.serverMutations, []);
    assert.equal(scrubbed.onboardingModalDisplay, 'none');
    assert.equal(scrubbed.onboardingName, '');
    assert.equal(scrubbed.onboardingBusy, false);
    assert.equal(scrubbed.bPresenceRequest, true);

    await page.evaluate(() => window.__fixture.releaseStaleWork());
    const staleResult = await page.evaluate(() => ({
      currentUser: window.currentUser,
      manager: window.profileManager.getProfile(),
      aProfile: localStorage.getItem(`crump_user_profile_v4:${window.__fixture.ownerA}`),
      bProfile: localStorage.getItem(`crump_user_profile_v4:${window.__fixture.ownerB}`),
      visibleText: document.body.innerText,
      devicesPresent: Boolean(document.getElementById('devicesModal')),
      deletePresent: Boolean(document.getElementById('deleteAccountModal')),
      deleteCalls: window.__fixture.deleteCalls,
      clearLocalStateCalls: window.__fixture.clearLocalStateCalls,
      toasts: window.__fixture.toasts,
      abortedRequests: window.__fixture.abortedRequests,
      presence: window.CrumpPresence.preferences,
      serverMutations: window.__fixture.serverMutations,
      identityCache: localStorage.getItem('crump_user_cache_v4'),
      bOnboarded: localStorage.getItem(`crump_has_onboarded:${window.__fixture.ownerB}`),
      onboardingName: document.getElementById('onboardingName').value,
    }));
    assert.equal(staleResult.currentUser.id, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    assert.equal(staleResult.manager.name, 'Bob Cached');
    assert.equal(staleResult.manager.email, 'bob@example.test');
    assert.equal(staleResult.aProfile, ownerAProfileBaseline);
    assert.equal(staleResult.bProfile.includes('Alice'), false);
    assert.ok(staleResult.bProfile.includes('Bob Cached'));
    assert.equal(staleResult.visibleText.includes('Alice Private'), false);
    assert.equal(staleResult.visibleText.includes('Alice Dirty Draft'), false);
    assert.equal(staleResult.visibleText.includes('Alice Phone'), false);
    assert.equal(staleResult.devicesPresent, false);
    assert.equal(staleResult.deletePresent, false);
    assert.equal(staleResult.deleteCalls, 0);
    assert.equal(staleResult.clearLocalStateCalls, 0);
    assert.deepEqual(staleResult.toasts, []);
    assert.equal(staleResult.abortedRequests.profile, true);
    assert.equal(staleResult.abortedRequests.devices, true);
    assert.equal(staleResult.abortedRequests.presence, true);
    assert.equal(staleResult.abortedRequests.onboardingProfile, true);
    assert.equal(staleResult.presence.enabled, false);
    assert.deepEqual(staleResult.serverMutations, []);
    assert.ok(staleResult.identityCache.includes('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'));
    assert.equal(staleResult.identityCache.includes('Alice'), false);
    assert.equal(staleResult.bOnboarded, null);
    assert.equal(staleResult.onboardingName, '');

    await page.evaluate(() => window.openSettings());
    await page.waitForFunction(() => document.getElementById('settingsModal').getAttribute('aria-hidden') === 'false');
    await page.waitForFunction(() => document.activeElement?.id === 'settingsTitle');
    const ownerBSettings = await page.evaluate(() => ({
      name: document.getElementById('settingsName').value,
      email: document.getElementById('settingsEmail').value,
      assistant: document.getElementById('assistantName').value,
      visibleText: document.body.innerText,
      focusedId: document.activeElement?.id || '',
    }));
    assert.equal(ownerBSettings.name, 'Bob Cached');
    assert.equal(ownerBSettings.email, 'bob@example.test');
    assert.equal(ownerBSettings.assistant, 'Bravo');
    assert.equal(ownerBSettings.focusedId, 'settingsTitle');
    assert.equal(ownerBSettings.visibleText.includes('Alice Private'), false);
    assert.equal(ownerBSettings.visibleText.includes('Alice Dirty Draft'), false);

    const nativeDeleteCas = await page.evaluate(() => (
      window.__fixture.exerciseNativeDeleteTokenCas()
    ));
    assert.equal(nativeDeleteCas.token, 'owner-b-native-token');
    assert.equal(nativeDeleteCas.clearLocalStateDelta, 0);
    assert.equal(nativeDeleteCas.currentUser.id, '11111111-1111-4111-8111-111111111111');
    assert.equal(nativeDeleteCas.path, '/tests/fixtures/profile-settings-auth-boundary.html');

    const healthMismatch = await page.evaluate(() => (
      window.__fixture.exerciseMissedStorageHealthMismatch()
    ));
    assert.deepEqual(healthMismatch.result, {stale: true, reloading: true});
    assert.equal(healthMismatch.currentUser, null);
    assert.deepEqual(healthMismatch.chats, []);
    assert.equal(healthMismatch.currentChatId, null);
    assert.equal(healthMismatch.chatText, '');
    assert.ok(healthMismatch.identityCache.includes('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'));
    assert.ok(healthMismatch.identityCache.includes('Bob Cache Must Survive'));
    assert.equal(healthMismatch.clearLocalStateCalls, 0);
    assert.equal(healthMismatch.reloads, 1);
    assert.equal(healthMismatch.healthCall.path, '/api/auth/check-session');
    assert.equal(healthMismatch.healthCall.ownerClaim, '11111111-1111-4111-8111-111111111111');
    assert.equal(healthMismatch.healthCall.serverOwner, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    assert.equal(healthMismatch.healthCall.refused, true);
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({
      scrubbed: true,
      staleIdentityIgnored: true,
      staleSaveIgnored: true,
      stalePresenceIgnored: true,
      staleDevicesIgnored: true,
      staleDeleteIgnored: true,
      staleOnboardingIgnored: true,
      staleIdentityCacheIgnored: true,
      cookieSkewRefused: true,
      authControllerHandoff: true,
      nativeDeleteTokenCas: true,
      missedStorageHealthMismatchScrubbed: true,
      ownerBSettings: {
        name: ownerBSettings.name,
        email: ownerBSettings.email,
        assistant: ownerBSettings.assistant,
      },
      errors,
    }));
  } finally {
    await browser.close();
    await new Promise(resolve => fixture.server.close(resolve));
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
