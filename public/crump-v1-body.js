(() => {
  'use strict';

  if (window.__askCrumpV1BodyLoaded) return;
  window.__askCrumpV1BodyLoaded = true;

  const BRAND = Object.freeze({
    mark: '/assets/brand/crump-mark.png',
    horizontalLight: '/assets/brand/crump-horizontal-light.png',
  });

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const byId = id => document.getElementById(id);

  function makeImage(src, className, alt = 'Ask Crump') {
    const img = document.createElement('img');
    img.src = src;
    img.alt = alt;
    img.className = className;
    img.decoding = 'async';
    return img;
  }

  function restoreHeaderBrand() {
    const host = $('.header-branding');
    if (!host) return;
    const existing = host.querySelector(':scope > .v1-body-header-logo');
    if (existing && host.children.length === 1) return;
    host.replaceChildren(makeImage(BRAND.horizontalLight, 'v1-body-header-logo'));
  }

  function restoreLibraryBrand() {
    const host = $('.sidebar-branding');
    if (!host) return;
    const existing = host.querySelector(':scope > .v1-library-logo');
    if (existing && host.children.length === 1) return;
    host.replaceChildren(makeImage(BRAND.horizontalLight, 'v1-library-logo'));
  }

  function restoreBranding() {
    restoreHeaderBrand();
    restoreLibraryBrand();

    $$('.onboarding-logo').forEach(img => {
      if (!(img instanceof HTMLImageElement)) return;
      if (img.getAttribute('src') !== BRAND.horizontalLight) img.src = BRAND.horizontalLight;
    });
  }

  function wireBrandGuards() {
    const header = $('.header-branding');
    if (header && header.dataset.v1BrandObserved !== 'true') {
      header.dataset.v1BrandObserved = 'true';
      new MutationObserver(() => restoreHeaderBrand())
        .observe(header, {childList: true});
    }

    const library = $('.sidebar-branding');
    if (library && library.dataset.v1BrandObserved !== 'true') {
      library.dataset.v1BrandObserved = 'true';
      new MutationObserver(() => restoreLibraryBrand())
        .observe(library, {childList: true});
    }
  }

  function setActiveMode(command) {
    $$('.v1-mode-pill').forEach(button => {
      button.classList.toggle('is-active', button.dataset.v1Command === command);
    });
  }

  function focusComposer(placeholder) {
    const input = byId('userInput');
    if (!input) return;
    if (placeholder) input.placeholder = placeholder;
    input.focus({preventScroll: true});
  }

  function openLibrary() {
    const sidebar = byId('sidebar');
    const overlay = byId('sidebarOverlay');
    if (!sidebar) return;

    if (matchMedia('(max-width: 1100px)').matches) {
      sidebar.classList.add('active');
      overlay?.classList.add('active');
      return;
    }

    document.body.classList.toggle('v1-library-collapsed');
    try {
      localStorage.setItem(
        'crump_v1_library_collapsed',
        document.body.classList.contains('v1-library-collapsed') ? '1' : '0'
      );
    } catch (_) {}
  }

  function forwardClick(id) {
    const target = byId(id);
    if (!target) return false;
    target.click();
    return true;
  }

  function command(command) {
    switch (command) {
      case 'new':
        forwardClick('newChatBtn');
        setActiveMode('focus');
        requestAnimationFrame(() => focusComposer());
        break;
      case 'library':
        openLibrary();
        break;
      case 'settings':
        forwardClick('settingsBtn');
        break;
      case 'billing':
        forwardClick('upgradeBtnSidebar');
        break;
      case 'research':
        setActiveMode('research');
        forwardClick('searchQuickAction');
        requestAnimationFrame(() => focusComposer('What should Crump research?'));
        break;
      case 'image':
        setActiveMode('image');
        forwardClick('imageQuickAction');
        requestAnimationFrame(() => focusComposer('Describe the image you want to create or change…'));
        break;
      case 'file':
        setActiveMode('file');
        forwardClick('attachBtn');
        break;
      case 'code':
        setActiveMode('focus');
        forwardClick('codeQuickAction');
        requestAnimationFrame(() => focusComposer('What are we building or debugging?'));
        break;
      case 'focus':
      default:
        setActiveMode('focus');
        requestAnimationFrame(() => focusComposer('Message Crump'));
        break;
    }
  }

  function wireCommands() {
    $$('[data-v1-command]').forEach(button => {
      if (button.dataset.v1Wired === 'true') return;
      button.dataset.v1Wired = 'true';
      button.addEventListener('click', () => command(button.dataset.v1Command));
    });
  }

  function legacyWelcomeRow() {
    const rows = $$('.message:not(.presence-message)', byId('chatContainer') || document);
    if (rows.length !== 1) return null;
    const row = rows[0];
    if (!row.classList.contains('assistant-message')) return null;
    const text = row.textContent || '';
    const looksLegacy =
      text.includes('your AI assistant') &&
      text.includes('What can I help you with today?');
    return looksLegacy ? row : null;
  }

  function removeLegacyEmptyState(container) {
    if (!container) return;
    $$('.crump-empty-state', container).forEach(node => node.remove());
  }

  function syncLaunchpad() {
    const launchpad = byId('v1Launchpad');
    const container = byId('chatContainer');
    if (!launchpad || !container) return;

    // The V1 launchpad is the sole owner of the authenticated empty/home state.
    // This also protects against one stale 4.3 asset arriving from an older PWA cache.
    removeLegacyEmptyState(container);

    const legacy = legacyWelcomeRow();
    if (legacy) {
      legacy.dataset.v1LegacyWelcome = 'true';
      legacy.hidden = true;
    }

    const meaningful = $$('.message:not(.presence-message)', container)
      .filter(row => row.dataset.v1LegacyWelcome !== 'true');

    const home = meaningful.length === 0;
    launchpad.classList.toggle('is-hidden', !home);
    launchpad.setAttribute('aria-hidden', home ? 'false' : 'true');
    document.body.classList.toggle('v1-home', home);
  }

  function syncWorkspaceTitle() {
    const active = $('.chat-item.active .chat-title');
    const title = byId('v1WorkspaceTitle');
    if (!title) return;
    const value = active?.textContent?.trim() || 'New conversation';
    title.textContent = value;
  }

  function userFirstName() {
    const full =
      window.currentUser?.fullName ||
      window.currentProfile?.profile?.name ||
      '';
    return String(full).trim().split(/\s+/)[0] || '';
  }

  function greetingForNow() {
    const hour = new Date().getHours();
    const part = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    const name = userFirstName();
    return name ? `${part}, ${name}.` : `${part}.`;
  }

  function syncGreeting() {
    const node = byId('v1Greeting');
    if (node) node.textContent = greetingForNow();
  }

  function syncComposerState() {
    const input = byId('userInput');
    const box = input?.closest('.input-container');
    if (!input || !box) return;
    const hasContent = !!input.value.trim();
    box.classList.toggle('has-content', hasContent);
    document.body.classList.toggle('v1-composer-active', hasContent);
  }

  function wireComposer() {
    const input = byId('userInput');
    if (!input || input.dataset.v1BodyWired === 'true') return;
    input.dataset.v1BodyWired = 'true';
    input.addEventListener('input', syncComposerState, {passive: true});
    input.addEventListener('focus', () => document.body.classList.add('v1-composer-focused'));
    input.addEventListener('blur', () => document.body.classList.remove('v1-composer-focused'));
    syncComposerState();
  }

  function showSettingsTab(name) {
    $$('[data-v1-settings-tab]').forEach(button => {
      const active = button.dataset.v1SettingsTab === name;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    $$('[data-v1-settings-panel]').forEach(panel => {
      panel.classList.toggle('is-active', panel.dataset.v1SettingsPanel === name);
    });
  }

  function wireSettingsTabs() {
    $$('[data-v1-settings-tab]').forEach(button => {
      if (button.dataset.v1Wired === 'true') return;
      button.dataset.v1Wired = 'true';
      button.addEventListener('click', () => showSettingsTab(button.dataset.v1SettingsTab));
    });

    const settings = byId('settingsModal');
    if (settings && settings.dataset.v1BodyObserved !== 'true') {
      settings.dataset.v1BodyObserved = 'true';
      new MutationObserver(() => {
        if (settings.style.display && settings.style.display !== 'none') {
          const current = $('[data-v1-settings-tab].is-active')?.dataset.v1SettingsTab || 'profile';
          showSettingsTab(current);
        }
      }).observe(settings, {attributes: true, attributeFilter: ['style']});
    }
  }

  function wireKeyboard() {
    if (document.documentElement.dataset.v1BodyKeys === 'true') return;
    document.documentElement.dataset.v1BodyKeys = 'true';

    document.addEventListener('keydown', event => {
      const modifier = event.metaKey || event.ctrlKey;

      if (modifier && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        focusComposer();
      }

      if (modifier && event.shiftKey && event.key.toLowerCase() === 'n') {
        event.preventDefault();
        command('new');
      }

      if (event.key === 'Escape') {
        const sidebar = byId('sidebar');
        const overlay = byId('sidebarOverlay');
        if (sidebar?.classList.contains('active')) {
          sidebar.classList.remove('active');
          overlay?.classList.remove('active');
        }
      }
    });
  }

  function wireObservers() {
    const chat = byId('chatContainer');
    if (chat && chat.dataset.v1BodyObserved !== 'true') {
      chat.dataset.v1BodyObserved = 'true';
      new MutationObserver(() => syncLaunchpad())
        .observe(chat, {childList: true, subtree: true});
    }

    const chats = byId('chatsList');
    if (chats && chats.dataset.v1BodyObserved !== 'true') {
      chats.dataset.v1BodyObserved = 'true';
      new MutationObserver(() => syncWorkspaceTitle())
        .observe(chats, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
    }

    const app = byId('appContainer');
    if (app && app.dataset.v1BodyObserved !== 'true') {
      app.dataset.v1BodyObserved = 'true';
      new MutationObserver(() => {
        if (app.style.display && app.style.display !== 'none') {
          syncGreeting();
          syncLaunchpad();
          syncWorkspaceTitle();
          requestAnimationFrame(restoreBranding);
        }
      }).observe(app, {attributes: true, attributeFilter: ['style']});
    }
  }

  function restoreDesktopPreference() {
    if (matchMedia('(max-width: 1100px)').matches) return;
    try {
      if (localStorage.getItem('crump_v1_library_collapsed') === '1') {
        document.body.classList.add('v1-library-collapsed');
      }
    } catch (_) {}
  }

  function wireViewport() {
    const media = matchMedia('(max-width: 1100px)');
    if (media.__crumpV1BodyWired) return;
    media.__crumpV1BodyWired = true;

    media.addEventListener?.('change', event => {
      const sidebar = byId('sidebar');
      const overlay = byId('sidebarOverlay');
      if (!event.matches) {
        sidebar?.classList.remove('active');
        overlay?.classList.remove('active');
        restoreDesktopPreference();
      } else {
        document.body.classList.remove('v1-library-collapsed');
      }
    });
  }

  function reassertAfterLegacyShell() {
    restoreBranding();
    syncLaunchpad();
    syncWorkspaceTitle();
    wireComposer();
  }

  function boot() {
    document.body.classList.add('crump-v1-body');
    restoreDesktopPreference();
    wireCommands();
    wireComposer();
    wireSettingsTabs();
    wireKeyboard();
    wireObservers();
    wireViewport();
    restoreBranding();
    wireBrandGuards();
    syncGreeting();
    syncLaunchpad();
    syncWorkspaceTitle();

    // 5.0 performs an immediate and one delayed shell pass.
    // These bounded reassertions reclaim only the brand/context surfaces.
    setTimeout(reassertAfterLegacyShell, 150);
    setTimeout(reassertAfterLegacyShell, 950);

    document.documentElement.dataset.crumpBodyV1 = 'ready';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, {once: true});
  } else {
    boot();
  }

  window.addEventListener('pageshow', reassertAfterLegacyShell);
})();
