import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const guidePath = 'public/guides/word-or-pdf-ai-document-output.html';
const migrationPath = 'migrations/20260910095400_release_word_pdf_search_attribution.sql';
const route = '/guides/word-or-pdf-ai-document-output';
const canonical = `https://www.askcrump.com${route}`;
const exactHref = '/ai-document-generator?signup=1&amp;plan=free&amp;acquisition=organic-search&amp;source=workflow-guide&amp;campaign=word-or-pdf-decision&amp;creative=search-article&amp;intent=document';

function fail(message) {
  console.error(`Word/PDF public release invalid: ${message}`);
  process.exit(1);
}
function read(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), 'utf8');
}
function count(source, marker) {
  return source.split(marker).length - 1;
}
function sha256(relativePath) {
  return createHash('sha256')
    .update(fs.readFileSync(path.join(repoRoot, relativePath)))
    .digest('hex')
    .toUpperCase();
}

const guide = read(guidePath);
for (const marker of [
  '<title>Word or PDF? Choose the Right AI Document Output | Ask Crump</title>',
  '<meta name="robots" content="index,follow,max-image-preview:large">',
  `<link rel="canonical" href="${canonical}">`,
  '<h1>Word or PDF? Start with what happens next.</h1>',
  '"datePublished": "2026-08-30"',
  '"dateModified": "2026-09-10"',
  exactHref,
  'Start free with a Word or PDF document',
  'every person, date, figure, threshold, and operating detail are invented',
  'this accepted file is not tagged for accessibility',
  'Export success is not final acceptance',
  'No customer content or testimonial is used',
]) {
  if (!guide.includes(marker)) fail(`guide marker missing: ${marker}`);
}
if (/staged for review|public release held/i.test(guide)) fail('staging language remains');
if (/checkout|stripe|purchase|subscribe|paid plan/i.test(guide)) fail('commerce language entered the guide');
if (count(guide, '<h1>') !== 1 || count(guide, 'class="button primary"') !== 1) {
  fail('guide must retain one H1 and one primary CTA');
}

const sitemap = read('public/sitemap.xml');
if (count(sitemap, `<loc>${canonical}</loc>`) !== 1) fail('sitemap entry count drifted');
if (!read('public/ai-document-generator.html').includes(`href="${route}">Compare Word and PDF output</a>`)) {
  fail('public document page inlink missing');
}
if (!/<meta[^>]+name=["']robots["'][^>]+content=["'][^"']*noindex/i.test(read('public/app.html'))) {
  fail('private app noindex boundary drifted');
}

const expectedAssets = {
  'public/assets/guides/word-or-pdf-guide-hero-1600x1000.png': 'E08EC5FFBA0937B0A377E0618F0631A16B4EECC2ACD79FF34636C323B0BB8713',
  'public/assets/guides/word-or-pdf-og-1200x630.png': 'E80F011EDE33B54404BA44F1F72C46DA140C11F21133081449B8FE1DCC9BFFDC',
  'public/assets/guides/word-or-pdf-word-page-2.png': '4C38D01E3243CEDDBB3B2C991FD301D8591BBA64A38299A8D5D6E0C37038D51D',
  'public/assets/guides/word-or-pdf-pdf-page-2.png': '2A8E161C5AEA004A1C7D7ED0CA41E6D66A5F3A6988BE594CFF2C7A33E58A7570',
};
for (const [relativePath, expected] of Object.entries(expectedAssets)) {
  if (sha256(relativePath) !== expected) fail(`accepted asset drifted: ${relativePath}`);
}

for (const relativePath of ['public/landing.js', 'public/auth-controller.js', 'backend/product_analytics.py']) {
  const contents = read(relativePath);
  if (!contents.includes('word-or-pdf-decision')) fail(`organic campaign missing: ${relativePath}`);
  if (contents.includes('word-or-pdf-social')) fail(`held social campaign registered: ${relativePath}`);
}
const sql = read(migrationPath);
for (const marker of [
  "campaign = 'word-or-pdf-decision'",
  "source = 'organic-search'",
  "placement = 'workflow-guide'",
  "intent = 'document'",
  "creative = 'search-article'",
  'security invoker',
  "set search_path = ''",
  'from public, anon, authenticated',
  'to service_role',
]) {
  if (!sql.includes(marker)) fail(`migration marker missing: ${marker}`);
}
if (/word-or-pdf-social/.test(sql)) fail('held social campaign entered migration');
if (/update\s+public\.product_events|delete\s+from\s+public\.product_events|truncate/i.test(sql)) {
  fail('migration is not forward-only');
}

const js = spawnSync(process.execPath, ['scripts/check-javascript.mjs'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
});
if (js.status !== 0) fail(`JavaScript validation failed: ${String(js.stdout || js.stderr).trim()}`);
for (const marker of ['Validated 10/10 Word/PDF attribution runtime cases.', 'Validated 49 JavaScript files.']) {
  if (!js.stdout.includes(marker)) fail(`JavaScript validation marker missing: ${marker}`);
}

console.log(JSON.stringify({
  object: 'word_pdf_public_release_verification',
  state: 'PUBLIC_ORGANIC_SEARCH_RELEASE_READY',
  canonical,
  exactOrganicTuple: 'organic-search/workflow-guide/word-or-pdf-decision/search-article/document',
  authenticAssets: Object.keys(expectedAssets).length,
  runtimeCases: 10,
  socialDistributionIncluded: false,
  spend: 0,
}, null, 2));
