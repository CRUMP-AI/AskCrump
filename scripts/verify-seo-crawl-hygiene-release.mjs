import {createHash} from 'node:crypto';
import {execFileSync, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const manifestPath = path.join(repoRoot, 'docs', 'seo-crawl-hygiene-release.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

function fail(message) {
  console.error(`SEO crawl-hygiene release invalid: ${message}`);
  process.exit(1);
}

function git(args, options = {}) {
  return execFileSync('git', args, {
    cwd: repoRoot,
    encoding: options.encoding === null ? null : 'utf8',
    maxBuffer: 10 * 1024 * 1024,
    windowsHide: true,
  });
}

function normalizePath(value) {
  return String(value || '').replaceAll('\\', '/');
}

function normalizeText(value) {
  return String(value || '').replaceAll('\r\n', '\n');
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function fileAt(commit, relativePath) {
  return git(['show', `${commit}:${relativePath}`], {encoding: null});
}

if (manifest.schemaVersion !== 1) fail('unsupported schema version');
if (manifest.status !== 'released-code-only') fail('release status drifted');
if (manifest.domainStep?.executed !== false) fail('held domain step is no longer held');
if (manifest.searchConsoleActionExecuted !== false) fail('Search Console boundary drifted');

for (const commit of [manifest.baseCommit, manifest.codeCommit]) {
  const result = spawnSync('git', ['cat-file', '-e', `${commit}^{commit}`], {
    cwd: repoRoot,
    windowsHide: true,
  });
  if (result.status !== 0) fail(`missing release commit: ${commit}`);
}

const ancestor = spawnSync('git', ['merge-base', '--is-ancestor', manifest.codeCommit, 'HEAD'], {
  cwd: repoRoot,
  windowsHide: true,
});
if (ancestor.status !== 0) fail('code commit is not an ancestor of HEAD');

const changed = git(['diff', '--name-only', manifest.baseCommit, manifest.codeCommit])
  .split(/\r?\n/)
  .filter(Boolean)
  .map(normalizePath)
  .sort();
const allowed = [...manifest.allowedCodePaths].map(normalizePath).sort();
if (JSON.stringify(changed) !== JSON.stringify(allowed)) {
  fail(`code path boundary drifted: ${changed.join(', ')}`);
}
if (changed.some(item => item.startsWith('migrations/') || item.startsWith('staging/'))) {
  fail('release contains database or staging SQL');
}

for (const [relativePath, expected] of Object.entries(manifest.contentHashes)) {
  const releasedBytes = fileAt(manifest.codeCommit, relativePath);
  if (sha256(releasedBytes) !== expected) fail(`released hash drifted: ${relativePath}`);
  if (sha256(fs.readFileSync(path.join(repoRoot, relativePath))) !== expected) {
    fail(`current release surface drifted: ${relativePath}`);
  }
}

for (const [relativePath, expected] of Object.entries(manifest.unchangedTrustBoundaries)) {
  const diff = spawnSync('git', ['diff', '--quiet', manifest.baseCommit, manifest.codeCommit, '--', relativePath], {
    cwd: repoRoot,
    windowsHide: true,
  });
  if (diff.status !== 0) fail(`trust boundary changed: ${relativePath}`);
  if (sha256(fileAt(manifest.codeCommit, relativePath)) !== expected) {
    fail(`trust-boundary hash drifted: ${relativePath}`);
  }
}

const expectedRobots = [
  'User-agent: *',
  'Allow: /',
  'Disallow: /api/',
  'Disallow: /delete-account',
  '',
  'Sitemap: https://www.askcrump.com/sitemap.xml',
  '',
].join('\n');
const robots = normalizeText(fileAt(manifest.codeCommit, 'public/robots.txt').toString('utf8'));
if (robots !== expectedRobots) fail('Ask robots boundary is not exact');
if (robots.includes('Disallow: /app')) fail('robots still blocks the app shell');

const vercel = JSON.parse(fileAt(manifest.codeCommit, 'vercel.json').toString('utf8'));
const xRobotsRules = (vercel.headers || []).filter(rule => (
  (rule.headers || []).some(header => String(header.key).toLowerCase() === 'x-robots-tag')
));
const expectedRule = [{
  source: '/app',
  headers: [{key: 'X-Robots-Tag', value: 'noindex, nofollow'}],
}];
if (JSON.stringify(xRobotsRules) !== JSON.stringify(expectedRule)) {
  fail('Vercel must contain exactly one exact /app X-Robots-Tag rule');
}

const app = fileAt(manifest.codeCommit, 'public/app.html').toString('utf8');
if (!app.includes('<meta name="robots" content="noindex,nofollow">')) {
  fail('rendered app noindex directive is missing');
}
const publicPage = fileAt(manifest.codeCommit, 'public/ai-document-generator.html').toString('utf8');
if (!publicPage.includes('<meta name="robots" content="index,follow,max-image-preview:large">')) {
  fail('public acquisition indexability drifted');
}
const sitemap = fileAt(manifest.codeCommit, 'public/sitemap.xml').toString('utf8');
if (sitemap.includes('<loc>https://www.askcrump.com/app')) fail('private app entered the sitemap');

const diffCheck = spawnSync('git', ['diff', '--check', manifest.baseCommit, manifest.codeCommit], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
});
if (diffCheck.status !== 0) fail(`diff integrity failed: ${String(diffCheck.stdout || diffCheck.stderr).trim()}`);

console.log(
  `Validated released ${manifest.releaseId}: ${allowed.length} exact code paths, `
  + `${Object.keys(manifest.contentHashes).length} released hashes, `
  + `${Object.keys(manifest.unchangedTrustBoundaries).length} unchanged trust boundaries, `
  + 'zero migrations, domain step held, Search Console action held.',
);
