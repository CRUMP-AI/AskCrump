'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const appHtml = fs.readFileSync(path.join(root, 'public', 'app.html'), 'utf8');
const start = appHtml.indexOf('<div id="settingsModal"');
const end = appHtml.indexOf('<div id="toastContainer"', start);
if (start < 0 || end < 0) throw new Error('Settings fixture boundary is missing.');
const settingsMarkup = appHtml.slice(start, end);

const ids = Object.freeze({
  owner: '00000000-0000-4000-8000-000000000001',
  connection: '00000000-0000-4000-8000-000000000002',
  task: '00000000-0000-4000-8000-000000000003',
  turn: '00000000-0000-4000-8000-000000000004',
  action: '00000000-0000-4000-8000-000000000005',
  approval: '00000000-0000-4000-8000-000000000006',
  schedule: '00000000-0000-4000-8000-000000000007',
  template: '00000000-0000-4000-8000-000000000008',
  chat: '00000000-0000-4000-8000-000000000009',
  flow: '00000000-0000-4000-8000-00000000000a',
  result: '00000000-0000-5000-8000-00000000000b',
  loop: '00000000-0000-4000-8000-00000000000c',
});
const sha = character => character.repeat(64);
const hashes = Object.freeze({
  approval: sha('a'),
  parameters: sha('b'),
  authorization: sha('c'),
  scopes: sha('d'),
  preview: sha('e'),
  resource: sha('f'),
});
const actions = Object.freeze([
  'mail.search', 'mail.get', 'mail.create_draft', 'mail.send', 'mail.reply',
  'calendar.list', 'calendar.get', 'calendar.free_busy',
  'calendar.create', 'calendar.update', 'calendar.cancel',
]);
const previewPayload = Object.freeze({
  account: 'founder@example.com',
  to: Object.freeze(['client@example.com']),
  cc: Object.freeze([]),
  bcc: Object.freeze([]),
  subject: 'Project update',
  bodyText: 'The exact draft Gregory reviewed.',
  replyContext: null,
});
const previewCanonical = JSON.stringify({
  version: 'connected-approval-preview-v1',
  approvalId: ids.approval,
  actionId: ids.action,
  action: 'mail.send',
  approvalBindingSha256: hashes.approval,
  parametersSha256: hashes.parameters,
  resourceVersionSha256: null,
  payload: previewPayload,
});
const displaySha256 = crypto.createHash('sha256').update(previewCanonical).digest('hex');
const calendarPreviewPayload = Object.freeze({
  calendar: 'work-calendar',
  eventContext: 'event-123',
  title: 'Client planning session',
  start: '2026-11-09T14:00:00-05:00',
  end: '2026-11-09T14:30:00-05:00',
  timeZone: 'America/New_York',
  attendees: Object.freeze([]),
  location: 'Online',
  description: 'Move the approved client session.',
});
const calendarPreviewCanonical = JSON.stringify({
  version: 'connected-approval-preview-v1',
  approvalId: ids.approval,
  actionId: ids.action,
  action: 'calendar.update',
  approvalBindingSha256: hashes.approval,
  parametersSha256: hashes.parameters,
  resourceVersionSha256: hashes.resource,
  payload: calendarPreviewPayload,
});
const calendarDisplaySha256 = crypto.createHash('sha256')
  .update(calendarPreviewCanonical)
  .digest('hex');

