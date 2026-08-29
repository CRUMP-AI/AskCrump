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

  const assets = Object.freeze([
    ['style', '/crump-4.3.css', 'crump43'],
    ['script', '/crump-4.3.js', 'crump43'],
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
    ['style', '/crump-v1.css', 'crumpv1'],
    ['script', '/crump-v1.js', 'crumpv1'],
  ]);

  function loadStyle(url, key) {
    const keyed = document.querySelector(`link[data-${key}]`);
    if (keyed) return Promise.resolve();

    const existing = document.querySelector(`link[href="${url}"]`);
    if (existing) {
      // Preserve the live stylesheet while a cached clone takes the canonical
      // runtime position. Re-appending the live node can flash unstyled content.
      return new Promise(resolve => {
        const node = existing.cloneNode();
        node.dataset[key] = 'true';
        node.addEventListener('load', resolve, {once: true});
        node.addEventListener('error', resolve, {once: true});
        document.head.appendChild(node);
      });
    }

    return new Promise(resolve => {
      const node = document.createElement('link');
      node.rel = 'stylesheet';
      node.href = url;
      node.dataset[key] = 'true';
      node.addEventListener('load', resolve, {once: true});
      node.addEventListener('error', resolve, {once: true});
      document.head.appendChild(node);
    });
  }

  function loadScript(url, key) {
    if (document.querySelector(`script[data-${key}]`)) return Promise.resolve();
    return new Promise(resolve => {
      const node = document.createElement('script');
      node.src = url;
      node.async = false;
      node.dataset[key] = 'true';
      node.addEventListener('load', resolve, {once: true});
      node.addEventListener('error', resolve, {once: true});
      document.head.appendChild(node);
    });
  }

  async function bootLayers() {
    const styles = assets.filter(([kind]) => kind === 'style');
    const scripts = assets.filter(([kind]) => kind === 'script');

    // Styles can fetch concurrently. A preloaded V1 layer is cloned at the final
    // cascade position so its active copy never leaves the document.
    await Promise.all(styles.map(([, url, key]) => loadStyle(url, key)));

    // Behavior layers stay deterministic because later modules wrap earlier ones.
    for (const [, url, key] of scripts) {
      await loadScript(url, key);
    }

    document.documentElement.dataset.crumpV1Runtime = 'ready';
  }

  if (document.readyState === 'complete') {
    void bootLayers();
  } else {
    window.addEventListener('load', () => { void bootLayers(); }, {once: true});
  }
})();
