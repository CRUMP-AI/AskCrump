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
 * The legacy navigation module keeps running underneath (its overlays still
 * drive the product sheets). This shell only replaces the rail markup and
 * mirrors the active destination, so nothing that depends on the old module
 * breaks. Old destination ids continue to resolve to their closest current
 * destination so bookmarked and delegated actions still work.
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
  var SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
  var ICONS = {
    ask: SVG_OPEN + '<path d="M5 5h14v11H9l-4 3z"/><path d="M8 9.5h8M8 12.5h5"/></svg>',
    projects: SVG_OPEN + '<path d="M4 7h6l2 2h8v10H4z"/><path d="M4 7V5h7l2 2"/></svg>',
    files: SVG_OPEN + '<path d="M5 3.5h8l5 5V20H5z"/><path d="M13 3.5v5h5M8 13h7M8 16h5"/></svg>',
    library: SVG_OPEN + '<path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M7 4v16M10 8.5h6"/></svg>',
    video: SVG_OPEN + '<rect x="3.5" y="5" width="13" height="14" rx="2"/><path d="m16.5 10 4-2v8l-4-2zM8 9l5 3-5 3z"/></svg>',
    autonomous: SVG_OPEN + '<path d="m9 7-5 5 5 5M15 7l5 5-5 5M13 4l-2 16"/></svg>',
    profile: SVG_OPEN + '<circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.7-4 2.9-6 6.5-6s5.8 2 6.5 6"/></svg>',
    more: SVG_OPEN + '<circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></svg>',
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

  function mascot(sizePx) {
    var px = Math.max(16, parseInt(sizePx, 10) || 32);
    var img = document.createElement('img');
    img.className = 'cv-mascot';
    img.src = '/assets/brand/crump-mascot.png';
    img.alt = 'Crump';
    img.width = px;
    img.height = px;
    return img;
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
      return;
    }
    sidebar.classList.remove('cv-legacy-hidden');
    sidebar.removeAttribute('aria-hidden');
    if (shell) shell.classList.remove('cv-vision-mounted');
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
    try {
      if (id === 'files') {
        if (window.CrumpProduct53 && typeof window.CrumpProduct53.openFiles === 'function') {
          window.CrumpProduct53.openFiles();
        } else if (window.CrumpProductLoader && typeof window.CrumpProductLoader.openFiles === 'function') {
          window.CrumpProductLoader.openFiles();
        }
        track(id);
        dispatchShow(id);
        return;
      }
      var legacy = window.CrumpNavigation5930;
      if (legacy && typeof legacy.open === 'function') {
        legacy.open(oldId);
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
    track(id);
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
    var popup = id === 'more'
      ? ' aria-haspopup="dialog" aria-controls="cvMoreMenu" aria-expanded="false"'
      : '';
    return (
      '<button type="button" class="' + cls + '" data-cv-destination="' + id + '" aria-label="' + esc(LABELS[id]) + '"' + popup + '>' +
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
      '<img src="/assets/brand/crump-shell-lockup-light.webp" alt="Ask Crump" width="903" height="258"></button>' +
      '<nav class="cv-rail-nav" aria-label="Ask Crump">' + buttons + '</nav>' +
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
  /* Observers: re-assert takeover, mirror legacy active destination     */
  /* ------------------------------------------------------------------ */

  function startGuards() {
    var guard = new MutationObserver(function () {
      if (!railHasVision()) takeOverRail();
      if (!document.getElementById('cvMobileNav')) takeOverMobileNav();
      if (!document.getElementById('cvMoreMenu')) ensureMoreMenu();
    });
    guard.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', function () {
      if (window.matchMedia('(min-width: 1101px)').matches) closeMoreMenu(false);
    }, { passive: true });
  }

  function startDatasetSync() {
    var docEl = document.documentElement;
    function sync() {
      if (settling) {
        settling = false;
        return;
      }
      if (isMounted()) return;
      var productStudio = document.getElementById('crump53Studio');
      var productSheet = document.getElementById('crump53Sheet');
      var filesSurfaceOpen = Boolean(
        productStudio && !productStudio.hidden &&
        productSheet && productSheet.dataset.projectView === 'files'
      );
      var mapped = filesSurfaceOpen ? 'files' : OLD_TO_NEW[docEl.dataset.crumpNavigationDestination];
      if (mapped && mapped !== currentId) {
        currentId = mapped;
        setActive(mapped);
      }
    }
    var observer = new MutationObserver(sync);
    observer.observe(docEl, { attributes: true, attributeFilter: ['data-crump-navigation-destination'] });
    var productSheet = document.getElementById('crump53Sheet');
    if (productSheet) {
      new MutationObserver(sync).observe(productSheet, {
        attributes: true,
        attributeFilter: ['data-project-view', 'hidden'],
      });
    }
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
    startGuards();
    startDatasetSync();
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
    mascot: mascot,
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
