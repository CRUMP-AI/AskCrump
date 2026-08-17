import { access, readFile, realpath } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootUrl = new URL('../', import.meta.url);
const rootPath = path.resolve(fileURLToPath(rootUrl));
const requireAndroidSigning = process.argv.includes('--require-android-signing');

async function exists(target) {
  try {
    await access(target, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(1);
}

const packageJson = await readFile(new URL('package.json', rootUrl), 'utf8');
const capacitorConfig = await readFile(new URL('capacitor.config.ts', rootUrl), 'utf8');
const gitignore = await readFile(new URL('.gitignore', rootUrl), 'utf8');
const prepareScript = await readFile(new URL('scripts/prepare-store-release.mjs', rootUrl), 'utf8');

if (!capacitorConfig.includes('com.clevercrump.askcrump')) {
  fail('Capacitor app ID must remain com.clevercrump.askcrump.');
}
if (!packageJson.includes('"store:signing:check"')) {
  fail('package.json is missing the mobile signing verification command.');
}
if (!prepareScript.includes('scripts/configure-android-signing.mjs')) {
  fail('Android store preparation is not wired to the signing scaffold.');
}

for (const pattern of [
  '*.jks',
  '*.keystore',
  '*.p8',
  '*.p12',
  '*.mobileprovision',
  'google-services.json',
  'GoogleService-Info.plist',
  'signing/',
  'credentials/',
]) {
  if (!gitignore.includes(pattern)) {
    fail(`.gitignore is missing signing protection: ${pattern}`);
  }
}

const gitCommand = process.platform === 'win32' ? 'git.exe' : 'git';
const git = spawnSync(gitCommand, ['--no-pager', '-C', rootPath, 'ls-files', '-z'], {
  encoding: 'utf8',
  shell: false,
});

if (git.error) {
  fail(`Could not launch Git to inspect tracked files: ${git.error.message}`);
}
if (git.status !== 0) {
  fail('Could not inspect Git-tracked files.');
}

const tracked = git.stdout.split('\0').filter(Boolean);
const sensitivePatterns = [
  /(^|\/)google-services\.json$/i,
  /(^|\/)GoogleService-Info\.plist$/i,
  /\.(jks|keystore|p8|p12|mobileprovision|provisionprofile|key)$/i,
  /(^|\/)(key|keystore)\.properties$/i,
  /(^|\/).*service[-_]?account.*\.json$/i,
  /(^|\/)AuthKey_[^/]+\.p8$/i,
];
const trackedSensitive = tracked.filter(file => sensitivePatterns.some(pattern => pattern.test(file)));
if (trackedSensitive.length) {
  fail(`Signing/store credential material is tracked by Git: ${trackedSensitive.join(', ')}`);
}

const signing = {
  file: String(process.env.ASKCRUMP_ANDROID_KEYSTORE_FILE || '').trim(),
  alias: String(process.env.ASKCRUMP_ANDROID_KEY_ALIAS || '').trim(),
  storePassword: String(process.env.ASKCRUMP_ANDROID_KEYSTORE_PASSWORD || '').trim(),
  keyPassword: String(process.env.ASKCRUMP_ANDROID_KEY_PASSWORD || '').trim(),
};

const present = Object.values(signing).filter(Boolean).length;

if (present > 0 && present < 4) {
  fail('Android signing environment is partial. Set all four ASKCRUMP_ANDROID_* variables or clear them.');
}
if (requireAndroidSigning && present !== 4) {
  fail('A signed Android release requires all four ASKCRUMP_ANDROID_* variables.');
}

if (present === 4) {
  const keystorePath = path.resolve(signing.file);
  if (!(await exists(keystorePath))) {
    fail(`Android upload keystore does not exist at ${keystorePath}.`);
  }

  const realRoot = await realpath(rootPath);
  const realKeystore = await realpath(keystorePath);
  const relative = path.relative(realRoot, realKeystore);

  if (!relative.startsWith('..') && !path.isAbsolute(relative)) {
    fail('Android upload keystore must live outside the Git repository.');
  }

  console.log(`Android signing credentials: complete (alias: ${signing.alias}).`);
} else {
  console.log('Android signing credentials: not loaded in this shell.');
}

const androidBuild = new URL('android/app/build.gradle', rootUrl);
if (await exists(androidBuild)) {
  const gradle = await readFile(androidBuild, 'utf8');
  if (!gradle.includes('// ASK CRUMP RELEASE SIGNING: BEGIN')) {
    fail('Generated Android project exists but does not contain the release signing scaffold.');
  }
  console.log('Generated Android signing scaffold: verified.');
}

console.log('Tracked mobile signing secrets: none detected.');
console.log('Mobile signing source controls verified.');
