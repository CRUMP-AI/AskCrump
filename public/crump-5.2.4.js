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
    if (!(img instanceof HTMLImageElement)) return;
    img.src = src;
    img.alt = alt;
    if (className) img.classList.add(className);
    img.removeAttribute('width');
    img.removeAttribute('height');
  }

  function restoreHeaderBranding() {
    const branding = document.querySelector('.header-branding');
    if (!branding) return;

    const existing = branding.querySelector('.crump524-header-wordmark');
    if (existing && existing.getAttribute('src') === BRAND.horizontalLight) return;

    branding.replaceChildren();
    branding.classList.add('crump524-header-brand');

    const logo = document.createElement('img');
    setImage(logo, BRAND.horizontalLight, 'crump524-header-wordmark');
    logo.decoding = 'async';
    branding.appendChild(logo);
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

    branding.replaceChildren();
    const logo = document.createElement('img');
    setImage(logo, BRAND.horizontalLight, 'crump524-sidebar-wordmark');
    branding.appendChild(logo);
  }

  function restoreEmptyStateBranding() {
    document.querySelectorAll('.crump-empty-mark img').forEach(img => {
      setImage(img, BRAND.mark, 'crump524-empty-mark', '');
    });

    document.querySelectorAll('.crump-empty-eyebrow').forEach(eyebrow => {
      eyebrow.hidden = true;
      eyebrow.setAttribute('aria-hidden', 'true');
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

    const observer = new MutationObserver(() => {
      restoreBranding();
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot, {once: true});
})();
