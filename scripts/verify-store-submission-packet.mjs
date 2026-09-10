import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { access, mkdtemp, open, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const rootUrl = new URL('../', import.meta.url);
const rootPath = path.resolve(fileURLToPath(rootUrl));
const schema = 'ask-crump-store-submission-evidence/v1';
const rootKeys = ['appVersion', 'artifact', 'buildNumber', 'checks', 'observedAt', 'platform', 'schema', 'screenshots'];
const artifactKeys = ['file', 'sha256'];
const screenshotKeys = ['file', 'sha256'];
const commonChecks = [
  'accessibilityVerified',
  'accountDeletionVerified',
  'aiReportingVerified',
  'offlineReconnectVerified',
  'physicalDeviceCoreJourneyVerified',
  'privacyFormsReconciled',
  'purchaseAndRestoreVerified',
  'reviewerPathVerified',
  'sessionPersistenceVerified',
  'storeConsoleScreenshotsAccepted',
];
const platformChecks = {
  android: [
    'notificationPermissionAndDeliveryVerified',
    'playConsoleDeclarationsReconciled',
    'playPreLaunchReportReviewed',
    'playProductsAndRevenueCatVerified',
    'signedBundleVerified',
  ],
  ios: [
    'appStoreConnectDeclarationsReconciled',
    'appStoreProductsAndRevenueCatVerified',
    'compiledPrivacyReportReviewed',
    'pushForegroundBackgroundTerminatedVerified',
    'signedArchiveVerified',
  ],
};

class PacketError extends Error {}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new PacketError(`${label} must be an object.`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    throw new PacketError(`${label} fields do not match the fixed submission schema.`);
  }
}

function normalizedHash(value, label) {
  const hash = String(value || '').trim().toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(hash)) throw new PacketError(`${label} must be a SHA-256 value.`);
  return hash;
}

function expectedBuildNumber(version) {
  const parts = String(version || '').split('.').map(Number);
  if (parts.length !== 3 || parts.some(part => !Number.isInteger(part) || part < 0 || part > 99)) {
    throw new PacketError('The package version is not a three-part store version.');
  }
  return parts[0] * 10_000 + parts[1] * 100 + parts[2];
}

function validateReviewerAccess(value, platform) {
  const selected = value?.[platform];
  if (!selected || typeof selected !== 'object' || Array.isArray(selected)) {
    throw new PacketError(`Reviewer access is missing the ${platform} account.`);
  }
  const username = String(selected.username || '').trim();
  const password = String(selected.password || '');
  if (!username || !username.includes('@') || /replace|example/i.test(username)) {
    throw new PacketError(`Reviewer access has no usable ${platform} username.`);
  }
  if (password.length < 12 || /replace_in_untracked_file/i.test(password)) {
    throw new PacketError(`Reviewer access has no usable ${platform} password.`);
  }
}

function validateEvidence(value, expected, now = new Date()) {
  exactKeys(value, rootKeys, 'Submission evidence');
  if (value.schema !== schema) throw new PacketError('Submission evidence schema is not current.');
  if (value.platform !== expected.platform) throw new PacketError('Submission evidence platform does not match the requested platform.');
  if (value.appVersion !== expected.version) throw new PacketError('Submission evidence version does not match package.json.');
  if (value.buildNumber !== expected.buildNumber) throw new PacketError('Submission evidence build number does not match the release identity.');

  const observedAt = new Date(value.observedAt);
  if (!Number.isFinite(observedAt.getTime())) throw new PacketError('Submission evidence observedAt is invalid.');
  const age = now.getTime() - observedAt.getTime();
  if (age < -5 * 60_000 || age > 14 * 24 * 60 * 60_000) {
    throw new PacketError('Submission evidence must be current within fourteen days and cannot be future-dated.');
  }

  exactKeys(value.artifact, artifactKeys, 'Artifact evidence');
  if (value.artifact.file !== expected.artifactFile) throw new PacketError('Artifact filename does not match the inspected file.');
  if (normalizedHash(value.artifact.sha256, 'Artifact hash') !== expected.artifactHash) {
    throw new PacketError('Artifact hash does not match the inspected file.');
  }

  if (!Array.isArray(value.screenshots)) throw new PacketError('Screenshot evidence must be an array.');
  const minimumScreenshots = expected.platform === 'android' ? 4 : 1;
  if (value.screenshots.length < minimumScreenshots || value.screenshots.length > 10) {
    throw new PacketError(`${expected.platform} screenshot evidence must contain ${minimumScreenshots}–10 files.`);
  }
  const declaredScreenshots = new Map();
  for (const item of value.screenshots) {
    exactKeys(item, screenshotKeys, 'Screenshot evidence item');
    const name = String(item.file || '');
    if (!name || path.basename(name) !== name || !/\.(?:png|jpe?g)$/i.test(name)) {
      throw new PacketError('Screenshot evidence contains an invalid filename.');
    }
    if (declaredScreenshots.has(name)) throw new PacketError('Screenshot evidence contains a duplicate filename.');
    declaredScreenshots.set(name, normalizedHash(item.sha256, 'Screenshot hash'));
  }
  if (declaredScreenshots.size !== expected.screenshotHashes.size) {
    throw new PacketError('Screenshot evidence does not match the complete inspected directory.');
  }
  for (const [name, hash] of expected.screenshotHashes) {
    if (declaredScreenshots.get(name) !== hash) {
      throw new PacketError('Screenshot evidence does not match the inspected files.');
    }
  }

  const requiredChecks = [...commonChecks, ...platformChecks[expected.platform]].sort();
  exactKeys(value.checks, requiredChecks, 'Submission checks');
  for (const check of requiredChecks) {
    if (value.checks[check] !== true) throw new PacketError(`Submission check is incomplete: ${check}.`);
  }
  return requiredChecks.length;
}

