/*
 * Ask Crump — Director's Cut · Projects view (1.0)
 *
 * Registers the 'projects' view on window.CrumpVision. Everything shown here
 * is real: projects come from GET /api/projects, the durable-memory timeline
 * from GET /api/projects/:id (project_context rows + manuscript updates),
 * linked chats from GET /api/projects/:id/chats, and books from the real
 * Library (GET /api/library/books filtered by projectId). This view is
 * intentionally read-only: it does not invent or persist a second project
 * task system alongside the server-authoritative workspace.
 *
 * Defensive by design: if CrumpVision is not ready yet, registration retries
 * until it is. All markup is escaped; all events are bound with
 * addEventListener (no inline handlers).
 */
(function () {
  'use strict';

  if (window.__cvProjectsRegistered) return;
  window.__cvProjectsRegistered = true;

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

  function routedProjectId() {
    try { return new URL(window.location.href).searchParams.get('project') || ''; }
    catch (_) { return ''; }
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
        kind: 'Manuscript updated',
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
      eyebrowHTML('Your ongoing work') +
      '<h1 class="cvp-title">Projects</h1>' +
      '<p class="cvp-lede">Pick up a project with its context, conversations, and manuscripts together — right where you left it.</p>';
    root.appendChild(header);

    var switcher = document.createElement('div');
    switcher.className = 'cvp-switcher';
    switcher.setAttribute('aria-label', 'Projects');
    root.appendChild(switcher);

    var detail = document.createElement('div');
    detail.className = 'cvp-detail';
    detail.id = 'cvpProjectDetail';
    detail.setAttribute('role', 'region');
    detail.setAttribute('aria-label', 'Project details');
    detail.setAttribute('tabindex', '0');
    root.appendChild(detail);

    switcher.innerHTML =
      '<div class="cvp-skeleton" aria-hidden="true"><i></i><i></i><i></i></div>' +
      '<p class="cvp-status" role="status">Loading your projects…</p>';

    // Authenticated data only: never fire workspace API calls for signed-out
    // visitors (they 404 and pollute the console). Demo mode serves fixture
    // data through its own interceptor.
    var authed = Boolean(window.currentUser && window.currentUser.id);
    var demo = window.__crumpVisionDemo === true;
    if (!authed && !demo) {
      switcher.innerHTML = '';
      detail.innerHTML =
        '<div class="cvp-panel" role="status">' +
          '<h2>Sign in to see your projects.</h2>' +
          '<p>Work you save as a Project lives here with its context, conversations, and books intact.</p>' +
        '</div>';
      return;
    }

    api('/api/projects').then(function (data) {
      var projects = Array.isArray(data.projects) ? data.projects : [];
      if (!projects.length) {
        switcher.innerHTML = '';
        detail.innerHTML = emptyProjectsHTML();
        bindEmpty(detail);
        return;
      }
      var routed = routedProjectId();
      var selected = projects.filter(function (project) {
        return String(project.id) === String(routed);
      })[0] || projects[0];
      renderSwitcher(switcher, projects, selected.id);
      selectProject(detail, selected.id, projects);
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
        '<img class="cvp-empty-mascot" src="/assets/brand/crump-mascot.png" alt="Crump, the Ask Crump mascot" width="120" height="120">' +
        '<h2>Give your work a place to continue.</h2>' +
        '<p>When a conversation becomes ongoing work, save it as a Project. Its context, conversations, and manuscripts will stay together here.</p>' +
        '<p class="cvp-empty-hint">Start in Ask, then save the conversation when you are ready to keep building.</p>' +
        '<button type="button" class="cvp-button cvp-empty-action" data-cvp-start-ask>Start in Ask</button>' +
      '</div>'
    );
  }

  function bindEmpty(root) {
    var start = root && root.querySelector ? root.querySelector('[data-cvp-start-ask]') : null;
    if (start) start.addEventListener('click', function () {
      if (window.CrumpVision && typeof window.CrumpVision.navigate === 'function') {
        window.CrumpVision.navigate('ask');
      }
    });
  }

  function renderSwitcher(switcher, projects, selectedProjectId) {
    switcher.innerHTML =
      '<div class="cvp-switcher-row" role="tablist" aria-label="Your projects">' +
      projects.map(function (project, index) {
        var active = String(project.id) === String(selectedProjectId);
        return (
          '<button type="button" class="cvp-switch' + (active ? ' is-active' : '') + '" role="tab" ' +
            'id="cvpProjectTab-' + index + '" aria-controls="cvpProjectDetail" tabindex="' + (active ? '0' : '-1') + '" ' +
            'aria-selected="' + (active ? 'true' : 'false') + '" ' +
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
          other.setAttribute('tabindex', active ? '0' : '-1');
        });
        var detail = document.getElementById('cvpProjectDetail');
        if (detail) detail.setAttribute('aria-labelledby', button.id);
        selectProject(detail, button.getAttribute('data-cvp-project'), projects);
      });
      button.addEventListener('keydown', function (event) {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        var index = buttons.indexOf(button);
        var offset = event.key === 'ArrowRight' ? 1 : -1;
        var next = buttons[(index + offset + buttons.length) % buttons.length];
        next.focus();
        next.click();
      });
    });
    var selectedButton = switcher.querySelector('[aria-selected="true"]');
    var detail = document.getElementById('cvpProjectDetail');
    if (detail && selectedButton) {
      detail.setAttribute('role', 'tabpanel');
      detail.removeAttribute('aria-label');
      detail.setAttribute('aria-labelledby', selectedButton.id);
    }
  }

  function selectProject(detail, projectId, projects) {
    if (!detail) return;
    var project = projects.filter(function (p) { return String(p.id) === String(projectId); })[0] || null;
    if (!project) return;
    var selectionId = String(project.id);
    detail.dataset.cvpActiveProject = selectionId;

    detail.innerHTML =
      '<div class="cvp-skeleton is-wide" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' +
      '<p class="cvp-status" role="status">Opening ' + esc(project.name || 'project') + '…</p>';

    Promise.all([
      api('/api/projects/' + encodeURIComponent(project.id)).catch(function () { return null; }),
      api('/api/projects/' + encodeURIComponent(project.id) + '/chats').catch(function () { return null; }),
      api('/api/library/books').catch(function () { return null; }),
    ]).then(function (results) {
      if (!detail.isConnected || detail.dataset.cvpActiveProject !== selectionId) return;
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
      if (!detail.isConnected || detail.dataset.cvpActiveProject !== selectionId) return;
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
    var timelineHTML;
    if (!timeline.length) {
      timelineHTML =
        '<div class="cvp-timeline-empty">' +
          '<p>No project history yet.</p>' +
          '<span>Instructions, notes, and decisions will appear here as the project takes shape.</span>' +
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
        eyebrowHTML('Project overview') +
        '<h2>' + esc(project.name || 'Untitled project') + '</h2>' +
        (project.description ? '<p class="cvp-project-desc">' + esc(project.description) + '</p>' : '') +
        '<p class="cvp-project-meta">' +
          (project.created_at ? '<span>Created ' + esc(fmtDate(project.created_at)) + '</span>' : '') +
          (project.updated_at ? '<span>Updated ' + esc(fmtDate(project.updated_at)) + '</span>' : '') +
        '</p>' +
      '</section>' +
      '<div class="cvp-grid">' +
        '<section class="cvp-panel" aria-label="Project history">' +
          '<div class="cvp-panel-head">' + eyebrowHTML('Project history') + '</div>' +
          timelineHTML +
        '</section>' +
        '<aside class="cvp-side">' +
          '<section class="cvp-panel" aria-label="Linked chats">' +
            '<div class="cvp-panel-head">' + eyebrowHTML('Conversations') + '</div>' +
            '<div data-cvp-chats></div>' +
          '</section>' +
          '<section class="cvp-panel" aria-label="Books and manuscripts">' +
            '<div class="cvp-panel-head">' + eyebrowHTML('Books & manuscripts') + '</div>' +
            '<div data-cvp-keepsakes></div>' +
          '</section>' +
        '</aside>' +
      '</div>';

    renderChats(detail.querySelector('[data-cvp-chats]'), conversations);
    renderKeepsakes(detail.querySelector('[data-cvp-keepsakes]'), keepsakes);
  }

  /* ---- Linked chats (real, content-free metadata) ---- */

  function renderChats(mount, conversations) {
    if (!mount) return;
    if (!conversations.length) {
      mount.innerHTML = '<p class="cvp-quiet">No conversations are linked to this project yet.</p>';
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

  /* ---- Books and manuscripts produced by this project (real Library data) ---- */

  function renderKeepsakes(mount, keepsakes) {
    if (!mount) return;
    if (!keepsakes.length) {
      mount.innerHTML = '<p class="cvp-quiet">No books or manuscripts from this project yet. Long-form writing you create here will appear in your Library.</p>';
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
