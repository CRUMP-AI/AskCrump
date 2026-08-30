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
    restoreFocus: null,
    pollTimer: 0,
  };
  const ACTIVE = new Set(['queued', 'provisioning', 'running', 'awaiting_approval', 'verifying']);
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

  async function api(path, options = {}) {
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
      const error = new Error(data.error || 'Crump Code could not complete that request.');
      error.code = data.code || 'CODE_REQUEST_FAILED';
      error.details = data;
      throw error;
    }
    return data;
  }

  function statusLabel(value, failureCode = '') {
    if (value === 'cancelled' && failureCode === 'CODE_TASK_EXPIRED') return 'Expired safely';
    if (value === 'cancelled' && failureCode === 'CODE_APPROVAL_EXPIRED') return 'Approval expired';
    return STATUS_LABELS[String(value || '')] || 'Status unavailable';
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
      return `${included} included run${included === 1 ? '' : 's'} per day on this plan; additional runs may use ${credits} Crump Credits.`;
    }
    if (credits > 0) return `This run may use ${credits} Crump Credits.`;
    return 'The exact charge, if any, is recorded before the task begins.';
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
            <span class="crump-code-kicker">CRUMP CODE · PRIVATE PREVIEW</span>
            <h2 id="crumpCodeTitle">Review the work before it runs.</h2>
            <p>Crump Code works on a temporary copy of a public GitHub repository. It cannot see secrets, publish, or push changes.</p>
          </div>
          <button type="button" id="crumpCodeClose" class="crump-code-icon-button" aria-label="Close Crump Code">×</button>
        </header>
        <div class="crump-code-safety" aria-label="Crump Code safety boundaries">
          <span><b>Isolated</b> temporary microVM</span>
          <span><b>Offline</b> after repository checkout</span>
          <span><b>Reviewable</b> patch and checks</span>
          <span><b>Bounded</b> four-minute maximum</span>
        </div>
        <div id="crumpCodeNotice" class="crump-code-notice" role="status" aria-live="polite" hidden></div>
        <div class="crump-code-layout">
          <aside class="crump-code-sidebar" aria-label="Crump Code tasks">
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

  async function refreshAvailability() {
    try {
      const data = await api('/api/features');
      const feature = data.features?.code_workspace || null;
      const provider = data.providers?.code || null;
      state.featureStatus = data;
      state.feature = feature;
      state.provider = provider;
      state.configured = Boolean(feature?.configured && provider?.configured);
      state.entitled = feature?.entitled === true;
      state.available = state.configured && state.entitled;
    } catch (_) {
      state.available = false;
      state.configured = false;
      state.entitled = false;
      state.feature = null;
      state.provider = null;
    }
    document.querySelectorAll('[data-crump-code-destination]').forEach(destination => {
      destination.hidden = !state.configured;
      destination.classList.toggle('is-locked', state.configured && !state.entitled);
      destination.setAttribute(
        'aria-label',
        state.configured && !state.entitled ? 'Code — Professional plan' : 'Code',
      );
    });
    document.body.classList.toggle('crump-code-configured', state.configured);
    if (!state.available && !byId('crumpCodeWorkspace')?.hidden) close();
    return state.available;
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
      empty.textContent = 'No code tasks in this Project yet.';
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
    title.textContent = String(task.objective || 'Crump Code task');
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
        : 'You can request cancellation. Crump Code checks that request before each next model or tool step.';
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
    setNotice('Loading Projects…');
    try {
      const data = await api('/api/projects');
      state.projects = Array.isArray(data.projects) ? data.projects : [];
      renderProjects();
      await loadTasks();
      setNotice('');
    } catch (error) {
      setNotice(error.message, 'danger');
    }
  }

  async function loadTasks() {
    state.tasks = [];
    state.task = null;
    renderTasks();
    renderDetail();
    if (!state.projectId) return;
    setNotice('Loading code tasks…');
    try {
      const data = await api(`/api/projects/${encodeURIComponent(state.projectId)}/code/tasks`);
      state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
      renderTasks();
      if (state.tasks.length) await selectTask(state.tasks[0].id, {quiet: true});
      setNotice('');
    } catch (error) {
      setNotice(error.message, 'danger');
    }
  }

  async function selectTask(taskId, {quiet = false} = {}) {
    if (!taskId) return;
    if (!quiet) setNotice('Loading task…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}`);
      state.task = data.task || null;
      const index = state.tasks.findIndex(item => item.id === state.task?.id);
      if (index >= 0) state.tasks[index] = {...state.tasks[index], ...state.task};
      renderTasks();
      renderDetail();
      if (ACTIVE.has(String(state.task?.status || '')) && state.task?.status !== 'queued') startPolling(state.task.id);
      else stopPolling();
      if (!quiet) setNotice('');
    } catch (error) {
      setNotice(error.message, 'danger');
    }
  }

  async function prepareTask(event) {
    event.preventDefault();
    if (!state.projectId) return setNotice('Choose a Project first.', 'danger');
    const button = byId('crumpCodePrepare');
    const restore = setButtonBusy(button, true, 'Preparing…');
    setNotice('');
    try {
      const data = await api(`/api/projects/${encodeURIComponent(state.projectId)}/code/tasks`, {
        method: 'POST',
        body: {
          repositoryUrl: byId('crumpCodeRepository')?.value.trim(),
          revision: byId('crumpCodeRevision')?.value.trim(),
          objective: byId('crumpCodeObjective')?.value.trim(),
          mode: byId('crumpCodeMode')?.value || 'plan',
          maxDurationSeconds: Number(state.provider?.maxDurationSeconds || 180),
        },
      });
      state.task = data.task;
      byId('crumpCodeObjective').value = '';
      await loadTasks();
      await selectTask(data.task.id, {quiet: true});
      setNotice('Task prepared. Review every field before starting the isolated run.', 'success');
    } catch (error) {
      setNotice(error.message, 'danger');
    } finally {
      restore();
    }
  }

  async function runTask(button) {
    if (!state.task?.id || !byId('crumpCodeRunConfirmed')?.checked) return;
    const taskId = state.task.id;
    const restore = setButtonBusy(button, true, 'Submitting…');
    setNotice('Submitting the confirmed task to the private worker…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}/run`, {
        method: 'POST', body: {confirmed: true},
      });
      state.task = data.task;
      renderDetail();
      renderTasks();
      setNotice('Task accepted. You can close this window; Crump Code will continue safely.', 'success');
      startPolling(taskId);
    } catch (error) {
      stopPolling();
      await selectTask(taskId, {quiet: true});
      setNotice(error.message, error.code === 'CODE_TASK_CANCELLED' ? '' : 'danger');
    } finally {
      restore();
    }
  }

  async function cancelTask(button) {
    if (!state.task?.id) return;
    const restore = setButtonBusy(button, true, 'Cancelling…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(state.task.id)}/cancel`, {
        method: 'POST', body: {},
      });
      state.task = data.task;
      await selectTask(state.task.id, {quiet: true});
      stopPolling();
      setNotice('Cancellation recorded. The bounded workspace will shut down without publishing changes.', 'success');
    } catch (error) {
      setNotice(error.message, 'danger');
    } finally {
      restore();
    }
  }

  async function decideApproval(button) {
    const approvalId = button.dataset.codeApproval;
    const decision = button.dataset.codeDecision;
    if (!state.task?.id || !approvalId || !decision) return;
    const restore = setButtonBusy(button, true, decision === 'approved' ? 'Approving…' : 'Denying…');
    try {
      const data = await api(`/api/code/tasks/${encodeURIComponent(state.task.id)}/approvals/${encodeURIComponent(approvalId)}`, {
        method: 'POST', body: {decision},
      });
      state.task = data.task;
      await selectTask(state.task.id, {quiet: true});
      setNotice(decision === 'approved' ? 'Bounded retry approved. Review it again before running.' : 'Request denied and task cancelled.', 'success');
    } catch (error) {
      if (error.code === 'CODE_APPROVAL_EXPIRED') {
        await selectTask(state.task.id, {quiet: true});
      }
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
    link.download = `crump-code-${String(state.task.id || 'change').slice(0, 8)}.patch`;
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
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = 0;
  }

  function startPolling(taskId) {
    stopPolling();
    const poll = async () => {
      if (byId('crumpCodeWorkspace')?.hidden || state.task?.id !== taskId) return;
      try {
        const data = await api(`/api/code/tasks/${encodeURIComponent(taskId)}`);
        state.task = data.task || state.task;
        renderDetail();
        renderTasks();
        if (!ACTIVE.has(String(state.task?.status || '')) || state.task?.status === 'queued') {
          if (state.task?.status === 'completed') {
            setNotice('Crump Code finished. Review the result, checks, and patch before using it.', 'success');
          } else if (state.task?.status === 'failed') {
            setNotice('Crump Code stopped safely. Review the task history before retrying.', 'danger');
          } else if (state.task?.status === 'cancelled') {
            setNotice('Cancellation recorded. No source changes were published.');
          }
          return;
        }
      } catch (_) {
        // A later poll can recover from a brief connectivity interruption.
      }
      state.pollTimer = window.setTimeout(poll, 2500);
    };
    state.pollTimer = window.setTimeout(poll, 1200);
  }

  async function refresh() {
    if (!(await refreshAvailability())) return setNotice('Crump Code is not available for this account.', 'danger');
    await loadProjects();
  }

  async function open() {
    createStaticShell();
    if (!(await refreshAvailability())) {
      if (state.configured && !state.entitled) {
        const modal = window.showBillingCenter?.({plan: 'professional'});
        if (!modal) window.showUpgradePrompt?.({plan: 'professional'});
      } else {
        window.showToast?.('Crump Code is still in private preview.', 'info');
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

  window.CrumpCodeWorkspace = Object.freeze({open, close, refresh, refreshAvailability});

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      createStaticShell();
      if (window.currentUser) void refreshAvailability();
    }, {once: true});
  } else {
    createStaticShell();
    if (window.currentUser) void refreshAvailability();
  }
  window.addEventListener('crump:authenticated-ready', () => void refreshAvailability());
})();