async function sha256File(file) {
  const hash = createHash('sha256');
  await new Promise((resolve, reject) => {
    const stream = createReadStream(file);
    stream.on('data', chunk => hash.update(chunk));
    stream.on('error', reject);
    stream.on('end', resolve);
  });
  return hash.digest('hex');
}

async function isImageFile(file) {
  const handle = await open(file, 'r');
  try {
    const details = await handle.stat();
    if (details.size < 4) return false;
    const first = Buffer.alloc(8);
    const last = Buffer.alloc(2);
    await handle.read(first, 0, first.length, 0);
    await handle.read(last, 0, last.length, Math.max(0, details.size - 2));
    const png = first.equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
    const jpeg = first[0] === 0xff && first[1] === 0xd8 && last[0] === 0xff && last[1] === 0xd9;
    return png || jpeg;
  } finally {
    await handle.close();
  }
}

async function screenshotHashes(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  if (entries.some(entry => entry.isDirectory())) throw new PacketError('Screenshot directory must be flat.');
  const files = entries.filter(entry => entry.isFile() && /\.(?:png|jpe?g)$/i.test(entry.name));
  if (files.length !== entries.length) throw new PacketError('Screenshot directory contains a non-image file.');
  const hashes = new Map();
  for (const entry of files.sort((left, right) => left.name.localeCompare(right.name))) {
    const file = path.join(directory, entry.name);
    if (!(await isImageFile(file))) throw new PacketError('A screenshot does not have a valid PNG or JPEG signature.');
    hashes.set(entry.name, await sha256File(file));
  }
  return hashes;
}

async function readJson(file, label, maximumBytes) {
  const details = await stat(file);
  if (!details.isFile() || details.size < 2 || details.size > maximumBytes) {
    throw new PacketError(`${label} is missing, empty, or unexpectedly large.`);
  }
  try {
    return JSON.parse(await readFile(file, 'utf8'));
  } catch {
    throw new PacketError(`${label} is not valid JSON.`);
  }
}

function parseArguments(argumentsList) {
  if (argumentsList.includes('--self-test')) return { selfTest: true };
  const allowed = new Set(['--platform', '--artifact', '--screenshots', '--evidence', '--reviewer-access']);
  const values = {};
  for (let index = 0; index < argumentsList.length; index += 2) {
    const name = argumentsList[index];
    const value = argumentsList[index + 1];
    if (!allowed.has(name) || !value || value.startsWith('--')) throw new PacketError('Store submission gate arguments are incomplete.');
    values[name.slice(2)] = value;
  }
  if (Object.keys(values).length !== allowed.size) throw new PacketError('Store submission gate requires platform, artifact, screenshots, evidence, and reviewer access.');
  return values;
}

function pathInsideRoot(file) {
  const relative = path.relative(rootPath, path.resolve(file));
  return relative && !relative.startsWith('..') && !path.isAbsolute(relative);
}

function requireIgnoredReviewerFile(file) {
  if (!pathInsideRoot(file)) return;
  const command = process.platform === 'win32' ? 'git.exe' : 'git';
  const result = spawnSync(command, ['-C', rootPath, 'check-ignore', '--quiet', path.resolve(file)], { shell: false });
  if (result.status !== 0) throw new PacketError('Reviewer access inside the repository must be ignored by Git.');
}

