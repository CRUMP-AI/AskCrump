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
    ['style', '/crump-5.0.css?v=5.9.76-precision-edit-entry-1', 'crump50'],
    ['script', '/crump-5.0.js?v=5.9.76-precision-edit-handoff-1', 'crump50'],
    ['style', '/crump-precision-image-edit.css?v=5.9.76-precision-edit-studio-1', 'crumpprecisionimage'],
    ['script', '/crump-precision-image-edit.js?v=5.9.76-precision-edit-studio-1', 'crumpprecisionimage'],
    ['style', '/crump-billing-5.1.css?v=5.9.76-credit-pack-truth-1', 'billing51'],
    ['script', '/crump-billing-5.1.js?v=5.9.76-credit-pack-truth-1', 'billing51'],
    ['style', '/crump-5.2.css', 'crump52'],
    ['script', '/crump-5.2.js?v=5.9.76-credit-pack-truth-1', 'crump52'],
    ['style', '/crump-5.2.2.css?v=5.9.76-new-response-cue-1', 'crump522'],
    ['script', '/crump-5.2.2.js?v=5.9.76-new-response-cue-1', 'crump522'],
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
