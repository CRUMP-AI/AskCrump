(() => {
  'use strict';

  const API = '/api/connected-apps';
  const OWNER_HEADER = 'X-Ask-Crump-Expected-Owner';
  const MAX_RESPONSE_BYTES = 262_144;
  const REQUEST_TIMEOUT_MS = 10_000;
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const SHA256 = /^[0-9a-f]{64}$/;
  const PROVIDERS = new Set(['google', 'microsoft']);
  const RESOURCES = new Set(['mail', 'calendar']);
  const CONNECTION_STATES = new Set(['active', 'revoked']);
  const SCHEDULE_STATES = new Set(['active', 'paused', 'cancelled']);
  const APPROVAL_STATES = new Set(['pending', 'approved', 'denied', 'expired']);
  const ACTION_STATES = new Set([
    'pending_approval', 'claimed', 'running', 'succeeded', 'ambiguous', 'failed', 'cancelled',
  ]);
  const TASK_STATES = new Set([
    'active', 'waiting_approval', 'clarification', 'completed', 'failed',
    'cancelled', 'expired', 'effect_unknown', 'limit_reached',
  ]);
  const STATUS_LABELS = Object.freeze({
    active: 'Active',
    waiting_approval: 'Waiting for review',
    pending_approval: 'Waiting for review',
    clarification: 'Needs your reply',
    completed: 'Completed',
    succeeded: 'Completed',
    claimed: 'Starting',
    running: 'In progress',
    ambiguous: 'Effect uncertain',
    effect_unknown: 'Effect uncertain',
    failed: 'Failed',
    cancelled: 'Cancelled',
    expired: 'Expired',
    limit_reached: 'Limit reached',
    approved: 'Approved',
    denied: 'Denied',
    pending: 'Pending',
    revoked: 'Revoked',
    paused: 'Paused',
  });
  const TASK_STATUS_COPY = Object.freeze({
    active: 'Crump is working within the connected permissions you granted.',
    waiting_approval: 'One exact external change is waiting for your decision.',
    clarification: 'Reply in the conversation to start a safely revised request.',
    completed: 'All planned connected steps finished.',
    failed: 'The task stopped after a failure. No further steps will run.',
    cancelled: 'The task was cancelled. No further steps will run.',
    expired: 'The task expired before finishing. No further steps will run.',
    effect_unknown: 'An external effect is uncertain. Crump will not repeat it automatically.',
    limit_reached: 'The task stopped at the eight-step safety limit.',
  });
  const ACTION_LABELS = Object.freeze({
    'mail.search': 'Search mail',
    'mail.get': 'Read mail',
    'mail.create_draft': 'Create a draft',
    'mail.send': 'Send mail',
    'mail.reply': 'Reply to mail',
    'calendar.list': 'List calendar events',
    'calendar.get': 'Read a calendar event',
    'calendar.free_busy': 'Check availability',
    'calendar.create': 'Create a calendar event',
    'calendar.update': 'Update a calendar event',
    'calendar.cancel': 'Cancel a calendar event',
  });
  const KNOWN_CAPABILITIES = new Set(Object.keys(ACTION_LABELS));
  const READ_ACTIONS = Object.freeze({
    mail: Object.freeze(['mail.search', 'mail.get']),
    calendar: Object.freeze(['calendar.list', 'calendar.get', 'calendar.free_busy']),
  });
  const MANAGE_ACTIONS = Object.freeze({
    mail: Object.freeze(['mail.create_draft', 'mail.send', 'mail.reply']),
    calendar: Object.freeze(['calendar.create', 'calendar.update', 'calendar.cancel']),
  });
  const GOOGLE_SCOPE_BY_ACTION = Object.freeze({
    'mail.search': 'https://www.googleapis.com/auth/gmail.readonly',
    'mail.get': 'https://www.googleapis.com/auth/gmail.readonly',
    'mail.create_draft': 'https://www.googleapis.com/auth/gmail.compose',
    'mail.send': 'https://www.googleapis.com/auth/gmail.send',
    'mail.reply': 'https://www.googleapis.com/auth/gmail.send',
    'calendar.list': 'https://www.googleapis.com/auth/calendar.events.owned.readonly',
    'calendar.get': 'https://www.googleapis.com/auth/calendar.events.owned.readonly',
    'calendar.free_busy': 'https://www.googleapis.com/auth/calendar.events.freebusy',
    'calendar.create': 'https://www.googleapis.com/auth/calendar.events.owned',
    'calendar.update': 'https://www.googleapis.com/auth/calendar.events.owned',
    'calendar.cancel': 'https://www.googleapis.com/auth/calendar.events.owned',
  });
  const MICROSOFT_SCOPE_BY_ACTION = Object.freeze({
    'mail.search': Object.freeze(['Mail.Read']),
    'mail.get': Object.freeze(['Mail.Read']),
    'mail.create_draft': Object.freeze(['Mail.ReadWrite']),
    'mail.send': Object.freeze(['Mail.ReadWrite', 'Mail.Send']),
    'mail.reply': Object.freeze(['Mail.ReadWrite', 'Mail.Send']),
    'calendar.list': Object.freeze(['Calendars.Read']),
    'calendar.get': Object.freeze(['Calendars.Read']),
    'calendar.free_busy': Object.freeze(['Calendars.ReadBasic']),
    'calendar.create': Object.freeze(['Calendars.ReadWrite']),
    'calendar.update': Object.freeze(['Calendars.ReadWrite']),
    'calendar.cancel': Object.freeze(['Calendars.ReadWrite']),
  });
  const CONSENT_COPY = Object.freeze({
    'mail:read': Object.freeze([
      'Search and read messages only when a task needs them.',
      'Cannot draft, send, reply, move, or delete mail.',
    ]),
    'mail:manage': Object.freeze([
      'Includes search and read access needed to prove outcomes.',
      'Create a provider draft only through a separate exact approval; creating a draft never sends it.',
      'Send or reply only through a separate exact approval.',
    ]),
    'calendar:read': Object.freeze([
      'Read calendars and events; work accounts may also share free/busy availability.',
      'Cannot create, update, cancel, or delete events.',
    ]),
    'calendar:manage': Object.freeze([
      'Includes calendar and availability reads needed to avoid conflicts and prove outcomes.',
      'Create or update an event only through a separate exact approval.',
      'Cancel an event only through a separate exact approval.',
    ]),
  });

  const state = {
    generation: 0,
    ownerId: '',
    authRevision: -1,
    released: false,
    statusChecked: false,
    checkingStatus: false,
    loadingDashboard: false,
    controller: null,
    oauthController: null,
    resultController: null,
    resultDialog: null,
    resultOpener: null,
    consent: null,
    attestedProviders: new Set(),
    attestedCapabilities: new Set(),
    connections: new Map(),
    oauthClientIds: new Map(),
    verifiedPreviews: new Map(),
    oauthReturnStatus: '',
  };

  const byId = id => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };

  function currentBoundary() {
    const ownerId = String(
      window.CrumpAuthBoundary?.authenticatedUserId?.() || window.currentUser?.id || '',
    ).trim();
    const revision = Number(window.CrumpAuthBoundary?.revision?.() ?? -1);
    if (!UUID.test(ownerId) || !Number.isSafeInteger(revision) || revision < 0) return null;
    return Object.freeze({ownerId, revision, generation: state.generation});
  }

  function boundaryIsCurrent(boundary) {
    if (!boundary || boundary.generation !== state.generation) return false;
    const current = currentBoundary();
    return Boolean(
      current
      && current.ownerId === boundary.ownerId
      && current.revision === boundary.revision,
    );
  }

  function newRequestId() {
    if (typeof window.crypto?.randomUUID !== 'function') throw new Error('CONNECTED_UI_UNAVAILABLE');
    const value = window.crypto.randomUUID();
    if (!UUID.test(value)) throw new Error('CONNECTED_UI_UNAVAILABLE');
    return value;
  }

  function fixedError(code = 'CONNECTED_UI_FAILED') {
    const error = new Error(code);
    error.code = code;
    return error;
  }

  function requestedActions(provider, resource, mode, accountKind) {
    if (!PROVIDERS.has(provider) || !RESOURCES.has(resource) || !['read', 'manage'].includes(mode)) {
      throw fixedError('CONNECTED_INPUT_INVALID');
    }
    let reads = [...READ_ACTIONS[resource]];
    if (provider === 'microsoft' && resource === 'calendar' && accountKind !== 'work_school') {
      reads = reads.filter(action => action !== 'calendar.free_busy');
    }
    return mode === 'read' ? reads : [...reads, ...MANAGE_ACTIONS[resource]];
  }

  function expectedScopes(provider, actions) {
    const scopes = new Set();
    if (provider === 'google') {
      scopes.add('openid');
      scopes.add('email');
    } else {
      scopes.add('offline_access');
      scopes.add('User.Read');
    }
    actions.forEach(action => {
      if (provider === 'google') scopes.add(GOOGLE_SCOPE_BY_ACTION[action]);
      else MICROSOFT_SCOPE_BY_ACTION[action].forEach(scope => scopes.add(scope));
    });
    if (scopes.has(undefined)) throw fixedError('CONNECTED_INPUT_INVALID');
    return [...scopes].sort();
  }

  async function boundedJson(response, controller) {
    const declared = response.headers.get('content-length');
    if (declared !== null) {
      const bytes = Number(declared);
      if (!Number.isSafeInteger(bytes) || bytes < 1 || bytes > MAX_RESPONSE_BYTES) {
        controller.abort('response-too-large');
        throw fixedError('CONNECTED_RESPONSE_INVALID');
      }
    }
    let raw = '';
    if (response.body?.getReader) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8', {fatal: true});
      let size = 0;
      try {
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > MAX_RESPONSE_BYTES) {
            controller.abort('response-too-large');
            throw fixedError('CONNECTED_RESPONSE_INVALID');
          }
          raw += decoder.decode(value, {stream: true});
        }
        raw += decoder.decode();
      } catch (error) {
        if (error?.code === 'CONNECTED_RESPONSE_INVALID') throw error;
        throw fixedError('CONNECTED_RESPONSE_INVALID');
      } finally {
        reader.releaseLock();
      }
    } else {
      const bytes = await response.arrayBuffer();
      if (!bytes.byteLength || bytes.byteLength > MAX_RESPONSE_BYTES) {
        controller.abort('response-too-large');
        throw fixedError('CONNECTED_RESPONSE_INVALID');
      }
      try { raw = new TextDecoder('utf-8', {fatal: true}).decode(bytes); }
      catch (_) { throw fixedError('CONNECTED_RESPONSE_INVALID'); }
    }
    if (!raw) throw fixedError('CONNECTED_RESPONSE_INVALID');
    try { return JSON.parse(raw); }
    catch (_) { throw fixedError('CONNECTED_RESPONSE_INVALID'); }
  }

  async function request(path, options = {}, boundary = currentBoundary()) {
    if (!boundary || !boundaryIsCurrent(boundary)) throw fixedError('CONNECTED_OWNER_REQUIRED');
    if (!options.controller && (!state.controller || state.controller.signal.aborted)) {
      state.controller = new AbortController();
    }
    const controller = options.controller || state.controller;
    if (!controller || controller.signal.aborted) throw fixedError('CONNECTED_OPERATION_CANCELLED');
    const timer = window.setTimeout(() => controller.abort('timeout'), REQUEST_TIMEOUT_MS);
    let response;
    try {
      response = await fetch(`${API}${path}`, {
        method: options.method || 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          [OWNER_HEADER]: boundary.ownerId,
          ...(options.body ? {'Content-Type': 'application/json'} : {}),
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
    } catch (_) {
      window.clearTimeout(timer);
      throw fixedError('CONNECTED_NETWORK_UNAVAILABLE');
    }
    let data;
    try {
      if (!boundaryIsCurrent(boundary)) throw fixedError('CONNECTED_OWNER_CHANGED');
      const contentType = String(response.headers.get('content-type') || '').toLowerCase();
      if (!contentType.startsWith('application/json')) throw fixedError('CONNECTED_RESPONSE_INVALID');
      data = await boundedJson(response, controller);
    } finally {
      window.clearTimeout(timer);
    }
    if (!boundaryIsCurrent(boundary) || controller.signal.aborted) {
      throw fixedError('CONNECTED_OWNER_CHANGED');
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      throw fixedError('CONNECTED_RESPONSE_INVALID');
    }
    if (!response.ok || data.success !== true) {
      const code = typeof data.code === 'string' && /^CONNECTED_[A-Z0-9_]{1,80}$/.test(data.code)
        ? data.code : 'CONNECTED_OPERATION_FAILED';
      throw fixedError(code);
    }
    return data;
  }

  function closeConsent({cancelOperation = true} = {}) {
    const dialog = byId('connectedAppsConsentDialog');
    if (cancelOperation) state.oauthController?.abort('consent-cancelled');
    state.oauthController = null;
    state.consent = null;
    if (!dialog) return;
    if (dialog.open && typeof dialog.close === 'function') dialog.close('cancel');
    else dialog.removeAttribute('open');
    byId('connectedAppsConsentContinue')?.removeAttribute('aria-busy');
  }

  function showEmpty(target, message) {
    target.replaceChildren(el('div', 'connected-empty-state', message));
  }

  function resetPrivateView() {
    const connections = byId('connectedAppsConnections');
    const tasks = byId('connectedAppsTasks');
    const approvals = byId('connectedAppsApprovals');
    const schedules = byId('connectedAppsSchedules');
    const activity = byId('connectedAppsActivity');
    if (connections) showEmpty(connections, 'No connected accounts.');
    if (tasks) showEmpty(tasks, 'No connected tasks.');
    if (approvals) showEmpty(approvals, 'Nothing is waiting for review.');
    if (schedules) showEmpty(schedules, 'No connected schedules.');
    if (activity) showEmpty(activity, 'No connected activity.');
    const taskCount = byId('connectedAppsTaskCount');
    if (taskCount) taskCount.textContent = '0';
    const count = byId('connectedAppsApprovalCount');
    if (count) count.textContent = '0';
    const updated = byId('connectedAppsLastUpdated');
    if (updated) updated.textContent = 'Only metadata is shown here.';
    closeConsent();
  }

  function closeResultViewer({restoreFocus = true} = {}) {
    state.resultController?.abort('result-viewer-closed');
    state.resultController = null;
    const dialog = state.resultDialog;
    const opener = state.resultOpener;
    state.resultDialog = null;
    state.resultOpener = null;
    if (dialog) {
      if (dialog.open && typeof dialog.close === 'function') dialog.close('close');
      dialog.remove();
    }
    if (restoreFocus && opener?.isConnected && typeof opener.focus === 'function') {
      opener.focus();
    }
  }

  function selectSafeSettingsTab() {
    const active = document.querySelector('[data-v1-settings-tab="connections"].is-active');
    if (active) document.querySelector('[data-v1-settings-tab="profile"]')?.click();
  }

  function setReleased(released, message = '') {
    state.released = released === true;
    document.querySelectorAll('[data-connected-operator-card]').forEach(card => {
      card.hidden = !state.released;
      card.setAttribute('aria-hidden', state.released ? 'false' : 'true');
    });
    const nav = byId('settingsNavConnections');
    const panel = byId('settingsPanelConnections');
    const workspace = byId('connectedAppsWorkspace');
    const availability = byId('connectedAppsAvailability');
    if (nav) {
      nav.hidden = !state.released;
      nav.setAttribute('aria-hidden', state.released ? 'false' : 'true');
    }
    if (!state.released) {
      state.attestedProviders = new Set();
      state.attestedCapabilities = new Set();
      state.oauthClientIds = new Map();
      selectSafeSettingsTab();
      if (panel) {
        panel.hidden = true;
        panel.setAttribute('aria-hidden', 'true');
        panel.classList.remove('is-active');
      }
      if (workspace) workspace.hidden = true;
      resetPrivateView();
      return;
    }
    if (panel) panel.setAttribute('aria-hidden', 'false');
    if (workspace) workspace.hidden = false;
    if (availability) availability.textContent = message || 'Secure connections are available.';
    updateProviderControls();
  }

  function activeConnection(provider, resource, accountKind) {
    if (!PROVIDERS.has(provider) || !RESOURCES.has(resource)
      || !['personal', 'work_school'].includes(accountKind)) return null;
    const matches = [...state.connections.values()].filter(record => (
      record.authorizationState === 'active'
      && record.provider === provider
      && record.resource === resource
      && record.accountKind === accountKind
    ));
    return matches.length === 1 ? matches[0] : null;
  }

  function updateProviderControls() {
    document.querySelectorAll('[data-connected-provider-card]').forEach(card => {
      const provider = card.dataset.connectedProviderCard;
      card.hidden = !state.released || !state.attestedProviders.has(provider);
    });
    document.querySelectorAll('[data-connected-start]').forEach(control => {
      const [provider, resource, mode] = String(control.dataset.connectedStart || '').split(':');
      const accountSelect = document.querySelector(`[data-connected-account-kind="${provider}"]`);
      const accountKind = accountSelect?.value;
      let actions = [];
      try { actions = requestedActions(provider, resource, mode, accountKind); }
      catch (_) { control.hidden = true; return; }
      const attested = state.attestedProviders.has(provider)
        && actions.every(action => state.attestedCapabilities.has(`${provider}:${action}`));
      const connection = activeConnection(provider, resource, accountKind);
      const granted = new Set(connection?.grantedActions || []);
      const alreadyGranted = actions.every(action => granted.has(action));
      control.hidden = !state.released || !attested || alreadyGranted;
      control.dataset.connectionId = connection?.connectionId || '';
    });
    document.querySelectorAll('[data-connected-account-kind]').forEach(select => {
      select.disabled = false;
    });
    document.querySelectorAll('[data-connected-grant]').forEach(status => {
      const [provider, resource] = String(status.dataset.connectedGrant || '').split(':');
      const accountKind = document.querySelector(
        `[data-connected-account-kind="${provider}"]`,
      )?.value;
      const connection = activeConnection(provider, resource, accountKind);
      if (!connection) {
        status.textContent = 'Not connected';
        status.className = 'connected-grant-state';
        return;
      }
      const manage = MANAGE_ACTIONS[connection.resource];
      const granted = new Set(connection.grantedActions);
      const manages = manage.every(action => granted.has(action));
      status.textContent = manages ? 'Read and manage connected' : 'Read-only connected';
      status.className = 'connected-grant-state is-connected';
    });
  }

  function scrub() {
    state.generation += 1;
    state.controller?.abort('owner-boundary');
    state.oauthController?.abort('owner-boundary');
    state.resultController?.abort('owner-boundary');
    state.controller = null;
    state.oauthController = null;
    state.resultController = null;
    state.ownerId = '';
    state.authRevision = -1;
    state.statusChecked = false;
    state.checkingStatus = false;
    state.loadingDashboard = false;
    state.attestedProviders = new Set();
    state.attestedCapabilities = new Set();
    state.connections = new Map();
    state.oauthClientIds = new Map();
    state.verifiedPreviews = new Map();
    closeResultViewer({restoreFocus: false});
    setReleased(false);
    const availability = byId('connectedAppsAvailability');
    if (availability) availability.textContent = 'Checking secure connection availability…';
  }

  function safeArray(value, maximum = 100) {
    if (!Array.isArray(value) || value.length > maximum) throw fixedError('CONNECTED_RESPONSE_INVALID');
    return value;
  }

  function canonicalUuid(value) {
    return typeof value === 'string' && UUID.test(value) ? value : null;
  }

  function canonicalSha(value, optional = false) {
    if (optional && value === null) return null;
    return typeof value === 'string' && SHA256.test(value) ? value : null;
  }

  function safeTime(value, optional = false) {
    if (optional && value === null) return null;
    if (typeof value !== 'string' || value.length > 40) return null;
    const parsed = new Date(value);
    return Number.isFinite(parsed.getTime()) ? parsed : null;
  }

  function formatTime(value) {
    const date = safeTime(value, true);
    if (!date) return 'Not scheduled';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium', timeStyle: 'short',
    }).format(date);
  }

  function providerLabel(value) {
    return value === 'google' ? 'Google' : value === 'microsoft' ? 'Microsoft' : 'Provider';
  }

  function resourceLabel(value) {
    return value === 'mail' ? 'Mail' : value === 'calendar' ? 'Calendar' : 'Connection';
  }

  function actionLabel(value) {
    return ACTION_LABELS[value] || 'Connected action';
  }

  function statusPill(value) {
    const label = STATUS_LABELS[value] || 'Status unavailable';
    const node = el('span', `connected-status connected-status-${String(value).replace(/[^a-z_]/g, '')}`, label);
    node.setAttribute('aria-label', `Status: ${label}`);
    return node;
  }

  function button(label, className, handler) {
    const node = el('button', className, label);
    node.type = 'button';
    node.addEventListener('click', handler);
    return node;
  }

  function exactKeys(value, keys) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const actual = Object.keys(value).sort();
    const expected = [...keys].sort();
    return actual.length === expected.length
      && actual.every((name, index) => name === expected[index]);
  }

  function boundedText(value, maximum, optional = false) {
    if (optional && value === null) return true;
    return typeof value === 'string' && value.length <= maximum;
  }

  function boundedTextArray(value, maximum, each) {
    return Array.isArray(value) && value.length <= maximum
      && value.every(item => boundedText(item, each));
  }

  function validateResultItem(item) {
    if (!item || item.trustBoundary !== 'untrusted_external_data') return null;
    if (item.kind === 'mail_summary') {
      if (!exactKeys(item, [
        'kind', 'messageId', 'threadId', 'receivedAt', 'subject',
        'subjectTruncated', 'sender', 'recipients', 'labels',
        'hasAttachments', 'trustBoundary',
      ])
        || !boundedText(item.messageId, 512) || !boundedText(item.threadId, 512, true)
        || !safeTime(item.receivedAt) || !boundedText(item.subject, 2_048)
        || typeof item.subjectTruncated !== 'boolean' || !boundedText(item.sender, 512)
        || !boundedTextArray(item.recipients, 20, 512)
        || !boundedTextArray(item.labels, 20, 128)
        || typeof item.hasAttachments !== 'boolean') return null;
      return item;
    }
    if (item.kind === 'mail_message') {
      if (!exactKeys(item, [
        'kind', 'messageId', 'threadId', 'receivedAt', 'subject',
        'subjectTruncated', 'sender', 'recipients', 'bodyText',
        'bodyTruncated', 'attachmentCount', 'trustBoundary',
      ])
        || !boundedText(item.messageId, 512) || !boundedText(item.threadId, 512, true)
        || !safeTime(item.receivedAt) || !boundedText(item.subject, 2_048)
        || typeof item.subjectTruncated !== 'boolean' || !boundedText(item.sender, 512)
        || !boundedTextArray(item.recipients, 20, 512)
        || !boundedText(item.bodyText, 80_000) || typeof item.bodyTruncated !== 'boolean'
        || !Number.isSafeInteger(item.attachmentCount)
        || item.attachmentCount < 0 || item.attachmentCount > 100) return null;
      return item;
    }
    if (item.kind === 'calendar_event') {
      if (!exactKeys(item, [
        'kind', 'eventId', 'calendarId', 'startsAt', 'endsAt', 'timeZone',
        'title', 'titleTruncated', 'description', 'descriptionTruncated',
        'location', 'attendees', 'organizer', 'status', 'trustBoundary',
      ])
        || !boundedText(item.eventId, 512) || !boundedText(item.calendarId, 512)
        || !safeTime(item.startsAt) || !safeTime(item.endsAt)
        || safeTime(item.endsAt).getTime() <= safeTime(item.startsAt).getTime()
        || !boundedText(item.timeZone, 128) || !boundedText(item.title, 2_048)
        || typeof item.titleTruncated !== 'boolean'
        || !boundedText(item.description, 16_000)
        || typeof item.descriptionTruncated !== 'boolean'
        || !boundedText(item.location, 2_048)
        || !boundedTextArray(item.attendees, 30, 512)
        || !boundedText(item.organizer, 512, true) || !boundedText(item.status, 128)) return null;
      return item;
    }
    if (item.kind === 'calendar_busy_window') {
      if (!exactKeys(item, [
        'kind', 'calendarId', 'startsAt', 'endsAt', 'status', 'trustBoundary',
      ])
        || !boundedText(item.calendarId, 512) || !safeTime(item.startsAt)
        || !safeTime(item.endsAt)
        || safeTime(item.endsAt).getTime() <= safeTime(item.startsAt).getTime()
        || !boundedText(item.status, 128)) return null;
      return item;
    }
    return null;
  }

  function validateReadResult(data, resultReferenceId, actionId) {
    if (!exactKeys(data, ['success', 'result']) || data.success !== true) return null;
    const record = data.result;
    if (!exactKeys(record, [
      'version', 'resultReferenceId', 'actionId', 'provider', 'resource',
      'action', 'observedAt', 'expiresAt', 'items', 'itemCount',
      'itemsTruncated', 'trustBoundary',
    ])
      || record.version !== 1 || record.resultReferenceId !== resultReferenceId
      || record.actionId !== actionId || !canonicalUuid(record.resultReferenceId)
      || !canonicalUuid(record.actionId) || !PROVIDERS.has(record.provider)
      || !RESOURCES.has(record.resource) || !READ_ACTIONS[record.resource]?.includes(record.action)
      || !safeTime(record.observedAt) || !safeTime(record.expiresAt)
      || record.trustBoundary !== 'untrusted_external_data'
      || !Array.isArray(record.items) || record.items.length > 100
      || typeof record.itemsTruncated !== 'boolean'
      || record.itemCount !== record.items.length) return null;
    if (safeTime(record.expiresAt).getTime() <= safeTime(record.observedAt).getTime()) return null;
    const items = record.items.map(validateResultItem);
    if (items.some(item => !item)) return null;
    return {...record, items};
  }

  function resultField(target, label, value, className = '') {
    const field = el('div', `connected-result-field ${className}`.trim());
    field.append(el('span', 'connected-result-label', label));
    const content = el('div', 'connected-result-value', value || '—');
    field.append(content);
    target.append(field);
    return content;
  }

  function renderResultItem(item) {
    const card = el('article', 'connected-result-card');
    if (item.kind === 'mail_summary' || item.kind === 'mail_message') {
      card.append(el('h3', '', item.subject || '(No subject)'));
      resultField(card, 'From', item.sender);
      resultField(card, 'Received', formatTime(item.receivedAt));
      resultField(card, 'To', item.recipients.join(', '));
      if (item.kind === 'mail_summary') {
        resultField(card, 'Attachments', item.hasAttachments ? 'Yes' : 'No');
      } else {
        resultField(card, 'Attachments', String(item.attachmentCount));
        const body = resultField(card, 'Message', '', 'connected-result-body');
        const bodyText = el('pre', '', item.bodyText);
        body.replaceChildren(bodyText);
      }
    } else if (item.kind === 'calendar_event') {
      card.append(el('h3', '', item.title || '(Untitled event)'));
      resultField(card, 'Starts', formatTime(item.startsAt));
      resultField(card, 'Ends', formatTime(item.endsAt));
      resultField(card, 'Location', item.location);
      resultField(card, 'Organizer', item.organizer || '—');
      resultField(card, 'Attendees', item.attendees.join(', '));
      if (item.description) {
        const description = resultField(card, 'Description', '', 'connected-result-body');
        description.replaceChildren(el('pre', '', item.description));
      }
    } else {
      card.append(el('h3', '', 'Busy time'));
      resultField(card, 'Starts', formatTime(item.startsAt));
      resultField(card, 'Ends', formatTime(item.endsAt));
      resultField(card, 'Status', item.status);
    }
    return card;
  }

  function resultViewerShell(opener) {
    closeResultViewer({restoreFocus: false});
    const dialog = el('dialog', 'connected-result-dialog');
    dialog.setAttribute('aria-labelledby', 'connectedResultTitle');
    const surface = el('section', 'connected-result-surface');
    const header = el('header', 'connected-result-head');
    const heading = el('div');
    heading.append(
      el('span', 'connected-result-eyebrow', 'CONNECTED RESULT'),
      el('h2', '', 'Opening your result…'),
    );
    heading.querySelector('h2').id = 'connectedResultTitle';
    const close = button('Close', 'connected-result-close', () => closeResultViewer());
    close.setAttribute('aria-label', 'Close connected result');
    header.append(heading, close);
    const content = el('div', 'connected-result-content');
    content.setAttribute('role', 'status');
    content.append(el('p', 'connected-result-loading', 'Loading only the result you chose…'));
    surface.append(header, content);
    dialog.append(surface);
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      closeResultViewer();
    });
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      closeResultViewer();
    });
    document.body.append(dialog);
    state.resultDialog = dialog;
    state.resultOpener = opener?.isConnected ? opener : null;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    close.focus();
    return {dialog, content, heading: heading.querySelector('h2')};
  }

  async function openConnectedResult(resultReferenceId, actionId, opener = null) {
    const boundary = currentBoundary();
    if (!boundary || !canonicalUuid(resultReferenceId) || !canonicalUuid(actionId)) return;
    const viewer = resultViewerShell(opener);
    const controller = new AbortController();
    state.resultController = controller;
    try {
      const data = await request(`/results/${encodeURIComponent(resultReferenceId)}`, {
        controller,
      }, boundary);
      const result = validateReadResult(data, resultReferenceId, actionId);
      if (!result) throw fixedError('CONNECTED_RESPONSE_INVALID');
      if (!boundaryIsCurrent(boundary) || state.resultDialog !== viewer.dialog) return;
      viewer.heading.textContent = actionLabel(result.action);
      viewer.content.removeAttribute('role');
      viewer.content.replaceChildren();
      const meta = el(
        'p', 'connected-result-meta',
        `${providerLabel(result.provider)} · Observed ${formatTime(result.observedAt)}`,
      );
      viewer.content.append(meta);
      if (result.itemsTruncated) {
        viewer.content.append(el(
          'p', 'connected-result-limit',
          'Showing the first 100 items. Refine the request to narrow the result.',
        ));
      }
      if (!result.items.length) {
        viewer.content.append(el('p', 'connected-result-empty', 'No matching items were returned.'));
      } else {
        result.items.forEach(item => viewer.content.append(renderResultItem(item)));
      }
      state.resultController = null;
    } catch (_) {
      if (!boundaryIsCurrent(boundary) || state.resultDialog !== viewer.dialog) return;
      state.resultController = null;
      viewer.heading.textContent = 'Connected result unavailable';
      viewer.content.setAttribute('role', 'alert');
      viewer.content.replaceChildren(el(
        'p', 'connected-result-error',
        'This result could not be opened safely. Nothing else was requested.',
      ));
    }
  }

  function validateConnection(record) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    const connectionId = canonicalUuid(record.connectionId);
    if (
      !connectionId || !PROVIDERS.has(record.provider) || !RESOURCES.has(record.resource)
      || !['personal', 'work_school'].includes(record.accountKind)
      || !CONNECTION_STATES.has(record.authorizationState)
      || !Number.isSafeInteger(record.authorizationRevision) || record.authorizationRevision < 0
      || !safeTime(record.updatedAt)
      || !Array.isArray(record.grantedActions) || !record.grantedActions.length
      || record.grantedActions.length > 12
      || new Set(record.grantedActions).size !== record.grantedActions.length
      || record.grantedActions.some(action => (
        !KNOWN_CAPABILITIES.has(action) || !action.startsWith(`${record.resource}.`)
      ))
    ) return null;
    return {...record, connectionId};
  }

  async function disconnectConnection(record, event) {
    if (!record || record.authorizationState !== 'active') return;
    const confirmed = window.confirm(
      `Disconnect ${providerLabel(record.provider)} ${record.accountKind === 'work_school' ? 'work or school' : 'personal'} ${resourceLabel(record.resource)}? `
      + 'Crump will immediately lose this access and cancel its connected schedules.',
    );
    if (!confirmed) return;
    const control = event.currentTarget;
    control.disabled = true;
    control.setAttribute('aria-busy', 'true');
    try {
      await request(`/connections/${record.connectionId}/disconnect`, {
        method: 'POST', body: {requestId: newRequestId(), confirmed: true},
      });
      await refreshDashboard();
    } catch (_) {
      showAvailability('That account could not be disconnected. Nothing else was changed.', true);
    } finally {
      control.disabled = false;
      control.removeAttribute('aria-busy');
    }
  }

  function renderConnections(records) {
    const target = byId('connectedAppsConnections');
    if (!target) return;
    const normalized = safeArray(records).map(validateConnection);
    if (normalized.some(value => !value)) throw fixedError('CONNECTED_RESPONSE_INVALID');
    const activeKeys = normalized
      .filter(record => record.authorizationState === 'active')
      .map(record => `${record.provider}:${record.accountKind}:${record.resource}`);
    if (new Set(activeKeys).size !== activeKeys.length) {
      throw fixedError('CONNECTED_RESPONSE_INVALID');
    }
    target.replaceChildren();
    state.connections = new Map(
      normalized
        .filter(record => record.authorizationState === 'active')
        .map(record => [record.connectionId, record]),
    );
    updateProviderControls();
    if (!normalized.length) return showEmpty(target, 'No connected accounts yet.');
    normalized.forEach(record => {
      const row = el('article', 'connected-list-card');
      const copy = el('div', 'connected-list-copy');
      copy.append(
        el('strong', '', `${providerLabel(record.provider)} ${resourceLabel(record.resource)}`),
        el('small', '', `${record.accountKind === 'work_school' ? 'Work or school' : 'Personal'} account · updated ${formatTime(record.updatedAt)}`),
      );
      const controls = el('div', 'connected-list-controls');
      controls.append(statusPill(record.authorizationState));
      if (record.authorizationState === 'active') {
        controls.append(button('Disconnect', 'connected-text-button connected-danger-button', event => {
          void disconnectConnection(record, event);
        }));
      }
      row.append(copy, controls);
      target.append(row);
    });
  }

  function validateSchedule(record) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    if (
      !canonicalUuid(record.scheduleId) || !canonicalUuid(record.connectionId)
      || !canonicalUuid(record.taskId) || !canonicalUuid(record.actionTemplateRef)
      || !PROVIDERS.has(record.provider) || !RESOURCES.has(record.resource)
      || !ACTION_LABELS[record.action] || !canonicalSha(record.parametersSha256)
      || !SCHEDULE_STATES.has(record.status)
      || !Number.isSafeInteger(record.taskStateRevision) || record.taskStateRevision < 1
      || typeof record.timeZone !== 'string' || record.timeZone.length > 100
      || !Number.isSafeInteger(record.cadenceSeconds) || record.cadenceSeconds < 60
      || typeof record.requiresApprovalEveryRun !== 'boolean'
      || !safeTime(record.updatedAt)
      || (record.nextRunAt !== null && !safeTime(record.nextRunAt))
    ) return null;
    return record;
  }

  async function transitionSchedule(record, target, event) {
    const control = event.currentTarget;
    const verb = target === 'cancel' ? 'cancel' : target;
    if (!window.confirm(`${verb[0].toUpperCase()}${verb.slice(1)} this schedule?`)) return;
    control.disabled = true;
    control.setAttribute('aria-busy', 'true');
    try {
      await request(`/schedules/${record.scheduleId}/${target}`, {
        method: 'POST',
        body: {
          requestId: newRequestId(),
          expectedTaskStateRevision: record.taskStateRevision,
          confirmed: true,
        },
      });
      await refreshDashboard();
    } catch (_) {
      showAvailability('The schedule changed elsewhere or could not be updated. Refresh and review it again.', true);
    } finally {
      control.disabled = false;
      control.removeAttribute('aria-busy');
    }
  }

  function renderSchedules(records) {
    const target = byId('connectedAppsSchedules');
    if (!target) return;
    const normalized = safeArray(records).map(validateSchedule);
    if (normalized.some(value => !value)) throw fixedError('CONNECTED_RESPONSE_INVALID');
    target.replaceChildren();
    if (!normalized.length) return showEmpty(target, 'No connected schedules.');
    normalized.forEach(record => {
      const row = el('article', 'connected-list-card connected-schedule-card');
      const copy = el('div', 'connected-list-copy');
      copy.append(
        el('strong', '', actionLabel(record.action)),
        el('small', '', `${providerLabel(record.provider)} · fixed ${record.cadenceSeconds}-second interval · next ${formatTime(record.nextRunAt)}`),
      );
      if (record.requiresApprovalEveryRun) {
        copy.append(el('small', 'connected-guard-copy', 'Every run requires your approval.'));
      }
      const controls = el('div', 'connected-list-controls');
      controls.append(statusPill(record.status));
      if (record.status === 'active') {
        controls.append(button('Pause', 'connected-text-button', event => void transitionSchedule(record, 'pause', event)));
      } else if (record.status === 'paused') {
        controls.append(button('Resume', 'connected-text-button', event => void transitionSchedule(record, 'resume', event)));
      }
      if (record.status !== 'cancelled') {
        controls.append(button('Cancel', 'connected-text-button connected-danger-button', event => void transitionSchedule(record, 'cancel', event)));
      }
      row.append(copy, controls);
      target.append(row);
    });
  }

  function validateTask(record) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    const expected = [
      'loopId', 'chatId', 'turnId', 'status', 'currentStep', 'maxSteps',
      'taskStateRevision', 'pendingApprovalId', 'lastResultReferenceId',
      'expiresAt', 'updatedAt',
    ];
    if (
      !exactKeys(record, expected)
      || !canonicalUuid(record.loopId) || !canonicalUuid(record.chatId)
      || !canonicalUuid(record.turnId) || !TASK_STATES.has(record.status)
      || !Number.isSafeInteger(record.currentStep) || record.currentStep < 0
      || !Number.isSafeInteger(record.maxSteps) || record.maxSteps !== 8
      || record.currentStep > record.maxSteps
      || !Number.isSafeInteger(record.taskStateRevision) || record.taskStateRevision < 1
      || (record.pendingApprovalId !== null && !canonicalUuid(record.pendingApprovalId))
      || (record.lastResultReferenceId !== null && !canonicalUuid(record.lastResultReferenceId))
      || !safeTime(record.expiresAt) || !safeTime(record.updatedAt)
      || safeTime(record.updatedAt).getTime() >= safeTime(record.expiresAt).getTime()
      || ((record.status === 'waiting_approval') !== (record.pendingApprovalId !== null))
    ) return null;
    return record;
  }

  async function cancelTask(record, event) {
    if (!['active', 'waiting_approval'].includes(record.status)) return;
    if (!window.confirm('Cancel this connected task? No further steps will run.')) return;
    const control = event.currentTarget;
    control.disabled = true;
    control.setAttribute('aria-busy', 'true');
    try {
      await request(`/tasks/${record.loopId}/cancel`, {
        method: 'POST',
        body: {
          taskStateRevision: record.taskStateRevision,
          confirmed: true,
        },
      });
      await refreshDashboard();
    } catch (_) {
      showAvailability('The task changed elsewhere or could not be cancelled. Refresh and review it again.', true);
    } finally {
      control.disabled = false;
      control.removeAttribute('aria-busy');
    }
  }

  function localTaskTitle(chatId) {
    const chats = window.chats;
    if (!Array.isArray(chats) || chats.length > 1_000) return 'Connected task';
    const matches = chats.filter(chat => {
      if (!chat || typeof chat !== 'object' || Array.isArray(chat)) return false;
      const candidate = typeof chat.chat_id === 'string' ? chat.chat_id : chat.id;
      return candidate === chatId;
    });
    if (matches.length !== 1 || typeof matches[0].title !== 'string') return 'Connected task';
    const title = matches[0].title.trim();
    if (
      !title || title.length > 120
      || /[\u0000-\u001F\u007F-\u009F\u202A-\u202E\u2066-\u2069]/.test(title)
    ) return 'Connected task';
    return title;
  }

  function renderTasks(records) {
    const target = byId('connectedAppsTasks');
    if (!target) return;
    const normalized = safeArray(records).map(validateTask);
    if (normalized.some(value => !value)) throw fixedError('CONNECTED_RESPONSE_INVALID');
    target.replaceChildren();
    const activeCount = normalized.filter(record => (
      record.status === 'active' || record.status === 'waiting_approval'
    )).length;
    const count = byId('connectedAppsTaskCount');
    if (count) count.textContent = String(activeCount);
    if (!normalized.length) return showEmpty(target, 'No connected tasks.');
    normalized.forEach(record => {
      const row = el('article', `connected-list-card connected-task-card connected-task-${record.status}`);
      const marker = el('span', 'connected-task-marker', '');
      marker.setAttribute('aria-hidden', 'true');
      const copy = el('div', 'connected-list-copy connected-task-copy');
      copy.append(
        el('strong', '', localTaskTitle(record.chatId)),
        el('small', '', `${record.currentStep} of ${record.maxSteps} steps used · updated ${formatTime(record.updatedAt)}`),
        el('small', 'connected-task-guidance', TASK_STATUS_COPY[record.status]),
      );
      const controls = el('div', 'connected-list-controls');
      controls.append(statusPill(record.status));
      if (record.status === 'waiting_approval') {
        controls.append(button('Review exact action', 'connected-text-button', () => {
          openConnectedWorkspace('approvals');
        }));
      } else if (record.status === 'clarification') {
        controls.append(button('Reply in chat', 'connected-text-button', focusComposer));
      }
      if (record.status === 'active' || record.status === 'waiting_approval') {
        controls.append(button('Cancel task', 'connected-text-button connected-danger-button', event => {
          void cancelTask(record, event);
        }));
      }
      row.append(marker, copy, controls);
      target.append(row);
    });
  }

  function validateApproval(record) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    if (
      !canonicalUuid(record.approvalId) || !canonicalUuid(record.actionId)
      || !canonicalUuid(record.connectionId) || !canonicalUuid(record.taskId)
      || !canonicalUuid(record.turnId) || !PROVIDERS.has(record.provider)
      || !RESOURCES.has(record.resource) || !ACTION_LABELS[record.action]
      || !record.action.startsWith(`${record.resource}.`)
      || !Number.isSafeInteger(record.authorizationRevision) || record.authorizationRevision < 1
      || !canonicalSha(record.authorizationSnapshotSha256)
      || !canonicalSha(record.grantedScopesSha256)
      || typeof record.policyVersion !== 'string'
      || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(record.policyVersion)
      || !Number.isSafeInteger(record.actionRevision) || record.actionRevision < 1
      || !APPROVAL_STATES.has(record.status)
      || !canonicalSha(record.approvalBindingSha256)
      || !canonicalSha(record.parametersSha256)
      || !canonicalSha(record.previewSha256)
      || canonicalSha(record.resourceVersionSha256, true) === null && record.resourceVersionSha256 !== null
      || (record.decisionId !== null && !canonicalUuid(record.decisionId))
      || !safeTime(record.expiresAt)
      || (record.decidedAt !== null && !safeTime(record.decidedAt))
    ) return null;
    return record;
  }

  function previewText(value, maximum, {nullable = false} = {}) {
    if (nullable && value === null) return null;
    if (typeof value !== 'string' || value.length > maximum) return undefined;
    if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(value)) return undefined;
    return value;
  }

  function previewList(value, maximumItems = 50) {
    if (!Array.isArray(value) || value.length > maximumItems) return null;
    const normalized = value.map(item => previewText(item, 320));
    if (normalized.some(item => item === undefined) || new Set(normalized).size !== normalized.length) {
      return null;
    }
    return normalized;
  }

  function normalizePreviewPayload(action, payload) {
    if (action.startsWith('mail.')) {
      const keys = ['account', 'to', 'cc', 'bcc', 'subject', 'bodyText', 'replyContext'];
      if (!exactKeys(payload, keys)) return null;
      const account = previewText(payload.account, 320);
      const to = previewList(payload.to);
      const cc = previewList(payload.cc);
      const bcc = previewList(payload.bcc);
      const subject = previewText(payload.subject, 998);
      const bodyText = previewText(payload.bodyText, 100_000);
      const replyContext = previewText(payload.replyContext, 1_000, {nullable: true});
      if (
        account === undefined || !to || !cc || !bcc || subject === undefined
        || bodyText === undefined || replyContext === undefined
        || (action === 'mail.reply' && !replyContext)
        || (action !== 'mail.reply' && replyContext !== null)
        || (action !== 'mail.create_draft' && !to.length && !cc.length && !bcc.length)
      ) return null;
      return {account, to, cc, bcc, subject, bodyText, replyContext};
    }
    if (action.startsWith('calendar.')) {
      const keys = [
        'calendar', 'eventContext', 'title', 'start', 'end', 'timeZone',
        'attendees', 'location', 'description',
      ];
      if (!exactKeys(payload, keys)) return null;
      const calendar = previewText(payload.calendar, 320);
      const eventContext = previewText(payload.eventContext, 1_000, {nullable: true});
      const title = previewText(payload.title, 1_000);
      const start = previewText(payload.start, 80);
      const end = previewText(payload.end, 80);
      const timeZone = previewText(payload.timeZone, 100);
      const attendees = previewList(payload.attendees, 200);
      const location = previewText(payload.location, 1_000);
      const description = previewText(payload.description, 100_000);
      const startTime = start === undefined ? NaN : Date.parse(start);
      const endTime = end === undefined ? NaN : Date.parse(end);
      if (
        calendar === undefined || title === undefined || !title.trim()
        || eventContext === undefined || start === undefined || end === undefined
        || !Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime <= startTime
        || timeZone === undefined || !/^[A-Za-z_+-]+(?:\/[A-Za-z0-9_+.-]+)+$/.test(timeZone)
        || !attendees || location === undefined || description === undefined
        || (action === 'calendar.create' && eventContext !== null)
        || (action !== 'calendar.create' && !eventContext)
      ) return null;
      return {
        calendar, eventContext, title, start, end, timeZone,
        attendees, location, description,
      };
    }
    return null;
  }

  async function digestText(value) {
    if (!window.crypto?.subtle) return null;
    try {
      const digest = await window.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
      return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
    } catch (_) { return null; }
  }

  function displayPreview(provider, action, payload) {
    if (action.startsWith('mail.')) {
      const accountLabel = provider === 'google'
        ? 'Google mail account'
        : provider === 'microsoft'
          ? 'Microsoft mail account'
          : 'Connected mail account';
      return [
        {label: 'Account', value: accountLabel},
        {label: 'To', tokens: payload.to},
        {label: 'Cc', tokens: payload.cc},
        {label: 'Bcc', tokens: payload.bcc},
        {label: 'Subject', value: payload.subject || '(No subject)'},
        {label: 'Message', value: payload.bodyText || '(Empty message)'},
        ...(payload.replyContext ? [{label: 'Replying to', value: payload.replyContext}] : []),
      ];
    }
    const calendarProvider = provider === 'google'
      ? 'Google Calendar'
      : provider === 'microsoft'
        ? 'Microsoft Calendar'
        : 'The connected calendar';
    let attendeeEffect;
    if (action === 'calendar.create') {
      attendeeEffect = payload.attendees.length
        ? `${calendarProvider} will send invitations to the listed attendees.`
        : 'No attendee invitations will be sent because no attendees are listed.';
    } else if (action === 'calendar.update') {
      attendeeEffect = payload.attendees.length
        ? `${calendarProvider} will send invitations or event updates to affected attendees.`
        : `${calendarProvider} may send cancellation notices to attendees removed by this change.`;
    } else {
      attendeeEffect = payload.attendees.length
        ? `${calendarProvider} will send cancellation notices to the listed attendees.`
        : 'No attendee cancellation notices are expected because no attendees are listed.';
    }
    return [
      {label: 'Calendar', value: payload.calendar},
      ...(payload.eventContext ? [{label: 'Event', value: payload.eventContext}] : []),
      {label: 'Title', value: payload.title},
      {label: 'Starts', value: payload.start},
      {label: 'Ends', value: payload.end},
      {label: 'Time zone', value: payload.timeZone},
      {label: 'Attendees', tokens: payload.attendees},
      {label: 'Attendee effect', value: attendeeEffect},
      {label: 'Location', value: payload.location || 'None'},
      {label: 'Description', value: payload.description || 'None'},
    ];
  }

  async function exactReview(record) {
    const review = record.reviewPreview;
    if (!exactKeys(review, [
      'version', 'approvalBindingSha256', 'parametersSha256', 'previewSha256',
      'displaySha256', 'payload',
    ])) return null;
    if (
      review.version !== 'connected-approval-preview-v1'
      || review.approvalBindingSha256 !== record.approvalBindingSha256
      || review.parametersSha256 !== record.parametersSha256
      || !canonicalSha(review.previewSha256)
      || review.previewSha256 !== record.previewSha256
      || !canonicalSha(review.displaySha256)
    ) return null;
    const payload = normalizePreviewPayload(record.action, review.payload);
    if (!payload) return null;
    const canonical = JSON.stringify({
      version: review.version,
      approvalId: record.approvalId,
      actionId: record.actionId,
      action: record.action,
      approvalBindingSha256: record.approvalBindingSha256,
      parametersSha256: record.parametersSha256,
      resourceVersionSha256: record.resourceVersionSha256,
      payload,
    });
    const computed = await digestText(canonical);
    if (!computed || computed !== review.displaySha256) return null;
    return {
      title: actionLabel(record.action),
      fields: displayPreview(record.provider, record.action, payload),
      previewSha256: review.previewSha256,
      displaySha256: computed,
    };
  }

  async function decideApproval(record, decision, event) {
    if (safeTime(record.expiresAt).getTime() <= Date.now()) return;
    const verified = state.verifiedPreviews.get(record.approvalId);
    if (
      decision === 'approved'
      && (!verified || verified.approvalBindingSha256 !== record.approvalBindingSha256)
    ) return;
    const control = event.currentTarget;
    control.disabled = true;
    control.setAttribute('aria-busy', 'true');
    try {
      await request(`/approvals/${record.approvalId}`, {
        method: 'POST',
        body: {
          decisionId: newRequestId(),
          actionId: record.actionId,
          connectionId: record.connectionId,
          taskId: record.taskId,
          turnId: record.turnId,
          provider: record.provider,
          resource: record.resource,
          action: record.action,
          authorizationRevision: record.authorizationRevision,
          authorizationSnapshotSha256: record.authorizationSnapshotSha256,
          grantedScopesSha256: record.grantedScopesSha256,
          policyVersion: record.policyVersion,
          actionRevision: record.actionRevision,
          approvalBindingSha256: record.approvalBindingSha256,
          previewSha256: record.previewSha256,
          parametersSha256: record.parametersSha256,
          resourceVersionSha256: record.resourceVersionSha256,
          decision,
          confirmed: true,
        },
      });
      await refreshDashboard();
    } catch (_) {
      showAvailability('That approval expired or changed. Refresh and review the current action.', true);
    } finally {
      control.disabled = false;
      control.removeAttribute('aria-busy');
    }
  }

  async function renderApprovals(records, boundary) {
    const target = byId('connectedAppsApprovals');
    if (!target) return;
    const normalized = safeArray(records).map(validateApproval);
    if (normalized.some(value => !value)) throw fixedError('CONNECTED_RESPONSE_INVALID');
    const pending = normalized.filter(record => record.status === 'pending');
    const reviewed = await Promise.all(pending.map(async record => ({
      record,
      review: await exactReview(record),
      expired: safeTime(record.expiresAt).getTime() <= Date.now(),
    })));
    if (!boundaryIsCurrent(boundary)) return;
    state.verifiedPreviews = new Map(
      reviewed
        .filter(item => item.review && !item.expired)
        .map(item => [item.record.approvalId, {
          approvalBindingSha256: item.record.approvalBindingSha256,
          previewSha256: item.review.previewSha256,
          displaySha256: item.review.displaySha256,
        }]),
    );
    const count = byId('connectedAppsApprovalCount');
    if (count) count.textContent = String(pending.length);
    target.replaceChildren();
    if (!pending.length) return showEmpty(target, 'Nothing is waiting for review.');
    reviewed.forEach(({record, review, expired}) => {
      const row = el('article', 'connected-approval-card');
      const heading = el('div', 'connected-approval-heading');
      heading.append(
        el('div', 'connected-approval-icon', record.action.startsWith('mail.') ? '✉' : '◫'),
        el('div', '', review?.title || actionLabel(record.action)),
        statusPill(expired ? 'expired' : 'pending'),
      );
      row.append(heading);
      if (review) {
        const preview = el('dl', 'connected-approval-preview');
        review.fields.forEach(field => {
          const value = el('dd');
          if (Array.isArray(field.tokens)) {
            if (!field.tokens.length) {
              value.textContent = 'None';
            } else {
              field.tokens.forEach((token, index) => {
                if (index) value.append(document.createTextNode(', '));
                const isolated = el('bdi', 'connected-approval-token', token);
                isolated.dir = 'auto';
                value.append(isolated);
              });
            }
          } else {
            value.textContent = field.value;
          }
          preview.append(el('dt', '', field.label), value);
        });
        row.append(preview);
      } else {
        row.append(el(
          'p', 'connected-approval-blocked',
          'Approval is blocked because the exact recipients, content, or time are not cryptographically available for review. You may safely deny it while it remains pending.',
        ));
      }
      row.append(el('small', 'connected-approval-expiry', `Expires ${formatTime(record.expiresAt)}`));
      const controls = el('div', 'connected-approval-actions');
      const deny = button('Deny', 'connected-secondary-button', event => void decideApproval(record, 'denied', event));
      const approve = button('Approve this action', 'connected-primary-button', event => void decideApproval(record, 'approved', event));
      deny.disabled = expired;
      approve.disabled = !review || expired;
      if (!review) approve.title = 'Exact cryptographic action preview required';
      if (expired) {
        deny.title = 'This approval has expired';
        approve.title = 'This approval has expired';
      }
      controls.append(deny, approve);
      row.append(controls);
      target.append(row);
    });
  }

  function validateAction(record) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    if (
      !canonicalUuid(record.actionId) || !canonicalUuid(record.connectionId)
      || !canonicalUuid(record.taskId) || !canonicalUuid(record.turnId)
      || !PROVIDERS.has(record.provider) || !RESOURCES.has(record.resource)
      || !ACTION_LABELS[record.action] || !ACTION_STATES.has(record.status)
      || !record.action.startsWith(`${record.resource}.`)
      || !Number.isSafeInteger(record.authorizationRevision) || record.authorizationRevision < 1
      || !canonicalSha(record.authorizationSnapshotSha256)
      || !canonicalSha(record.grantedScopesSha256)
      || typeof record.policyVersion !== 'string'
      || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(record.policyVersion)
      || !Number.isSafeInteger(record.actionRevision) || record.actionRevision < 1
      || !canonicalSha(record.parametersSha256)
      || canonicalSha(record.resourceVersionSha256, true) === null && record.resourceVersionSha256 !== null
      || !safeTime(record.updatedAt)
    ) return null;
    return record;
  }

  function renderActions(records) {
    const target = byId('connectedAppsActivity');
    if (!target) return;
    const normalized = safeArray(records).map(validateAction);
    if (normalized.some(value => !value)) throw fixedError('CONNECTED_RESPONSE_INVALID');
    target.replaceChildren();
    if (!normalized.length) return showEmpty(target, 'No connected activity.');
    normalized.forEach(record => {
      const row = el('article', 'connected-list-card');
      const copy = el('div', 'connected-list-copy');
      copy.append(
        el('strong', '', actionLabel(record.action)),
        el('small', '', `${providerLabel(record.provider)} · ${formatTime(record.updatedAt)}`),
      );
      row.append(copy, statusPill(record.status));
      target.append(row);
    });
  }

  function showAvailability(message, error = false) {
    const node = byId('connectedAppsAvailability');
    if (!node) return;
    node.textContent = message;
    node.classList.toggle('is-error', error);
  }

  async function refreshDashboard() {
    if (!state.released || state.loadingDashboard) return;
    const boundary = currentBoundary();
    if (!boundary) return scrub();
    state.loadingDashboard = true;
    showAvailability('Refreshing secure connection metadata…');
    try {
      const [connections, tasks, schedules, approvals, actions] = await Promise.all([
        request('/connections', {}, boundary),
        request('/tasks', {}, boundary),
        request('/schedules', {}, boundary),
        request('/approvals', {}, boundary),
        request('/actions', {}, boundary),
      ]);
      if (!boundaryIsCurrent(boundary)) return;
      renderConnections(connections.connections);
      renderTasks(tasks.tasks);
      renderSchedules(schedules.schedules);
      await renderApprovals(approvals.approvals, boundary);
      if (!boundaryIsCurrent(boundary)) return;
      renderActions(actions.actions);
      const updated = byId('connectedAppsLastUpdated');
      if (updated) updated.textContent = `Updated ${new Intl.DateTimeFormat(undefined, {timeStyle: 'short'}).format(new Date())}`;
      showAvailability('Secure connection metadata is current.');
    } catch (_) {
      if (boundaryIsCurrent(boundary)) {
        resetPrivateView();
        showAvailability('Connections are temporarily unavailable. No action was taken.', true);
      }
    } finally {
      if (boundaryIsCurrent(boundary)) state.loadingDashboard = false;
    }
  }

  async function checkAvailability() {
    if (state.checkingStatus) return;
    const boundary = currentBoundary();
    if (!boundary) return scrub();
    state.checkingStatus = true;
    state.ownerId = boundary.ownerId;
    state.authRevision = boundary.revision;
    showAvailability('Checking secure connection availability…');
    try {
      const data = await request('/status', {}, boundary);
      if (!boundaryIsCurrent(boundary)) return;
      const providers = safeArray(data.providers, 2);
      const capabilities = data.capabilities;
      const oauthClientIds = data.oauthClientIds;
      const capabilityMapValid = capabilities && typeof capabilities === 'object'
        && !Array.isArray(capabilities)
        && Object.keys(capabilities).length === providers.length
        && providers.every(provider => {
          const actions = capabilities[provider];
          return Array.isArray(actions)
            && actions.length > 0 && actions.length <= KNOWN_CAPABILITIES.size
            && new Set(actions).size === actions.length
            && actions.every(value => KNOWN_CAPABILITIES.has(value));
        });
      const released = data.enabled === true
        && data.status === 'ready'
        && providers.length > 0
        && new Set(providers).size === providers.length
        && providers.every(value => PROVIDERS.has(value))
        && capabilityMapValid
        && oauthClientIds && typeof oauthClientIds === 'object' && !Array.isArray(oauthClientIds)
        && Object.keys(oauthClientIds).length === providers.length
        && providers.every(provider => (
          typeof oauthClientIds[provider] === 'string'
          && /^[A-Za-z0-9._~-]{3,255}$/.test(oauthClientIds[provider])
        ));
      if (released) {
        state.attestedProviders = new Set(providers);
        state.attestedCapabilities = new Set(
          providers.flatMap(provider => capabilities[provider].map(action => `${provider}:${action}`)),
        );
        state.oauthClientIds = new Map(providers.map(provider => [provider, oauthClientIds[provider]]));
      }
      state.statusChecked = true;
      setReleased(released, released ? 'Secure connections are available.' : '');
      if (released && byId('settingsNavConnections')?.classList.contains('is-active')) {
        await refreshDashboard();
      }
    } catch (_) {
      if (boundaryIsCurrent(boundary)) {
        state.statusChecked = true;
        setReleased(false);
      }
    } finally {
      if (boundaryIsCurrent(boundary)) state.checkingStatus = false;
    }
  }

  function openConsent(provider, resource, mode, sourceButton) {
    if (
      !state.released || !PROVIDERS.has(provider) || !RESOURCES.has(resource)
      || !['read', 'manage'].includes(mode)
    ) return;
    const accountKind = document.querySelector(`[data-connected-account-kind="${provider}"]`)?.value;
    if (!['personal', 'work_school'].includes(accountKind)) return;
    const actions = requestedActions(provider, resource, mode, accountKind);
    if (!actions.every(action => state.attestedCapabilities.has(`${provider}:${action}`))) return;
    const existing = activeConnection(provider, resource, accountKind);
    state.consent = Object.freeze({
      provider, resource, mode, accountKind, actions: Object.freeze(actions),
      connectionId: existing?.connectionId || null, sourceButton,
    });
    const title = byId('connectedAppsConsentTitle');
    const description = byId('connectedAppsConsentDescription');
    const scopes = byId('connectedAppsConsentScopes');
    if (title) {
      const kindLabel = accountKind === 'work_school' ? 'work or school' : 'personal';
      title.textContent = `${existing ? 'Expand' : 'Connect'} ${providerLabel(provider)} ${kindLabel} ${resourceLabel(resource)}`;
    }
    if (description) {
      description.textContent = mode === 'read'
        ? `Ask Crump is requesting read-only ${resourceLabel(resource).toLowerCase()} access.`
        : `Ask Crump is requesting additional ${resourceLabel(resource).toLowerCase()} management access.`;
    }
    if (scopes) {
      scopes.replaceChildren(...CONSENT_COPY[`${resource}:${mode}`].map(value => el('li', '', value)));
    }
    const dialog = byId('connectedAppsConsentDialog');
    if (!dialog) return;
    if (typeof dialog.showModal !== 'function') {
      state.consent = null;
      showAvailability('Secure permission review is unavailable in this browser. Nothing was connected.', true);
      return;
    }
    dialog.showModal();
    byId('connectedAppsConsentCancel')?.focus({preventScroll: true});
  }

  function validateAuthorization(record, consent, requestId) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    if (
      record.requestId !== requestId || !canonicalUuid(record.flowId)
      || !canonicalUuid(record.connectionId) || record.provider !== consent.provider
      || (consent.connectionId && record.connectionId !== consent.connectionId)
      || !safeTime(record.expiresAt) || typeof record.authorizationUrl !== 'string'
      || record.authorizationUrl.length > 4096
    ) return null;
    const expiry = safeTime(record.expiresAt);
    const now = Date.now();
    if (expiry.getTime() <= now || expiry.getTime() - now > 10 * 60 * 1000) return null;
    let url;
    try { url = new URL(record.authorizationUrl); }
    catch (_) { return null; }
    const expectedHost = consent.provider === 'google' ? 'accounts.google.com' : 'login.microsoftonline.com';
    const microsoftTenant = consent.accountKind === 'personal' ? 'consumers' : 'organizations';
    const expectedPath = consent.provider === 'google'
      ? '/o/oauth2/v2/auth' : `/${microsoftTenant}/oauth2/v2.0/authorize`;
    if (
      url.protocol !== 'https:' || url.hostname !== expectedHost || url.username || url.password
      || url.port || url.hash || url.pathname !== expectedPath
    ) return null;
    const pairs = [...url.searchParams.entries()];
    const keys = pairs.map(([key]) => key);
    const required = new Set([
      'client_id', 'redirect_uri', 'response_type', 'scope', 'state',
      'code_challenge', 'code_challenge_method',
    ]);
    const optional = consent.provider === 'google'
      ? new Set(['access_type', 'include_granted_scopes', 'prompt'])
      : new Set(['response_mode', 'prompt']);
    const forbidden = new Set([
      'access_token', 'refresh_token', 'id_token', 'code', 'authorization_code',
      'client_secret', 'client_assertion', 'client_assertion_type', 'code_verifier',
    ]);
    if (
      !pairs.length || new Set(keys).size !== keys.length
      || keys.some(key => key !== key.toLowerCase())
      || [...required].some(key => !url.searchParams.has(key))
      || keys.some(key => !required.has(key) && !optional.has(key))
      || keys.some(key => forbidden.has(key))
    ) return null;
    const parameter = key => url.searchParams.get(key);
    const redirectUri = `https://www.askcrump.com/api/connected-apps/oauth/callback/${consent.provider}`;
    const scopes = String(parameter('scope') || '').split(' ');
    if (
      parameter('client_id') !== state.oauthClientIds.get(consent.provider)
      || parameter('redirect_uri') !== redirectUri
      || parameter('response_type') !== 'code'
      || parameter('code_challenge_method') !== 'S256'
      || !/^[A-Za-z0-9_-]{43,128}$/.test(String(parameter('code_challenge') || ''))
      || !/^[A-Za-z0-9_-]{32,512}$/.test(String(parameter('state') || ''))
      || scopes.length !== new Set(scopes).size
      || JSON.stringify([...scopes].sort()) !== JSON.stringify(expectedScopes(consent.provider, consent.actions))
      || (consent.provider === 'google' && parameter('access_type') !== 'offline')
      || (consent.provider === 'google' && parameter('include_granted_scopes') !== 'false')
      || (consent.provider === 'google' && parameter('prompt') !== null
        && !['consent', 'select_account'].includes(parameter('prompt')))
      || (consent.provider === 'microsoft' && parameter('response_mode') !== 'query')
      || (consent.provider === 'microsoft' && parameter('prompt') !== null
        && !['consent', 'select_account'].includes(parameter('prompt')))
    ) return null;
    return url.href;
  }

  async function continueConsent() {
    const consent = state.consent;
    const boundary = currentBoundary();
    if (!consent || !boundaryIsCurrent(boundary)) return closeConsent();
    const control = byId('connectedAppsConsentContinue');
    if (control) {
      control.disabled = true;
      control.setAttribute('aria-busy', 'true');
      control.textContent = 'Opening provider…';
    }
    if (consent.sourceButton) consent.sourceButton.disabled = true;
    const oauthController = new AbortController();
    state.oauthController?.abort('replaced');
    state.oauthController = oauthController;
    const requestId = newRequestId();
    try {
      const data = await request('/oauth/start', {
        method: 'POST',
        controller: oauthController,
        body: {
          requestId,
          provider: consent.provider,
          resource: consent.resource,
          accountKind: consent.accountKind,
          actions: [...consent.actions],
          redirectUri: `https://www.askcrump.com/api/connected-apps/oauth/callback/${consent.provider}`,
          ...(consent.connectionId ? {connectionId: consent.connectionId} : {}),
          confirmed: true,
        },
      }, boundary);
      if (state.consent !== consent || state.oauthController !== oauthController) {
        throw fixedError('CONNECTED_OPERATION_CANCELLED');
      }
      const destination = validateAuthorization(data.authorization, consent, requestId);
      if (!destination || oauthController.signal.aborted) throw fixedError('CONNECTED_RESPONSE_INVALID');
      state.oauthController = null;
      closeConsent({cancelOperation: false});
      if (!boundaryIsCurrent(boundary)) return;
      window.location.assign(destination);
    } catch (_) {
      if (boundaryIsCurrent(boundary)) {
        closeConsent();
        showAvailability('The secure provider handoff could not start. Nothing was connected.', true);
      }
    } finally {
      if (control) {
        control.disabled = false;
        control.removeAttribute('aria-busy');
        control.textContent = 'Continue securely';
      }
      if (consent.sourceButton) consent.sourceButton.disabled = false;
    }
  }

  function modalOpen() {
    const modal = byId('settingsModal');
    return Boolean(modal && modal.style.display && modal.style.display !== 'none');
  }

  function focusComposer() {
    window.closeSettings?.();
    window.requestAnimationFrame(() => byId('userInput')?.focus({preventScroll: true}));
  }

  function openConnectedWorkspace(section = 'connections') {
    if (!state.released || !currentBoundary()) return false;
    const targets = Object.freeze({
      connections: 'connectedAppsAccounts',
      approvals: 'connectedAppsApprovalsTitle',
      tasks: 'connectedAppsTasksTitle',
      schedules: 'connectedAppsSchedulesTitle',
      activity: 'connectedAppsActivityTitle',
    });
    const targetId = targets[section];
    if (!targetId) return false;
    window.openSettings?.();
    byId('settingsNavConnections')?.click();
    window.requestAnimationFrame(() => {
      const target = byId(targetId);
      target?.scrollIntoView({block: 'start', behavior: 'smooth'});
      target?.focus({preventScroll: true});
    });
    return true;
  }

  function wire() {
    try {
      const url = new URL(window.location.href);
      const marker = url.searchParams.get('connected-app');
      if (marker === 'connected' || marker === 'denied' || marker === 'failed') {
        state.oauthReturnStatus = marker;
      }
      if (url.searchParams.has('connected-app')) {
        url.searchParams.delete('connected-app');
        const clean = `${url.pathname}${url.search}${url.hash}`;
        window.history.replaceState(window.history.state, '', clean);
      }
    } catch (_) {
      state.oauthReturnStatus = '';
    }
    document.querySelectorAll('[data-connected-start]').forEach(control => {
      if (control.dataset.connectedWired === 'true') return;
      control.dataset.connectedWired = 'true';
      control.addEventListener('click', () => {
        const [provider, resource, mode] = String(control.dataset.connectedStart || '').split(':');
        openConsent(provider, resource, mode, control);
      });
    });
    document.querySelectorAll('[data-connected-account-kind]').forEach(select => {
      select.addEventListener('change', updateProviderControls);
    });
    byId('connectedAppsConsentContinue')?.addEventListener('click', () => void continueConsent());
    byId('connectedAppsConsentCancel')?.addEventListener('click', () => closeConsent());
    const consentDialog = byId('connectedAppsConsentDialog');
    consentDialog?.addEventListener('cancel', event => {
      event.preventDefault();
      event.stopPropagation();
      closeConsent();
    });
    consentDialog?.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      closeConsent();
    });
    consentDialog?.addEventListener('close', () => {
      if (state.consent || state.oauthController) closeConsent();
    });
    byId('connectedAppsRefresh')?.addEventListener('click', () => void refreshDashboard());
    document.querySelectorAll('[data-connected-jump]').forEach(control => {
      control.addEventListener('click', () => openConnectedWorkspace(control.dataset.connectedJump));
    });
    byId('settingsNavConnections')?.addEventListener('click', () => {
      if (state.released) {
        void refreshDashboard().then(() => {
          if (state.oauthReturnStatus === 'connected') {
            state.oauthReturnStatus = '';
            showAvailability('The account was connected securely.', false);
          } else if (state.oauthReturnStatus === 'denied') {
            state.oauthReturnStatus = '';
            showAvailability(
              'Permission was not granted. Nothing was connected or changed. You can try again whenever you are ready.',
              false,
            );
          } else if (state.oauthReturnStatus === 'failed') {
            state.oauthReturnStatus = '';
            showAvailability(
              'The account was not connected. Try again from Connections.',
              true,
            );
          }
        });
      }
    });

    const modal = byId('settingsModal');
    if (modal) {
      new MutationObserver(() => {
        if (modalOpen()) void checkAvailability();
        else scrub();
      }).observe(modal, {attributes: true, attributeFilter: ['style', 'aria-hidden']});
    }

    window.CrumpAuthBoundary?.register?.('connected-apps-ui', scrub);
    window.addEventListener('crump:authentication-required', scrub);
    window.addEventListener('crump:authenticated-ready', () => {
      scrub();
      if (modalOpen()) void checkAvailability();
    });
    resetPrivateView();
    if (modalOpen()) void checkAvailability();
  }

  window.CrumpConnectedAppsUI = Object.freeze({
    refresh: () => refreshDashboard(),
    scrub,
    checkAvailability: () => checkAvailability(),
    openResult: (resultReferenceId, actionId, opener) => (
      openConnectedResult(resultReferenceId, actionId, opener)
    ),
    openWorkspace: section => openConnectedWorkspace(section),
    focusComposer,
    isReleased: () => state.released,
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire, {once: true});
  else wire();
})();
