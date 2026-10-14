import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const MINIMUM_XCODE_MAJOR = 26;
const MINIMUM_IPHONEOS_SDK_MAJOR = 26;

function run(command, args, label) {
  try {
    return execFileSync(command, args, { encoding: 'utf8' }).trim();
  } catch (error) {
    const detail = error instanceof Error && error.message ? ` ${error.message}` : '';
    throw new Error(`Unable to read ${label}.${detail}`);
  }
}

export function parseXcodeMajor(output) {
  const match = String(output || '').match(/^Xcode\s+(\d+)(?:\.\d+)*\s*$/im);
  return match ? Number.parseInt(match[1], 10) : null;
}

export function parseSdkMajor(output) {
  const match = String(output || '').trim().match(/^(\d+)(?:\.\d+)*$/);
  return match ? Number.parseInt(match[1], 10) : null;
}

export function verifyAppleToolchain({ xcodeVersionOutput, iphoneosSdkVersion }) {
  const failures = [];
  const xcodeMajor = parseXcodeMajor(xcodeVersionOutput);
  const sdkMajor = parseSdkMajor(iphoneosSdkVersion);

  if (xcodeMajor === null) {
    failures.push('Xcode version output could not be parsed.');
  } else if (xcodeMajor < MINIMUM_XCODE_MAJOR) {
    failures.push(`Xcode ${xcodeMajor} is below the App Store build floor of Xcode ${MINIMUM_XCODE_MAJOR}.`);
  }

  if (sdkMajor === null) {
    failures.push('iPhoneOS SDK version output could not be parsed.');
  } else if (sdkMajor < MINIMUM_IPHONEOS_SDK_MAJOR) {
    failures.push(`iPhoneOS SDK ${sdkMajor} is below the App Store build floor of iOS ${MINIMUM_IPHONEOS_SDK_MAJOR}.`);
  }

  return {
    ok: failures.length === 0,
    failures,
    xcodeMajor,
    sdkMajor,
  };
}

export function main() {
  const xcodeVersionOutput = process.env.ASKCRUMP_XCODE_VERSION_OUTPUT
    ?? run('xcodebuild', ['-version'], 'Xcode version');
  const iphoneosSdkVersion = process.env.ASKCRUMP_IPHONEOS_SDK_VERSION
    ?? run('xcrun', ['--sdk', 'iphoneos', '--show-sdk-version'], 'iPhoneOS SDK version');
  const result = verifyAppleToolchain({ xcodeVersionOutput, iphoneosSdkVersion });

  if (!result.ok) {
    for (const failure of result.failures) console.error(`Apple toolchain verification failed: ${failure}`);
    console.error('Select a GitHub runner/toolchain with Xcode 26+ and the iPhoneOS 26+ SDK before compiling.');
    return 1;
  }

  console.log(`Apple toolchain verified: Xcode ${result.xcodeMajor}+ and iPhoneOS SDK ${result.sdkMajor}+ satisfy the 26+ submission floor.`);
  return 0;
}

const invokedDirectly = process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  try {
    process.exitCode = main();
  } catch (error) {
    console.error(`Apple toolchain verification failed: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}
