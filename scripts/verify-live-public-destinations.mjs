import {readFileSync, readdirSync, statSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const publicRoot = path.join(repoRoot, 'public');
const configuredOrigin = process.env.ASKCRUMP_PUBLIC_ORIGIN || 'https://www.askcrump.com';
const origin = new URL(configuredOrigin);
const allowedHosts = new Set([
  'askcrump.com',
  'www.askcrump.com',
  'clevercrump.com',
  'www.clevercrump.com',
]);
const expectedCompatibilityRedirects = new Map([
  [new URL('/legal.html', origin).href, new URL('/legal', origin).href],
  [new URL('/delete-account.html', origin).href, new URL('/delete-account', origin).href],
]);

function fail(message) {
  throw new Error(`Live public destination verification failed: ${message}`);
}

function publicMarkupFiles(directory) {
  return readdirSync(directory)
    .map(name => path.join(directory, name))
    .flatMap(candidate => {
      if (statSync(candidate).isDirectory()) return publicMarkupFiles(candidate);
      return candidate.endsWith('.html') || candidate.endsWith('.js') ? [candidate] : [];
    })
    .sort();
}

function sourceRoute(file) {
  const relative = path.relative(publicRoot, file).replaceAll('\\', '/');
  if (relative === 'ask-crump.html' || relative === 'clever-crump.html') return '/';
  return `/${relative.replace(/\.html$/i, '')}`;
}

function sourceOrigin(file) {
  return path.basename(file).toLowerCase() === 'clever-crump.html'
    ? new URL('https://www.clevercrump.com')
    : origin;
}

function anchorDestinations() {
  const destinations = new Map();
  const anchorPattern = /<a\b[^>]*\bhref\s*=\s*(["'])(.*?)\1/gi;
  for (const file of publicMarkupFiles(publicRoot)) {
    const source = readFileSync(file, 'utf8');
    const sourceUrl = new URL(sourceRoute(file), sourceOrigin(file));
    for (const match of source.matchAll(anchorPattern)) {
      const raw = String(match[2] || '').trim().replaceAll('&amp;', '&');
      if (!raw || raw.includes('${') || raw.startsWith(('#', 'mailto:', 'tel:', 'javascript:', 'data:', 'blob:'))) continue;
      let destination;
      try {
        destination = new URL(raw, sourceUrl);
      } catch {
        fail(`${path.relative(repoRoot, file)} contains an invalid href: ${raw}`);
      }
      if (!allowedHosts.has(destination.hostname.toLowerCase())) continue;
      if (destination.pathname.startsWith('/api/')) continue;
      destination.hash = '';
      const key = destination.href;
      const sources = destinations.get(key) || [];
      sources.push(path.relative(repoRoot, file).replaceAll('\\', '/'));
      destinations.set(key, sources);
    }
  }
  return destinations;
}

function sitemapDestinations() {
  const source = readFileSync(path.join(publicRoot, 'sitemap.xml'), 'utf8');
  const urls = [...source.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => new URL(match[1].trim()));
  if (!urls.length) fail('sitemap.xml contains no public URLs');
  for (const url of urls) {
    if (url.origin !== origin.origin) fail(`sitemap URL leaves the canonical origin: ${url.href}`);
  }
  return urls;
}

async function fetchDirect(url) {
  const request = target => fetch(target, {
    redirect: 'manual',
    signal: AbortSignal.timeout(15_000),
    headers: {'user-agent': 'AskCrump-public-destination-verifier/1.0'},
  });
  let response = await request(url);
  if (response.status >= 300 && response.status < 400) {
    const location = response.headers.get('location');
    if (!location) fail(`${url.href} redirects without a Location header`);
    const redirected = new URL(location, url);
    const expected = expectedCompatibilityRedirects.get(url.href);
    if (!expected || redirected.href !== expected) {
      fail(`${url.href} unexpectedly redirects to ${redirected.href}`);
    }
    response = await request(redirected);
    if (response.status >= 300 && response.status < 400) {
      fail(`${url.href} enters another redirect at ${redirected.href}`);
    }
  }
  if (response.status !== 200) fail(`${url.href} returned HTTP ${response.status}`);
  return response;
}

async function runBounded(items, worker, concurrency = 6) {
  const pending = [...items];
  const workers = Array.from({length: Math.min(concurrency, pending.length)}, async () => {
    while (pending.length) await worker(pending.shift());
  });
  await Promise.all(workers);
}

const anchors = anchorDestinations();
const sitemapUrls = sitemapDestinations();
const requested = new Map(anchors);
for (const url of sitemapUrls) requested.set(url.href, requested.get(url.href) || ['public/sitemap.xml']);
requested.set(new URL('/robots.txt', origin).href, ['public/robots.txt']);
requested.set(new URL('/sitemap.xml', origin).href, ['public/sitemap.xml']);

const bodies = new Map();
await runBounded([...requested.keys()].map(value => new URL(value)), async url => {
  let response;
  try {
    response = await fetchDirect(url);
  } catch (error) {
    const sources = (requested.get(url.href) || []).join(', ');
    const message = String(error?.message || error).replace(/^Live public destination verification failed:\s*/, '');
    fail(`${message}; referenced by ${sources}`);
  }
  bodies.set(url.href, {
    contentType: response.headers.get('content-type') || '',
    text: await response.text(),
  });
});

for (const url of sitemapUrls) {
  const result = bodies.get(url.href);
  if (!result?.contentType.toLowerCase().includes('text/html')) {
    fail(`${url.href} did not return HTML`);
  }
  const match = result.text.match(/<link\b[^>]*\brel=["']canonical["'][^>]*\bhref=["']([^"']+)["']/i)
    || result.text.match(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\brel=["']canonical["']/i);
  if (!match) fail(`${url.href} is missing a canonical link`);
  if (new URL(match[1], origin).href !== url.href) {
    fail(`${url.href} declares canonical ${match[1]}`);
  }
}

const robots = bodies.get(new URL('/robots.txt', origin).href)?.text || '';
if (!robots.includes(`Sitemap: ${new URL('/sitemap.xml', origin).href}`)) {
  fail('robots.txt does not advertise the canonical sitemap');
}

console.log(
  `Live public destination proof passed: ${anchors.size} unique first-party anchor destinations, `
  + `${sitemapUrls.length} canonical sitemap pages, ${requested.size} HTTP 200 destinations, and `
  + `${expectedCompatibilityRedirects.size} exact native-compatibility redirects.`,
);
