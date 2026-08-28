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

  function syncLibraryControl() {
    const sidebar = byId('sidebar');
    if (!sidebar) return;
    const controls = [
      $('[data-v1-command="library"]', $('.v1-rail') || document),
      $('[data-crump5930-library-toggle]'),
      byId('menuBtn'),
    ].filter(Boolean);
    const compact = matchMedia('(max-width: 1100px)').matches;
    const expanded = compact
      ? sidebar.classList.contains('active')
      : !document.body.classList.contains('v1-library-collapsed');
    controls.forEach(control => {
      control.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      control.classList.toggle('is-active', expanded);
    });
    sidebar.setAttribute('aria-hidden', expanded ? 'false' : 'true');

    // Remove the interaction guard immediately when opening. When closing,
    // defer it until the triggering click has finished so iOS cannot redirect
    // that same tap to the overlay before the requested action runs.
    const revision = Number(sidebar.dataset.v1InertRevision || 0) + 1;
    sidebar.dataset.v1InertRevision = String(revision);
    if (expanded) {
      sidebar.removeAttribute('inert');
      return;
    }
    window.setTimeout(() => {
      if (Number(sidebar.dataset.v1InertRevision || 0) !== revision) return;
      if (matchMedia('(max-width: 1100px)').matches && sidebar.classList.contains('active')) return;
      sidebar.setAttribute('inert', '');
    }, 0);
  }

  function openLibrary() {
    const sidebar = byId('sidebar');
    const overlay = byId('sidebarOverlay');
    if (!sidebar) return;

    if (matchMedia('(max-width: 1100px)').matches) {
      sidebar.classList.add('active');
      overlay?.classList.add('active');
      syncLibraryControl();
      return;
    }

    document.body.classList.toggle('v1-library-collapsed');
    syncLibraryControl();
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

  let pendingProductTab = '';

  function productLabel(tab) {
    if (tab === 'projects') return 'Projects';
    if (tab === 'video') return 'Video';
    if (tab === 'library') return 'Library';
    return 'That workspace';
  }

  function setProductLaunchBusy(tab, busy) {
    $$(`[data-v1-command="${tab}"]`).forEach(button => {
      button.classList.toggle('is-loading', busy);
      if (busy) button.setAttribute('aria-busy', 'true');
      else button.removeAttribute('aria-busy');

      const marker = button.querySelector(':scope > b');
      if (!marker) return;
      if (!marker.dataset.v1ReadyMarker) marker.dataset.v1ReadyMarker = marker.textContent || '↗';
      marker.textContent = busy ? '…' : marker.dataset.v1ReadyMarker;
    });
  }

  function flushPendingProduct() {
    const tab = pendingProductTab;
    if (!tab) return false;
    pendingProductTab = '';
    setProductLaunchBusy(tab, false);

    const open = window.CrumpProduct53?.open;
    if (typeof open !== 'function') {
      window.showToast?.(`${productLabel(tab)} did not finish loading. Refresh Ask Crump and try again.`, 'error');
      return false;
    }
    open(tab);
    return true;
  }

  function openProduct(tab) {
    const open = window.CrumpProduct53?.open;
    if (typeof open === 'function') {
      open(tab);
      return true;
    }

    if (pendingProductTab && pendingProductTab !== tab) {
      setProductLaunchBusy(pendingProductTab, false);
    }
    pendingProductTab = tab;
    setProductLaunchBusy(tab, true);

    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      return flushPendingProduct();
    }
    return false;
  }

  window.addEventListener('crump:body-runtime-ready', flushPendingProduct);

  const STARTER_INTENTS = new Set(['focus', 'research', 'file', 'image', 'projects', 'video']);

  async function recordStarterIntent(command) {
    if (!STARTER_INTENTS.has(command)) return false;
    return Boolean(await window.CrumpAnalytics?.track?.('StarterIntentReached', {
      eventKey: 'first-starter-intent',
      source: command,
    }));
  }

  function recentWorkChat() {
    const current = String(window.currentChatId || '');
    return (Array.isArray(window.chats) ? window.chats : [])
      .filter(chat =>
        String(chat?.id || chat?.chat_id || '') !== current
        && Array.isArray(chat?.messages)
        && chat.messages.length > 0
      )
      .sort((left, right) => {
        const rightTime = Date.parse(right?.updatedAt || right?.updated_at || right?.createdAt || 0) || 0;
        const leftTime = Date.parse(left?.updatedAt || left?.updated_at || left?.createdAt || 0) || 0;
        return rightTime - leftTime;
      })[0] || null;
  }

  function syncRecentWork() {
    const region = byId('v1RecentWork');
    const button = byId('v1RecentWorkButton');
    const nameNode = byId('v1RecentWorkName');
    const hintNode = byId('v1RecentWorkHint');
    if (!region || !button) return;
    const recent = recentWorkChat();
    const chatId = String(recent?.id || recent?.chat_id || '');
    const rawName = String(recent?.title || '')
      .replace(/\s+/g, ' ')
      .trim();
    const hasUsefulName = rawName && rawName.toLowerCase() !== 'new conversation';
    const recentName = hasUsefulName ? rawName.slice(0, 72) : 'Continue recent work';
    button.dataset.chatId = chatId;
    button.setAttribute('aria-label', hasUsefulName ? `Continue: ${recentName}` : recentName);
    if (nameNode) nameNode.textContent = recentName;
    if (hintNode) {
      hintNode.textContent = hasUsefulName
        ? 'Continue where you left off.'
        : 'Open your most recent active conversation.';
    }
    region.hidden = !chatId;
  }

  function wireRecentWork() {
    const button = byId('v1RecentWorkButton');
    if (!button || button.dataset.v1Wired === 'true') return;
    button.dataset.v1Wired = 'true';
    button.addEventListener('click', () => {
      const chatId = String(button.dataset.chatId || '');
      if (!chatId || typeof window.loadChat !== 'function') return;
      void window.CrumpAnalytics?.track?.('RecentWorkResumed', {
        eventKey: 'recent-work-resumed',
        source: 'launchpad',
      });
      window.loadChat(chatId);
    });
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
      case 'projects':
        openProduct('projects');
        break;
      case 'video':
        openProduct('video');
        break;
      case 'saved':
        openProduct('library');
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
      button.addEventListener('click', () => {
        const requested = button.dataset.v1Command;
        if (button.closest('#v1Launchpad')) void recordStarterIntent(requested);
        command(requested);
      });
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
    syncRecentWork();
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
          syncLibraryControl();
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
      new MutationObserver(() => {
        syncWorkspaceTitle();
        syncRecentWork();
      })
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

    const sidebar = byId('sidebar');
    if (sidebar && sidebar.dataset.v1LibraryObserved !== 'true') {
      sidebar.dataset.v1LibraryObserved = 'true';
      new MutationObserver(syncLibraryControl)
        .observe(sidebar, {attributes: true, attributeFilter: ['class']});
    }
  }

  function restoreDesktopPreference() {
    if (!matchMedia('(max-width: 1100px)').matches) {
      try {
        // The reorganized rail originally removed the only visible Chats
        // control. Clear that stranded preference once so existing desktop
        // users see their conversation history and can make a fresh choice
        // with the permanent Chats toggle.
        if (localStorage.getItem('crump_v1_library_control_v2') !== 'ready') {
          localStorage.removeItem('crump_v1_library_collapsed');
          localStorage.setItem('crump_v1_library_control_v2', 'ready');
        }
        if (localStorage.getItem('crump_v1_library_collapsed') === '1') {
          document.body.classList.add('v1-library-collapsed');
        }
      } catch (_) {}
    }
    syncLibraryControl();
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
      syncLibraryControl();
    });
  }

  function reassertAfterLegacyShell() {
    restoreBranding();
    syncLaunchpad();
    syncWorkspaceTitle();
    syncRecentWork();
    syncLibraryControl();
    wireComposer();
  }

  function boot() {
    document.body.classList.add('crump-v1-body');
    restoreDesktopPreference();
    wireCommands();
    wireRecentWork();
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
    syncRecentWork();

    // 5.0 performs an immediate and one delayed shell pass.
    // These bounded reassertions reclaim only the brand/context surfaces.
    setTimeout(reassertAfterLegacyShell, 150);
    setTimeout(reassertAfterLegacyShell, 950);

    document.documentElement.dataset.crumpBodyV1 = 'ready';
  }

  window.CrumpBodyV1 = Object.freeze({
    command,
    syncConversationLibrary: syncLibraryControl,
    toggleConversationLibrary: openLibrary,
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, {once: true});
  } else {
    boot();
  }

  window.addEventListener('pageshow', reassertAfterLegacyShell);
})();
