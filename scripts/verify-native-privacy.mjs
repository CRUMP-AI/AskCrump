import { readFile, readdir } from 'node:fs/promises';
import { resolve, relative, sep } from 'node:path';

const root = new URL('../', import.meta.url);
const mode = String(process.argv[2] || 'source').toLowerCase();
const suppliedPath = process.argv[3] ? resolve(process.argv[3]) : '';
const failures = [];

const expectedNativePackages = [
  '@aparajita/capacitor-secure-storage',
  '@capacitor-community/media',
  '@capacitor/app',
  '@capacitor/core',
  '@capacitor/haptics',
  '@capacitor/keyboard',
  '@capacitor/network',
  '@capacitor/push-notifications',
  '@capacitor/status-bar',
  '@revenuecat/purchases-capacitor',
];

function fail(message) {
  failures.push(message);
}

function privacyDeclaration(source, dataType) {
  const marker = `<string>${dataType}</string>`;
  const markerAt = source.indexOf(marker);
  if (markerAt < 0) return '';
  const start = source.lastIndexOf('<dict>', markerAt);
  const end = source.indexOf('</dict>', markerAt);
  return start >= 0 && end >= 0 ? source.slice(start, end + '</dict>'.length) : '';
}

function containsKeyBoolean(source, key, expected) {
  const value = expected ? 'true' : 'false';
  return new RegExp(`<key>${key}</key>\\s*<${value}\\s*/>`).test(source);
}

function emptyArrayForKey(source, key) {
  return new RegExp(`<key>${key}</key>\\s*(?:<array\\s*/>|<array>\\s*</array>)`).test(source);
}

function verifyAppPrivacyManifest(source, label) {
  if (!containsKeyBoolean(source, 'NSPrivacyTracking', false)) {
    fail(`${label} must explicitly declare NSPrivacyTracking=false.`);
  }
  if (!emptyArrayForKey(source, 'NSPrivacyTrackingDomains')) {
    fail(`${label} must keep NSPrivacyTrackingDomains empty while Ask Crump has no tracking SDK.`);
  }
  if (!source.includes('<key>NSPrivacyAccessedAPITypes</key>')) {
    fail(`${label} is missing NSPrivacyAccessedAPITypes.`);
  }

  for (const dataType of [
    'NSPrivacyCollectedDataTypeName',
    'NSPrivacyCollectedDataTypeEmailAddress',
    'NSPrivacyCollectedDataTypeUserID',
    'NSPrivacyCollectedDataTypeOtherUserContent',
    'NSPrivacyCollectedDataTypePurchaseHistory',
    'NSPrivacyCollectedDataTypeDeviceID',
    'NSPrivacyCollectedDataTypeProductInteraction',
  ]) {
    const declaration = privacyDeclaration(source, dataType);
    if (!declaration) {
      fail(`${label} is missing ${dataType}.`);
      continue;
    }
    if (!containsKeyBoolean(declaration, 'NSPrivacyCollectedDataTypeLinked', true)) {
      fail(`${label} must mark ${dataType} as linked to the Ask Crump account.`);
    }
    if (!containsKeyBoolean(declaration, 'NSPrivacyCollectedDataTypeTracking', false)) {
      fail(`${label} must mark ${dataType} as not used for tracking.`);
    }
    if (!declaration.includes('NSPrivacyCollectedDataTypePurposeAppFunctionality')) {
      fail(`${label} must declare app functionality for ${dataType}.`);
    }
  }

  for (const dataType of [
    'NSPrivacyCollectedDataTypePurchaseHistory',
    'NSPrivacyCollectedDataTypeProductInteraction',
  ]) {
    const declaration = privacyDeclaration(source, dataType);
    if (declaration && !declaration.includes('NSPrivacyCollectedDataTypePurposeAnalytics')) {
      fail(`${label} must declare analytics for ${dataType}.`);
    }
  }
}

async function walk(directory, filename) {
  const matches = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const child = resolve(directory, entry.name);
    if (entry.isDirectory()) matches.push(...await walk(child, filename));
    else if (entry.name === filename) matches.push(child);
  }
  return matches;
}

