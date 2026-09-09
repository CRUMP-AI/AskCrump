import {createHash} from 'node:crypto';
import {execFileSync, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const manifestPath = path.join(repoRoot, 'docs', 'word-pdf-guide-isolated-diff.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const publicDescription = 'See a real Ask Crump Word and PDF output pair. Learn when to keep an editable DOCX, deliver a fixed-layout PDF, and use a seven-point handoff review.';
const guidePath = 'public/guides/word-or-pdf-ai-document-output.html';
const stagingSqlPath = 'staging/add_word_pdf_guide_attribution.sql';

function fail(message) {
  console.error(`Word/PDF guide candidate invalid: ${message}`);
  process.exit(1);
}

function git(args) {
  return execFileSync('git', args, {
    cwd: repoRoot,
    encoding: 'utf8',
    windowsHide: true,
  }).trim();
}

function normalizePath(value) {
  return String(value || '').replaceAll('\\', '/');
}

function normalizeWhitespace(value) {
  return String(value || '').replaceAll('\r\n', '\n').split(/\s+/).filter(Boolean).join(' ');
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

if (manifest.schemaVersion !== 1) fail('unsupported schema version');
if (manifest.status !== 'held') fail('candidate must remain held');
if (manifest.candidateId !== 'word-pdf-guide-20260831') fail('candidate id drifted');
if (manifest.releaseUnit?.order !== 6 || manifest.releaseUnit?.id !== 'word-pdf-guide') {
  fail('release-train identity drifted');
}
if (manifest.releaseUnit?.requiresFreshMigrationIdentity !== true) {
  fail('fresh migration identity gate is missing');
}
if (manifest.releaseUnit?.requiresCandidateRebuild !== true) {
  fail('mandatory predecessor rebuild gate is missing');
}
if (git(['rev-parse', 'HEAD']) !== manifest.baseCommit) fail('candidate base commit drifted');

const cached = spawnSync('git', ['diff', '--cached', '--quiet'], {
  cwd: repoRoot,
  windowsHide: true,
});
if (cached.status !== 0) fail('candidate contains staged index changes');

const status = execFileSync('git', ['status', '--porcelain=v1', '-uall'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
})
  .split(/\r?\n/)
  .filter(Boolean)
  .map(line => normalizePath(line.slice(3)))
  .sort();
const allowed = [...manifest.allowedPaths].map(normalizePath).sort();
if (JSON.stringify(status) !== JSON.stringify(allowed)) {
  const missing = allowed.filter(item => !status.includes(item));
  const unexpected = status.filter(item => !allowed.includes(item));
  fail(`path boundary drifted; missing=[${missing.join(', ')}] unexpected=[${unexpected.join(', ')}]`);
}
if (status.some(item => item.startsWith('migrations/'))) {
  fail('candidate contains an applyable migration');
}
const stagingPaths = status.filter(item => item.startsWith('staging/'));
if (JSON.stringify(stagingPaths) !== JSON.stringify([stagingSqlPath])) {
  fail('candidate must contain exactly the reviewed staging-only SQL path');
}

for (const [relativePath, expected] of Object.entries(manifest.contentHashes)) {
  if (!fs.existsSync(path.join(repoRoot, relativePath))) fail(`hashed file missing: ${relativePath}`);
  if (sha256(relativePath) !== expected) fail(`content hash drifted: ${relativePath}`);
}
if (Object.keys(manifest.contentHashes).length !== allowed.length - 1) {
  fail('every allowed path except the manifest must be hash-locked');
}

const guide = fs.readFileSync(path.join(repoRoot, guidePath), 'utf8');
const guideNormalized = normalizeWhitespace(guide);
for (const marker of [
  '<title>Word or PDF? Choose the Right AI Document Output | Ask Crump</title>',
  '<h1>Word or PDF? Start with what happens next.</h1>',
  '<link rel="canonical" href="https://www.askcrump.com/guides/word-or-pdf-ai-document-output">',
  '<meta name="robots" content="noindex,nofollow">',
  '<meta property="og:description" content="Choose the working format from the next action, then inspect the real file before relying on it.">',
  '<meta name="twitter:description" content="Use Word while work is moving and PDF after the reviewed layout is ready to travel.">',
  'Prepared <strong>August 30, 2026</strong>',
  'Status <strong>staged for review</strong>',
  'every person, date, figure, threshold, and operating detail are invented',
  'this accepted file is not tagged for accessibility',
  'Export success is not final acceptance',
  'No customer content or testimonial is used',
]) {
  if (!guide.includes(marker)) fail(`guide contract marker is missing: ${marker}`);
}
if (count(guide, publicDescription) !== 2) {
  fail('exact public description must appear once in meta and once in Article JSON-LD');
}
if (!guide.includes(`<meta name="description" content="${publicDescription}">`)) {
  fail('HTML meta description drifted');
}
if (!guideNormalized.includes(normalizeWhitespace(`"description": "${publicDescription}"`))) {
  fail('Article JSON-LD description drifted');
}
if (count(guide, '<h1>') !== 1 || count(guide, 'class="button primary"') !== 1) {
  fail('guide must retain one H1 and one primary CTA');
}
const cta = 'href="/ai-document-generator?acquisition=organic-search&amp;source=workflow-guide&amp;campaign=word-or-pdf-decision&amp;creative=search-article"';
if (!guide.includes(cta)) fail('exact primary CTA tuple drifted');
for (const forbidden of [
  'datePublished', 'dateModified', 'article:published_time', 'article:modified_time',
  'FAQPage', '"@type": "HowTo"', '"@type": "Review"', 'aggregateRating',
]) {
  if (guide.includes(forbidden)) fail(`staged guide contains forbidden public-schema marker: ${forbidden}`);
}

for (const relativePath of [
  'tests/test_search_guides.py',
  'docs/WORD_PDF_GUIDE_PRODUCT_RELEASE_ACTION_RECORD_2026-08-30.md',
  'docs/WORD_PDF_GUIDE_STAGED_ACCEPTANCE_2026-08-30.md',
  'docs/WORD_PDF_GUIDE_ISOLATED_CANDIDATE_ACCEPTANCE_2026-08-31.md',
]) {
  const text = normalizeWhitespace(fs.readFileSync(path.join(repoRoot, relativePath), 'utf8'));
  const comparison = relativePath.startsWith('tests/') ? text.replace(/"\s+"/g, '') : text;
  if (!comparison.includes(publicDescription)) {
    fail(`${relativePath} does not lock the exact public description`);
  }
}

const sitemap = fs.readFileSync(path.join(repoRoot, 'public', 'sitemap.xml'), 'utf8');
const route = '/guides/word-or-pdf-ai-document-output';
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
  if (sha256(relativePath) !== expected) fail(`accepted asset hash drifted: ${relativePath}`);
}
if (sha256(stagingSqlPath) !== '583ac0fb91c41d84249836f4c9c7d0a35dfcc6627f3691a5c00e6e5bd87864df') {
  fail('reviewed staging-only SQL hash drifted');
}

const landing = fs.readFileSync(path.join(repoRoot, 'public', 'landing.js'), 'utf8');
const auth = fs.readFileSync(path.join(repoRoot, 'public', 'auth-controller.js'), 'utf8');
const backend = fs.readFileSync(path.join(repoRoot, 'backend', 'product_analytics.py'), 'utf8');
const sql = fs.readFileSync(path.join(repoRoot, stagingSqlPath), 'utf8');
for (const source of [landing, auth]) {
  for (const marker of [
    "'word-or-pdf-decision': {\n      intent: 'document',\n      acquisitions: new Set(['organic-search']),\n      placements: new Set(['workflow-guide']),\n      creatives: new Set(['search-article'])",
    "'word-or-pdf-social': {\n      intent: 'document',\n      acquisitions: new Set(['facebook', 'instagram']),\n      placements: new Set(['organic-social']),\n      creatives: new Set(['word-pdf-feed', 'word-pdf-story'])",
    'const attribution = stored ? normalizeAttribution(stored) : candidate',
  ]) {
    if (!source.includes(marker)) fail('JavaScript registry or immutable first-touch boundary drifted');
  }
}
for (const marker of [
  '"word-or-pdf-decision": {',
  '"acquisitions": frozenset({"organic-search"})',
  '"word-or-pdf-social": {',
  '"acquisitions": frozenset({"facebook", "instagram"})',
  '"creatives": frozenset({"word-pdf-feed", "word-pdf-story"})',
]) {
  if (!backend.includes(marker)) fail(`Python registry marker is missing: ${marker}`);
}
for (const marker of [
  "campaign = 'word-or-pdf-decision'",
  "source = 'organic-search'",
  "placement = 'workflow-guide'",
  "campaign = 'word-or-pdf-social'",
  "source in ('facebook', 'instagram')",
  "placement = 'organic-social'",
  "creative in ('word-pdf-feed', 'word-pdf-story')",
]) {
  if (!sql.includes(marker)) fail(`staging SQL registry marker is missing: ${marker}`);
}
for (const forbidden of ['MARKETING_LANDING_KEY', 'MarketingLanding']) {
  if (landing.includes(forbidden)) fail(`predecessor unit leaked into isolated landing runtime: ${forbidden}`);
}

const actionRecord = fs.readFileSync(path.join(repoRoot, manifest.actionRecord), 'utf8');
const acceptance = fs.readFileSync(path.join(repoRoot, manifest.acceptanceRecord), 'utf8');
for (const source of [actionRecord, acceptance]) {
  if (!source.includes('SEO crawl-hygiene unit') || !source.includes('every actual predecessor')) {
    fail('mandatory later predecessor rebuild boundary is missing');
  }
}

const diffCheck = spawnSync('git', ['diff', '--check'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
});
if (diffCheck.status !== 0) {
  fail(`diff integrity failed: ${String(diffCheck.stdout || diffCheck.stderr).trim()}`);
}

console.log(
  `Validated held ${manifest.candidateId}: ${allowed.length} exact paths, `
  + `${Object.keys(manifest.contentHashes).length} immutable hashes, four accepted assets, `
  + 'one staging-only SQL file, zero applyable migrations, exact public description, '
  + 'immutable first touch, zero public discovery, zero staged index changes.',
);
