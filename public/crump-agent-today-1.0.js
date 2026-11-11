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
    automations: [],
    loaded: false,
    failed: false,
    loading: false,
    runDetails: {},
    google: null,
    brief: null,
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

  function currentUserIsGuest() {
    try {
      var access = window.CrumpAccess;
      if (access && typeof access.isGuest === 'function') return !!access.isGuest();
    } catch (_) {}
    try {
      if (window.currentUser && window.currentUser.isGuest) return true;
    } catch (_) {}
    return false;
  }

  function captureOwnerId() {
    // Guest sessions carry a user id, but agent data (capabilities,
    // approvals, runs) belongs to signed-in accounts: the endpoints
    // reject guest credentials, so fetching for a guest only produced
    // failed requests. Guests keep the signed-out Today state.
    if (currentUserIsGuest()) return '';
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

  /* The Google connection record is the single source of truth for
     brief availability: the connect notice and the brief both read the
     /api/connections/google/status response (connected + granted
     scopes on that one record). No surface treats Gmail or Calendar as
     connected independently of it, and until the record says connected
     the brief renders no inbox or calendar lines at all. */
  function googleConnected() {
    return !!(state.google && state.google.connected === true);
  }

  function googleScopes() {
    var scopes = [];
    if (!state.google || !Array.isArray(state.google.accounts)) return scopes;
    state.google.accounts.forEach(function (account) {
      if (account && account.status === 'connected' && Array.isArray(account.scopes)) {
        account.scopes.forEach(function (scope) {
          if (scopes.indexOf(scope) === -1) scopes.push(scope);
        });
      }
    });
    return scopes;
  }

  function googleScopeGranted(fragment) {
    // No recorded scopes means the status payload did not scope the
    // grant; the connection itself stays the authority and the brief
    // payload decides what actually renders.
    var scopes = googleScopes();
    if (!scopes.length) return true;
    return scopes.some(function (scope) { return String(scope).indexOf(fragment) !== -1; });
  }

  function loadAgentData() {
    if (state.loading) return Promise.resolve();
    if (!captureOwnerId()) {
      state.loaded = false;
      state.failed = false;
      renderToday();
      renderYouConnections();
      return Promise.resolve();
    }
    state.loading = true;
    return Promise.all([
      settled(api('/api/agent/capabilities')),
      settled(api('/api/agent/approvals')),
      settled(api('/api/agent/runs')),
      settled(api('/api/connections/google/status')),
      settled(api('/api/agent/today')),
      settled(api('/api/agent/automations')),
    ]).then(function (results) {
      state.loading = false;
      var caps = results[0];
      var approvals = results[1];
      var runs = results[2];
      var google = results[3];
      var brief = results[4];
      var automations = results[5];
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
      if (google.ok) {
        state.google = {
          configured: google.data.configured !== false,
          connected: google.data.connected === true,
          accounts: Array.isArray(google.data.accounts) ? google.data.accounts : [],
        };
      }
      if (brief.ok && brief.data.brief && typeof brief.data.brief === 'object') {
        state.brief = brief.data.brief;
      }
      if (automations.ok) {
        state.automations = Array.isArray(automations.data.automations)
          ? automations.data.automations : [];
      }
      state.loaded = caps.ok || approvals.ok || runs.ok;
      state.failed = !state.loaded;
      renderToday();
      renderChat();
      renderYouConnections();
      if (tasksPanel && tasksPanel.classList.contains('is-open')) renderTasks();
    }).catch(function () {
      state.loading = false;
      state.failed = true;
      renderToday();
      renderChat();
      renderYouConnections();
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

  /* The frozen detail is the inspectable record of the exact action,
     so it renders payload values exactly: array fields list every
     item (one per line), and no field is silently truncated or
     reduced to a count. What the user approves is what they can read
     here, in full. */
  function payloadList(payload) {
    var entries = [];
    if (payload && typeof payload === 'object') {
      Object.keys(payload).forEach(function (key) {
        var value = payload[key];
        var text;
        if (value == null) text = '';
        else if (typeof value === 'string') text = value;
        else if (typeof value === 'number' || typeof value === 'boolean') text = String(value);
        else if (Array.isArray(value)) {
          text = value.map(function (item) {
            var itemText = payloadText(item);
            if (!itemText && item && typeof item === 'object') {
              try { itemText = JSON.stringify(item); } catch (_) { itemText = ''; }
            }
            return itemText;
          }).join('\n');
        } else {
          try { text = JSON.stringify(value); } catch (_) { text = 'Details included'; }
        }
        entries.push([key, text]);
      });
    }
    if (!entries.length) return null;
    var list = h('dl', 'cat-payload');
    entries.forEach(function (pair) {
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

  function payloadText(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) {
      return value.map(function (item) { return payloadText(item); }).filter(Boolean).join(', ');
    }
    return '';
  }

  /* The approval card leads with the exact action, derived from the
     pending action's own frozen payload — the recipients for a send,
     the event title and time for a calendar create, the query for a
     search — never the capability label alone. The rendered summary
     stays as the secondary line when it adds anything. */
  function approvalExact(action) {
    var payload = action.payload && typeof action.payload === 'object' ? action.payload : {};
    var id = String(action.capabilityId || '');
    if (id === 'gmail.send' || id === 'gmail.draft') {
      var recipients = payloadText(payload.to || payload.recipients || payload.recipient);
      var verb = id === 'gmail.send' ? 'Send to ' : 'Draft to ';
      if (recipients) {
        var subject = payloadText(payload.subject);
        return { text: verb + recipients + (subject ? ' — “' + subject + '”' : ''), fromPayload: true };
      }
    }
    if (id === 'calendar.create') {
      var title = payloadText(payload.summary || payload.title);
      var when = fmtTime(payload.start);
      if (title) return { text: 'Book “' + title + '”' + (when ? ' · ' + when : ''), fromPayload: true };
    }
    if (id === 'gmail.search' || id === 'research.web_search') {
      var query = payloadText(payload.query);
      if (query) return { text: 'Search for “' + query + '”', fromPayload: true };
    }
    if (id === 'browser.read') {
      var url = payloadText(payload.url);
      if (url) return { text: 'Read ' + url, fromPayload: true };
    }
    if (id === 'browser.act') {
      var instruction = payloadText(payload.instruction);
      if (instruction) return { text: instruction, fromPayload: true };
    }
    var keys = ['to', 'recipients', 'summary', 'title', 'query', 'url', 'instruction', 'subject'];
    for (var i = 0; i < keys.length; i += 1) {
      var value = payloadText(payload[keys[i]]);
      if (value) return { text: capabilityTitle(id) + ' — ' + value, fromPayload: true };
    }
    return { text: action.summary || capabilityTitle(id), fromPayload: false };
  }

  function approvalExactSummary(action) {
    return approvalExact(action).text;
  }

  /* A secondary summary line renders only when it contributes a
     complete, non-duplicative sentence next to the headline. Stored
     summaries and capability verb phrases are often fragments of the
     headline itself ("Send an email — Send an email to", "Open the
     browser and"): a line that duplicates the headline, is a prefix
     of it, or trails off mid-phrase (ending on a verb, conjunction,
     or preposition still awaiting its object, with no sentence
     punctuation) is never rendered, on any card. The conservative
     rule is to suppress the line rather than complete it from data
     that is not there. */
  var DANGLING_FINAL_WORDS = {
    to: 1, and: 1, or: 1, nor: 1, but: 1, the: 1, a: 1, an: 1, for: 1,
    with: 1, of: 1, in: 1, on: 1, at: 1, by: 1, from: 1, into: 1,
    is: 1, are: 1, be: 1, will: 1, your: 1, you: 1, it: 1, this: 1, that: 1,
  };

  function summaryAddsInformation(summary, headline) {
    if (!summary) return false;
    var text = String(summary).trim();
    if (!text || !headline) return false;
    var normalize = function (value) {
      return String(value).toLowerCase().replace(/\s+/g, ' ').trim();
    };
    var line = normalize(text);
    var head = normalize(headline);
    if (line === head) return false;
    // A prefix of the headline, a line the headline already contains,
    // or a headline that is itself the start of the line duplicates
    // the headline instead of adding to it.
    if (head.indexOf(line) === 0 || line.indexOf(head) === 0) return false;
    if (head.indexOf(line) !== -1) return false;
    // Trailing off mid-phrase: the last word still awaits its object.
    var tail = text.replace(/[\s"”'’)\]]+$/, '');
    var lastWord = tail.split(/\s+/).pop().toLowerCase().replace(/[^a-z'-]/g, '');
    if (DANGLING_FINAL_WORDS[lastWord]) return false;
    // A complete sentence ends with sentence punctuation.
    if (!/[.!?]["”'’)\]]*$/.test(text)) return false;
    return true;
  }

  function approvalCard(action) {
    var card = h('article', 'cat-card');
    card.setAttribute('aria-label', capabilityTitle(action.capabilityId));
    var head = h('div', 'cat-card-head');
    var titleWrap = h('div');
    var exact = approvalExact(action).text;
    titleWrap.appendChild(h('h3', 'cat-card-title cat-card-exact', exact));
    // When the headline is derived from the frozen payload it is the
    // exact action; the stored summary may appear under it only when
    // it is a complete sentence that adds information (see
    // summaryAddsInformation). Fragment summaries never render. On
    // the fallback path the headline already is the stored summary
    // (or the capability title), so the same check keeps the line
    // from duplicating it.
    if (summaryAddsInformation(action.summary, exact)) {
      titleWrap.appendChild(h('p', 'cat-card-summary', action.summary));
    }
    head.appendChild(titleWrap);
    head.appendChild(h('span', statusClass('pending'), 'Waiting on you'));
    card.appendChild(head);

    var payload = payloadList(action.payload);
    if (payload) {
      var detail = h('div', 'cat-approval-detail');
      detail.hidden = true;
      detail.appendChild(payload);
      var detailToggle = button('Open detail', 'cat-detail-toggle');
      detailToggle.setAttribute('aria-expanded', 'false');
      detailToggle.addEventListener('click', function () {
        var open = detail.hidden;
        detail.hidden = !open;
        detailToggle.textContent = open ? 'Close detail' : 'Open detail';
        detailToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      card.appendChild(detailToggle);
      card.appendChild(detail);
    }

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

  /* The current step in plain language: the run detail's latest step
     when steps have been loaded for this run, otherwise the honest
     status line. A step is never invented for a run that has not
     reported one. */
  function runStepText(run) {
    var detail = state.runDetails[run.id];
    var steps = detail && Array.isArray(detail.steps) ? detail.steps : [];
    if (steps.length) return stepLabel(steps[steps.length - 1]);
    return statusLabel(run.status);
  }

  function runPreviewSource(run) {
    var detail = state.runDetails[run.id] || {};
    var candidates = [run.previewUrl, run.thumbnailUrl, run.preview, detail.previewUrl, detail.thumbnailUrl];
    for (var i = 0; i < candidates.length; i += 1) {
      if (typeof candidates[i] === 'string' && candidates[i]) return candidates[i];
    }
    return '';
  }

  function runCard(run) {
    var isBrowser = run.capabilityId === 'browser.act' || run.capabilityId === 'browser.read';
    var card = h('article', 'cat-card' + (isBrowser ? ' cat-card-browser' : ''));
    var head = h('div', 'cat-card-head');
    var titleWrap = h('div');
    titleWrap.appendChild(h('h3', 'cat-card-title', capabilityTitle(run.capabilityId)));
    var cap = state.capabilities[run.capabilityId];
    // The capability verb phrase is a headline fragment by design
    // ("Open the browser and", "Send an email to"); it renders as a
    // summary line only if it is ever a complete sentence that adds
    // information next to the title — otherwise it dangles.
    if (cap && summaryAddsInformation(cap.verbPhrase, capabilityTitle(run.capabilityId))) {
      titleWrap.appendChild(h('p', 'cat-card-summary', cap.verbPhrase));
    }
    head.appendChild(titleWrap);
    head.appendChild(h('span', statusClass(run.status), statusLabel(run.status)));
    card.appendChild(head);
    var stepText = runStepText(run);
    var step = h('p', 'cat-card-step');
    step.appendChild(h('span', 'cat-card-step-label', 'Current step'));
    step.appendChild(document.createTextNode(stepText));
    card.appendChild(step);
    if (isBrowser) {
      // A small preview tile: the run's own preview image when the run
      // data carries one, otherwise a neutral browser-chrome tile with
      // the step text — never a fabricated screenshot of a page.
      var tile = h('div', 'cat-browser-tile');
      var preview = runPreviewSource(run);
      if (preview) {
        var img = h('img', 'cat-browser-tile-img');
        img.src = preview;
        img.alt = '';
        tile.appendChild(img);
      } else {
        var chrome = h('div', 'cat-browser-tile-chrome');
        chrome.setAttribute('aria-hidden', 'true');
        chrome.appendChild(h('span', 'cat-browser-dot'));
        chrome.appendChild(h('span', 'cat-browser-dot'));
        chrome.appendChild(h('span', 'cat-browser-dot'));
        tile.appendChild(chrome);
        tile.appendChild(h('p', 'cat-browser-tile-text', stepText));
      }
      card.appendChild(tile);
    }
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
  /* Brief                                                             */
  /*                                                                   */
  /* Counts always come from the same loaded approvals/runs the       */
  /* sections render. Calendar and inbox rows render only when the    */
  /* connection record says connected, and only from the brief        */
  /* payload actually returned — a source the brief could not read    */
  /* says so on its own row instead of inventing a line.              */
  /* ---------------------------------------------------------------- */

  function briefCountsText() {
    var bits = [];
    var approvals = state.approvals.length;
    var live = liveRuns().length;
    bits.push(approvals === 1 ? '1 approval waiting' : approvals + ' approvals waiting');
    bits.push(live === 1 ? '1 task running' : live + ' tasks running');
    return bits.join(' · ');
  }

  function briefRow(label, value) {
    var row = h('div', 'cat-brief-row');
    row.appendChild(h('span', 'cat-brief-row-label', label));
    row.appendChild(h('span', 'cat-brief-row-value', value));
    return row;
  }

  function briefSourceRow(label, source, summarize) {
    if (typeof source === 'string') {
      var reason = source.indexOf('unavailable:') === 0
        ? source.slice('unavailable:'.length).trim()
        : source;
      return briefRow(label, reason || 'Unavailable right now.');
    }
    if (Array.isArray(source)) return briefRow(label, summarize(source));
    return briefRow(label, 'Unavailable right now.');
  }

  function briefCard() {
    var card = h('div', 'cat-card cat-brief-card');
    var weekday = new Date().toLocaleDateString(undefined, { weekday: 'long' });
    card.appendChild(h('h3', 'cat-brief-title', weekday + ' brief'));
    card.appendChild(h('p', 'cat-brief-counts', briefCountsText()));
    var brief = state.brief || {};
    if (googleScopeGranted('calendar')) {
      card.appendChild(briefSourceRow('Calendar', brief.calendar, function (events) {
        if (!events.length) return 'Nothing on the calendar today.';
        var first = events[0] || {};
        var when = fmtClock(first.start) || fmtTime(first.start);
        var line = first.summary || 'Calendar event';
        if (when) line += ' · ' + when;
        if (events.length > 1) line += ' · +' + (events.length - 1) + ' more';
        return line;
      }));
    }
    if (googleScopeGranted('gmail')) {
      card.appendChild(briefSourceRow('Inbox', brief.inboxHighlights, function (messages) {
        if (!messages.length) return 'Inbox is clear.';
        var first = messages[0] || {};
        var subject = first.subject || first.snippet || 'New message';
        return messages.length === 1
          ? subject
          : messages.length + ' threads · latest: ' + subject;
      }));
    }
    return card;
  }

  function connectNotice() {
    var wrap = h('div', 'cat-brief-connect');
    var connect = h('div', 'cat-connect-notice');
    connect.appendChild(h('p', 'cat-connect-text',
      'Connect Google for your brief — email and calendar, read-only.'));
    var connectNote = h('p', 'cat-connect-note', '');
    connectNote.hidden = true;
    var connectBtn = button('Connect Google', 'cat-connect-btn', function () {
      connectNote.textContent = 'Connecting Google is the next step — this notice turns into your brief as soon as it lands.';
      connectNote.hidden = false;
    });
    connect.appendChild(connectBtn);
    wrap.appendChild(connect);
    wrap.appendChild(connectNote);
    return wrap;
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
      googleConnected() ? 'google-in' : 'google-out',
      state.brief && state.brief.generatedAt ? String(state.brief.generatedAt) : 'no-brief',
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
      // One approval is visible at a time, in a fixed position: the
      // first pending approval renders as the full card, and any others
      // sit behind a single quiet count row — the real remaining count
      // from the same pending list the brief counts — that opens the
      // Tasks panel, where every pending approval renders in full.
      if (state.approvals.length) {
        waitStack.appendChild(approvalCard(state.approvals[0]));
        if (state.approvals.length > 1) {
          var moreCount = state.approvals.length - 1;
          var queueRow = button('+' + moreCount + ' more waiting', 'cat-queue-row');
          queueRow.setAttribute('aria-label',
            moreCount + ' more approvals waiting — open Tasks');
          queueRow.addEventListener('click', function () { openTasks(); });
          waitStack.appendChild(queueRow);
        }
      }
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
    briefArea.appendChild(h('h3', 'cat-today-section-title', 'Brief'));
    if (!googleConnected()) {
      // Disconnected: the slim notice plus genuinely local content
      // only — the counts come from the loaded runs/approvals, and no
      // inbox or calendar line renders in this state.
      briefArea.appendChild(connectNotice());
      if (state.approvals.length || live.length) {
        briefArea.appendChild(h('p', 'cat-brief-local', briefCountsText()));
      } else {
        briefArea.appendChild(h('p', 'cat-brief-local', 'Nothing needs you right now.'));
      }
    } else if (state.brief) {
      briefArea.appendChild(briefCard());
    } else {
      briefArea.appendChild(h('p', 'cat-brief-local',
        briefCountsText() + ' · Your brief could not load just now.'));
    }
    node.appendChild(briefArea);
  }

  /* ---------------------------------------------------------------- */
  /* Chat surface: the open conversation's own agent work              */
  /*                                                                   */
  /* The open conversation is the one the product shell has open:      */
  /* app.js keeps window.currentChatId current on every open, fresh,   */
  /* and delete path, and announces each opening with the              */
  /* crump:conversation-opened window event (detail.chatId). Runs      */
  /* carry that same id as conversationId in the runs payload, and a   */
  /* pending approval belongs to a conversation through its run. The   */
  /* section below is a sibling the layer owns, placed after the       */
  /* message list inside the workspace body — the shell keeps owning   */
  /* the message DOM itself, and the section never writes into it.     */
  /* ---------------------------------------------------------------- */

  function openConversationId() {
    try {
      return String(window.currentChatId || '').trim();
    } catch (_) {
      return '';
    }
  }

  /* The Chat view is the workspace with a conversation open in it:
     the app is showing, no vision stage is mounted over the workspace,
     the shell's current destination is the workspace itself (Today /
     Chat), and the launchpad home state is not up — the v1 body turns
     v1-home off exactly when the open conversation has messages. On
     Today (v1-home) this section never renders; Today is PR2's
     surface and keeps its own unscoped cards. */
  function chatIsActive() {
    var app = document.getElementById('appContainer');
    if (!app || app.style.display === 'none') return false;
    var stage = document.getElementById('cvStage');
    if (stage && !stage.hidden) return false;
    try {
      if (window.CrumpVision && typeof window.CrumpVision.current === 'function') {
        var current = window.CrumpVision.current();
        if (current && current !== 'today' && current !== 'chat' && current !== 'home') return false;
      }
    } catch (_) {}
    if (document.body.classList.contains('v1-home')) return false;
    return !!openConversationId();
  }

  var chatNode = null;
  var lastChatSignature = '';

  function ensureChatWork() {
    if (chatNode && chatNode.isConnected) return chatNode;
    var body = document.querySelector('.v1-workspace-body');
    if (!body) return null;
    chatNode = h('section', 'cat-chat-work');
    chatNode.id = 'catChatWork';
    chatNode.setAttribute('aria-label', 'Work in this conversation');
    chatNode.hidden = true;
    var container = document.getElementById('chatContainer');
    if (container && container.parentElement === body) {
      body.insertBefore(chatNode, container.nextSibling);
    } else {
      body.appendChild(chatNode);
    }
    return chatNode;
  }

  function runTime(run) {
    var value = Date.parse(run.updatedAt || run.createdAt || '');
    return isNaN(value) ? 0 : value;
  }

  /* This conversation's work, in the order the surface emphasises:
     pending approvals first (in the loaded list's own order), then
     live and waiting runs newest first, then finished runs newest
     first. Approvals join through their run's conversationId. */
  function conversationWork(conversationId) {
    var runsById = {};
    state.runs.forEach(function (run) {
      if (run && run.id) runsById[run.id] = run;
    });
    var approvals = state.approvals.filter(function (action) {
      if (!action || !action.runId) return false;
      var run = runsById[action.runId];
      return !!run && String(run.conversationId || '') === conversationId;
    });
    var covered = {};
    approvals.forEach(function (action) { covered[action.runId] = true; });
    var mine = state.runs.filter(function (run) {
      return run && String(run.conversationId || '') === conversationId;
    });
    var live = mine.filter(function (run) {
      return (RUNNING[run.status] || WAITING[run.status]) && !covered[run.id];
    }).sort(function (a, b) { return runTime(b) - runTime(a); });
    var done = mine.filter(function (run) {
      return TERMINAL[run.status];
    }).sort(function (a, b) { return runTime(b) - runTime(a); });
    return { approvals: approvals, live: live, done: done };
  }

  function resultCard(run) {
    var card = h('article', 'cat-card cat-card-result');
    var head = h('div', 'cat-card-head');
    var titleWrap = h('div');
    titleWrap.appendChild(h('h3', 'cat-card-title', capabilityTitle(run.capabilityId)));
    head.appendChild(titleWrap);
    head.appendChild(h('span', statusClass(run.status), statusLabel(run.status)));
    card.appendChild(head);
    card.appendChild(h('p', 'cat-card-summary', String(run.resultSummary)));
    var when = fmtTime(run.updatedAt || run.createdAt);
    if (when) card.appendChild(h('p', 'cat-card-meta', 'Updated ' + when));
    return card;
  }

  /* Quiet secondary rows: everything after the one primary card is a
     single line in a list, never another full card. A secondary
     approval row opens the Tasks panel, where that approval renders
     as a full card with its exact action and decision buttons. */
  function chatSecondaryRow(item) {
    if (item.kind === 'approval') {
      var row = button('', 'cat-chat-row cat-chat-row-action');
      row.setAttribute('aria-label',
        'Open Tasks to review: ' + approvalExactSummary(item.action));
      var approvalMain = h('span', 'cat-chat-row-main');
      approvalMain.appendChild(h('span', 'cat-chat-row-title', approvalExactSummary(item.action)));
      row.appendChild(approvalMain);
      row.appendChild(h('span', 'cat-chat-row-status', 'Waiting on you'));
      row.addEventListener('click', function () { openTasks(); });
      return row;
    }
    var run = item.run;
    var plain = h('div', 'cat-chat-row');
    var main = h('span', 'cat-chat-row-main');
    main.appendChild(h('span', 'cat-chat-row-title', capabilityTitle(run.capabilityId)));
    var detailText = item.kind === 'result' && typeof run.resultSummary === 'string' && run.resultSummary
      ? run.resultSummary
      : (RUNNING[run.status] || WAITING[run.status] ? runStepText(run) : statusLabel(run.status));
    main.appendChild(h('span', 'cat-chat-row-detail', detailText));
    plain.appendChild(main);
    plain.appendChild(h('span', 'cat-chat-row-status', statusLabel(run.status)));
    return plain;
  }

  function renderChat() {
    var node = ensureChatWork();
    if (!node) return;
    var conversationId = openConversationId();
    var active = chatIsActive();
    // Guests never render the section (and never fetch agent data:
    // loadAgentData is gated on the same owner check).
    var work = active && captureOwnerId() && state.loaded
      ? conversationWork(conversationId)
      : { approvals: [], live: [], done: [] };
    var items = [];
    work.approvals.forEach(function (action) { items.push({ kind: 'approval', action: action }); });
    work.live.forEach(function (run) { items.push({ kind: 'run', run: run }); });
    work.done.forEach(function (run) { items.push({ kind: 'result', run: run }); });

    if (!active || !items.length) {
      // No work in this conversation renders nothing at all — no
      // empty placeholder and no instructional copy.
      node.hidden = true;
      if (node.childNodes.length) node.innerHTML = '';
      lastChatSignature = '';
      return;
    }

    var signature = [
      conversationId,
      items.map(function (item) {
        return item.kind === 'approval'
          ? 'a:' + item.action.id + ':' + item.action.status
          : 'r:' + item.run.id + ':' + item.run.status + ':' + (item.run.updatedAt || '');
      }).join(','),
    ].join('|');
    if (signature === lastChatSignature && node.childNodes.length) {
      node.hidden = false;
      return;
    }
    lastChatSignature = signature;

    node.innerHTML = '';
    node.appendChild(h('h3', 'cat-chat-title', 'In this conversation'));
    var stack = h('div', 'cat-chat-stack');
    // One card carries the emphasis: the pending approval if there is
    // one, else the most recently updated live run, else the latest
    // finished result (a compact result card when the run recorded a
    // real result summary, the shared run card otherwise).
    var primary = items[0];
    var primaryCard;
    if (primary.kind === 'approval') primaryCard = approvalCard(primary.action);
    else if (primary.kind === 'result' &&
        typeof primary.run.resultSummary === 'string' && primary.run.resultSummary) {
      primaryCard = resultCard(primary.run);
    } else {
      primaryCard = runCard(primary.run);
    }
    primaryCard.classList.add('cat-chat-primary');
    stack.appendChild(primaryCard);
    var rest = items.slice(1);
    if (rest.length) {
      var more = h('div', 'cat-chat-more');
      rest.forEach(function (item) { more.appendChild(chatSecondaryRow(item)); });
      stack.appendChild(more);
    }
    node.appendChild(stack);
    node.hidden = false;
  }

  /* ---------------------------------------------------------------- */
  /* You surface: the Connections section of Settings                  */
  /*                                                                   */
  /* The shell delegates You to the Settings sheet. Its Connections    */
  /* panel renders from the SAME single Google record this layer      */
  /* already loads — state.google, from                              */
  /* GET /api/connections/google/status — so the brief, the connect    */
  /* notice, and You can never disagree about whether Google, Gmail,   */
  /* or Calendar is connected. Capability lines are derived from the   */
  /* connected account's granted scopes on that one record; there is   */
  /* no per-service fetch and no second state. Guests render the       */
  /* signed-out row and make no connections fetch (loadAgentData is    */
  /* gated on the same owner check). Connect/disconnect reuse the      */
  /* existing endpoints.                                               */
  /* ---------------------------------------------------------------- */

  function googleAccount() {
    if (!googleConnected() || !state.google || !Array.isArray(state.google.accounts)) return null;
    var found = null;
    state.google.accounts.forEach(function (account) {
      if (!found && account && account.status === 'connected') found = account;
    });
    return found;
  }

  function googleCapabilityLines(scopes) {
    var granted = Array.isArray(scopes) ? scopes : [];
    function has(fragment) {
      return granted.some(function (scope) { return String(scope).indexOf(fragment) !== -1; });
    }
    var lines = [];
    if (has('gmail.readonly')) lines.push(['Gmail', 'Read']);
    if (has('gmail.compose')) lines.push(['Gmail', 'Draft']);
    if (has('gmail.send')) lines.push(['Gmail', 'Send']);
    if (has('calendar.events')) lines.push(['Calendar', 'Read/write']);
    else if (has('calendar.readonly')) lines.push(['Calendar', 'Read']);
    return lines;
  }

  function youConnectionRow(label, value) {
    var row = h('div', 'settings-row cat-you-row');
    var text = h('div', 'settings-row-text');
    text.appendChild(h('div', 'settings-label', label));
    row.appendChild(text);
    row.appendChild(h('div', 'settings-label cat-you-value', value));
    return row;
  }

  function renderYouConnections() {
    var mount = document.querySelector('[data-cat-you-connections]');
    if (!mount) return;
    mount.innerHTML = '';
    var list = h('div', 'settings-list');
    var owner = captureOwnerId();
    var account = owner ? googleAccount() : null;
    if (!owner) {
      list.appendChild(youConnectionRow('Google', 'Not connected'));
      mount.appendChild(list);
      mount.appendChild(h('p', 'settings-help cat-you-note', 'Sign in to connect Google.'));
      return;
    }
    if (!state.loaded && !state.google) {
      list.appendChild(youConnectionRow('Google', 'Checking…'));
      mount.appendChild(list);
      return;
    }
    if (!account) {
      list.appendChild(youConnectionRow('Google', 'Not connected'));
      mount.appendChild(list);
      var connectNote = h('p', 'settings-help cat-you-note', '');
      connectNote.hidden = true;
      var connectBtn = button('Connect Google', 'cat-btn cat-you-action', function () {
        connectBtn.disabled = true;
        api('/api/connections/google/connect').then(function (data) {
          if (data && data.authorizationUrl) {
            window.location.assign(data.authorizationUrl);
            return;
          }
          throw new Error('connect unavailable');
        }).catch(function () {
          connectBtn.disabled = false;
          connectNote.textContent = 'Google connect is not available yet.';
          connectNote.hidden = false;
        });
      });
      mount.appendChild(connectBtn);
      mount.appendChild(connectNote);
      return;
    }
    var email = String(account.email || '').trim();
    list.appendChild(youConnectionRow('Google', email || 'Connected'));
    googleCapabilityLines(account.scopes).forEach(function (line) {
      list.appendChild(youConnectionRow(line[0], line[1]));
    });
    mount.appendChild(list);
    var disconnectNote = h('p', 'settings-help cat-you-note', '');
    disconnectNote.hidden = true;
    var disconnectBtn = button('Disconnect Google', 'cat-btn cat-you-action', function () {
      disconnectBtn.disabled = true;
      api('/api/connections/google/disconnect', {
        method: 'POST',
        body: email ? { accountEmail: email } : {},
      }).then(function () {
        state.google = null;
        renderYouConnections();
        loadAgentData();
      }).catch(function () {
        disconnectBtn.disabled = false;
        disconnectNote.textContent = 'Disconnect did not finish. Try again.';
        disconnectNote.hidden = false;
      });
    });
    mount.appendChild(disconnectBtn);
    mount.appendChild(disconnectNote);
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

  function rowMarker(status) {
    var kind = 'done';
    if (TERMINAL[status]) kind = status === 'failed' ? 'failed' : 'done';
    else if (WAITING[status] || status === 'pending') kind = 'waiting';
    else if (RUNNING[status]) kind = 'live';
    var marker = h('span', 'cat-row-marker cat-row-marker-' + kind);
    marker.setAttribute('aria-hidden', 'true');
    return marker;
  }

  function taskRow(run) {
    var row = h('div', 'cat-task-row');
    var headBtn = h('button', 'cat-task-row-head');
    headBtn.type = 'button';
    headBtn.setAttribute('aria-expanded', 'false');
    headBtn.appendChild(rowMarker(run.status));
    var main = h('span', 'cat-task-row-main');
    main.appendChild(h('span', 'cat-task-row-title', capabilityTitle(run.capabilityId)));
    var metaBits = [statusLabel(run.status)];
    var when = fmtTime(run.createdAt);
    if (when) metaBits.push('started ' + when);
    main.appendChild(h('span', 'cat-task-row-meta', metaBits.join(' · ')));
    headBtn.appendChild(main);
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

  /* ---------------------------------------------------------------- */
  /* Scheduled rows                                                    */
  /*                                                                   */
  /* An automation row is a record of a standing schedule. Its line    */
  /* is derived only from the fields the record itself carries: the    */
  /* stored schedule kind and local time, and the stored next run.     */
  /* No frequency wording is invented for a record that does not       */
  /* carry it. Paused automations stay in this group — they are part   */
  /* of the standing record, not finished work — with their paused     */
  /* status shown.                                                     */
  /* ---------------------------------------------------------------- */

  function fmtScheduleTime(value) {
    var match = /^([01][0-9]|2[0-3]):([0-5][0-9])$/.exec(String(value || ''));
    if (!match) return '';
    var hour = parseInt(match[1], 10);
    var suffix = hour < 12 ? 'AM' : 'PM';
    var hour12 = hour % 12 || 12;
    return hour12 + ':' + match[2] + ' ' + suffix;
  }

  function automationScheduleLine(automation) {
    var bits = [];
    var schedule = automation.schedule && typeof automation.schedule === 'object'
      ? automation.schedule : {};
    var timeText = fmtScheduleTime(schedule.time);
    if (schedule.kind === 'daily' && timeText) bits.push('Daily at ' + timeText);
    else if (timeText) bits.push(timeText);
    else if (typeof schedule.kind === 'string' && schedule.kind) bits.push(schedule.kind);
    var next = fmtTime(automation.nextRunAt);
    if (automation.enabled !== false && next) bits.push('Next ' + next);
    return bits.join(' · ');
  }

  function automationRow(automation) {
    var enabled = automation.enabled !== false;
    var row = h('div', 'cat-task-row cat-sched-row');
    var headBtn = h('button', 'cat-task-row-head');
    headBtn.type = 'button';
    headBtn.setAttribute('aria-expanded', 'false');
    var marker = h('span', 'cat-row-marker ' + (enabled ? 'cat-row-marker-live' : 'cat-row-marker-done'));
    marker.setAttribute('aria-hidden', 'true');
    headBtn.appendChild(marker);
    var main = h('span', 'cat-task-row-main');
    main.appendChild(h('span', 'cat-task-row-title', capabilityTitle(automation.capabilityId)));
    var metaBits = [enabled ? 'Scheduled' : 'Paused'];
    var line = automationScheduleLine(automation);
    if (line) metaBits.push(line);
    main.appendChild(h('span', 'cat-task-row-meta', metaBits.join(' · ')));
    headBtn.appendChild(main);
    row.appendChild(headBtn);

    var detail = h('div', 'cat-task-detail');
    detail.hidden = true;
    var schedule = automation.schedule && typeof automation.schedule === 'object'
      ? automation.schedule : {};
    var lines = [];
    if (line) lines.push(['Schedule', line]);
    if (schedule.timezone) lines.push(['Timezone', String(schedule.timezone)]);
    if (automation.lastRunAt && fmtTime(automation.lastRunAt)) {
      lines.push(['Last run', fmtTime(automation.lastRunAt)]);
    }
    if (!lines.length) lines.push(['Schedule', enabled ? 'Scheduled' : 'Paused']);
    lines.forEach(function (pair) {
      var item = h('p', 'cat-task-detail-line');
      item.appendChild(h('span', 'cat-task-detail-label', pair[0]));
      item.appendChild(document.createTextNode(pair[1]));
      detail.appendChild(item);
    });
    row.appendChild(detail);

    headBtn.addEventListener('click', function () {
      var open = detail.hidden;
      detail.hidden = !open;
      headBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    return row;
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

    var scheduledGroup = h('section', 'cat-group');
    scheduledGroup.appendChild(h('h3', 'cat-group-title', 'Scheduled'));
    if (!state.automations.length) {
      scheduledGroup.appendChild(h('p', 'cat-group-empty', 'Nothing is scheduled.'));
    }
    state.automations.forEach(function (automation) {
      scheduledGroup.appendChild(automationRow(automation));
    });
    tasksBody.appendChild(scheduledGroup);

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
    win.setAttribute('aria-labelledby', 'catBrowserTitle');

    var head = h('div', 'cat-browser-head');
    var headText = h('div', 'cat-browser-head-text');
    var title = h('h2', 'cat-browser-title', 'Live browser');
    title.id = 'catBrowserTitle';
    headText.appendChild(title);
    browserStep = h('p', 'cat-browser-step', 'No browser task is running.');
    browserStep.setAttribute('aria-live', 'polite');
    headText.appendChild(browserStep);
    head.appendChild(headText);
    // Pause and dismissal are distinct controls: Pause stays an
    // honest disabled control while sessions are not live, and Back
    // is the always-available way out of the panel.
    var headActions = h('div', 'cat-browser-head-actions');
    var pauseBtn = button('Pause', 'cat-btn cat-browser-pause');
    pauseBtn.disabled = true;
    pauseBtn.setAttribute('aria-disabled', 'true');
    headActions.appendChild(pauseBtn);
    var closeBtn = button('Back', 'cat-icon-btn cat-browser-dismiss', closeBrowserPanel);
    closeBtn.setAttribute('aria-label', 'Back — close the browser panel');
    headActions.appendChild(closeBtn);
    head.appendChild(headActions);
    win.appendChild(head);

    var viewport = h('div', 'cat-browser-viewport');
    viewport.appendChild(h('p', null,
      'Per-user browser sessions are not live yet, so there is nothing to show here. ' +
      'When a browser task runs, you will watch it here and be able to pause it or take over.'));
    win.appendChild(viewport);

    var controls = h('div', 'cat-browser-controls');
    var takeOverBtn = button('Take over', 'cat-btn');
    takeOverBtn.disabled = true;
    takeOverBtn.setAttribute('aria-disabled', 'true');
    controls.appendChild(takeOverBtn);
    win.appendChild(controls);

    // A rightward swipe on the panel dismisses it, matching the
    // slide-over direction; taps and vertical scrolling are untouched.
    var swipeStart = null;
    win.addEventListener('touchstart', function (event) {
      var touch = event.touches && event.touches[0];
      swipeStart = touch ? { x: touch.clientX, y: touch.clientY } : null;
    }, { passive: true });
    win.addEventListener('touchend', function (event) {
      if (!swipeStart) return;
      var touch = event.changedTouches && event.changedTouches[0];
      var start = swipeStart;
      swipeStart = null;
      if (!touch) return;
      var dx = touch.clientX - start.x;
      var dy = touch.clientY - start.y;
      if (dx > 64 && Math.abs(dy) < 48) closeBrowserPanel();
    }, { passive: true });
    win.addEventListener('touchcancel', function () { swipeStart = null; }, { passive: true });

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
    var closeButton = browserPanel.querySelector('.cat-browser-dismiss');
    if (closeButton) closeButton.focus({ preventScroll: true });
  }

  function closeBrowserPanel() {
    if (!browserPanel) return;
    browserPanel.hidden = true;
    if (browserOpener && browserOpener.isConnected) browserOpener.focus({ preventScroll: true });
    browserOpener = null;
  }

  // The panel is modal, so while it is open Tab and Shift+Tab cycle
  // among its enabled controls instead of walking out into the
  // dimmed chat behind it. Disabled controls are skipped — Pause
  // and Take over while sessions are not live — so with Back as the
  // only enabled control both directions stay on Back. The trap
  // only intercepts Tab at the edges (or when focus sits outside
  // the panel); it never touches the open/close paths, so every
  // dismissal route keeps its exact behavior.
  function browserPanelFocusables() {
    var focusables = [];
    if (!browserPanel) return focusables;
    var nodes = browserPanel.querySelectorAll(
      'a[href], button, input, select, textarea, [tabindex]');
    nodes.forEach(function (node) {
      if (node.disabled) return;
      var tabindex = node.getAttribute('tabindex');
      if (tabindex !== null && Number(tabindex) < 0) return;
      if (!node.getClientRects().length) return;
      focusables.push(node);
    });
    return focusables;
  }

  function keepBrowserPanelFocus(event) {
    var focusables = browserPanelFocusables();
    if (!focusables.length) {
      event.preventDefault();
      return;
    }
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    var active = document.activeElement;
    var inside = Boolean(active) && browserPanel.contains(active);
    if (event.shiftKey) {
      if (!inside || active === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      }
    } else if (!inside || active === last) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    }
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
      if (ensureChatWork()) renderChat();
    });
  }

  function boot() {
    applyNav();
    ensureToday();
    renderToday();
    ensureChatWork();
    renderChat();
    syncComposerPlaceholder();
    suppressTour();

    var observer = new MutationObserver(function (records) {
      var relevant = records.some(function (record) {
        var target = record.target;
        if (!target || target.nodeType !== 1) return true;
        return !target.closest('#catToday, #catChatWork, #catTasksPanel, #catBrowserPanel');
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
    // The shell announces every conversation opening on window with
    // the opened id; the chat section re-scopes to it and refreshes
    // its data so the cards it shows are that conversation's own.
    window.addEventListener('crump:conversation-opened', function () {
      renderChat();
      if (captureOwnerId()) loadAgentData();
      queueSync();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        if (browserPanel && !browserPanel.hidden) closeBrowserPanel();
        else if (tasksPanel && tasksPanel.classList.contains('is-open')) closeTasks();
      } else if (event.key === 'Tab' && browserPanel && !browserPanel.hidden) {
        keepBrowserPanelFocus(event);
      }
    });

    // Opening the Settings Connections panel refreshes the one Google
    // record and re-renders the You rows from it.
    document.addEventListener('click', function (event) {
      var tab = event.target && event.target.closest
        ? event.target.closest('[data-v1-settings-tab="connections"]')
        : null;
      if (!tab) return;
      renderYouConnections();
      if (captureOwnerId()) loadAgentData();
    });

    // Auth resolves after this layer loads, so retry the first fetch a
    // few times before settling into the signed-out empty state.
    loadAgentData();
    [1200, 3500, 8000].forEach(function (delay) {
      setTimeout(function () {
        if (!state.loaded && captureOwnerId()) loadAgentData();
        else { renderToday(); renderChat(); }
      }, delay);
    });

    setInterval(function () {
      if (document.hidden) return;
      if ((homeIsActive() || chatIsActive()) && captureOwnerId()) loadAgentData();
    }, REFRESH_MS);
  }

  window.CrumpAgentToday = {
    openTasks: openTasks,
    openBrowser: openBrowserPanel,
    refresh: loadAgentData,
    renderYouConnections: renderYouConnections,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
