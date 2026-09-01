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
    ['/onboarding.css?v=5.9.76-video-destination-1', 'workspaceonboarding'],
    ['/conversation.css?v=5.9.76-intelligence-receipt-1', 'workspaceconversation'],
    ['/crump-4.3.css', 'crump43'],
    ['/crump-4.4.css', 'crump44'],
    ['/crump-5.0.css?v=5.9.76-file-delivery-2', 'crump50'],
    ['/crump-billing-5.1.css?v=5.9.76-contextual-plan-recovery-1', 'billing51'],
    ['/crump-5.2.css', 'crump52'],
    ['/crump-5.2.2.css', 'crump522'],
    ['/crump-v1-body.css?v=5.9.76-intelligence-architecture-1', 'crumpbodyv1'],
    ['/lifecycle.css?v=5.9.76-lifecycle-activation-1', 'lifecycleactivation'],
  ]);

  const enhancementStyles = Object.freeze([
    ['/crump-navigation-5.2.5.css', 'crumpnav525'],
    ['/crump-product-5.3.css?v=5.9.76-file-library-usability-2', 'crumpproduct53'],
    ['/crump-product-5.3.1.css', 'crumpproduct531'],
    ['/crump-polish-5.6.css', 'crumppolish56'],
    ['/crump-library-5.7.css', 'crumplibrary57'],
    ['/crump-code-5.9.35.css?v=5.9.76-intelligence-architecture-1', 'crumpcode5935'],
    ['/crump-v1-stability.css', 'crumpv1stability'],
    ['/crump-navigation-5.9.30.css?v=5.9.76-mobile-drawer-destinations-1', 'crumpnav5930'],
  ]);

  const workspaceScripts = Object.freeze([
    ['/onboarding.js?v=5.9.76-video-destination-1', 'workspaceonboarding'],
    ['/scroll-manager.js', 'workspacescroll'],
    ['/profile-manager.js', 'workspaceprofile'],
    ['/billing-manager.js?v=5.9.76-commerce-recovery-1', 'workspacebilling'],
    ['/subscription-ui.js?v=5.9.76-commerce-recovery-1', 'workspacesubscription'],
    ['/chat-resilience.js?v=5.9.76-image-safety-recovery-1', 'workspacechatresilience'],
    ['/ui-functions.js?v=5.9.76-continuity-action-1', 'workspaceui'],
    ['/presence-manager.js?v=5.9.76', 'workspacepresence'],
    ['/sync-manager.js?v=5.9.76', 'workspacesync'],
    ['/chat-sync.js?v=5.9.76-sync-cadence-1', 'workspacechatsync'],
    ['/account-manager.js?v=5.9.76-account-deletion-billing-1', 'workspaceaccount'],
    ['/app.js?v=5.9.76-core-reliability-1', 'workspaceapp'],
    ['/product-analytics.js?v=5.9.76', 'workspaceanalytics'],
  ]);

  const enhancementScripts = Object.freeze([
    ['/crump-4.3.js?v=5.9.76-intelligence-architecture-1', 'crump43'],
    ['/crump-4.4.js?v=5.9.76-core-reliability-1', 'crump44'],
    ['/crump-5.0.js?v=5.9.76-file-delivery-2', 'crump50'],
    ['/crump-billing-5.1.js?v=5.9.76-commerce-recovery-1', 'billing51'],
    ['/crump-5.2.js?v=5.9.76-truthful-enterprise-positioning-1', 'crump52'],
    ['/crump-5.2.2.js?v=5.9.76-image-scroll-stability-1', 'crump522'],
    ['/crump-v1-body.js?v=5.9.76-destination-background-guard-1', 'crumpbodyv1'],
    ['/crump-v1-stability.js?v=5.9.76-intelligence-architecture-1', 'crumpv1stability'],
  ]);

  const finalScripts = Object.freeze([
    ['/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1', 'crumpnav525'],
    ['/crump-product-5.3.js?v=5.9.76-studio-section-isolation-1', 'crumpproduct53'],
    ['/crump-product-5.3.1.js?v=5.9.76-core-reliability-1', 'crumpproduct531'],
    ['/crump-subscriptions-5.3.2.js?v=5.9.76-commerce-recovery-1', 'crumpsubscriptions532'],
    ['/crump-polish-5.6.js?v=5.9.76-video-destination-1', 'crumppolish56'],
    ['/crump-library-5.7.js?v=5.9.76-demand-hydration-1', 'crumplibrary57'],
    ['/crump-navigation-5.9.30.js?v=5.9.76-destination-background-guard-1', 'crumpnav5930'],
    ['/crump-code-5.9.35.js?v=5.9.76-intelligence-architecture-1', 'crumpcode5935'],
    ['/lifecycle-share.js?v=5.9.76-lifecycle-activation-1', 'lifecycleshare'],
    ['/lifecycle-manager.js?v=5.9.76-continuity-action-1', 'lifecyclemanager'],
  ]);

  const scriptPlan = Object.freeze([
    ...workspaceScripts,
    ...enhancementScripts,
    ...finalScripts,
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

  function primeScript(url, key) {
    if (document.querySelector(`script[data-${key}]`) ||
        document.querySelector(`link[data-crump-script-preload="${key}"]`)) return;

    const node = document.createElement('link');
    node.rel = 'preload';
    node.as = 'script';
    node.href = url;
    node.dataset.crumpScriptPreload = key;
    document.head.appendChild(node);
  }

  function primeScripts(entries) {
    entries.forEach(([url, key]) => primeScript(url, key));
  }

  let runtimePromise = null;

  async function boot() {
    document.documentElement.dataset.crumpBodyRuntime = 'loading';
    // Insert every stylesheet in final cascade order before awaiting the network.
    // CSS keeps DOM-order authority while downloading concurrently.
    const stylesReady = Promise.all(
      [...workspaceStyles, ...enhancementStyles].map(([url, key]) => loadStyle(url, key)),
    );
    // Fetch classic scripts in parallel, then preserve the proven execution order below.
    primeScripts(scriptPlan);
    await stylesReady;

    for (const [url, key] of scriptPlan) {
      await loadScript(url, key);
    }

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
