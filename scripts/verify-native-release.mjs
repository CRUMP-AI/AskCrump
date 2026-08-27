import { access, readFile, readdir } from 'node:fs/promises';
import { constants } from 'node:fs';

const root = new URL('../', import.meta.url);
const target = String(process.argv[2] || 'all').toLowerCase();
if (!['all', 'android', 'ios'].includes(target)) {
  throw new Error('Native target must be android, ios, or all.');
}

const packageMetadata = JSON.parse(await readFile(new URL('package.json', root), 'utf8'));
const expectedVersion = String(process.env.STORE_VERSION_NAME || packageMetadata.version || '').trim();
if (!/^\d+\.\d+\.\d+$/.test(expectedVersion)) {
  throw new Error(`Invalid STORE_VERSION_NAME: ${expectedVersion || '(empty)'}`);
}
const versionParts = expectedVersion.split('.').map(Number);
const defaultBuildNumber = versionParts[0] * 10_000 + versionParts[1] * 100 + versionParts[2];
const expectedBuildNumber = Number(process.env.STORE_BUILD_NUMBER || defaultBuildNumber);
if (!Number.isSafeInteger(expectedBuildNumber) || expectedBuildNumber < 1 || expectedBuildNumber > 2_100_000_000) {
  throw new Error('STORE_BUILD_NUMBER must be a positive integer no greater than 2100000000.');
}

const failures = [];
const warnings = [];

async function exists(url) {
  try { await access(url, constants.F_OK); return true; } catch { return false; }
}

async function walk(url, predicate, depth = 0) {
  if (depth > 8 || !(await exists(url))) return [];
  const entries = await readdir(url, { withFileTypes: true });
  const matches = [];
  for (const entry of entries) {
    const child = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, url);
    if (entry.isDirectory()) matches.push(...await walk(child, predicate, depth + 1));
    else if (predicate(entry.name, child)) matches.push(child);
  }
  return matches;
}

const distIndex = new URL('dist/index.html', root);
const runtimeConfigPath = new URL('dist/runtime-body-v1.js', root);
let runtimeConfig = '';
if (!(await exists(distIndex))) {
  failures.push('dist/index.html is missing. Run `npm run build`.');
} else {
  const source = await readFile(distIndex, 'utf8');
  if (!source.includes('id="appContainer"')) failures.push('The native index does not contain the Ask Crump app shell.');
}
if (!(await exists(runtimeConfigPath))) {
  failures.push('dist/runtime-body-v1.js is missing. Run `npm run build`.');
} else {
  runtimeConfig = await readFile(runtimeConfigPath, 'utf8');
}

if (target === 'all' || target === 'android') {
  if (/"revenueCatGoogleApiKey":\s*""/.test(runtimeConfig)) {
    warnings.push('REVENUECAT_ANDROID_PUBLIC_SDK_KEY was empty during the native build; Play Billing cannot be submitted until it is configured and rebuilt.');
  }
  const variables = new URL('android/variables.gradle', root);
  if (!(await exists(variables))) {
    failures.push('Android project is missing. Run `npx cap add android`.');
  } else {
    const source = await readFile(variables, 'utf8');
    const compileSdk = Number(source.match(/compileSdkVersion\s*=\s*(\d+)/)?.[1] || 0);
    const targetSdk = Number(source.match(/targetSdkVersion\s*=\s*(\d+)/)?.[1] || 0);
    if (compileSdk < 36) failures.push(`Android compileSdkVersion is ${compileSdk || 'unreadable'}; expected at least 36.`);
    if (targetSdk < 36) failures.push(`Android targetSdkVersion is ${targetSdk || 'unreadable'}; expected at least 36.`);

    const buildPath = new URL('android/app/build.gradle', root);
    if (!(await exists(buildPath))) {
      failures.push('android/app/build.gradle is missing.');
    } else {
      const buildSource = await readFile(buildPath, 'utf8');
      if (!buildSource.includes('namespace = "com.clevercrump.askcrump"')) failures.push('Android namespace does not match the permanent package ID.');
      if (!buildSource.includes('applicationId "com.clevercrump.askcrump"')) failures.push('Android applicationId does not match the permanent package ID.');
      const versionCode = Number(buildSource.match(/versionCode\s+(\d+)/)?.[1] || 0);
      const versionName = buildSource.match(/versionName\s+["']([^"']+)["']/)?.[1] || '';
      if (versionCode !== expectedBuildNumber) failures.push(`Android versionCode is ${versionCode || 'unreadable'}; expected ${expectedBuildNumber}.`);
      if (versionName !== expectedVersion) failures.push(`Android versionName is ${versionName || 'unreadable'}; expected ${expectedVersion}.`);
    }

    const androidIcons = await walk(new URL('android/app/src/main/res/', root), name => /^ic_launcher.*\.(png|webp|xml)$/.test(name));
    if (androidIcons.length < 4) failures.push('Generated Android launcher icons were not found. Run `npm run native:assets`.');

    const manifestPath = new URL('android/app/src/main/AndroidManifest.xml', root);
    if (!(await exists(manifestPath))) {
      failures.push('AndroidManifest.xml is missing.');
    } else {
      const manifest = await readFile(manifestPath, 'utf8');
      if (!manifest.includes('android:allowBackup="false"')) failures.push('Android local backup must be disabled for account-linked session data. Run `npm run native:configure`.');
      if (!manifest.includes('android:usesCleartextTraffic="false"')) failures.push('Android cleartext traffic must be disabled. Run `npm run native:configure`.');
      if (!manifest.includes('android.permission.POST_NOTIFICATIONS')) failures.push('Android POST_NOTIFICATIONS permission is missing. Run `npm run native:configure`.');
      if (!manifest.includes('crump_check_ins')) failures.push('Android notification channel metadata is missing. Run `npm run native:configure`.');
    }
    if (!(await exists(new URL('android/app/google-services.json', root)))) warnings.push('android/app/google-services.json is missing; FCM registration will not work until it is added.');
  }
}

