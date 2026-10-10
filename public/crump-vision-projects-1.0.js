/*
 * Ask Crump — Director's Cut · Projects view (1.0)
 *
 * Registers the 'projects' view on window.CrumpVision. Everything shown here
 * is real: projects come from GET /api/projects, the durable-memory timeline
 * from GET /api/projects/:id (project_context rows + manuscript updates),
 * linked chats from GET /api/projects/:id/chats, and keepsakes from the real
 * Library (GET /api/library/books filtered by projectId). The only thing this
 * view stores itself is the "Next steps" checklist, in localStorage under
 * the 'cv-projects' key — plain user data, never mixed with app state.
 *
 * Defensive by design: if CrumpVision is not ready yet, registration retries
 * until it is. All markup is escaped; all events are bound with
 * addEventListener (no inline handlers).
 */
(function () {
  'use strict';

  if (window.__cvProjectsRegistered) return;
  window.__cvProjectsRegistered = true;

  var STORE_KEY = 'cv-projects';

  function cv() {
    return window.CrumpVision || null;
  }

  function esc(value) {
    var c = cv();
    if (c && typeof c.esc === 'function') return c.esc(value);
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function eyebrowHTML(text) {
    var c = cv();
    if (c && typeof c.eyebrow === 'function') {
      try {
        var out = c.eyebrow(text);
        if (typeof out === 'string' && out) return out;
      } catch (_) { /* fall through to local markup */ }
    }
    return '<div class="cv-eyebrow">' + esc(text) + '</div>';
  }

  function fmtDate(value) {
    if (!value) return '';
    var d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function fmtCount(value) {
    var n = Number(value || 0);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'm';
    if (n >= 1000) return Math.round(n / 1000) + 'k';
    return String(n);
  }

  async function api(path) {
    var response = await fetch(path, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    var data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.success === false) {
      var error = new Error(data.error || data.message || 'Request failed (' + response.status + ')');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  /* ------------------------------------------------------------------ */
  /* Next-steps store (localStorage, namespaced 'cv-projects').          */
  /* ------------------------------------------------------------------ */

  function readStore() {
    try {
      var raw = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
    } catch (_) { /* corrupted or unavailable — start clean */ }
    return {};
  }

  function writeStore(store) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); } catch (_) { /* private mode etc. */ }
  }

  function readSteps(projectId) {
    var store = readStore();
    var entry = store[projectId];
    if (entry && Array.isArray(entry.steps)) return entry.steps;
    return [];
  }

  function persistSteps(projectId, steps) {
    var store = readStore();
    store[projectId] = { steps: steps };
    writeStore(store);
  }

  function newStepId() {
    return 'step-' + Date.now().toString(36) + '-' + Math.floor(Math.random() * 1e6).toString(36);
  }

  /* ------------------------------------------------------------------ */
  /* Timeline assembly from real project metadata.                       */
  /* ------------------------------------------------------------------ */

  var KIND_LABELS = {
    decision: 'Decision',
    note: 'Note',
    question: 'Open question',
    canon: 'Canon',
    instruction: 'Instruction',
    file: 'Reference file',
    memory: 'Memory',
  };

  function kindLabel(kind) {
    var key = String(kind || '').toLowerCase();
    if (KIND_LABELS[key]) return KIND_LABELS[key];
    if (!key) return 'Entry';
    return key.charAt(0).toUpperCase() + key.slice(1);
  }

  function buildTimeline(project, context) {
    var entries = [];
    if (project && project.created_at) {
      entries.push({
        at: project.created_at,
        kind: 'Project created',
        title: 'Project created',
        body: project.description || '',
      });
    }
    var canon = (context && Array.isArray(context.canon)) ? context.canon : [];
    canon.forEach(function (row) {
      entries.push({
        at: row.updated_at,
        kind: kindLabel(row.kind),
        title: row.label || kindLabel(row.kind),
        body: row.content || '',
      });
    });
    var manuscripts = (context && Array.isArray(context.manuscripts)) ? context.manuscripts : [];
    manuscripts.forEach(function (m) {
      entries.push({
        at: m.updated_at,
        kind: 'Keepsake updated',
        title: m.title || 'Untitled manuscript',
        body: (m.status ? String(m.status) : ''),
      });
    });
    entries = entries.filter(function (e) { return e.at && !Number.isNaN(new Date(e.at).getTime()); });
    entries.sort(function (a, b) { return new Date(b.at).getTime() - new Date(a.at).getTime(); });
    return entries;
  }

  /* ------------------------------------------------------------------ */
  /* View render.                                                        */
  /* ------------------------------------------------------------------ */

  function renderProjectsView(root) {
    if (!root) return;
    root.innerHTML = '';
    root.className = 'cvp-root';

    var header = document.createElement('div');
    header.className = 'cvp-header';
    header.innerHTML =
      eyebrowHTML('WORK THAT OUTLIVES ONE CHAT') +
      '<h1 class="cvp-title">Projects</h1>' +
      '<p class="cvp-lede">Every durable body of work keeps its instructions, decisions, conversations, and keepsakes together. Pick one up where you left it.</p>';
    root.appendChild(header);

    var switcher = document.createElement('div');
    switcher.className = 'cvp-switcher';
    switcher.setAttribute('aria-label', 'Projects');
    root.appendChild(switcher);

    var detail = document.createElement('div');
    detail.className = 'cvp-detail';
    root.appendChild(detail);

    switcher.innerHTML =
      '<div class="cvp-skeleton" aria-hidden="true"><i></i><i></i><i></i></div>' +
      '<p class="cvp-status" role="status">Loading your projects…</p>';

    api('/api/projects').then(function (data) {
      var projects = Array.isArray(data.projects) ? data.projects : [];
      if (!projects.length) {
        switcher.innerHTML = '';
        detail.innerHTML = emptyProjectsHTML();
        bindEmpty(detail);
        return;
      }
      renderSwitcher(switcher, projects);
      selectProject(detail, projects[0].id, projects);
    }).catch(function (error) {
      switcher.innerHTML = '';
      detail.innerHTML =
        '<div class="cvp-panel cvp-error" role="alert">' +
          '<h2>Projects could not load.</h2>' +
          '<p>' + esc(error.message || 'Try again in a moment.') + '</p>' +
          '<button type="button" class="cvp-button" data-cvp-retry>Try again</button>' +
        '</div>';
      var retry = detail.querySelector('[data-cvp-retry]');
      if (retry) retry.addEventListener('click', function () { renderProjectsView(root); });
    });
  }

  function emptyProjectsHTML() {
    return (
      '<div class="cvp-empty">' +
        '<img class="cvp-empty-mascot" src="/assets/crump-mascot-official.jpg" alt="Crump, the Ask Crump mascot" width="120" height="120">' +
        '<h2>Give serious work somewhere to continue.</h2>' +
        '<p>No projects yet. When a conversation becomes durable work, save it as a Project and it will live here — with its instructions, decisions, and keepsakes intact.</p>' +
        '<p class="cvp-empty-hint">Projects are created from a chat, so the memory stays attached to the work that made it.</p>' +
      '</div>'
    );
  }

  function bindEmpty() { /* no actions in the projects empty state by design */ }

  function renderSwitcher(switcher, projects) {
    switcher.innerHTML =
      '<div class="cvp-switcher-row" role="tablist" aria-label="Your projects">' +
      projects.map(function (project, index) {
        return (
          '<button type="button" class="cvp-switch' + (index === 0 ? ' is-active' : '') + '" role="tab" ' +
            'aria-selected="' + (index === 0 ? 'true' : 'false') + '" ' +
            'data-cvp-project="' + esc(project.id) + '">' +
            '<span class="cvp-switch-name">' + esc(project.name || 'Untitled project') + '</span>' +
            '<span class="cvp-switch-date">' + esc(fmtDate(project.updated_at) || '') + '</span>' +
          '</button>'
        );
      }).join('') +
      '</div>';
    var buttons = Array.prototype.slice.call(switcher.querySelectorAll('[data-cvp-project]'));
    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        buttons.forEach(function (other) {
          var active = other === button;
          other.classList.toggle('is-active', active);
          other.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        selectProject(document.querySelector('.cvp-detail'), button.getAttribute('data-cvp-project'), projects);
      });
    });
  }

  function selectProject(detail, projectId, projects) {
    if (!detail) return;
    var project = projects.filter(function (p) { return String(p.id) === String(projectId); })[0] || null;
    if (!project) return;

    detail.innerHTML =
      '<div class="cvp-skeleton is-wide" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' +
      '<p class="cvp-status" role="status">Opening ' + esc(project.name || 'project') + '…</p>';

    Promise.all([
      api('/api/projects/' + encodeURIComponent(project.id)).catch(function () { return null; }),
      api('/api/projects/' + encodeURIComponent(project.id) + '/chats').catch(function () { return null; }),
      api('/api/library/books').catch(function () { return null; }),
    ]).then(function (results) {
      var detailData = results[0];
      var chatsData = results[1];
      var booksData = results[2];
      var context = detailData && detailData.context ? detailData.context : {};
      var fullProject = (detailData && detailData.project) ? detailData.project : project;
      var conversations = (chatsData && Array.isArray(chatsData.conversations)) ? chatsData.conversations : [];
      var books = (booksData && Array.isArray(booksData.books)) ? booksData.books : [];
      var keepsakes = books.filter(function (b) { return String(b.projectId || '') === String(project.id); });
      renderDetail(detail, fullProject, context, conversations, keepsakes);
    }).catch(function () {
      detail.innerHTML =
        '<div class="cvp-panel cvp-error" role="alert">' +
          '<h2>This project could not open.</h2>' +
          '<p>Try again in a moment.</p>' +
          '<button type="button" class="cvp-button" data-cvp-retry-detail>Try again</button>' +
        '</div>';
      var retry = detail.querySelector('[data-cvp-retry-detail]');
      if (retry) retry.addEventListener('click', function () { selectProject(detail, projectId, projects); });
    });
  }

  function renderDetail(detail, project, context, conversations, keepsakes) {
    var timeline = buildTimeline(project, context);
    var steps = readSteps(String(project.id));

    var timelineHTML;
    if (!timeline.length) {
      timelineHTML =
        '<div class="cvp-timeline-empty">' +
          '<p>No durable memory recorded yet.</p>' +
          '<span>When this project holds instructions, canon, or decisions, they will appear here as a dated record.</span>' +
        '</div>';
    } else {
      timelineHTML =
        '<ol class="cvp-timeline">' +
        timeline.map(function (entry) {
          return (
            '<li class="cvp-timeline-item">' +
              '<div class="cvp-timeline-marker" aria-hidden="true"></div>' +
              '<div class="cvp-timeline-body">' +
                '<div class="cvp-timeline-head">' +
                  '<span class="cvp-timeline-kind">' + esc(entry.kind) + '</span>' +
                  '<time class="cvp-timeline-date">' + esc(fmtDate(entry.at)) + '</time>' +
                '</div>' +
                '<h4>' + esc(entry.title) + '</h4>' +
                (entry.body ? '<p>' + esc(entry.body) + '</p>' : '') +
              '</div>' +
            '</li>'
          );
        }).join('') +
        '</ol>';
    }

    detail.innerHTML =
      '<section class="cvp-project-head">' +
        eyebrowHTML('PROJECT') +
        '<h2>' + esc(project.name || 'Untitled project') + '</h2>' +
        (project.description ? '<p class="cvp-project-desc">' + esc(project.description) + '</p>' : '') +
        '<p class="cvp-project-meta">' +
          (project.created_at ? '<span>Created ' + esc(fmtDate(project.created_at)) + '</span>' : '') +
          (project.updated_at ? '<span>Updated ' + esc(fmtDate(project.updated_at)) + '</span>' : '') +
        '</p>' +
      '</section>' +
      '<div class="cvp-grid">' +
        '<section class="cvp-panel" aria-label="Durable memory">' +
          '<div class="cvp-panel-head">' + eyebrowHTML('DURABLE MEMORY') + '</div>' +
          timelineHTML +
        '</section>' +
        '<aside class="cvp-side">' +
          '<section class="cvp-panel" aria-label="Next steps">' +
            '<div class="cvp-panel-head">' + eyebrowHTML('NEXT STEPS') + '</div>' +
            '<div data-cvp-steps></div>' +
          '</section>' +
          '<section class="cvp-panel" aria-label="Linked chats">' +
            '<div class="cvp-panel-head">' + eyebrowHTML('LINKED CHATS') + '</div>' +
            '<div data-cvp-chats></div>' +
          '</section>' +
          '<section class="cvp-panel" aria-label="Keepsakes">' +
            '<div class="cvp-panel-head">' + eyebrowHTML('KEEPSAKES') + '</div>' +
            '<div data-cvp-keepsakes></div>' +
          '</section>' +
        '</aside>' +
      '</div>';

    renderSteps(detail.querySelector('[data-cvp-steps]'), project);
    renderChats(detail.querySelector('[data-cvp-chats]'), conversations);
    renderKeepsakes(detail.querySelector('[data-cvp-keepsakes]'), keepsakes, project);
  }

  /* ---- Next steps (localStorage, namespaced 'cv-projects') ---- */

  function renderSteps(mount, project) {
    if (!mount) return;
    var projectId = String(project.id);
    var steps = readSteps(projectId);

    function persist() { persistSteps(projectId, steps); }

    function paint() {
      var list = mount.querySelector('[data-cvp-step-list]');
      if (!list) return;
      if (!steps.length) {
        list.innerHTML = '<p class="cvp-quiet">Nothing queued. Add the next move for this project.</p>';
        return;
      }
      list.innerHTML = steps.map(function (step) {
        return (
          '<li class="cvp-step' + (step.done ? ' is-done' : '') + '" data-cvp-step="' + esc(step.id) + '">' +
            '<label class="cvp-step-label">' +
              '<input type="checkbox" data-cvp-step-check' + (step.done ? ' checked' : '') + '>' +
              '<span>' + esc(step.text) + '</span>' +
            '</label>' +
            '<button type="button" class="cvp-step-remove" data-cvp-step-remove aria-label="Remove step">×</button>' +
          '</li>'
        );
      }).join('');
      list.querySelectorAll('[data-cvp-step-check]').forEach(function (box) {
        box.addEventListener('change', function () {
          var item = box.closest('[data-cvp-step]');
          var step = steps.filter(function (s) { return s.id === item.getAttribute('data-cvp-step'); })[0];
          if (step) { step.done = box.checked; persist(); }
          item.classList.toggle('is-done', box.checked);
        });
      });
      list.querySelectorAll('[data-cvp-step-remove]').forEach(function (button) {
        button.addEventListener('click', function () {
          var item = button.closest('[data-cvp-step]');
          steps = steps.filter(function (s) { return s.id !== item.getAttribute('data-cvp-step'); });
          persist();
          paint();
        });
      });
    }

    mount.innerHTML =
      '<ul class="cvp-step-list" data-cvp-step-list></ul>' +
      '<form class="cvp-step-add" id="cvp-step-form" data-cvp-step-form>' +
        '<input type="text" data-cvp-step-input placeholder="Add a next step…" maxlength="200" aria-label="Add a next step">' +
        '<button type="submit" class="cvp-button">Add</button>' +
      '</form>';

    var form = mount.querySelector('#cvp-step-form');
    var input = mount.querySelector('[data-cvp-step-input]');
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      steps.push({ id: newStepId(), text: text, done: false, createdAt: new Date().toISOString() });
      persist();
      input.value = '';
      paint();
    });

    paint();
  }

  /* ---- Linked chats (real, content-free metadata) ---- */

  function renderChats(mount, conversations) {
    if (!mount) return;
    if (!conversations.length) {
      mount.innerHTML = '<p class="cvp-quiet">No conversations linked to this project yet.</p>';
      return;
    }
    mount.innerHTML =
      '<ul class="cvp-chat-list">' +
      conversations.map(function (chat) {
        return (
          '<li class="cvp-chat">' +
            '<span class="cvp-chat-title">' + esc(chat.title || 'New conversation') + '</span>' +
            '<time class="cvp-chat-date">' + esc(fmtDate(chat.updatedAt || chat.createdAt)) + '</time>' +
          '</li>'
        );
      }).join('') +
      '</ul>';
  }

  /* ---- Keepsakes produced by this project (real Library data) ---- */

  function renderKeepsakes(mount, keepsakes, project) {
    if (!mount) return;
    if (!keepsakes.length) {
      mount.innerHTML = '<p class="cvp-quiet">No keepsakes from this project yet. Finished documents and decks will appear here.</p>';
      return;
    }
    mount.innerHTML =
      '<ul class="cvp-keepsake-list">' +
      keepsakes.map(function (book) {
        return (
          '<li class="cvp-keepsake">' +
            '<span class="cvp-keepsake-title">' + esc(book.title || 'Untitled manuscript') + '</span>' +
            '<span class="cvp-keepsake-meta">' +
              esc(String(book.status || 'draft')) + ' · ' +
              esc(fmtCount(book.wordCount)) + ' words · ' +
              esc(fmtDate(book.updatedAt)) +
            '</span>' +
            '<button type="button" class="cvp-link" data-cvp-open-library>Open in Library</button>' +
          '</li>'
        );
      }).join('') +
      '</ul>';
    mount.querySelectorAll('[data-cvp-open-library]').forEach(function (button) {
      button.addEventListener('click', function () {
        var c = cv();
        try {
          if (c && typeof c.navigate === 'function') { c.navigate('library'); return; }
        } catch (_) { /* fall through */ }
        window.location.href = '/app';
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Registration — retries until the CrumpVision shell is ready.        */
  /* ------------------------------------------------------------------ */

  function register() {
    var c = cv();
    if (!c || typeof c.registerView !== 'function') return false;
    try {
      c.registerView('projects', { title: 'Projects', render: renderProjectsView });
    } catch (_) {
      return false;
    }
    return true;
  }

  var attempts = 0;
  if (!register()) {
    var timer = setInterval(function () {
      attempts += 1;
      if (register() || attempts >= 150) clearInterval(timer);
    }, 200);
  }
})();
