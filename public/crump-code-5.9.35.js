(() => {
  'use strict';

  if (window.__crumpCode5935Loaded) return;
  window.__crumpCode5935Loaded = true;

  const byId = id => document.getElementById(id);
  const state = {
    available: false,
    configured: false,
    entitled: false,
    feature: null,
    featureStatus: null,
    provider: null,
    projects: [],
    projectId: '',
    tasks: [],
    task: null,
    ownerId: '',
    navigationEpoch: 0,
    restoreFocus: null,
    pollTimer: 0,
    pollController: null,
    pollFailureCount: 0,
    pollGeneration: 0,
  };
  const ACTIVE = new Set(['queued', 'provisioning', 'running', 'awaiting_approval', 'verifying']);
  const POLL_INITIAL_MS = 1200;
  const POLL_BASE_MS = 2500;
  const POLL_MAX_MS = 30000;
  const POLL_TIMEOUT_MS = 12000;
  const STATUS_LABELS = Object.freeze({
    queued: 'Ready for review',
    provisioning: 'Starting isolated workspace',
    running: 'Working in isolated copy',
    awaiting_approval: 'Waiting for your approval',
    verifying: 'Verifying the change',
    completed: 'Completed',
    failed: 'Failed safely',
    cancelled: 'Cancelled',
  });

  async function apiOnce(path, options = {}) {
    const request = {
      credentials: 'same-origin',
      method: options.method || 'GET',
      headers: {
        Accept: 'application/json',
        'X-Ask-Crump-Expected-Owner': currentOwnerId(),
      },
      cache: 'no-store',
    };
    if (options.signal) request.signal = options.signal;
    if (options.body !== undefined) {
      request.headers['Content-Type'] = 'application/json';
      request.body = JSON.stringify(options.body);
    }
    const response = await fetch(path, request);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
      const error = new Error(data.error || 'Autonomous Crump could not complete that request.');
      error.code = data.code || 'CODE_REQUEST_FAILED';
      error.details = data;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function api(path, options = {}) {
    const controller = window.CrumpCreditConfirmation;
    if (!controller?.run) return apiOnce(path, options);
    return controller.run(confirmation => {
      const next = {...options};
      if (confirmation && next.body && typeof next.body === 'object') {
        next.body = {...next.body, creditConfirmation: confirmation};
      }
      return apiOnce(path, next);
    });
  }

  function statusLabel(value, failureCode = '') {
    if (value === 'cancelled' && failureCode === 'CODE_TASK_EXPIRED') return 'Expired safely';
    if (value === 'cancelled' && failureCode === 'CODE_APPROVAL_EXPIRED') return 'Approval expired';
    return STATUS_LABELS[String(value || '')] || 'Status unavailable';
  }

  function currentOwnerId() {
    return String(window.currentUser?.id || '').trim();
  }

  function beginNavigation() {
    return {ownerId: state.ownerId, epoch: ++state.navigationEpoch};
  }

  function navigationIsCurrent(context) {
    return Boolean(
      context
      && context.ownerId
      && context.ownerId === state.ownerId
      && context.ownerId === currentOwnerId()
      && context.epoch === state.navigationEpoch,
    );
  }

  function currentNavigation() {
    return {ownerId: state.ownerId, epoch: state.navigationEpoch};
  }

  function formatDate(value) {
    const date = new Date(value || '');
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString([], {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
  }

  function setNotice(message = '', tone = '') {
    const notice = byId('crumpCodeNotice');
    if (!notice) return;
    notice.textContent = message;
    notice.dataset.tone = tone;
    notice.hidden = !message;
  }

  function setButtonBusy(button, busy, busyLabel) {
    if (!button) return () => {};
    const label = button.textContent;
    button.disabled = busy;
    if (busy && busyLabel) button.textContent = busyLabel;
    return () => {
      button.disabled = false;
      button.textContent = label;
    };
  }

  function costCopy() {
    if (state.featureStatus?.internalAccess) return 'Founder preview · this run is not metered.';
    const included = Number(state.feature?.includedDaily);
    const credits = Number(state.feature?.standardOverflowCredits ?? state.feature?.overflowCredits ?? 0);
    if (included > 0 && credits > 0) {
      return `${included} included run${included === 1 ? '' : 's'} per day on this plan. Ask Crump checks the next run and asks before any credit charge.`;
    }
    if (credits > 0) return 'Ask Crump shows the exact credit charge before this run can start.';
    return 'Ask Crump checks and records the payment source before the task begins.';
  }

  function createStaticShell() {
    if (byId('crumpCodeWorkspace')) return;
    const overlay = document.createElement('div');
    overlay.id = 'crumpCodeWorkspace';
    overlay.className = 'crump-code-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="crump-code-shell" role="dialog" aria-modal="true" aria-labelledby="crumpCodeTitle">
        <header class="crump-code-header">
          <div>
            <span class="crump-code-kicker">CODING AGENT · BETA</span>
            <h2 id="crumpCodeTitle">Autonomous Crump</h2>
            <p>Prepare and verify coding work in a temporary copy of a public GitHub repository. Autonomous Crump receives no Ask Crump credentials and cannot publish or push changes.</p>
          </div>
          <button type="button" id="crumpCodeClose" class="crump-code-icon-button" aria-label="Close Autonomous Crump">×</button>
        </header>
        <div class="crump-code-safety" aria-label="Autonomous Crump safety boundaries">
          <span><b>Isolated</b> temporary microVM</span>
          <span><b>Offline</b> after repository checkout</span>
          <span><b>Reviewable</b> patch and checks</span>
          <span><b>Bounded</b> four-minute maximum</span>
        </div>
        <div id="crumpCodeNotice" class="crump-code-notice" role="status" aria-live="polite" hidden></div>
        <div class="crump-code-layout">
          <aside class="crump-code-sidebar" aria-label="Autonomous Crump tasks">
            <div class="crump-code-sidebar-head">
              <label for="crumpCodeProject">Project</label>
              <button type="button" id="crumpCodeRefresh" class="crump-code-text-button">Refresh</button>
            </div>
            <select id="crumpCodeProject" class="crump-code-control" aria-describedby="crumpCodeProjectHelp"></select>
            <p id="crumpCodeProjectHelp" class="crump-code-help">Code tasks stay attached to one Ask Crump Project.</p>
            <div id="crumpCodeTaskList" class="crump-code-task-list"></div>
          </aside>
          <main class="crump-code-main">
            <section id="crumpCodeComposer" class="crump-code-panel" aria-labelledby="crumpCodeComposerTitle">
              <div class="crump-code-panel-head">
                <div><span>NEW TASK</span><h3 id="crumpCodeComposerTitle">Prepare an isolated task</h3></div>
                <span id="crumpCodeCost" class="crump-code-cost"></span>
              </div>
              <form id="crumpCodeForm">
                <fieldset id="crumpCodeFields">
                  <label>Public GitHub repository
                    <input id="crumpCodeRepository" class="crump-code-control" type="url" required maxlength="500" inputmode="url" autocomplete="url" placeholder="https://github.com/owner/repository">
                  </label>
                  <div class="crump-code-form-row">
                    <label>Mode
                      <select id="crumpCodeMode" class="crump-code-control">
                        <option value="plan">Plan only — no edits</option>
                        <option value="implement">Implement in isolated copy</option>
                      </select>
                    </label>
                    <label>Branch or revision <small>optional</small>
                      <input id="crumpCodeRevision" class="crump-code-control" type="text" maxlength="160" spellcheck="false" placeholder="main">
                    </label>
                  </div>
                  <label>Objective
                    <textarea id="crumpCodeObjective" class="crump-code-control" required maxlength="12000" rows="5" placeholder="Describe the outcome, relevant constraints, and how success should be verified."></textarea>
                  </label>
                  <div class="crump-code-compose-footer">
                    <p>Preparing saves the task for review. It does not start a model or spend credits.</p>
                    <button type="submit" id="crumpCodePrepare" class="crump-code-primary">Prepare task</button>
                  </div>
                </fieldset>
              </form>
              <div id="crumpCodeNoProjects" class="crump-code-empty" hidden>
                <h3>Create a Project first.</h3>
                <p>Projects keep the repository task, patch, and later continuation together.</p>
                <button type="button" id="crumpCodeOpenProjects" class="crump-code-secondary">Open Projects</button>
              </div>
            </section>
            <section id="crumpCodeDetail" class="crump-code-panel crump-code-detail" aria-live="polite" hidden></section>
          </main>
        </div>
      </section>`;
    document.body.appendChild(overlay);
    const main = overlay.querySelector('.crump-code-main');
    const detail = byId('crumpCodeDetail');
    const composer = byId('crumpCodeComposer');
    if (main && detail && composer) main.insertBefore(detail, composer);

    byId('crumpCodeClose')?.addEventListener('click', () => close({restoreFocus: true}));
    overlay.addEventListener('click', event => {
      if (event.target === overlay) close({restoreFocus: true});
    });
    overlay.addEventListener('keydown', trapFocus);
    byId('crumpCodeProject')?.addEventListener('change', event => {
      state.projectId = event.target.value;
      state.task = null;
      void loadTasks();
    });
    byId('crumpCodeRefresh')?.addEventListener('click', () => void refresh());
    byId('crumpCodeForm')?.addEventListener('submit', event => void prepareTask(event));
    byId('crumpCodeTaskList')?.addEventListener('click', event => {
      const button = event.target.closest?.('[data-crump-code-task]');
      if (button) void selectTask(button.dataset.crumpCodeTask);
    });
    byId('crumpCodeOpenProjects')?.addEventListener('click', () => {
      close();
      window.CrumpNavigation5930?.open?.('projects');
    });
    byId('crumpCodeDetail')?.addEventListener('click', event => void handleDetailAction(event));
    byId('crumpCodeDetail')?.addEventListener('change', event => {
      if (event.target.id === 'crumpCodeRunConfirmed') updateRunButton();
    });
  }

  function trapFocus(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close({restoreFocus: true});
      return;
    }
    if (event.key !== 'Tab') return;
    const shell = document.querySelector('#crumpCodeWorkspace .crump-code-shell');
    const focusable = [...(shell?.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href]') || [])]
      .filter(node => !node.closest('[hidden]'));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function hydrateAvailability(data) {
    const feature = data?.features?.code_workspace || null;
    const provider = data?.providers?.code || null;
    state.featureStatus = data || null;
    state.feature = feature;
    state.provider = provider;
    state.configured = Boolean(feature?.configured && provider?.configured);
    state.entitled = feature?.entitled === true;
    state.available = state.configured && state.entitled;
    document.querySelectorAll('[data-crump-code-destination]').forEach(destination => {
      destination.hidden = !state.configured;
      destination.classList.toggle('is-locked', state.configured && !state.entitled);
      destination.setAttribute(
        'aria-label',
        state.configured && !state.entitled ? 'Autonomous Crump — Professional plan' : 'Autonomous Crump',
      );
    });
    document.body.classList.toggle('crump-code-configured', state.configured);
    if (!state.available && !byId('crumpCodeWorkspace')?.hidden) close();
    return state.available;
  }

  async function refreshAvailability() {
    const ownerId = currentOwnerId();
    const epoch = state.navigationEpoch;
    try {
      const data = await api('/api/features');
      if (!ownerId || ownerId !== state.ownerId || ownerId !== currentOwnerId() || epoch !== state.navigationEpoch) {
        return false;
      }
      return hydrateAvailability(data);
    } catch (_) {
      if (ownerId !== state.ownerId || epoch !== state.navigationEpoch) return false;
      return hydrateAvailability(null);
    }
  }

  function renderProjects() {
    const select = byId('crumpCodeProject');
    const fields = byId('crumpCodeFields');
    const empty = byId('crumpCodeNoProjects');
    if (!select || !fields || !empty) return;
    select.replaceChildren();
    if (!state.projects.length) {
      const option = document.createElement('option');
      option.textContent = 'No Projects yet';
      option.value = '';
      select.appendChild(option);
      select.disabled = true;
      fields.hidden = true;
      empty.hidden = false;
      state.projectId = '';
      renderTasks();
      return;
    }
    select.disabled = false;
    fields.hidden = false;
    empty.hidden = true;
    for (const project of state.projects) {
      const option = document.createElement('option');
      option.value = String(project.id || '');
      option.textContent = String(project.name || 'Untitled Project');
      select.appendChild(option);
    }
    if (!state.projects.some(project => String(project.id) === state.projectId)) {
      state.projectId = String(state.projects[0].id || '');
    }
    select.value = state.projectId;
  }

  function renderTasks() {
    const list = byId('crumpCodeTaskList');
    if (!list) return;
    list.replaceChildren();
    if (!state.projectId) return;
    if (!state.tasks.length) {
      const empty = document.createElement('p');
      empty.className = 'crump-code-sidebar-empty';
      empty.textContent = 'No Autonomous Crump tasks in this Project yet.';
      list.appendChild(empty);
      return;
    }
    for (const task of state.tasks) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'crump-code-task';
      if (state.task?.id === task.id) button.classList.add('is-active');
      button.dataset.crumpCodeTask = String(task.id || '');
      const title = document.createElement('strong');
      title.textContent = String(task.objective || 'Untitled Autonomous Crump task').replace(/\s+/g, ' ').trim().slice(0, 90);
      const meta = document.createElement('span');
      meta.textContent = `${statusLabel(task.status, task.failure_code)} · ${formatDate(task.updated_at || task.created_at)}`;
      button.append(title, meta);
      list.appendChild(button);
    }
  }

  function addTextRow(parent, label, value) {
    if (value === undefined || value === null || value === '') return;
    const row = document.createElement('div');
    row.className = 'crump-code-fact';
    const term = document.createElement('span');
    term.textContent = label;
    const detail = document.createElement('strong');
    detail.textContent = String(value);
    row.append(term, detail);
    parent.appendChild(row);
  }

  function renderApprovals(container, task) {
    const approvals = Array.isArray(task.approvals) ? task.approvals.filter(item => item.status === 'pending') : [];
    if (!approvals.length) return;
    const section = document.createElement('section');
    section.className = 'crump-code-result crump-code-approval';
    const heading = document.createElement('h4');
    heading.textContent = 'Approval required';
    section.appendChild(heading);
    for (const approval of approvals) {
      const card = document.createElement('article');
      const title = document.createElement('strong');
      title.textContent = String(approval.title || 'Review this action');
      const detail = document.createElement('p');
      const approvalExpiry = formatDate(approval.expires_at);
      detail.textContent = `${String(approval.details || 'Review the requested boundary before deciding.')}${approvalExpiry ? ` This approval expires ${approvalExpiry}.` : ''}`;
      const actions = document.createElement('div');
      actions.className = 'crump-code-actions';
      for (const [decision, label, tone] of [['denied', 'Deny', 'secondary'], ['approved', 'Approve bounded retry', 'primary']]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `crump-code-${tone}`;
        button.dataset.codeApproval = String(approval.id || '');
        button.dataset.codeDecision = decision;
        button.textContent = label;
        actions.appendChild(button);
      }
      card.append(title, detail, actions);
      section.appendChild(card);
    }
    container.appendChild(section);
  }

  function renderVerification(container, task) {
    const checks = Array.isArray(task.verification) ? task.verification : [];
    if (!checks.length) return;
    const section = document.createElement('section');
    section.className = 'crump-code-result';
    const heading = document.createElement('h4');
    heading.textContent = 'Verification';
    section.appendChild(heading);
    for (const check of checks) {
      const row = document.createElement('div');
      row.className = 'crump-code-check';
      const command = document.createElement('code');
      const args = Array.isArray(check.args) ? check.args.join(' ') : '';
      command.textContent = `${check.command || 'check'} ${args}`.trim();
      const result = document.createElement('span');
      const passed = Number(check.returnCode) === 0;
      result.textContent = passed ? 'Passed' : `Exited ${check.returnCode ?? 'unknown'}`;
      result.dataset.tone = passed ? 'success' : 'danger';
      row.append(command, result);
      section.appendChild(row);
    }
    container.appendChild(section);
  }

  function renderHistory(container, task) {
    const events = Array.isArray(task.events) ? task.events : [];
    if (!events.length) return;
    const details = document.createElement('details');
    details.className = 'crump-code-history';
    const summary = document.createElement('summary');
    summary.textContent = `Activity history (${events.length})`;
    const list = document.createElement('ol');
    for (const event of events) {
      const item = document.createElement('li');
      const name = document.createElement('strong');
      name.textContent = String(event.event_type || 'task.updated').replaceAll('.', ' ');
      const time = document.createElement('span');
      time.textContent = formatDate(event.created_at);
      item.append(name, time);
      list.appendChild(item);
    }
    details.append(summary, list);
    container.appendChild(details);
  }

  function renderDetail() {
    const detail = byId('crumpCodeDetail');
    if (!detail) return;
    detail.replaceChildren();
    const task = state.task;
    detail.hidden = !task;
    if (!task) return;

    const head = document.createElement('div');
    head.className = 'crump-code-detail-head';
    const titleWrap = document.createElement('div');
    const label = document.createElement('span');
    label.textContent = String(task.mode || 'plan').toUpperCase();
    const title = document.createElement('h3');
    title.textContent = String(task.objective || 'Autonomous Crump task');
    titleWrap.append(label, title);
    const badge = document.createElement('span');
    badge.className = 'crump-code-status';
    badge.dataset.status = String(task.status || 'unknown');
    badge.textContent = statusLabel(task.status, task.failure_code);
    head.append(titleWrap, badge);
    detail.appendChild(head);

    const facts = document.createElement('div');
    facts.className = 'crump-code-facts';
    addTextRow(facts, 'Repository', String(task.source_repo_url || '').replace(/\.git$/, ''));
    addTextRow(facts, 'Revision', task.source_ref || 'Default branch');
    addTextRow(facts, 'Network', task.network_policy === 'deny_all' ? 'Blocked after checkout' : task.network_policy);
    addTextRow(facts, 'Maximum', `${task.max_duration_seconds || state.provider?.maxDurationSeconds || 180} seconds`);
    addTextRow(facts, 'Expires', formatDate(task.expires_at));
    addTextRow(facts, 'Charge', task.payment_source ? `${task.payment_source}${Number(task.credits_spent) ? ` · ${task.credits_spent} credits` : ''}` : 'Not started');
    detail.appendChild(facts);

    renderApprovals(detail, task);

    if (task.result_summary) {
      const result = document.createElement('section');
      result.className = 'crump-code-result';
      const heading = document.createElement('h4');
      heading.textContent = 'Result';
      const copy = document.createElement('p');
      copy.className = 'crump-code-summary';
      copy.textContent = String(task.result_summary);
      result.append(heading, copy);
      detail.appendChild(result);
    }
    renderVerification(detail, task);

    if (task.result_patch) {
      const patch = document.createElement('details');
      patch.className = 'crump-code-patch';
      const summary = document.createElement('summary');
      summary.textContent = 'Review patch';
      const pre = document.createElement('pre');
      pre.textContent = String(task.result_patch);
      const download = document.createElement('button');
      download.type = 'button';
      download.className = 'crump-code-secondary';
      download.dataset.codeAction = 'download';
      download.textContent = 'Download .patch';
      patch.append(summary, pre, download);
      detail.appendChild(patch);
    }

    if (task.failure_code) {
      const failure = document.createElement('p');
      failure.className = 'crump-code-failure';
      failure.textContent = `Stopped safely: ${String(task.failure_code).replaceAll('_', ' ').toLowerCase()}.`;
      detail.appendChild(failure);
    }

    if (task.status === 'queued') {
      const review = document.createElement('section');
      review.className = 'crump-code-run-review';
      const heading = document.createElement('h4');
      heading.textContent = 'Final run confirmation';
      const copy = document.createElement('p');
      copy.textContent = `${costCopy()} The repository copy is destroyed when the bounded run ends; no change is pushed.`;
      const labelNode = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.id = 'crumpCodeRunConfirmed';
      const textNode = document.createElement('span');
      textNode.textContent = 'I reviewed the repository, objective, mode, and cost boundary.';
      labelNode.append(checkbox, textNode);
      const run = document.createElement('button');
      run.type = 'button';
      run.id = 'crumpCodeRun';
      run.className = 'crump-code-primary';
      run.dataset.codeAction = 'run';
      run.disabled = true;
      run.textContent = 'Run isolated task';
      review.append(heading, copy, labelNode, run);
      detail.appendChild(review);
    }

    if (ACTIVE.has(String(task.status || '')) && task.status !== 'queued') {
      const actions = document.createElement('div');
      actions.className = 'crump-code-actions crump-code-cancel-row';
      const progress = document.createElement('p');
      progress.textContent = task.status === 'awaiting_approval'
        ? 'Review the requested boundary above.'
        : 'You can request cancellation. Autonomous Crump checks that request before each next model or tool step.';
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'crump-code-danger';
      cancel.dataset.codeAction = 'cancel';
      cancel.textContent = 'Cancel task';
      actions.append(progress, cancel);
      detail.appendChild(actions);
    }

    renderHistory(detail, task);
  }

  function resetWorkspaceState(ownerId = '') {
    state.navigationEpoch += 1;
    stopPolling();
    state.ownerId = String(ownerId || '').trim();
    state.projects = [];
    state.projectId = '';
    state.tasks = [];
    state.task = null;
    for (const id of ['crumpCodeRepository', 'crumpCodeRevision', 'crumpCodeObjective']) {
      const control = byId(id);
      if (control) control.value = '';
    }
    renderProjects();
    renderTasks();
    renderDetail();
    setNotice('');
  }

  function updateRunButton() {
    const button = byId('crumpCodeRun');
    const checkbox = byId('crumpCodeRunConfirmed');
    if (button) button.disabled = !checkbox?.checked;
  }

  function activityStatus(task) {
    const status = String(task?.status || '').trim().toLowerCase();
    if (status === 'queued') return task?.payment_source ? 'queued' : '';
    if (status === 'provisioning' || status === 'running' || status === 'verifying') return 'running';
    if (status === 'completed') return 'ready';
    if (status === 'awaiting_approval' || status === 'failed' || status === 'cancelled') return 'failed';
    return '';
  }

  function reportTaskActivity(task) {
    const status = activityStatus(task);
    const taskId = String(task?.id || '').trim();
    const projectId = String(task?.project_id || state.projectId || '').trim();
    if (!status || !taskId || !projectId) return false;
    return window.CrumpActivityCenter?.report?.({
      id: `code:${taskId}`,
      taskId,
      projectId,
      codeStatus: String(task.status || '').trim().toLowerCase(),
      source: 'code',
      kind: 'code',
      status,
      createdAt: task.created_at,
      updatedAt: task.completed_at || task.updated_at || task.created_at,
    }) || false;
  }

  function applyTask(task, {render = true} = {}) {
    if (!task || typeof task !== 'object' || !task.id) return null;
    const index = state.tasks.findIndex(item => item.id === task.id);
    const merged = index >= 0 ? {...state.tasks[index], ...task} : {...task};
    if (index >= 0) state.tasks[index] = merged;
    else state.tasks.unshift(merged);
    state.task = merged;
    reportTaskActivity(merged);
    if (render) {
      renderTasks();
      renderDetail();
    }
    return merged;
  }

  async function loadProjects({projectId = '', taskId = ''} = {}, context = null) {
    const requestContext = context || beginNavigation();
    setNotice('Loading Projects…');
    try {
      const data = await api('/api/projects');
      if (!navigationIsCurrent(requestContext)) return false;
      state.projects = Array.isArray(data.projects) ? data.projects : [];
      const requestedProjectId = String(projectId || '').trim();
      if (requestedProjectId && state.projects.some(project => String(project.id) === requestedProjectId)) {
        state.projectId = requestedProjectId;
      }
      renderProjects();
      await loadTasks(String(taskId || '').trim(), requestContext);
      if (!navigationIsCurrent(requestContext)) return false;
      setNotice('');
      return true;
    } catch (error) {
      if (navigationIsCurrent(requestContext)) setNotice(error.message, 'danger');
      return false;
    }
  }

  async function loadTasks(targetTaskId = '', context = null) {
    const requestContext = context || beginNavigation();
    const projectId = state.projectId;
    if (!navigationIsCurrent(requestContext)) return false;
    stopPolling();
    state.tasks = [];
    state.task = null;
    renderTasks();
    renderDetail();
    if (!projectId) return false;
    setNotice('Loading Autonomous Crump tasks…');
    try {
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/code/tasks`);
      if (!navigationIsCurrent(requestContext) || state.projectId !== projectId) return false;
      state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
      renderTasks();
      const requestedTaskId = String(targetTaskId || '').trim();
      const selectedTaskId = requestedTaskId || state.tasks[0]?.id || '';
      if (selectedTaskId) {
        await selectTask(selectedTaskId, {
          quiet: true,
          context: requestContext,
          projectId,
        });
      }
      if (!navigationIsCurrent(requestContext) || state.projectId !== projectId) return false;
      setNotice('');
      return true;
    } catch (error) {
      if (navigationIsCurrent(requestContext) && state.projectId === projectId) {
        setNotice(error.message, 'danger');
      }
      return false;
    }
  }

  async function selectTask(taskId, {quiet = false, context = null, projectId = state.projectId} = {}) {
    if (!taskId) return;
    const requestContext = context || beginNavigation();
    const expectedProjectId = String(projectId || '').trim();
    stopPolling();
    if (!quiet) setNotice('Loading task…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}`);
      if (!navigationIsCurrent(requestContext) || state.projectId !== expectedProjectId) return false;
      const returnedProjectId = String(data.task?.project_id || expectedProjectId || '').trim();
      if (expectedProjectId && returnedProjectId !== expectedProjectId) {
        throw new Error('That task no longer belongs to the selected Project.');
      }
      applyTask(data.task || null);
      if (shouldPollTask()) startPolling(state.task.id);
      else stopPolling();
      if (!quiet) setNotice('');
      return true;
    } catch (error) {
      if (navigationIsCurrent(requestContext) && state.projectId === expectedProjectId) {
        setNotice(error.message, 'danger');
      }
      return false;
    }
  }

  async function prepareTask(event) {
    event.preventDefault();
    if (!state.projectId) return setNotice('Choose a Project first.', 'danger');
    const requestContext = beginNavigation();
    const projectId = state.projectId;
    const button = byId('crumpCodePrepare');
    const restore = setButtonBusy(button, true, 'Preparing…');
    setNotice('');
    try {
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/code/tasks`, {
        method: 'POST',
        body: {
          repositoryUrl: byId('crumpCodeRepository')?.value.trim(),
          revision: byId('crumpCodeRevision')?.value.trim(),
          objective: byId('crumpCodeObjective')?.value.trim(),
          mode: byId('crumpCodeMode')?.value || 'plan',
          maxDurationSeconds: Number(state.provider?.maxDurationSeconds || 180),
        },
      });
      if (!navigationIsCurrent(requestContext) || state.projectId !== projectId) return;
      applyTask(data.task);
      byId('crumpCodeObjective').value = '';
      await loadTasks(data.task.id, requestContext);
      if (!navigationIsCurrent(requestContext) || state.projectId !== projectId) return;
      setNotice('Task prepared. Review every field before starting the isolated run.', 'success');
    } catch (error) {
      if (navigationIsCurrent(requestContext)) setNotice(error.message, 'danger');
    } finally {
      restore();
    }
  }

  async function runTask(button) {
    if (!state.task?.id || !byId('crumpCodeRunConfirmed')?.checked) return;
    const taskId = state.task.id;
    const requestContext = currentNavigation();
    const restore = setButtonBusy(button, true, 'Submitting…');
    setNotice('Submitting the confirmed task to the private worker…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}/run`, {
        method: 'POST', body: {confirmed: true},
      });
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      applyTask(data.task);
      setNotice('Task accepted. You can close this window; Autonomous Crump will continue safely.', 'success');
      startPolling(taskId);
    } catch (error) {
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      stopPolling();
      await selectTask(taskId, {
        quiet: true,
        context: requestContext,
        projectId: state.projectId,
      });
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      setNotice(error.message, error.code === 'CODE_TASK_CANCELLED' ? '' : 'danger');
    } finally {
      restore();
    }
  }

  async function cancelTask(button) {
    if (!state.task?.id) return;
    const taskId = state.task.id;
    const requestContext = currentNavigation();
    const restore = setButtonBusy(button, true, 'Cancelling…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}/cancel`, {
        method: 'POST', body: {},
      });
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      applyTask(data.task);
      await selectTask(data.task.id, {
        quiet: true,
        context: requestContext,
        projectId: state.projectId,
      });
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      stopPolling();
      setNotice('Cancellation recorded. The bounded workspace will shut down without publishing changes.', 'success');
    } catch (error) {
      if (navigationIsCurrent(requestContext) && state.task?.id === taskId) {
        setNotice(error.message, 'danger');
      }
    } finally {
      restore();
    }
  }

  async function decideApproval(button) {
    const approvalId = button.dataset.codeApproval;
    const decision = button.dataset.codeDecision;
    if (!state.task?.id || !approvalId || !decision) return;
    const taskId = state.task.id;
    const requestContext = currentNavigation();
    const restore = setButtonBusy(button, true, decision === 'approved' ? 'Approving…' : 'Denying…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}/approvals/${encodeURIComponent(approvalId)}`, {
        method: 'POST', body: {decision},
      });
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      applyTask(data.task);
      await selectTask(data.task.id, {
        quiet: true,
        context: requestContext,
        projectId: state.projectId,
      });
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      setNotice(decision === 'approved' ? 'Bounded retry approved. Review it again before running.' : 'Request denied and task cancelled.', 'success');
    } catch (error) {
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      if (error.code === 'CODE_APPROVAL_EXPIRED') {
        await selectTask(taskId, {
          quiet: true,
          context: requestContext,
          projectId: state.projectId,
        });
      }
      if (!navigationIsCurrent(requestContext) || state.task?.id !== taskId) return;
      setNotice(error.message, 'danger');
    } finally {
      restore();
    }
  }

  function downloadPatch() {
    if (!state.task?.result_patch) return;
    const blob = new Blob([String(state.task.result_patch)], {type: 'text/x-diff;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `autonomous-crump-${String(state.task.id || 'change').slice(0, 8)}.patch`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function handleDetailAction(event) {
    const approval = event.target.closest?.('[data-code-approval]');
    if (approval) return decideApproval(approval);
    const button = event.target.closest?.('[data-code-action]');
    if (!button) return;
    if (button.dataset.codeAction === 'run') await runTask(button);
    else if (button.dataset.codeAction === 'cancel') await cancelTask(button);
    else if (button.dataset.codeAction === 'download') downloadPatch();
  }

  function stopPolling() {
    state.pollGeneration += 1;
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = 0;
    state.pollController?.abort?.();
    state.pollController = null;
    state.pollFailureCount = 0;
  }

  function shouldPollTask(task = state.task) {
    const status = String(task?.status || '');
    return ACTIVE.has(status) && (status !== 'queued' || Boolean(task?.payment_source));
  }

  function startPolling(taskId, {immediate = false} = {}) {
    stopPolling();
    const generation = state.pollGeneration;
    const ownerId = state.ownerId;
    const schedule = delay => {
      if (generation !== state.pollGeneration) return;
      state.pollTimer = window.setTimeout(poll, delay);
    };
    const poll = async () => {
      state.pollTimer = 0;
      if (
        generation !== state.pollGeneration
        || ownerId !== state.ownerId
        || ownerId !== currentOwnerId()
        || document.hidden
        || byId('crumpCodeWorkspace')?.hidden
        || state.task?.id !== taskId
      ) return;
      const controller = new AbortController();
      state.pollController = controller;
      const timeout = window.setTimeout(() => controller.abort(), POLL_TIMEOUT_MS);
      try {
        const data = await apiOnce(`/api/code/tasks/${encodeURIComponent(taskId)}`, {
          signal: controller.signal,
        });
        if (generation !== state.pollGeneration || ownerId !== state.ownerId || state.task?.id !== taskId) return;
        applyTask(data.task || state.task);
        state.pollFailureCount = 0;
        if (!shouldPollTask()) {
          if (state.task?.status === 'completed') {
            setNotice('Autonomous Crump finished. Review the result, checks, and patch before using it.', 'success');
          } else if (state.task?.status === 'failed') {
            setNotice('Autonomous Crump stopped safely. Review the task history before retrying.', 'danger');
          } else if (state.task?.status === 'cancelled') {
            setNotice('Cancellation recorded. No source changes were published.');
          }
          return;
        }
      } catch (_) {
        if (
          generation !== state.pollGeneration
          || ownerId !== state.ownerId
          || document.hidden
          || byId('crumpCodeWorkspace')?.hidden
          || state.task?.id !== taskId
        ) return;
        state.pollFailureCount = Math.min(state.pollFailureCount + 1, 4);
        setNotice('Status refresh is delayed. The durable task continues safely; Ask Crump will retry.', '');
      } finally {
        window.clearTimeout(timeout);
        if (state.pollController === controller) state.pollController = null;
      }
      if (
        generation !== state.pollGeneration
        || ownerId !== state.ownerId
        || document.hidden
        || byId('crumpCodeWorkspace')?.hidden
        || state.task?.id !== taskId
        || !shouldPollTask()
      ) return;
      schedule(Math.min(POLL_MAX_MS, POLL_BASE_MS * (2 ** state.pollFailureCount)));
    };
    schedule(immediate ? 0 : POLL_INITIAL_MS);
  }

  async function refresh() {
    const ownerId = currentOwnerId();
    if (ownerId !== state.ownerId) resetWorkspaceState(ownerId);
    if (!(await refreshAvailability())) return setNotice('Autonomous Crump is not available for this account.', 'danger');
    await loadProjects();
  }

  async function open({projectId = '', taskId = ''} = {}) {
    createStaticShell();
    const ownerId = currentOwnerId();
    if (!ownerId) return false;
    if (ownerId !== state.ownerId) resetWorkspaceState(ownerId);
    const requestContext = beginNavigation();
    if (!(await refreshAvailability())) {
      if (!navigationIsCurrent(requestContext)) return false;
      if (state.configured && !state.entitled) {
        const modal = window.showBillingCenter?.({plan: 'professional'});
        if (!modal) window.showUpgradePrompt?.({plan: 'professional'});
      } else {
        window.showToast?.('Autonomous Crump is still in beta.', 'info');
      }
      return false;
    }
    if (!navigationIsCurrent(requestContext)) return false;
    const overlay = byId('crumpCodeWorkspace');
    state.restoreFocus = document.activeElement;
    overlay.hidden = false;
    document.body.classList.add('crump-code-open');
    byId('crumpCodeCost').textContent = costCopy();
    requestAnimationFrame(() => byId('crumpCodeClose')?.focus({preventScroll: true}));
    await loadProjects({projectId, taskId}, requestContext);
    if (!navigationIsCurrent(requestContext)) return false;
    return true;
  }

  function close({restoreFocus = false} = {}) {
    const overlay = byId('crumpCodeWorkspace');
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.classList.remove('crump-code-open');
    stopPolling();
    if (restoreFocus) state.restoreFocus?.focus?.({preventScroll: true});
    state.restoreFocus = null;
  }

  window.CrumpCodeWorkspace = Object.freeze({open, close, refresh, refreshAvailability, hydrateAvailability});

  const bootstrapStatus = window.__crumpCodeBootstrapStatus || null;
  delete window.__crumpCodeBootstrapStatus;

  function initialize() {
    createStaticShell();
    if (currentOwnerId() && currentOwnerId() !== state.ownerId) {
      resetWorkspaceState(currentOwnerId());
    }
    // The lazy loader applies its server-confirmed status only after both the
    // script and stylesheet are ready, so a newly revealed destination cannot
    // open an unstyled workspace.
    if (!bootstrapStatus && window.currentUser) void refreshAvailability();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, {once: true});
  } else initialize();
  window.addEventListener('crump:authenticated-ready', () => {
    const ownerId = currentOwnerId();
    if (ownerId !== state.ownerId) resetWorkspaceState(ownerId);
    if (!window.CrumpCodeLoader) void refreshAvailability();
  });
  window.addEventListener('crump:authentication-required', () => {
    close();
    resetWorkspaceState('');
  });
  window.addEventListener('online', () => {
    if (!byId('crumpCodeWorkspace')?.hidden && shouldPollTask()) {
      startPolling(state.task.id, {immediate: true});
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopPolling();
      return;
    }
    if (!byId('crumpCodeWorkspace')?.hidden && shouldPollTask()) {
      startPolling(state.task.id, {immediate: true});
    }
  });
})();