async function run() {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 900}});
  const consoleErrors = [];
  const capturedCalls = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', error => consoleErrors.push(error.message));
  await page.exposeFunction('__recordConnectedCall', call => { capturedCalls.push(call); });

  await page.route('https://www.askcrump.com/app', route => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: `<!doctype html><html data-theme="light"><body class="crump-v1-body"><main><div id="chatContainer"></div><textarea id="userInput"></textarea></main>${settingsMarkup}</body></html>`,
  }));
  await page.route('https://accounts.google.com/**', route => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: '<!doctype html><title>Google authorization handoff</title>',
  }));
  await page.goto('https://www.askcrump.com/app');
  await page.addStyleTag({path: path.join(root, 'public', 'connected-apps-ui.css')});
  await page.evaluate(({
    ids, hashes, actions, previewPayload, displaySha256,
    calendarPreviewPayload, calendarDisplaySha256,
  }) => {
    window.currentUser = {id: ids.owner};
    window.__ownerId = ids.owner;
    window.__authRevision = 0;
    window.__statusEnabled = true;
    window.__calendarApproval = false;
    window.__oauthDelayMs = 0;
    window.__calls = [];
    window.__scrub = null;
    window.__connectedScrub = null;
    window.chats = [{
      id: ids.chat,
      chat_id: ids.chat,
      title: 'Quarterly client follow-up',
      messages: [],
    }];
    window.closeSettings = () => {
      const modal = document.getElementById('settingsModal');
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    };
    let randomCounter = 16;
    Object.defineProperty(window.crypto, 'randomUUID', {
      configurable: true,
      value: () => `10000000-0000-4000-8000-${(randomCounter++).toString(16).padStart(12, '0')}`,
    });
    window.CrumpAuthBoundary = Object.freeze({
      authenticatedUserId: () => window.__ownerId,
      revision: () => window.__authRevision,
      register: (name, scrub) => {
        window.__scrub = scrub;
        if (name === 'connected-apps-ui') window.__connectedScrub = scrub;
        return () => {};
      },
    });
    window.confirm = () => true;

    const responseFor = (pathname, options, body) => {
      if (pathname.endsWith('/status')) return {
        success: true,
        enabled: window.__statusEnabled,
        status: window.__statusEnabled ? 'ready' : 'not_released',
        providers: window.__statusEnabled ? ['google', 'microsoft'] : [],
        capabilities: window.__statusEnabled
          ? {google: [...actions], microsoft: [...actions]} : [],
        oauthClientIds: window.__statusEnabled ? {
          google: 'google-client.apps.googleusercontent.com',
          microsoft: 'microsoft-client-id',
        } : {},
      };
      if (pathname.endsWith('/connections')) return {
        success: true,
        connections: [{
          connectionId: ids.connection,
          provider: 'google',
          resource: 'mail',
          accountKind: 'personal',
          authorizationState: 'active',
          authorizationRevision: 1,
          grantedActions: ['mail.search', 'mail.get'],
          expiresAt: null,
          updatedAt: '2026-11-07T20:00:00Z',
        }],
      };
      if (pathname.endsWith('/schedules')) return {
        success: true,
        schedules: [{
          scheduleId: ids.schedule,
          connectionId: ids.connection,
          taskId: ids.task,
          provider: 'google',
          resource: 'mail',
          action: 'mail.search',
          actionTemplateRef: ids.template,
          parametersSha256: hashes.parameters,
          taskStateRevision: 1,
          timeZone: 'America/New_York',
          cadenceSeconds: 3600,
          quietStart: '22:00',
          quietEnd: '07:00',
          requiresApprovalEveryRun: false,
          status: 'active',
          nextRunAt: '2026-11-07T21:00:00Z',
          updatedAt: '2026-11-07T20:00:00Z',
        }],
      };
      if (pathname.endsWith('/tasks')) return {
        success: true,
        tasks: [{
          loopId: ids.loop,
          chatId: ids.chat,
          turnId: ids.turn,
          status: 'active',
          currentStep: 2,
          maxSteps: 8,
          taskStateRevision: 4,
          pendingApprovalId: null,
          lastResultReferenceId: ids.result,
          expiresAt: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
          updatedAt: new Date(Date.now() - 60 * 1000).toISOString(),
        }],
      };
      if (pathname.endsWith('/approvals')) return {
        success: true,
        approvals: [window.__calendarApproval ? {
          approvalId: ids.approval,
          actionId: ids.action,
          connectionId: ids.connection,
          taskId: ids.task,
          turnId: ids.turn,
          provider: 'google',
          resource: 'calendar',
          action: 'calendar.update',
          authorizationRevision: 1,
          authorizationSnapshotSha256: hashes.authorization,
          grantedScopesSha256: hashes.scopes,
          policyVersion: 'connected-action-policy-v1',
          actionRevision: 3,
          status: 'pending',
          approvalBindingSha256: hashes.approval,
          parametersSha256: hashes.parameters,
          resourceVersionSha256: hashes.resource,
          previewSha256: hashes.preview,
          decisionId: null,
          expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
          decidedAt: null,
          reviewPreview: {
            version: 'connected-approval-preview-v1',
            approvalBindingSha256: hashes.approval,
            parametersSha256: hashes.parameters,
            previewSha256: hashes.preview,
            displaySha256: calendarDisplaySha256,
            payload: calendarPreviewPayload,
          },
        } : {
          approvalId: ids.approval,
          actionId: ids.action,
          connectionId: ids.connection,
          taskId: ids.task,
          turnId: ids.turn,
          provider: 'google',
          resource: 'mail',
          action: 'mail.send',
          authorizationRevision: 1,
          authorizationSnapshotSha256: hashes.authorization,
          grantedScopesSha256: hashes.scopes,
          policyVersion: 'connected-action-policy-v1',
          actionRevision: 3,
          status: 'pending',
          approvalBindingSha256: hashes.approval,
          parametersSha256: hashes.parameters,
          resourceVersionSha256: null,
          previewSha256: hashes.preview,
          decisionId: null,
          expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
          decidedAt: null,
          reviewPreview: {
            version: 'connected-approval-preview-v1',
            approvalBindingSha256: hashes.approval,
            parametersSha256: hashes.parameters,
            previewSha256: hashes.preview,
            displaySha256,
            payload: previewPayload,
          },
        }],
      };
      if (pathname.endsWith('/actions')) return {
        success: true,
        actions: [{
          actionId: ids.action,
          connectionId: ids.connection,
          taskId: ids.task,
          turnId: ids.turn,
          provider: 'google',
          resource: 'mail',
          action: 'mail.send',
          authorizationRevision: 1,
          authorizationSnapshotSha256: hashes.authorization,
          grantedScopesSha256: hashes.scopes,
          policyVersion: 'connected-action-policy-v1',
          actionRevision: 3,
          status: 'pending_approval',
          parametersSha256: hashes.parameters,
          resourceVersionSha256: null,
          updatedAt: '2026-11-07T20:00:00Z',
        }],
      };
      if (pathname.endsWith(`/results/${ids.result}`)) return {
        success: true,
        result: {
          version: 1,
          resultReferenceId: ids.result,
          actionId: ids.action,
          provider: 'google',
          resource: 'mail',
          action: 'mail.get',
          observedAt: '2026-11-07T20:00:00+00:00',
          expiresAt: '2026-11-14T20:00:00+00:00',
          items: [{
            kind: 'mail_message',
            messageId: 'provider-message-1',
            threadId: null,
            receivedAt: '2026-11-07T19:55:00+00:00',
            subject: '<img src=x onerror="window.__unsafeRendered=true"> Project update',
            subjectTruncated: false,
            sender: 'sender@example.com',
            recipients: ['owner@example.com'],
            bodyText: '<script>window.__unsafeRendered=true</script>Untrusted mail body',
            bodyTruncated: false,
            attachmentCount: 0,
            trustBoundary: 'untrusted_external_data',
          }],
          itemCount: 1,
          itemsTruncated: false,
          trustBoundary: 'untrusted_external_data',
        },
      };
      if (pathname.includes('/approvals/') && options.method === 'POST') {
        return {success: true, approval: {status: 'approved'}};
      }
      if (pathname.endsWith(`/tasks/${ids.loop}/cancel`) && options.method === 'POST') {
        return {success: true, task: {loopId: ids.loop, status: 'cancelled'}};
      }
      if (pathname.endsWith('/oauth/start') && options.method === 'POST') {
        const query = new URLSearchParams({
          client_id: 'google-client.apps.googleusercontent.com',
          redirect_uri: 'https://www.askcrump.com/api/connected-apps/oauth/callback/google',
          response_type: 'code',
          scope: [
            'email',
            'https://www.googleapis.com/auth/gmail.compose',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'openid',
          ].join(' '),
          state: 's'.repeat(43),
          code_challenge: 'c'.repeat(43),
          code_challenge_method: 'S256',
          access_type: 'offline',
          include_granted_scopes: 'false',
          prompt: 'consent',
        });
        return {
          success: true,
          authorization: {
            requestId: body.requestId,
            flowId: ids.flow,
            connectionId: ids.connection,
            provider: 'google',
            authorizationUrl: `https://accounts.google.com/o/oauth2/v2/auth?${query}`,
            expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
          },
        };
      }
      throw new Error(`Unexpected request: ${pathname}`);
    };

    const abortableDelay = (milliseconds, signal) => new Promise((resolve, reject) => {
      if (!milliseconds) return resolve();
      const timer = setTimeout(resolve, milliseconds);
      signal?.addEventListener('abort', () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      }, {once: true});
    });

    window.fetch = async (input, options = {}) => {
      const url = new URL(String(input), 'https://www.askcrump.com');
      const headers = Object.fromEntries(new Headers(options.headers || {}).entries());
      const body = options.body ? JSON.parse(options.body) : null;
      const call = {pathname: url.pathname, method: options.method || 'GET', headers, body};
      window.__calls.push(call);
      await window.__recordConnectedCall(call);
      if (url.pathname.endsWith('/oauth/start')) {
        await abortableDelay(window.__oauthDelayMs, options.signal);
      }
      return new Response(JSON.stringify(responseFor(url.pathname, options, body)), {
        status: 200,
        headers: {'Content-Type': 'application/json; charset=utf-8'},
      });
    };

    document.querySelectorAll('[data-v1-settings-tab]').forEach(button => {
      button.addEventListener('click', () => {
        document.querySelectorAll('[data-v1-settings-tab]').forEach(candidate => {
          candidate.classList.toggle('is-active', candidate === button);
        });
        document.querySelectorAll('[data-v1-settings-panel]').forEach(panel => {
          const active = panel.dataset.v1SettingsPanel === button.dataset.v1SettingsTab;
          panel.hidden = !active;
          panel.classList.toggle('is-active', active);
        });
      });
    });
    const modal = document.getElementById('settingsModal');
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
  }, {
    ids, hashes, actions, previewPayload, displaySha256,
    calendarPreviewPayload, calendarDisplaySha256,
  });

  await page.addScriptTag({path: path.join(root, 'public', 'connected-apps-ui.js')});
  await page.addScriptTag({path: path.join(root, 'public', 'ui-functions.js')});
  await page.waitForFunction(() => document.getElementById('settingsNavConnections').hidden === false);
  await page.getByRole('button', {name: 'Connections'}).click();
  await page.waitForFunction(() => document.querySelectorAll('#connectedAppsConnections .connected-list-card').length === 1);

  const readButton = page.locator('[data-connected-start="google:mail:read"]');
  const manageButton = page.locator('[data-connected-start="google:mail:manage"]');
  if (!(await readButton.isHidden())) throw new Error('Already-granted read access was offered again.');
  if (!(await manageButton.isVisible())) throw new Error('Separate mail-management expansion was not offered.');
  const grantText = await page.locator('[data-connected-grant="google:mail"]').textContent();
  if (grantText !== 'Read-only connected') throw new Error(`Read-only grant state was not truthful: ${grantText}`);
  const desktopProviderColumns = await page.locator('.connected-provider-grid').evaluate(
    node => getComputedStyle(node).gridTemplateColumns.split(' ').length,
  );
  if (desktopProviderColumns !== 2) throw new Error('Desktop provider layout did not retain two columns.');
  const desktopOverviewFits = await page.locator('.connected-operator-overview').evaluate(node => {
    const rect = node.getBoundingClientRect();
    const panel = document.getElementById('settingsPanelConnections').getBoundingClientRect();
    return rect.left >= panel.left && rect.right <= panel.right + 1;
  });
  if (!desktopOverviewFits) throw new Error('Connected operator overview overflowed the desktop panel.');

  await page.waitForFunction(() => document.querySelectorAll('#connectedAppsTasks .connected-task-card').length === 1);
  if ((await page.locator('#connectedAppsTaskCount').textContent()) !== '1') {
    throw new Error('Active connected task count was not rendered.');
  }
  const taskCopy = await page.locator('#connectedAppsTasks .connected-task-card').textContent();
  if (
    !taskCopy.includes('Quarterly client follow-up')
    || !taskCopy.includes('2 of 8 steps used')
    || !taskCopy.includes('Crump is working')
  ) {
    throw new Error('Connected task progress was not truthful.');
  }
  await page.evaluate(({loop, action, approval}) => {
    window.renderMessages?.([{
      id: '00000000-0000-4000-8000-00000000000d',
      role: 'assistant',
      content: '',
      connectedOperator: {
        version: 1,
        state: 'pending_approval',
        loopId: loop,
        currentStep: 2,
        maxSteps: 8,
        actionId: action,
        approvalId: approval,
      },
    }]);
  }, {loop: ids.loop, action: ids.action, approval: ids.approval});
  const chatCard = page.locator('[data-connected-operator-card="pending_approval"]');
  if (!(await chatCard.isVisible())) throw new Error('Connected review card was not visible after readiness.');
  await chatCard.getByRole('button', {name: 'Review action'}).click();
  await page.waitForFunction(() => document.activeElement?.id === 'connectedAppsApprovalsTitle');

  await page.getByRole('button', {name: 'Cancel task'}).click();
  await page.waitForFunction(
    loop => window.__calls.some(call => call.pathname.endsWith(`/tasks/${loop}/cancel`) && call.method === 'POST'),
    ids.loop,
  );
  const taskCancelCall = capturedCalls.find(
    call => call.pathname.endsWith(`/tasks/${ids.loop}/cancel`) && call.method === 'POST',
  );
  if (
    taskCancelCall?.body?.taskStateRevision !== 4
    || taskCancelCall.body.confirmed !== true
    || Object.keys(taskCancelCall.body).sort().join(',') !== 'confirmed,taskStateRevision'
    || taskCancelCall.headers['x-ask-crump-expected-owner'] !== ids.owner
  ) throw new Error(`Task cancellation lost its exact owner/revision/confirmation boundary: ${JSON.stringify(taskCancelCall)}`);

  await page.evaluate(({result, action}) => {
    window.__unsafeRendered = false;
    const opener = document.createElement('button');
    opener.id = 'connectedResultBrowserOpener';
    opener.type = 'button';
    opener.textContent = 'View result';
    opener.addEventListener('click', () => {
      void window.CrumpConnectedAppsUI.openResult(result, action, opener);
    });
    document.body.append(opener);
  }, {result: ids.result, action: ids.action});
  if (capturedCalls.some(call => call.pathname.endsWith(`/results/${ids.result}`))) {
    throw new Error('Connected result loaded without an explicit user click.');
  }
  await page.locator('#connectedResultBrowserOpener').click();
  await page.waitForSelector('.connected-result-dialog[open]');
  await page.waitForFunction(() => document.querySelectorAll('.connected-result-card').length === 1);
  const resultCall = capturedCalls.find(call => call.pathname.endsWith(`/results/${ids.result}`));
  if (!resultCall || resultCall.headers['x-ask-crump-expected-owner'] !== ids.owner) {
    throw new Error('Connected result request lost its exact owner boundary.');
  }
  if (await page.locator('.connected-result-dialog img,.connected-result-dialog script').count()) {
    throw new Error('Untrusted connected content was interpreted as HTML.');
  }
  if (await page.evaluate(() => window.__unsafeRendered)) {
    throw new Error('Untrusted connected content executed.');
  }
  const bodyText = await page.locator('.connected-result-body pre').textContent();
  if (!bodyText.includes('<script>') || !bodyText.includes('Untrusted mail body')) {
    throw new Error('Untrusted connected content was not preserved as text data.');
  }
  if (!(await page.getByRole('button', {name: 'Close connected result'}).evaluate(
    node => node === document.activeElement,
  ))) throw new Error('Connected result viewer did not place keyboard focus safely.');
  await page.keyboard.press('Escape');
  if (await page.locator('.connected-result-dialog').count()) {
    throw new Error('Escape did not scrub the connected result viewer.');
  }
  if (!(await page.locator('#connectedResultBrowserOpener').evaluate(
    node => node === document.activeElement,
  ))) throw new Error('Connected result viewer did not restore opener focus.');

  await page.getByRole('button', {name: 'Approve this action'}).click();
  await page.waitForFunction(
    () => window.__calls.some(call => call.pathname.includes('/approvals/') && call.method === 'POST'),
    null,
    {timeout: 5_000},
  );
  const approvalCall = capturedCalls.find(call => call.pathname.includes('/approvals/') && call.method === 'POST');
  const requiredApprovalBindings = {
    actionId: ids.action,
    connectionId: ids.connection,
    taskId: ids.task,
    turnId: ids.turn,
    provider: 'google',
    resource: 'mail',
    action: 'mail.send',
    authorizationRevision: 1,
    authorizationSnapshotSha256: hashes.authorization,
    grantedScopesSha256: hashes.scopes,
    policyVersion: 'connected-action-policy-v1',
    actionRevision: 3,
    approvalBindingSha256: hashes.approval,
    previewSha256: hashes.preview,
    parametersSha256: hashes.parameters,
    resourceVersionSha256: null,
    decision: 'approved',
    confirmed: true,
  };
  for (const [key, expected] of Object.entries(requiredApprovalBindings)) {
    if (approvalCall?.body?.[key] !== expected) {
      throw new Error(`Approval command lost exact ${key} binding.`);
    }
  }
  if (approvalCall.headers['x-ask-crump-expected-owner'] !== ids.owner) {
    throw new Error('Expected-owner header was not sent.');
  }

  await page.getByRole('button', {name: 'Deny'}).click();
  await page.waitForFunction(
    () => window.__calls.filter(
      call => call.pathname.includes('/approvals/') && call.method === 'POST',
    ).length >= 2,
    null,
    {timeout: 5_000},
  );
  const denialCall = capturedCalls.filter(
    call => call.pathname.includes('/approvals/') && call.method === 'POST',
  )[1];
  if (
    denialCall?.body?.decision !== 'denied'
    || denialCall.body.previewSha256 !== hashes.preview
  ) {
    throw new Error('Denial command lost the durable keyed preview commitment.');
  }

  await page.evaluate(() => { window.__calendarApproval = true; });
  await page.evaluate(() => window.CrumpConnectedAppsUI.refresh());
  await page.waitForFunction(() => (
    document.getElementById('connectedAppsApprovals')?.textContent
      .includes('Attendee effect')
  ));
  const calendarApprovalText = await page.locator('#connectedAppsApprovals').textContent();
  if (!calendarApprovalText.includes(
    'Google Calendar may send cancellation notices to attendees removed by this change.',
  )) {
    throw new Error('Calendar approval did not disclose its attendee notification effect.');
  }

  await page.setViewportSize({width: 390, height: 844});
  const columns = await page.locator('.connected-provider-grid').evaluate(
    node => getComputedStyle(node).gridTemplateColumns.split(' ').length,
  );
  if (columns !== 1) throw new Error('Mobile provider cards did not collapse to one column.');
  const overviewColumns = await page.locator('.connected-operator-overview').evaluate(
    node => getComputedStyle(node).gridTemplateColumns.split(' ').length,
  );
  if (overviewColumns !== 1) throw new Error('Mobile operator overview did not collapse to one column.');
  const shortControls = await page.locator('.connected-workspace-nav button').evaluateAll(
    nodes => nodes.filter(node => node.getBoundingClientRect().height < 44).length,
  );
  if (shortControls) throw new Error('Mobile connected workspace controls were smaller than 44px.');
  const taskBounds = await page.locator('#connectedAppsTasks .connected-task-card').evaluate(node => {
    const rect = node.getBoundingClientRect();
    const panel = document.getElementById('settingsPanelConnections').getBoundingClientRect();
    return {left: rect.left, right: rect.right, panelLeft: panel.left, panelRight: panel.right};
  });
  if (taskBounds.right > taskBounds.panelRight + 1 || taskBounds.left < taskBounds.panelLeft - 1) {
    throw new Error(`Connected task card overflowed its mobile panel: ${JSON.stringify(taskBounds)}`);
  }
  const managementWidth = await manageButton.evaluate(node => Math.round(node.getBoundingClientRect().width));
  if (managementWidth < 300) throw new Error('Mobile permission control did not remain touch-sized.');

  await page.locator('#connectedResultBrowserOpener').click();
  await page.waitForSelector('.connected-result-dialog[open]');
  const resultDialogWidth = await page.locator('.connected-result-dialog').evaluate(
    node => Math.round(node.getBoundingClientRect().width),
  );
  if (resultDialogWidth > 382) throw new Error('Connected result viewer overflowed the mobile viewport.');

  await page.evaluate(() => {
    window.__ownerId = '00000000-0000-4000-8000-00000000000b';
    window.__authRevision += 1;
    window.__connectedScrub({reason: 'authenticated-user-changed'});
  });
  if (!(await page.locator('#settingsNavConnections').isHidden())) {
    throw new Error('Owner switch did not hide Connections.');
  }
  if (await page.locator('.connected-result-dialog').count()) {
    throw new Error('Owner switch did not remove the connected result from the DOM.');
  }
  if ((await page.locator('body').textContent()).includes('Untrusted mail body')) {
    throw new Error('Owner switch left connected provider content in the DOM.');
  }
  const privateText = await page.locator('#connectedAppsApprovals').textContent();
  if (privateText.includes('client@example.com') || privateText.includes('Project update')) {
    throw new Error('Owner switch left approval content in the DOM.');
  }

  await page.evaluate(({owner}) => {
    window.__ownerId = owner;
    window.__authRevision += 1;
    window.__statusEnabled = false;
  }, {owner: ids.owner});
  await page.evaluate(() => window.CrumpConnectedAppsUI.checkAvailability());
  await page.waitForFunction(() => document.getElementById('settingsNavConnections').hidden === true);
  if (!(await chatCard.isHidden())) throw new Error('Release-off state left a connected chat card visible.');
  await page.evaluate(() => { window.__statusEnabled = true; });
  await page.evaluate(() => window.CrumpConnectedAppsUI.checkAvailability());
  await page.waitForFunction(() => document.getElementById('settingsNavConnections').hidden === false);
  if (!(await chatCard.isVisible())) throw new Error('Ready state did not restore the connected chat card.');
  await page.getByRole('button', {name: 'Connections'}).click();
  await page.waitForFunction(() => document.querySelectorAll('#connectedAppsConnections .connected-list-card').length === 1);

  const oauthCallsBefore = capturedCalls.filter(call => call.pathname.endsWith('/oauth/start')).length;
  await page.locator('[data-connected-start="google:mail:manage"]').click();
  if (capturedCalls.filter(call => call.pathname.endsWith('/oauth/start')).length !== oauthCallsBefore) {
    throw new Error('OAuth started before explicit consent.');
  }
  await page.locator('#connectedAppsConsentCancel').click();
  if (capturedCalls.filter(call => call.pathname.endsWith('/oauth/start')).length !== oauthCallsBefore) {
    throw new Error('Cancelling permission review started OAuth.');
  }

  await page.evaluate(() => { window.__oauthDelayMs = 250; });
  await page.locator('[data-connected-start="google:mail:manage"]').click();
  await page.getByRole('button', {name: 'Continue securely'}).click();
  await page.waitForFunction(
    expected => window.__calls.filter(call => call.pathname.endsWith('/oauth/start')).length > expected,
    oauthCallsBefore,
  );
  await page.locator('#connectedAppsConsentCancel').click();
  await page.waitForTimeout(300);
  if (page.url() !== 'https://www.askcrump.com/app') {
    throw new Error('Cancelling an in-flight OAuth start still navigated away.');
  }

  await page.evaluate(() => { window.__oauthDelayMs = 0; });
  await page.locator('[data-connected-start="google:mail:manage"]').click();
  await page.getByRole('button', {name: 'Continue securely'}).click();
  await page.waitForURL('https://accounts.google.com/o/oauth2/v2/auth?**');
  const oauthCall = [...capturedCalls].reverse().find(call => call.pathname.endsWith('/oauth/start'));
  const expectedActions = ['mail.search', 'mail.get', 'mail.create_draft', 'mail.send', 'mail.reply'];
  if (
    oauthCall?.body?.confirmed !== true
    || oauthCall.body.provider !== 'google'
    || oauthCall.body.resource !== 'mail'
    || oauthCall.body.connectionId !== ids.connection
    || oauthCall.body.redirectUri !== 'https://www.askcrump.com/api/connected-apps/oauth/callback/google'
    || JSON.stringify(oauthCall.body.actions) !== JSON.stringify(expectedActions)
  ) throw new Error('OAuth management-expansion command was incomplete or over-broad.');

  if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(' | ')}`);
  await browser.close();
  process.stdout.write('connected apps UI browser verifier passed\n');
}

run().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
