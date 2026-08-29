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

  const styles = Object.freeze([
    ['/crump-4.3.css', 'crump43'],
    ['/crump-4.4.css', 'crump44'],
    ['/crump-5.0.css', 'crump50'],
    ['/crump-billing-5.1.css', 'billing51'],
    ['/crump-5.2.css', 'crump52'],
    ['/crump-5.2.2.css', 'crump522'],
    ['/crump-v1-body.css?v=5.9.70', 'crumpbodyv1'],
  ]);

  const scripts = Object.freeze([
    ['/crump-4.3.js?v=5.9.70', 'crump43'],
    ['/crump-4.4.js', 'crump44'],
    ['/crump-5.0.js?v=5.9.70', 'crump50'],
    ['/crump-billing-5.1.js', 'billing51'],
    ['/crump-5.2.js', 'crump52'],
    ['/crump-5.2.2.js', 'crump522'],
    ['/crump-v1-body.js', 'crumpbodyv1'],
    ['/crump-v1-stability.js', 'crumpv1stability'],
  ]);

  function loadStyle(url, key) {
    const keyed = document.querySelector(`link[data-${key}]`);
    if (keyed) return Promise.resolve();

    const existing = document.querySelector(`link[href="${url}"]`);
    if (existing) {
      existing.dataset[key] = 'true';
      document.head.appendChild(existing);
      return Promise.resolve();
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

  async function boot() {
    await Promise.all(styles.map(([url, key]) => loadStyle(url, key)));

    // Navigation cleanup is intentionally loaded after the existing visual stack so
    // its narrow sidebar rules have final authority without disturbing legacy layers.
    await loadStyle('/crump-navigation-5.2.5.css', 'crumpnav525');
    await loadStyle('/crump-product-5.3.css', 'crumpproduct53');
    await loadStyle('/crump-product-5.3.1.css', 'crumpproduct531');
    await loadStyle('/crump-polish-5.6.css', 'crumppolish56');
    await loadStyle('/crump-library-5.7.css', 'crumplibrary57');
    await loadStyle('/crump-code-5.9.35.css', 'crumpcode5935');
    // Keep the stability layer after every tool stylesheet so its mobile viewport
    // and editor rules win over dynamically rendered feature controls.
    await loadStyle('/crump-v1-stability.css', 'crumpv1stability');
    // The five-destination information architecture is the final visual layer.
    // It reorganizes navigation without changing the underlying product surfaces.
    await loadStyle('/crump-navigation-5.9.30.css', 'crumpnav5930');

    for (const [url, key] of scripts) {
      await loadScript(url, key);
    }

    // Load last so the cleanup runs after legacy/V1 handlers have initialized.
    await loadScript('/crump-navigation-5.2.5.js', 'crumpnav525');
    await loadScript('/crump-product-5.3.js', 'crumpproduct53');
    await loadScript('/crump-product-5.3.1.js', 'crumpproduct531');
    await loadScript('/crump-subscriptions-5.3.2.js', 'crumpsubscriptions532');
    await loadScript('/crump-polish-5.6.js', 'crumppolish56');
    await loadScript('/crump-library-5.7.js', 'crumplibrary57');
    await loadScript('/crump-navigation-5.9.30.js', 'crumpnav5930');
    await loadScript('/crump-code-5.9.35.js', 'crumpcode5935');

    document.documentElement.dataset.crumpBodyRuntime = 'ready';
    window.dispatchEvent(new CustomEvent('crump:body-runtime-ready'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { void boot(); }, {once: true});
  } else {
    void boot();
  }
})();
