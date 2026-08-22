(() => {
  'use strict';

  if (window.__crumpNavigation525Loaded) return;
  window.__crumpNavigation525Loaded = true;

  const byId = id => document.getElementById(id);

  function closeMobileSidebar() {
    byId('sidebar')?.classList.remove('active');
    byId('sidebarOverlay')?.classList.remove('active');
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
      return Boolean(document.querySelector('.billing51-modal'));
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

    // Capture phase makes this resilient to late modules replacing or inserting
    // sidebar destinations. Existing handlers get the first chance to open their
    // surface; the zero-delay fallback repairs a lost listener without double-opening.
    document.addEventListener('click', event => {
      const destination = event.target.closest?.(
        '#settingsBtn, #upgradeBtnSidebar, #crump53ProjectsSidebar'
      );
      if (!destination) return;
      closeMobileSidebar();
      window.setTimeout(() => openDestination(destination.id), 0);
    }, true);
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
