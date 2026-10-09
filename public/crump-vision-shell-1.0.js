/*
 * Crump Vision — application shell (1.0)
 *
 * Owns the destination rail (desktop) and bottom nav (mobile), replacing the
 * seven-destination system with six: home, chats, projects, library, studios,
 * you. Screens register through window.CrumpVision.registerView; a
 * destination with no registered vision view falls back to the existing
 * product behavior, so chat, sync, and billing keep working untouched.
 *
 * The legacy navigation module keeps running underneath (its overlays still
 * drive the product sheets). This shell only replaces the rail markup and
 * mirrors the active destination, so nothing that depends on the old module
 * breaks. Old destination ids keep working: ask -> chats,
 * code/create/video -> studios.
 */
(() => {
  'use strict';

  if (window.__crumpVisionShellLoaded) return;

  var OLD_TO_NEW = {
    home: 'home', chats: 'chats', projects: 'projects',
    library: 'library', studios: 'studios', you: 'you',
    ask: 'chats', code: 'studios', create: 'studios', video: 'studios',
  };
  var NEW_TO_OLD = {
    home: 'ask', chats: 'ask', projects: 'projects',
    library: 'library', studios: 'create', you: 'you',
  };
  var ORDER = ['home', 'chats', 'projects', 'library', 'studios', 'you'];
  var LABELS = {
    home: 'Home', chats: 'Chats', projects: 'Projects',
    library: 'Library', studios: 'Studios', you: 'You',
  };
  var SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
  var ICONS = {
    home: SVG_OPEN + '<path d="M4 11.5 12 4l8 7.5"/><path d="M6.5 10.3V20h11v-9.7"/></svg>',
    chats: SVG_OPEN + '<path d="M5 5h14v11H9l-4 3z"/><path d="M8 9.5h8M8 12.5h5"/></svg>',
    projects: SVG_OPEN + '<path d="M4 7h6l2 2h8v10H4z"/><path d="M4 7V5h7l2 2"/></svg>',
    library: SVG_OPEN + '<path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M7 4v16M10 8.5h6"/></svg>',
    studios: SVG_OPEN + '<path d="m12 4 8 4-8 4-8-4z"/><path d="m4 12 8 4 8-4"/><path d="m4 16 8 4 8-4"/></svg>',
    you: SVG_OPEN + '<circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.7-4 2.9-6 6.5-6s5.8 2 6.5 6"/></svg>',
    conversations: SVG_OPEN + '<path d="M5 6h14M5 12h14M5 18h9"/></svg>',
  };

  var ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  var views = new Map();
  var currentId = 'home';
  var booted = false;
  var explicitNav = false;
  var settling = false;
  var stage = null;
  var stageBody = null;
  var inertTargets = [];

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
    img.src = '/assets/crump-mascot-official.jpg';
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
    var key = normalizeId(id);
    if (!key || !def || typeof def.render !== 'function') return false;
    views.set(key, def);
    if (!booted) return true;
    if (!explicitNav && key === 'home' && !isMounted()) mountView('home', def);
    else if (key === currentId && !isMounted()) mountView(key, def);
    return true;
  }

  function navigate(rawId) {
    ensureBoot();
    var id = normalizeId(rawId) || 'home';
    explicitNav = true;
    settling = false;
    var def = views.get(id);
    if (def) {
      mountView(id, def);
      return;
    }
    fallbackToLegacy(id);
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
  }

  function fallbackToLegacy(id) {
    unmountView();
    currentId = id;
    setActive(id);
    var oldId = NEW_TO_OLD[id] || 'ask';
    try {
      var legacy = window.CrumpNavigation5930;
      if (legacy && typeof legacy.open === 'function') {
        legacy.open(oldId);
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
      var active = buttons[i].getAttribute('data-cv-destination') === id;
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
          source: id,
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
    return (
      '<button type="button" class="' + cls + '" data-cv-destination="' + id + '" aria-label="' + esc(LABELS[id]) + '">' +
      ICONS[id] +
      '<span>' + esc(LABELS[id]) + '</span>' +
      '</button>'
    );
  }

  function railMarkup() {
    var buttons = ORDER.map(function (id) {
      return destinationButton(id, 'cv-destination');
    }).join('');
    return (
      '<div class="cv-rail-inner">' +
      '<div class="cv-rail-brand"><img src="/assets/ask-crump-lockup-onblack.png" alt="Ask Crump" width="903" height="258"></div>' +
      '<nav class="cv-rail-nav" aria-label="Ask Crump">' + buttons + '</nav>' +
      '<div class="cv-rail-foot">' +
      '<button type="button" class="cv-rail-utility" data-cv-conversations>' + ICONS.conversations + '<span>Conversations</span></button>' +
      '<button type="button" class="cv-credits" data-cv-credits-open aria-label="Plan and credits"><span class="cv-credits-label" data-cv-credits-label>Credits</span></button>' +
      '<p class="cv-rail-microcopy">Built in Savannah</p>' +
      '</div>' +
      '</div>'
    );
  }

  function railHasVision() {
    var rail = document.querySelector('.v1-rail');
    return Boolean(rail && rail.querySelector(':scope > .cv-rail-inner'));
  }

  function takeOverRail() {
    var rail = document.querySelector('.v1-rail');
    if (!rail || railHasVision()) return;
    rail.classList.add('cv-rail');
    rail.classList.remove('crump5930-rail');
    rail.innerHTML = railMarkup();
    wireNav(rail);
    var conversations = rail.querySelector('[data-cv-conversations]');
    if (conversations) {
      conversations.addEventListener('click', function () {
        try {
          if (window.CrumpBodyV1 && typeof window.CrumpBodyV1.toggleConversationLibrary === 'function') {
            window.CrumpBodyV1.toggleConversationLibrary();
          }
        } catch (_) {}
      });
    }
    var credits = rail.querySelector('[data-cv-credits-open]');
    if (credits) {
      credits.addEventListener('click', function () {
        var btn = document.getElementById('upgradeBtnSidebar');
        if (btn && typeof btn.click === 'function') btn.click();
      });
    }
  }

  function takeOverMobileNav() {
    var app = document.getElementById('appContainer');
    if (!app || document.getElementById('cvMobileNav')) return;
    var nav = el('<nav id="cvMobileNav" class="cv-mobile-nav" aria-label="Ask Crump"></nav>');
    if (!nav) return;
    ORDER.forEach(function (id) {
      nav.appendChild(el(destinationButton(id, 'cv-mnav-item')));
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
          navigate(button.getAttribute('data-cv-destination'));
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
    });
    guard.observe(document.body, { childList: true, subtree: true });
  }

  function startDatasetSync() {
    var docEl = document.documentElement;
    var observer = new MutationObserver(function () {
      if (settling) {
        settling = false;
        return;
      }
      if (isMounted()) return;
      var mapped = OLD_TO_NEW[docEl.dataset.crumpNavigationDestination];
      if (mapped && mapped !== currentId) {
        currentId = mapped;
        setActive(mapped);
      }
    });
    observer.observe(docEl, { attributes: true, attributeFilter: ['data-crump-navigation-destination'] });
  }

  function startCreditsSync() {
    var host = document.getElementById('upgradeBtnSidebar');
    if (!host) return;
    new MutationObserver(syncCredits).observe(host, {
      childList: true,
      subtree: true,
      characterData: true,
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
    startGuards();
    startDatasetSync();
    startCreditsSync();
    currentId = 'home';
    setActive('home');
    syncCredits();
    document.documentElement.dataset.cvShell = 'ready';
    document.dispatchEvent(new CustomEvent('crumpvision:ready'));
    var def = views.get('home');
    if (def) mountView('home', def);
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
