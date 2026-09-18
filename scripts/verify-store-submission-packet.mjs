import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { access, mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const rootUrl = new URL('../', import.meta.url);
const rootPath = path.resolve(fileURLToPath(rootUrl));
const schema = 'ask-crump-store-submission-evidence/v2';
const rootKeys = ['appVersion', 'artifact', 'buildNumber', 'checks', 'observedAt', 'platform', 'schema', 'screenshots'];
const artifactKeys = ['file', 'sha256'];
const screenshotKeys = ['device', 'file', 'height', 'sha256', 'width'];
const appleScreenshotDimensions = Object.freeze({
  'iphone-6.9': new Set(['1260x2736', '2736x1260', '1290x2796', '2796x1290', '1320x2868', '2868x1320']),
  'ipad-13': new Set(['2064x2752', '2752x2064', '2048x2732', '2732x2048']),
});
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
    'ipadLayoutAndCoreJourneyVerified',
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
  if (platform === 'ios') {
    const contact = selected.contact;
    if (!contact || typeof contact !== 'object' || Array.isArray(contact)) {
      throw new PacketError('Reviewer access is missing the iOS App Review contact.');
    }
    const contactFirstName = String(contact.firstName || '').trim();
    const contactLastName = String(contact.lastName || '').trim();
    const contactEmail = String(contact.email || '').trim();
    const contactPhone = String(contact.phone || '').trim();
    if (!contactFirstName || !contactLastName || /replace|example/i.test(`${contactFirstName} ${contactLastName}`)) {
      throw new PacketError('Reviewer access requires usable iOS App Review contact first and last names.');
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactEmail) || /replace|example/i.test(contactEmail)) {
      throw new PacketError('Reviewer access has no usable iOS App Review contact email.');
    }
    if (!/^\+[1-9]\d{7,14}$/.test(contactPhone)) {
      throw new PacketError('Reviewer access iOS App Review phone must use international E.164 format.');
    }
  }
}

