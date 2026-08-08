import { copyFile, cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { build } from 'esbuild';

const outDir = new URL('../dist/', import.meta.url);
const publicDir = new URL('../public/', import.meta.url);

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });
await cp(publicDir, outDir, { recursive: true });
await copyFile(new URL('../public/app.html', import.meta.url), new URL('../dist/index.html', import.meta.url));

await build({
  entryPoints: [new URL('../public/native-entry.js', import.meta.url).pathname],
  bundle: true,
  minify: true,
  format: 'iife',
  platform: 'browser',
  target: ['safari16.4', 'chrome120'],
  outfile: new URL('../dist/native-runtime.js', import.meta.url).pathname,
  legalComments: 'none',
});

const config = {
  apiBase: process.env.CRUMP_API_BASE || 'https://askcrump.com',
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

const loaders = String.raw`
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
    ['script', '/crump-billing-5.1.js', 'billing51'],
    ['style', '/crump-5.2.css', 'crump52'],
    ['script', '/crump-5.2.js', 'crump52'],
    ['style', '/crump-5.2.2.css', 'crump522'],
    ['script', '/crump-5.2.2.js', 'crump522'],
    ['style', '/crump-v1.css', 'crumpv1'],
    ['script', '/crump-v1.js', 'crumpv1'],
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

  async function bootLayers() {
    const styles = assets.filter(([kind]) => kind === 'style');
    const scripts = assets.filter(([kind]) => kind === 'script');

    await Promise.all(styles.map(([, url, key]) => loadStyle(url, key)));

    for (const [, url, key] of scripts) {
      await loadScript(url, key);
    }

    document.documentElement.dataset.crumpV1Runtime = 'ready';
  }

  if (document.readyState === 'complete') void bootLayers();
  else window.addEventListener('load', () => { void bootLayers(); }, {once:true});
})();
`;

const runtime = `window.CRUMP_CONFIG = Object.freeze(${JSON.stringify(config, null, 2)});\n${loaders}\n`;

await writeFile(new URL('../dist/runtime-config-v1.js', import.meta.url), runtime);
await writeFile(new URL('../dist/runtime-config.js', import.meta.url), runtime);
await rm(new URL('../dist/native-entry.js', import.meta.url), { force: true });

console.log('Ask Crump V1 native web bundle created in dist/.');
