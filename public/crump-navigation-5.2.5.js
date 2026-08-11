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

  function wireDrawerClose() {
    if (document.documentElement.dataset.crumpNavigation525Wired === 'true') return;
    document.documentElement.dataset.crumpNavigation525Wired = 'true';

    // Capture phase makes this resilient to the billing module replacing/cloning
    // #upgradeBtnSidebar while still allowing its existing destination handler to run.
    document.addEventListener('click', event => {
      const destination = event.target.closest?.('#settingsBtn, #upgradeBtnSidebar');
      if (!destination) return;
      closeMobileSidebar();
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