async function selfTest() {
  const version = '5.9.76';
  const validHash = 'a'.repeat(64);
  const screenshotMap = new Map([
    ['01.png', '1'.repeat(64)],
    ['02.png', '2'.repeat(64)],
    ['03.png', '3'.repeat(64)],
    ['04.png', '4'.repeat(64)],
  ]);
  const checks = Object.fromEntries([...commonChecks, ...platformChecks.android].map(name => [name, true]));
  const manifest = {
    schema,
    platform: 'android',
    appVersion: version,
    buildNumber: expectedBuildNumber(version),
    observedAt: '2026-09-10T12:00:00.000Z',
    artifact: { file: 'ask-crump.aab', sha256: validHash },
    screenshots: [...screenshotMap].map(([file, sha256]) => ({ file, sha256 })),
    checks,
  };
  const expected = {
    platform: 'android', version, buildNumber: 50976, artifactFile: 'ask-crump.aab',
    artifactHash: validHash, screenshotHashes: screenshotMap,
  };
  const cases = [
    ['valid exact packet', () => validateEvidence(manifest, expected, new Date('2026-09-10T12:05:00Z')), false],
    ['valid reviewer', () => validateReviewerAccess({ android: { username: 'reviewer@askcrump.com', password: 'long-secret-value' } }, 'android'), false],
    ['wrong platform', () => validateEvidence({ ...manifest, platform: 'ios' }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong build', () => validateEvidence({ ...manifest, buildNumber: 1 }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['stale evidence', () => validateEvidence(manifest, expected, new Date('2026-10-10T12:05:00Z')), true],
    ['wrong artifact hash', () => validateEvidence({ ...manifest, artifact: { ...manifest.artifact, sha256: 'b'.repeat(64) } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['missing screenshot', () => validateEvidence({ ...manifest, screenshots: manifest.screenshots.slice(0, 3) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['extra evidence field', () => validateEvidence({ ...manifest, notes: 'not allowed' }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['incomplete check', () => validateEvidence({ ...manifest, checks: { ...checks, purchaseAndRestoreVerified: false } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['unknown check', () => validateEvidence({ ...manifest, checks: { ...checks, invented: true } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['placeholder reviewer', () => validateReviewerAccess({ android: { username: 'REPLACE_IN_UNTRACKED_FILE', password: 'REPLACE_IN_UNTRACKED_FILE' } }, 'android'), true],
    ['short reviewer secret', () => validateReviewerAccess({ android: { username: 'reviewer@askcrump.com', password: 'short' } }, 'android'), true],
  ];
  let passed = 0;
  for (const [name, operation, shouldFail] of cases) {
    let failed = false;
    try { operation(); } catch (error) { failed = error instanceof PacketError; }
    if (failed !== shouldFail) throw new PacketError(`Self-test failed: ${name}.`);
    passed += 1;
  }
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), 'askcrump-store-gate-'));
  try {
    const image = path.join(temporaryRoot, 'proof.png');
    const bytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x01]);
    await writeFile(image, bytes);
    if (!(await isImageFile(image))) throw new PacketError('Self-test failed: PNG signature.');
    if ((await sha256File(image)) !== createHash('sha256').update(bytes).digest('hex')) {
      throw new PacketError('Self-test failed: file SHA-256.');
    }
    passed += 2;
  } finally {
    const resolved = path.resolve(temporaryRoot);
    const expectedPrefix = `${path.resolve(tmpdir())}${path.sep}`;
    if (!resolved.startsWith(expectedPrefix) || !path.basename(resolved).startsWith('askcrump-store-gate-')) {
      throw new PacketError('Self-test temporary directory boundary is invalid.');
    }
    await rm(resolved, { recursive: true, force: true });
  }
  console.log(`Store submission packet gate self-test passed ${passed}/${cases.length + 2} cases.`);
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  if (args.selfTest) return await selfTest();
  const platform = String(args.platform || '').toLowerCase();
  if (!Object.hasOwn(platformChecks, platform)) throw new PacketError('Platform must be android or ios.');
  const artifact = path.resolve(args.artifact);
  const extension = path.extname(artifact).toLowerCase();
  if ((platform === 'android' && extension !== '.aab') || (platform === 'ios' && extension !== '.ipa')) {
    throw new PacketError(`The ${platform} submission artifact has the wrong file type.`);
  }
  await access(artifact, constants.R_OK);
  const artifactDetails = await stat(artifact);
  if (!artifactDetails.isFile() || artifactDetails.size === 0) throw new PacketError('Submission artifact is empty.');

  const packageMetadata = JSON.parse(await readFile(new URL('package.json', rootUrl), 'utf8'));
  const version = String(packageMetadata.version || '').trim();
  const buildNumber = expectedBuildNumber(version);
  const screenshots = await screenshotHashes(path.resolve(args.screenshots));
  const artifactHash = await sha256File(artifact);
  const reviewerFile = path.resolve(args['reviewer-access']);
  requireIgnoredReviewerFile(reviewerFile);
  const reviewer = await readJson(reviewerFile, 'Reviewer access file', 16 * 1024);
  validateReviewerAccess(reviewer, platform);
  const evidence = await readJson(path.resolve(args.evidence), 'Submission evidence file', 64 * 1024);
  const checkCount = validateEvidence(evidence, {
    platform,
    version,
    buildNumber,
    artifactFile: path.basename(artifact),
    artifactHash,
    screenshotHashes: screenshots,
  });

  console.log(`Ask Crump ${platform} submission packet passed its fail-closed completeness gate.`);
  console.log(`Release identity: ${version} (${buildNumber}); checks: ${checkCount}; screenshots: ${screenshots.size}.`);
  console.log('No upload or store submission was performed. Final owner approval remains required.');
}

main().catch(error => {
  const message = error instanceof PacketError ? error.message : `Submission packet check failed (${error?.constructor?.name || 'Error'}).`;
  console.error(`FAIL: ${message}`);
  process.exitCode = 1;
});
