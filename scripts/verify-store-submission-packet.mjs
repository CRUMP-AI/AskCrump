import { createHash, X509Certificate } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { access, mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { deflateSync, inflateSync } from 'node:zlib';

const rootUrl = new URL('../', import.meta.url);
const rootPath = path.resolve(fileURLToPath(rootUrl));
const schema = 'ask-crump-store-submission-evidence/v3';
const bundleId = 'com.clevercrump.askcrump';
const rootKeys = [
  'accessClosure',
  'appVersion',
  'artifact',
  'buildNumber',
  'checks',
  'ciReceipts',
  'console',
  'observedAt',
  'operator',
  'platform',
  'schema',
  'screenshots',
  'source',
];
const sourceKeys = ['commit', 'repository'];
const ciReceiptKeys = ['conclusion', 'headSha', 'runId', 'url', 'workflow'];
const artifactKeys = ['file', 'sha256', 'signing'];
const signingKeys = ['certificateRole', 'certificateSha256'];
const consoleKeys = ['appRecordId', 'buildIdentity', 'channel', 'consoleRecordId', 'receiptUrl', 'status'];
const operatorKeys = ['id', 'kind', 'workOrderId'];
const accessClosureKeys = [
  'confirmedAt',
  'confirmedBy',
  'consoleAccess',
  'evidence',
  'repositoryWriteAccess',
  'signingAccess',
];
const accessEvidenceKeys = ['file', 'sha256'];
const repositoryUrl = 'https://github.com/CRUMP-AI/AskCrump';
const ciWorkflow = 'ci';
const postgresWorkflow = 'video-provider-deletion-fence-postgres';
const nativeWorkflow = Object.freeze({
  android: 'android-store-verify',
  ios: 'ios-store-verify',
});
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
  'ownerControlledSigningVerified',
  'physicalDeviceCoreJourneyVerified',
  'privacyFormsReconciled',
  'purchaseAndRestoreVerified',
  'reviewerPathVerified',
  'sessionPersistenceVerified',
  'specialistAccessRemovedOrNotUsed',
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

function normalizedCommit(value, label) {
  const commit = String(value || '').trim().toLowerCase();
  if (!/^[a-f0-9]{40}$/.test(commit)) throw new PacketError(`${label} must be a full 40-character Git commit.`);
  return commit;
}

function normalizedRunId(value, label) {
  if (typeof value !== 'string') throw new PacketError(`${label} must be a string GitHub Actions run ID.`);
  const runId = value;
  if (!/^[1-9]\d{5,19}$/.test(runId)) throw new PacketError(`${label} must be a GitHub Actions run ID.`);
  return runId;
}

function defaultAndroidBuildNumber(version) {
  const parts = String(version || '').split('.').map(Number);
  if (parts.length !== 3 || parts.some(part => !Number.isInteger(part) || part < 0 || part > 99)) {
    throw new PacketError('The package version is not a three-part store version.');
  }
  return parts[0] * 10_000 + parts[1] * 100 + parts[2];
}

function normalizedBuildNumber(platform, value, label, { cli = false } = {}) {
  if (platform === 'android') {
    if ((!cli && typeof value !== 'number') || (cli && !/^\d+$/.test(String(value)))) {
      throw new PacketError(`${label} must be a Google Play integer.`);
    }
    const buildNumber = Number(value);
    if (!Number.isSafeInteger(buildNumber) || buildNumber < 1 || buildNumber > 2_100_000_000) {
      throw new PacketError(`${label} must be between 1 and 2100000000 for Google Play.`);
    }
    return buildNumber;
  }
  if (typeof value !== 'string') throw new PacketError(`${label} must be an Apple build string.`);
  const buildNumber = value.trim();
  const parts = buildNumber.split('.');
  if (parts.length < 1 || parts.length > 3
      || !parts.every(part => /^\d+$/.test(part))
      || Number(parts[0]) < 1 || parts[0].length > 4
      || parts.slice(1).some(part => part.length > 2)) {
    throw new PacketError(`${label} must be an Apple-compatible one-to-three-part build string.`);
  }
  return buildNumber;
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
  if (value?.schema === 'ask-crump-store-submission-evidence/v2') {
    throw new PacketError('Submission evidence v2 is retired; recreate the packet from the current v3 template.');
  }
  exactKeys(value, rootKeys, 'Submission evidence');
  if (value.schema !== schema) throw new PacketError('Submission evidence schema is not current.');
  if (value.platform !== expected.platform) throw new PacketError('Submission evidence platform does not match the requested platform.');
  if (value.appVersion !== expected.version) throw new PacketError('Submission evidence version does not match package.json.');
  const declaredBuildNumber = normalizedBuildNumber(
    expected.platform,
    value.buildNumber,
    'Submission evidence build number',
  );
  if (declaredBuildNumber !== expected.buildNumber) throw new PacketError('Submission evidence build number does not match the release identity.');
  exactKeys(value.source, sourceKeys, 'Source evidence');
  if (value.source.repository !== repositoryUrl) {
    throw new PacketError('Submission evidence repository does not match Ask Crump.');
  }
  const sourceCommit = normalizedCommit(value.source.commit, 'Source commit');
  if (sourceCommit !== expected.sourceCommit) {
    throw new PacketError('Submission evidence source commit does not match the inspected checkout.');
  }

  if (!Array.isArray(value.ciReceipts) || value.ciReceipts.length !== 3) {
    throw new PacketError('CI receipt evidence must contain the three required release receipts.');
  }
  const requiredWorkflows = new Set([ciWorkflow, nativeWorkflow[expected.platform], postgresWorkflow]);
  const seenWorkflows = new Set();
  const seenRuns = new Set();
  for (const receipt of value.ciReceipts) {
    exactKeys(receipt, ciReceiptKeys, 'CI receipt evidence item');
    const workflow = String(receipt.workflow || '');
    if (!requiredWorkflows.has(workflow) || seenWorkflows.has(workflow)) {
      throw new PacketError('CI receipt workflows must be the unique required release workflows.');
    }
    const runId = normalizedRunId(receipt.runId, `CI receipt ${workflow}`);
    if (seenRuns.has(runId)) throw new PacketError('CI receipt evidence contains a duplicate run ID.');
    if (normalizedCommit(receipt.headSha, `CI receipt ${workflow} head SHA`) !== sourceCommit) {
      throw new PacketError('CI receipt head SHA does not match the inspected source commit.');
    }
    if (receipt.conclusion !== 'success') throw new PacketError('Every CI receipt must have a success conclusion.');
    if (receipt.url !== `${repositoryUrl}/actions/runs/${runId}`) {
      throw new PacketError('CI receipt URL does not match its Ask Crump run ID.');
    }
    seenWorkflows.add(workflow);
    seenRuns.add(runId);
  }
  if (seenWorkflows.size !== requiredWorkflows.size
      || [...requiredWorkflows].some(workflow => !seenWorkflows.has(workflow))) {
    throw new PacketError('CI receipt evidence is missing a required release workflow.');
  }

  exactKeys(value.console, consoleKeys, 'Store console evidence');
  const appRecordId = String(value.console.appRecordId || '').trim();
  const consoleRecordId = String(value.console.consoleRecordId || '').trim();
  const validAppRecordId = expected.platform === 'android'
    ? appRecordId === bundleId
    : /^\d{8,12}$/.test(appRecordId);
  if (!validAppRecordId || /replace|example/i.test(appRecordId)) {
    throw new PacketError('Store console evidence has no usable app record identifier.');
  }
  if (!/^\d{3,20}$/.test(consoleRecordId)
      || (expected.platform === 'ios' && consoleRecordId !== appRecordId)) {
    throw new PacketError('Store console evidence has no usable numeric console record identifier.');
  }
  if (value.console.buildIdentity !== `${expected.version}+${expected.buildNumber}`) {
    throw new PacketError('Store console build identity does not match the release identity.');
  }
  const expectedChannel = expected.platform === 'android' ? 'play-internal-testing' : 'testflight';
  if (value.console.channel !== expectedChannel || value.console.status !== 'available-to-testers') {
    throw new PacketError('Store console channel/status does not prove an available internal candidate.');
  }
  let receiptUrl;
  try { receiptUrl = new URL(value.console.receiptUrl); } catch { throw new PacketError('Store console receipt URL is invalid.'); }
  const expectedHost = expected.platform === 'android' ? 'play.google.com' : 'appstoreconnect.apple.com';
  if (receiptUrl.protocol !== 'https:' || receiptUrl.hostname !== expectedHost || receiptUrl.username
      || receiptUrl.password || receiptUrl.search || receiptUrl.hash || /replace|example/i.test(receiptUrl.href)) {
    throw new PacketError('Store console receipt URL is not a canonical private console destination.');
  }
  const receiptPathMatches = expected.platform === 'android'
    ? receiptUrl.pathname.startsWith('/console/')
      && new RegExp(`/app/${consoleRecordId}(?:/|$)`).test(receiptUrl.pathname)
    : receiptUrl.pathname.startsWith(`/apps/${appRecordId}/`)
      && receiptUrl.pathname.includes('/testflight');
  if (!receiptPathMatches) {
    throw new PacketError('Store console receipt URL does not identify the declared app and test channel.');
  }

  const observedAt = new Date(value.observedAt);
  if (!Number.isFinite(observedAt.getTime())) throw new PacketError('Submission evidence observedAt is invalid.');
  const age = now.getTime() - observedAt.getTime();
  if (age < -5 * 60_000 || age > 14 * 24 * 60 * 60_000) {
    throw new PacketError('Submission evidence must be current within fourteen days and cannot be future-dated.');
  }

  exactKeys(value.operator, operatorKeys, 'Release operator evidence');
  if (!['owner', 'release-specialist'].includes(value.operator.kind)) {
    throw new PacketError('Release operator kind must be owner or release-specialist.');
  }
  const operatorId = String(value.operator.id || '').trim();
  const workOrderId = String(value.operator.workOrderId || '').trim();
  if (!/^[a-z0-9][a-z0-9._-]{2,63}$/.test(operatorId) || /replace|example/i.test(operatorId)) {
    throw new PacketError('Release operator evidence has no usable identifier.');
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/.test(workOrderId) || /replace|example/i.test(workOrderId)) {
    throw new PacketError('Release operator evidence has no usable work order identifier.');
  }

  exactKeys(value.accessClosure, accessClosureKeys, 'Temporary access closure evidence');
  exactKeys(value.accessClosure.evidence, accessEvidenceKeys, 'Access closeout file evidence');
  const confirmedAt = new Date(value.accessClosure.confirmedAt);
  if (!Number.isFinite(confirmedAt.getTime())
      || confirmedAt.getTime() > observedAt.getTime() + 5 * 60_000
      || now.getTime() - confirmedAt.getTime() > 14 * 24 * 60 * 60_000) {
    throw new PacketError('Temporary access closure must be current and confirmed before the packet observation.');
  }
  const confirmedBy = String(value.accessClosure.confirmedBy || '').trim();
  if (!/^[a-z0-9][a-z0-9._-]{2,63}$/.test(confirmedBy) || /replace|example/i.test(confirmedBy)) {
    throw new PacketError('Temporary access closure has no usable owner confirmation.');
  }
  const consoleAccess = value.accessClosure.consoleAccess;
  const repositoryAccess = value.accessClosure.repositoryWriteAccess;
  const signingAccess = value.accessClosure.signingAccess;
  if (!['not-used', 'revoked'].includes(consoleAccess)
      || !['not-used', 'revoked'].includes(repositoryAccess)
      || !['not-used', 'revoked', 'rotated'].includes(signingAccess)) {
    throw new PacketError('Temporary access closure contains an active or unknown access status.');
  }
  if (value.operator.kind === 'owner') {
    if ([consoleAccess, repositoryAccess, signingAccess].some(status => status !== 'not-used')) {
      throw new PacketError('Owner-operated release evidence must mark specialist access not-used.');
    }
  } else if (confirmedBy === operatorId) {
    throw new PacketError('Release-specialist access must be independently closed before final packet approval.');
  }
  if (value.accessClosure.evidence.file !== expected.accessEvidenceFile
      || normalizedHash(value.accessClosure.evidence.sha256, 'Access closeout evidence hash') !== expected.accessEvidenceHash) {
    throw new PacketError('Access closeout evidence does not match the inspected file.');
  }

  exactKeys(value.artifact, artifactKeys, 'Artifact evidence');
  if (value.artifact.file !== expected.artifactFile) throw new PacketError('Artifact filename does not match the inspected file.');
  if (normalizedHash(value.artifact.sha256, 'Artifact hash') !== expected.artifactHash) {
    throw new PacketError('Artifact hash does not match the inspected file.');
  }
  exactKeys(value.artifact.signing, signingKeys, 'Signing certificate evidence');
  const expectedCertificateRole = expected.platform === 'android' ? 'play-upload' : 'apple-distribution';
  if (value.artifact.signing.certificateRole !== expectedCertificateRole
      || normalizedHash(value.artifact.signing.certificateSha256, 'Signing certificate fingerprint')
        !== expected.signingCertificateSha256) {
    throw new PacketError('Signing certificate evidence does not match the inspected owner-controlled certificate.');
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
      ? Boolean(name && path.basename(name) === name && /\.png$/i.test(name))
      : /^(?:iphone|ipad)\/[^/\\]+\.png$/i.test(name);
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

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function inspectPng(bytes) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (bytes.length < 45 || !bytes.subarray(0, 8).equals(signature)) return null;
  let offset = 8;
  let header = null;
  let hasTransparency = false;
  let ended = false;
  const imageData = [];
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    const next = offset + 12 + length;
    if (next > bytes.length) throw new PacketError('A PNG screenshot contains a truncated chunk.');
    const crcInput = bytes.subarray(offset + 4, offset + 8 + length);
    const declaredCrc = bytes.readUInt32BE(offset + 8 + length);
    if (crc32(crcInput) !== declaredCrc) throw new PacketError('A PNG screenshot contains an invalid chunk checksum.');
    if (!header) {
      if (type !== 'IHDR' || length !== 13) throw new PacketError('A PNG screenshot has no valid IHDR header.');
      header = {
        width: bytes.readUInt32BE(offset + 8),
        height: bytes.readUInt32BE(offset + 12),
        bitDepth: bytes[offset + 16],
        colorType: bytes[offset + 17],
        compression: bytes[offset + 18],
        filter: bytes[offset + 19],
        interlace: bytes[offset + 20],
      };
    }
    if (type === 'tRNS') hasTransparency = true;
    if (type === 'IDAT') imageData.push(bytes.subarray(offset + 8, offset + 8 + length));
    if (type === 'IEND') {
      if (length !== 0 || next !== bytes.length) throw new PacketError('A PNG screenshot has an invalid ending.');
      ended = true;
      break;
    }
    offset = next;
  }
  if (!header || !ended || !header.width || !header.height) throw new PacketError('A PNG screenshot is incomplete.');
  if (header.width > 3840 || header.height > 3840) throw new PacketError('A PNG screenshot has unsafe dimensions.');
  if (header.bitDepth !== 8 || header.colorType !== 2 || hasTransparency
      || header.compression !== 0 || header.filter !== 0 || header.interlace !== 0) {
    throw new PacketError('PNG screenshots must be 24-bit RGB without alpha or transparency.');
  }
  if (!imageData.length || imageData.every(chunk => chunk.length === 0)) {
    throw new PacketError('A PNG screenshot has no compressed image data.');
  }
  const rowBytes = header.width * 3 + 1;
  const expectedLength = rowBytes * header.height;
  let decoded;
  try {
    decoded = inflateSync(Buffer.concat(imageData), { maxOutputLength: expectedLength + 1 });
  } catch {
    throw new PacketError('A PNG screenshot has invalid compressed image data.');
  }
  if (decoded.length !== expectedLength) throw new PacketError('A PNG screenshot has incomplete pixel data.');
  for (let row = 0; row < header.height; row += 1) {
    if (decoded[row * rowBytes] > 4) throw new PacketError('A PNG screenshot uses an invalid row filter.');
  }
  return { format: 'png', width: header.width, height: header.height };
}

async function inspectImageFile(file) {
  const details = await stat(file);
  if (!details.isFile() || details.size < 12 || details.size > 16 * 1024 * 1024) {
    throw new PacketError('A screenshot is empty or unexpectedly large.');
  }
  const bytes = await readFile(file);
  const image = inspectPng(bytes);
  if (!image) throw new PacketError('Store screenshots must be validated PNG files.');
  const extension = path.extname(file).toLowerCase();
  if (extension !== '.png') {
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
  const files = entries.filter(entry => entry.isFile() && /\.png$/i.test(entry.name));
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
  if (argumentsList.length === 1 && argumentsList[0] === '--self-test') return { selfTest: true };
  const allowed = new Set([
    '--platform',
    '--artifact',
    '--screenshots',
    '--evidence',
    '--reviewer-access',
    '--signing-certificate',
    '--access-evidence',
    '--build-number',
  ]);
  const values = {};
  for (let index = 0; index < argumentsList.length; index += 2) {
    const name = argumentsList[index];
    const value = argumentsList[index + 1];
    if (!allowed.has(name) || !value || value.startsWith('--')) throw new PacketError('Store submission gate arguments are incomplete.');
    const key = name.slice(2);
    if (Object.hasOwn(values, key)) throw new PacketError('Store submission gate arguments cannot be repeated.');
    values[key] = value;
  }
  if (Object.keys(values).length !== allowed.size) {
    throw new PacketError('Store submission gate requires platform, artifact, screenshots, evidence, reviewer access, signing certificate, access evidence, and build number.');
  }
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

function requireIgnoredEvidenceFile(file) {
  if (!pathInsideRoot(file)) return;
  const command = process.platform === 'win32' ? 'git.exe' : 'git';
  const result = spawnSync(command, ['-C', rootPath, 'check-ignore', '--quiet', path.resolve(file)], { shell: false });
  if (result.status !== 0) throw new PacketError('Submission evidence inside the repository must be ignored by Git.');
}

function requireIgnoredAccessEvidenceFile(file) {
  if (!pathInsideRoot(file)) return;
  const command = process.platform === 'win32' ? 'git.exe' : 'git';
  const result = spawnSync(command, ['-C', rootPath, 'check-ignore', '--quiet', path.resolve(file)], { shell: false });
  if (result.status !== 0) throw new PacketError('Access closeout evidence inside the repository must be ignored by Git.');
}

function gitHeadCommit() {
  const command = process.platform === 'win32' ? 'git.exe' : 'git';
  const result = spawnSync(command, ['-C', rootPath, 'rev-parse', 'HEAD'], {
    encoding: 'utf8',
    shell: false,
  });
  if (result.status !== 0) throw new PacketError('The inspected checkout has no readable Git HEAD commit.');
  return normalizedCommit(result.stdout, 'Inspected checkout commit');
}

function requireAskCrumpOrigin() {
  const command = process.platform === 'win32' ? 'git.exe' : 'git';
  const result = spawnSync(command, ['-C', rootPath, 'remote', 'get-url', 'origin'], {
    encoding: 'utf8',
    shell: false,
  });
  const remote = String(result.stdout || '').trim().replace(/\.git$/i, '');
  const allowed = new Set([
    repositoryUrl,
    'git@github.com:CRUMP-AI/AskCrump',
    'ssh://git@github.com/CRUMP-AI/AskCrump',
  ]);
  if (result.status !== 0 || !allowed.has(remote)) {
    throw new PacketError('The inspected checkout origin is not the canonical Ask Crump repository.');
  }
}

function requireCleanCheckout() {
  const command = process.platform === 'win32' ? 'git.exe' : 'git';
  const result = spawnSync(command, ['-C', rootPath, 'status', '--porcelain', '--untracked-files=normal'], {
    encoding: 'utf8',
    shell: false,
  });
  if (result.status !== 0) throw new PacketError('The inspected checkout status could not be verified.');
  if (String(result.stdout || '').trim()) {
    throw new PacketError('The inspected checkout must be clean before a final submission packet can pass.');
  }
}

async function signingCertificateSha256(file) {
  let certificate;
  try {
    certificate = new X509Certificate(await readFile(file));
  } catch {
    throw new PacketError('Signing certificate must be a readable public X.509 PEM or DER file.');
  }
  return certificate.fingerprint256.replaceAll(':', '').toLowerCase();
}

async function selfTest() {
  const version = '5.9.76';
  const androidBuildNumber = defaultAndroidBuildNumber(version);
  const iosBuildNumber = version;
  const validHash = 'a'.repeat(64);
  const screenshotMap = new Map([
    ['01.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '1'.repeat(64) }],
    ['02.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '2'.repeat(64) }],
    ['03.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '3'.repeat(64) }],
    ['04.png', { device: 'android-phone', width: 1080, height: 1920, sha256: '4'.repeat(64) }],
  ]);
  const checks = Object.fromEntries([...commonChecks, ...platformChecks.android].map(name => [name, true]));
  const sourceCommit = 'b'.repeat(40);
  const signingCertificateHash = 'c'.repeat(64);
  const accessEvidenceHash = 'd'.repeat(64);
  const accessEvidenceFile = 'access-closeout.pdf';
  const ciReceipt = (workflow, runId) => ({
    workflow,
    runId,
    url: `${repositoryUrl}/actions/runs/${runId}`,
    headSha: sourceCommit,
    conclusion: 'success',
  });
  const manifest = {
    schema,
    platform: 'android',
    appVersion: version,
    buildNumber: androidBuildNumber,
    observedAt: '2026-09-10T12:00:00.000Z',
    source: { repository: repositoryUrl, commit: sourceCommit },
    ciReceipts: [
      ciReceipt(ciWorkflow, '35566340678'),
      ciReceipt(nativeWorkflow.android, '35566340621'),
      ciReceipt(postgresWorkflow, '35566340631'),
    ],
    operator: { kind: 'owner', id: 'owner-gregory-crump', workOrderId: 'AC-STORE-2026-09-21-01' },
    artifact: {
      file: 'ask-crump.aab',
      sha256: validHash,
      signing: { certificateRole: 'play-upload', certificateSha256: signingCertificateHash },
    },
    console: {
      appRecordId: bundleId,
      consoleRecordId: '200',
      buildIdentity: `${version}+${androidBuildNumber}`,
      channel: 'play-internal-testing',
      status: 'available-to-testers',
      receiptUrl: 'https://play.google.com/console/developers/100/app/200/internal-testing',
    },
    accessClosure: {
      consoleAccess: 'not-used',
      signingAccess: 'not-used',
      repositoryWriteAccess: 'not-used',
      confirmedAt: '2026-09-10T11:55:00.000Z',
      confirmedBy: 'owner-gregory-crump',
      evidence: { file: accessEvidenceFile, sha256: accessEvidenceHash },
    },
    screenshots: [...screenshotMap].map(([file, evidence]) => ({ file, ...evidence })),
    checks,
  };
  const expected = {
    platform: 'android', version, buildNumber: androidBuildNumber, artifactFile: 'ask-crump.aab',
    artifactHash: validHash, screenshotHashes: screenshotMap, sourceCommit,
    signingCertificateSha256: signingCertificateHash, accessEvidenceFile, accessEvidenceHash,
  };
  const iosScreenshotMap = new Map([
    ['iphone/01.png', { device: 'iphone-6.9', width: 1320, height: 2868, sha256: '5'.repeat(64) }],
    ['ipad/01.png', { device: 'ipad-13', width: 2064, height: 2752, sha256: '6'.repeat(64) }],
  ]);
  const iosManifest = {
    ...manifest,
    platform: 'ios',
    buildNumber: iosBuildNumber,
    ciReceipts: [
      ciReceipt(ciWorkflow, '35566340678'),
      ciReceipt(nativeWorkflow.ios, '35566340555'),
      ciReceipt(postgresWorkflow, '35566340631'),
    ],
    artifact: {
      file: 'ask-crump.ipa',
      sha256: validHash,
      signing: { certificateRole: 'apple-distribution', certificateSha256: signingCertificateHash },
    },
    console: {
      appRecordId: '1234567890',
      consoleRecordId: '1234567890',
      buildIdentity: `${version}+${iosBuildNumber}`,
      channel: 'testflight',
      status: 'available-to-testers',
      receiptUrl: 'https://appstoreconnect.apple.com/apps/1234567890/testflight/ios',
    },
    screenshots: [...iosScreenshotMap].map(([file, evidence]) => ({ file, ...evidence })),
    checks: Object.fromEntries([...commonChecks, ...platformChecks.ios].map(name => [name, true])),
  };
  const iosExpected = {
    platform: 'ios', version, buildNumber: iosBuildNumber, artifactFile: 'ask-crump.ipa',
    artifactHash: validHash, screenshotHashes: iosScreenshotMap, sourceCommit,
    signingCertificateSha256: signingCertificateHash, accessEvidenceFile, accessEvidenceHash,
  };
  const cases = [
    ['valid exact packet', () => validateEvidence(manifest, expected, new Date('2026-09-10T12:05:00Z')), false],
    ['valid least-privilege specialist packet', () => validateEvidence({
      ...manifest,
      operator: { kind: 'release-specialist', id: 'specialist-work-order-01', workOrderId: 'AC-STORE-2026-09-21-01' },
      accessClosure: {
        ...manifest.accessClosure,
        confirmedBy: 'owner-gregory-crump',
      },
    }, expected, new Date('2026-09-10T12:05:00Z')), false],
    ['valid dual-device iOS packet', () => validateEvidence(iosManifest, iosExpected, new Date('2026-09-10T12:05:00Z')), false],
    ['valid reviewer', () => validateReviewerAccess({ android: { username: 'reviewer@askcrump.com', password: 'long-secret-value' } }, 'android'), false],
    ['valid iOS reviewer contact', () => validateReviewerAccess({ ios: {
      username: 'reviewer@askcrump.com',
      password: 'long-secret-value',
      contact: { firstName: 'Review', lastName: 'Contact', email: 'reviewer@askcrump.test', phone: '+12025550123' },
    } }, 'ios'), false],
    ['wrong platform', () => validateEvidence({ ...manifest, platform: 'ios' }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong build', () => validateEvidence({ ...manifest, buildNumber: 1 }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['Android build above Play maximum', () => normalizedBuildNumber('android', 2_100_000_001, 'Test Android build'), true],
    ['invalid five-digit iOS build', () => normalizedBuildNumber('ios', '50976', 'Test iOS build'), true],
    ['numeric iOS build rejected', () => normalizedBuildNumber('ios', 5976, 'Test iOS build'), true],
    ['retired v2 packet', () => validateEvidence({ schema: 'ask-crump-store-submission-evidence/v2' }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['mixed self-test arguments', () => parseArguments(['--self-test', '--platform', 'android']), true],
    ['duplicate CLI argument', () => parseArguments([
      '--platform', 'android', '--artifact', 'app.aab', '--screenshots', 'shots',
      '--evidence', 'evidence.json', '--reviewer-access', 'reviewer.json',
      '--signing-certificate', 'certificate.pem', '--access-evidence', 'closeout.pdf',
      '--build-number', '50976', '--platform', 'android',
    ]), true],
    ['wrong source commit', () => validateEvidence({ ...manifest, source: { ...manifest.source, commit: 'e'.repeat(40) } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['missing CI receipt', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.slice(0, 2) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['duplicate CI workflow', () => validateEvidence({ ...manifest, ciReceipts: [manifest.ciReceipts[0], manifest.ciReceipts[1], { ...manifest.ciReceipts[1], runId: '45566340621', url: `${repositoryUrl}/actions/runs/45566340621` }] }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['duplicate CI run ID', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.map((item, index) => index === 1 ? { ...item, runId: manifest.ciReceipts[0].runId, url: manifest.ciReceipts[0].url } : item) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong native CI workflow', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.map((item, index) => index === 1 ? { ...item, workflow: nativeWorkflow.ios } : item) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong CI head', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.map((item, index) => index ? item : { ...item, headSha: 'e'.repeat(40) }) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong CI URL', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.map((item, index) => index ? item : { ...item, url: 'https://example.test/actions/runs/35566340678' }) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['numeric CI run ID', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.map((item, index) => index ? item : { ...item, runId: 35566340678 }) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['failed CI receipt', () => validateEvidence({ ...manifest, ciReceipts: manifest.ciReceipts.map((item, index) => index ? item : { ...item, conclusion: 'failure' }) }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong signing certificate', () => validateEvidence({ ...manifest, artifact: { ...manifest.artifact, signing: { ...manifest.artifact.signing, certificateSha256: 'e'.repeat(64) } } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong console record', () => validateEvidence({ ...manifest, console: { ...manifest.console, appRecordId: 'another.app' } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['console route record mismatch', () => validateEvidence({ ...manifest, console: { ...manifest.console, consoleRecordId: '201' } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['invalid iOS app record', () => validateEvidence({ ...iosManifest, console: { ...iosManifest.console, appRecordId: bundleId, consoleRecordId: bundleId } }, iosExpected, new Date('2026-09-10T12:05:00Z')), true],
    ['console URL with query', () => validateEvidence({ ...manifest, console: { ...manifest.console, receiptUrl: `${manifest.console.receiptUrl}?account=1` } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['specialist self-confirmed closeout', () => validateEvidence({
      ...manifest,
      operator: { kind: 'release-specialist', id: 'specialist-work-order-01', workOrderId: 'AC-STORE-2026-09-21-01' },
      accessClosure: { ...manifest.accessClosure, confirmedBy: 'specialist-work-order-01' },
    }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['active specialist access', () => validateEvidence({ ...manifest, accessClosure: { ...manifest.accessClosure, consoleAccess: 'active' } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['wrong access evidence hash', () => validateEvidence({ ...manifest, accessClosure: { ...manifest.accessClosure, evidence: { ...manifest.accessClosure.evidence, sha256: 'e'.repeat(64) } } }, expected, new Date('2026-09-10T12:05:00Z')), true],
    ['closeout after packet', () => validateEvidence({ ...manifest, accessClosure: { ...manifest.accessClosure, confirmedAt: '2026-09-10T12:10:01.000Z' } }, expected, new Date('2026-09-10T12:10:01Z')), true],
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
    const pngChunk = (type, data) => {
      const chunk = Buffer.alloc(data.length + 12);
      chunk.writeUInt32BE(data.length, 0);
      chunk.write(type, 4, 'ascii');
      data.copy(chunk, 8);
      chunk.writeUInt32BE(crc32(chunk.subarray(4, 8 + data.length)), 8 + data.length);
      return chunk;
    };
    const pngBytes = (width, height, colorType = 2, includeData = true) => {
      const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
      const header = Buffer.alloc(13);
      header.writeUInt32BE(width, 0);
      header.writeUInt32BE(height, 4);
      header[8] = 8;
      header[9] = colorType;
      const channels = colorType === 6 ? 4 : 3;
      const rows = Buffer.alloc((width * channels + 1) * height);
      const chunks = [signature, pngChunk('IHDR', header)];
      if (includeData) chunks.push(pngChunk('IDAT', deflateSync(rows)));
      chunks.push(pngChunk('IEND', Buffer.alloc(0)));
      return Buffer.concat(chunks);
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
    let noImageDataRejected = false;
    try { inspectPng(pngBytes(1080, 1920, 2, false)); } catch (error) { noImageDataRejected = error instanceof PacketError; }
    if (!noImageDataRejected) throw new PacketError('Self-test failed: no-IDAT PNG rejection.');
    const brokenCrc = Buffer.from(bytes);
    brokenCrc[brokenCrc.length - 1] ^= 0xff;
    let badCrcRejected = false;
    try { inspectPng(brokenCrc); } catch (error) { badCrcRejected = error instanceof PacketError; }
    if (!badCrcRejected) throw new PacketError('Self-test failed: PNG checksum rejection.');
    const jpeg = Buffer.from([
      0xff, 0xd8, 0xff, 0xc0, 0x00, 0x11, 0x08, 0x07, 0x80, 0x04, 0x38, 0x03,
      0x01, 0x11, 0x00, 0x02, 0x11, 0x00, 0x03, 0x11, 0x00, 0xff, 0xd9,
    ]);
    const jpegFile = path.join(temporaryRoot, 'unverified.jpg');
    await writeFile(jpegFile, jpeg);
    let jpegRejected = false;
    try { await inspectImageFile(jpegFile); } catch (error) { jpegRejected = error instanceof PacketError; }
    if (!jpegRejected) throw new PacketError('Self-test failed: unverified JPEG rejection.');
    passed += 8;
  } finally {
    const resolved = path.resolve(temporaryRoot);
    const expectedPrefix = `${path.resolve(tmpdir())}${path.sep}`;
    if (!resolved.startsWith(expectedPrefix) || !path.basename(resolved).startsWith('askcrump-store-gate-')) {
      throw new PacketError('Self-test temporary directory boundary is invalid.');
    }
    await rm(resolved, { recursive: true, force: true });
  }
  console.log(`Store submission packet gate self-test passed ${passed}/${cases.length + 8} cases.`);
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  if (args.selfTest) return await selfTest();
  requireCleanCheckout();
  requireAskCrumpOrigin();
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
  defaultAndroidBuildNumber(version);
  const buildNumber = normalizedBuildNumber(
    platform,
    args['build-number'],
    'Store build number',
    { cli: true },
  );
  const screenshots = await screenshotHashes(path.resolve(args.screenshots), platform);
  const artifactHash = await sha256File(artifact);
  const signingCertificateFile = path.resolve(args['signing-certificate']);
  const certificateDetails = await stat(signingCertificateFile);
  if (!certificateDetails.isFile() || certificateDetails.size < 64 || certificateDetails.size > 1024 * 1024) {
    throw new PacketError('Signing certificate is missing, empty, or unexpectedly large.');
  }
  const signingCertificateHash = await signingCertificateSha256(signingCertificateFile);
  const accessEvidenceFile = path.resolve(args['access-evidence']);
  requireIgnoredAccessEvidenceFile(accessEvidenceFile);
  const accessEvidenceDetails = await stat(accessEvidenceFile);
  if (!accessEvidenceDetails.isFile() || accessEvidenceDetails.size < 1 || accessEvidenceDetails.size > 16 * 1024 * 1024) {
    throw new PacketError('Access closeout evidence is missing, empty, or unexpectedly large.');
  }
  const accessEvidenceHash = await sha256File(accessEvidenceFile);
  const reviewerFile = path.resolve(args['reviewer-access']);
  requireIgnoredReviewerFile(reviewerFile);
  const reviewer = await readJson(reviewerFile, 'Reviewer access file', 16 * 1024);
  validateReviewerAccess(reviewer, platform);
  const evidenceFile = path.resolve(args.evidence);
  requireIgnoredEvidenceFile(evidenceFile);
  const evidence = await readJson(evidenceFile, 'Submission evidence file', 64 * 1024);
  const checkCount = validateEvidence(evidence, {
    platform,
    version,
    buildNumber,
    artifactFile: path.basename(artifact),
    artifactHash,
    screenshotHashes: screenshots,
    sourceCommit: gitHeadCommit(),
    signingCertificateSha256: signingCertificateHash,
    accessEvidenceFile: path.basename(accessEvidenceFile),
    accessEvidenceHash,
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
