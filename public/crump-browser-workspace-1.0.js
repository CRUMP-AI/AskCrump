/* Ask Crump Browser Workspace — owner-scoped research and reviewed actions. */
(() => {
  'use strict';

  if (window.__crumpBrowserWorkspaceLoaded) return;
  window.__crumpBrowserWorkspaceLoaded = true;

  const API = '/api/browser';
  const OWNER_HEADER = 'X-Ask-Crump-Expected-Owner';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const MAX_BYTES = 262_144;
  const TIMEOUT_MS = 12_000;
  const ACTIVE = new Set(['queued', 'preparing', 'running']);
  const TERMINAL = new Set(['done', 'failed', 'cancelled']);
  const STAGES = Object.freeze(['brief', 'progress', 'review', 'result']);
  const STATUS_LABELS = Object.freeze({
    queued: 'Queued', preparing: 'Preparing', running: 'In progress', paused: 'Paused',
    waiting_approval: 'Waiting for review', blocked: 'Blocked', done: 'Done', failed: 'Failed',
    cancelled: 'Cancelled', draft: 'Brief',
  });

  const state = {
    generation: 0,
    root: null,
    ownerId: '',
    revision: -1,
    mode: 'research',
    released: false,
    statusChecked: false,
    loading: false,
    tasks: [],
    activeTaskId: '',
    notice: null,
    pendingAction: '',
    ambiguousMutation: null,
    draft: {objective: '', sites: '', boundaries: '', timeLimitMinutes: '20'},
    draftOwnerId: '',
    controllers: new Map(),
    pollTimer: 0,
    reconcileTimer: 0,
    refreshFailures: 0,
    mounted: false,
    boundaryUnregister: null,
  };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };

  function boundary() {
    const ownerId = String(
      window.CrumpAuthBoundary?.authenticatedUserId?.() || window.currentUser?.id || '',
    ).trim();
    const revision = Number(window.CrumpAuthBoundary?.revision?.() ?? -1);
    if (!UUID.test(ownerId) || !Number.isSafeInteger(revision) || revision < 0) return null;
    return Object.freeze({ownerId, revision, generation: state.generation});
  }

  function boundaryCurrent(candidate) {
    const current = boundary();
    return Boolean(
      candidate && current
      && candidate.generation === state.generation
      && current.ownerId === candidate.ownerId
      && current.revision === candidate.revision,
    );
  }

  function abortRequests(reason = 'owner-boundary') {
    state.controllers.forEach(controller => controller.abort(reason));
    state.controllers.clear();
    window.clearTimeout(state.pollTimer);
    state.pollTimer = 0;
    window.clearTimeout(state.reconcileTimer);
    state.reconcileTimer = 0;
  }

  function abortChannel(channel, reason = 'superseded') {
    const controller = state.controllers.get(channel);
    if (!controller) return;
    controller.abort(reason);
    state.controllers.delete(channel);
  }

  function syncEntryVisibility() {
    document.querySelectorAll('[data-browser-workspace-entry]').forEach(entry => {
      entry.hidden = state.released !== true;
      entry.setAttribute('aria-hidden', state.released === true ? 'false' : 'true');
    });
    let visibleIndex = 1;
    document.querySelectorAll('.v1-launch-card').forEach(card => {
      if (card.hidden) return;
      card.dataset.v1Index = String(visibleIndex).padStart(2, '0');
      visibleIndex += 1;
    });
  }

  function scrub(transition = null) {
    state.generation += 1;
    abortRequests();
    state.ownerId = '';
    state.revision = -1;
    state.released = false;
    state.mode = 'research';
    state.statusChecked = false;
    state.loading = false;
    state.tasks = [];
    state.activeTaskId = '';
    state.notice = null;
    state.pendingAction = '';
    state.ambiguousMutation = null;
    state.refreshFailures = 0;
    state.draft = {objective: '', sites: '', boundaries: '', timeLimitMinutes: '20'};
    state.draftOwnerId = '';
    syncEntryVisibility();
    if (state.mounted && state.root?.isConnected) {
      state.root.replaceChildren();
      render(state.root);
    }
    const nextOwnerId = String(transition?.nextUserId || '').trim();
    queueMicrotask(() => {
      if (!state.mounted) return;
      const current = boundary();
      if (nextOwnerId && current?.ownerId === nextOwnerId) {
        refresh();
        return;
      }
      if (!nextOwnerId && !current) render(state.root);
    });
  }

  function ensureBoundaryRegistration() {
    if (state.boundaryUnregister || typeof window.CrumpAuthBoundary?.register !== 'function') return;
    state.boundaryUnregister = window.CrumpAuthBoundary.register('browser-workspace', scrub);
  }

  async function boundedJson(response, controller) {
    const declared = response.headers.get('content-length');
    if (declared !== null) {
      const size = Number(declared);
      if (!Number.isSafeInteger(size) || size < 1 || size > MAX_BYTES) {
        controller.abort('response-too-large');
        throw new Error('BROWSER_RESPONSE_INVALID');
      }
    }
    const bytes = await response.arrayBuffer();
    if (!bytes.byteLength || bytes.byteLength > MAX_BYTES) throw new Error('BROWSER_RESPONSE_INVALID');
    let raw = '';
    try { raw = new TextDecoder('utf-8', {fatal: true}).decode(bytes); }
    catch (_) { throw new Error('BROWSER_RESPONSE_INVALID'); }
    try { return JSON.parse(raw); }
    catch (_) { throw new Error('BROWSER_RESPONSE_INVALID'); }
  }

  async function request(path, options = {}, expected = boundary()) {
    if (!expected || !boundaryCurrent(expected)) throw new Error('BROWSER_OWNER_REQUIRED');
    const channel = String(options.channel || 'control');
    const controller = new AbortController();
    abortChannel(channel);
    state.controllers.set(channel, controller);
    const timeout = window.setTimeout(() => controller.abort('timeout'), TIMEOUT_MS);
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
          [OWNER_HEADER]: expected.ownerId,
          ...(options.body ? {'Content-Type': 'application/json'} : {}),
          ...(options.requestId ? {'X-Request-Id': options.requestId} : {}),
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
      if (!boundaryCurrent(expected)) throw new Error('BROWSER_OWNER_CHANGED');
      if (!String(response.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) {
        throw new Error('BROWSER_RESPONSE_INVALID');
      }
      const data = await boundedJson(response, controller);
      if (!boundaryCurrent(expected) || controller.signal.aborted) throw new Error('BROWSER_OWNER_CHANGED');
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('BROWSER_RESPONSE_INVALID');
      if (!response.ok || data.success !== true) {
        const error = new Error(typeof data.code === 'string' ? data.code : 'BROWSER_REQUEST_FAILED');
        error.code = typeof data.code === 'string' ? data.code : 'BROWSER_REQUEST_FAILED';
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (controller.signal.aborted && boundaryCurrent(expected)) {
        const reason = String(controller.signal.reason || '');
        if (reason === 'superseded' || reason === 'control-started') {
          throw new Error('BROWSER_REQUEST_SUPERSEDED');
        }
        throw new Error('BROWSER_NETWORK_UNAVAILABLE');
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
      if (state.controllers.get(channel) === controller) state.controllers.delete(channel);
    }
  }

  function isAuthenticationFailure(error) {
    const status = Number(error?.status || 0);
    return status === 401 || status === 403
      || error?.code === 'AUTH_REQUIRED'
      || error?.code === 'AUTH_OWNER_MISMATCH';
  }

  function failClosedForAuthentication() {
    scrub({nextUserId: ''});
    state.statusChecked = true;
    state.notice = {
      kind: 'auth',
      text: 'Your Browser session could not be verified. Sign in again before viewing tasks or retrying an action.',
      tone: 'danger',
    };
    syncEntryVisibility();
    if (state.mounted && state.root?.isConnected) render(state.root);
    document.dispatchEvent(new CustomEvent('crump:authentication-required', {detail: {source: 'browser-workspace'}}));
  }

  function taskStatus(task) {
    const value = String(task?.status || 'draft').toLowerCase();
    return STATUS_LABELS[value] ? value : 'blocked';
  }

  function statusTone(status) {
    if (['queued', 'preparing', 'running'].includes(status)) return 'active';
    if (['paused', 'waiting_approval', 'blocked'].includes(status)) return 'waiting';
    if (status === 'done') return 'done';
    if (['failed', 'cancelled'].includes(status)) return 'failed';
    return 'neutral';
  }

  function safeArray(value, maximum = 100) {
    return Array.isArray(value) ? value.slice(0, maximum) : [];
  }

  function normalizeTask(record) {
    if (!record || typeof record !== 'object' || !UUID.test(String(record.id || ''))) return null;
    return Object.freeze({
      id: String(record.id),
      projectId: UUID.test(String(record.projectId || '')) ? String(record.projectId) : '',
      objective: String(record.objective || 'Browser task').replace(/\s+/g, ' ').trim().slice(0, 240),
      mode: record.mode === 'act' ? 'act' : 'research',
      status: taskStatus(record),
      stage: STAGES.includes(record.stage) ? record.stage : 'progress',
      currentUrl: String(record.currentUrl || '').slice(0, 2048),
      currentDomain: String(record.currentDomain || '').replace(/[^a-z0-9.-]/gi, '').slice(0, 253),
      summary: String(record.summary || '').slice(0, 6000),
      updatedAt: String(record.updatedAt || ''),
      progress: safeArray(record.progress, 80),
      sources: safeArray(record.sources, 80),
      receipts: safeArray(record.receipts, 80),
      approval: record.approval && typeof record.approval === 'object' ? record.approval : null,
      canPause: record.canPause === true,
      canResume: record.canResume === true,
      canCancel: record.canCancel === true,
    });
  }

  function normalizeTasks(value) {
    return safeArray(value, 100).map(normalizeTask).filter(Boolean);
  }

  function activeTask() {
    return state.tasks.find(task => task.id === state.activeTaskId) || null;
  }

  function announce(message) {
    const live = state.root?.querySelector('[data-cbw-live]');
    if (live) live.textContent = String(message || '');
  }

  function banner(text, tone = 'neutral') {
    const node = el('div', 'cbw-status-banner', text);
    node.dataset.tone = tone;
    node.setAttribute('role', tone === 'danger' ? 'alert' : 'status');
    return node;
  }

  function captureDraft(root = state.root) {
    const form = root?.querySelector('.cbw-form');
    const ownerId = String(boundary()?.ownerId || '');
    if (!form || !ownerId || form.dataset.cbwOwner !== ownerId) return;
    state.draftOwnerId = ownerId;
    state.draft = {
      objective: String(form.elements.objective?.value || '').slice(0, 4000),
      sites: String(form.elements.sites?.value || '').slice(0, 1000),
      boundaries: String(form.elements.boundaries?.value || '').slice(0, 2000),
      timeLimitMinutes: ['10', '20', '30'].includes(String(form.elements.timeLimitMinutes?.value || ''))
        ? String(form.elements.timeLimitMinutes.value)
        : '20',
    };
  }

  function button(label, className, onClick) {
    const node = el('button', `cbw-button ${className || ''}`.trim(), label);
    node.type = 'button';
    if (onClick) node.addEventListener('click', onClick);
    return node;
  }

  function renderHero(root) {
    const hero = el('header', 'cbw-hero');
    const copy = el('div');
    copy.append(el('span', 'cbw-eyebrow', 'Browser workspace'));
    copy.append(el('h1', 'cbw-title', 'Explore the web. Keep the proof.'));
    copy.append(el('p', 'cbw-intro', 'Research across public sources or complete a browser task. You see the plan, live progress, sources, and every external change before it happens.'));
    hero.append(copy);

    const switcher = el('div', 'cbw-mode-switch');
    switcher.setAttribute('role', 'group');
    switcher.setAttribute('aria-label', 'Browser task mode');
    [['research', 'Research'], ['act', 'Act']].forEach(([value, label]) => {
      const option = el('button', '', label);
      option.type = 'button';
      option.setAttribute('aria-pressed', state.mode === value ? 'true' : 'false');
      option.disabled = Boolean(state.pendingAction);
      option.addEventListener('click', () => {
        captureDraft(root);
        state.mode = value;
        render(root);
      });
      switcher.append(option);
    });
    hero.append(switcher);
    root.append(hero);
  }

  function renderTasks() {
    const side = el('aside', 'cbw-side');
    side.dataset.cbwTaskSide = '1';
    side.setAttribute('aria-label', 'Browser tasks');
    const head = el('div', 'cbw-side-head');
    head.append(el('strong', '', 'Work'));
    const newButton = el('button', 'cbw-icon-button', '+');
    newButton.type = 'button';
    newButton.dataset.cbwFocusKey = 'new-task';
    newButton.setAttribute('aria-label', 'New browser task');
    newButton.disabled = Boolean(state.pendingAction);
    newButton.addEventListener('click', () => {
      state.activeTaskId = '';
      render(state.root);
      window.requestAnimationFrame(() => state.root?.querySelector('#cbwObjective')?.focus());
    });
    head.append(newButton);
    side.append(head);
    const list = el('div', 'cbw-task-list');
    if (!state.tasks.length) {
      list.append(el('div', 'cbw-empty', 'No browser work yet.'));
    } else {
      state.tasks.forEach(task => {
        const row = el('button', 'cbw-task-row');
        row.type = 'button';
        row.dataset.cbwFocusKey = `task:${task.id}`;
        row.disabled = Boolean(state.pendingAction);
        row.setAttribute('aria-current', task.id === state.activeTaskId ? 'true' : 'false');
        const dot = el('span', 'cbw-task-dot');
        dot.dataset.tone = statusTone(task.status);
        dot.setAttribute('aria-hidden', 'true');
        const copy = el('span', 'cbw-task-copy');
        copy.append(el('strong', '', task.objective || 'Browser task'));
        copy.append(el('small', '', STATUS_LABELS[task.status] || 'Blocked'));
        row.append(dot, copy);
        row.addEventListener('click', () => {
          state.activeTaskId = task.id;
          render(state.root);
        });
        list.append(row);
      });
    }
    side.append(list);
    return side;
  }

  function inputField(label, help, control) {
    const field = el('div', 'cbw-field');
    const id = control.id;
    const text = el('label', '', label);
    text.htmlFor = id;
    field.append(text, control);
    if (help) {
      const helpText = el('small', '', help);
      helpText.id = `${id}Help`;
      control.setAttribute('aria-describedby', helpText.id);
      field.append(helpText);
    }
    return field;
  }

  function renderBrief() {
    const panel = el('section', 'cbw-panel');
    panel.dataset.cbwMain = 'brief';
    panel.setAttribute('aria-labelledby', 'cbwBriefTitle');
    const heading = el('h2', 'cbw-sr-only', 'New browser task');
    heading.id = 'cbwBriefTitle';
    panel.append(heading);

    const currentBoundary = boundary();
    const ownerReady = Boolean(currentBoundary);
    const draft = state.draftOwnerId === currentBoundary?.ownerId
      ? state.draft
      : {objective: '', sites: '', boundaries: '', timeLimitMinutes: '20'};
    if (!ownerReady) panel.append(banner('Sign in to use private browser work. No task or browser state is kept for a guest.', 'waiting'));
    else if (!state.statusChecked) panel.append(banner('Checking secure browser availability…'));
    else if (!state.released) panel.append(banner('Browser work is prepared locally but is not released for this account yet. Nothing will run or spend credits until the production browser boundary is verified.', 'waiting'));

    const form = el('form', 'cbw-form');
    form.dataset.cbwOwner = currentBoundary?.ownerId || '';
    const objective = el('textarea');
    objective.id = 'cbwObjective';
    objective.name = 'objective';
    objective.maxLength = 4000;
    objective.required = true;
    objective.value = draft.objective;
    objective.placeholder = state.mode === 'research'
      ? 'What should Crump find, compare, verify, or explain?'
      : 'What outcome should Crump complete in the browser?';
    form.append(inputField('Outcome', 'Describe the result you want—not a list of clicks.', objective));

    const twoUp = el('div', 'cbw-two-up');
    const sites = el('input');
    sites.id = 'cbwSites';
    sites.name = 'sites';
    sites.maxLength = 1000;
    sites.value = draft.sites;
    sites.placeholder = 'Optional: example.com, docs.example.org';
    twoUp.append(inputField('Sites or sources', 'Leave blank for public research across the web.', sites));
    const time = el('select');
    time.id = 'cbwTime';
    time.name = 'timeLimitMinutes';
    [['10', 'Up to 10 minutes'], ['20', 'Up to 20 minutes'], ['30', 'Up to 30 minutes']].forEach(([value, label]) => {
      const option = el('option', '', label);
      option.value = value;
      if (value === draft.timeLimitMinutes) option.selected = true;
      time.append(option);
    });
    twoUp.append(inputField('Time boundary', 'Crump stops when this boundary is reached.', time));
    form.append(twoUp);

    const boundaries = el('textarea');
    boundaries.id = 'cbwBoundaries';
    boundaries.name = 'boundaries';
    boundaries.maxLength = 2000;
    boundaries.value = draft.boundaries;
    boundaries.placeholder = state.mode === 'research'
      ? 'Optional: date range, geography, sources to avoid, required evidence…'
      : 'Optional: what may be changed, what must stay untouched, when to stop…';
    form.append(inputField('Boundaries', 'Credentials, money, destructive changes, and private-data release always stop for your review.', boundaries));

    const actions = el('div', 'cbw-actions');
    const start = button(state.mode === 'research' ? 'Start research' : 'Prepare browser task', 'cbw-button-primary');
    start.type = 'submit';
    start.disabled = !ownerReady || !state.released || Boolean(state.pendingAction);
    if (state.pendingAction === 'create') start.textContent = 'Verifying start…';
    actions.append(start);
    form.append(actions);
    form.addEventListener('input', () => captureDraft(form.closest('.cbw-view')));
    form.addEventListener('change', () => captureDraft(form.closest('.cbw-view')));
    form.addEventListener('submit', event => {
      event.preventDefault();
      createTask(form);
    });
    panel.append(form);
    return panel;
  }

  function stageIndex(task) {
    if (task.status === 'waiting_approval') return 2;
    if (TERMINAL.has(task.status)) return 3;
    if (task.status === 'draft') return 0;
    return 1;
  }

  function renderStages(task) {
    const list = el('ol', 'cbw-stage-list');
    const current = stageIndex(task);
    ['Brief', 'Progress', 'Review', 'Result'].forEach((label, index) => {
      const item = el('li', '', label);
      item.dataset.index = String(index + 1).padStart(2, '0');
      if (index === current) item.setAttribute('aria-current', 'step');
      if (index < current) item.dataset.complete = 'true';
      list.append(item);
    });
    return list;
  }

  function safePublicUrl(value) {
    try {
      const url = new URL(String(value || ''));
      if (url.protocol !== 'https:' || url.username || url.password) return null;
      return url;
    } catch (_) {
      return null;
    }
  }

  function detailList(items, kind) {
    const list = el('ul', kind === 'source' ? 'cbw-source-list' : kind === 'receipt' ? 'cbw-receipt-list' : 'cbw-progress-list');
    safeArray(items, 80).forEach(item => {
      if (!item || typeof item !== 'object') return;
      const row = el('li');
      const title = String(item.title || item.label || item.action || 'Update').replace(/\s+/g, ' ').trim().slice(0, 240);
      const sourceUrl = kind === 'source' ? safePublicUrl(item.url) : null;
      const detail = String(item.detail || item.summary || item.observedAt || '').replace(/\s+/g, ' ').trim().slice(0, 1000);
      row.append(el('strong', '', title));
      if (detail) row.append(el('small', '', detail));
      if (sourceUrl) {
        const link = el('a', 'cbw-source-link', `Open source · ${sourceUrl.hostname}`);
        link.href = sourceUrl.href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        row.append(link);
      }
      list.append(row);
    });
    if (!list.children.length) list.append(el('li', '', kind === 'source' ? 'No sources recorded yet.' : kind === 'receipt' ? 'No action receipts yet.' : 'Preparing the first update…'));
    return list;
  }

  function approvalValue(approval, key, fallback = 'Not provided') {
    const value = String(approval?.[key] || '').replace(/\s+/g, ' ').trim();
    return value ? value.slice(0, 1000) : fallback;
  }

  function renderApproval(task) {
    if (task.status !== 'waiting_approval' || !task.approval) return null;
    const approval = task.approval;
    const box = el('section', 'cbw-approval');
    box.setAttribute('aria-labelledby', 'cbwApprovalTitle');
    const title = el('h3', '', 'Review the exact action');
    title.id = 'cbwApprovalTitle';
    box.append(title, el('p', '', 'The page cannot approve this. Only your decision here can authorize one exact action.'));
    const details = el('dl');
    [['Destination', approvalValue(approval, 'destination')], ['Action', approvalValue(approval, 'action')], ['Data shared', approvalValue(approval, 'dataShared', 'None')], ['Account', approvalValue(approval, 'account', 'No connected account')], ['Side effect', approvalValue(approval, 'sideEffect', 'No external change described')], ['Expires', approvalValue(approval, 'expiresAt')]].forEach(([label, value]) => {
      details.append(el('dt', '', label), el('dd', '', value));
    });
    box.append(details);
    const actions = el('div', 'cbw-actions');
    const approve = button('Approve once', 'cbw-button-primary', () => decideApproval(task, 'approved'));
    const deny = button('Deny', 'cbw-button-danger', () => decideApproval(task, 'denied'));
    approve.disabled = Boolean(state.pendingAction);
    deny.disabled = Boolean(state.pendingAction);
    actions.append(approve, deny);
    box.append(actions);
    return box;
  }

  function renderTask(task) {
    const panel = el('section', 'cbw-panel');
    panel.dataset.cbwMain = task.id;
    const head = el('div', 'cbw-work-head');
    const copy = el('div');
    copy.append(el('span', 'cbw-label', `${task.mode === 'act' ? 'Browser action' : 'Research'} · ${STATUS_LABELS[task.status] || 'Blocked'}`));
    copy.append(el('h2', '', task.objective));
    copy.append(el('p', '', task.currentDomain ? `Currently at ${task.currentDomain}` : 'Owner-scoped work with sources and durable status.'));
    head.append(copy);
    const controls = el('div', 'cbw-actions');
    if (task.canPause) controls.append(button('Pause', '', () => taskCommand(task, 'pause')));
    if (task.canResume) controls.append(button('Resume', 'cbw-button-primary', () => taskCommand(task, 'resume')));
    if (task.canCancel) controls.append(button('Cancel', 'cbw-button-danger', () => taskCommand(task, 'cancel')));
    controls.querySelectorAll('button').forEach(control => { control.disabled = Boolean(state.pendingAction); });
    head.append(controls);
    panel.append(head, renderStages(task));

    if (task.status === 'waiting_approval') panel.append(banner('One exact external action is waiting for your review.', 'waiting'));
    else if (task.status === 'done') panel.append(banner('Browser work finished. Review the sources and receipts below.', 'success'));
    else if (task.status === 'failed') panel.append(banner('Browser work stopped without claiming completion. You can review the last verified step.', 'danger'));
    else if (task.status === 'cancelled') panel.append(banner('Browser work was cancelled. No further actions will run.', 'waiting'));
    else if (task.status === 'paused') panel.append(banner('Browser work is paused at a durable boundary.', 'waiting'));

    const grid = el('div', 'cbw-grid');
    const progress = el('section', 'cbw-card cbw-card-wide');
    progress.append(el('h3', '', 'Progress'), el('p', '', task.summary || 'Crump records each verified step without exposing credentials or private browser state.'), detailList(task.progress, 'progress'));
    grid.append(progress);
    const sources = el('section', 'cbw-card');
    sources.append(el('h3', '', 'Sources'), el('p', '', 'Observed pages remain separate from conclusions.'), detailList(task.sources, 'source'));
    grid.append(sources);
    const receipts = el('section', 'cbw-card');
    receipts.append(el('h3', '', 'Receipts'), el('p', '', 'External effects appear only after durable settlement.'), detailList(task.receipts, 'receipt'));
    grid.append(receipts);
    panel.append(grid);
    const approval = renderApproval(task);
    if (approval) panel.append(approval);
    return panel;
  }

  function renderNotices() {
    const notices = el('div', 'cbw-notices');
    notices.dataset.cbwNotices = '1';
    if (state.notice) notices.append(banner(state.notice.text, state.notice.tone));
    if (state.notice?.kind === 'offline') {
      const retry = button('Retry now', 'cbw-button-secondary', () => {
        state.refreshFailures = 0;
        void refresh();
      });
      retry.disabled = state.controllers.has('refresh');
      notices.append(retry);
    }
    if (state.ambiguousMutation) {
      const verify = button('Check verified state', 'cbw-button-secondary', () => {
        state.ambiguousMutation.attempts = 0;
        queueAmbiguousReconciliation(boundary(), state.ambiguousMutation, 0);
      });
      verify.disabled = state.controllers.has('reconcile');
      notices.append(verify);
    }
    return notices;
  }

  function panelFocusToken(panel) {
    const active = document.activeElement;
    if (!panel?.contains(active)) return null;
    if (active.dataset.cbwFocusKey) return {kind: 'key', value: active.dataset.cbwFocusKey};
    if (active.matches('input[id], textarea[id], select[id]')) {
      return {
        kind: 'control',
        value: active.id,
        selectionStart: Number.isInteger(active.selectionStart) ? active.selectionStart : null,
        selectionEnd: Number.isInteger(active.selectionEnd) ? active.selectionEnd : null,
      };
    }
    if (active.matches('a[href]')) return {kind: 'link', value: active.getAttribute('href') || ''};
    if (active.matches('button')) {
      return {
        kind: 'button',
        value: String(active.getAttribute('aria-label') || active.textContent || '').trim(),
      };
    }
    return null;
  }

  function restorePanelFocus(panel, token) {
    if (!panel || !token) return;
    const candidates = token.kind === 'key'
      ? panel.querySelectorAll('[data-cbw-focus-key]')
      : token.kind === 'control'
        ? panel.querySelectorAll('input[id], textarea[id], select[id]')
        : token.kind === 'link'
          ? panel.querySelectorAll('a[href]')
          : panel.querySelectorAll('button');
    const match = Array.from(candidates).find(node => {
      const value = token.kind === 'key'
        ? node.dataset.cbwFocusKey || ''
        : token.kind === 'control'
          ? node.id
          : token.kind === 'link'
            ? node.getAttribute('href') || ''
            : String(node.getAttribute('aria-label') || node.textContent || '').trim();
      return value === token.value;
    });
    if (!match) return;
    match.focus({preventScroll: true});
    if (token.kind === 'control' && token.selectionStart !== null && typeof match.setSelectionRange === 'function') {
      match.setSelectionRange(token.selectionStart, token.selectionEnd);
    }
  }

  function updateRenderedRegions({notices = false, tasks = false, main = false} = {}) {
    if (!state.mounted || !state.root?.isConnected) return;
    const layout = state.root.querySelector('.cbw-layout');
    if (!layout) {
      render(state.root);
      return;
    }
    if (notices) {
      const current = state.root.querySelector('[data-cbw-notices]');
      if (!current) {
        render(state.root);
        return;
      }
      current.replaceWith(renderNotices());
    }
    if (tasks) {
      const current = layout.querySelector('[data-cbw-task-side]');
      if (!current) {
        render(state.root);
        return;
      }
      const focusToken = panelFocusToken(current);
      const next = renderTasks();
      current.replaceWith(next);
      restorePanelFocus(next, focusToken);
    }
    if (main) {
      const current = layout.querySelector('[data-cbw-main]');
      if (!current) {
        render(state.root);
        return;
      }
      const focusToken = panelFocusToken(current);
      const next = activeTask() ? renderTask(activeTask()) : renderBrief();
      current.replaceWith(next);
      restorePanelFocus(next, focusToken);
    }
  }

  function render(root = state.root) {
    if (!root) return;
    state.root = root;
    root.classList.add('cv-view', 'cbw-view');
    root.replaceChildren();
    const shell = el('div', 'cbw-shell');
    renderHero(shell);
    shell.append(renderNotices());
    const layout = el('div', 'cbw-layout');
    layout.append(renderTasks(), activeTask() ? renderTask(activeTask()) : renderBrief());
    shell.append(layout);
    const live = el('div', 'cbw-sr-only');
    live.dataset.cbwLive = '1';
    live.setAttribute('role', 'status');
    live.setAttribute('aria-live', 'polite');
    shell.append(live);
    root.append(shell);
  }

  function requestId() {
    const id = window.crypto?.randomUUID?.();
    if (!UUID.test(String(id || ''))) throw new Error('BROWSER_UI_UNAVAILABLE');
    return id;
  }

  function noticesFingerprint() {
    return JSON.stringify({
      notice: state.notice,
      ambiguousRequestId: state.ambiguousMutation?.requestId || '',
      ambiguousAttempts: state.ambiguousMutation?.attempts || 0,
    });
  }

  function queueAmbiguousReconciliation(expected, mutation, delay = 500) {
    if (!expected || !mutation || state.ambiguousMutation !== mutation) return;
    window.clearTimeout(state.reconcileTimer);
    state.reconcileTimer = window.setTimeout(() => {
      state.reconcileTimer = 0;
      void reconcileAmbiguousMutation(expected, mutation);
    }, delay);
  }

  async function reconcileAmbiguousMutation(expected, mutation) {
    if (!state.mounted || !boundaryCurrent(expected) || state.ambiguousMutation !== mutation) return false;
    mutation.attempts += 1;
    try {
      const response = await request(`/requests/${mutation.requestId}`, {channel: 'reconcile'}, expected);
      if (response.settled !== true) throw new Error('BROWSER_REQUEST_UNSETTLED');
      const task = normalizeTask(response.task);
      if (!task) throw new Error('BROWSER_RESPONSE_INVALID');
      if (mutation.kind !== 'create' && task.id !== mutation.taskId) throw new Error('BROWSER_RESPONSE_INVALID');
      state.tasks = mutation.kind === 'create'
        ? [task, ...state.tasks.filter(item => item.id !== task.id)]
        : state.tasks.some(item => item.id === task.id)
          ? state.tasks.map(item => item.id === task.id ? task : item)
          : [task, ...state.tasks];
      if (mutation.kind === 'create') {
        state.activeTaskId = task.id;
        state.draft = {objective: '', sites: '', boundaries: '', timeLimitMinutes: '20'};
        state.draftOwnerId = '';
      }
      state.ambiguousMutation = null;
      state.pendingAction = '';
      state.notice = null;
      render(state.root);
      announce('Verified browser state restored from the durable request receipt.');
      schedulePoll();
      return true;
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        failClosedForAuthentication();
        return false;
      }
      if (!boundaryCurrent(expected) || state.ambiguousMutation !== mutation) return false;
      state.notice = {
        kind: 'ambiguous',
        text: mutation.attempts < 4
          ? 'The request outcome is still being verified. Do not retry while this check is active.'
          : 'The request outcome remains unknown. Use Check verified state before retrying or taking another action.',
        tone: 'danger',
      };
      render(state.root);
      if (mutation.attempts < 4) {
        queueAmbiguousReconciliation(expected, mutation, 500 * (2 ** mutation.attempts));
      }
      return false;
    }
  }

  async function createTask(form) {
    const expected = boundary();
    if (!expected || !state.released || state.pendingAction || state.ambiguousMutation) return;
    if (!form?.isConnected || form.dataset.cbwOwner !== expected.ownerId) return;
    abortChannel('refresh', 'control-started');
    state.notice = null;
    captureDraft(form.closest('.cbw-view'));
    const data = new FormData(form);
    const objective = String(data.get('objective') || '').trim();
    if (!objective) return;
    const sites = String(data.get('sites') || '').split(',').map(value => value.trim().toLowerCase()).filter(Boolean).slice(0, 20);
    const boundaries = String(data.get('boundaries') || '').trim();
    const timeLimitMinutes = Number(data.get('timeLimitMinutes') || 20);
    const mutation = {kind: 'create', requestId: requestId(), taskId: '', attempts: 0};
    state.pendingAction = 'create';
    const start = form.querySelector('.cbw-button-primary');
    if (start) { start.disabled = true; start.textContent = 'Preparing…'; }
    try {
      const response = await request('/tasks', {
        method: 'POST',
        requestId: mutation.requestId,
        body: {objective, mode: state.mode, allowedDomains: sites, boundaries, timeLimitMinutes},
      }, expected);
      const task = normalizeTask(response.task);
      if (!task) throw new Error('BROWSER_RESPONSE_INVALID');
      state.tasks = [task, ...state.tasks.filter(item => item.id !== task.id)];
      state.activeTaskId = task.id;
      state.draft = {objective: '', sites: '', boundaries: '', timeLimitMinutes: '20'};
      state.draftOwnerId = '';
      state.pendingAction = '';
      state.notice = null;
      render(state.root);
      announce('Browser task prepared.');
      schedulePoll();
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        failClosedForAuthentication();
        return;
      }
      if (!boundaryCurrent(expected)) return;
      state.ambiguousMutation = mutation;
      state.notice = {kind: 'ambiguous', text: 'The start request outcome is unknown. Verifying its durable request receipt before you can retry.', tone: 'danger'};
      render(state.root);
      queueAmbiguousReconciliation(expected, mutation);
    }
  }

  async function taskCommand(task, command) {
    const expected = boundary();
    if (!expected || state.pendingAction || state.ambiguousMutation || !UUID.test(task.id) || !['pause', 'resume', 'cancel'].includes(command)) return;
    abortChannel('refresh', 'control-started');
    state.notice = null;
    const actionKey = `${task.id}:${command}`;
    const mutation = {kind: 'control', requestId: requestId(), taskId: task.id, command, attempts: 0};
    state.pendingAction = actionKey;
    render(state.root);
    try {
      const response = await request(`/tasks/${task.id}/${command}`, {method: 'POST', requestId: mutation.requestId}, expected);
      const next = normalizeTask(response.task);
      if (!next || next.id !== task.id) throw new Error('BROWSER_RESPONSE_INVALID');
      state.tasks = state.tasks.map(item => item.id === next.id ? next : item);
      state.notice = null;
      state.pendingAction = '';
      render(state.root);
      announce(`${STATUS_LABELS[next.status] || 'Task updated'}.`);
      schedulePoll();
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        failClosedForAuthentication();
        return;
      }
      if (boundaryCurrent(expected)) {
        state.ambiguousMutation = mutation;
        state.notice = {kind: 'ambiguous', text: 'That control request outcome is unknown. Verifying its durable request receipt before you can retry.', tone: 'danger'};
        render(state.root);
        announce('That browser control outcome is unknown while Crump verifies the durable request receipt.');
        queueAmbiguousReconciliation(expected, mutation);
      }
    }
  }

  async function decideApproval(task, decision) {
    const expected = boundary();
    const approvalId = String(task.approval?.id || '');
    if (!expected || state.pendingAction || state.ambiguousMutation || !UUID.test(task.id) || !UUID.test(approvalId) || !['approved', 'denied'].includes(decision)) return;
    abortChannel('refresh', 'control-started');
    state.notice = null;
    const actionKey = `${task.id}:approval:${approvalId}`;
    const mutation = {kind: 'approval', requestId: requestId(), taskId: task.id, approvalId, decision, attempts: 0};
    state.pendingAction = actionKey;
    render(state.root);
    try {
      const response = await request(`/tasks/${task.id}/approvals/${approvalId}`, {
        method: 'POST',
        requestId: mutation.requestId,
        body: {decision},
      }, expected);
      const next = normalizeTask(response.task);
      if (!next || next.id !== task.id) throw new Error('BROWSER_RESPONSE_INVALID');
      state.tasks = state.tasks.map(item => item.id === next.id ? next : item);
      state.notice = null;
      state.pendingAction = '';
      render(state.root);
      announce(decision === 'approved' ? 'Action approved once.' : 'Action denied.');
      schedulePoll();
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        failClosedForAuthentication();
        return;
      }
      if (boundaryCurrent(expected)) {
        state.ambiguousMutation = mutation;
        state.notice = {kind: 'ambiguous', text: 'That review decision outcome is unknown. Verifying its durable receipt before you can retry or take another action.', tone: 'danger'};
        render(state.root);
        announce('That review decision outcome is unknown while Crump verifies the durable receipt.');
        queueAmbiguousReconciliation(expected, mutation);
      }
    }
  }

  function schedulePoll() {
    window.clearTimeout(state.pollTimer);
    if (!state.mounted || !state.released || !state.tasks.some(task => ACTIVE.has(task.status))) return;
    state.pollTimer = window.setTimeout(() => refresh({quiet: true}), 3500);
  }

  function scheduleRefreshRetry() {
    window.clearTimeout(state.pollTimer);
    if (!state.mounted || state.refreshFailures > 4) return;
    const delay = Math.min(8_000, 750 * (2 ** (state.refreshFailures - 1)));
    state.pollTimer = window.setTimeout(() => refresh({quiet: true}), delay);
  }

  function handleKeydown(event) {
    if (!state.mounted || event.defaultPrevented || event.key !== 'Escape') return;
    event.preventDefault();
    if (state.activeTaskId) {
      state.activeTaskId = '';
      state.notice = null;
      render(state.root);
      window.requestAnimationFrame(() => state.root?.querySelector('[aria-label="New browser task"]')?.focus());
      return;
    }
    window.CrumpVision?.navigate?.('home');
  }

  async function refresh({quiet = false} = {}) {
    const expected = boundary();
    if (!expected || state.loading) return false;
    const previousStatusChecked = state.statusChecked;
    const previousReleased = state.released;
    const previousNoticesFingerprint = noticesFingerprint();
    const previousTasksFingerprint = JSON.stringify(state.tasks);
    const previousActiveTaskId = state.activeTaskId;
    const previousActiveTask = state.tasks.find(task => task.id === previousActiveTaskId) || null;
    const previousActiveFingerprint = JSON.stringify(previousActiveTask);
    state.loading = true;
    if (!quiet) render(state.root);
    try {
      const status = await request('/status', {channel: 'refresh'}, expected);
      if (!boundaryCurrent(expected)) return false;
      if (typeof status.released !== 'boolean') throw new Error('BROWSER_RESPONSE_INVALID');
      let nextTasks = [];
      if (status.released) {
        const response = await request('/tasks', {channel: 'refresh'}, expected);
        if (!boundaryCurrent(expected)) return false;
        if (!Array.isArray(response.tasks)) throw new Error('BROWSER_RESPONSE_INVALID');
        nextTasks = normalizeTasks(response.tasks);
        if (nextTasks.length !== response.tasks.length) throw new Error('BROWSER_RESPONSE_INVALID');
      }
      state.statusChecked = true;
      state.released = status.released;
      state.tasks = nextTasks;
      if (state.activeTaskId && !nextTasks.some(task => task.id === state.activeTaskId)) state.activeTaskId = '';
      state.ownerId = expected.ownerId;
      state.revision = expected.revision;
      state.refreshFailures = 0;
      if (state.notice?.kind === 'offline') state.notice = null;
      syncEntryVisibility();
      if (!quiet) {
        render(state.root);
      } else {
        const tasksChanged = previousTasksFingerprint !== JSON.stringify(state.tasks);
        const activeChanged = previousActiveTaskId !== state.activeTaskId
          || previousActiveFingerprint !== JSON.stringify(activeTask());
        const availabilityChanged = previousStatusChecked !== state.statusChecked
          || previousReleased !== state.released;
        updateRenderedRegions({
          notices: previousNoticesFingerprint !== noticesFingerprint(),
          tasks: tasksChanged,
          main: availabilityChanged || activeChanged,
        });
      }
      schedulePoll();
      return true;
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        failClosedForAuthentication();
        return false;
      }
      if (!boundaryCurrent(expected)) return false;
      if (error?.message === 'BROWSER_REQUEST_SUPERSEDED') return false;
      state.refreshFailures += 1;
      if (!state.ambiguousMutation) {
        state.notice = {
          kind: 'offline',
          text: state.refreshFailures <= 4
            ? 'Browser status is temporarily unavailable. Your last verified tasks remain in place while Crump retries automatically.'
            : 'Browser status is still unavailable. Your last verified tasks remain in place; choose Retry now when your connection returns.',
          tone: 'danger',
        };
      }
      if (!quiet) render(state.root);
      else updateRenderedRegions({
        notices: previousNoticesFingerprint !== noticesFingerprint(),
      });
      scheduleRefreshRetry();
      return false;
    } finally {
      state.loading = false;
    }
  }

  function onShow() {
    state.mounted = true;
    ensureBoundaryRegistration();
    document.addEventListener('keydown', handleKeydown);
    if (state.ambiguousMutation) {
      state.ambiguousMutation.attempts = 0;
      queueAmbiguousReconciliation(boundary(), state.ambiguousMutation, 0);
    }
    refresh();
  }

  function onHide() {
    state.mounted = false;
    document.removeEventListener('keydown', handleKeydown);
    abortRequests('view-hidden');
  }

  async function probeAvailability() {
    ensureBoundaryRegistration();
    const expected = boundary();
    if (!expected) {
      state.statusChecked = true;
      state.released = false;
      syncEntryVisibility();
      return false;
    }
    try {
      const response = await request('/status', {channel: 'availability'}, expected);
      if (!boundaryCurrent(expected)) return false;
      if (typeof response.released !== 'boolean') throw new Error('BROWSER_RESPONSE_INVALID');
      state.statusChecked = true;
      state.released = response.released;
      syncEntryVisibility();
      return state.released;
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        failClosedForAuthentication();
        return false;
      }
      if (!boundaryCurrent(expected)) return false;
      return state.released;
    }
  }

  function register() {
    const vision = window.CrumpVision;
    if (!vision || typeof vision.registerView !== 'function') return false;
    return vision.registerView('browser', {title: 'Browser', render, onShow, onHide}) === true;
  }

  function open(options = {}) {
    if (options.mode === 'act' || options.mode === 'research') state.mode = options.mode;
    if (UUID.test(String(options.taskId || ''))) state.activeTaskId = String(options.taskId);
    window.CrumpVision?.navigate?.('browser');
  }

  window.CrumpBrowserWorkspace = Object.freeze({
    open,
    refresh,
    scrub,
    isReleased: () => state.released === true,
  });
  window.addEventListener('crumpbrowser:open', event => open(event.detail || {}));
  document.addEventListener('click', event => {
    const trigger = event.target instanceof Element ? event.target.closest('[data-browser-workspace-open]') : null;
    if (!trigger) return;
    event.preventDefault();
    open({mode: trigger.getAttribute('data-browser-mode') || 'research'});
  });
  ensureBoundaryRegistration();
  syncEntryVisibility();
  window.addEventListener('crump:body-runtime-ready', () => {
    ensureBoundaryRegistration();
    probeAvailability();
  }, {once: true});
  window.addEventListener('crump:authenticated-ready', probeAvailability);
  if (!register()) document.addEventListener('crumpvision:ready', register, {once: true});
})();
