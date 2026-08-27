import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const variablesPath = new URL('android/variables.gradle', root);
const target = String(process.argv[2] || 'all').toLowerCase();
if (!['all', 'android', 'ios'].includes(target)) {
  throw new Error('Native target must be android, ios, or all.');
}

const packageMetadata = JSON.parse(await readFile(new URL('package.json', root), 'utf8'));
const versionName = String(process.env.STORE_VERSION_NAME || packageMetadata.version || '').trim();
if (!/^\d+\.\d+\.\d+$/.test(versionName)) {
  throw new Error(`Invalid STORE_VERSION_NAME: ${versionName || '(empty)'}`);
}
const numericVersion = versionName.split(/[-+]/, 1)[0].split('.').map(Number);
const defaultBuildNumber = numericVersion[0] * 10_000 + numericVersion[1] * 100 + numericVersion[2];
const buildNumber = Number(process.env.STORE_BUILD_NUMBER || defaultBuildNumber);
if (!Number.isSafeInteger(buildNumber) || buildNumber < 1 || buildNumber > 2_100_000_000) {
  throw new Error('STORE_BUILD_NUMBER must be a positive integer no greater than 2100000000.');
}

async function patchAndroidSdk() {
  let source;
  try {
    source = await readFile(variablesPath, 'utf8');
  } catch {
    throw new Error('Android project not found. Run `npx cap add android` first.');
  }
  for (const [pattern, replacement] of [
    [/compileSdkVersion\s*=\s*\d+/, 'compileSdkVersion = 36'],
    [/targetSdkVersion\s*=\s*\d+/, 'targetSdkVersion = 36'],
  ]) {
    if (!pattern.test(source)) throw new Error(`Could not find ${replacement.split(' = ')[0]} in android/variables.gradle.`);
    source = source.replace(pattern, replacement);
  }
  await writeFile(variablesPath, source);
}

async function patchAndroidVersion() {
  const buildPath = new URL('android/app/build.gradle', root);
  let source = await readFile(buildPath, 'utf8');
  if (!/versionCode\s+\d+/.test(source) || !/versionName\s+["'][^"']+["']/.test(source)) {
    throw new Error('Could not locate Android versionCode/versionName in android/app/build.gradle.');
  }
  source = source
    .replace(/versionCode\s+\d+/, `versionCode ${buildNumber}`)
    .replace(/versionName\s+["'][^"']+["']/, `versionName "${versionName}"`);
  await writeFile(buildPath, source);
}

async function patchAndroidNotifications() {
  const manifestPath = new URL('android/app/src/main/AndroidManifest.xml', root);
  let manifest = await readFile(manifestPath, 'utf8');
  if (/android:allowBackup="[^"]*"/.test(manifest)) {
    manifest = manifest.replace(/android:allowBackup="[^"]*"/, 'android:allowBackup="false"');
  } else {
    manifest = manifest.replace('<application', '<application\n        android:allowBackup="false"');
  }
  if (/android:usesCleartextTraffic="[^"]*"/.test(manifest)) {
    manifest = manifest.replace(/android:usesCleartextTraffic="[^"]*"/, 'android:usesCleartextTraffic="false"');
  } else {
    manifest = manifest.replace('<application', '<application\n        android:usesCleartextTraffic="false"');
  }
  if (!manifest.includes('android.permission.POST_NOTIFICATIONS')) {
    manifest = manifest.replace('<application', '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n\n    <application');
  }
  const metadata = `
        <meta-data
            android:name="com.google.firebase.messaging.default_notification_icon"
            android:resource="@drawable/ic_stat_crump" />
        <meta-data
            android:name="com.google.firebase.messaging.default_notification_channel_id"
            android:value="crump_check_ins" />`;
  if (!manifest.includes('com.google.firebase.messaging.default_notification_channel_id')) {
    manifest = manifest.replace('</application>', `${metadata}\n    </application>`);
  }
  await writeFile(manifestPath, manifest);

  const drawableDir = new URL('android/app/src/main/res/drawable/', root);
  await mkdir(drawableDir, { recursive: true });
  await writeFile(new URL('ic_stat_crump.xml', drawableDir), `<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24">
    <path android:fillColor="#FFFFFFFF" android:pathData="M12,2A10,10 0,1 0,18.32 19.74L22,23.41L23.41,22L19.74,18.32A10,10 0,0 0,12 2M12,4A8,8 0,1 1,4 12A8,8 0,0 1,12 4M14.9,8.4A4.5,4.5 0,1 0,14.9 15.6L13.5,14.2A2.5,2.5 0,1 1,13.5 9.8Z" />
</vector>
`);
}

async function patchIosPushCallbacks() {
  const appDelegatePath = new URL('ios/App/App/AppDelegate.swift', root);
  let source;
  try {
    source = await readFile(appDelegatePath, 'utf8');
  } catch {
    throw new Error('iOS project not found. Run `npx cap add ios` first.');
  }
  if (!source.includes('capacitorDidRegisterForRemoteNotifications')) {
    const callbacks = `

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
    }
`;
    const finalBrace = source.lastIndexOf('}');
    if (finalBrace < 0) throw new Error('Could not patch ios/App/App/AppDelegate.swift.');
    source = `${source.slice(0, finalBrace)}${callbacks}${source.slice(finalBrace)}`;
    await writeFile(appDelegatePath, source);
  }
}

