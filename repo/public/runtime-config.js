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
  if (!document.querySelector('link[data-crump-44]')) {
    const stylesheet = document.createElement('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = '/crump-4.4.css';
    stylesheet.dataset.crump44 = 'true';
    document.head.appendChild(stylesheet);
  }
  if (!document.querySelector('script[data-crump-44]')) {
    const script = document.createElement('script');
    script.src = '/crump-4.4.js';
    script.async = false;
    script.dataset.crump44 = 'true';
    document.head.appendChild(script);
  }
})();
