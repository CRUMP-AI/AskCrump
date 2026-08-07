(() => {
  'use strict';

  if (window.__crump524IdentityLoaded) return;
  window.__crump524IdentityLoaded = true;

  function restoreBranding() {
    const branding = document.querySelector('.header-branding');
    if (branding) {
      branding.replaceChildren();
      const logo = document.createElement('img');
      logo.src = '/assets/ask-crump-header.png';
      logo.alt = 'Ask Crump';
      logo.className = 'crump524-header-wordmark';
      branding.appendChild(logo);
      branding.dataset.crump524 = 'true';
    }

    document.querySelectorAll('.auth-logo').forEach(logo => {
      logo.src = '/assets/ask-crump-header.png';
      logo.alt = 'Ask Crump';
      logo.classList.add('crump524-auth-wordmark');
    });
  }

  function boot() {
    restoreBranding();

    // Older visual layers may rebuild the header during startup. Reassert the
    // actual brand mark only when that node changes, without polling.
    const branding = document.querySelector('.header-branding');
    if (branding) {
      new MutationObserver(() => {
        const current = branding.querySelector('.crump524-header-wordmark');
        if (!current) restoreBranding();
      }).observe(branding, {childList: true, subtree: true});
    }
  }

  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot, {once: true});
})();
