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

  const workspaceStyles = Object.freeze([
    ['/billing.css', 'workspacebilling'],
    ['/onboarding.css', 'workspaceonboarding'],
    ['/conversation.css?v=5.9.76', 'workspaceconversation'],
    ['/crump-4.3.css', 'crump43'],
    ['/crump-4.4.css', 'crump44'],
    ['/crump-5.0.css', 'crump50'],
    ['/crump-billing-5.1.css', 'billing51'],
    ['/crump-5.2.css', 'crump52'],
    ['/crump-5.2.2.css', 'crump522'],
    ['/crump-v1-body.css?v=5.9.76', 'crumpbodyv1'],
  ]);

  const workspaceScripts = Object.freeze([
    ['/onboarding.js', 'workspaceonboarding'],
    ['/scroll-manager.js', 'workspacescroll'],
    ['/profile-manager.js', 'workspaceprofile'],
    ['/billing-manager.js', 'workspacebilling'],
    ['/subscription-ui.js', 'workspacesubscription'],
    ['/chat-resilience.js?v=5.9.76', 'workspacechatresilience'],
    ['/ui-functions.js?v=5.9.76-referral-1', 'workspaceui'],
    ['/presence-manager.js?v=5.9.76', 'workspacepresence'],
    ['/sync-manager.js?v=5.9.76', 'workspacesync'],
    ['/chat-sync.js?v=5.9.76-sync-cadence-1', 'workspacechatsync'],
    ['/account-manager.js', 'workspaceaccount'],
    ['/app.js?v=5.9.76', 'workspaceapp'],
    ['/product-analytics.js?v=5.9.76', 'workspaceanalytics'],
  ]);

  const enhancementScripts = Object.freeze([
    ['/crump-4.3.js?v=5.9.76', 'crump43'],
    ['/crump-4.4.js', 'crump44'],
    ['/crump-5.0.js?v=5.9.76', 'crump50'],
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
      // Keep the active stylesheet in place. Moving a loaded <link> briefly
      // detaches its CSS in Chromium, exposing an unstyled workspace frame.
      // A cached clone can take final cascade position without creating that gap.
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

  let runtimePromise = null;

  async function boot() {
    document.documentElement.dataset.crumpBodyRuntime = 'loading';
    await Promise.all(workspaceStyles.map(([url, key]) => loadStyle(url, key)));

    // Navigation cleanup is intentionally loaded after the existing visual stack so
    // its narrow sidebar rules have final authority without disturbing legacy layers.
    await loadStyle('/crump-navigation-5.2.5.css', 'crumpnav525');
    await loadStyle('/crump-product-5.3.css?v=5.9.76-project-workspaces-3', 'crumpproduct53');
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

    for (const [url, key] of workspaceScripts) {
      await loadScript(url, key);
    }

    for (const [url, key] of enhancementScripts) {
      await loadScript(url, key);
    }

    // Load last so the cleanup runs after legacy/V1 handlers have initialized.
    await loadScript('/crump-navigation-5.2.5.js', 'crumpnav525');
    await loadScript('/crump-product-5.3.js?v=5.9.76-project-workspaces-3', 'crumpproduct53');
    await loadScript('/crump-product-5.3.1.js', 'crumpproduct531');
    await loadScript('/crump-subscriptions-5.3.2.js', 'crumpsubscriptions532');
    await loadScript('/crump-polish-5.6.js', 'crumppolish56');
    await loadScript('/crump-library-5.7.js', 'crumplibrary57');
    await loadScript('/crump-navigation-5.9.30.js', 'crumpnav5930');
    await loadScript('/crump-code-5.9.35.js', 'crumpcode5935');

    document.documentElement.dataset.crumpBodyRuntime = 'ready';
    window.dispatchEvent(new CustomEvent('crump:body-runtime-ready'));
  }

  function load() {
    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') return Promise.resolve();
    if (runtimePromise) return runtimePromise;
    runtimePromise = boot().catch(error => {
      runtimePromise = null;
      delete document.documentElement.dataset.crumpBodyRuntime;
      throw error;
    });
    return runtimePromise;
  }

  window.CrumpWorkspaceRuntime = Object.freeze({load});
  window.addEventListener('crump:workspace-runtime-requested', () => { void load(); });
})();
