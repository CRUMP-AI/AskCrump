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

  let runtimePromise = null;

  async function boot() {
    document.documentElement.dataset.crumpBodyRuntime = 'loading';
    await Promise.all(workspaceStyles.map(([url,key]) => loadStyle(url,key)));

    await loadStyle('/crump-navigation-5.2.5.css', 'crumpnav525');
    await loadStyle('/crump-product-5.3.css?v=5.9.76-project-workspaces-3', 'crumpproduct53');
    await loadStyle('/crump-product-5.3.1.css', 'crumpproduct531');
    await loadStyle('/crump-polish-5.6.css', 'crumppolish56');
    await loadStyle('/crump-library-5.7.css', 'crumplibrary57');
    await loadStyle('/crump-code-5.9.35.css', 'crumpcode5935');
    await loadStyle('/crump-v1-stability.css', 'crumpv1stability');
    await loadStyle('/crump-navigation-5.9.30.css', 'crumpnav5930');

    for (const [url,key] of workspaceScripts) await loadScript(url,key);
    for (const [url,key] of enhancementScripts) await loadScript(url,key);

    await loadScript('/crump-navigation-5.2.5.js', 'crumpnav525');
    await loadScript('/crump-product-5.3.js?v=5.9.76-project-workspaces-3', 'crumpproduct53');
    await loadScript('/crump-product-5.3.1.js', 'crumpproduct531');
    await loadScript('/crump-subscriptions-5.3.2.js', 'crumpsubscriptions532');
    await loadScript('/crump-polish-5.6.js', 'crumppolish56');
    await loadScript('/crump-library-5.7.js', 'crumplibrary57');
    await loadScript('/crump-navigation-5.9.30.js?v=5.9.76-projects-entry-1', 'crumpnav5930');
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
`;

const runtime = `window.CRUMP_CONFIG = Object.freeze(${JSON.stringify(config, null, 2)});\n${loader}\n`;

await writeFile(new URL('../dist/runtime-body-v1.js', import.meta.url), runtime);
await rm(new URL('../dist/native-entry.js', import.meta.url), { force: true });

console.log('Ask Crump V1 new-body native web bundle created in dist/.');