async function patchIosVersionAndPrivacy() {
  const projectPath = new URL('ios/App/App.xcodeproj/project.pbxproj', root);
  let project = await readFile(projectPath, 'utf8');
  if (!/CURRENT_PROJECT_VERSION = [^;]+;/.test(project) || !/MARKETING_VERSION = [^;]+;/.test(project)) {
    throw new Error('Could not locate iOS version settings in project.pbxproj.');
  }
  project = project
    .replace(/CURRENT_PROJECT_VERSION = [^;]+;/g, `CURRENT_PROJECT_VERSION = ${buildNumber};`)
    .replace(/MARKETING_VERSION = [^;]+;/g, `MARKETING_VERSION = ${versionName};`);

  const privacySource = await readFile(new URL('resources/PrivacyInfo.xcprivacy', root), 'utf8');
  await writeFile(new URL('ios/App/App/PrivacyInfo.xcprivacy', root), privacySource);

  if (!project.includes('PrivacyInfo.xcprivacy')) {
    const buildId = 'C0DEC0DE5A41000000000001';
    const fileId = 'C0DEC0DE5A41000000000002';
    const buildFile = `\t\t${buildId} /* PrivacyInfo.xcprivacy in Resources */ = {isa = PBXBuildFile; fileRef = ${fileId} /* PrivacyInfo.xcprivacy */; };\n`;
    const fileReference = `\t\t${fileId} /* PrivacyInfo.xcprivacy */ = {isa = PBXFileReference; lastKnownFileType = text.xml; path = PrivacyInfo.xcprivacy; sourceTree = "<group>"; };\n`;

    if (!project.includes('/* End PBXBuildFile section */') || !project.includes('/* End PBXFileReference section */')) {
      throw new Error('Could not locate iOS project file sections for PrivacyInfo.xcprivacy.');
    }
    project = project
      .replace('/* End PBXBuildFile section */', `${buildFile}/* End PBXBuildFile section */`)
      .replace('/* End PBXFileReference section */', `${fileReference}/* End PBXFileReference section */`);

    const infoEntry = project.match(/^[\t ]+[A-Fa-f0-9]{24} \/\* Info\.plist \*\/,\r?$/m)?.[0];
    if (!infoEntry) throw new Error('Could not locate the iOS App group for PrivacyInfo.xcprivacy.');
    const infoIndent = infoEntry.match(/^[\t ]*/)?.[0] || '\t\t\t\t';
    project = project.replace(
      infoEntry,
      `${infoIndent}${fileId} /* PrivacyInfo.xcprivacy */,\n${infoEntry}`,
    );

    const resourcesSection = /(\/\* Begin PBXResourcesBuildPhase section \*\/[\s\S]*?files = \(\r?\n)/;
    if (!resourcesSection.test(project)) throw new Error('Could not locate the iOS Resources build phase.');
    project = project.replace(
      resourcesSection,
      `$1\t\t\t\t${buildId} /* PrivacyInfo.xcprivacy in Resources */,\n`,
    );
  }
  await writeFile(projectPath, project);
}

async function patchIosPhotoLibraryUsage() {
  const infoPath = new URL('ios/App/App/Info.plist', root);
  let source;
  try {
    source = await readFile(infoPath, 'utf8');
  } catch {
    throw new Error('iOS Info.plist was not found for Photos save configuration.');
  }

  const additions = [];
  if (!source.includes('<key>NSPhotoLibraryUsageDescription</key>')) {
    additions.push(
      '    <key>NSPhotoLibraryUsageDescription</key>\n' +
      '    <string>Ask Crump can access Photos when you choose media for your workspace.</string>'
    );
  }
  if (!source.includes('<key>NSPhotoLibraryAddUsageDescription</key>')) {
    additions.push(
      '    <key>NSPhotoLibraryAddUsageDescription</key>\n' +
      '    <string>Ask Crump saves generated images and videos to Photos when you ask it to.</string>'
    );
  }
  if (additions.length) {
    const closing = source.lastIndexOf('</dict>');
    if (closing < 0) throw new Error('Could not patch iOS Info.plist for Photos access.');
    source = `${source.slice(0, closing)}${additions.join('\n')}\n${source.slice(closing)}`;
    await writeFile(infoPath, source);
  }
}

if (target === 'all' || target === 'android') {
  await patchAndroidSdk();
  await patchAndroidVersion();
  await patchAndroidNotifications();
  console.log(`Android configured for API 36 and Ask Crump ${versionName} (${buildNumber}).`);
}
if (target === 'all' || target === 'ios') {
  await patchIosPushCallbacks();
  await patchIosPhotoLibraryUsage();
  await patchIosVersionAndPrivacy();
  console.log(`iOS configured for Ask Crump ${versionName} (${buildNumber}) with a bundled privacy manifest.`);
}
console.log('Still required in owner accounts: add google-services.json, enable iOS Push Notifications + Background Modes, and configure APNs/FCM credentials.');
