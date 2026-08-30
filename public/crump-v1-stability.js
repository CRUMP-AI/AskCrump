(() => {
  'use strict';

  if (window.__askCrumpV1StabilityLoaded) return;
  window.__askCrumpV1StabilityLoaded = true;

  const SETTINGS_GLYPH = `
    <circle cx="12" cy="12" r="3.25"></circle>
    <path d="M12 2.75v2M12 19.25v2M2.75 12h2M19.25 12h2M5.46 5.46l1.42 1.42M17.12 17.12l1.42 1.42M18.54 5.46l-1.42 1.42M6.88 17.12l-1.42 1.42"></path>
  `;

  function patchSettingsIcons() {
    document
      .querySelectorAll('[data-v1-command="settings"] svg, #settingsBtn svg')
      .forEach(svg => {
        if (svg.dataset.v1SettingsGlyph === 'true') return;
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.innerHTML = SETTINGS_GLYPH;
        svg.dataset.v1SettingsGlyph = 'true';
      });
  }

  function keepCrumpControlsOpen() {
    const panel = document.getElementById('crumpIntelligencePanel');
    if (!panel || panel.dataset.v1StableControls === 'true') return;

    panel.dataset.v1StableControls = 'true';

    /* Response effort, memory switches, answer review, and other controls
       rebuild panel contents synchronously. Stopping bubbling at the stable
       panel shell prevents the document's outside-click handler from
       misclassifying those rebuilt controls as outside clicks. */
    panel.addEventListener('click', event => {
      event.stopPropagation();
    });
  }

  function install() {
    patchSettingsIcons();
    keepCrumpControlsOpen();
  }

  install();
  requestAnimationFrame(install);
  setTimeout(install, 200);
  setTimeout(install, 1100);

  window.addEventListener('pageshow', install);

  const app = document.getElementById('appContainer');
  if (app) {
    new MutationObserver(() => {
      patchSettingsIcons();
      keepCrumpControlsOpen();
    }).observe(app, { childList: true, subtree: true });
  }
})();
