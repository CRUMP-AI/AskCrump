window.CRUMP_CONFIG = Object.freeze({
  apiBase: 'https://askcrump.com',
  revenueCatAppleApiKey: '',
  revenueCatGoogleApiKey: '',
  revenueCatEntitlement: 'professional',
  revenueCatProfessionalProductId: 'askcrump_professional_monthly',
  revenueCatEnterpriseProductId: 'askcrump_enterprise_monthly',
  webProfessionalPriceLabel: '$20/month',
  webEnterprisePriceLabel: '$50/month',
});

(() => {
  'use strict';
  const assets = [
    ['style', '/crump-4.4.css', 'crump44'],
    ['script', '/crump-4.4.js', 'crump44'],
    ['style', '/crump-5.0.css', 'crump50'],
    ['script', '/crump-5.0.js', 'crump50'],
  ];
  for (const [kind, url, key] of assets) {
    if (kind === 'style' && !document.querySelector(`link[data-${key}]`)) {
      const node = document.createElement('link');
      node.rel = 'stylesheet'; node.href = url; node.dataset[key] = 'true'; document.head.appendChild(node);
    }
    if (kind === 'script' && !document.querySelector(`script[data-${key}]`)) {
      const node = document.createElement('script');
      node.src = url; node.async = false; node.dataset[key] = 'true'; document.head.appendChild(node);
    }
  }
})();
