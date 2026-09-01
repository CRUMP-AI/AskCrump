import { copyFile, cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { loadRevenueCatCatalog } from './revenuecat-catalog.mjs';

const outDir = new URL('../dist/', import.meta.url);
const publicDir = new URL('../public/', import.meta.url);

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });
await cp(publicDir, outDir, { recursive: true });
await copyFile(new URL('../public/app.html', import.meta.url), new URL('../dist/index.html', import.meta.url));

await build({
  entryPoints: [fileURLToPath(new URL('../public/native-entry.js', import.meta.url))],
  bundle: true,
  minify: true,
  format: 'iife',
  platform: 'browser',
  target: ['safari16.4', 'chrome120'],
  outfile: fileURLToPath(new URL('../dist/native-runtime.js', import.meta.url)),
  legalComments: 'none',
});

const revenueCatCatalog = await loadRevenueCatCatalog();
const config = {
  apiBase: process.env.CRUMP_API_BASE || 'https://www.askcrump.com',
  revenueCatAppleApiKey: process.env.REVENUECAT_IOS_PUBLIC_SDK_KEY || '',
  revenueCatGoogleApiKey: process.env.REVENUECAT_ANDROID_PUBLIC_SDK_KEY || '',
  revenueCatEntitlement: revenueCatCatalog.entitlementId,
  revenueCatProfessionalProductId: revenueCatCatalog.subscriptions.professional,
  revenueCatEnterpriseProductId: revenueCatCatalog.subscriptions.enterprise,
  revenueCatCredits50ProductId: revenueCatCatalog.credits.credits_50,
  revenueCatCredits150ProductId: revenueCatCatalog.credits.credits_150,
  revenueCatCredits400ProductId: revenueCatCatalog.credits.credits_400,
  webProfessionalPriceLabel: process.env.WEB_PROFESSIONAL_PRICE_LABEL || '$20/month',
  webEnterprisePriceLabel: process.env.WEB_ENTERPRISE_PRICE_LABEL || '$50/month',
  webCredits50PriceLabel: process.env.WEB_CREDITS_50_PRICE_LABEL || '$4.99',
  webCredits150PriceLabel: process.env.WEB_CREDITS_150_PRICE_LABEL || '$9.99',
  webCredits400PriceLabel: process.env.WEB_CREDITS_400_PRICE_LABEL || '$19.99',
};

const loader = String.raw`
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
    ['/crump-product-5.3.css?v=5.9.76-visual-media-reliability-2', 'crumpproduct53'],
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
    ['/crump-v1-body.js?v=5.9.76-desktop-chats-default-1', 'crumpbodyv1'],
    ['/crump-v1-stability.js?v=5.9.76-intelligence-architecture-1', 'crumpv1stability'],
  ]);

  const finalScripts = Object.freeze([
    ['/crump-navigation-5.2.5.js?v=5.9.76-chats-language-1', 'crumpnav525'],
    ['/crump-product-5.3.js?v=5.9.76-visual-media-reliability-2', 'crumpproduct53'],
    ['/crump-product-5.3.1.js?v=5.9.76-core-reliability-1', 'crumpproduct531'],
    ['/crump-subscriptions-5.3.2.js?v=5.9.76-commerce-recovery-1', 'crumpsubscriptions532'],
    ['/crump-polish-5.6.js?v=5.9.76-video-destination-1', 'crumppolish56'],
    ['/crump-library-5.7.js?v=5.9.76-demand-hydration-1', 'crumplibrary57'],
    ['/crump-navigation-5.9.30.js?v=5.9.76-create-destination-handoff-1', 'crumpnav5930'],
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
    const keyed = document.querySelector('link[data-' + key + ']');
    if (keyed) return Promise.resolve();

    const existing = document.querySelector('link[href="' + url + '"]');
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
      node.addEventListener('load', resolve, {once:true});
      node.addEventListener('error', resolve, {once:true});
      document.head.appendChild(node);
    });
  }

  function loadScript(url, key) {
    if (document.querySelector('script[data-' + key + ']')) return Promise.resolve();
    return new Promise(resolve => {
      const node = document.createElement('script');
      node.src = url;
      node.async = false;
      node.dataset[key] = 'true';
      node.addEventListener('load', resolve, {once:true});
      node.addEventListener('error', resolve, {once:true});
      document.head.appendChild(node);
    });
  }

  function primeScript(url, key) {
    if (document.querySelector('script[data-' + key + ']') ||
        document.querySelector('link[data-crump-script-preload="' + key + '"]')) return;

    const node = document.createElement('link');
    node.rel = 'preload';
    node.as = 'script';
    node.href = url;
    node.dataset.crumpScriptPreload = key;
    document.head.appendChild(node);
  }

  function primeScripts(entries) {
    entries.forEach(([url,key]) => primeScript(url,key));
  }

  let runtimePromise = null;

  async function boot() {
    document.documentElement.dataset.crumpBodyRuntime = 'loading';
    const stylesReady = Promise.all(
      [...workspaceStyles, ...enhancementStyles].map(([url,key]) => loadStyle(url,key)),
    );
    primeScripts(scriptPlan);
    await stylesReady;

    for (const [url,key] of scriptPlan) await loadScript(url,key);

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
`;

const runtime = `window.CRUMP_CONFIG = Object.freeze(${JSON.stringify(config, null, 2)});\n${loader}\n`;

await writeFile(new URL('../dist/runtime-body-v1.js', import.meta.url), runtime);
await rm(new URL('../dist/native-entry.js', import.meta.url), { force: true });

console.log('Ask Crump V1 new-body native web bundle created in dist/.');
