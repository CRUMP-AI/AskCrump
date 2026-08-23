(() => {
  'use strict';

  if (window.__askCrumpV1StabilityLoaded) return;
  window.__askCrumpV1StabilityLoaded = true;

  const SETTINGS_GLYPH = `
    <circle cx="12" cy="12" r="3.25"></circle>
    <path d="M12 2.75v2M12 19.25v2M2.75 12h2M19.25 12h2M5.46 5.46l1.42 1.42M17.12 17.12l1.42 1.42M18.54 5.46l-1.42 1.42M6.88 17.12l-1.42 1.42"></path>
  `;

  const TOOL_TARGETS = Object.freeze({
    Web: 'searchQuickAction',
    Image: 'imageQuickAction',
    Code: 'codeQuickAction',
  });

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

  function invokeQuickActionWithoutClosing(panel, label) {
    const targetId = TOOL_TARGETS[label];
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) return;

    /* The 4.4 panel historically calls target.click() and then closes itself.
       Dispatch directly to the target without bubbling to document so the
       quick action still runs while Crump Controls remains open. */
    target.dispatchEvent(new MouseEvent('click', {
      bubbles: false,
      cancelable: true,
      view: window,
    }));

    document.getElementById('userInput')?.focus({ preventScroll: true });
    panel.querySelector('.crump44-close')?.focus({ preventScroll: true });
  }

  function keepCrumpControlsOpen() {
    const panel = document.getElementById('crumpIntelligencePanel');
    if (!panel || panel.dataset.v1StableControls === 'true') return;

    panel.dataset.v1StableControls = 'true';

    /* Capture the three tool buttons before their 4.4 handlers can execute the
       old closePanel() behavior. The panel now stays open until the user closes
       it, presses Escape, or clicks outside it. */
    panel.addEventListener('click', event => {
      const tool = event.target.closest?.('.crump44-tool');
      if (!tool || !panel.contains(tool)) return;

      const label = tool.textContent?.trim();
      if (!TOOL_TARGETS[label]) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      invokeQuickActionWithoutClosing(panel, label);
    }, true);

    /* Response mode, memory switches, answer checking, and other controls
       rebuild panel contents synchronously. Stopping bubbling at the stable
       panel shell prevents the document's outside-click handler from
       misclassifying those rebuilt controls as outside clicks. */
    panel.addEventListener('click', event => {
      event.stopPropagation();
    });
  }

  function installViewportGesturePolicy() {
    if (document.documentElement.dataset.crumpViewportGesturePolicy === 'true') return;
    document.documentElement.dataset.crumpViewportGesturePolicy = 'true';

    /* Keep the application at its intended 1:1 viewport scale. Safari exposes
       gesture* events for pinch zoom; touchmove is the cross-engine fallback. */
    const blockViewportPinch = event => event.preventDefault();

    document.addEventListener('gesturestart', blockViewportPinch, { passive: false });
    document.addEventListener('gesturechange', blockViewportPinch, { passive: false });

    document.addEventListener('touchmove', event => {
      if ((event.touches?.length || 0) < 2) return;
      event.preventDefault();
    }, { passive: false });
  }

  function install() {
    patchSettingsIcons();
    keepCrumpControlsOpen();
    installViewportGesturePolicy();
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
