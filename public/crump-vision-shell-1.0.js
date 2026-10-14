/*
 * Crump Vision — application shell (1.0)
 *
 * Owns the calm, product-first destination rail (desktop) and five-item
 * bottom nav (mobile). Ask is the workspace; Projects preserves durable
 * context; Files, Library, Video, Autonomous, and Profile delegate to the
 * existing production surfaces. Screens register through
 * window.CrumpVision.registerView; a
 * destination with no registered vision view falls back to the existing
 * product behavior, so chat, sync, and billing keep working untouched.
 *
 * This is the sole visual owner of navigation. The legacy navigation module
 * remains a behavior adapter for the proven product sheets, focus management,
 * analytics, and creation handoffs; it no longer paints a second rail. Old
 * destination ids continue to resolve to their closest current destination so
 * bookmarked and delegated actions keep working.
 */
(() => {
  'use strict';

  if (window.__crumpVisionShellLoaded) return;

  var OLD_TO_NEW = {
    ask: 'ask', chats: 'ask', home: 'ask',
    projects: 'projects', files: 'files', library: 'library',
    video: 'video', code: 'autonomous', autonomous: 'autonomous',
    create: 'ask', studios: 'video', you: 'profile', profile: 'profile',
    more: 'more',
  };
  var NEW_TO_OLD = {
    ask: 'ask', projects: 'projects', library: 'library',
    video: 'video', autonomous: 'code', profile: 'you',
  };
  var ORDER = ['ask', 'projects', 'files', 'library', 'video', 'autonomous'];
  var MOBILE_ORDER = ['ask', 'projects', 'library', 'video', 'more'];
  var MORE_DESTINATIONS = ['files', 'autonomous', 'profile'];
  var ANALYTICS_SOURCE = {
    ask: 'ask', projects: 'projects', files: 'projects', library: 'library',
    video: 'video', autonomous: 'code', profile: 'you',
  };
  var LABELS = {
    ask: 'Ask', projects: 'Projects', files: 'Files', library: 'Library',
    video: 'Video', autonomous: 'Autonomous', profile: 'Profile & settings',
    more: 'More',
  };
  var SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
  var ICONS = {
    ask: SVG_OPEN + '<path d="M6.15 5.4h11.7a2.35 2.35 0 0 1 2.35 2.35v6.4a2.35 2.35 0 0 1-2.35 2.35h-6.2l-4.85 3.1.8-3.1H6.15a2.35 2.35 0 0 1-2.35-2.35v-6.4A2.35 2.35 0 0 1 6.15 5.4Z"/><path d="m15.8 7.8.42 1.03 1.03.42-1.03.42-.42 1.03-.42-1.03-1.03-.42 1.03-.42.42-1.03Z"/></svg>',
    projects: SVG_OPEN + '<path d="M5.25 7.1h5.15l1.7 1.75h6.65a1.9 1.9 0 0 1 1.9 1.9v6.05a2.2 2.2 0 0 1-2.2 2.2H5.55a2.2 2.2 0 0 1-2.2-2.2V9a1.9 1.9 0 0 1 1.9-1.9Z"/><path d="M5.15 7.1V5.3h5.7l1.65 1.8"/></svg>',
    files: SVG_OPEN + '<path d="M7.15 4.1h6.25l3.45 3.45v9.9a2.05 2.05 0 0 1-2.05 2.05H7.15a2.05 2.05 0 0 1-2.05-2.05V6.15A2.05 2.05 0 0 1 7.15 4.1Z"/><path d="M13.2 4.25v3.7h3.55M8.35 12h5.45M8.35 15.2h4"/></svg>',
    library: SVG_OPEN + '<path d="M4.25 5.15h5.1A2.65 2.65 0 0 1 12 7.8v11.05a3.45 3.45 0 0 0-3.45-2.65h-4.3V5.15Z"/><path d="M19.75 5.15h-5.1A2.65 2.65 0 0 0 12 7.8v11.05a3.45 3.45 0 0 1 3.45-2.65h4.3V5.15Z"/></svg>',
    video: SVG_OPEN + '<rect x="3.8" y="5.25" width="16.4" height="13.5" rx="2.4"/><path d="m10.25 9.15 5 2.85-5 2.85v-5.7Z"/></svg>',
    autonomous: SVG_OPEN + '<path d="M7.1 5.1h9.8l3 5.35-3 5.35H7.1l-3-5.35 3-5.35Z"/><path d="m9.4 8.2-2.25 2.25 2.25 2.25M14.6 8.2l2.25 2.25-2.25 2.25M13.05 7.45l-2.1 6"/></svg>',
    profile: SVG_OPEN + '<circle cx="12" cy="8.1" r="3.35"/><path d="M5.6 19.2c.75-3.7 2.9-5.55 6.4-5.55s5.65 1.85 6.4 5.55"/></svg>',
    more: SVG_OPEN + '<circle cx="5.25" cy="12" r="1.05" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.05" fill="currentColor" stroke="none"/><circle cx="18.75" cy="12" r="1.05" fill="currentColor" stroke="none"/></svg>',
    new: SVG_OPEN + '<path d="M12 4.2v15.6M4.2 12h15.6"/><path d="m18.2 4 .35.85.85.35-.85.35-.35.85-.35-.85-.85-.35.85-.35.35-.85Z"/></svg>',
    conversations: SVG_OPEN + '<path d="M6.1 5.15h11.8a2.35 2.35 0 0 1 2.35 2.35v6.2a2.35 2.35 0 0 1-2.35 2.35h-6.25l-4.9 3.1.82-3.1H6.1a2.35 2.35 0 0 1-2.35-2.35V7.5A2.35 2.35 0 0 1 6.1 5.15Z"/><path d="M8 9.25h8M8 12.25h5.35"/></svg>',
  };

  var ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  var views = new Map();
  var currentId = 'ask';
  var booted = false;
  var explicitNav = false;
  var settling = false;
  var stage = null;
  var stageBody = null;
  var inertTargets = [];
  var moreMenu = null;
  var moreMenuOpener = null;
  var conversationDrawerOpener = null;
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
    // Home, Studios, and You were presentation-only experiments. Keeping
    // them out of the registry prevents local-only controls from replacing
    // the real Ask, Video, and account surfaces.
    if (sourceKey === 'home' || sourceKey === 'studios' || sourceKey === 'you') return false;
    var key = normalizeId(sourceKey);
    if (!key || !def || typeof def.render !== 'function') return false;
    views.set(key, def);
    if (booted && key === currentId && !isMounted()) mountView(key, def);
    return true;
  }

  function navigate(rawId) {
    ensureBoot();
    var id = normalizeId(rawId) || 'ask';
    if (id === 'more') {
      openMoreMenu();
      return;
    }
    closeMoreMenu(false);
    explicitNav = true;
    settling = false;
    var def = views.get(id);
    if (def) {
      mountView(id, def);
      return;
    }
    fallbackToLegacy(id);
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

  function mountView(id, def) {
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
    track(id);
    dispatchShow(id);
  }

  function unmountView() {
    if (!isMounted()) return;
    var def = views.get(currentId);
    try {
      if (def && typeof def.onHide === 'function') def.onHide();
    } catch (_) {}
    stage.hidden = true;
    setWorkspaceInert(false);
    setLegacySidebarHidden(false);
  }

  function fallbackToLegacy(id) {
    unmountView();
    currentId = id;
    setActive(id);
    var oldId = NEW_TO_OLD[id] || 'ask';
    var trackedByLegacyAdapter = false;
    try {
      if (id === 'files') {
        if (window.CrumpProduct53 && typeof window.CrumpProduct53.openFiles === 'function') {
          window.CrumpProduct53.openFiles();
        } else if (window.CrumpProductLoader && typeof window.CrumpProductLoader.openFiles === 'function') {
          window.CrumpProductLoader.openFiles();
        } else {
          window.showToast?.('Files are still loading. Try again in a moment.', 'info');
          currentId = 'ask';
          setActive('ask');
          return;
        }
        track(id);
        dispatchShow(id);
        return;
      }
      var legacy = window.CrumpNavigation5930;
      if (legacy && typeof legacy.open === 'function') {
        legacy.open(oldId);
        // The adapter owns analytics for delegated legacy destinations. Keep
        // one authoritative selection event for each user action.
        trackedByLegacyAdapter = true;
        if (id === 'profile') {
          // "Profile" should always land on the account identity panel, even
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
    if (!trackedByLegacyAdapter) track(id);
    dispatchShow(id);
  }

  function isMounted() {
    return Boolean(stage && !stage.hidden);
  }

  function setActive(id) {
    var buttons = document.querySelectorAll('[data-cv-destination]');
    for (var i = 0; i < buttons.length; i++) {
      var target = buttons[i].getAttribute('data-cv-destination');
      var active = target === id || (target === 'more' && MORE_DESTINATIONS.indexOf(id) !== -1);
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
    // Autonomous is fail-closed until the authenticated feature probe says
    // the provider is configured. The loader removes these attributes for
    // both the rail and the mobile More sheet in one availability update.
    var availability = id === 'autonomous'
      ? ' data-crump-code-destination hidden disabled aria-hidden="true"'
      : '';
    var popup = id === 'more'
      ? ' aria-haspopup="dialog" aria-controls="cvMoreMenu" aria-expanded="false"'
      : '';
    return (
      '<button type="button" class="' + cls + '" data-cv-destination="' + id + '"' + availability + ' aria-label="' + esc(LABELS[id]) + '"' + popup + '>' +
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
      '<button type="button" class="cv-rail-brand" data-cv-destination="ask" aria-label="Open Ask Crump">' +
        '<span class="cv-rail-brand-mark" aria-hidden="true"><img src="/assets/brand/crump-mark-320.webp" alt="" width="320" height="357"></span>' +
        '<span class="cv-rail-brand-copy"><strong>Ask Crump</strong><small>AI workspace</small></span>' +
      '</button>' +
      '<div class="cv-rail-actions" aria-label="Conversation controls">' +
        '<button type="button" class="cv-rail-new" data-cv-new-conversation>' + ICONS.new + '<span>New conversation</span></button>' +
        '<button type="button" class="cv-rail-conversations" data-cv-drawer-toggle aria-controls="sidebar" aria-expanded="false">' +
          ICONS.conversations + '<span>Conversations</span>' +
        '</button>' +
      '</div>' +
      '<div class="cv-rail-section-label" aria-hidden="true">Workspace</div>' +
      '<nav class="cv-rail-nav" aria-label="Workspace destinations">' + buttons + '</nav>' +
      '<div class="cv-rail-foot">' +
      '<button type="button" class="cv-rail-utility cv-profile-link" data-cv-destination="profile">' +
      ICONS.profile + '<span><b>Profile</b><small>Settings & plan</small></span></button>' +
      '</div>' +
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

  function closeConversationDrawer(restoreFocus) {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar || !conversationDrawerIsOpen()) {
      syncConversationDrawer();
      if (restoreFocus) restoreConversationDrawerFocus();
      return;
    }
    if (compactNavigation()) {
      sidebar.classList.remove('active');
      document.getElementById('sidebarOverlay')?.classList.remove('active');
      document.getElementById('menuBtn')?.setAttribute('aria-expanded', 'false');
      window.CrumpBodyV1?.syncConversationLibrary?.();
    } else {
      window.CrumpBodyV1?.toggleConversationLibrary?.();
    }
    syncConversationDrawer();
    if (restoreFocus) restoreConversationDrawerFocus();
  }

  function ensureConversationDrawerOpen() {
    if (conversationDrawerIsOpen()) {
      syncConversationDrawer();
      focusConversationDrawer();
      return;
    }
    window.CrumpBodyV1?.toggleConversationLibrary?.();
    syncConversationDrawer();
    focusConversationDrawer();
  }

  function toggleConversationDrawer(opener) {
    conversationDrawerOpener = opener || document.activeElement;
    if (currentId !== 'ask' || isMounted()) {
      navigate('ask');
      window.requestAnimationFrame(ensureConversationDrawerOpen);
      return;
    }
    if (conversationDrawerIsOpen()) closeConversationDrawer(true);
    else ensureConversationDrawerOpen();
  }

  function startNewConversation() {
    closeMoreMenu(false);
    if (currentId !== 'ask' || isMounted()) navigate('ask');
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
    Array.prototype.forEach.call(host.querySelectorAll('[data-cv-drawer-toggle]'), function (button) {
      if (button.dataset.cvShellControlWired === '1') return;
      button.dataset.cvShellControlWired = '1';
      button.addEventListener('click', function () { toggleConversationDrawer(button); });
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
        closeConversationDrawer(true);
      });
    }
    if (close && close.dataset.cvDrawerWired !== '1') {
      close.dataset.cvDrawerWired = '1';
      close.addEventListener('click', function () {
        closeConversationDrawer(true);
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
      closeConversationDrawer(true);
    });
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
      nav.appendChild(el(destinationButton(id, 'cv-mnav-item')));
    });
    app.appendChild(nav);
    wireNav(nav);
    ensureMoreMenu(app);
  }

  function wireNav(root) {
    var buttons = root.querySelectorAll('[data-cv-destination]');
    for (var i = 0; i < buttons.length; i++) {
      (function (button) {
        if (button.getAttribute('data-cv-wired') === '1') return;
        button.setAttribute('data-cv-wired', '1');
        button.addEventListener('click', function () {
          var id = button.getAttribute('data-cv-destination');
          if (id === 'more') openMoreMenu(button);
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

    function filesNavigationIsPending() {
      return Boolean(document.querySelector('[data-cv-destination="files"][aria-busy="true"]'));
    }

    function filesSurfaceIsOpen() {
      var productStudio = document.getElementById('crump53Studio');
      var productSheet = document.getElementById('crump53Sheet');
      return Boolean(
        productStudio && !productStudio.hidden &&
        productSheet && productSheet.dataset.projectView === 'files'
      );
    }

    function sync() {
      if (settling) {
        settling = false;
        return;
      }
      if (isMounted()) return;
      // A cold Files navigation inserts the product sheet lazily. Preserve the
      // requested destination while those assets are busy, then use the sheet's
      // own view marker as the authoritative state. This prevents the legacy
      // Projects adapter from briefly or permanently taking the highlight back.
      var filesOwnSurface = filesSurfaceIsOpen()
        || (currentId === 'files' && filesNavigationIsPending());
      var mapped = filesOwnSurface ? 'files' : OLD_TO_NEW[docEl.dataset.crumpNavigationDestination];
      if (mapped && mapped !== currentId) {
        currentId = mapped;
        setActive(mapped);
      }
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
    currentId = 'ask';
    setActive('ask');
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
