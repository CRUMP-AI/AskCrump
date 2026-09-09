import {createHash} from 'node:crypto';
import {execFileSync, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const productBase = '2fbfc5e2844c671453b5f90ca98bb4241c54daa2';
const branchName = 'candidate/word-pdf-current-20260909';
const guidePath = 'public/guides/word-or-pdf-ai-document-output.html';
const stagingSqlPath = 'staging/add_word_pdf_guide_attribution.sql';
const publicDescription = 'See a real Ask Crump Word and PDF output pair. Learn when to keep an editable DOCX, deliver a fixed-layout PDF, and use a seven-point handoff review.';
const bundledGit = 'C:\\Users\\gcrum\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\native\\git\\cmd\\git.exe';
const gitExecutable = fs.existsSync(bundledGit) ? bundledGit : 'git';
const expectedChanged = [
  'backend/product_analytics.py',
  'public/assets/guides/word-or-pdf-guide-hero-1600x1000.png',
  'public/assets/guides/word-or-pdf-og-1200x630.png',
  'public/assets/guides/word-or-pdf-pdf-page-2.png',
  'public/assets/guides/word-or-pdf-word-page-2.png',
  guidePath,
  'public/guide.css',
  'public/auth-controller.js',
  'public/landing.js',
  'scripts/check-javascript.mjs',
  'scripts/verify-word-pdf-guide-candidate.mjs',
  'scripts/verify-word-pdf-guide-render.cjs',
  stagingSqlPath,
  'tests/test_attribution_measurement.py',
  'tests/test_search_guides.py',
].sort();

function fail(message) {
  console.error(`Word/PDF current candidate invalid: ${message}`);
  process.exit(1);
}

function git(args) {
  return execFileSync(gitExecutable, args, {
    cwd: repoRoot,
    encoding: 'utf8',
    windowsHide: true,
  }).trim();
}

function normalizePath(value) {
  return String(value || '').replaceAll('\\', '/');
}

function sha256(relativePath) {
  return createHash('sha256')
    .update(fs.readFileSync(path.join(repoRoot, relativePath)))
    .digest('hex');
}

function count(source, marker) {
  return source.split(marker).length - 1;
}

function htmlFiles(root) {
  const result = [];
  for (const entry of fs.readdirSync(root, {withFileTypes: true})) {
    const absolute = path.join(root, entry.name);
    if (entry.isDirectory()) result.push(...htmlFiles(absolute));
    else if (entry.isFile() && entry.name.endsWith('.html')) result.push(absolute);
  }
  return result;
}

if (git(['branch', '--show-current']) !== branchName) fail('branch identity drifted');
if (git(['status', '--porcelain=v1', '-uall'])) fail('candidate worktree is not clean');
if (git(['branch', '-r', '--contains', 'HEAD'])) fail('candidate HEAD is already published remotely');
const distance = git(['rev-list', '--left-right', '--count', `${productBase}...HEAD`]).split(/\s+/);
if (distance[0] !== '0' || distance[1] !== '2') fail(`candidate ancestry drifted: ${distance.join('/')}`);
const changed = git(['diff', '--name-only', `${productBase}...HEAD`]).split(/\r?\n/).filter(Boolean).map(normalizePath).sort();
if (JSON.stringify(changed) !== JSON.stringify(expectedChanged)) {
  fail(`exact file boundary drifted: ${changed.join(', ')}`);
}
if (changed.some(relativePath => relativePath.startsWith('migrations/'))) {
  fail('candidate contains an applyable migration');
}
if (git(['diff', '--check', `${productBase}...HEAD`])) fail('diff integrity failed');

const guide = fs.readFileSync(path.join(repoRoot, guidePath), 'utf8');
for (const marker of [
  '<title>Word or PDF? Choose the Right AI Document Output | Ask Crump</title>',
  `<meta name="description" content="${publicDescription}">`,
  '<h1>Word or PDF? Start with what happens next.</h1>',
  '<link rel="canonical" href="https://www.askcrump.com/guides/word-or-pdf-ai-document-output">',
  '<meta name="robots" content="noindex,nofollow">',
  'every person, date, figure, threshold, and operating detail are invented',
  'this accepted file is not tagged for accessibility',
  'Export success is not final acceptance',
  'No customer content or testimonial is used',
]) {
  if (!guide.includes(marker)) fail(`guide marker is missing: ${marker}`);
}
if (count(guide, publicDescription) !== 2) fail('public description is not exact in meta and JSON-LD');
if (count(guide, '<h1>') !== 1 || count(guide, 'class="button primary"') !== 1) {
  fail('guide must retain one H1 and one primary CTA');
}
const cta = 'href="/ai-document-generator?acquisition=organic-search&amp;source=workflow-guide&amp;campaign=word-or-pdf-decision&amp;creative=search-article"';
if (!guide.includes(cta)) fail('exact search CTA tuple drifted');
for (const forbidden of [
  'datePublished', 'dateModified', 'article:published_time', 'article:modified_time',
  'FAQPage', '"@type": "HowTo"', '"@type": "Review"', 'aggregateRating',
]) {
  if (guide.includes(forbidden)) fail(`staged guide contains forbidden schema marker: ${forbidden}`);
}

const route = '/guides/word-or-pdf-ai-document-output';
const sitemap = fs.readFileSync(path.join(repoRoot, 'public', 'sitemap.xml'), 'utf8');
if (sitemap.includes(route)) fail('held guide entered sitemap');
for (const absolutePath of htmlFiles(path.join(repoRoot, 'public'))) {
  if (normalizePath(path.relative(repoRoot, absolutePath)) === guidePath) continue;
  if (fs.readFileSync(absolutePath, 'utf8').includes(`href="${route}"`)) {
    fail(`held guide entered public discovery at ${normalizePath(path.relative(repoRoot, absolutePath))}`);
  }
}

const expectedAssets = {
  'public/assets/guides/word-or-pdf-guide-hero-1600x1000.png': 'e08ec5ffba0937b0a377e0618f0631a16b4eecc2acd79ff34636c323b0bb8713',
  'public/assets/guides/word-or-pdf-og-1200x630.png': 'e80f011ede33b54404ba44f1f72c46da140c11f21133081449b8fe1dcc9bffdc',
  'public/assets/guides/word-or-pdf-word-page-2.png': '4c38d01e3243ceddbb3b2c991fd301d8591bba64a38299a8d5d6e0c37038d51d',
  'public/assets/guides/word-or-pdf-pdf-page-2.png': '2a8e161c5aea004a1c7d7ed0ca41e6d66a5f3a6988be594cff2c7a33e58a7570',
};
for (const [relativePath, expected] of Object.entries(expectedAssets)) {
  if (sha256(relativePath) !== expected) fail(`accepted authentic asset drifted: ${relativePath}`);
}

const landing = fs.readFileSync(path.join(repoRoot, 'public', 'landing.js'), 'utf8');
const auth = fs.readFileSync(path.join(repoRoot, 'public', 'auth-controller.js'), 'utf8');
const backend = fs.readFileSync(path.join(repoRoot, 'backend', 'product_analytics.py'), 'utf8');
const sql = fs.readFileSync(path.join(repoRoot, stagingSqlPath), 'utf8');
for (const source of [landing, auth]) {
  for (const marker of [
    "'word-or-pdf-decision': {",
    "'organic-search|workflow-guide|search-article'",
    "'word-or-pdf-social': {",
    "'facebook|organic-social|word-pdf-feed'",
    "'facebook|organic-social|word-pdf-story'",
    "'instagram|organic-social|word-pdf-feed'",
    "'instagram|organic-social|word-pdf-story'",
    'const attribution = stored ? normalizeAttribution(stored) : candidate',
  ]) {
    if (!source.includes(marker)) fail(`JavaScript registry marker is missing: ${marker}`);
  }
}
for (const marker of [
  '"word-or-pdf-decision": {',
  '("organic-search", "workflow-guide", "search-article")',
  '"word-or-pdf-social": {',
  '("facebook", "organic-social", "word-pdf-feed")',
  '("facebook", "organic-social", "word-pdf-story")',
  '("instagram", "organic-social", "word-pdf-feed")',
  '("instagram", "organic-social", "word-pdf-story")',
]) {
  if (!backend.includes(marker)) fail(`Python registry marker is missing: ${marker}`);
}
for (const marker of [
  '20260909165000',
  'drop constraint if exists product_events_campaign_check',
  'drop constraint if exists product_events_creative_check',
  'drop constraint if exists product_events_campaign_registry_check',
  "campaign = 'word-or-pdf-decision'",
  "campaign = 'word-or-pdf-social'",
  "campaign = 'draft-to-clearer'",
  "campaign = 'research-to-decision'",
  "creative = 'word-pdf-feed'",
  "creative = 'word-pdf-story'",
  'to service_role',
]) {
  if (!sql.includes(marker)) fail(`staging SQL marker is missing: ${marker}`);
}
const normalizedSql = sql.toLowerCase().replaceAll(/\s+/g, ' ');
for (const forbidden of ['update public.product_events', 'delete from public.product_events', 'truncate']) {
  if (normalizedSql.includes(forbidden)) fail(`staging SQL is not forward-only: ${forbidden}`);
}

const js = spawnSync(process.execPath, ['scripts/check-javascript.mjs'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
});
if (js.status !== 0) fail(`JavaScript validation failed: ${String(js.stdout || js.stderr).trim()}`);
for (const marker of [
  'Validated 23/23 Word/PDF attribution runtime cases.',
  'Validated 49 JavaScript files.',
]) {
  if (!js.stdout.includes(marker)) fail(`JavaScript validation marker is missing: ${marker}`);
}

console.log(JSON.stringify({
  object: 'word_pdf_current_candidate_verification',
  productBase,
  head: git(['rev-parse', 'HEAD']),
  branch: branchName,
  state: 'STAGED_CANDIDATE_READY / PUBLIC_RELEASE_HELD',
  changedPaths: expectedChanged.length,
  authenticAssets: Object.keys(expectedAssets).length,
  runtimeCases: 23,
  applyableMigrations: 0,
  publicDiscovery: 0,
  publicationAuthorized: false,
  deploymentAuthorized: false,
  spend: 0,
}, null, 2));
