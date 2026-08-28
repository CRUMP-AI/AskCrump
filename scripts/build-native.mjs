import { copyFile, cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

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

const config = {
  apiBase: process.env.CRUMP_API_BASE || 'https://www.askcrump.com',
  revenueCatAppleApiKey: process.env.REVENUECAT_IOS_PUBLIC_SDK_KEY || '',
  revenueCatGoogleApiKey: process.env.REVENUECAT_ANDROID_PUBLIC_SDK_KEY || '',
  revenueCatEntitlement: process.env.REVENUECAT_ENTITLEMENT || 'professional',
  revenueCatProfessionalProductId: process.env.REVENUECAT_PROFESSIONAL_PRODUCT_ID || 'askcrump_professional_monthly',
  revenueCatEnterpriseProductId: process.env.REVENUECAT_ENTERPRISE_PRODUCT_ID || 'askcrump_enterprise_monthly',
  revenueCatCredits50ProductId: process.env.REVENUECAT_CREDITS_50_PRODUCT_ID || 'askcrump_credits_50',
  revenueCatCredits150ProductId: process.env.REVENUECAT_CREDITS_150_PRODUCT_ID || 'askcrump_credits_150',
  revenueCatCredits400ProductId: process.env.REVENUECAT_CREDITS_400_PRODUCT_ID || 'askcrump_credits_400',
  webProfessionalPriceLabel: process.env.WEB_PROFESSIONAL_PRICE_LABEL || '$20/month',
  webEnterprisePriceLabel: process.env.WEB_ENTERPRISE_PRICE_LABEL || '$50/month',
  webCredits50PriceLabel: process.env.WEB_CREDITS_50_PRICE_LABEL || '$4.99',
  webCredits150PriceLabel: process.env.WEB_CREDITS_150_PRICE_LABEL || '$9.99',
  webCredits400PriceLabel: process.env.WEB_CREDITS_400_PRICE_LABEL || '$19.99',
};

const loader = String.raw`
(() => {
  'use strict';

  const styles = Object.freeze([
    ['/crump-4.3.css', 'crump43'],
    ['/crump-4.4.css', 'crump44'],
    ['/crump-5.0.css', 'crump50'],
    ['/crump-billing-5.1.css', 'billing51'],
    ['/crump-5.2.css', 'crump52'],
    ['/crump-5.2.2.css', 'crump522'],
    ['/crump-v1-body.css?v=5.9.64', 'crumpbodyv1'],
    ['/crump-v1-stability.css', 'crumpv1stability'],
  ]);

  const scripts = Object.freeze([
    ['/crump-4.3.js?v=5.9.64', 'crump43'],
    ['/crump-4.4.js', 'crump44'],
    ['/crump-5.0.js?v=5.9.64', 'crump50'],
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

  async function boot() {
    await Promise.all(styles.map(([url,key]) => loadStyle(url,key)));

    await loadStyle('/crump-navigation-5.2.5.css', 'crumpnav525');
    await loadStyle('/crump-product-5.3.css', 'crumpproduct53');
    await loadStyle('/crump-product-5.3.1.css', 'crumpproduct531');
    await loadStyle('/crump-polish-5.6.css', 'crumppolish56');
    await loadStyle('/crump-library-5.7.css', 'crumplibrary57');
    await loadStyle('/crump-code-5.9.35.css', 'crumpcode5935');
    await loadStyle('/crump-navigation-5.9.30.css', 'crumpnav5930');

    for (const [url,key] of scripts) await loadScript(url,key);

    await loadScript('/crump-navigation-5.2.5.js', 'crumpnav525');
    await loadScript('/crump-product-5.3.js', 'crumpproduct53');
    await loadScript('/crump-product-5.3.1.js', 'crumpproduct531');
    await loadScript('/crump-subscriptions-5.3.2.js', 'crumpsubscriptions532');
    await loadScript('/crump-polish-5.6.js', 'crumppolish56');
    await loadScript('/crump-library-5.7.js', 'crumplibrary57');
    await loadScript('/crump-navigation-5.9.30.js', 'crumpnav5930');
    await loadScript('/crump-code-5.9.35.js', 'crumpcode5935');

    document.documentElement.dataset.crumpBodyRuntime = 'ready';
  }

  if (document.readyState === 'complete') void boot();
  else window.addEventListener('load', () => { void boot(); }, {once:true});
})();
`;

const runtime = `window.CRUMP_CONFIG = Object.freeze(${JSON.stringify(config, null, 2)});\n${loader}\n`;

await writeFile(new URL('../dist/runtime-body-v1.js', import.meta.url), runtime);
await rm(new URL('../dist/native-entry.js', import.meta.url), { force: true });

console.log('Ask Crump V1 new-body native web bundle created in dist/.');
