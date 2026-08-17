import { readFile, writeFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const buildPath = new URL('android/app/build.gradle', root);
const marker = '// ASK CRUMP RELEASE SIGNING: BEGIN';

let source;
try {
  source = await readFile(buildPath, 'utf8');
} catch {
  throw new Error('Android project not found. Run store preparation first.');
}

if (!source.includes(marker)) {
  const variables = `
// ASK CRUMP RELEASE SIGNING: BEGIN
// Credentials are read only from the release process environment.
// Never hard-code keystore paths or passwords into generated Gradle source.
def askCrumpSigning = [
    file: System.getenv("ASKCRUMP_ANDROID_KEYSTORE_FILE"),
    alias: System.getenv("ASKCRUMP_ANDROID_KEY_ALIAS"),
    storePassword: System.getenv("ASKCRUMP_ANDROID_KEYSTORE_PASSWORD"),
    keyPassword: System.getenv("ASKCRUMP_ANDROID_KEY_PASSWORD")
]
def askCrumpSigningValues = askCrumpSigning.values().findAll { it != null && !it.trim().isEmpty() }
def askCrumpSigningReady = askCrumpSigningValues.size() == 4
if (askCrumpSigningValues.size() > 0 && !askCrumpSigningReady) {
    throw new GradleException("Ask Crump Android signing is partially configured. Set all four ASKCRUMP_ANDROID_* variables or none of them.")
}
// ASK CRUMP RELEASE SIGNING: END

`;

  const androidIndex = source.indexOf('android {');
  if (androidIndex < 0) {
    throw new Error('Could not locate the Android Gradle android block.');
  }
  source = `${source.slice(0, androidIndex)}${variables}${source.slice(androidIndex)}`;

  const androidBlockPattern = /android\s*\{\s*\r?\n/;
  if (!androidBlockPattern.test(source)) {
    throw new Error('Could not reopen the Android Gradle android block.');
  }

  const signingConfig = `    // ASK CRUMP RELEASE SIGNING CONFIG: BEGIN
    signingConfigs {
        release {
            if (askCrumpSigningReady) {
                storeFile file(askCrumpSigning.file)
                storePassword askCrumpSigning.storePassword
                keyAlias askCrumpSigning.alias
                keyPassword askCrumpSigning.keyPassword
            }
        }
    }
    // ASK CRUMP RELEASE SIGNING CONFIG: END

`;
  source = source.replace(androidBlockPattern, match => `${match}${signingConfig}`);

  const releasePattern = /(buildTypes\s*\{\s*\r?\n\s*release\s*\{\s*\r?\n)/;
  if (!releasePattern.test(source)) {
    throw new Error('Could not locate the Android release buildType.');
  }
  source = source.replace(
    releasePattern,
    `$1            if (askCrumpSigningReady) {\n                signingConfig signingConfigs.release\n            }\n`,
  );

  await writeFile(buildPath, source);
  console.log('Android release signing scaffold added to generated Gradle source.');
} else {
  console.log('Android release signing scaffold already present.');
}

const values = [
  process.env.ASKCRUMP_ANDROID_KEYSTORE_FILE,
  process.env.ASKCRUMP_ANDROID_KEY_ALIAS,
  process.env.ASKCRUMP_ANDROID_KEYSTORE_PASSWORD,
  process.env.ASKCRUMP_ANDROID_KEY_PASSWORD,
].filter(value => String(value || '').trim());

if (values.length === 4) {
  console.log('Android signing environment: complete.');
} else if (values.length > 0) {
  throw new Error('Android signing environment is partial. Set all four ASKCRUMP_ANDROID_* variables or clear them.');
} else {
  console.log('Android signing environment: not loaded. Generated release remains unsigned until owner credentials are supplied.');
}
