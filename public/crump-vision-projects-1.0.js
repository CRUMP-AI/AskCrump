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

  var mountedProjectsRoot = null;
  var projectsAuthScrubberRegistered = false;
  var projectsAuthFallbackBound = false;

  function captureProjectsAuthBoundary() {
    var boundary = window.CrumpAuthBoundary;
    var ownerId = String(
      boundary && typeof boundary.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : (window.currentUser && window.currentUser.id) || '',
    ).trim();
    var rawRevision = boundary && typeof boundary.revision === 'function'
      ? boundary.revision()
      : 0;
    var revision = Number(rawRevision);
    var demo = !ownerId && window.__crumpVisionDemo === true;
    return Object.freeze({
      ownerId: demo ? '__crump_projects_demo__' : ownerId,
      revision: Number.isFinite(revision) ? revision : 0,
      demo: demo,
    });
  }

  function projectsAuthBoundaryIsCurrent(snapshot) {
    if (!snapshot || !snapshot.ownerId) return false;
    var current = captureProjectsAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
  }

  function projectsViewIsCurrent(root, snapshot) {
    return Boolean(
      root && root.isConnected && projectsAuthBoundaryIsCurrent(snapshot)
      && String(root.dataset.cvpOwnerId || '') === snapshot.ownerId
      && Number(root.dataset.cvpOwnerRevision) === snapshot.revision
    );
  }

  function projectsDestinationIsActive() {
    var c = cv();
    return !c || typeof c.current !== 'function' || c.current() === 'projects';
  }

  function scrubProjectsPrivateView(boundary) {
    var root = mountedProjectsRoot;
    if (!root || !root.isConnected || !projectsDestinationIsActive()) return;
    // app.js owns the full lexical/exported conversation state and visible
    // sidebar/message cleanup. Invoke its memory-only scrub before a new
    // account's Projects view can reveal or act on anything; durable,
    // account-scoped storage is deliberately untouched.
    try { window.CrumpConversationState?.scrubAuthBoundary?.(); } catch (_) {}
    root.className = 'cvp-root';
    root.innerHTML =
      '<div class="cvp-panel" role="status">' +
        '<h2>Projects are ready for the signed-in account.</h2>' +
        '<p>Open Projects again to load that account\'s private work.</p>' +
      '</div>';
    delete root.dataset.cvpOwnerId;
    delete root.dataset.cvpOwnerRevision;
    var nextOwnerId = String(boundary && boundary.nextUserId || '').trim();
    if (nextOwnerId) {
      queueMicrotask(function () {
        if (mountedProjectsRoot !== root || !root.isConnected || root.dataset.cvpOwnerId
            || !projectsDestinationIsActive()) return;
        var current = captureProjectsAuthBoundary();
        if (current.ownerId === nextOwnerId) renderProjectsView(root);
      });
    }
  }

  function ensureProjectsAuthScrubber() {
    var boundary = window.CrumpAuthBoundary;
    if (!projectsAuthScrubberRegistered && boundary && typeof boundary.register === 'function') {
      boundary.register('vision-projects', scrubProjectsPrivateView);
      projectsAuthScrubberRegistered = true;
    }
    if (!projectsAuthFallbackBound) {
      projectsAuthFallbackBound = true;
      window.addEventListener('crump:authentication-required', scrubProjectsPrivateView);
      window.addEventListener('crump:authenticated-ready', function () {
        ensureProjectsAuthScrubber();
        queueMicrotask(function () {
          var root = mountedProjectsRoot;
          if (!root || !root.isConnected || !projectsDestinationIsActive()) return;
          var current = captureProjectsAuthBoundary();
          if (!root.dataset.cvpOwnerId) {
            if (current.ownerId) renderProjectsView(root);
            return;
          }
          var snapshot = {
            ownerId: String(root.dataset.cvpOwnerId || ''),
            revision: Number(root.dataset.cvpOwnerRevision),
          };
          if (!projectsAuthBoundaryIsCurrent(snapshot)) {
            scrubProjectsPrivateView({nextUserId: current.ownerId});
          }
        });
      });
    }
  }

  function releaseProjectsView() {
    mountedProjectsRoot = null;
  }

  function fmtCount(value) {
    var n = Number(value || 0);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'm';
    if (n >= 1000) return Math.round(n / 1000) + 'k';
    return String(n);
  }

  async function api(path, authBoundary) {
    if (!authBoundary || !authBoundary.ownerId || !projectsAuthBoundaryIsCurrent(authBoundary)) {
      throw new Error('The signed-in account changed before this request began.');
    }
    var response = await fetch(path, {
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
      },
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
    ensureProjectsAuthScrubber();
    mountedProjectsRoot = root;
    var authBoundary = captureProjectsAuthBoundary();
    root.dataset.cvpOwnerId = authBoundary.ownerId;
    root.dataset.cvpOwnerRevision = String(authBoundary.revision);
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
    var authed = Boolean(authBoundary.ownerId && projectsAuthBoundaryIsCurrent(authBoundary));
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

    api('/api/projects', authBoundary).then(function (data) {
      if (!projectsViewIsCurrent(root, authBoundary)) return;
      var projects = Array.isArray(data.projects) ? data.projects : [];
      if (!projects.length) {
        switcher.innerHTML = '';
        detail.innerHTML = emptyProjectsHTML();
        bindEmpty(detail, root, authBoundary);
        return;
      }
      var routed = routedProjectId();
      var selected = projects.filter(function (project) {
        return String(project.id) === String(routed);
      })[0] || projects[0];
      renderSwitcher(switcher, projects, selected.id, root, authBoundary);
      selectProject(detail, selected.id, projects, authBoundary);
    }).catch(function (error) {
      if (!projectsViewIsCurrent(root, authBoundary)) return;
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
        '<h2>Give your work a place to continue.</h2>' +
        '<p>When a conversation becomes ongoing work, save it as a Project. Its context, conversations, and manuscripts will stay together here.</p>' +
        '<p class="cvp-empty-hint">Start in Ask, then save the conversation when you are ready to keep building.</p>' +
        '<button type="button" class="cvp-button cvp-empty-action" data-cvp-start-ask>Start in Ask</button>' +
      '</div>'
    );
  }

  function bindEmpty(detail, root, authBoundary) {
    var start = detail && detail.querySelector ? detail.querySelector('[data-cvp-start-ask]') : null;
    if (start) start.addEventListener('click', function () {
      if (!projectsViewIsCurrent(root, authBoundary)) return;
      if (window.CrumpVision && typeof window.CrumpVision.navigate === 'function') {
        window.CrumpVision.navigate('ask');
      }
    });
  }

  function renderSwitcher(switcher, projects, selectedProjectId, root, authBoundary) {
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
        if (!projectsViewIsCurrent(root, authBoundary)) return;
        buttons.forEach(function (other) {
          var active = other === button;
          other.classList.toggle('is-active', active);
          other.setAttribute('aria-selected', active ? 'true' : 'false');
          other.setAttribute('tabindex', active ? '0' : '-1');
        });
        var detail = document.getElementById('cvpProjectDetail');
        if (detail) detail.setAttribute('aria-labelledby', button.id);
        selectProject(detail, button.getAttribute('data-cvp-project'), projects, authBoundary);
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

  function selectProject(detail, projectId, projects, authBoundary) {
    if (!detail) return;
    var root = detail.closest('.cvp-root');
    if (!projectsViewIsCurrent(root, authBoundary)) return;
    var project = projects.filter(function (p) { return String(p.id) === String(projectId); })[0] || null;
    if (!project) return;
    var selectionId = String(project.id);
    detail.dataset.cvpActiveProject = selectionId;

    detail.innerHTML =
      '<div class="cvp-skeleton is-wide" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' +
      '<p class="cvp-status" role="status">Opening ' + esc(project.name || 'project') + '…</p>';

    Promise.all([
      api('/api/projects/' + encodeURIComponent(project.id), authBoundary).catch(function () { return null; }),
      api('/api/projects/' + encodeURIComponent(project.id) + '/chats', authBoundary).catch(function () { return null; }),
      api('/api/library/books', authBoundary).catch(function () { return null; }),
    ]).then(function (results) {
      if (!projectsViewIsCurrent(root, authBoundary)
          || detail.dataset.cvpActiveProject !== selectionId) return;
      var detailData = results[0];
      var chatsData = results[1];
      var booksData = results[2];
      var context = detailData && detailData.context ? detailData.context : {};
      var fullProject = (detailData && detailData.project) ? detailData.project : project;
      var conversations = (chatsData && Array.isArray(chatsData.conversations)) ? chatsData.conversations : [];
      var books = (booksData && Array.isArray(booksData.books)) ? booksData.books : [];
      var keepsakes = books.filter(function (b) { return String(b.projectId || '') === String(project.id); });
      renderDetail(detail, fullProject, context, conversations, keepsakes, authBoundary);
    }).catch(function () {
      if (!projectsViewIsCurrent(root, authBoundary)
          || detail.dataset.cvpActiveProject !== selectionId) return;
      detail.innerHTML =
        '<div class="cvp-panel cvp-error" role="alert">' +
          '<h2>This project could not open.</h2>' +
          '<p>Try again in a moment.</p>' +
          '<button type="button" class="cvp-button" data-cvp-retry-detail>Try again</button>' +
        '</div>';
      var retry = detail.querySelector('[data-cvp-retry-detail]');
      if (retry) retry.addEventListener('click', function () {
        selectProject(detail, projectId, projects, authBoundary);
      });
    });
  }

  function renderDetail(detail, project, context, conversations, keepsakes, authBoundary) {
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

    renderChats(
      detail.querySelector('[data-cvp-chats]'),
      conversations,
      String(project.id || ''),
      authBoundary,
    );
    renderKeepsakes(detail.querySelector('[data-cvp-keepsakes]'), keepsakes, authBoundary);
  }

  /* ---- Linked chats (real, content-free metadata) ---- */

  function localConversation(chatId) {
    var target = String(chatId || '').trim();
    if (!target || !Array.isArray(window.chats)) return null;
    return window.chats.filter(function (chat) {
      return String(chat && (chat.id || chat.chat_id) || '').trim() === target;
    })[0] || null;
  }

  function resumeActionIsCurrent(button, projectId, authBoundary) {
    var detail = button && typeof button.closest === 'function'
      ? button.closest('.cvp-detail')
      : null;
    return Boolean(
      button && button.isConnected && detail && detail.isConnected
      && String(detail.dataset.cvpActiveProject || '') === String(projectId || '')
      && projectsViewIsCurrent(detail.closest('.cvp-root'), authBoundary)
    );
  }

  function canOpenAsk() {
    return Boolean(
      (window.CrumpVision && typeof window.CrumpVision.navigate === 'function')
      || (window.CrumpNavigation5930 && typeof window.CrumpNavigation5930.open === 'function')
    );
  }

  function openAsk() {
    if (window.CrumpVision && typeof window.CrumpVision.navigate === 'function') {
      window.CrumpVision.navigate('ask');
      return true;
    }
    if (window.CrumpNavigation5930 && typeof window.CrumpNavigation5930.open === 'function') {
      window.CrumpNavigation5930.open('ask');
      return true;
    }
    return false;
  }

  function recordProjectResume() {
    var track = window.CrumpAnalytics && window.CrumpAnalytics.track;
    if (typeof track !== 'function') return;
    void Promise.resolve(track('RecentWorkResumed', {
      eventKey: 'recent-work-resumed',
      source: 'project',
    })).catch(function () { /* analytics must not interrupt the restored conversation */ });
  }

  async function resumeProjectConversation(button, rawChatId, rawProjectId, authBoundary) {
    if (!button || button.disabled || button.dataset.cvpOpening === 'true') return false;
    var chatId = String(rawChatId || '').trim();
    var projectId = String(rawProjectId || '').trim();
    if (!chatId || !projectId || !authBoundary || !authBoundary.ownerId
        || !resumeActionIsCurrent(button, projectId, authBoundary)) {
      return false;
    }

    var originalText = button.textContent;
    button.dataset.cvpOpening = 'true';
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Opening…';
    try {
      if (!localConversation(chatId)) {
        if (typeof window.syncChatsFromServer !== 'function') {
          throw new Error('Conversation synchronization is unavailable.');
        }
        var result = await window.syncChatsFromServer();
        if (result && result.success === false) {
          throw new Error('Conversation synchronization failed.');
        }
      }
      if (!resumeActionIsCurrent(button, projectId, authBoundary)) return false;
      if (!localConversation(chatId)) {
        throw new Error('The conversation was not returned by synchronization.');
      }
      if (typeof window.loadChat !== 'function' || !canOpenAsk()) {
        throw new Error('The conversation workspace is still loading.');
      }

      await Promise.resolve(window.loadChat(chatId));
      if (!resumeActionIsCurrent(button, projectId, authBoundary)) return false;
      if (String(window.currentChatId || '').trim() !== chatId) {
        throw new Error('The conversation did not open.');
      }
      if (!openAsk()) throw new Error('The Ask workspace did not open.');
      recordProjectResume();
      window.requestAnimationFrame(function () {
        document.getElementById('userInput')?.focus({preventScroll: true});
      });
      return true;
    } catch (_) {
      if (resumeActionIsCurrent(button, projectId, authBoundary)) {
        window.showToast?.(
          'That conversation could not be restored on this device yet. Your Project is still here—try again.',
          'error',
        );
      }
      return false;
    } finally {
      delete button.dataset.cvpOpening;
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = originalText;
    }
  }

  function renderChats(mount, conversations, projectId, authBoundary) {
    if (!mount) return;
    if (!conversations.length) {
      mount.innerHTML = '<p class="cvp-quiet">No conversations are linked to this project yet.</p>';
      return;
    }
    mount.innerHTML =
      '<ul class="cvp-chat-list">' +
      conversations.map(function (chat) {
        var chatId = String(chat.chatId || '').trim();
        var title = String(chat.title || 'New conversation').replace(/\s+/g, ' ').trim() || 'New conversation';
        return (
          '<li class="cvp-chat">' +
            '<span class="cvp-chat-title">' + esc(title) + '</span>' +
            '<time class="cvp-chat-date">' + esc(fmtDate(chat.updatedAt || chat.createdAt)) + '</time>' +
            (chatId
              ? '<button type="button" class="cvp-link cvp-chat-continue" data-cvp-chat="' + esc(chatId) + '" aria-label="Continue “' + esc(title) + '” in Ask">Continue</button>'
              : '') +
          '</li>'
        );
      }).join('') +
      '</ul>';
    mount.querySelectorAll('[data-cvp-chat]').forEach(function (button) {
      button.addEventListener('click', function () {
        void resumeProjectConversation(
          button,
          button.getAttribute('data-cvp-chat'),
          projectId,
          authBoundary,
        );
      });
    });
  }

  /* ---- Books and manuscripts produced by this project (real Library data) ---- */

  function renderKeepsakes(mount, keepsakes, authBoundary) {
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
        var root = button.closest('.cvp-root');
        if (!projectsViewIsCurrent(root, authBoundary)) return;
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
      c.registerView('projects', {
        title: 'Projects',
        render: renderProjectsView,
        onHide: releaseProjectsView,
      });
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
