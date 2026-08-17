(() => {
  'use strict';

  if (window.__askCrumpPolish56Loaded) return;
  window.__askCrumpPolish56Loaded = true;
  document.documentElement.dataset.crumpPolish = '5.6';

  const byId = id => document.getElementById(id);

  function syncStudioA11y() {
    const studio = byId('crump53Studio');
    if (!studio) return;
    const tabs = [...studio.querySelectorAll('[data-crump53-tab]')];
    const panels = [...studio.querySelectorAll('[data-crump53-panel]')];
    tabs.forEach((tab, index) => {
      const name = tab.dataset.crump53Tab;
      const panel = panels.find(item => item.dataset.crump53Panel === name);
      const tabId = `crump53Tab-${name}`;
      const panelId = `crump53Panel-${name}`;
      tab.id ||= tabId;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', panelId);
      tab.setAttribute('aria-selected', tab.classList.contains('is-active') ? 'true' : 'false');
      tab.tabIndex = tab.classList.contains('is-active') ? 0 : -1;
      if (panel) {
        panel.id ||= panelId;
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', tabId);
      }
      if (tab.dataset.crump56Wired !== 'true') {
        tab.dataset.crump56Wired = 'true';
        tab.addEventListener('click', () => requestAnimationFrame(syncStudioA11y));
        tab.addEventListener('keydown', event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          let next = index;
          if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
          if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
          if (event.key === 'Home') next = 0;
          if (event.key === 'End') next = tabs.length - 1;
          tabs[next]?.click();
          tabs[next]?.focus();
        });
      }
    });
  }

  function addTourControl() {
    const about = document.querySelector('[data-v1-settings-panel="about"] .settings-list');
    if (!about || byId('crump56ReplayTour')) return;
    const button = document.createElement('button');
    button.id = 'crump56ReplayTour';
    button.type = 'button';
    button.className = 'settings-row settings-row-action crump56-tour-row';
    button.innerHTML = `
      <div class="settings-row-text">
        <div class="settings-label">Replay product tour</div>
        <div class="settings-help">See Projects, creation tools, video continuation, and your Saved Library.</div>
      </div>
      <div class="settings-chevron" aria-hidden="true">›</div>`;
    button.addEventListener('click', () => {
      byId('closeSettingsBtn')?.click();
      window.setTimeout(() => window.restartTutorial?.(), 80);
    });
    about.prepend(button);
  }

  function markBusyButtons() {
    document.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button) return;
      requestAnimationFrame(() => {
        button.setAttribute('aria-busy', button.disabled ? 'true' : 'false');
      });
    }, true);
  }

  function observeStudio() {
    const root = document.body;
    const observer = new MutationObserver(records => {
      if (records.some(record => record.type === 'childList' || record.attributeName === 'hidden' || record.attributeName === 'class')) {
        syncStudioA11y();
        addTourControl();
      }
    });
    observer.observe(root, {subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'class']});
  }

  function boot() {
    syncStudioA11y();
    addTourControl();
    markBusyButtons();
    observeStudio();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
