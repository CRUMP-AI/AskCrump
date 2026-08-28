(() => {
  'use strict';

  if (window.__askCrumpPolish56Loaded) return;
  window.__askCrumpPolish56Loaded = true;
  document.documentElement.dataset.crumpPolish = '5.6';

  const byId = id => document.getElementById(id);

  function syncStudioA11y() {
    const studio = byId('crump53Studio');
    if (!studio) return;
    const panels = [...studio.querySelectorAll('[data-crump53-panel]')];
    const labels = {projects: 'Projects', manuscripts: 'Manuscripts', video: 'Video Studio', library: 'Library'};
    panels.forEach(panel => {
      const name = panel.dataset.crump53Panel || '';
      panel.setAttribute('role', 'region');
      panel.setAttribute('aria-label', labels[name] || 'Ask Crump workspace');
      panel.setAttribute('aria-hidden', panel.hidden ? 'true' : 'false');
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
        <div class="settings-label">Replay workspace guide</div>
        <div class="settings-help">Review Ask, Projects, Create, Library, and You.</div>
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
