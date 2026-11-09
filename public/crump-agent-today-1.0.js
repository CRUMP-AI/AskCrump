/*
 * Agent Today layer (1.0)
 *
 * Renders the Today home surface on top of the existing workspace: what is
 * waiting on the user, what is running, and the brief connection card, all
 * from the agent registry, run ledger, and approval endpoints. Also owns
 * the Tasks drawer and the browser panel shell. Everything here is
 * additive — the vision shell and the conversation keep their own modules,
 * and when the agent endpoints are not available yet the surface degrades
 * to a quiet empty state instead of inventing data.
 */
(() => {
  'use strict';

  if (window.__crumpAgentTodayLoaded) return;
  window.__crumpAgentTodayLoaded = true;

  var REQUEST_TIMEOUT_MS = 12000;
  var REFRESH_MS = 45000;

  var TERMINAL = { succeeded: true, failed: true, cancelled: true };
  var WAITING = { waiting_approval: true, waiting_user: true };
  var RUNNING = { queued: true, planning: true, running: true };
  var STATUS_LABELS = {
    queued: 'Queued',
    planning: 'Planning',
    running: 'Running',
    waiting_approval: 'Waiting on you',
    waiting_user: 'Waiting on you',
    succeeded: 'Done',
    failed: "Didn't finish",
    cancelled: 'Cancelled',
    pending: 'Waiting on you',
  };

  var state = {
    capabilities: {},
    capabilityList: [],
    approvals: [],
    runs: [],
    loaded: false,
    failed: false,
    loading: false,
    runDetails: {},
  };

  /* ---------------------------------------------------------------- */
  /* Small DOM helpers. Every string that comes from the API is set    */
  /* through textContent, never parsed as markup.                      */
  /* ---------------------------------------------------------------- */

  function h(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function button(label, className, onClick) {
    var btn = h('button', className, label);
    btn.type = 'button';
    if (typeof onClick === 'function') btn.addEventListener('click', onClick);
    return btn;
  }

  function fmtTime(value) {
    if (!value) return '';
    var d = new Date(value);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
  }

  function fmtClock(value) {
    if (!value) return '';
    var d = new Date(value);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || String(status || 'In progress');
  }

  function statusClass(status) {
    if (TERMINAL[status]) return status === 'failed' ? 'cat-status cat-status-failed' : 'cat-status cat-status-done';
    if (WAITING[status] || status === 'pending') return 'cat-status cat-status-waiting';
    return 'cat-status cat-status-live';
  }

  function capabilityTitle(capabilityId) {
    var cap = state.capabilities[capabilityId];
    if (cap && cap.title) return cap.title;
    return capabilityId || 'Task';
  }

  function userFirstName() {
    var full = '';
    try {
      full = (window.currentUser && (window.currentUser.fullName || window.currentUser.name)) ||
        (window.currentProfile && window.currentProfile.profile && window.currentProfile.profile.name) || '';
    } catch (_) {}
    if (!full) {
      var input = document.getElementById('settingsName');
      if (input && input.value) full = input.value;
    }
    return String(full || '').trim().split(/\s+/)[0] || '';
  }

  /* ---------------------------------------------------------------- */
  /* Authenticated fetch, mirroring the vision modules: account        */
  /* session cookies plus the expected-owner header.                   */
  /* ---------------------------------------------------------------- */

  function captureOwnerId() {
    try {
      var boundary = window.CrumpAuthBoundary;
      if (boundary && typeof boundary.authenticatedUserId === 'function') {
        var fromBoundary = String(boundary.authenticatedUserId() || '').trim();
        if (fromBoundary) return fromBoundary;
      }
    } catch (_) {}
    try {
      if (window.currentUser && window.currentUser.id) return String(window.currentUser.id).trim();
    } catch (_) {}
    return '';
  }

  function api(path, options) {
    var opts = options || {};
    var ownerId = captureOwnerId();
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS) : null;
    var headers = { Accept: 'application/json' };
    if (ownerId) headers['X-Ask-Crump-Expected-Owner'] = ownerId;
    if (opts.body != null) headers['Content-Type'] = 'application/json';
    return fetch(path, {
      method: opts.method || 'GET',
      credentials: 'include',
      headers: headers,
      body: opts.body != null ? JSON.stringify(opts.body) : undefined,
      signal: controller ? controller.signal : undefined,
    }).then(function (response) {
      if (timer) clearTimeout(timer);
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok || (data && data.success === false)) {
          var message = (data && (data.error || data.message)) || ('Request failed (' + response.status + ')');
          throw new Error(message);
        }
        return data || {};
      });
    }, function (err) {
      if (timer) clearTimeout(timer);
      throw err;
    });
  }

  function settled(promise) {
    return promise.then(
      function (data) { return { ok: true, data: data }; },
      function (error) { return { ok: false, error: error }; }
    );
  }

  /* ---------------------------------------------------------------- */
  /* Data                                                              */
  /* ---------------------------------------------------------------- */

  function googleBriefIsPlanned() {
    var google = state.capabilityList.filter(function (cap) {
      return cap && (String(cap.id || '').indexOf('gmail.') === 0 ||
        String(cap.id || '').indexOf('calendar.') === 0 ||
        cap.id === 'agent.today_brief');
    });
    if (!google.length) return false;
    return google.some(function (cap) { return cap.status === 'planned'; });
  }

  function loadAgentData() {
    if (state.loading) return Promise.resolve();
    if (!captureOwnerId()) {
      state.loaded = false;
      state.failed = false;
      renderToday();
      return Promise.resolve();
    }
    state.loading = true;
    return Promise.all([
      settled(api('/api/agent/capabilities')),
      settled(api('/api/agent/approvals')),
      settled(api('/api/agent/runs')),
    ]).then(function (results) {
      state.loading = false;
      var caps = results[0];
      var approvals = results[1];
      var runs = results[2];
      if (caps.ok && Array.isArray(caps.data.capabilities)) {
        state.capabilityList = caps.data.capabilities;
        state.capabilities = {};
        caps.data.capabilities.forEach(function (cap) {
          if (cap && cap.id) state.capabilities[cap.id] = cap;
        });
      }
      if (approvals.ok) {
        state.approvals = Array.isArray(approvals.data.approvals) ? approvals.data.approvals : [];
      }
      if (runs.ok) {
        state.runs = Array.isArray(runs.data.runs) ? runs.data.runs : [];
      }
      state.loaded = caps.ok || approvals.ok || runs.ok;
      state.failed = !state.loaded;
      renderToday();
      if (tasksPanel && tasksPanel.classList.contains('is-open')) renderTasks();
    }).catch(function () {
      state.loading = false;
      state.failed = true;
      renderToday();
    });
  }

  function liveRuns() {
    return state.runs.filter(function (run) { return run && RUNNING[run.status]; });
  }

  function waitingRunsWithoutApproval() {
    var covered = {};
    state.approvals.forEach(function (action) {
      if (action && action.runId) covered[action.runId] = true;
    });
    return state.runs.filter(function (run) {
      return run && WAITING[run.status] && !covered[run.id];
    });
  }

  /* ---------------------------------------------------------------- */
  /* Shared card builders                                              */
  /* ---------------------------------------------------------------- */

  function payloadList(payload) {
    var entries = [];
    if (payload && typeof payload === 'object') {
      Object.keys(payload).forEach(function (key) {
        var value = payload[key];
        var text;
        if (value == null) text = '';
        else if (typeof value === 'string') text = value.length > 220 ? value.slice(0, 220) + '…' : value;
        else if (typeof value === 'number' || typeof value === 'boolean') text = String(value);
        else if (Array.isArray(value)) text = value.length === 1 ? '1 item' : value.length + ' items';
        else {
          try { text = JSON.stringify(value); } catch (_) { text = 'Details included'; }
          if (text.length > 220) text = text.slice(0, 220) + '…';
        }
        entries.push([key, text]);
      });
    }
    if (!entries.length) return null;
    var list = h('dl', 'cat-payload');
    entries.slice(0, 8).forEach(function (pair) {
      var row = h('div', 'cat-payload-row');
      row.appendChild(h('dt', null, pair[0]));
      row.appendChild(h('dd', null, pair[1]));
      list.appendChild(row);
    });
    return list;
  }

  function creditLine(capabilityId, creditCost) {
    if (typeof creditCost === 'number' && creditCost > 0) {
      return creditCost + (creditCost === 1 ? ' credit' : ' credits') + ' · charged only if it succeeds';
    }
    var cap = state.capabilities[capabilityId];
    if (cap && cap.creditCost && cap.creditCost.kind === 'fixed' &&
        typeof cap.creditCost.credits === 'number' && cap.creditCost.credits > 0) {
      return cap.creditCost.credits + (cap.creditCost.credits === 1 ? ' credit' : ' credits') + ' · charged only if it succeeds';
    }
    if (cap && cap.creditCost && cap.creditCost.kind === 'quote') {
      return 'Priced before it runs · nothing is charged unless it succeeds';
    }
    return '';
  }

  function approvalCard(action) {
    var card = h('article', 'cat-card');
    card.setAttribute('aria-label', capabilityTitle(action.capabilityId));
    var head = h('div', 'cat-card-head');
    var titleWrap = h('div');
    titleWrap.appendChild(h('h3', 'cat-card-title', capabilityTitle(action.capabilityId)));
    if (action.summary) titleWrap.appendChild(h('p', 'cat-card-summary', action.summary));
    head.appendChild(titleWrap);
    head.appendChild(h('span', statusClass('pending'), 'Waiting on you'));
    card.appendChild(head);

    var payload = payloadList(action.payload);
    if (payload) card.appendChild(payload);

    var meta = [];
    var cost = creditLine(action.capabilityId, action.creditCost);
    if (cost) meta.push(cost);
    if (action.expiresAt) meta.push('Expires ' + fmtTime(action.expiresAt));
    if (meta.length) card.appendChild(h('p', 'cat-card-meta', meta.join(' · ')));

    var note = h('p', 'cat-card-note', '');
    note.hidden = true;
    var actions = h('div', 'cat-actions');
    var approveBtn = button('Approve', 'cat-btn cat-btn-primary');
    var denyBtn = button('Not now', 'cat-btn');
    denyBtn.title = 'Dismiss this request';
    function decide(decision) {
      approveBtn.disabled = true;
      denyBtn.disabled = true;
      note.hidden = true;
      api(`/api/agent/approvals/${encodeURIComponent(action.id)}/decision`, {
        method: 'POST',
        body: { decision: decision },
      }).then(function () {
        note.className = 'cat-card-note';
        note.textContent = decision === 'approved' ? 'Approved. It is in the queue now.' : 'Dismissed.';
        note.hidden = false;
        actions.remove();
        setTimeout(loadAgentData, 700);
      }).catch(function () {
        approveBtn.disabled = false;
        denyBtn.disabled = false;
        note.className = 'cat-card-note cat-card-note-error';
        note.textContent = 'That decision could not be recorded. Try again.';
        note.hidden = false;
      });
    }
    approveBtn.addEventListener('click', function () { decide('approved'); });
    denyBtn.addEventListener('click', function () { decide('denied'); });
    actions.appendChild(approveBtn);
    actions.appendChild(denyBtn);
    card.appendChild(actions);
    card.appendChild(note);
    return card;
  }

  function runCard(run) {
    var isBrowser = run.capabilityId === 'browser.act';
    var card = h('article', 'cat-card' + (isBrowser ? ' cat-card-browser' : ''));
    var head = h('div', 'cat-card-head');
    var titleWrap = h('div');
    titleWrap.appendChild(h('h3', 'cat-card-title', capabilityTitle(run.capabilityId)));
    var cap = state.capabilities[run.capabilityId];
    if (cap && cap.verbPhrase) titleWrap.appendChild(h('p', 'cat-card-summary', cap.verbPhrase));
    head.appendChild(titleWrap);
    head.appendChild(h('span', statusClass(run.status), statusLabel(run.status)));
    card.appendChild(head);
    var when = fmtTime(run.updatedAt || run.createdAt);
    if (when) card.appendChild(h('p', 'cat-card-meta', 'Updated ' + when));
    if (isBrowser) {
      var actions = h('div', 'cat-actions');
      actions.appendChild(button('Open browser', 'cat-btn', function () { openBrowserPanel(run); }));
      card.appendChild(actions);
    }
    return card;
  }

  /* ---------------------------------------------------------------- */
  /* Today surface                                                     */
  /* ---------------------------------------------------------------- */

  var todayNode = null;
  var lastTodaySignature = '';

  function ensureToday() {
    if (todayNode && todayNode.isConnected) return todayNode;
    var body = document.querySelector('.v1-workspace-body');
    if (!body) return null;
    todayNode = h('section', 'cat-today');
    todayNode.id = 'catToday';
    todayNode.setAttribute('aria-label', 'Today');
    var launchpad = document.getElementById('v1Launchpad');
    if (launchpad && launchpad.parentElement === body) body.insertBefore(todayNode, launchpad);
    else body.insertBefore(todayNode, body.firstChild);
    return todayNode;
  }

  function homeIsActive() {
    var app = document.getElementById('appContainer');
    if (!app || app.style.display === 'none') return false;
    var stage = document.getElementById('cvStage');
    if (stage && !stage.hidden) return false;
    try {
      if (window.CrumpVision && typeof window.CrumpVision.current === 'function') {
        return window.CrumpVision.current() === 'home';
      }
    } catch (_) {}
    return true;
  }

  function greetingHeadline() {
    var hour = new Date().getHours();
    var part = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    var name = userFirstName();
    return name ? part + ', ' + name + '.' : part + '.';
  }

  function renderToday() {
    var node = ensureToday();
    if (!node) return;
    var home = homeIsActive();
    var fullHome = document.body.classList.contains('v1-home');
    node.classList.toggle('cat-today--slim', !fullHome);
    var hasWork = state.approvals.length > 0 || liveRuns().length > 0 || waitingRunsWithoutApproval().length > 0;
    node.hidden = !home || (!fullHome && !hasWork);
    if (node.hidden) return;

    // Skip the rebuild when nothing the surface shows has changed. This
    // also keeps the layer's own DOM writes from feeding its observers.
    var signature = [
      fullHome ? 'full' : 'slim',
      captureOwnerId() ? 'in' : 'out',
      state.loaded ? 'loaded' : 'pending',
      state.failed ? 'failed' : 'ok',
      greetingHeadline(),
      state.approvals.map(function (a) { return a.id + ':' + a.status; }).join(','),
      state.runs.map(function (r) { return r.id + ':' + r.status; }).join(','),
      googleBriefIsPlanned() ? 'planned' : 'brief-open',
    ].join('|');
    if (signature === lastTodaySignature && node.childNodes.length) return;
    lastTodaySignature = signature;

    node.innerHTML = '';

    var head = h('div', 'cat-today-head');
    var weekday = new Date().toLocaleDateString(undefined, { weekday: 'long' });
    head.appendChild(h('p', 'cat-today-eyebrow', weekday + ' · Built in Savannah'));
    head.appendChild(h('h2', 'cat-today-title', greetingHeadline()));
    var subBits = [];
    if (state.approvals.length) {
      subBits.push(state.approvals.length === 1 ? 'One thing needs your call' : state.approvals.length + ' things need your call');
    }
    if (liveRuns().length) {
      subBits.push(liveRuns().length === 1 ? 'one job in progress' : liveRuns().length + ' jobs in progress');
    }
    var sub = subBits.length
      ? subBits.join(' · ').replace(/^./, function (c) { return c.toUpperCase(); }) + '.'
      : 'Here is where approvals, work in progress, and your brief land.';
    head.appendChild(h('p', 'cat-today-sub', sub));
    node.appendChild(head);

    var owner = captureOwnerId();
    if (!owner) {
      var signedOut = h('div', 'cat-today-section');
      signedOut.appendChild(h('p', 'cat-empty', 'Sign in to see your approvals, work in progress, and brief here.'));
      node.appendChild(signedOut);
      return;
    }

    if (!state.loaded && !state.failed) {
      var loading = h('div', 'cat-today-section');
      loading.appendChild(h('p', 'cat-empty', 'Checking what needs you…'));
      node.appendChild(loading);
      return;
    }

    if (state.failed) {
      var failed = h('div', 'cat-today-section');
      var failedCard = h('div', 'cat-empty');
      failedCard.appendChild(document.createTextNode('Today could not load just now. Your conversation still works. '));
      failedCard.appendChild(button('Try again', 'cat-btn', function () { loadAgentData(); }));
      failed.appendChild(failedCard);
      node.appendChild(failed);
      return;
    }

    var waiting = waitingRunsWithoutApproval();
    if (state.approvals.length || waiting.length) {
      var waitSection = h('section', 'cat-today-section');
      waitSection.setAttribute('aria-label', 'Waiting on you');
      waitSection.appendChild(h('h3', 'cat-today-section-title', 'Waiting on you'));
      var waitStack = h('div', 'cat-today-stack');
      state.approvals.forEach(function (action) { waitStack.appendChild(approvalCard(action)); });
      waiting.forEach(function (run) { waitStack.appendChild(runCard(run)); });
      waitSection.appendChild(waitStack);
      node.appendChild(waitSection);
    }

    var live = liveRuns();
    if (live.length) {
      var liveSection = h('section', 'cat-today-section');
      liveSection.setAttribute('aria-label', 'Live work');
      liveSection.appendChild(h('h3', 'cat-today-section-title', 'Live work'));
      var liveStack = h('div', 'cat-today-stack');
      live.forEach(function (run) { liveStack.appendChild(runCard(run)); });
      liveSection.appendChild(liveStack);
      node.appendChild(liveSection);
    }

    var briefArea = h('section', 'cat-today-section cat-brief-area');
    briefArea.setAttribute('aria-label', 'Your brief');
    if (googleBriefIsPlanned()) {
      var connect = h('article', 'cat-card cat-connect');
      connect.appendChild(h('h3', 'cat-card-title', 'Your brief is almost ready'));
      connect.appendChild(h('p', 'cat-card-summary',
        'Connect Google to unlock your brief — your email and calendar, read-only to start, ' +
        'summarized here each morning. No brief is shown until the connection is real.'));
      var connectActions = h('div', 'cat-actions');
      var connectNote = h('p', 'cat-card-note', '');
      connectNote.hidden = true;
      var connectBtn = button('Connect Google', 'cat-btn cat-btn-primary', function () {
        connectNote.textContent = 'Connecting Google is the next step — this card turns into your brief as soon as it lands.';
        connectNote.hidden = false;
      });
      connectActions.appendChild(connectBtn);
      connect.appendChild(connectActions);
      connect.appendChild(connectNote);
      briefArea.appendChild(connect);
      node.appendChild(briefArea);
    } else if (!state.approvals.length && !live.length && !waiting.length) {
      briefArea.appendChild(h('p', 'cat-empty',
        'Nothing needs you right now. Ask for an outcome below and it will show up here while it runs.'));
      node.appendChild(briefArea);
    }
  }

  /* ---------------------------------------------------------------- */
  /* Tasks drawer                                                      */
  /* ---------------------------------------------------------------- */

  var tasksOverlay = null;
  var tasksPanel = null;
  var tasksBody = null;
  var tasksOpener = null;
  var tasksCloseBtn = null;

  function ensureTasksPanel() {
    if (tasksPanel && tasksPanel.isConnected) return tasksPanel;
    tasksOverlay = h('div', 'cat-overlay');
    tasksOverlay.hidden = true;
    tasksOverlay.addEventListener('click', closeTasks);

    tasksPanel = h('aside', 'cat-drawer');
    tasksPanel.id = 'catTasksPanel';
    tasksPanel.setAttribute('role', 'dialog');
    tasksPanel.setAttribute('aria-modal', 'true');
    tasksPanel.setAttribute('aria-label', 'Tasks');
    tasksPanel.hidden = true;

    var head = h('div', 'cat-drawer-head');
    head.appendChild(h('h2', 'cat-drawer-title', 'Tasks'));
    var headActions = h('div', 'cat-drawer-head-actions');
    headActions.appendChild(button('Browser', 'cat-icon-btn', function () { openBrowserPanel(null); }));
    headActions.appendChild(button('Refresh', 'cat-icon-btn', function () { loadAgentData(); }));
    var closeBtn = button('Close', 'cat-icon-btn', closeTasks);
    closeBtn.setAttribute('aria-label', 'Close Tasks');
    tasksCloseBtn = closeBtn;
    headActions.appendChild(closeBtn);
    head.appendChild(headActions);
    tasksPanel.appendChild(head);

    tasksBody = h('div', 'cat-drawer-body');
    tasksPanel.appendChild(tasksBody);

    document.body.appendChild(tasksOverlay);
    document.body.appendChild(tasksPanel);
    return tasksPanel;
  }

  function openTasks() {
    ensureTasksPanel();
    tasksOpener = document.activeElement;
    tasksOverlay.hidden = false;
    tasksPanel.hidden = false;
    requestAnimationFrame(function () { tasksPanel.classList.add('is-open'); });
    document.querySelectorAll('[data-cat-tasks]').forEach(function (btn) {
      btn.classList.add('is-active');
    });
    renderTasks();
    loadAgentData();
    if (tasksCloseBtn) tasksCloseBtn.focus({ preventScroll: true });
  }

  function closeTasks() {
    if (!tasksPanel) return;
    tasksPanel.classList.remove('is-open');
    tasksOverlay.hidden = true;
    tasksPanel.hidden = true;
    document.querySelectorAll('[data-cat-tasks]').forEach(function (btn) {
      btn.classList.remove('is-active');
    });
    if (tasksOpener && tasksOpener.isConnected) tasksOpener.focus({ preventScroll: true });
    tasksOpener = null;
  }

  function taskRow(run) {
    var row = h('div', 'cat-task-row');
    var headBtn = h('button', 'cat-task-row-head');
    headBtn.type = 'button';
    headBtn.setAttribute('aria-expanded', 'false');
    var main = h('span', 'cat-task-row-main');
    main.appendChild(h('span', 'cat-task-row-title', capabilityTitle(run.capabilityId)));
    var metaBits = [statusLabel(run.status)];
    var when = fmtTime(run.createdAt);
    if (when) metaBits.push('started ' + when);
    main.appendChild(h('span', 'cat-task-row-meta', metaBits.join(' · ')));
    headBtn.appendChild(main);
    headBtn.appendChild(h('span', statusClass(run.status), statusLabel(run.status)));
    row.appendChild(headBtn);

    var detail = h('div', 'cat-task-detail');
    detail.hidden = true;
    row.appendChild(detail);

    headBtn.addEventListener('click', function () {
      var open = detail.hidden;
      detail.hidden = !open;
      headBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) fillTaskDetail(run, detail);
    });
    if (run.capabilityId === 'browser.act') {
      var actions = h('div', 'cat-actions');
      actions.appendChild(button('Open browser', 'cat-btn', function () { openBrowserPanel(run); }));
      detail.appendChild(actions);
    }
    return row;
  }

  function fillTaskDetail(run, detail) {
    if (detail.dataset.catLoaded === '1') return;
    detail.dataset.catLoaded = '1';
    var loading = h('p', 'cat-group-empty', 'Loading steps…');
    detail.appendChild(loading);
    api(`/api/agent/runs/${encodeURIComponent(run.id)}`).then(function (data) {
      var full = data && data.run ? data.run : null;
      loading.remove();
      if (!full) {
        detail.appendChild(h('p', 'cat-group-empty', 'Steps could not load for this run.'));
        return;
      }
      state.runDetails[run.id] = full;
      var steps = Array.isArray(full.steps) ? full.steps : [];
      if (steps.length) {
        var list = h('ol', 'cat-step-list');
        steps.forEach(function (step) {
          var item = h('li');
          item.appendChild(h('span', null, stepLabel(step)));
          var clock = fmtClock(step.createdAt);
          if (clock) item.appendChild(h('time', null, clock));
          list.appendChild(item);
        });
        detail.appendChild(list);
      } else {
        detail.appendChild(h('p', 'cat-group-empty', 'No steps recorded yet.'));
      }
      var pending = Array.isArray(full.pendingActions)
        ? full.pendingActions.filter(function (a) { return a && a.status === 'pending'; })
        : [];
      pending.forEach(function (action) { detail.appendChild(approvalCard(action)); });
      if (full.resultSummary) {
        var resultText = typeof full.resultSummary === 'string'
          ? full.resultSummary
          : 'Result recorded.';
        detail.appendChild(h('p', 'cat-card-meta', resultText.slice(0, 220)));
      }
      if (!TERMINAL[run.status]) {
        var actions = h('div', 'cat-actions');
        var cancelBtn = button('Cancel run', 'cat-btn', function () {
          cancelBtn.disabled = true;
          api(`/api/agent/runs/${encodeURIComponent(run.id)}/cancel`, { method: 'POST' })
            .then(function () { loadAgentData(); })
            .catch(function () { cancelBtn.disabled = false; });
        });
        actions.appendChild(cancelBtn);
        detail.appendChild(actions);
      }
    }).catch(function () {
      loading.textContent = 'Steps could not load for this run.';
    });
  }

  function stepLabel(step) {
    var type = String((step && step.type) || 'step');
    var labels = {
      'run.created': 'Run created',
      'run.queued': 'Queued',
      'run.cancelled': 'Cancelled',
      'approval.requested': 'Approval requested',
      'approval.decided': 'Approval decided',
    };
    return labels[type] || type.replace(/[._]/g, ' ');
  }

  function renderTasks() {
    if (!tasksBody) return;
    tasksBody.innerHTML = '';
    if (!captureOwnerId()) {
      tasksBody.appendChild(h('p', 'cat-empty', 'Sign in to see your tasks.'));
      return;
    }
    if (!state.loaded && !state.failed) {
      tasksBody.appendChild(h('p', 'cat-empty', 'Loading your tasks…'));
      return;
    }
    if (state.failed) {
      tasksBody.appendChild(h('p', 'cat-empty', 'Tasks could not load just now. Try Refresh in a moment.'));
      return;
    }

    var waitingGroup = h('section', 'cat-group');
    waitingGroup.appendChild(h('h3', 'cat-group-title', 'Waiting on you'));
    var waitingCount = 0;
    state.approvals.forEach(function (action) {
      waitingGroup.appendChild(approvalCard(action));
      waitingCount += 1;
    });
    waitingRunsWithoutApproval().forEach(function (run) {
      waitingGroup.appendChild(taskRow(run));
      waitingCount += 1;
    });
    if (!waitingCount) waitingGroup.appendChild(h('p', 'cat-group-empty', 'Nothing is waiting on you.'));
    tasksBody.appendChild(waitingGroup);

    var runningGroup = h('section', 'cat-group');
    runningGroup.appendChild(h('h3', 'cat-group-title', 'Running'));
    var running = liveRuns();
    if (!running.length) runningGroup.appendChild(h('p', 'cat-group-empty', 'Nothing is running right now.'));
    running.forEach(function (run) { runningGroup.appendChild(taskRow(run)); });
    tasksBody.appendChild(runningGroup);

    var doneGroup = h('section', 'cat-group');
    doneGroup.appendChild(h('h3', 'cat-group-title', 'Done'));
    var done = state.runs.filter(function (run) { return run && TERMINAL[run.status]; });
    if (!done.length) doneGroup.appendChild(h('p', 'cat-group-empty', 'Finished work will land here.'));
    done.forEach(function (run) { doneGroup.appendChild(taskRow(run)); });
    tasksBody.appendChild(doneGroup);
  }

  /* ---------------------------------------------------------------- */
  /* Browser panel. The surface is real; per-user browser execution   */
  /* is not live yet, and the panel says so plainly. Controls that     */
  /* depend on a live session stay disabled.                           */
  /* ---------------------------------------------------------------- */

  var browserPanel = null;
  var browserStep = null;
  var browserOpener = null;

  function ensureBrowserPanel() {
    if (browserPanel && browserPanel.isConnected) return browserPanel;
    browserPanel = h('div', 'cat-browser');
    browserPanel.id = 'catBrowserPanel';
    browserPanel.hidden = true;

    var win = h('div', 'cat-browser-window');
    win.setAttribute('role', 'dialog');
    win.setAttribute('aria-modal', 'true');
    win.setAttribute('aria-label', 'Browser');

    var head = h('div', 'cat-browser-head');
    var headText = h('div');
    headText.appendChild(h('h2', 'cat-browser-title', 'Browser'));
    browserStep = h('p', 'cat-browser-step', 'No browser task is running.');
    headText.appendChild(browserStep);
    head.appendChild(headText);
    var closeBtn = button('Close', 'cat-icon-btn', closeBrowserPanel);
    closeBtn.setAttribute('aria-label', 'Close browser panel');
    head.appendChild(closeBtn);
    win.appendChild(head);

    var viewport = h('div', 'cat-browser-viewport');
    viewport.appendChild(h('p', null,
      'Per-user browser sessions are not live yet, so there is nothing to show here. ' +
      'When a browser task runs, you will watch it here and be able to pause it or take over.'));
    win.appendChild(viewport);

    var controls = h('div', 'cat-browser-controls');
    var pauseBtn = button('Pause', 'cat-btn');
    pauseBtn.disabled = true;
    pauseBtn.setAttribute('aria-disabled', 'true');
    var takeOverBtn = button('Take over', 'cat-btn');
    takeOverBtn.disabled = true;
    takeOverBtn.setAttribute('aria-disabled', 'true');
    controls.appendChild(pauseBtn);
    controls.appendChild(takeOverBtn);
    win.appendChild(controls);

    browserPanel.appendChild(win);
    browserPanel.addEventListener('click', function (event) {
      if (event.target === browserPanel) closeBrowserPanel();
    });
    document.body.appendChild(browserPanel);
    return browserPanel;
  }

  function openBrowserPanel(run) {
    ensureBrowserPanel();
    browserOpener = document.activeElement;
    if (run) {
      var detail = state.runDetails[run.id];
      var steps = detail && Array.isArray(detail.steps) ? detail.steps : [];
      var lastStep = steps.length ? steps[steps.length - 1] : null;
      browserStep.textContent = capabilityTitle(run.capabilityId) + ' · ' + statusLabel(run.status) +
        (lastStep ? ' · ' + stepLabel(lastStep) : '');
    } else {
      browserStep.textContent = 'No browser task is running.';
    }
    browserPanel.hidden = false;
    var closeButton = browserPanel.querySelector('.cat-icon-btn');
    if (closeButton) closeButton.focus({ preventScroll: true });
  }

  function closeBrowserPanel() {
    if (!browserPanel) return;
    browserPanel.hidden = true;
    if (browserOpener && browserOpener.isConnected) browserOpener.focus({ preventScroll: true });
    browserOpener = null;
  }

  /* ---------------------------------------------------------------- */
  /* Navigation: Home becomes Today, and Tasks joins the rail and     */
  /* the mobile bar. Existing destinations are left exactly as they    */
  /* are; the shell keeps owning them.                                 */
  /* ---------------------------------------------------------------- */

  var TASKS_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    '<path d="M5 5.5h13M5 12h13M5 18.5h8"/>' +
    '<path d="m2.8 5.4.9.9 1.6-1.7M2.8 11.9l.9.9 1.6-1.7M2.8 18.4l.9.9 1.6-1.7"/></svg>';

  function relabelHome() {
    document.querySelectorAll('[data-cv-destination="home"]').forEach(function (btn) {
      var label = btn.querySelector('span:not(.cv-rail-brand-mark):not(.cv-rail-brand-copy)');
      var spans = btn.querySelectorAll('span');
      spans.forEach(function (span) {
        if (span.textContent.trim() === 'Home') span.textContent = 'Today';
      });
      if (label && label.textContent.trim() === 'Home') label.textContent = 'Today';
      if (btn.getAttribute('aria-label') === 'Open Home') btn.setAttribute('aria-label', 'Open Today');
      if (btn.getAttribute('aria-label') === 'Home') btn.setAttribute('aria-label', 'Today');
    });
  }

  function tasksButton(className) {
    var btn = h('button', className);
    btn.type = 'button';
    btn.setAttribute('data-cat-tasks', '1');
    btn.setAttribute('aria-label', 'Tasks');
    var iconWrap = h('span');
    iconWrap.innerHTML = TASKS_ICON;
    btn.appendChild(iconWrap.firstChild);
    btn.appendChild(h('span', null, 'Tasks'));
    btn.addEventListener('click', openTasks);
    return btn;
  }

  function ensureTasksNav() {
    var railNav = document.querySelector('.cv-rail-nav');
    if (railNav && !railNav.querySelector('[data-cat-tasks]')) {
      var railBtn = tasksButton('cv-destination');
      var homeBtn = railNav.querySelector('[data-cv-destination="home"]');
      if (homeBtn && homeBtn.nextSibling) railNav.insertBefore(railBtn, homeBtn.nextSibling);
      else railNav.appendChild(railBtn);
    }
    var mobileNav = document.getElementById('cvMobileNav');
    if (mobileNav && !mobileNav.querySelector('[data-cat-tasks]')) {
      var mobileBtn = tasksButton('cv-mnav-item');
      var mobileHome = mobileNav.querySelector('[data-cv-destination="home"]');
      if (mobileHome && mobileHome.nextSibling) mobileNav.insertBefore(mobileBtn, mobileHome.nextSibling);
      else mobileNav.appendChild(mobileBtn);
    }
  }

  function applyNav() {
    relabelHome();
    ensureTasksNav();
  }

  /* ---------------------------------------------------------------- */
  /* Declutter + composer                                              */
  /* ---------------------------------------------------------------- */

  function suppressTour() {
    var overlay = document.getElementById('tutorialOverlay');
    if (overlay) overlay.remove();
  }

  function syncComposerPlaceholder() {
    var input = document.getElementById('userInput');
    if (!input) return;
    var current = input.getAttribute('placeholder') || '';
    var isDefault = current === '' || current === 'Ask Crump anything…' || current === 'Message Crump';
    if (!isDefault) return;
    if (document.querySelector('.crump50-sheet')) return;
    input.setAttribute('placeholder', 'What should Crump get done for you?');
  }

  /* ---------------------------------------------------------------- */
  /* Boot + observers. The shell can re-render its rail, and the app   */
  /* container flips visibility as auth resolves, so the layer keeps   */
  /* its own DOM in sync with light observers instead of edits to the  */
  /* modules that own those surfaces.                                  */
  /* ---------------------------------------------------------------- */

  var navTickQueued = false;
  function queueSync() {
    if (navTickQueued) return;
    navTickQueued = true;
    requestAnimationFrame(function () {
      navTickQueued = false;
      applyNav();
      suppressTour();
      syncComposerPlaceholder();
      if (ensureToday()) renderToday();
    });
  }

  function boot() {
    applyNav();
    ensureToday();
    renderToday();
    syncComposerPlaceholder();
    suppressTour();

    var observer = new MutationObserver(function (records) {
      var relevant = records.some(function (record) {
        var target = record.target;
        if (!target || target.nodeType !== 1) return true;
        return !target.closest('#catToday, #catTasksPanel, #catBrowserPanel');
      });
      if (relevant) queueSync();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'style', 'hidden'],
    });

    document.addEventListener('crumpvision:show', function (event) {
      if (event && event.detail && event.detail.id === 'home') loadAgentData();
      queueSync();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      if (browserPanel && !browserPanel.hidden) closeBrowserPanel();
      else if (tasksPanel && tasksPanel.classList.contains('is-open')) closeTasks();
    });

    // Auth resolves after this layer loads, so retry the first fetch a
    // few times before settling into the signed-out empty state.
    loadAgentData();
    [1200, 3500, 8000].forEach(function (delay) {
      setTimeout(function () {
        if (!state.loaded && captureOwnerId()) loadAgentData();
        else renderToday();
      }, delay);
    });

    setInterval(function () {
      if (document.hidden) return;
      if (homeIsActive() && captureOwnerId()) loadAgentData();
    }, REFRESH_MS);
  }

  window.CrumpAgentToday = {
    openTasks: openTasks,
    openBrowser: openBrowserPanel,
    refresh: loadAgentData,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
