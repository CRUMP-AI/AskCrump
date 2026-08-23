(() => {
  'use strict';

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  const ACQUISITION_KEY = 'askcrump.acquisition-source';

  function safeSource(value, fallback = '') {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9_-]{1,32}$/.test(normalized) ? normalized : fallback;
  }

  function referringSource() {
    if (!document.referrer) return 'direct';
    try {
      const host = new URL(document.referrer).hostname.toLowerCase();
      if (host === location.hostname || host.endsWith('.askcrump.com')) return 'direct';
      const sources = [
        ['instagram.com', 'instagram'],
        ['facebook.com', 'facebook'],
        ['linkedin.com', 'linkedin'],
        ['tiktok.com', 'tiktok'],
        ['youtube.com', 'youtube'],
        ['youtu.be', 'youtube'],
        ['twitter.com', 'x'],
        ['x.com', 'x'],
        ['t.co', 'x'],
        ['clevercrump.com', 'clevercrump'],
      ];
      return sources.find(([domain]) => host === domain || host.endsWith(`.${domain}`))?.[1] || 'referral';
    } catch (_) {
      return 'direct';
    }
  }

  function acquisitionSource() {
    const params = new URLSearchParams(location.search);
    const explicit = safeSource(
      params.get('utm_source') || params.get('acquisition') || params.get('source'),
    );
    if (explicit) {
      try { sessionStorage.setItem(ACQUISITION_KEY, explicit); } catch (_) {}
      return explicit;
    }
    try {
      const stored = safeSource(sessionStorage.getItem(ACQUISITION_KEY));
      if (stored) return stored;
    } catch (_) {}
    const derived = referringSource();
    try { sessionStorage.setItem(ACQUISITION_KEY, derived); } catch (_) {}
    return derived;
  }

  const acquisition = acquisitionSource();
  document.querySelectorAll('[data-cta]').forEach(link => {
    try {
      const destination = new URL(link.getAttribute('href'), location.href);
      if (destination.origin === location.origin && destination.pathname === '/app') {
        destination.searchParams.set('acquisition', acquisition);
        link.setAttribute('href', `${destination.pathname}${destination.search}${destination.hash}`);
      }
    } catch (_) {}
    link.addEventListener('click', () => {
      window.va('event', {
        name: 'MarketingCTA',
        data: {
          location: link.dataset.cta || 'unknown',
          plan: link.dataset.plan || 'unspecified',
          acquisition,
        },
      });
    });
  });

  const navbar = document.querySelector('.navbar');
  if (!navbar) return;
  const updateNavbar = () => navbar.classList.toggle('scrolled', window.scrollY > 24);
  window.addEventListener('scroll', updateNavbar, { passive: true });
  updateNavbar();
})();