async function verifySource() {
  const packageMetadata = JSON.parse(await readFile(new URL('package.json', root), 'utf8'));
  const runtimePackages = Object.keys(packageMetadata.dependencies || {})
    .filter(name => /^(?:@capacitor\/|@revenuecat\/|@aparajita\/|@capacitor-community\/)/.test(name))
    .sort();
  if (JSON.stringify(runtimePackages) !== JSON.stringify(expectedNativePackages)) {
    fail('Native runtime package inventory changed; reconcile Apple App Privacy, Google Data Safety, and this verifier before release.');
  }

  const dataSafety = await readFile(new URL('docs/DATA_SAFETY.md', root), 'utf8');
  for (const packageName of expectedNativePackages) {
    if (!dataSafety.includes(`\`${packageName}\``)) {
      fail(`docs/DATA_SAFETY.md is missing native SDK ${packageName}.`);
    }
  }
  for (const phrase of [
    'purchase history',
    'purchase reconciliation',
    'aggregate subscription and credit analytics',
    'no advertising SDK',
    'Precise location | No',
    'Contacts | No',
  ]) {
    if (!dataSafety.includes(phrase)) fail(`docs/DATA_SAFETY.md is missing the privacy boundary: ${phrase}.`);
  }

  const source = await readFile(new URL('resources/PrivacyInfo.xcprivacy', root), 'utf8');
  verifyAppPrivacyManifest(source, 'resources/PrivacyInfo.xcprivacy');

  for (const manifestPath of [
    'node_modules/@capacitor/ios/Capacitor/Capacitor/PrivacyInfo.xcprivacy',
    'node_modules/@capacitor/ios/CapacitorCordova/CapacitorCordova/PrivacyInfo.xcprivacy',
  ]) {
    let dependencyManifest = '';
    try {
      dependencyManifest = await readFile(new URL(manifestPath, root), 'utf8');
    } catch {
      fail(`${manifestPath} is missing from the locked Capacitor dependency.`);
      continue;
    }
    if (!containsKeyBoolean(dependencyManifest, 'NSPrivacyTracking', false)) {
      fail(`${manifestPath} does not explicitly declare NSPrivacyTracking=false.`);
    }
  }

  const revenueCatPodspec = await readFile(
    new URL('node_modules/@revenuecat/purchases-capacitor/RevenuecatPurchasesCapacitor.podspec', root),
    'utf8',
  );
  if (!revenueCatPodspec.includes("s.dependency 'PurchasesHybridCommon'")) {
    fail('The locked RevenueCat bridge no longer exposes its expected native Purchases dependency.');
  }
}

async function verifyIosBundle() {
  if (!suppliedPath) throw new Error('Usage: verify-native-privacy.mjs ios-bundle <App.app>');
  const manifests = await walk(suppliedPath, 'PrivacyInfo.xcprivacy');
  const rootManifest = resolve(suppliedPath, 'PrivacyInfo.xcprivacy');
  if (!manifests.includes(rootManifest)) {
    fail('The compiled iOS app bundle is missing its root PrivacyInfo.xcprivacy.');
  } else {
    const rootBytes = await readFile(rootManifest);
    if (!rootBytes.subarray(0, 6).equals(Buffer.from('bplist'))) {
      verifyAppPrivacyManifest(rootBytes.toString('utf8'), 'compiled app PrivacyInfo.xcprivacy');
    }
  }

  const normalized = manifests.map(path => relative(suppliedPath, path).split(sep).join('/'));
  for (const requiredManifest of [
    'Frameworks/Capacitor.framework/PrivacyInfo.xcprivacy',
    'Frameworks/Cordova.framework/PrivacyInfo.xcprivacy',
    'RevenueCat_RevenueCat.bundle/PrivacyInfo.xcprivacy',
    'SDWebImage_SDWebImage.bundle/PrivacyInfo.xcprivacy',
  ]) {
    if (!normalized.some(path => path.endsWith(requiredManifest))) {
      fail(`The compiled iOS app is missing ${requiredManifest}.`);
    }
  }
  console.log(`Compiled iOS privacy manifests (${normalized.length}): ${normalized.sort().join(', ')}`);
}

async function verifyAndroidManifest() {
  if (!suppliedPath) throw new Error('Usage: verify-native-privacy.mjs android-manifest <AndroidManifest.xml>');
  const manifest = await readFile(suppliedPath, 'utf8');
  const permissions = [...manifest.matchAll(/<uses-permission[^>]+android:name=["']([^"']+)["']/g)]
    .map(match => match[1]);
  for (const required of ['android.permission.INTERNET', 'android.permission.POST_NOTIFICATIONS']) {
    if (!permissions.includes(required)) fail(`The merged Android manifest is missing ${required}.`);
  }
  for (const prohibited of [
    'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_BACKGROUND_LOCATION',
    'android.permission.READ_CONTACTS',
    'android.permission.WRITE_CONTACTS',
    'android.permission.GET_ACCOUNTS',
    'android.permission.READ_CALL_LOG',
    'android.permission.WRITE_CALL_LOG',
    'android.permission.READ_SMS',
    'android.permission.SEND_SMS',
    'android.permission.RECEIVE_SMS',
    'com.google.android.gms.permission.AD_ID',
  ]) {
    if (permissions.includes(prohibited)) {
      fail(`The merged Android manifest unexpectedly requests ${prohibited}; reconcile the product and Data Safety declaration.`);
    }
  }
  console.log(`Merged Android permissions (${permissions.length}): ${[...new Set(permissions)].sort().join(', ')}`);
}

if (!['source', 'ios-bundle', 'android-manifest'].includes(mode)) {
  throw new Error('Privacy verification mode must be source, ios-bundle, or android-manifest.');
}

if (mode === 'source') await verifySource();
if (mode === 'ios-bundle') await verifyIosBundle();
if (mode === 'android-manifest') await verifyAndroidManifest();

if (failures.length) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}

console.log(`Native privacy verification passed (${mode}).`);
