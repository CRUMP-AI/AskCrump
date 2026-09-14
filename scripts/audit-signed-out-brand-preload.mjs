import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const origin = (process.env.ASKCRUMP_PRODUCTION_ORIGIN || 'https://www.askcrump.com').replace(/\/$/, '');
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const samplesPerVariant = Number(process.env.ASKCRUMP_AUDIT_SAMPLES || 5);
const variants = Object.freeze(['current-retina', 'legacy-full-mark']);

function median(values) {
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
const samples = [];
try {
  for (let round = 0; round < samplesPerVariant; round += 1) {
    for (const variant of variants) {
      const context = await browser.newContext({
        viewport: {width: 390, height: 844},
        serviceWorkers: 'block',
      });
      const page = await context.newPage();
      const errors = [];
      page.on('console', message => {
        if (message.type() === 'error') errors.push(message.text());
      });
      page.on('pageerror', error => errors.push(error.message));
      await page.route(`${origin}/app?**`, async route => {
        const response = await route.fetch();
        let body = await response.text();
        if (variant === 'legacy-full-mark') {
          const before = body;
          body = body.replaceAll('/assets/brand/crump-mark-320.webp', '/assets/brand/crump-mark.webp');
          if (body === before || body.includes('/assets/brand/crump-mark-320.webp')) {
            throw new Error('Legacy full-size comparison transformation did not apply exactly.');
          }
        }
        await route.fulfill({response, body});
      });
      await page.addInitScript(() => {
        window.__askCrumpAuditPerf = {lcp: 0, lcpElement: '', cls: 0};
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) {
            window.__askCrumpAuditPerf.lcp = entry.startTime;
            const element = entry.element;
            window.__askCrumpAuditPerf.lcpElement = element
              ? `${element.tagName}:${(element.textContent || element.getAttribute('alt') || '').trim().slice(0, 80)}`
              : '';
          }
        }).observe({type: 'largest-contentful-paint', buffered: true});
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) {
            if (!entry.hadRecentInput) window.__askCrumpAuditPerf.cls += entry.value;
          }
        }).observe({type: 'layout-shift', buffered: true});
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
      await page.goto(`${origin}/app?release_probe=brand-preload-audit&round=${round + 1}&variant=${variant}`, {
        waitUntil: 'load',
        timeout: 45_000,
      });
      await page.waitForTimeout(2_500);
      const metrics = await page.evaluate(() => {
        const resources = performance.getEntriesByType('resource');
        return {
          fcp: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0,
          load: performance.getEntriesByType('navigation')[0]?.loadEventEnd || 0,
          ...window.__askCrumpAuditPerf,
          brandResources: resources
            .filter(entry => entry.name.includes('/assets/brand/'))
            .map(entry => ({
              path: new URL(entry.name).pathname,
              duration: Math.round(entry.duration),
              transferSize: entry.transferSize,
            })),
          signedOutVisible: getComputedStyle(document.getElementById('authContainer')).display !== 'none',
        };
      });
      if (errors.length || !metrics.signedOutVisible || metrics.cls > 0.01) {
        throw new Error(`${variant} round ${round + 1} failed: ${JSON.stringify({errors, metrics})}`);
      }
      samples.push({round: round + 1, variant, ...metrics});
      await context.close();
    }
  }
} finally {
  await browser.close();
}

const summary = Object.fromEntries(variants.map(variant => {
  const rows = samples.filter(sample => sample.variant === variant);
  return [variant, {
    medianFcp: median(rows.map(row => row.fcp)),
    medianLcp: median(rows.map(row => row.lcp)),
    medianLoad: median(rows.map(row => row.load)),
        markRequests: rows.filter(row => row.brandResources.some(resource => /\/crump-mark(?:-320)?\.webp$/.test(resource.path))).length,
        medianMarkTransfer: median(rows.map(row => row.brandResources.find(resource => /\/crump-mark(?:-320)?\.webp$/.test(resource.path))?.transferSize || 0)),
    lcpElements: [...new Set(rows.map(row => row.lcpElement))],
  }];
}));

console.log(JSON.stringify({origin, samplesPerVariant, summary, samples}, null, 2));
