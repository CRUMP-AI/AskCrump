(() => {
  'use strict';

  if (window.__crumpNavigation5930Loaded) return;
  window.__crumpNavigation5930Loaded = true;

  const byId = id => document.getElementById(id);
  const all = selector => [...document.querySelectorAll(selector)];
  const MODE_KEY = 'askcrump.navigation.mode';
  const CREATION_HANDOFF_INTENTS = new Set(['document', 'presentation', 'resume', 'image', 'video', 'projects']);
  let lastFocus = null;
  let destinationBackgroundState = null;
  let destinationFocusOpener = null;
  let activePersistentDestination = null;
  let suppressDestinationFocusRestore = false;
  let destinationFocusFrame = 0;
  let syncFrame = 0;

  const destinations = Object.freeze([
    {
      id: 'home',
      label: 'Home',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 11 8-7 8 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-6h4v6"/></svg>',
    },
    {
      id: 'chats',
      label: 'Chats',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v11H9l-4 3z"/><path d="M8 9h8M8 12h5"/></svg>',
    },
    {
      id: 'projects',
      label: 'Projects',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h6l2 2h8v10H4z"/><path d="M4 7V5h7l2 2"/></svg>',
    },
    {
      id: 'library',
      label: 'Library',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M7 4v16M10 8h6"/></svg>',
    },
    {
      id: 'studios',
      label: 'Studios',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><circle cx="12" cy="12" r="3.2"/><path d="m18.5 5.5 .8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z"/></svg>',
    },
    {
      id: 'you',
      label: 'You',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.7-4 2.9-6 6.5-6s5.8 2 6.5 6"/></svg>',
    },
  ]);

  function legacyModeRequested() {
    try {
      return localStorage.getItem(MODE_KEY) === 'legacy';
    } catch (_) {
      return false;
    }
  }

  function destinationButtons() {
    return all('[data-crump5930-destination]');
  }

  function setActive(destination) {
    const value = destinations.some(item => item.id === destination) ? destination : 'home';
    document.documentElement.dataset.crumpNavigationDestination = value;
    destinationButtons().forEach(button => {
      const active = button.dataset.crump5930Destination === value;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  }

  function buttonMarkup(destination) {
    return `<button type="button" class="crump5930-destination" data-crump5930-destination="${destination.id}" aria-label="${destination.label}">${destination.icon}<span>${destination.label}</span></button>`;
  }

  function conversationLibraryMarkup() {
    return `<button type="button" class="crump5930-rail-toggle" data-crump5930-library-toggle aria-label="Show or hide conversation list" title="Conversations" aria-controls="sidebar" aria-expanded="true"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6h14M5 12h14M5 18h9"/></svg></button>`;
  }

  function injectDesktopNavigation() {
    const rail = document.querySelector('.v1-rail');
    if (!rail) return;
    rail.classList.add('crump5930-rail');
    rail.innerHTML = `
      <div class="crump5930-rail-brand" aria-hidden="true"><img src="/assets/brand/crump-mark-320.webp" width="320" height="357" loading="lazy" decoding="async" alt=""></div>
      <div class="crump5930-rail-destinations">
        ${buttonMarkup(destinations[0])}
        ${conversationLibraryMarkup()}
        ${destinations.slice(1).map(buttonMarkup).join('')}
      </div>`;
  }

  function injectMobileNavigation() {
    const app = byId('appContainer');
    if (!app || byId('crump5930MobileNav')) return;
    const nav = document.createElement('nav');
    nav.id = 'crump5930MobileNav';
    nav.className = 'crump5930-mobile-nav';
    nav.setAttribute('aria-label', 'Ask Crump destinations');
    nav.innerHTML = destinations.map(buttonMarkup).join('');
    app.appendChild(nav);
  }

  function syncPlanSummary() {
    const summary = byId('v1PlanCreditSummary');
    if (!summary) return;
    const balance = byId('upgradeBtnSidebar')?.querySelector('.billing51-sidebar-balance')?.textContent?.trim();
    summary.textContent = balance
      ? `${balance} available · Review plans and purchase history`
      : 'Review plans, credits, and purchase history';
  }

  function consolidateAccountNavigation() {
    const footer = document.querySelector('.v1-library-footer');
    const planButton = byId('v1OpenPlanBtn');
    if (!footer || !planButton) return;

    // Chats owns conversation history only. Projects already has a first-class
    // destination, while settings, legal, and billing now live under You.
    footer.hidden = true;
    footer.setAttribute('aria-hidden', 'true');

    if (planButton.dataset.crump5930Wired !== 'true') {
      planButton.dataset.crump5930Wired = 'true';
      planButton.addEventListener('click', () => byId('upgradeBtnSidebar')?.click());
    }

    if (footer.dataset.crump5930PlanObserved !== 'true') {
      footer.dataset.crump5930PlanObserved = 'true';
      new MutationObserver(syncPlanSummary).observe(footer, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
    syncPlanSummary();
  }

  function closeSidebar() {
    byId('sidebar')?.classList.remove('active');
    byId('sidebarOverlay')?.classList.remove('active');
  }

  function studioIsOpen() {
    const studio = byId('crump53Studio');
    return Boolean(studio && !studio.hidden);
  }

  function closeStudio() {
    if (studioIsOpen()) byId('crump53Close')?.click();
  }

  function settingsIsOpen() {
    const modal = byId('settingsModal');
    return Boolean(modal && modal.style.display && modal.style.display !== 'none');
  }

  function codeWorkspaceIsOpen() {
    const workspace = byId('crumpCodeWorkspace');
    return Boolean(workspace && !workspace.hidden);
  }

  function closeCodeWorkspace() {
    if (codeWorkspaceIsOpen()) window.CrumpCodeWorkspace?.close?.();
  }

  function closeSettings() {
    if (settingsIsOpen()) byId('closeSettingsBtn')?.click();
  }

  function destinationBackgroundElements() {
    return [byId('sidebar'), document.querySelector('.v1-workspace')].filter(Boolean);
  }

  function setDestinationBackgroundInert(inert) {
    if (inert) {
      if (!destinationBackgroundState) {
        destinationBackgroundState = destinationBackgroundElements().map(element => ({
          element,
          inert: element.hasAttribute('inert'),
          ariaHidden: element.getAttribute('aria-hidden'),
        }));
      }
      destinationBackgroundState.forEach(({element}) => {
        element.dataset.crump5930DestinationInert = 'true';
        element.setAttribute('inert', '');
        element.setAttribute('aria-hidden', 'true');
      });
      return;
    }
    if (!destinationBackgroundState) return;
    destinationBackgroundState.forEach(({element, inert: wasInert, ariaHidden}) => {
      delete element.dataset.crump5930DestinationInert;
      if (!wasInert) element.removeAttribute('inert');
      if (ariaHidden === null) element.removeAttribute('aria-hidden');
      else element.setAttribute('aria-hidden', ariaHidden);
    });
    destinationBackgroundState = null;
  }

  function syncDestinationBackground() {
    setDestinationBackgroundInert(
      studioIsOpen() || settingsIsOpen() || codeWorkspaceIsOpen() || studiosHubIsOpen(),
    );
  }

  function persistentDestination() {
    if (codeWorkspaceIsOpen()) return 'code';
    return selectedStudioDestination() || (settingsIsOpen() ? 'you' : null);
  }

  function visibleDestinationButton(destination) {
    return destinationButtons().find(button => {
      if (button.dataset.crump5930Destination !== destination) return false;
      return Boolean(button.offsetWidth || button.offsetHeight || button.getClientRects().length);
    }) || null;
  }

  function rememberDestinationOpener(destination) {
    const active = document.activeElement;
    destinationFocusOpener = active?.dataset?.crump5930Destination === destination
      ? active
      : visibleDestinationButton(destination) || null;
  }

  function destinationSurface(destination) {
    if (destination === 'you') return document.querySelector('#settingsModal [role="dialog"]');
    if (destination === 'code') return document.querySelector('#crumpCodeWorkspace [role="dialog"]');
    return byId('crump53Sheet');
  }

  function destinationFocusTarget(destination) {
    if (destination === 'you') return byId('settingsTitle');
    if (destination === 'code') return byId('crumpCodeTitle');
    return byId('crump53WorkspaceTitle');
  }

  function scheduleDestinationSurfaceFocus(destination) {
    if (destinationFocusFrame) cancelAnimationFrame(destinationFocusFrame);
    destinationFocusFrame = requestAnimationFrame(() => {
      destinationFocusFrame = 0;
      if (persistentDestination() !== destination) return;
      const surface = destinationSurface(destination);
      const target = destinationFocusTarget(destination);
      if (!surface || !target || surface.contains(document.activeElement)) return;
      target.focus({preventScroll: true});
    });
  }

  function restoreDestinationFocus() {
    if (destinationFocusFrame) cancelAnimationFrame(destinationFocusFrame);
    destinationFocusFrame = 0;
    const opener = destinationFocusOpener;
    destinationFocusOpener = null;
    requestAnimationFrame(() => {
      if (persistentDestination()) return;
      const target = opener?.isConnected && !opener.disabled
        ? opener
        : visibleDestinationButton('chats');
      target?.focus?.({preventScroll: true});
    });
  }

  function syncDestinationFocus() {
    const current = persistentDestination();
    const previous = activePersistentDestination;
    if (current) {
      if (current !== previous) {
        const active = document.activeElement;
        if (active?.dataset?.crump5930Destination === current) destinationFocusOpener = active;
        else if (previous || !destinationFocusOpener) {
          destinationFocusOpener = visibleDestinationButton(current) || destinationFocusOpener;
        }
        activePersistentDestination = current;
        suppressDestinationFocusRestore = false;
        scheduleDestinationSurfaceFocus(current);
      }
      return;
    }
    if (previous) {
      activePersistentDestination = null;
      if (suppressDestinationFocusRestore) {
        suppressDestinationFocusRestore = false;
        destinationFocusOpener = null;
        return;
      }
      restoreDestinationFocus();
      return;
    }
    if (suppressDestinationFocusRestore) {
      suppressDestinationFocusRestore = false;
      destinationFocusOpener = null;
    }
  }

  function suppressPersistentDestinationRestore() {
    if (persistentDestination() || activePersistentDestination) suppressDestinationFocusRestore = true;
  }

  function closeToolSheet() {
    document.querySelector('.crump50-sheet .crump50-sheet-close')?.click();
  }

  function studiosHubIsOpen() {
    const hub = byId('crump5930StudiosHub');
    return Boolean(hub && !hub.hidden);
  }

  function closeStudiosHub({restoreFocus = false} = {}) {
    const hub = byId('crump5930StudiosHub');
    if (!hub || hub.hidden) return;
    hub.hidden = true;
    document.body.classList.remove('crump5930-studios-open');
    setDestinationBackgroundInert(false);
    if (restoreFocus) lastFocus?.focus?.({preventScroll: true});
    lastFocus = null;
    scheduleSurfaceSync();
  }

  function studioCard(action, eyebrow, title, detail, icon) {
    return `<button type="button" class="crump5930-studios-card" data-crump5930-studio="${action}"><span class="crump5930-studios-icon">${icon}</span><span><small>${eyebrow}</small><strong>${title}</strong><b>${detail}</b></span><i aria-hidden="true">↗</i></button>`;
  }

  function injectStudiosHub() {
    if (byId('crump5930StudiosHub')) return;
    const overlay = document.createElement('div');
    overlay.id = 'crump5930StudiosHub';
    overlay.className = 'crump5930-studios-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="crump5930-studios-sheet" role="dialog" aria-modal="false" aria-labelledby="crump5930StudiosTitle">
        <header class="crump5930-studios-head">
          <div><span>STUDIOS</span><h2 id="crump5930StudiosTitle">What shall we make?</h2><p>Pick a studio and I'll set everything up. Your work stays connected to your account.</p></div>
          <button type="button" id="crump5930StudiosClose" aria-label="Close Studios">×</button>
        </header>
        <div class="crump5930-studios-grid">
          ${studioCard('document', 'WRITING', 'Documents', 'Reports, résumés, PDFs, spreadsheets, and more.', '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5M10 12h5M10 16h5"/></svg>')}
          ${studioCard('presentation', 'STORYTELLING', 'Presentations', 'Editable PowerPoint built around a clear narrative.', '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="12" rx="2"/><path d="M8 21h8M12 17v4M8 13l3-3 2 2 3-4"/></svg>')}
          ${studioCard('image', 'VISUALS', 'Images', 'Generate, edit, or build from a reference.', '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="m7 16 4-4 3 3 2-2 2 3"/><circle cx="9" cy="9" r="1.5"/></svg>')}
          ${studioCard('manuscript', 'LONG-FORM', 'Manuscripts', 'Plan, draft, pause, and continue chapter by chapter.', '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h6a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H5z"/><path d="M19 4h-3a2 2 0 0 0-2 2v14a3 3 0 0 1 3-3h2z"/></svg>')}
          ${studioCard('video', 'MOTION', 'Video', 'Create a scene or continue a compatible clip.', '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="13" height="14" rx="2"/><path d="m16.5 10 4-2v8l-4-2zM8 9l5 3-5 3z"/></svg>')}
          ${studioCard('code', 'BUILD', 'Code Studio', 'Write, run, and refine code with Crump pairing alongside.', '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 7-5 5 5 5M15 7l5 5-5 5M13 4l-2 16"/></svg>')}
        </div>
        <footer><span>Nothing generates until you review the setup and send your request.</span></footer>
      </section>`;
    document.body.appendChild(overlay);

    byId('crump5930StudiosClose')?.addEventListener('click', () => closeStudiosHub({restoreFocus: true}));
    overlay.addEventListener('click', event => {
      if (event.target === overlay) closeStudiosHub({restoreFocus: true});
    });
    overlay.querySelectorAll('[data-crump5930-studio]').forEach(button => {
      button.addEventListener('click', () => openStudioTool(button.dataset.crump5930Studio));
    });
  }

  function openStudios() {
    closeSidebar();
    suppressPersistentDestinationRestore();
    closeStudio();
    closeSettings();
    closeCodeWorkspace();
    setDestinationBackgroundInert(false);
    syncDestinationFocus();
    closeToolSheet();
    injectStudiosHub();
    const hub = byId('crump5930StudiosHub');
    if (!hub) return;
    lastFocus = document.activeElement;
    hub.hidden = false;
    document.body.classList.add('crump5930-studios-open');
    setDestinationBackgroundInert(true);
    setActive('studios');
    recordDestinationSelection('studios');
    void (window.CrumpCodeWorkspace?.refreshAvailability?.() || window.CrumpCodeLoader?.refreshAvailability?.());
    requestAnimationFrame(() => byId('crump5930StudiosClose')?.focus({preventScroll: true}));
  }

  function openStudioTool(action) {
    closeStudiosHub();
    if (action === 'projects') {
      openProjects();
      return true;
    }
    setActive('studios');
    if (action === 'document') {
      window.CrumpDocumentStudio?.open?.();
      return true;
    }
    if (action === 'presentation') {
      window.CrumpDocumentStudio?.select?.('pptx', 'Describe the presentation, audience, objective, key evidence, and desired next step…');
      return true;
    }
    if (action === 'resume') {
      window.CrumpDocumentStudio?.select?.('docx', 'Describe your real experience, target role, education, skills, and the job requirements you want to match…', 'resume');
      return true;
    }
    if (action === 'image') {
      if (typeof window.CrumpImageStudio?.open !== 'function') return false;
      window.CrumpImageStudio.open();
      return true;
    }
    if (action === 'video') {
      openVideo();
      return true;
    }
    if (action === 'manuscript') {
      rememberDestinationOpener('studios');
      window.CrumpProduct53?.open?.('manuscripts');
      syncDestinationBackground();
      syncDestinationFocus();
      return true;
    }
    if (action === 'code') {
      void openCodeStudio();
      return true;
    }
    return false;
  }

  function continueCreationIntent(detail = {}) {
    const kind = String(detail.kind || '').trim().toLowerCase();
    if (!CREATION_HANDOFF_INTENTS.has(kind) || !openStudioTool(kind)) return false;
    const capturedAt = Number(detail.capturedAt || 0);
    window.va?.('event', {
      name: 'CreationIntentContinued',
      data: {
        intent: kind,
        acquisition: String(detail.acquisition || 'direct').slice(0, 32),
        source: String(detail.source || 'unknown').slice(0, 32),
      },
    });
    window.dispatchEvent(new CustomEvent('crump:creation-intent-consumed', {
      detail: {kind, capturedAt},
    }));
    return true;
  }

  function openHome() {
    closeSidebar();
    suppressPersistentDestinationRestore();
    closeStudio();
    closeSettings();
    closeCodeWorkspace();
    setDestinationBackgroundInert(false);
    syncDestinationFocus();
    closeStudiosHub();
    closeToolSheet();
    setActive('home');
    recordDestinationSelection('home');
    window.CrumpBodyV1?.showLaunchpad?.();
  }

  function openChats() {
    closeSidebar();
    suppressPersistentDestinationRestore();
    closeStudio();
    closeSettings();
    closeCodeWorkspace();
    setDestinationBackgroundInert(false);
    syncDestinationFocus();
    closeStudiosHub();
    closeToolSheet();
    setActive('chats');
    recordDestinationSelection('chats');
    window.CrumpBodyV1?.hideLaunchpad?.();
    requestAnimationFrame(() => byId('userInput')?.focus({preventScroll: true}));
  }

  function openProjects() {
    rememberDestinationOpener('projects');
    closeSidebar();
    closeSettings();
    closeCodeWorkspace();
    closeStudiosHub();
    closeToolSheet();
    window.CrumpProduct53?.open?.('projects');
    syncDestinationBackground();
    setActive('projects');
    recordDestinationSelection('projects');
    syncDestinationFocus();
  }

  function openLibrary() {
    rememberDestinationOpener('library');
    closeSidebar();
    closeSettings();
    closeCodeWorkspace();
    closeStudiosHub();
    closeToolSheet();
    window.CrumpProduct53?.open?.('library');
    syncDestinationBackground();
    setActive('library');
    recordDestinationSelection('library');
    syncDestinationFocus();
  }

  function openVideo() {
    rememberDestinationOpener('studios');
    closeSidebar();
    closeSettings();
    closeCodeWorkspace();
    closeStudiosHub();
    closeToolSheet();
    window.CrumpProduct53?.open?.('video');
    syncDestinationBackground();
    setActive('studios');
    recordDestinationSelection('studios-video');
    syncDestinationFocus();
  }

  function openYou() {
    rememberDestinationOpener('you');
    closeSidebar();
    closeStudio();
    closeCodeWorkspace();
    closeStudiosHub();
    closeToolSheet();
    if (typeof window.openSettings === 'function') window.openSettings();
    else byId('settingsBtn')?.click();
    syncDestinationBackground();
    setActive('you');
    recordDestinationSelection('you');
    syncDestinationFocus();
  }

  async function openCodeStudio() {
    rememberDestinationOpener('studios');
    closeSidebar();
    closeStudio();
    closeSettings();
    closeStudiosHub();
    closeToolSheet();
    const opened = window.CrumpCodeWorkspace?.open
      ? await window.CrumpCodeWorkspace.open()
      : await window.CrumpCodeLoader?.open?.();
    if (!opened) {
      setActive('studios');
      return;
    }
    syncDestinationBackground();
    setActive('studios');
    recordDestinationSelection('studios-code');
    syncDestinationFocus();
  }

  function recordDestinationSelection(destination) {
    void window.CrumpAnalytics?.track?.('NavigationDestinationSelected', {
      eventKey: 'navigation-destination-selected',
      source: destination,
    });
  }

  function openDestination(destination) {
    if (destination === 'home') openHome();
    else if (destination === 'chats') openChats();
    else if (destination === 'projects') openProjects();
    else if (destination === 'library') openLibrary();
    else if (destination === 'studios') openStudios();
    else if (destination === 'you') openYou();
    else openHome();
  }

  function wireDestinations() {
    destinationButtons().forEach(button => {
      if (button.dataset.crump5930Wired === 'true') return;
      button.dataset.crump5930Wired = 'true';
      button.addEventListener('click', () => openDestination(button.dataset.crump5930Destination));
    });

    const chats = document.querySelector('[data-crump5930-library-toggle]');
    if (chats && chats.dataset.crump5930Wired !== 'true') {
      chats.dataset.crump5930Wired = 'true';
      chats.addEventListener('click', () => window.CrumpBodyV1?.toggleConversationLibrary?.());
    }
  }

  function selectedStudioDestination() {
    if (!studioIsOpen()) return null;
    const section = byId('crump53Sheet')?.dataset.crump53Section;
    if (section === 'library') return 'library';
    if (section === 'projects') return 'projects';
    if (section === 'video' || section === 'manuscripts') return 'studios';
    return null;
  }

  function syncFromSurfaces() {
    syncFrame = 0;
    syncDestinationBackground();
    syncDestinationFocus();
    if (codeWorkspaceIsOpen()) return setActive('studios');
    if (studiosHubIsOpen()) return setActive('studios');
    const studioDestination = selectedStudioDestination();
    if (studioDestination) return setActive(studioDestination);
    if (settingsIsOpen()) return setActive('you');
    if (document.querySelector('.crump50-options-sheet')) return setActive('studios');
    if (window.CrumpBodyV1?.isLaunchpadVisible?.()) return setActive('home');
    setActive('chats');
  }

  function scheduleSurfaceSync() {
    if (syncFrame) return;
    syncFrame = requestAnimationFrame(syncFromSurfaces);
  }

  function wireSurfaceSync() {
    if (document.documentElement.dataset.crump5930Observed === 'true') return;
    document.documentElement.dataset.crump5930Observed = 'true';
    new MutationObserver(scheduleSurfaceSync).observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'style', 'class'],
    });
    document.addEventListener('click', event => {
      if (event.target.closest?.('.chat-item, #newChatBtn, [data-v1-command="focus"], [data-v1-command="research"]')) {
        requestAnimationFrame(() => setActive('chats'));
      }
    }, true);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && studiosHubIsOpen()) {
        event.preventDefault();
        closeStudiosHub({restoreFocus: true});
        return;
      }
    });
  }

  function boot() {
    if (legacyModeRequested()) {
      document.documentElement.dataset.crumpNavigation5930 = 'legacy';
      return;
    }
    injectDesktopNavigation();
    injectMobileNavigation();
    injectStudiosHub();
    consolidateAccountNavigation();
    wireDestinations();
    window.CrumpBodyV1?.syncConversationLibrary?.();
    wireSurfaceSync();
    document.documentElement.dataset.crumpNavigation5930 = 'ready';
    syncFromSurfaces();
  }

  window.CrumpNavigation5930 = Object.freeze({
    open: openDestination,
    continueCreation: continueCreationIntent,
    modeKey: MODE_KEY,
  });

  window.addEventListener('crump:creation-intent', event => {
    continueCreationIntent(event.detail);
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
