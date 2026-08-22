(() => {
  'use strict';

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  document.querySelectorAll('[data-cta]').forEach(link => {
    link.addEventListener('click', () => {
      window.va('event', {
        name: 'MarketingCTA',
        data: {
          location: link.dataset.cta || 'unknown',
          plan: link.dataset.plan || 'unspecified',
        },
      });
    });
  });

  const host = window.location.hostname.toLowerCase();
  if ((host === 'askcrump.com' || host === 'www.askcrump.com') && window.location.pathname === '/') {
    window.location.replace('/app');
    return;
  }

  const navbar = document.querySelector('.navbar');
  if (!navbar) return;
  const updateNavbar = () => navbar.classList.toggle('scrolled', window.scrollY > 24);
  window.addEventListener('scroll', updateNavbar, { passive: true });
  updateNavbar();
})();
