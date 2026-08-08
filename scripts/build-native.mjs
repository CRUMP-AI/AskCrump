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

const loader = String.raw`
(() => {
  'use strict';

  const styles = Object.freeze([
    ['/crump-4.4.css', 'crump44'],
    ['/crump-5.0.css', 'crump50'],
    ['/crump-billing-5.1.css', 'billing51'],
    ['/crump-5.2.css', 'crump52'],
    ['/crump-5.2.2.css', 'crump522'],
    ['/crump-v1-body.css', 'crumpbodyv1'],
  ]);

  const scripts = Object.freeze([
    ['/crump-4.4.js', 'crump44'],
    ['/crump-5.0.js', 'crump50'],
    ['/crump-billing-5.1.js', 'billing51'],
    ['/crump-5.2.js', 'crump52'],
    ['/crump-5.2.2.js', 'crump522'],
    ['/crump-v1-body.js', 'crumpbodyv1'],
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
    for (const [url,key] of scripts) await loadScript(url,key);
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
