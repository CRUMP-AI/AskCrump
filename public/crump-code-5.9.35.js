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
    selectedTaskId: '',
    restoreFocus: null,
    projectsRequestGeneration: 0,
    tasksRequestGeneration: 0,
    taskRequestGeneration: 0,
    pollTimer: 0,
    pollGeneration: 0,
    pollFailures: 0,
    selectedDiffPath: '',
  };
  const ACTIVE = new Set(['queued', 'provisioning', 'running', 'awaiting_approval', 'verifying']);
  const STATUS_LABELS = Object.freeze({
    queued: 'Prepared for review',
    provisioning: 'Starting isolated workspace',
    running: 'Working in isolated copy',
    awaiting_approval: 'Paused at unsupported boundary',
    verifying: 'Verifying the change',
    completed: 'Review required',
    failed: 'Failed safely',
    cancelled: 'Cancelled',
  });
  const PROGRESS_STAGES = Object.freeze([
    ['queued', 'Prepared'],
    ['provisioning', 'Accepted'],
    ['running', 'Working'],
    ['verifying', 'Verifying'],
    ['completed', 'Review required'],
  ]);

  async function apiOnce(path, options = {}) {
    const request = {
      credentials: 'same-origin',
      method: options.method || 'GET',
      headers: {Accept: 'application/json'},
    };
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

  function resultSemantics(task) {
    if (String(task?.status || '') !== 'completed') return null;
    const checks = Array.isArray(task.verification) ? task.verification : [];
    const failed = checks.filter(check => Number(check.returnCode) !== 0);
    const patch = String(task.result_patch || '');
    if (String(task.mode || '') === 'plan') {
      return {
        label: 'Plan requires review',
        detail: 'Plan-only mode made no source changes. Review the recommendations before acting on them.',
      };
    }
    if (!patch.trim()) {
      return {
        label: 'No change produced',
        detail: 'The run ended without a downloadable patch. Nothing is ready to apply.',
      };
    }
    if (!checks.length) {
      return {
        label: 'Unverified patch',
        detail: 'A patch was produced, but no verification check was recorded. Treat it as unverified.',
      };
    }
    if (failed.length) {
      return {
        label: 'Verification failed',
        detail: 'One or more recorded checks failed. Do not apply the patch without correcting and rerunning them.',
      };
    }
    return {
      label: 'Review required',
      detail: `${checks.length} recorded check${checks.length === 1 ? '' : 's'} passed. Review the complete patch and evidence before applying it.`,
    };
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
            <span class="crump-code-kicker">AUTONOMOUS CRUMP · PRIVATE PREVIEW</span>
            <h2 id="crumpCodeTitle">Delegate repository work. Keep final control.</h2>
            <p>No Ask Crump or account credentials are injected. Public repository contents and check output may be sent to the configured coding model, so use only source you are authorized and prepared to share. This preview remains disabled while source, security, cost, and recovery boundaries are independently verified.</p>
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
      setProjectSelection(event.target.value, {invalidateProjects: true});
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
    try {
      return hydrateAvailability(await api('/api/features'));
    } catch (_) {
      return hydrateAvailability(null);
    }
  }

  function setProjectSelection(projectId, {invalidateProjects = false} = {}) {
    if (invalidateProjects) state.projectsRequestGeneration += 1;
    const nextProjectId = String(projectId || '');
    if (state.projectId === nextProjectId) return;
    state.projectId = nextProjectId;
    state.tasksRequestGeneration += 1;
    state.taskRequestGeneration += 1;
    state.selectedTaskId = '';
    state.selectedDiffPath = '';
    state.tasks = [];
    state.task = null;
    stopPolling();
    renderTasks();
    renderDetail();
  }

  function ownsTaskRequest(taskId, generation) {
    return generation === state.taskRequestGeneration
      && String(taskId || '') === state.selectedTaskId;
  }

  function ownsRenderedTask(taskId, generation = state.taskRequestGeneration) {
    return ownsTaskRequest(taskId, generation)
      && String(state.task?.id || '') === state.selectedTaskId;
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
      setProjectSelection('');
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
      setProjectSelection(String(state.projects[0].id || ''));
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
      empty.textContent = 'No code tasks in this Project yet.';
      list.appendChild(empty);
      return;
    }
    for (const task of state.tasks) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'crump-code-task';
      if (state.selectedTaskId === String(task.id || '')) button.classList.add('is-active');
      button.dataset.crumpCodeTask = String(task.id || '');
      const title = document.createElement('strong');
      title.textContent = String(task.objective || 'Untitled code task').replace(/\s+/g, ' ').trim().slice(0, 90);
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

  function cleanDiffPath(value) {
    let path = String(value || '').trim();
    if (path.startsWith('"') && path.endsWith('"')) path = path.slice(1, -1);
    if (path === '/dev/null') return '';
    if (path.startsWith('a/') || path.startsWith('b/')) path = path.slice(2);
    return path.replace(/[\r\n\0]/g, '').slice(0, 240);
  }

  function parseUnifiedPatch(value) {
    const patch = String(value || '').replace(/\r\n?/g, '\n').slice(0, 200000);
    if (!patch.trim()) return [];
    const files = [];
    let current = null;
    const finish = () => {
      if (!current) return;
      current.path = current.newPath || current.oldPath || `Change ${files.length + 1}`;
      current.kind = !current.oldPath ? 'added'
        : !current.newPath ? 'deleted'
          : current.oldPath !== current.newPath ? 'renamed' : 'modified';
      current.text = current.lines.join('\n').slice(0, 200000);
      delete current.lines;
      files.push(current);
    };
    for (const line of patch.split('\n')) {
      if (line.startsWith('diff --git ')) {
        finish();
        current = {oldPath: '', newPath: '', added: 0, removed: 0, lines: [line]};
        continue;
      }
      if (!current) current = {oldPath: '', newPath: '', added: 0, removed: 0, lines: []};
      current.lines.push(line);
      if (line.startsWith('--- ')) current.oldPath = cleanDiffPath(line.slice(4));
      else if (line.startsWith('+++ ')) current.newPath = cleanDiffPath(line.slice(4));
      else if (line.startsWith('+')) current.added += 1;
      else if (line.startsWith('-')) current.removed += 1;
    }
    finish();
    return files.slice(0, 80);
  }

  function latestProgressCopy(task) {
    const events = Array.isArray(task.events) ? task.events : [];
    const latest = events[events.length - 1] || null;
    const payload = latest?.payload && typeof latest.payload === 'object' ? latest.payload : {};
    const eventType = String(latest?.event_type || '');
    if (eventType === 'tool.requested') {
      if (payload.path) return `Inspecting ${String(payload.path).slice(0, 160)}`;
      if (payload.command) return `Running ${String(payload.command).slice(0, 120)}`;
      return 'Inspecting the repository';
    }
    if (eventType === 'tool.completed') return 'Repository step completed';
    if (eventType === 'verification.started') return 'Running bounded verification';
    if (eventType === 'verification.completed') return 'Verification evidence recorded';
    if (eventType === 'task.requeued') return 'Retry scheduled without another charge';
    if (eventType === 'approval.requested') return 'Paused at an unsupported boundary';
    if (eventType === 'task.completed') return 'Result saved for required review';
    if (eventType === 'task.cancelled') return 'Cancellation recorded';
    if (eventType === 'task.failed') return 'The run stopped safely';
    return statusLabel(task.status, task.failure_code);
  }

  function renderProgress(container, task) {
    const status = String(task.status || 'queued');
    const activeIndex = status === 'awaiting_approval'
      ? 2
      : Math.max(0, PROGRESS_STAGES.findIndex(([value]) => value === status));
    const terminalFailure = status === 'failed' || status === 'cancelled';
    const section = document.createElement('section');
    section.className = 'crump-code-progress';
    section.setAttribute('aria-label', 'Durable task progress');
    const head = document.createElement('div');
    head.className = 'crump-code-progress-head';
    const heading = document.createElement('h4');
    heading.textContent = terminalFailure ? statusLabel(status, task.failure_code) : 'Durable run progress';
    const connection = document.createElement('span');
    connection.className = 'crump-code-connection';
    connection.dataset.tone = state.pollFailures ? 'recovering' : 'connected';
    connection.textContent = state.pollFailures ? 'Reconnecting' : 'Saved to Project';
    head.append(heading, connection);
    const stages = document.createElement('ol');
    stages.className = 'crump-code-progress-stages';
    for (const [stageStatus, label] of PROGRESS_STAGES) {
      const stage = document.createElement('li');
      const index = PROGRESS_STAGES.findIndex(([value]) => value === stageStatus);
      const completed = !terminalFailure && index < activeIndex;
      const current = !terminalFailure && index === activeIndex;
      stage.dataset.state = completed ? 'complete' : current ? 'current' : 'pending';
      if (current) stage.setAttribute('aria-current', 'step');
      const marker = document.createElement('span');
      marker.setAttribute('aria-hidden', 'true');
      marker.textContent = completed ? '✓' : String(index + 1);
      const text = document.createElement('strong');
      text.textContent = label;
      stage.append(marker, text);
      stages.appendChild(stage);
    }
    const latest = document.createElement('p');
    latest.className = 'crump-code-progress-latest';
    const updated = formatDate(task.updated_at);
    latest.textContent = `${latestProgressCopy(task)}${updated ? ` · Updated ${updated}` : ''}`;
    const continuity = document.createElement('p');
    continuity.className = 'crump-code-progress-continuity';
    continuity.textContent = ACTIVE.has(status) && status !== 'queued'
      ? 'You can close this window or explore Ask Crump. The private worker continues, and this Project keeps the latest status.'
      : 'This task, its checks, and its review state remain attached to this Project.';
    section.append(head, stages, latest, continuity);
    container.appendChild(section);
  }

  function renderApprovals(container, task) {
    const approvals = Array.isArray(task.approvals) ? task.approvals.filter(item => item.status === 'pending') : [];
    if (!approvals.length) return;
    const section = document.createElement('section');
    section.className = 'crump-code-result crump-code-approval';
    const heading = document.createElement('h4');
    heading.textContent = 'Unsupported boundary reached';
    section.appendChild(heading);
    for (const approval of approvals) {
      const card = document.createElement('article');
      const title = document.createElement('strong');
      title.textContent = String(approval.title || 'Review this action');
      const detail = document.createElement('p');
      const approvalExpiry = formatDate(approval.expires_at);
      detail.textContent = `${String(approval.details || 'The run reached a boundary this preview cannot resume safely.')}${approvalExpiry ? ` The recorded request expires ${approvalExpiry}.` : ''} No approval action is available; cancel this task and prepare a narrower objective.`;
      card.append(title, detail);
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
      const row = document.createElement('details');
      row.className = 'crump-code-check';
      const summary = document.createElement('summary');
      const command = document.createElement('code');
      const args = Array.isArray(check.args) ? check.args.join(' ') : '';
      const commandText = String(check.command || 'check');
      command.textContent = `${commandText}${args && !commandText.includes(' ') ? ` ${args}` : ''}`.slice(0, 1000);
      const result = document.createElement('span');
      const passed = Number(check.returnCode) === 0;
      row.dataset.status = passed ? 'passed' : 'failed';
      result.textContent = passed ? 'Passed' : `Exited ${check.returnCode ?? 'unknown'}`;
      result.dataset.tone = passed ? 'success' : 'danger';
      summary.append(command, result);
      row.appendChild(summary);
      const output = [check.stdout, check.stderr]
        .map(value => String(value || '').trim())
        .filter(Boolean)
        .join('\n\n')
        .slice(0, 8000);
      if (output) {
        const pre = document.createElement('pre');
        pre.textContent = output;
        row.appendChild(pre);
      }
      section.appendChild(row);
    }
    container.appendChild(section);
  }

  function renderPatch(container, task) {
    const files = parseUnifiedPatch(task.result_patch);
    if (!files.length) return;
    if (!files.some(file => file.path === state.selectedDiffPath)) {
      state.selectedDiffPath = files[0].path;
    }
    const selected = files.find(file => file.path === state.selectedDiffPath) || files[0];
    const added = files.reduce((total, file) => total + file.added, 0);
    const removed = files.reduce((total, file) => total + file.removed, 0);
    const section = document.createElement('section');
    section.className = 'crump-code-diff';
    const head = document.createElement('div');
    head.className = 'crump-code-diff-head';
    const heading = document.createElement('h4');
    heading.textContent = `Changes · ${files.length} file${files.length === 1 ? '' : 's'}`;
    const totals = document.createElement('span');
    totals.className = 'crump-code-diff-totals';
    totals.innerHTML = `<b>+${added}</b><i>−${removed}</i>`;
    head.append(heading, totals);

    const body = document.createElement('div');
    body.className = 'crump-code-diff-layout';
    const fileList = document.createElement('div');
    fileList.className = 'crump-code-diff-files';
    fileList.setAttribute('aria-label', 'Changed files');
    for (const file of files) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.codeAction = 'diff-file';
      button.dataset.diffPath = file.path;
      button.className = 'crump-code-diff-file';
      button.classList.toggle('is-active', file.path === selected.path);
      button.setAttribute('aria-pressed', file.path === selected.path ? 'true' : 'false');
      const path = document.createElement('span');
      path.textContent = file.path;
      const stats = document.createElement('small');
      stats.innerHTML = `<b>+${file.added}</b><i>−${file.removed}</i>`;
      button.append(path, stats);
      fileList.appendChild(button);
    }
    const viewer = document.createElement('div');
    viewer.className = 'crump-code-diff-viewer';
    const viewerHead = document.createElement('div');
    const path = document.createElement('strong');
    path.textContent = selected.path;
    const kind = document.createElement('span');
    kind.textContent = selected.kind;
    viewerHead.append(path, kind);
    const pre = document.createElement('pre');
    pre.setAttribute('aria-label', `Patch for ${selected.path}`);
    for (const line of selected.text.split('\n')) {
      const row = document.createElement('span');
      row.className = line.startsWith('+') && !line.startsWith('+++') ? 'is-added'
        : line.startsWith('-') && !line.startsWith('---') ? 'is-removed'
          : line.startsWith('@@') ? 'is-hunk' : '';
      row.textContent = `${line}\n`;
      pre.appendChild(row);
    }
    viewer.append(viewerHead, pre);
    body.append(fileList, viewer);

    const actions = document.createElement('div');
    actions.className = 'crump-code-actions crump-code-diff-actions';
    const boundary = document.createElement('p');
    boundary.textContent = 'Nothing is pushed. Review or download the complete patch before applying it.';
    const download = document.createElement('button');
    download.type = 'button';
    download.className = 'crump-code-secondary';
    download.dataset.codeAction = 'download';
    download.textContent = 'Download .patch';
    actions.append(boundary, download);
    section.append(head, body, actions);
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
    const task = String(state.task?.id || '') === state.selectedTaskId ? state.task : null;
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
    const outcome = resultSemantics(task);
    badge.textContent = outcome?.label || statusLabel(task.status, task.failure_code);
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

    renderProgress(detail, task);

    renderApprovals(detail, task);

    if (outcome) {
      const qualifier = document.createElement('p');
      qualifier.className = 'crump-code-failure';
      qualifier.textContent = outcome.detail;
      detail.appendChild(qualifier);
    }

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

    if (task.result_patch) renderPatch(detail, task);

    if (task.failure_code) {
      const failure = document.createElement('p');
      failure.className = 'crump-code-failure';
      const paymentCopy = task.payment_source === 'refunded'
        ? 'The recorded charge or allowance was returned.'
        : task.payment_source === 'refund_pending'
          ? 'Refund reconciliation is pending in the private worker.'
          : 'No usable result is being presented as ready.';
      failure.textContent = `Stopped safely: ${String(task.failure_code).replaceAll('_', ' ').toLowerCase()}. ${paymentCopy} Review the recorded evidence, then prepare a new task.`;
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
        ? 'This preview cannot resume from the recorded boundary. Cancel it and prepare a narrower objective.'
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

  function updateRunButton() {
    const button = byId('crumpCodeRun');
    const checkbox = byId('crumpCodeRunConfirmed');
    if (button) button.disabled = !checkbox?.checked;
  }

  async function loadProjects() {
    const generation = ++state.projectsRequestGeneration;
    setNotice('Loading Projects…');
    try {
      const data = await api('/api/projects');
      if (generation !== state.projectsRequestGeneration) return;
      state.projects = Array.isArray(data.projects) ? data.projects : [];
      renderProjects();
      if (generation !== state.projectsRequestGeneration) return;
      await loadTasks();
      if (generation === state.projectsRequestGeneration) setNotice('');
    } catch (error) {
      if (generation === state.projectsRequestGeneration) setNotice(error.message, 'danger');
    }
  }

  async function loadTasks({preferredTaskId = ''} = {}) {
    const projectId = state.projectId;
    const generation = ++state.tasksRequestGeneration;
    const previousTaskId = String(preferredTaskId || state.selectedTaskId || '');
    state.taskRequestGeneration += 1;
    state.selectedTaskId = '';
    state.selectedDiffPath = '';
    state.tasks = [];
    state.task = null;
    stopPolling();
    renderTasks();
    renderDetail();
    if (!projectId) return;
    setNotice('Loading code tasks…');
    try {
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/code/tasks`);
      if (generation !== state.tasksRequestGeneration || state.projectId !== projectId) return;
      state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
      renderTasks();
      const selected = state.tasks.find(task => String(task.id || '') === previousTaskId)
        || state.tasks[0];
      if (selected) await selectTask(selected.id, {quiet: true, expectedProjectId: projectId});
      if (generation === state.tasksRequestGeneration && state.projectId === projectId) setNotice('');
    } catch (error) {
      if (generation === state.tasksRequestGeneration && state.projectId === projectId) {
        setNotice(error.message, 'danger');
      }
    }
  }

  async function selectTask(taskId, {quiet = false, expectedProjectId = state.projectId} = {}) {
    const requestedTaskId = String(taskId || '');
    const projectId = String(expectedProjectId || '');
    if (!requestedTaskId || projectId !== state.projectId) return;
    stopPolling();
    const generation = ++state.taskRequestGeneration;
    state.selectedTaskId = requestedTaskId;
    state.selectedDiffPath = '';
    state.task = null;
    renderTasks();
    renderDetail();
    if (!quiet) setNotice('Loading task…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(requestedTaskId)}`);
      if (!ownsTaskRequest(requestedTaskId, generation) || state.projectId !== projectId) return;
      if (String(data.task?.id || '') !== requestedTaskId
          || (data.task?.project_id && String(data.task.project_id) !== projectId)) {
        setNotice('The selected task response did not match this Project.', 'danger');
        return;
      }
      state.task = data.task || null;
      const index = state.tasks.findIndex(item => item.id === state.task?.id);
      if (index >= 0) state.tasks[index] = {...state.tasks[index], ...state.task};
      renderTasks();
      renderDetail();
      if (ACTIVE.has(String(state.task?.status || '')) && state.task?.status !== 'queued') startPolling(state.task.id);
      else stopPolling();
      if (!quiet) setNotice('');
    } catch (error) {
      if (ownsTaskRequest(requestedTaskId, generation) && state.projectId === projectId) {
        setNotice(error.message, 'danger');
      }
    }
  }

  async function prepareTask(event) {
    event.preventDefault();
    if (!state.projectId) return setNotice('Choose a Project first.', 'danger');
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
      if (state.projectId !== projectId) return;
      byId('crumpCodeObjective').value = '';
      await loadTasks({preferredTaskId: data.task?.id});
      if (state.projectId === projectId && state.selectedTaskId === String(data.task?.id || '')) {
        setNotice('Task prepared. Review every field before starting the isolated run.', 'success');
      }
    } catch (error) {
      if (state.projectId === projectId) setNotice(error.message, 'danger');
    } finally {
      restore();
    }
  }

  async function runTask(button) {
    const taskId = state.selectedTaskId;
    const generation = state.taskRequestGeneration;
    if (!ownsRenderedTask(taskId, generation) || !byId('crumpCodeRunConfirmed')?.checked) return;
    const restore = setButtonBusy(button, true, 'Submitting…');
    setNotice('Submitting the confirmed task to the private worker…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}/run`, {
        method: 'POST', body: {confirmed: true},
      });
      if (!ownsTaskRequest(taskId, generation) || String(data.task?.id || '') !== taskId) return;
      state.task = data.task;
      renderDetail();
      renderTasks();
      setNotice('Task accepted. You can close this window; Autonomous Crump will continue safely.', 'success');
      startPolling(taskId);
    } catch (error) {
      if (!ownsTaskRequest(taskId, generation)) return;
      stopPolling();
      await selectTask(taskId, {quiet: true});
      if (state.selectedTaskId === taskId) {
        setNotice(error.message, error.code === 'CODE_TASK_CANCELLED' ? '' : 'danger');
      }
    } finally {
      restore();
    }
  }

  async function cancelTask(button) {
    const taskId = state.selectedTaskId;
    const generation = state.taskRequestGeneration;
    if (!ownsRenderedTask(taskId, generation)) return;
    const restore = setButtonBusy(button, true, 'Cancelling…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}/cancel`, {
        method: 'POST', body: {},
      });
      if (!ownsTaskRequest(taskId, generation) || String(data.task?.id || '') !== taskId) return;
      state.task = data.task;
      renderDetail();
      renderTasks();
      stopPolling();
      setNotice('Cancellation recorded. The bounded workspace will shut down without publishing changes.', 'success');
    } catch (error) {
      if (ownsTaskRequest(taskId, generation)) setNotice(error.message, 'danger');
    } finally {
      restore();
    }
  }

  function downloadPatch() {
    if (!ownsRenderedTask(state.selectedTaskId) || !state.task?.result_patch) return;
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
    const button = event.target.closest?.('[data-code-action]');
    if (!button) return;
    if (button.dataset.codeAction === 'run') await runTask(button);
    else if (button.dataset.codeAction === 'cancel') await cancelTask(button);
    else if (button.dataset.codeAction === 'download') downloadPatch();
    else if (button.dataset.codeAction === 'diff-file') {
      state.selectedDiffPath = String(button.dataset.diffPath || '');
      renderDetail();
      [...(byId('crumpCodeDetail')?.querySelectorAll('[data-diff-path]') || [])]
        .find(node => node.dataset.diffPath === state.selectedDiffPath)
        ?.focus({preventScroll: true});
    }
  }

  function stopPolling() {
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = 0;
    state.pollGeneration += 1;
    state.pollFailures = 0;
  }

  function startPolling(taskId, {immediate = false} = {}) {
    const requestedTaskId = String(taskId || '');
    const taskGeneration = state.taskRequestGeneration;
    if (!ownsRenderedTask(requestedTaskId, taskGeneration)) return;
    stopPolling();
    const generation = state.pollGeneration;
    const poll = async () => {
      if (generation !== state.pollGeneration
          || byId('crumpCodeWorkspace')?.hidden
          || !ownsRenderedTask(requestedTaskId, taskGeneration)) return;
      try {
        const data = await api(`/api/code/tasks/${encodeURIComponent(requestedTaskId)}`);
        if (generation !== state.pollGeneration
            || !ownsTaskRequest(requestedTaskId, taskGeneration)
            || String(data.task?.id || '') !== requestedTaskId) return;
        const recovered = state.pollFailures > 0;
        state.pollFailures = 0;
        state.task = data.task || state.task;
        renderDetail();
        renderTasks();
        if (recovered && ACTIVE.has(String(state.task?.status || ''))) {
          setNotice('Connection restored. The private worker kept running while this view reconnected.', 'success');
        }
        if (!ACTIVE.has(String(state.task?.status || '')) || state.task?.status === 'queued') {
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
        if (generation !== state.pollGeneration
            || !ownsTaskRequest(requestedTaskId, taskGeneration)) return;
        state.pollFailures += 1;
        renderDetail();
        setNotice('Connection paused. The private worker continues safely; this view is reconnecting…');
      }
      if (generation !== state.pollGeneration
          || !ownsTaskRequest(requestedTaskId, taskGeneration)) return;
      const delay = Math.min(15000, 2500 * (2 ** Math.min(state.pollFailures, 3)));
      state.pollTimer = window.setTimeout(poll, delay);
    };
    state.pollTimer = window.setTimeout(poll, immediate ? 0 : 1200);
  }

  async function refresh() {
    if (!(await refreshAvailability())) return setNotice('Autonomous Crump is not available for this account.', 'danger');
    await loadProjects();
  }

  async function open() {
    createStaticShell();
    if (!(await refreshAvailability())) {
      if (state.configured && !state.entitled) {
        const modal = window.showBillingCenter?.({plan: 'professional'});
        if (!modal) window.showUpgradePrompt?.({plan: 'professional'});
      } else {
        window.showToast?.('Autonomous Crump is still in private preview.', 'info');
      }
      return false;
    }
    const overlay = byId('crumpCodeWorkspace');
    state.restoreFocus = document.activeElement;
    overlay.hidden = false;
    document.body.classList.add('crump-code-open');
    byId('crumpCodeCost').textContent = costCopy();
    requestAnimationFrame(() => byId('crumpCodeClose')?.focus({preventScroll: true}));
    await loadProjects();
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
    // The lazy loader applies its server-confirmed status only after both the
    // script and stylesheet are ready, so a newly revealed destination cannot
    // open an unstyled workspace.
    if (!bootstrapStatus && window.currentUser) void refreshAvailability();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, {once: true});
  } else initialize();
  window.addEventListener('crump:authenticated-ready', () => {
    if (!window.CrumpCodeLoader) void refreshAvailability();
  });
  window.addEventListener('online', () => {
    if (!byId('crumpCodeWorkspace')?.hidden && ACTIVE.has(String(state.task?.status || ''))) {
      startPolling(state.task.id, {immediate: true});
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible'
      && !byId('crumpCodeWorkspace')?.hidden
      && ACTIVE.has(String(state.task?.status || ''))) {
      startPolling(state.task.id, {immediate: true});
    }
  });
})();
