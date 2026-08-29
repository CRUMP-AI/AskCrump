window.CRUMP_CONFIG = Object.freeze({
  apiBase: 'https://www.askcrump.com',
  revenueCatAppleApiKey: '',
  revenueCatGoogleApiKey: '',
  revenueCatEntitlement: 'professional',
  revenueCatProfessionalProductId: 'askcrump_professional_monthly',
  revenueCatEnterpriseProductId: 'askcrump_enterprise_monthly',
  revenueCatCredits50ProductId: 'askcrump_credits_50',
  revenueCatCredits150ProductId: 'askcrump_credits_150',
  revenueCatCredits400ProductId: 'askcrump_credits_400',
  webProfessionalPriceLabel: '$20/month',
  webEnterprisePriceLabel: '$50/month',
  webCredits50PriceLabel: '$4.99',
  webCredits150PriceLabel: '$9.99',
  webCredits400PriceLabel: '$19.99',
});

(() => {
  'use strict';
  const assets = [
    ['style', '/crump-4.4.css', 'crump44'],
    ['script', '/crump-4.4.js', 'crump44'],
    ['style', '/crump-5.0.css', 'crump50'],
    ['script', '/crump-5.0.js', 'crump50'],
    ['style', '/crump-billing-5.1.css', 'billing51'],
    ['script', '/crump-billing-5.1.js?v=5.9.76-credit-refresh-1', 'billing51'],
    ['style', '/crump-5.2.css', 'crump52'],
    ['script', '/crump-5.2.js', 'crump52'],
    ['style', '/crump-5.2.2.css', 'crump522'],
    ['script', '/crump-5.2.2.js', 'crump522'],
    ['style', '/crump-5.2.4.css', 'crump524'],
    ['script', '/crump-5.2.4.js', 'crump524'],
  ];
  for (const [kind, url, key] of assets) {
    const selector = kind === 'style' ? `link[data-${key}]` : `script[data-${key}]`;
    if (document.querySelector(selector)) continue;
    const node = document.createElement(kind === 'style' ? 'link' : 'script');
    if (kind === 'style') {
      node.rel = 'stylesheet';
      node.href = url;
    } else {
      node.src = url;
      node.async = false;
    }
    node.dataset[key] = 'true';
    document.head.appendChild(node);
  }
})();
