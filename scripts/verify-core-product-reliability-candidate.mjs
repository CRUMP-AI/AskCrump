import {createHash} from 'node:crypto';
import {execFileSync, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const manifestPath = path.join(repoRoot, 'docs', 'core-product-reliability-isolated-diff.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

function fail(message) {
  console.error(`Core reliability candidate invalid: ${message}`);
  process.exit(1);
}

function git(args, options = {}) {
  return execFileSync('git', args, {
    cwd: repoRoot,
    encoding: 'utf8',
    windowsHide: true,
    ...options,
  }).trim();
}

function normalize(value) {
  return String(value || '').replaceAll('\\', '/');
}

function hashFile(relativePath) {
  const bytes = fs.readFileSync(path.join(repoRoot, relativePath));
  return createHash('sha256').update(bytes).digest('hex');
}

if (manifest.schemaVersion !== 1) fail('unsupported manifest schema');
if (manifest.status !== 'held') fail('candidate must remain held until action-time approval');
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
  .map(line => normalize(line.slice(3)))
  .sort();
const allowed = [...manifest.allowedPaths].map(normalize).sort();
if (JSON.stringify(status) !== JSON.stringify(allowed)) {
  const missing = allowed.filter(item => !status.includes(item));
  const unexpected = status.filter(item => !allowed.includes(item));
  fail(`path boundary drifted; missing=[${missing.join(', ')}] unexpected=[${unexpected.join(', ')}]`);
}

for (const prefix of manifest.forbiddenPathPrefixes) {
  const found = status.find(item => item === prefix || item.startsWith(prefix));
  if (found) fail(`forbidden release path present: ${found}`);
}

for (const [relativePath, expected] of Object.entries(manifest.contentHashes)) {
  if (!fs.existsSync(path.join(repoRoot, relativePath))) fail(`hashed file missing: ${relativePath}`);
  const actual = hashFile(relativePath);
  if (actual !== expected) fail(`content hash drifted: ${relativePath}`);
}

for (const [relativePath, markers] of Object.entries(manifest.requiredMarkers)) {
  const source = fs.readFileSync(path.join(repoRoot, relativePath), 'utf8');
  for (const marker of markers) {
    if (!source.includes(marker)) fail(`${relativePath} is missing required marker: ${marker}`);
  }
}

const sourcePaths = status.filter(relativePath => (
  relativePath.startsWith('backend/')
  || relativePath.startsWith('public/')
  || relativePath === 'scripts/build-native.mjs'
  || relativePath === 'scripts/check-javascript.mjs'
));
for (const relativePath of sourcePaths) {
  const diff = git(['diff', '--unified=0', '--', relativePath]);
  const additions = diff
    .split(/\r?\n/)
    .filter(line => line.startsWith('+') && !line.startsWith('+++'))
    .map(line => line.slice(1))
    .join('\n');
  for (const marker of manifest.forbiddenAddedMarkers) {
    if (additions.includes(marker)) {
      fail(`${relativePath} adds forbidden unrelated marker: ${marker}`);
    }
  }
}

const actionRecord = fs.readFileSync(path.join(repoRoot, manifest.actionRecord), 'utf8');
if (!actionRecord.includes('Approve the cumulative core product reliability release')) {
  fail('cumulative action-time approval phrase is missing');
}
if (!actionRecord.includes('Include only the six named accepted repairs')) {
  fail('cumulative six-repair isolation phrase is missing');
}

const diffCheck = spawnSync('git', ['diff', '--check'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
});
if (diffCheck.status !== 0) fail(`diff integrity failed: ${String(diffCheck.stdout || diffCheck.stderr).trim()}`);

console.log(
  `Validated held ${manifest.candidateId}: ${allowed.length} exact paths, `
  + `${Object.keys(manifest.contentHashes).length} immutable content hashes, zero migrations, zero staged index changes.`,
);
