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

function tags(source, name) {
  return [...source.matchAll(new RegExp(`<${name}\\b[^>]*>`, 'gi'))].map(match => match[0]);
}

function attributes(tag) {
  const result = new Map();
  for (const match of tag.matchAll(/([^\s=/>]+)\s*=\s*(["'])(.*?)\2/g)) {
    result.set(match[1].toLowerCase(), match[3].replaceAll('&amp;', '&'));
  }
  return result;
}

function metaContents(source, attribute, expected) {
  return tags(source, 'meta')
    .map(attributes)
    .filter(values => values.get(attribute) === expected)
    .map(values => values.get('content') || '');
}

function oneValue(values, label, url) {
  if (values.length !== 1 || !String(values[0]).trim()) {
    fail(`${url.href} must expose exactly one non-empty ${label}`);
  }
  return String(values[0]).trim();
}

function elementText(source, name) {
  return [...source.matchAll(new RegExp(`<${name}\\b[^>]*>([\\s\\S]*?)<\\/${name}>`, 'gi'))]
    .map(match => match[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim());
}

function structuredData(source, url) {
  const blocks = [...source.matchAll(
    /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi,
  )];
  if (!blocks.length) fail(`${url.href} is missing JSON-LD structured data`);
  return blocks.map(match => {
    try {
      return JSON.parse(match[1]);
    } catch (_) {
      fail(`${url.href} contains invalid JSON-LD structured data`);
    }
  });
}

async function fetchDirect(url) {
  const request = async target => {
    let lastError;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        const response = await fetch(target, {
          redirect: 'manual',
          signal: AbortSignal.timeout(15_000),
          headers: {'user-agent': 'AskCrump-public-destination-verifier/1.0'},
        });
        if (![408, 429, 500, 502, 503, 504].includes(response.status) || attempt === 3) {
          return response;
        }
        lastError = new Error(`${target.href} returned transient HTTP ${response.status}`);
      } catch (error) {
        lastError = error;
        if (attempt === 3) throw error;
      }
      await new Promise(resolve => setTimeout(resolve, attempt * 250));
    }
    throw lastError || new Error(`${target.href} could not be reached`);
  };
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

const seenTitles = new Map();
const seenDescriptions = new Map();
const socialImages = new Map();
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

  const language = oneValue(
    tags(result.text, 'html').map(attributes).map(values => values.get('lang') || ''),
    'HTML language',
    url,
  );
  if (language.toLowerCase() !== 'en') fail(`${url.href} declares unexpected language ${language}`);

  const title = oneValue(elementText(result.text, 'title'), 'document title', url);
  const description = oneValue(metaContents(result.text, 'name', 'description'), 'meta description', url);
  const headings = elementText(result.text, 'h1');
  oneValue(headings, 'H1 heading', url);
  const viewport = oneValue(metaContents(result.text, 'name', 'viewport'), 'viewport declaration', url);
  if (!viewport.toLowerCase().includes('width=device-width')) {
    fail(`${url.href} has a non-responsive viewport declaration`);
  }
  const robotsValue = oneValue(metaContents(result.text, 'name', 'robots'), 'robots directive', url)
    .toLowerCase();
  if (!robotsValue.includes('index') || !robotsValue.includes('follow')
      || robotsValue.includes('noindex') || robotsValue.includes('nofollow')) {
    fail(`${url.href} is not explicitly indexable and followable`);
  }
  if (seenTitles.has(title)) fail(`${url.href} duplicates the title from ${seenTitles.get(title)}`);
  if (seenDescriptions.has(description)) {
    fail(`${url.href} duplicates the description from ${seenDescriptions.get(description)}`);
  }
  seenTitles.set(title, url.href);
  seenDescriptions.set(description, url.href);

  if (url.pathname !== '/legal') {
    const structured = structuredData(result.text, url);
    if (!JSON.stringify(structured).includes(JSON.stringify(url.href))) {
      fail(`${url.href} structured data does not reference its canonical URL`);
    }
    oneValue(metaContents(result.text, 'property', 'og:title'), 'Open Graph title', url);
    oneValue(metaContents(result.text, 'property', 'og:description'), 'Open Graph description', url);
    const openGraphUrl = oneValue(metaContents(result.text, 'property', 'og:url'), 'Open Graph URL', url);
    if (new URL(openGraphUrl, origin).href !== url.href) {
      fail(`${url.href} declares Open Graph URL ${openGraphUrl}`);
    }
    const openGraphImage = new URL(
      oneValue(metaContents(result.text, 'property', 'og:image'), 'Open Graph image', url),
      origin,
    );
    if (openGraphImage.protocol !== 'https:' || !allowedHosts.has(openGraphImage.hostname)) {
      fail(`${url.href} declares an invalid Open Graph image origin`);
    }
    const twitterCard = oneValue(metaContents(result.text, 'name', 'twitter:card'), 'Twitter card', url);
    if (twitterCard !== 'summary_large_image') {
      fail(`${url.href} declares unexpected Twitter card ${twitterCard}`);
    }
    const twitterImage = new URL(
      oneValue(metaContents(result.text, 'name', 'twitter:image'), 'Twitter image', url),
      origin,
    );
    if (twitterImage.href !== openGraphImage.href) {
      fail(`${url.href} uses different Open Graph and Twitter images`);
    }
    socialImages.set(openGraphImage.href, url.href);
  }
}

await runBounded([...socialImages.keys()].map(value => new URL(value)), async url => {
  let response;
  try {
    response = await fetchDirect(url);
  } catch (error) {
    const message = String(error?.message || error).replace(/^Live public destination verification failed:\s*/, '');
    fail(`${message}; social preview for ${socialImages.get(url.href)}`);
  }
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.toLowerCase().startsWith('image/')) {
    fail(`${url.href} is not served as an image for ${socialImages.get(url.href)}`);
  }
});

const robots = bodies.get(new URL('/robots.txt', origin).href)?.text || '';
if (!robots.includes(`Sitemap: ${new URL('/sitemap.xml', origin).href}`)) {
  fail('robots.txt does not advertise the canonical sitemap');
}

console.log(
  `Live public destination proof passed: ${anchors.size} unique first-party anchor destinations, `
  + `${sitemapUrls.length} canonical sitemap pages, ${requested.size} HTTP 200 destinations, and `
  + `${expectedCompatibilityRedirects.size} exact native-compatibility redirects; `
  + `${socialImages.size} social-preview images and every sitemap page's title, description, H1, `
  + 'indexability, canonical, structured data, and responsive viewport are valid.',
);