function verifyStoreMetadataSource() {
  const result = spawnSync(process.execPath, ['scripts/verify-store-metadata.mjs'], {
    cwd: rootPath,
    encoding: 'utf8',
    shell: false,
  });
  if (result.status !== 0) {
    throw new PacketError(`Store metadata source gate failed.\n${String(result.stderr || result.stdout || '').trim()}`);
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
  const minimumScreenshots = expected.platform === 'android' ? 4 : 2;
  const maximumScreenshots = expected.platform === 'android' ? 8 : 20;
  if (value.screenshots.length < minimumScreenshots || value.screenshots.length > maximumScreenshots) {
    throw new PacketError(`${expected.platform} screenshot evidence must contain ${minimumScreenshots}–${maximumScreenshots} files.`);
  }
  const declaredScreenshots = new Map();
  for (const item of value.screenshots) {
    exactKeys(item, screenshotKeys, 'Screenshot evidence item');
    const name = String(item.file || '');
    const validName = expected.platform === 'android'
      ? Boolean(name && path.basename(name) === name && /\.(?:png|jpe?g)$/i.test(name))
      : /^(?:iphone|ipad)\/[^/\\]+\.(?:png|jpe?g)$/i.test(name);
    if (!validName) {
      throw new PacketError('Screenshot evidence contains an invalid filename.');
    }
    if (declaredScreenshots.has(name)) throw new PacketError('Screenshot evidence contains a duplicate filename.');
    const width = Number(item.width);
    const height = Number(item.height);
    if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1) {
      throw new PacketError('Screenshot evidence contains invalid dimensions.');
    }
    declaredScreenshots.set(name, {
      device: String(item.device || ''),
      height,
      sha256: normalizedHash(item.sha256, 'Screenshot hash'),
      width,
    });
  }
  if (declaredScreenshots.size !== expected.screenshotHashes.size) {
    throw new PacketError('Screenshot evidence does not match the complete inspected directory.');
  }
  for (const [name, inspected] of expected.screenshotHashes) {
    const declared = declaredScreenshots.get(name);
    if (!declared
        || declared.sha256 !== inspected.sha256
        || declared.device !== inspected.device
        || declared.width !== inspected.width
        || declared.height !== inspected.height) {
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

function inspectPng(bytes) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (bytes.length < 45 || !bytes.subarray(0, 8).equals(signature)) return null;
  let offset = 8;
  let header = null;
  let hasTransparency = false;
  let ended = false;
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    const next = offset + 12 + length;
    if (next > bytes.length) throw new PacketError('A PNG screenshot contains a truncated chunk.');
    if (!header) {
      if (type !== 'IHDR' || length !== 13) throw new PacketError('A PNG screenshot has no valid IHDR header.');
      header = {
        width: bytes.readUInt32BE(offset + 8),
        height: bytes.readUInt32BE(offset + 12),
        bitDepth: bytes[offset + 16],
        colorType: bytes[offset + 17],
      };
    }
    if (type === 'tRNS') hasTransparency = true;
    if (type === 'IEND') {
      if (length !== 0 || next !== bytes.length) throw new PacketError('A PNG screenshot has an invalid ending.');
      ended = true;
      break;
    }
    offset = next;
  }
  if (!header || !ended || !header.width || !header.height) throw new PacketError('A PNG screenshot is incomplete.');
  if (header.bitDepth !== 8 || header.colorType !== 2 || hasTransparency) {
    throw new PacketError('PNG screenshots must be 24-bit RGB without alpha or transparency.');
  }
  return { format: 'png', width: header.width, height: header.height };
}

function inspectJpeg(bytes) {
  if (bytes.length < 12 || bytes[0] !== 0xff || bytes[1] !== 0xd8
      || bytes[bytes.length - 2] !== 0xff || bytes[bytes.length - 1] !== 0xd9) return null;
  const startOfFrameMarkers = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);
  let offset = 2;
  while (offset < bytes.length - 2) {
    while (offset < bytes.length && bytes[offset] !== 0xff) offset += 1;
    while (offset < bytes.length && bytes[offset] === 0xff) offset += 1;
    if (offset >= bytes.length) break;
    const marker = bytes[offset];
    offset += 1;
    if (marker === 0xd9 || marker === 0xda) break;
    if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd8)) continue;
    if (offset + 2 > bytes.length) break;
    const length = bytes.readUInt16BE(offset);
    if (length < 2 || offset + length > bytes.length) throw new PacketError('A JPEG screenshot contains a truncated segment.');
    if (startOfFrameMarkers.has(marker)) {
      if (length < 7) throw new PacketError('A JPEG screenshot has an invalid frame header.');
      const height = bytes.readUInt16BE(offset + 3);
      const width = bytes.readUInt16BE(offset + 5);
      if (!width || !height) throw new PacketError('A JPEG screenshot has invalid dimensions.');
      return { format: 'jpeg', width, height };
    }
    offset += length;
  }
  throw new PacketError('A JPEG screenshot has no supported frame header.');
}

async function inspectImageFile(file) {
  const details = await stat(file);
  if (!details.isFile() || details.size < 12 || details.size > 16 * 1024 * 1024) {
    throw new PacketError('A screenshot is empty or unexpectedly large.');
  }
  const bytes = await readFile(file);
  const png = inspectPng(bytes);
  const jpeg = png ? null : inspectJpeg(bytes);
  const image = png || jpeg;
  if (!image) throw new PacketError('A screenshot does not have a valid PNG or JPEG structure.');
  const extension = path.extname(file).toLowerCase();
  if ((image.format === 'png' && extension !== '.png')
      || (image.format === 'jpeg' && !['.jpg', '.jpeg'].includes(extension))) {
    throw new PacketError('A screenshot extension does not match its image format.');
  }
  return { ...image, bytes: details.size };
}

