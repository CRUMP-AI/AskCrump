import { access, readFile, readdir } from 'node:fs/promises';
import { constants } from 'node:fs';

const root = new URL('../', import.meta.url);
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
if (!(await exists(distIndex))) {
  failures.push('dist/index.html is missing. Run `npm run build`.');
} else {
  const source = await readFile(distIndex, 'utf8');
  if (!source.includes('id="appContainer"')) failures.push('The native index does not contain the Ask Crump app shell.');
}

const variables = new URL('android/variables.gradle', root);
if (!(await exists(variables))) {
  failures.push('Android project is missing. Run `npx cap add android`.');
} else {
  const source = await readFile(variables, 'utf8');
  const compile = Number(source.match(/compileSdkVersion\s*=\s*(\d+)/)?.[1] || 0);
  const target = Number(source.match(/targetSdkVersion\s*=\s*(\d+)/)?.[1] || 0);
  if (compile < 36) failures.push(`Android compileSdkVersion is ${compile || 'unreadable'}; expected at least 36.`);
  if (target < 36) failures.push(`Android targetSdkVersion is ${target || 'unreadable'}; expected at least 36.`);
  const androidIcons = await walk(new URL('android/app/src/main/res/', root), name => /^ic_launcher.*\.(png|webp|xml)$/.test(name));
  if (androidIcons.length < 4) failures.push('Generated Android launcher icons were not found. Run `npm run native:assets`.');
  const manifestPath = new URL('android/app/src/main/AndroidManifest.xml', root);
  const manifest = await readFile(manifestPath, 'utf8');
  if (!manifest.includes('android.permission.POST_NOTIFICATIONS')) failures.push('Android POST_NOTIFICATIONS permission is missing. Run `npm run native:configure`.');
  if (!manifest.includes('crump_check_ins')) failures.push('Android notification channel metadata is missing. Run `npm run native:configure`.');
  if (!(await exists(new URL('android/app/google-services.json', root)))) warnings.push('android/app/google-services.json is missing; FCM registration will not work until it is added.');
}

const iosRoot = new URL('ios/', root);
if (!(await exists(iosRoot))) {
  failures.push('iOS project is missing. Run `npx cap add ios`.');
} else {
  const appIcons = await walk(iosRoot, name => name === 'Contents.json');
  if (!appIcons.some(url => url.pathname.includes('AppIcon.appiconset'))) failures.push('Generated iOS AppIcon set was not found. Run `npm run native:assets`.');
  const appDelegate = new URL('ios/App/App/AppDelegate.swift', root);
  if (!(await exists(appDelegate))) failures.push('iOS AppDelegate.swift was not found.');
  else {
    const source = await readFile(appDelegate, 'utf8');
    if (!source.includes('capacitorDidRegisterForRemoteNotifications')) failures.push('iOS push callbacks are missing. Run `npm run native:configure`.');
  }
  const entitlementFiles = await walk(iosRoot, name => name.endsWith('.entitlements'));
  if (!entitlementFiles.length) warnings.push('No iOS entitlements file was found. Enable Push Notifications in Xcode before archiving.');
  const privacyManifests = await walk(iosRoot, name => name === 'PrivacyInfo.xcprivacy');
  if (!privacyManifests.length) {
    warnings.push('No PrivacyInfo.xcprivacy file was found. Generate the native dependencies, inspect Xcode recommendations, and add accurate required-reason declarations before upload.');
  }
}

for (const warning of warnings) console.warn(`WARNING: ${warning}`);
if (failures.length) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exit(1);
}
console.log('Native release source checks passed. Complete signed archive/device/store validation next.');