if (target === 'all' || target === 'ios') {
  if (/"revenueCatAppleApiKey":\s*""/.test(runtimeConfig)) {
    warnings.push('REVENUECAT_IOS_PUBLIC_SDK_KEY was empty during the native build; App Store billing cannot be submitted until it is configured and rebuilt.');
  }
  const iosRoot = new URL('ios/', root);
  if (!(await exists(iosRoot))) {
    failures.push('iOS project is missing. Run `npx cap add ios`.');
  } else {
    const appIcons = await walk(iosRoot, name => name === 'Contents.json');
    if (!appIcons.some(url => url.pathname.includes('AppIcon.appiconset'))) failures.push('Generated iOS AppIcon set was not found. Run `npm run native:assets`.');

    const appDelegate = new URL('ios/App/App/AppDelegate.swift', root);
    if (!(await exists(appDelegate))) {
      failures.push('iOS AppDelegate.swift was not found.');
    } else {
      const source = await readFile(appDelegate, 'utf8');
      if (!source.includes('capacitorDidRegisterForRemoteNotifications')) failures.push('iOS push callbacks are missing. Run `npm run native:configure`.');
    }

    const projectPath = new URL('ios/App/App.xcodeproj/project.pbxproj', root);
    if (!(await exists(projectPath))) {
      failures.push('The iOS Xcode project file is missing.');
    } else {
      const project = await readFile(projectPath, 'utf8');
      if (!project.includes('PRODUCT_BUNDLE_IDENTIFIER = com.clevercrump.askcrump;')) {
        failures.push('iOS bundle ID does not match the permanent app identifier.');
      }
      const marketingVersions = [...project.matchAll(/MARKETING_VERSION = ([^;]+);/g)].map(match => match[1].trim());
      const buildNumbers = [...project.matchAll(/CURRENT_PROJECT_VERSION = ([^;]+);/g)].map(match => Number(match[1].trim()));
      if (!marketingVersions.length || marketingVersions.some(value => value !== expectedVersion)) {
        failures.push(`iOS MARKETING_VERSION must be ${expectedVersion}.`);
      }
      if (!buildNumbers.length || buildNumbers.some(value => value !== expectedBuildNumber)) {
        failures.push(`iOS CURRENT_PROJECT_VERSION must be ${expectedBuildNumber}.`);
      }
      if (!project.includes('PrivacyInfo.xcprivacy in Resources')) failures.push('PrivacyInfo.xcprivacy is not included in the iOS Resources build phase.');
    }

    const privacyManifest = new URL('ios/App/App/PrivacyInfo.xcprivacy', root);
    if (!(await exists(privacyManifest))) {
      failures.push('The app PrivacyInfo.xcprivacy file is missing. Run `npm run native:configure`.');
    } else {
      const source = await readFile(privacyManifest, 'utf8');
      if (!source.includes('<key>NSPrivacyTracking</key>') || !source.includes('<key>NSPrivacyAccessedAPITypes</key>')) {
        failures.push('PrivacyInfo.xcprivacy does not contain the required privacy-manifest keys.');
      }
    }

    const entitlementFiles = await walk(iosRoot, name => name.endsWith('.entitlements'));
    if (!entitlementFiles.length) warnings.push('No iOS entitlements file was found. Enable Push Notifications and Background Modes in Xcode before archiving.');
  }
}

for (const warning of warnings) console.warn(`WARNING: ${warning}`);
if (failures.length) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}
console.log(`Native ${target} release source checks passed for Ask Crump ${expectedVersion} (${expectedBuildNumber}).`);
console.log('Complete signed archive, physical-device, billing, and store-console validation next.');