function validateScreenshotDimensions(image, platform, device) {
  const dimensions = `${image.width}x${image.height}`;
  if (platform === 'ios') {
    if (!appleScreenshotDimensions[device]?.has(dimensions)) {
      throw new PacketError(`The ${device} screenshot size ${dimensions} is not an accepted current Apple size.`);
    }
    return;
  }
  const short = Math.min(image.width, image.height);
  const long = Math.max(image.width, image.height);
  if (short < 1080 || long > 3840 || long * 9 !== short * 16) {
    throw new PacketError(`Android phone screenshot size ${dimensions} must be 9:16 or 16:9, at least 1080 pixels on the short edge, and no larger than 3840 pixels.`);
  }
  if (image.bytes > 8 * 1024 * 1024) throw new PacketError('Android screenshots must be no larger than 8 MB.');
}

async function collectScreenshotDirectory(directory, prefix, device, platform) {
  const entries = await readdir(directory, { withFileTypes: true });
  if (entries.some(entry => entry.isDirectory())) throw new PacketError('A screenshot device directory must be flat.');
  const files = entries.filter(entry => entry.isFile() && /\.(?:png|jpe?g)$/i.test(entry.name));
  if (files.length !== entries.length) throw new PacketError('Screenshot directory contains a non-image file.');
  const inspected = [];
  for (const entry of files.sort((left, right) => left.name.localeCompare(right.name))) {
    const file = path.join(directory, entry.name);
    const image = await inspectImageFile(file);
    validateScreenshotDimensions(image, platform, device);
    inspected.push({
      key: prefix ? `${prefix}/${entry.name}` : entry.name,
      value: {
        device,
        height: image.height,
        sha256: await sha256File(file),
        width: image.width,
      },
    });
  }
  return inspected;
}

