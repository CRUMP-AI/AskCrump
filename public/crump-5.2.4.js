(() => {
  'use strict';

  if (window.__crump524IdentityLoaded) return;
  window.__crump524IdentityLoaded = true;

  const BRAND = Object.freeze({
    horizontalLight: '/assets/ask-crump-horizontal-light.png',
    horizontalDark: '/assets/ask-crump-horizontal-dark.png',
    mark: '/assets/ask-crump-mark-display.png',
  });

  function setImage(img, src, className, alt = 'Ask Crump') {
    if (!(img instanceof HTMLImageElement)) return false;

    let changed = false;
    if (img.getAttribute('src') !== src) {
      img.src = src;
      changed = true;
    }
    if (img.alt !== alt) {
      img.alt = alt;
      changed = true;
    }
    if (className && !img.classList.contains(className)) {
      img.classList.add(className);
      changed = true;
    }
    if (img.hasAttribute('width')) {
      img.removeAttribute('width');
      changed = true;
    }
    if (img.hasAttribute('height')) {
      img.removeAttribute('height');
      changed = true;
    }
    return changed;
  }

  function restoreHeaderBranding() {
    const branding = document.querySelector('.header-branding');
    if (!branding) return;

    const existing = branding.querySelector(':scope > .crump524-header-wordmark');
    if (
      existing instanceof HTMLImageElement &&
      existing.getAttribute('src') === BRAND.horizontalLight &&
      branding.children.length === 1
    ) {
      return;
    }

    const logo = document.createElement('img');
    setImage(logo, BRAND.horizontalLight, 'crump524-header-wordmark');
    logo.decoding = 'async';

    branding.replaceChildren(logo);
    branding.classList.add('crump524-header-brand');
    branding.dataset.crump524 = 'true';
  }

  function restoreAuthBranding() {
    document.querySelectorAll('.auth-logo').forEach(logo => {
      setImage(logo, BRAND.horizontalLight, 'crump524-auth-wordmark');
    });

    document.querySelectorAll('.onboarding-logo').forEach(logo => {
      setImage(logo, BRAND.horizontalLight, 'crump524-onboarding-wordmark');
    });
  }

  function restoreSidebarBranding() {
    const branding = document.querySelector('.sidebar-branding');
    if (!branding) return;

    const existing = branding.querySelector(':scope > .crump524-sidebar-wordmark');
    if (
      existing instanceof HTMLImageElement &&
      existing.getAttribute('src') === BRAND.horizontalLight &&
      branding.children.length === 1
    ) {
      return;
    }

    const logo = document.createElement('img');
    setImage(logo, BRAND.horizontalLight, 'crump524-sidebar-wordmark');
    branding.replaceChildren(logo);
  }

  function restoreEmptyStateBranding(root = document) {
    root.querySelectorAll?.('.crump-empty-mark img').forEach(img => {
      setImage(img, BRAND.mark, 'crump524-empty-mark', '');
    });

    root.querySelectorAll?.('.crump-empty-eyebrow').forEach(eyebrow => {
      if (!eyebrow.hidden) eyebrow.hidden = true;
      if (eyebrow.getAttribute('aria-hidden') !== 'true') {
        eyebrow.setAttribute('aria-hidden', 'true');
      }
    });
  }

  function restoreBranding() {
    restoreHeaderBranding();
    restoreAuthBranding();
    restoreSidebarBranding();
    restoreEmptyStateBranding();
  }

  function boot() {
    restoreBranding();

    // Only watch for newly-rendered UI nodes that actually need branding.
    // Never rewrite the whole sidebar/header on every DOM mutation.
    const observer = new MutationObserver(mutations => {
      let needsEmptyStateRefresh = false;
      let needsAuthRefresh = false;

      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;

          if (
            node.matches?.('.crump-empty-state, .crump-empty-mark, .crump-empty-eyebrow') ||
            node.querySelector?.('.crump-empty-mark, .crump-empty-eyebrow')
          ) {
            needsEmptyStateRefresh = true;
          }

          if (
            node.matches?.('.auth-logo, .onboarding-logo') ||
            node.querySelector?.('.auth-logo, .onboarding-logo')
          ) {
            needsAuthRefresh = true;
          }
        }
      }

      if (needsEmptyStateRefresh) restoreEmptyStateBranding();
      if (needsAuthRefresh) restoreAuthBranding();
    });

    observer.observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot, {once: true});
})();
