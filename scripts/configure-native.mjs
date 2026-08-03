import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const variablesPath = new URL('android/variables.gradle', root);

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

async function patchAndroidNotifications() {
  const manifestPath = new URL('android/app/src/main/AndroidManifest.xml', root);
  let manifest = await readFile(manifestPath, 'utf8');
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

await patchAndroidSdk();
await patchAndroidNotifications();
await patchIosPushCallbacks();
console.log('Native configuration updated: Android API 36, notification channel/icon, and iOS push callbacks.');
console.log('Still required in owner accounts: add google-services.json, enable iOS Push Notifications + Background Modes, and configure APNs/FCM credentials.');