async function screenshotHashes(directory, platform) {
  const hashes = new Map();
  if (platform === 'android') {
    const entries = await collectScreenshotDirectory(directory, '', 'android-phone', platform);
    if (entries.length < 4 || entries.length > 8) throw new PacketError('Android screenshot directory must contain 4–8 phone screenshots.');
    for (const { key, value } of entries) hashes.set(key, value);
    return hashes;
  }

  const roots = await readdir(directory, { withFileTypes: true });
  const names = roots.map(entry => entry.name).sort();
  if (roots.some(entry => !entry.isDirectory()) || JSON.stringify(names) !== JSON.stringify(['ipad', 'iphone'])) {
    throw new PacketError('iOS screenshots must use exactly the iphone and ipad device directories.');
  }
  for (const [prefix, device] of [['iphone', 'iphone-6.9'], ['ipad', 'ipad-13']]) {
    const entries = await collectScreenshotDirectory(path.join(directory, prefix), prefix, device, platform);
    if (entries.length < 1 || entries.length > 10) throw new PacketError(`The iOS ${prefix} directory must contain 1–10 screenshots.`);
    for (const { key, value } of entries) hashes.set(key, value);
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
    ['01.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '1'.repeat(64) }],
    ['02.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '2'.repeat(64) }],
    ['03.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '3'.repeat(64) }],
    ['04.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '4'.repeat(64) }],
  ]);
  const checks = Object.fromEntries([...commonChecks, ...platformChecks.android].map(name => [name, true]));
  const manifest = {
    schema,
    platform: 'android',
    appVersion: version,
    buildNumber: expectedBuildNumber(version),
    observedAt: '2026-09-10T12:00:00.000Z',
    artifact: { file: 'ask-crump.aab', sha256: validHash },
    screenshots: [...screenshotMap].map(([file, evidence]) => ({ file, ...evidence })),
    checks,
  };
  const expected = {
    platform: 'android', version, buildNumber: 50976, artifactFile: 'ask-crump.aab',
    artifactHash: validHash, screenshotHashes: screenshotMap,
  };
  const iosScreenshotMap = new Map([
    ['iphone/01.png', { device: 'iphone-6.9', width: 1320, height: 2868, sha256: '5'.repeat(64) }],
    ['ipad/01.png', { device: 'ipad-13', width: 2064, height: 2752, sha256: '6'.repeat(64) }],
  ]);
  const iosManifest = {
    ...manifest,
    platform: 'ios',
    artifact: { file: 'ask-crump.ipa', sha256: validHash },
    screenshots: [...iosScreenshotMap].map(([file, evidence]) => ({ file, ...evidence })),
    checks: Object.fromEntries([...commonChecks, ...platformChecks.ios].map(name => [name, true])),
  };
  const iosExpected = {
    platform: 'ios', version, buildNumber: 50976, artifactFile: 'ask-crump.ipa',
    artifactHash: validHash, screenshotHashes: iosScreenshotMap,
  };
  const cases = [
    ['valid exact packet', () => validateEvidence(manifest, expected, new Date('2026-09-10T12:05:00Z')), false],
    ['valid dual-device iOS packet', () => validateEvidence(iosManifest, iosExpected, new Date('2026-09-10T12:05:00Z')), false],
    ['valid reviewer', () => validateReviewerAccess({ android: { username: 'reviewer@askcrump.com', password: 'long-secret-value' } }, 'android'), false],
    ['valid iOS reviewer contact', () => validateReviewerAccess({ ios: {
      username: 'reviewer@askcrump.com',
      password: 'long-secret-value',
      contact: { firstName: 'Review', lastName: 'Contact', email: 'reviewer@askcrump.test', phone: '+12025550123' },
    } }, 'ios'), false],
    ['wrong platform', () => validateEvidence({ ...manifest, platform: 'ios' }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong build', () => validateEvidence({ ...manifest, buildNumber: 1 }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['stale evidence', () => validateEvidence(manifest, expected, new Date('2026-10-10T12:05:00Z')), true],
    ['wrong artifact hash', () => validateEvidence({ ...manifest, artifact: { ...manifest.artifact, sha256: 'b'.repeat(64) } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['missing screenshot', () => validateEvidence({ ...manifest, screenshots: manifest.screenshots.slice(0, 3) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong screenshot dimensions', () => validateEvidence({ ...manifest, screenshots: manifest.screenshots.map((item, index) => index ? item : { ...item, width: 720 }) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong screenshot device', () => validateEvidence({ ...manifest, screenshots: manifest.screenshots.map((item, index) => index ? item : { ...item, device: 'ipad-13' }) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['extra evidence field', () => validateEvidence({ ...manifest, notes: 'not allowed' }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['incomplete check', () => validateEvidence({ ...manifest, checks: { ...checks, purchaseAndRestoreVerified: false } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['unknown check', () => validateEvidence({ ...manifest, checks: { ...checks, invented: true } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['placeholder reviewer', () => validateReviewerAccess({ android: { username: 'REPLACE_IN_UNTRACKED_FILE', password: 'REPLACE_IN_UNTRACKED_FILE' } }, 'android'), true],
    ['short reviewer secret', () => validateReviewerAccess({ android: { username: 'reviewer@askcrump.com', password: 'short' } }, 'android'), true],
    ['missing iOS reviewer contact', () => validateReviewerAccess({ ios: { username: 'reviewer@askcrump.com', password: 'long-secret-value' } }, 'ios'), true],
    ['invalid iOS reviewer phone', () => validateReviewerAccess({ ios: {
      username: 'reviewer@askcrump.com',
      password: 'long-secret-value',
      contact: { firstName: 'Review', lastName: 'Contact', email: 'reviewer@askcrump.test', phone: '(202) 555-0123' },
    } }, 'ios'), true],
  ];
  let passed = 0;
  for (const [name, operation, shouldFail] of cases) {
    let failed = false;
    try { await operation(); } catch (error) { failed = error instanceof PacketError; }
    if (failed !== shouldFail) throw new PacketError(`Self-test failed: ${name}.`);
    passed += 1;
  }
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), 'askcrump-store-gate-'));
  try {
    const pngBytes = (width, height, colorType = 2) => {
      const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
      const header = Buffer.alloc(25);
      header.writeUInt32BE(13, 0);
      header.write('IHDR', 4, 'ascii');
      header.writeUInt32BE(width, 8);
      header.writeUInt32BE(height, 12);
      header[16] = 8;
      header[17] = colorType;
      const ending = Buffer.alloc(12);
      ending.write('IEND', 4, 'ascii');
      return Buffer.concat([signature, header, ending]);
    };
    const androidDirectory = path.join(temporaryRoot, 'android');
    await mkdir(androidDirectory);
    const bytes = pngBytes(1080, 1920);
    for (let index = 1; index <= 4; index += 1) {
      await writeFile(path.join(androidDirectory, `0${index}.png`), bytes);
    }
    const androidScreenshots = await screenshotHashes(androidDirectory, 'android');
    if (androidScreenshots.size !== 4) throw new PacketError('Self-test failed: Android screenshot inventory.');
    if ((await sha256File(path.join(androidDirectory, '01.png'))) !== createHash('sha256').update(bytes).digest('hex')) {
      throw new PacketError('Self-test failed: file SHA-256.');
    }
    const iosDirectory = path.join(temporaryRoot, 'ios');
    await mkdir(path.join(iosDirectory, 'iphone'), { recursive: true });
    await mkdir(path.join(iosDirectory, 'ipad'), { recursive: true });
    await writeFile(path.join(iosDirectory, 'iphone', '01.png'), pngBytes(1320, 2868));
    await writeFile(path.join(iosDirectory, 'ipad', '01.png'), pngBytes(2064, 2752));
    const iosScreenshots = await screenshotHashes(iosDirectory, 'ios');
    if (iosScreenshots.size !== 2 || !iosScreenshots.has('iphone/01.png') || !iosScreenshots.has('ipad/01.png')) {
      throw new PacketError('Self-test failed: iOS device screenshot inventory.');
    }
    let transparentRejected = false;
    try { inspectPng(pngBytes(1080, 1920, 6)); } catch (error) { transparentRejected = error instanceof PacketError; }
    if (!transparentRejected) throw new PacketError('Self-test failed: transparent PNG rejection.');
    let wrongAppleSizeRejected = false;
    try { validateScreenshotDimensions({ width: 1080, height: 1920 }, 'ios', 'iphone-6.9'); } catch (error) { wrongAppleSizeRejected = error instanceof PacketError; }
    if (!wrongAppleSizeRejected) throw new PacketError('Self-test failed: Apple screenshot dimensions.');
    const jpeg = Buffer.from([
      0xff, 0xd8, 0xff, 0xc0, 0x00, 0x11, 0x08, 0x07, 0x80, 0x04, 0x38, 0x03,
      0x01, 0x11, 0x00, 0x02, 0x11, 0x00, 0x03, 0x11, 0x00, 0xff, 0xd9,
    ]);
    const jpegDetails = inspectJpeg(jpeg);
    if (jpegDetails?.width !== 1080 || jpegDetails?.height !== 1920) throw new PacketError('Self-test failed: JPEG dimensions.');
    passed += 6;
  } finally {
    const resolved = path.resolve(temporaryRoot);
    const expectedPrefix = `${path.resolve(tmpdir())}${path.sep}`;
    if (!resolved.startsWith(expectedPrefix) || !path.basename(resolved).startsWith('askcrump-store-gate-')) {
      throw new PacketError('Self-test temporary directory boundary is invalid.');
    }
    await rm(resolved, { recursive: true, force: true });
  }
  console.log(`Store submission packet gate self-test passed ${passed}/${cases.length + 6} cases.`);
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  if (args.selfTest) return await selfTest();
  verifyStoreMetadataSource();
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
  const screenshots = await screenshotHashes(path.resolve(args.screenshots), platform);
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
