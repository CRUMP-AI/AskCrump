(() => {
  'use strict';

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  const ACQUISITION_KEY = 'askcrump.acquisition-source';
  const LEGACY_ACQUISITION_SOURCES = new Set([
    'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'organic', 'clevercrump',
  ]);

  function safeSource(value, fallback = '') {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9_-]{1,32}$/.test(normalized) ? normalized : fallback;
  }

  function referringSource() {
    if (!document.referrer) return 'direct';
    try {
      const host = new URL(document.referrer).hostname.toLowerCase();
      if (host === location.hostname || host.endsWith('.askcrump.com')) return 'direct';
      const searchHosts = [
        'bing.com',
        'duckduckgo.com',
        'search.yahoo.com',
        'ecosia.org',
        'search.brave.com',
      ];
      if (
        /(^|\.)google\.[a-z.]+$/.test(host)
        || searchHosts.some(domain => host === domain || host.endsWith(`.${domain}`))
      ) return 'organic';
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
    const explicit = safeSource(params.get('utm_source') || params.get('acquisition'));
    const legacySource = safeSource(params.get('source'));
    const source = explicit || (LEGACY_ACQUISITION_SOURCES.has(legacySource) ? legacySource : '');
    if (source) {
      try { sessionStorage.setItem(ACQUISITION_KEY, source); } catch (_) {}
      return source;
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
    let analyticsEvent = 'MarketingCTA';
    try {
      const destination = new URL(link.getAttribute('href'), location.href);
      if (destination.origin === location.origin && destination.pathname === '/app') {
        analyticsEvent = destination.searchParams.get('signup') === '1'
          ? 'MarketingCTA'
          : 'MarketingSignin';
        destination.searchParams.set('acquisition', acquisition);
        link.setAttribute('href', `${destination.pathname}${destination.search}${destination.hash}`);
      }
    } catch (_) {}
    link.addEventListener('click', () => {
      window.va('event', {
        name: analyticsEvent,
        data: {
          location: link.dataset.cta || 'unknown',
          plan: link.dataset.plan || 'unspecified',
          acquisition,
        },
      });
    });
  });

  document.querySelectorAll('[data-explore]').forEach(link => {
    link.addEventListener('click', () => {
      window.va('event', {
        name: 'MarketingExplore',
        data: {
          destination: safeSource(link.dataset.explore, 'unknown'),
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
