/*
 * Crump Vision — application shell (1.0)
 *
 * Owns the calm, product-first destination rail (desktop) and five-item
 * bottom nav (mobile). The destinations are exactly five: Today, Chat,
 * Tasks, Projects, and You. Today is the real Ask workspace; Chat owns the
 * real conversation drawer; Tasks opens the agent task record; Projects
 * and You delegate only to existing production surfaces. Screens register
 * through window.CrumpVision.registerView; a destination with no
 * registered vision view falls back to the existing product behavior, so
 * chat, sync, and billing keep working untouched.
 *
 * This is the sole visual owner of navigation. The legacy navigation module
 * remains a behavior adapter for the proven product sheets, focus management,
 * analytics, and creation handoffs; it no longer paints a second rail. Old
 * destination ids continue to resolve to their closest current destination so
 * bookmarked and delegated actions keep working: the Library and Studios ids
 * resolve to Projects, while the Library and Studios views stay registered
 * under their own keys for the surfaces that still reach them in code.
 */
(() => {
  'use strict';

  if (window.__crumpVisionShellLoaded) return;

  var OLD_TO_NEW = {
    ask: 'today', home: 'today', today: 'today',
    autonomous: 'today', code: 'today', create: 'today',
    chats: 'chat', chat: 'chat', tasks: 'tasks',
    projects: 'projects', files: 'projects', library: 'projects',
    video: 'projects', studios: 'projects',
    you: 'you', profile: 'you', more: 'you',
  };
  // New ids map back to the ids the legacy behavior adapter understands.
  // The adapter's home workspace id is 'ask' (its destinations list and
  // openAsk), so today -> 'ask'. Chat never reaches the legacy fallback
  // (the shell owns the conversation drawer); 'chats' is recorded so the
  // map stays a faithful inverse of the old chats destination.
  var NEW_TO_OLD = {
    today: 'ask', chat: 'chats', tasks: 'ask',
    projects: 'projects', you: 'you',
  };
  var ORDER = ['today', 'chat', 'tasks', 'projects', 'you'];
  var MOBILE_ORDER = ['today', 'chat', 'tasks', 'projects', 'you'];
  var MORE_DESTINATIONS = [];
  var ANALYTICS_SOURCE = {
    today: 'ask', chat: 'chats', tasks: 'tasks', projects: 'projects', you: 'you',
  };
  var ACTIVE_PARENT = {};
  var LABELS = {
    today: 'Today', chat: 'Chat', tasks: 'Tasks', projects: 'Projects', you: 'You',
    home: 'Today', chats: 'Chat', files: 'Files', library: 'Library',
    studios: 'Studios', autonomous: 'Autonomous',
    more: 'More',
  };
  var SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
  var ICONS = {
    today: SVG_OPEN + '<path d="M4.2 10.35 12 4.1l7.8 6.25v8.25a1.3 1.3 0 0 1-1.3 1.3h-13a1.3 1.3 0 0 1-1.3-1.3v-8.25Z"/><path d="M9.2 19.75v-5.8h5.6v5.8"/></svg>',
    home: SVG_OPEN + '<path d="M4.2 10.35 12 4.1l7.8 6.25v8.25a1.3 1.3 0 0 1-1.3 1.3h-13a1.3 1.3 0 0 1-1.3-1.3v-8.25Z"/><path d="M9.2 19.75v-5.8h5.6v5.8"/></svg>',
    chat: SVG_OPEN + '<path d="M6.1 5.15h11.8a2.35 2.35 0 0 1 2.35 2.35v6.2a2.35 2.35 0 0 1-2.35 2.35h-6.25l-4.9 3.1.82-3.1H6.1a2.35 2.35 0 0 1-2.35-2.35V7.5A2.35 2.35 0 0 1 6.1 5.15Z"/><path d="M8 9.25h8M8 12.25h5.35"/></svg>',
    tasks: SVG_OPEN + '<path d="M9.6 6.1h9.9M9.6 12h9.9M9.6 17.9h9.9"/><path d="m3.7 6.3 1.3 1.3 2.6-2.6M3.7 12.2l1.3 1.3 2.6-2.6M3.7 18.1l1.3 1.3 2.6-2.6"/></svg>',
    chats: SVG_OPEN + '<path d="M6.1 5.15h11.8a2.35 2.35 0 0 1 2.35 2.35v6.2a2.35 2.35 0 0 1-2.35 2.35h-6.25l-4.9 3.1.82-3.1H6.1a2.35 2.35 0 0 1-2.35-2.35V7.5A2.35 2.35 0 0 1 6.1 5.15Z"/><path d="M8 9.25h8M8 12.25h5.35"/></svg>',
    ask: SVG_OPEN + '<path d="M6.15 5.4h11.7a2.35 2.35 0 0 1 2.35 2.35v6.4a2.35 2.35 0 0 1-2.35 2.35h-6.2l-4.85 3.1.8-3.1H6.15a2.35 2.35 0 0 1-2.35-2.35v-6.4A2.35 2.35 0 0 1 6.15 5.4Z"/><path d="m15.8 7.8.42 1.03 1.03.42-1.03.42-.42 1.03-.42-1.03-1.03-.42 1.03-.42.42-1.03Z"/></svg>',
    projects: SVG_OPEN + '<path d="M5.25 7.1h5.15l1.7 1.75h6.65a1.9 1.9 0 0 1 1.9 1.9v6.05a2.2 2.2 0 0 1-2.2 2.2H5.55a2.2 2.2 0 0 1-2.2-2.2V9a1.9 1.9 0 0 1 1.9-1.9Z"/><path d="M5.15 7.1V5.3h5.7l1.65 1.8"/></svg>',
    files: SVG_OPEN + '<path d="M7.15 4.1h6.25l3.45 3.45v9.9a2.05 2.05 0 0 1-2.05 2.05H7.15a2.05 2.05 0 0 1-2.05-2.05V6.15A2.05 2.05 0 0 1 7.15 4.1Z"/><path d="M13.2 4.25v3.7h3.55M8.35 12h5.45M8.35 15.2h4"/></svg>',
    library: SVG_OPEN + '<path d="M4.25 5.15h5.1A2.65 2.65 0 0 1 12 7.8v11.05a3.45 3.45 0 0 0-3.45-2.65h-4.3V5.15Z"/><path d="M19.75 5.15h-5.1A2.65 2.65 0 0 0 12 7.8v11.05a3.45 3.45 0 0 1 3.45-2.65h4.3V5.15Z"/></svg>',
    video: SVG_OPEN + '<rect x="3.8" y="5.25" width="16.4" height="13.5" rx="2.4"/><path d="m10.25 9.15 5 2.85-5 2.85v-5.7Z"/></svg>',
    studios: SVG_OPEN + '<rect x="3.8" y="4.8" width="16.4" height="14.4" rx="2.4"/><path d="m6.8 15.8 3.65-3.7 2.75 2.7 1.85-1.85 2.15 2.15"/><circle cx="9" cy="9" r="1.25"/></svg>',
    autonomous: SVG_OPEN + '<path d="M7.1 5.1h9.8l3 5.35-3 5.35H7.1l-3-5.35 3-5.35Z"/><path d="m9.4 8.2-2.25 2.25 2.25 2.25M14.6 8.2l2.25 2.25-2.25 2.25M13.05 7.45l-2.1 6"/></svg>',
    profile: SVG_OPEN + '<circle cx="12" cy="8.1" r="3.35"/><path d="M5.6 19.2c.75-3.7 2.9-5.55 6.4-5.55s5.65 1.85 6.4 5.55"/></svg>',
    you: SVG_OPEN + '<circle cx="12" cy="8.1" r="3.35"/><path d="M5.6 19.2c.75-3.7 2.9-5.55 6.4-5.55s5.65 1.85 6.4 5.55"/></svg>',
    more: SVG_OPEN + '<circle cx="5.25" cy="12" r="1.05" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.05" fill="currentColor" stroke="none"/><circle cx="18.75" cy="12" r="1.05" fill="currentColor" stroke="none"/></svg>',
    new: SVG_OPEN + '<path d="M12 4.2v15.6M4.2 12h15.6"/><path d="m18.2 4 .35.85.85.35-.85.35-.35.85-.35-.85-.85-.35.85-.35.35-.85Z"/></svg>',
    conversations: SVG_OPEN + '<path d="M6.1 5.15h11.8a2.35 2.35 0 0 1 2.35 2.35v6.2a2.35 2.35 0 0 1-2.35 2.35h-6.25l-4.9 3.1.82-3.1H6.1a2.35 2.35 0 0 1-2.35-2.35V7.5A2.35 2.35 0 0 1 6.1 5.15Z"/><path d="M8 9.25h8M8 12.25h5.35"/></svg>',
  };

  var ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  var views = new Map();
  var currentId = 'today';
  var booted = false;
  var explicitNav = false;
  var settling = false;
  var stage = null;
  var stageBody = null;
  var inertTargets = [];
  var moreMenu = null;
  var moreMenuOpener = null;
  var conversationDrawerOpener = null;
  var conversationDrawerReturnId = null;
  var drawerObserver = null;

  /* ------------------------------------------------------------------ */
  /* Public helpers                                                      */
  /* ------------------------------------------------------------------ */

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ESCAPE_MAP[ch];
    });
  }

  function el(html) {
    var template = document.createElement('template');
    template.innerHTML = String(html == null ? '' : html).trim();
    return template.content.firstElementChild;
  }

  function eyebrow(text) {
    var node = document.createElement('div');
    node.className = 'cv-eyebrow';
    node.textContent = text == null ? '' : String(text);
    return node;
  }

  function card(opts) {
    var o = opts || {};
    var section = el('<section class="cv-card"></section>');
    var head = el('<div class="cv-card-head"></div>');
    var headText = el('<div></div>');
    if (o.eyebrow) headText.appendChild(eyebrow(o.eyebrow));
    if (o.title != null && String(o.title) !== '') {
      var h = document.createElement('h3');
      h.className = 'cv-card-title';
      h.textContent = String(o.title);
      headText.appendChild(h);
    }
    head.appendChild(headText);
    section.appendChild(head);
    if (o.body != null && String(o.body) !== '') {
      var body = el('<div class="cv-card-copy"></div>');
      body.innerHTML = String(o.body);
      section.appendChild(body);
    }
    var actions = Array.isArray(o.actions) ? o.actions : [];
    if (actions.length) {
      var wrap = el('<div class="cv-actions"></div>');
      actions.forEach(function (a) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'cv-btn ' + (a && a.primary ? 'cv-btn-primary' : 'cv-btn-ghost');
        btn.textContent = (a && a.label) || '';
        if (a && typeof a.onSelect === 'function') btn.addEventListener('click', a.onSelect);
        wrap.appendChild(btn);
      });
      section.appendChild(wrap);
    }
    return section;
  }

  /* ------------------------------------------------------------------ */
  /* View registry + navigation                                          */
  /* ------------------------------------------------------------------ */

  function normalizeId(raw) {
    return OLD_TO_NEW[String(raw == null ? '' : raw).toLowerCase()] || null;
  }

  function current() {
    return currentId;
  }

  function registerView(id, def) {
    var sourceKey = String(id == null ? '' : id).toLowerCase();
    // Today and You keep delegating to the authoritative Ask and account
    // surfaces. Studios can register because its view delegates only to the
    // released Image and Video tools.
    if (sourceKey === 'ask' || sourceKey === 'home' || sourceKey === 'today' || sourceKey === 'profile' || sourceKey === 'you') return false;
    if (!def || typeof def.render !== 'function') return false;
    // Library and Studios are no longer destinations, but their views stay
    // registered under their own keys so the surfaces that reach them in
    // code keep working; navigation resolves their ids to Projects.
    var key = (sourceKey === 'library' || sourceKey === 'studios')
      ? sourceKey
      : normalizeId(sourceKey);
    if (!key) return false;
    views.set(key, def);
    if (booted && key === currentId && !isMounted()) mountView(key, def);
    return true;
  }

  // Leaving Tasks for another destination closes the Tasks panel through
  // the Today layer's own Close control; the panel observer then returns
  // the highlight to the workspace underneath.
  function closeTasksPanel() {
    var panel = document.getElementById('catTasksPanel');
    if (!panel || panel.hidden) return;
    var close = panel.querySelector('[aria-label="Close Tasks"]');
    if (close) close.click();
  }

  function navigate(rawId, options) {
    ensureBoot();
    var id = normalizeId(rawId) || 'today';
    if (id === 'chat') {
      toggleConversationDrawer(document.activeElement);
      return;
    }
    if (id === 'tasks') {
      openTasksDestination(options);
      return;
    }
    closeTasksPanel();
    closeMoreMenu(false);
    closeConversationDrawer(false, false);
    explicitNav = true;
    settling = false;
    var def = views.get(id);
    if (def) {
      mountView(id, def, options);
      return;
    }
    fallbackToLegacy(id, options);
  }

  // Tasks is a destination state owned by the agent Today layer: the task
  // record opens over the workspace and Tasks stays active while it is
  // open. If that layer failed to load, land on Today instead of leaving
  // a dead button.
  function openTasksDestination(options) {
    var silent = Boolean(options && options.silent);
    closeMoreMenu(false);
    closeConversationDrawer(false, false);
    explicitNav = true;
    settling = false;
    var agentToday = window.CrumpAgentToday;
    if (!agentToday || typeof agentToday.openTasks !== 'function') {
      fallbackToLegacy('today', options);
      return;
    }
    unmountView();
    currentId = 'tasks';
    setActive('tasks');
    try {
      agentToday.openTasks();
    } catch (_) {
      fallbackToLegacy('today', options);
      return;
    }
    if (!silent) {
      track('tasks');
      dispatchShow('tasks');
    }
  }

  // The legacy conversation library renders as a second sidebar next to the
  // vision rail. While a vision view owns the stage there is exactly one
  // sidebar: hide the legacy one (it is restored when falling back to legacy).
  function setLegacySidebarHidden(hidden) {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    var shell = document.querySelector('.v1-shell');
    if (hidden) {
      sidebar.classList.add('cv-legacy-hidden');
      sidebar.setAttribute('aria-hidden', 'true');
      if (shell) shell.classList.add('cv-vision-mounted');
      syncConversationDrawer();
      return;
    }
    sidebar.classList.remove('cv-legacy-hidden');
    sidebar.removeAttribute('aria-hidden');
    if (shell) shell.classList.remove('cv-vision-mounted');
    syncConversationDrawer();
  }

  function mountView(id, def, options) {
    var silent = Boolean(options && options.silent);
    if (id === currentId && isMounted()) {
      setActive(id);
      return;
    }
    unmountView();
    closeLegacySurfaces();
    if (!ensureStage()) {
      fallbackToLegacy(id);
      return;
    }
    try {
      stageBody.innerHTML = '';
      stageBody.className = 'cv-stage-body';
      def.render(stageBody);
    } catch (_) {
      fallbackToLegacy(id);
      return;
    }
    currentId = id;
    stage.hidden = false;
    setWorkspaceInert(true);
    setLegacySidebarHidden(true);
    setActive(id);
    try {
      if (typeof def.onShow === 'function') def.onShow();
    } catch (_) {}
    try {
      stage.focus({ preventScroll: true });
    } catch (_) {}
    if (!silent) {
      track(id);
      dispatchShow(id);
    }
  }

  function unmountView() {
    if (!isMounted()) return;
    var def = views.get(currentId);
    try {
      if (def && typeof def.onHide === 'function') def.onHide();
    } catch (_) {}
    stage.hidden = true;
    if (stageBody) stageBody.className = 'cv-stage-body';
    setWorkspaceInert(false);
    setLegacySidebarHidden(false);
  }

  function fallbackToLegacy(id, options) {
    var silent = Boolean(options && options.silent);
    unmountView();
    currentId = id;
    setActive(id);
    var oldId = NEW_TO_OLD[id] || 'ask';
    var trackedByLegacyAdapter = false;
    try {
      var legacy = window.CrumpNavigation5930;
      if (legacy && typeof legacy.open === 'function') {
        legacy.open(oldId, silent ? { recordSelection: false, focus: false } : undefined);
        // The adapter owns analytics for delegated legacy destinations. Keep
        // one authoritative selection event for each user action.
        trackedByLegacyAdapter = true;
        if (id === 'you') {
          // "You" should always land on the account identity panel, even
          // when the user last left Settings on Plan or About.
          setTimeout(function () {
            var profileTab = document.querySelector('[data-v1-settings-tab="profile"]');
            if (profileTab) profileTab.click();
          }, 0);
        }
      } else if (oldId === 'ask') {
        var input = document.getElementById('userInput');
        if (input && typeof input.focus === 'function') input.focus({ preventScroll: true });
      }
    } catch (_) {}
    if (!silent && !trackedByLegacyAdapter) track(id);
    if (!silent) dispatchShow(id);
  }

  function isMounted() {
    return Boolean(stage && !stage.hidden);
  }

  function setActive(id) {
    var activeId = ACTIVE_PARENT[id] || id;
    var buttons = document.querySelectorAll('[data-cv-destination]');
    for (var i = 0; i < buttons.length; i++) {
      var target = buttons[i].getAttribute('data-cv-destination');
      var active = target === activeId || (target === 'more' && MORE_DESTINATIONS.indexOf(activeId) !== -1);
      buttons[i].classList.toggle('is-active', active);
      if (active) buttons[i].setAttribute('aria-current', 'page');
      else buttons[i].removeAttribute('aria-current');
    }
  }

  function track(id) {
    try {
      if (window.CrumpAnalytics && typeof window.CrumpAnalytics.track === 'function') {
        window.CrumpAnalytics.track('NavigationDestinationSelected', {
          eventKey: 'navigation-destination-selected',
          source: ANALYTICS_SOURCE[id] || 'ask',
        });
      }
    } catch (_) {}
  }

  function dispatchShow(id) {
    try {
      document.dispatchEvent(new CustomEvent('crumpvision:show', { detail: { id: id } }));
    } catch (_) {}
  }

  /* ------------------------------------------------------------------ */
  /* Legacy surface handling (never edited, only driven)                 */
  /* ------------------------------------------------------------------ */

  function closeLegacySurfaces() {
    try {
      var hub = document.getElementById('crump5930CreateHub');
      if (hub && !hub.hidden) {
        var hubClose = document.getElementById('crump5930CreateClose');
        if (hubClose) hubClose.click();
      }
      var settingsModal = document.getElementById('settingsModal');
      if (settingsModal && settingsModal.style.display && settingsModal.style.display !== 'none') {
        var settingsClose = document.getElementById('closeSettingsBtn');
        if (settingsClose) settingsClose.click();
      }
      var studio = document.getElementById('crump53Studio');
      if (studio && !studio.hidden) {
        var studioClose = document.getElementById('crump53Close');
        if (studioClose) studioClose.click();
      }
      var codeWorkspace = document.getElementById('crumpCodeWorkspace');
      if (codeWorkspace && !codeWorkspace.hidden) {
        if (window.CrumpCodeWorkspace && typeof window.CrumpCodeWorkspace.close === 'function') {
          window.CrumpCodeWorkspace.close();
        }
      }
      var toolClose = document.querySelector('.crump50-sheet .crump50-sheet-close');
      if (toolClose) toolClose.click();
      var sidebar = document.getElementById('sidebar');
      if (sidebar) sidebar.classList.remove('active');
      var overlay = document.getElementById('sidebarOverlay');
      if (overlay) overlay.classList.remove('active');
    } catch (_) {}
  }

  /* ------------------------------------------------------------------ */
  /* Stage                                                               */
  /* ------------------------------------------------------------------ */

  function ensureStage() {
    if (stage) return stage;
    var workspace = document.querySelector('.v1-workspace');
    if (!workspace) return null;
    stage = document.createElement('section');
    stage.id = 'cvStage';
    stage.className = 'cv-stage';
    stage.hidden = true;
    stage.setAttribute('tabindex', '-1');
    stage.setAttribute('aria-label', 'Ask Crump');
    var scroll = document.createElement('div');
    scroll.className = 'cv-stage-scroll';
    stageBody = document.createElement('div');
    stageBody.className = 'cv-stage-body';
    scroll.appendChild(stageBody);
    stage.appendChild(scroll);
    workspace.appendChild(stage);
    return stage;
  }

  function setWorkspaceInert(on) {
    var workspace = document.querySelector('.v1-workspace');
    if (!workspace) return;
    if (on) {
      inertTargets = Array.prototype.slice.call(
        workspace.querySelectorAll('.v1-workspace-header, .v1-workspace-body, .v1-command-dock, #scrollToEndBtn, #filePreview')
      );
      inertTargets.forEach(function (node) {
        node.setAttribute('inert', '');
        node.setAttribute('aria-hidden', 'true');
      });
      return;
    }
    inertTargets.forEach(function (node) {
      if (node.isConnected) {
        node.removeAttribute('inert');
        node.removeAttribute('aria-hidden');
      }
    });
    inertTargets = [];
  }

  /* ------------------------------------------------------------------ */
  /* Rail + mobile nav takeover                                          */
  /* ------------------------------------------------------------------ */

  function destinationButton(id, cls) {
    var beta = id === 'autonomous' ? '<small>Beta</small>' : '';
    // Autonomous is not a destination, but if a secondary surface ever
    // paints its control it stays fail-closed until the authenticated
    // feature probe says the provider is configured. The code loader
    // removes these attributes for both the rail and the mobile More
    // sheet in one availability update.
    var availability = id === 'autonomous'
      ? ' data-crump-code-destination hidden disabled aria-hidden="true"'
      : '';
    var popup = id === 'chat'
      ? ' data-cv-drawer-toggle aria-controls="sidebar" aria-expanded="false"'
      : id === 'more'
        ? ' aria-haspopup="dialog" aria-controls="cvMoreMenu" aria-expanded="false"'
        : '';
    // The agent Today layer marks its own Tasks controls with
    // data-cat-tasks and skips injecting another button when one exists;
    // the shell's Tasks destination carries the same hook so there is
    // exactly one Tasks control and its open state styling is shared.
    var tasksHook = id === 'tasks' ? ' data-cat-tasks="1"' : '';
    return (
      '<button type="button" class="' + cls + '" data-cv-destination="' + id + '"' + availability + tasksHook + ' aria-label="' + esc(LABELS[id]) + '"' + popup + '>' +
      ICONS[id] +
      '<span>' + esc(LABELS[id]) + beta + '</span>' +
      '</button>'
    );
  }

  function railMarkup() {
    var buttons = ORDER.map(function (id) {
      return destinationButton(id, 'cv-destination');
    }).join('');
    return (
      '<div class="cv-rail-inner">' +
      '<button type="button" class="cv-rail-brand" data-cv-destination="today" aria-label="Open Today">' +
        '<span class="cv-rail-brand-mark" aria-hidden="true"><img src="/assets/brand/crump-mark-320.webp" alt="" width="320" height="357"></span>' +
        '<span class="cv-rail-brand-copy"><strong>Ask Crump</strong><small>AI workspace</small></span>' +
      '</button>' +
      '<div class="cv-rail-actions" aria-label="Conversation controls">' +
        '<button type="button" class="cv-rail-new" data-cv-new-conversation>' + ICONS.new + '<span>New conversation</span><kbd>⇧⌘N</kbd></button>' +
      '</div>' +
      '<div class="cv-rail-section-label" aria-hidden="true">Workspace</div>' +
      '<nav class="cv-rail-nav" aria-label="Workspace destinations">' + buttons + '</nav>' +
      '</div>'
    );
  }

  function railHasVision() {
    var rail = document.querySelector('.v1-rail');
    return Boolean(rail && rail.querySelector(':scope > .cv-rail-inner'));
  }

  function compactNavigation() {
    return window.matchMedia('(max-width: 1100px)').matches;
  }

  function conversationDrawerIsOpen() {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar || sidebar.classList.contains('cv-legacy-hidden')) return false;
    return compactNavigation()
      ? sidebar.classList.contains('active')
      : !document.body.classList.contains('v1-library-collapsed');
  }

  function syncConversationDrawer() {
    var expanded = conversationDrawerIsOpen();
    document.body.classList.toggle('cv-conversations-open', expanded);
    Array.prototype.forEach.call(document.querySelectorAll('[data-cv-drawer-toggle]'), function (button) {
      button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      button.classList.toggle('is-open', expanded);
      button.setAttribute('aria-label', expanded ? 'Hide Conversations' : 'Show Conversations');
      button.setAttribute('title', expanded ? 'Hide Conversations' : 'Show Conversations');
    });
    setActive(expanded ? 'chat' : currentId);
  }

  function focusConversationDrawer() {
    window.requestAnimationFrame(function () {
      var target = document.getElementById('newChatBtn') || document.querySelector('#sidebar button, #sidebar [href]');
      if (target && conversationDrawerIsOpen()) target.focus({ preventScroll: true });
    });
  }

  function restoreConversationDrawerFocus() {
    var opener = conversationDrawerOpener;
    conversationDrawerOpener = null;
    if (!opener || !opener.isConnected || opener.disabled) return;
    window.requestAnimationFrame(function () {
      opener.focus({ preventScroll: true });
    });
  }

  function restoreConversationDrawerDestination() {
    var returnId = conversationDrawerReturnId;
    conversationDrawerReturnId = null;
    if (!returnId || returnId === 'today') return;
    navigate(returnId, { silent: true });
  }

  function closeConversationDrawer(restoreFocus, restoreDestination) {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar || !conversationDrawerIsOpen()) {
      syncConversationDrawer();
      if (restoreDestination) restoreConversationDrawerDestination();
      else conversationDrawerReturnId = null;
      if (restoreFocus) restoreConversationDrawerFocus();
      return;
    }
    if (compactNavigation()) {
      sidebar.classList.remove('active');
      document.getElementById('sidebarOverlay')?.classList.remove('active');
      document.getElementById('menuBtn')?.setAttribute('aria-expanded', 'false');
      window.CrumpBodyV1?.syncConversationLibrary?.();
    } else {
      window.CrumpBodyV1?.toggleConversationLibrary?.({ recordSelection: false });
    }
    syncConversationDrawer();
    if (restoreDestination) restoreConversationDrawerDestination();
    else conversationDrawerReturnId = null;
    if (restoreFocus) restoreConversationDrawerFocus();
  }

  function ensureConversationDrawerOpen() {
    if (conversationDrawerIsOpen()) {
      syncConversationDrawer();
      focusConversationDrawer();
      return;
    }
    window.CrumpBodyV1?.toggleConversationLibrary?.({ recordSelection: false });
    syncConversationDrawer();
    focusConversationDrawer();
  }

  function toggleConversationDrawer(opener) {
    conversationDrawerOpener = opener || document.activeElement;
    closeTasksPanel();
    track('chat');
    dispatchShow('chat');
    if (currentId !== 'today' || isMounted()) {
      var returnId = currentId !== 'today' ? currentId : null;
      navigate('today', { silent: true });
      conversationDrawerReturnId = returnId;
      window.requestAnimationFrame(ensureConversationDrawerOpen);
      return;
    }
    if (conversationDrawerIsOpen()) closeConversationDrawer(true, true);
    else ensureConversationDrawerOpen();
  }

  function startNewConversation() {
    closeMoreMenu(false);
    closeConversationDrawer(false, false);
    if (currentId !== 'today' || isMounted()) navigate('today');
    window.requestAnimationFrame(function () {
      document.getElementById('newChatBtn')?.click();
      document.getElementById('userInput')?.focus({ preventScroll: true });
    });
  }

  function wireShellControls(root) {
    var host = root || document;
    Array.prototype.forEach.call(host.querySelectorAll('[data-cv-new-conversation]'), function (button) {
      if (button.dataset.cvShellControlWired === '1') return;
      button.dataset.cvShellControlWired = '1';
      button.addEventListener('click', startNewConversation);
    });
    syncConversationDrawer();
  }

  function wireConversationDrawer() {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    var overlay = document.getElementById('sidebarOverlay');
    var close = document.getElementById('closeSidebarBtn');
    var mobileMenu = document.getElementById('menuBtn');

    if (overlay && overlay.dataset.cvDrawerWired !== '1') {
      overlay.dataset.cvDrawerWired = '1';
      overlay.addEventListener('click', function () {
        closeConversationDrawer(true, true);
      });
    }
    if (close && close.dataset.cvDrawerWired !== '1') {
      close.dataset.cvDrawerWired = '1';
      close.addEventListener('click', function () {
        closeConversationDrawer(true, true);
      });
    }
    if (mobileMenu && mobileMenu.dataset.cvDrawerWired !== '1') {
      mobileMenu.dataset.cvDrawerWired = '1';
      mobileMenu.addEventListener('click', function () {
        conversationDrawerOpener = mobileMenu;
        window.requestAnimationFrame(function () {
          syncConversationDrawer();
          if (conversationDrawerIsOpen()) focusConversationDrawer();
        });
      });
    }
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape' || !conversationDrawerIsOpen()) return;
      event.preventDefault();
      closeConversationDrawer(true, true);
    }, true);
    drawerObserver = new MutationObserver(syncConversationDrawer);
    drawerObserver.observe(sidebar, { attributes: true, attributeFilter: ['class', 'aria-hidden'] });
    drawerObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }

  function ensureMoreMenu(app) {
    if (moreMenu && moreMenu.isConnected) return moreMenu;
    var host = app || document.getElementById('appContainer') || document.body;
    moreMenu = el(
      '<div id="cvMoreMenu" class="cv-more-menu" hidden>' +
        '<button type="button" class="cv-more-backdrop" data-cv-more-close tabindex="-1" aria-label="Close More menu"></button>' +
        '<section class="cv-more-sheet" role="dialog" aria-modal="true" aria-labelledby="cvMoreTitle">' +
          '<div class="cv-more-head"><div><p>Workspace</p><h2 id="cvMoreTitle">More</h2></div>' +
          '<button type="button" class="cv-more-close" data-cv-more-close aria-label="Close More menu">×</button></div>' +
          '<div class="cv-more-list">' +
            MORE_DESTINATIONS.map(function (id) { return destinationButton(id, 'cv-more-item'); }).join('') +
          '</div>' +
        '</section>' +
      '</div>'
    );
    if (!moreMenu) return null;
    host.appendChild(moreMenu);
    wireNav(moreMenu);
    Array.prototype.forEach.call(moreMenu.querySelectorAll('[data-cv-more-close]'), function (button) {
      button.addEventListener('click', function () { closeMoreMenu(true); });
    });
    document.addEventListener('keydown', function (event) {
      if (!moreMenu || moreMenu.hidden) return;
      if (event.key === 'Escape') {
        closeMoreMenu(true);
        return;
      }
      if (event.key !== 'Tab') return;
      var focusable = Array.prototype.slice.call(
        moreMenu.querySelectorAll('.cv-more-sheet button:not([disabled]), .cv-more-sheet [href], .cv-more-sheet [tabindex]:not([tabindex="-1"])')
      ).filter(function (node) { return node.offsetParent !== null; });
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    return moreMenu;
  }

  function openMoreMenu(opener) {
    var menu = ensureMoreMenu();
    if (!menu) return;
    moreMenuOpener = opener || document.querySelector('[data-cv-destination="more"]');
    menu.hidden = false;
    Array.prototype.forEach.call(document.querySelectorAll('[data-cv-destination="more"]'), function (button) {
      button.setAttribute('aria-expanded', 'true');
    });
    document.body.classList.add('cv-more-open');
    var first = menu.querySelector('.cv-more-item');
    if (first) first.focus({ preventScroll: true });
  }

  function closeMoreMenu(restoreFocus) {
    if (!moreMenu || moreMenu.hidden) return;
    moreMenu.hidden = true;
    Array.prototype.forEach.call(document.querySelectorAll('[data-cv-destination="more"]'), function (button) {
      button.setAttribute('aria-expanded', 'false');
    });
    document.body.classList.remove('cv-more-open');
    if (restoreFocus && moreMenuOpener && moreMenuOpener.isConnected) {
      moreMenuOpener.focus({ preventScroll: true });
    }
    moreMenuOpener = null;
  }

  function takeOverRail() {
    var rail = document.querySelector('.v1-rail');
    if (!rail || railHasVision()) return;
    rail.classList.add('cv-rail');
    rail.classList.remove('crump5930-rail');
    rail.innerHTML = railMarkup();
    wireNav(rail);
    wireShellControls(rail);
  }

  function takeOverMobileNav() {
    var app = document.getElementById('appContainer');
    if (!app || document.getElementById('cvMobileNav')) return;
    var nav = el('<nav id="cvMobileNav" class="cv-mobile-nav" aria-label="Ask Crump"></nav>');
    if (!nav) return;
    MOBILE_ORDER.forEach(function (id) {
      var button = el(destinationButton(id, 'cv-mnav-item'));
      if (!button) return;
      if (id === 'you') button.id = 'cvMobileYou';
      nav.appendChild(button);
    });
    app.appendChild(nav);
    wireNav(nav);
  }

  function wireNav(root) {
    var buttons = root.querySelectorAll('[data-cv-destination]');
    for (var i = 0; i < buttons.length; i++) {
      (function (button) {
        if (button.getAttribute('data-cv-wired') === '1') return;
        button.setAttribute('data-cv-wired', '1');
        button.addEventListener('click', function () {
          var id = button.getAttribute('data-cv-destination');
          if (id === 'chat') toggleConversationDrawer(button);
          else if (id === 'more') openMoreMenu(button);
          else navigate(id);
        });
      })(buttons[i]);
    }
  }

  function syncCredits() {
    var balance = '';
    try {
      var host = document.getElementById('upgradeBtnSidebar');
      var node = host ? host.querySelector('.billing51-sidebar-balance') : null;
      balance = node && node.textContent ? node.textContent.trim() : '';
    } catch (_) {}
    var labels = document.querySelectorAll('[data-cv-credits-label]');
    for (var i = 0; i < labels.length; i++) {
      labels[i].textContent = balance || 'Credits';
    }
  }

  /* ------------------------------------------------------------------ */
  /* Observers: mirror the behavior adapter's active destination         */
  /* ------------------------------------------------------------------ */

  function startDatasetSync() {
    var docEl = document.documentElement;
    var observedSheet = null;
    var observedStudio = null;
    var sheetObserver = null;
    var studioObserver = null;
    var insertionObserver = null;

    function tasksPanelIsOpen() {
      var panel = document.getElementById('catTasksPanel');
      return Boolean(panel && !panel.hidden);
    }

    function sync() {
      if (settling) {
        settling = false;
        return;
      }
      if (isMounted()) return;
      // While the Tasks panel is open, Tasks owns the highlight: the
      // adapter reports 'ask' for the workspace underneath the panel, and
      // that must not steal the active state back.
      if (tasksPanelIsOpen()) {
        if (currentId !== 'tasks') {
          currentId = 'tasks';
          setActive('tasks');
        }
        return;
      }
      // The adapter reports its own destination ids; the remap turns them
      // into current destinations (Files, Library, and Video all land on
      // Projects) so the highlight follows the surface the adapter opened.
      var mapped = OLD_TO_NEW[docEl.dataset.crumpNavigationDestination];
      if (mapped && mapped !== currentId) {
        currentId = mapped;
        setActive(mapped);
      }
    }

    // The Tasks panel is inserted lazily by the agent Today layer. Track
    // its open state so closing it returns the highlight to Today, the
    // workspace underneath, mirroring the conversation drawer's restore.
    var observedTasksPanel = null;
    var tasksPanelObserver = null;
    var tasksInsertionObserver = null;
    function bindTasksPanelObserver() {
      var panel = document.getElementById('catTasksPanel');
      if (!panel || panel === observedTasksPanel) return;
      tasksPanelObserver?.disconnect();
      observedTasksPanel = panel;
      tasksPanelObserver = new MutationObserver(function () {
        if (tasksPanelIsOpen()) {
          if (currentId !== 'tasks') {
            currentId = 'tasks';
            setActive('tasks');
          }
          return;
        }
        if (currentId === 'tasks' && !isMounted()) {
          currentId = 'today';
          setActive('today');
        }
      });
      tasksPanelObserver.observe(panel, { attributes: true, attributeFilter: ['hidden'] });
      tasksInsertionObserver?.disconnect();
    }

    function bindProductSurfaceObservers() {
      var productSheet = document.getElementById('crump53Sheet');
      if (productSheet && productSheet !== observedSheet) {
        sheetObserver?.disconnect();
        observedSheet = productSheet;
        sheetObserver = new MutationObserver(sync);
        sheetObserver.observe(productSheet, {
          attributes: true,
          attributeFilter: ['data-project-view', 'data-crump53-section'],
        });
      }
      var productStudio = document.getElementById('crump53Studio');
      if (productStudio && productStudio !== observedStudio) {
        studioObserver?.disconnect();
        observedStudio = productStudio;
        studioObserver = new MutationObserver(sync);
        studioObserver.observe(productStudio, {
          attributes: true,
          attributeFilter: ['hidden'],
        });
      }
      if (observedSheet && observedStudio) insertionObserver?.disconnect();
    }

    var observer = new MutationObserver(sync);
    observer.observe(docEl, { attributes: true, attributeFilter: ['data-crump-navigation-destination'] });
    bindProductSurfaceObservers();
    if (!observedSheet || !observedStudio) {
      insertionObserver = new MutationObserver(function () {
        bindProductSurfaceObservers();
        sync();
      });
      insertionObserver.observe(document.body, {childList: true, subtree: true});
    }
    bindTasksPanelObserver();
    if (!observedTasksPanel) {
      tasksInsertionObserver = new MutationObserver(bindTasksPanelObserver);
      tasksInsertionObserver.observe(document.body, {childList: true, subtree: true});
    }
    document.addEventListener('crump:product-view-changed', function (event) {
      var destination = normalizeId(event?.detail?.destination);
      if (!destination || isMounted()) return;
      currentId = destination;
      setActive(destination);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                                */
  /* ------------------------------------------------------------------ */

  function ensureBoot() {
    if (!booted) boot();
  }

  function boot() {
    if (booted) return;
    booted = true;
    takeOverRail();
    takeOverMobileNav();
    wireConversationDrawer();
    startDatasetSync();
    window.addEventListener('resize', function () {
      if (window.matchMedia('(min-width: 1101px)').matches) closeMoreMenu(false);
      syncConversationDrawer();
    }, { passive: true });
    currentId = 'today';
    setActive('today');
    document.documentElement.dataset.cvShell = 'ready';
    document.dispatchEvent(new CustomEvent('crumpvision:ready'));
    settling = true;
    setTimeout(function () {
      settling = false;
    }, 1500);
  }

  /* ------------------------------------------------------------------ */
  /* Public API (exactly the contract the screen builders share)         */
  /* ------------------------------------------------------------------ */

  var api = {
    registerView: registerView,
    navigate: navigate,
    current: current,
    esc: esc,
    el: el,
    eyebrow: eyebrow,
    card: card,
  };

  // A sibling module may have installed a placeholder before the shell
  // arrived (standalone mode). Keep any namespaces it attached, such as
  // window.CrumpVision.chats, without letting its stubs win.
  var previous = window.CrumpVision;
  if (previous && typeof previous === 'object') {
    Object.keys(previous).forEach(function (key) {
      if (!(key in api)) {
        try {
          api[key] = previous[key];
        } catch (_) {}
      }
    });
  }
  window.CrumpVision = api;
  window.__crumpVisionShellLoaded = true;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
