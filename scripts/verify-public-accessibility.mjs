import {createReadStream, existsSync, statSync} from 'node:fs';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const axePath = require.resolve('axe-core/axe.min.js');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicRoot = path.join(root, 'public');

const mimeTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.jpeg', 'image/jpeg'],
  ['.jpg', 'image/jpeg'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
  ['.webmanifest', 'application/manifest+json; charset=utf-8'],
  ['.woff2', 'font/woff2'],
]);

const scenarios = Object.freeze([
  {name: 'Ask Crump home', pathname: '/'},
  {name: 'Ask Crump product', pathname: '/ask-crump'},
  {name: 'Projects capability', pathname: '/ai-project-workspace'},
  {name: 'Document capability', pathname: '/ai-document-generator'},
  {name: 'Presentation capability', pathname: '/ai-presentation-maker'},
  {name: 'Resume capability', pathname: '/ai-resume-builder'},
  {name: 'Video capability', pathname: '/ai-video-generator'},
  {name: 'Sign in', pathname: '/app', ready: '#loginForm'},
  {name: 'Create account', pathname: '/app?signup=1', ready: '#registerForm'},
  {
    name: 'Password recovery',
    pathname: '/app',
    ready: '#forgotPasswordForm',
    prepare: async page => {
      await page.locator('#showForgotPasswordLink').click();
    },
  },
  {name: 'Clever Crump company', pathname: '/clever-crump'},
]);

const viewports = Object.freeze([
  {name: 'phone', width: 390, height: 844},
  {name: 'desktop', width: 1440, height: 900},
]);

function resolvePublicFile(rawPathname) {
  const decoded = decodeURIComponent(rawPathname);
  const route = decoded === '/' ? '/ask-crump.html' : decoded;
  const candidates = path.extname(route) ? [route] : [`${route}.html`, route];
  for (const candidate of candidates) {
    const resolved = path.resolve(publicRoot, `.${candidate}`);
    if (!resolved.startsWith(`${publicRoot}${path.sep}`)) continue;
    if (existsSync(resolved) && statSync(resolved).isFile()) return resolved;
  }
  return null;
}

function startServer() {
  const server = createServer((request, response) => {
    const requestUrl = new URL(request.url || '/', 'http://127.0.0.1');
    if (requestUrl.pathname.startsWith('/api/')) {
      response.writeHead(200, {'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store'});
      response.end(JSON.stringify({success: true, authenticated: false}));
      return;
    }
    const file = resolvePublicFile(requestUrl.pathname);
    if (!file) {
      response.writeHead(404, {'content-type': 'text/plain; charset=utf-8'});
      response.end('Not found');
      return;
    }
    response.writeHead(200, {
      'content-type': mimeTypes.get(path.extname(file).toLowerCase()) || 'application/octet-stream',
      'cache-control': 'no-store',
    });
    if (request.method === 'HEAD') response.end();
    else createReadStream(file).pipe(response);
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

function compactViolations(violations) {
  return violations.map(violation => ({
    id: violation.id,
    impact: violation.impact,
    description: violation.description,
    targets: violation.nodes.slice(0, 8).map(node => node.target),
  }));
}

const server = await startServer();
const address = server.address();
if (!address || typeof address === 'string') throw new Error('Accessibility server did not expose a TCP port.');

const requestedBrowserExecutable = process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || process.env.ASK_CRUMP_BROWSER_PATH
  || process.env.CODEX_BROWSER_EXECUTABLE
  || undefined;
const browser = await chromium.launch({headless: true, executablePath: requestedBrowserExecutable});
const failures = [];

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: {width: viewport.width, height: viewport.height},
      reducedMotion: 'reduce',
      serviceWorkers: 'block',
    });
    for (const scenario of scenarios) {
      const page = await context.newPage();
      await page.goto(`http://127.0.0.1:${address.port}${scenario.pathname}`, {
        waitUntil: 'domcontentloaded',
        timeout: 30_000,
      });
      if (scenario.prepare) await scenario.prepare(page);
      if (scenario.ready) {
        await page.locator(scenario.ready).waitFor({state: 'visible', timeout: 10_000});
      }
      await page.addScriptTag({path: axePath});
      const result = await page.evaluate(async () => axe.run(document, {
        runOnly: {
          type: 'tag',
          values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'],
        },
        resultTypes: ['violations'],
      }));
      if (result.violations.length) {
        failures.push({scenario: scenario.name, viewport: viewport.name, violations: compactViolations(result.violations)});
      } else {
        console.log(`PASS ${viewport.name}: ${scenario.name}`);
      }
      await page.close();
    }
    await context.close();
  }
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}

if (failures.length) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}

console.log(`Accessibility matrix passed ${scenarios.length * viewports.length}/${scenarios.length * viewports.length} scenarios.`);
