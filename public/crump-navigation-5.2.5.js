(() => {
  'use strict';

  if (window.__crumpNavigation525Loaded) return;
  window.__crumpNavigation525Loaded = true;

  const byId = id => document.getElementById(id);

  function closeMobileSidebar() {
    byId('sidebar')?.classList.remove('active');
    byId('sidebarOverlay')?.classList.remove('active');
    const menu = byId('menuBtn');
    menu?.setAttribute('aria-expanded', 'false');
    menu?.setAttribute('aria-label', 'Open Chats');
    menu?.setAttribute('title', 'Open Chats');
    window.CrumpBodyV1?.syncConversationLibrary?.();
  }

  function removeDuplicateRailDestinations() {
    document
      .querySelectorAll(
        '.v1-rail [data-v1-command="settings"], ' +
        '.v1-rail [data-v1-command="billing"]'
      )
      .forEach(node => node.remove());

    document.querySelector('.v1-rail .v1-rail-spacer')?.remove();
  }

  function normalizeFooterDestination(id, label) {
    const button = byId(id);
    if (!button) return;

    // The footer label is the navigation affordance. Removing its decorative
    // destination icon prevents the row from reading like two separate controls.
    button.querySelector(':scope > svg')?.remove();
    button.setAttribute('aria-label', label);
  }

  function normalizeSidebar() {
    removeDuplicateRailDestinations();
    normalizeFooterDestination('settingsBtn', 'Settings');
    normalizeFooterDestination('upgradeBtnSidebar', 'Plan & credits');
  }

  function destinationIsOpen(id) {
    if (id === 'settingsBtn') {
      const modal = byId('settingsModal');
      return Boolean(modal && modal.style.display && modal.style.display !== 'none');
    }
    if (id === 'upgradeBtnSidebar') {
      return Boolean(document.querySelector('.billing51-modal, .upgrade-modal.active'));
    }
    if (id === 'crump53ProjectsSidebar') {
      const studio = byId('crump53Studio');
      return Boolean(studio && !studio.hidden);
    }
    return false;
  }

  function openDestination(id) {
    if (destinationIsOpen(id)) return;

    if (id === 'settingsBtn') {
      window.openSettings?.();
      return;
    }
    if (id === 'upgradeBtnSidebar') {
      const openBilling = window.showBillingCenter || window.showUpgradePrompt;
      openBilling?.();
      return;
    }
    if (id === 'crump53ProjectsSidebar') {
      window.CrumpProduct53?.open?.('projects');
    }
  }

  function wireDrawerClose() {
    if (document.documentElement.dataset.crumpNavigation525Wired === 'true') return;
    document.documentElement.dataset.crumpNavigation525Wired = 'true';

    // Let the destination's own handler finish before the drawer closes. Closing
    // during capture makes touch browsers retarget the same activation to the
    // conversation behind the drawer, so the requested surface never appears.
    // The zero-delay fallback still repairs a lost late-bound listener.
    document.addEventListener('click', event => {
      const destination = event.target.closest?.(
        '#settingsBtn, #upgradeBtnSidebar, #crump53ProjectsSidebar'
      );
      if (!destination) return;
      const destinationId = destination.id;
      window.setTimeout(() => {
        openDestination(destinationId);
        closeMobileSidebar();
      }, 0);
    });
  }

  function observeSidebar() {
    const sidebar = byId('sidebar');
    if (!sidebar || sidebar.dataset.crumpNavigation525Observed === 'true') return;

    sidebar.dataset.crumpNavigation525Observed = 'true';
    new MutationObserver(() => normalizeSidebar())
      .observe(sidebar, {childList: true, subtree: true});
  }

  function boot() {
    normalizeSidebar();
    wireDrawerClose();
    observeSidebar();

    // A bounded second pass covers late billing hydration without polling.
    requestAnimationFrame(normalizeSidebar);
    setTimeout(normalizeSidebar, 250);

    document.documentElement.dataset.crumpNavigation525 = 'ready';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, {once: true});
  } else {
    boot();
  }

  window.addEventListener('pageshow', normalizeSidebar);
})();
