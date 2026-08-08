(() => {
  'use strict';

  if (window.__crump524IdentityLoaded) return;
  window.__crump524IdentityLoaded = true;

  const BRAND = Object.freeze({
    mark: '/assets/ask-crump-mark.png',
    wordmarkDark: '/assets/ask-crump-wordmark-dark.png',
    wordmarkLight: '/assets/ask-crump-wordmark-light.png',
  });

  function buildMark(className, alt = 'Ask Crump') {
    const logo = document.createElement('img');
    logo.src = BRAND.mark;
    logo.alt = alt;
    logo.className = className;
    logo.decoding = 'async';
    return logo;
  }

  function restoreHeaderBranding() {
    const branding = document.querySelector('.header-branding');
    if (!branding) return;

    const existingMark = branding.querySelector('.crump524-header-mark');
    const existingLabel = branding.querySelector('.crump524-header-label');
    if (existingMark && existingLabel) return;

    branding.replaceChildren();
    branding.classList.add('crump524-header-brand');

    const logo = buildMark('crump524-header-mark');
    const label = document.createElement('span');
    label.className = 'crump524-header-label';
    label.textContent = 'Ask Crump';

    branding.append(logo, label);
    branding.dataset.crump524 = 'true';
  }

  function restoreAuthBranding() {
    document.querySelectorAll('.auth-logo').forEach(logo => {
      logo.src = BRAND.wordmarkLight;
      logo.alt = 'Ask Crump';
      logo.classList.add('crump524-auth-wordmark');
      logo.removeAttribute('width');
      logo.removeAttribute('height');
    });

    document.querySelectorAll('.onboarding-logo').forEach(logo => {
      logo.src = BRAND.wordmarkLight;
      logo.alt = 'Ask Crump';
      logo.classList.add('crump524-onboarding-wordmark');
      logo.removeAttribute('width');
      logo.removeAttribute('height');
    });
  }

  function restoreSidebarBranding() {
    const branding = document.querySelector('.sidebar-branding');
    if (!branding) return;

    const oldIcon = branding.querySelector('.sidebar-logo-icon');
    if (oldIcon) {
      oldIcon.src = BRAND.mark;
      oldIcon.alt = 'Ask Crump';
      oldIcon.classList.add('crump524-sidebar-mark');
    }

    const label = branding.querySelector('.sidebar-logo');
    if (label) {
      label.textContent = 'Ask Crump';
      label.classList.add('crump524-sidebar-label');
    }
  }

  function restoreBranding() {
    restoreHeaderBranding();
    restoreAuthBranding();
    restoreSidebarBranding();
  }

  function observeBranding() {
    const header = document.querySelector('.header-branding');
    if (header) {
      new MutationObserver(() => {
        if (!header.querySelector('.crump524-header-mark')) {
          restoreHeaderBranding();
        }
      }).observe(header, {childList: true, subtree: true});
    }

    const bodyObserver = new MutationObserver(mutations => {
      let shouldRestore = false;
      for (const mutation of mutations) {
        if (mutation.type !== 'attributes') continue;
        const target = mutation.target;
        if (
          target instanceof HTMLImageElement &&
          (
            target.classList.contains('auth-logo') ||
            target.classList.contains('onboarding-logo') ||
            target.classList.contains('sidebar-logo-icon')
          )
        ) {
          shouldRestore = true;
          break;
        }
      }
      if (shouldRestore) restoreBranding();
    });

    bodyObserver.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ['src'],
    });
  }

  function boot() {
    restoreBranding();
    observeBranding();
  }

  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot, {once: true});
})();
