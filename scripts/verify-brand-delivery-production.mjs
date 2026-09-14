import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const origin = (process.env.ASKCRUMP_PRODUCTION_ORIGIN || 'https://www.askcrump.com').replace(/\/$/, '');
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const assets = Object.freeze([
  {url: '/assets/brand/crump-mark.webp', file: 'public/assets/brand/crump-mark.webp'},
  {url: '/assets/brand/crump-shell-lockup-light.webp', file: 'public/assets/brand/crump-shell-lockup-light.webp'},
]);

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

for (const asset of assets) {
  const [local, response] = await Promise.all([
    readFile(path.join(repoRoot, asset.file)),
    fetch(`${origin}${asset.url}`, {cache: 'no-store', signal: AbortSignal.timeout(15_000)}),
  ]);
  if (!response.ok) throw new Error(`${asset.url} returned HTTP ${response.status}.`);
  const type = response.headers.get('content-type') || '';
  if (!type.toLowerCase().startsWith('image/webp')) {
    throw new Error(`${asset.url} returned ${type || 'no content type'} instead of image/webp.`);
  }
  const remote = Buffer.from(await response.arrayBuffer());
  if (sha256(remote) !== sha256(local)) throw new Error(`${asset.url} does not match the reviewed file.`);
}

const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
const runs = [];
try {
  for (let index = 0; index < 3; index += 1) {
    const context = await browser.newContext({
      viewport: {width: 390, height: 844},
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    const errors = [];
    const brandResponses = [];
    const brandRequests = [];
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.url().includes('/assets/brand/')) brandRequests.push(request.url());
    });
    page.on('response', response => {
      if (response.url().includes('/assets/brand/')) {
        brandResponses.push({
          url: response.url(),
          status: response.status(),
          type: response.headers()['content-type'] || '',
        });
      }
    });

    await page.addInitScript(() => {
      window.__askCrumpBrandPerf = {lcp: 0, cls: 0, longTasks: 0};
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) window.__askCrumpBrandPerf.lcp = entry.startTime;
      }).observe({type: 'largest-contentful-paint', buffered: true});
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) window.__askCrumpBrandPerf.cls += entry.value;
        }
      }).observe({type: 'layout-shift', buffered: true});
      new PerformanceObserver(list => {
        window.__askCrumpBrandPerf.longTasks += list.getEntries().length;
      }).observe({type: 'longtask', buffered: true});
    });

    const session = await context.newCDPSession(page);
    await session.send('Network.enable');
    await session.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 150,
      downloadThroughput: 200_000,
      uploadThroughput: 93_750,
      connectionType: 'cellular4g',
    });
    await session.send('Emulation.setCPUThrottlingRate', {rate: 4});

    await page.goto(`${origin}/app?release_probe=brand-delivery-1&run=${index + 1}`, {
      waitUntil: 'load',
      timeout: 45_000,
    });
    await page.waitForTimeout(3_000);
    const metrics = await page.evaluate(() => ({
      fcp: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0,
      load: performance.getEntriesByType('navigation')[0]?.loadEventEnd || 0,
      ...window.__askCrumpBrandPerf,
      decodedBrandImages: [...document.querySelectorAll('img[src$=".webp"]')]
        .filter(image => image.complete && image.naturalWidth > 0).length,
    }));

    const uniqueRequests = [...new Set(brandRequests)];
    const pngRequests = uniqueRequests.filter(url => /crump-(?:mark|shell-lockup-light)\.png(?:\?|$)/.test(url));
    const failedWebp = brandResponses.filter(response =>
      response.url.endsWith('.webp') &&
      (response.status !== 200 || !response.type.toLowerCase().startsWith('image/webp')),
    );
    if (errors.length || pngRequests.length || failedWebp.length || metrics.decodedBrandImages < 2 || metrics.cls > 0.01) {
      throw new Error(`Production brand run ${index + 1} failed: ${JSON.stringify({errors, pngRequests, failedWebp, metrics})}`);
    }
    runs.push({run: index + 1, metrics, brandRequests: uniqueRequests});
    await context.close();
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify({origin, assets: assets.map(asset => asset.url), runs}, null, 2));
