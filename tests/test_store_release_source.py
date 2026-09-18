import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_store_prepare_commands_are_platform_specific():
    package = json.loads(read('package.json'))
    scripts = package['scripts']
    assert scripts['store:prepare:android'].endswith('prepare-store-release.mjs android')
    assert scripts['store:prepare:ios'].endswith('prepare-store-release.mjs ios')
    assert scripts['store:verify:metadata'].endswith('verify-store-metadata.mjs')
    assert scripts['store:verify:privacy'].endswith('verify-native-privacy.mjs source')

    prepare = read('scripts/prepare-store-release.mjs')
    assert "['android', 'ios'].includes(platform)" in prepare
    assert "['scripts/configure-native.mjs', platform]" in prepare
    assert "['scripts/verify-native-release.mjs', platform]" in prepare
    assert "['scripts/verify-store-metadata.mjs']" in prepare
    assert "['scripts/verify-native-privacy.mjs', 'source']" in prepare
    assert "platform === 'android'" in prepare
    assert "'REVENUECAT_ANDROID_PUBLIC_SDK_KEY'" in prepare
    assert "'REVENUECAT_IOS_PUBLIC_SDK_KEY'" in prepare
    assert "process.env.STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS === '1'" in prepare
    assert "String(process.env[publicBillingKeyVariable] || '').trim()" in prepare
    assert 'opt-out builds are not release-ready' in prepare
    assert "new URL('package-lock.json', root)" in prepare
    assert 'required for reproducible store preparation' in prepare
    dependency_check = "run(npm, ['ls', '--all']);"
    assert dependency_check in prepare
    assert prepare.index("new URL('package-lock.json', root)") < prepare.index(dependency_check)
    assert prepare.index(dependency_check) < prepare.index("run(npm, ['run', 'build']);")

    ci = read('.github/workflows/ci.yml')
    assert 'npm run store:verify:metadata && npm run store:verify:privacy' in ci


def test_store_prepare_public_billing_key_gate_fails_closed_and_allows_only_explicit_ci_opt_out(tmp_path):
    node = os.environ.get('ASKCRUMP_NODE_EXECUTABLE') or shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to execute the store preparation gate.')

    project = tmp_path / 'store-prepare'
    scripts = project / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / 'scripts' / 'prepare-store-release.mjs', scripts)
    shutil.copy2(ROOT / 'scripts' / 'native-api-origin.mjs', scripts)
    (project / 'android').mkdir()
    (project / 'package-lock.json').write_text('{}', encoding='utf-8')

    for filename in (
        'verify-store-metadata.mjs',
        'verify-native-privacy.mjs',
        'configure-native.mjs',
        'configure-android-signing.mjs',
        'verify-native-release.mjs',
    ):
        (scripts / filename).write_text('', encoding='utf-8')

    fake_bin = project / 'fake-bin'
    fake_bin.mkdir()
    if os.name == 'nt':
        for command in ('npm.cmd', 'npx.cmd'):
            (fake_bin / command).write_text('@echo off\r\nexit /b 0\r\n', encoding='utf-8')
    else:
        for command in ('npm', 'npx'):
            executable = fake_bin / command
            executable.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            executable.chmod(0o755)

    base_env = os.environ.copy()
    for variable in (
        'REVENUECAT_ANDROID_PUBLIC_SDK_KEY',
        'REVENUECAT_IOS_PUBLIC_SDK_KEY',
        'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS',
    ):
        base_env.pop(variable, None)
    base_env['PATH'] = str(fake_bin) + os.pathsep + base_env.get('PATH', '')

    def prepare(platform, extra_env=None):
        env = base_env.copy()
        env.update(extra_env or {})
        return subprocess.run(
            [node, str(scripts / 'prepare-store-release.mjs'), platform],
            cwd=project,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    for platform, variable in (
        ('android', 'REVENUECAT_ANDROID_PUBLIC_SDK_KEY'),
        ('ios', 'REVENUECAT_IOS_PUBLIC_SDK_KEY'),
    ):
        missing = prepare(platform)
        assert missing.returncode == 1
        assert f'{variable} is required for {platform} store release preparation' in missing.stderr
        assert 'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS=1' in missing.stderr

        whitespace_only = prepare(platform, {variable: '   '})
        assert whitespace_only.returncode == 1
        assert f'{variable} is required for {platform} store release preparation' in whitespace_only.stderr

    invalid_opt_out = prepare('android', {'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS': 'true'})
    assert invalid_opt_out.returncode == 1

    unsigned_ci = prepare('android', {'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS': '1'})
    assert unsigned_ci.returncode == 0, unsigned_ci.stderr
    assert 'explicit unsigned structural CI opt-out' in unsigned_ci.stderr
    assert 'not release-ready' in unsigned_ci.stderr
    assert 'release source is prepared and verified' in unsigned_ci.stdout


def test_reproducible_node22_lockfile_is_committed_and_aligned():
    package = json.loads(read('package.json'))
    lock = json.loads(read('package-lock.json'))
    root = lock['packages']['']

    assert lock['name'] == package['name']
    assert lock['version'] == package['version']
    assert lock['lockfileVersion'] == 3
    assert root['engines']['node'] == package['engines']['node'] == '22.x'
    assert root['dependencies'] == package['dependencies']
    assert root['devDependencies'] == package['devDependencies']


def test_dependabot_keeps_capacitor_release_packages_in_one_version_update():
    dependabot = read('.github/dependabot.yml')
    group_start = dependabot.index('      capacitor-release-toolchain:')
    group = dependabot[group_start:]

    assert '        applies-to: version-updates' in group
    for package_name in (
        '@capacitor/core',
        '@capacitor/cli',
        '@capacitor/android',
        '@capacitor/ios',
    ):
        assert f'          - "{package_name}"' in group


def test_ios_cloud_verification_cannot_sign_or_upload():
    workflow = read('.github/workflows/ios-store-verify.yml')

    assert 'runs-on: macos-26' in workflow
    for source in (
        'public/**',
        'backend/revenuecat_catalog.json',
        'store/**',
        'docs/DATA_SAFETY.md',
        'scripts/check-javascript.mjs',
        'scripts/production-build-preflight.mjs',
        'scripts/revenuecat-catalog.mjs',
        'scripts/verify-native-privacy.mjs',
    ):
        assert source in workflow
    assert 'npm run store:prepare:ios' in workflow
    assert 'App Store candidates require Xcode 26 or later' in workflow
    assert 'App Store candidates require the iOS 26 SDK or later' in workflow
    assert 'xcrun --sdk iphoneos --show-sdk-version' in workflow
    assert 'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS: "1"' in workflow
    assert 'unsigned iOS structural' in workflow
    assert 'not release-ready' in workflow
    assert 'CODE_SIGNING_ALLOWED=NO' in workflow
    assert 'CODE_SIGNING_REQUIRED=NO' in workflow
    assert 'verify-native-privacy.mjs ios-bundle "$app_bundle"' in workflow
    assert "plutil -lint \"$manifest\"" in workflow
    assert 'ios/App/App.xcworkspace' in workflow
    assert 'ios/App/App.xcodeproj' in workflow
    assert 'secrets.' not in workflow
    assert 'upload-app' not in workflow
    assert 'upload-testflight' not in workflow
    assert 'app-store-connect' not in workflow.lower()


def test_android_cloud_verification_builds_a_bundle_without_signing_or_upload():
    workflow = read('.github/workflows/android-store-verify.yml')

    assert 'runs-on: ubuntu-latest' in workflow
    for source in (
        'public/**',
        'backend/revenuecat_catalog.json',
        'store/**',
        'docs/DATA_SAFETY.md',
        'scripts/check-javascript.mjs',
        'scripts/production-build-preflight.mjs',
        'scripts/revenuecat-catalog.mjs',
        'scripts/verify-native-privacy.mjs',
    ):
        assert source in workflow
    assert 'actions/setup-java@v6' in workflow
    assert 'java-version: "21"' in workflow
    assert 'npm run store:prepare:android' in workflow
    assert 'scripts/native-api-origin.mjs' in workflow
    assert 'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS: "1"' in workflow
    assert 'unsigned Android structural' in workflow
    assert 'not release-ready' in workflow
    assert workflow.index('npm run store:prepare:android') < workflow.index('uses: actions/setup-java@v6')
    assert 'npm run store:signing:check' in workflow
    assert 'store:signing:check:android' not in workflow
    assert './gradlew --no-daemon bundleRelease' in workflow
    assert 'verify-native-privacy.mjs android-manifest "$merged_manifest"' in workflow
    assert "-name '*.aab'" in workflow
    assert 'secrets.' not in workflow
    assert 'actions/upload-artifact' not in workflow
    assert 'google-github-actions/auth' not in workflow
    assert 'playstore' not in workflow.lower()


def test_store_versions_and_android_api_are_guarded():
    configure = read('scripts/configure-native.mjs')
    verify = read('scripts/verify-native-release.mjs')
    assert 'compileSdkVersion = 36' in configure
    assert 'targetSdkVersion = 36' in configure
    assert 'STORE_BUILD_NUMBER' in configure
    assert 'versionCode' in configure and 'versionName' in configure
    assert 'CURRENT_PROJECT_VERSION' in configure and 'MARKETING_VERSION' in configure
    assert 'TARGETED_DEVICE_FAMILY = "1,2";' in configure
    assert 'expectedBuildNumber' in verify
    assert 'REVENUECAT_ANDROID_PUBLIC_SDK_KEY' in verify
    assert 'REVENUECAT_IOS_PUBLIC_SDK_KEY' in verify
    assert 'applicationId "com.clevercrump.askcrump"' in verify
    assert 'PRODUCT_BUNDLE_IDENTIFIER = com.clevercrump.askcrump;' in verify
    assert "value !== '1,2'" in verify
    assert 'android:allowBackup="false"' in configure
    assert 'android:usesCleartextTraffic="false"' in configure
    assert 'android:allowBackup="false"' in verify
    assert 'android:usesCleartextTraffic="false"' in verify


def test_ios_media_usage_descriptions_are_configured_and_fail_closed():
    configure = read('scripts/configure-native.mjs')
    verify = read('scripts/verify-native-release.mjs')

    required_keys = (
        'NSCameraUsageDescription',
        'NSPhotoLibraryUsageDescription',
        'NSPhotoLibraryAddUsageDescription',
    )
    for key in required_keys:
        assert f'<key>{key}</key>' in configure
        assert f"'{key}'" in verify

    assert 'function plistStringValue(source, key)' in verify
    assert "match?.[1].trim() || ''" in verify
    assert 'is missing or empty' in verify


def test_ios_media_usage_description_verifier_rejects_missing_and_empty_values(tmp_path):
    node = os.environ.get('ASKCRUMP_NODE_EXECUTABLE') or shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to execute the native release verifier.')

    project = tmp_path / 'native-release'
    for relative in (
        'scripts',
        'backend',
        'dist',
        'ios/App/App/Assets.xcassets/AppIcon.appiconset',
        'ios/App/App.xcodeproj',
    ):
        (project / relative).mkdir(parents=True)

    for filename in ('verify-native-release.mjs', 'revenuecat-catalog.mjs', 'native-api-origin.mjs'):
        shutil.copy2(ROOT / 'scripts' / filename, project / 'scripts' / filename)
    shutil.copy2(
        ROOT / 'backend' / 'revenuecat_catalog.json',
        project / 'backend' / 'revenuecat_catalog.json',
    )

    package = json.loads(read('package.json'))
    version = package['version']
    version_parts = [int(part) for part in version.split('.')]
    build_number = version_parts[0] * 10_000 + version_parts[1] * 100 + version_parts[2]
    (project / 'package.json').write_text(
        json.dumps({'version': version}),
        encoding='utf-8',
    )
    (project / 'dist' / 'index.html').write_text(
        '<main id="appContainer"></main>',
        encoding='utf-8',
    )

    catalog = json.loads((project / 'backend' / 'revenuecat_catalog.json').read_text(encoding='utf-8'))
    runtime_values = {
        'apiBase': 'https://www.askcrump.com',
        'revenueCatEntitlement': catalog['entitlementId'],
        'revenueCatProfessionalProductId': catalog['subscriptions']['professional'],
        'revenueCatEnterpriseProductId': catalog['subscriptions']['enterprise'],
        'revenueCatCredits50ProductId': catalog['credits']['credits_50'],
        'revenueCatCredits150ProductId': catalog['credits']['credits_150'],
        'revenueCatCredits400ProductId': catalog['credits']['credits_400'],
    }
    runtime_config_path = project / 'dist' / 'runtime-body-v1.js'

    def write_runtime_config():
        runtime_config_path.write_text(
            '\n'.join(f'{json.dumps(key)}: {json.dumps(value)}' for key, value in runtime_values.items()),
            encoding='utf-8',
        )

    write_runtime_config()
    (project / 'ios' / 'App' / 'App' / 'AppDelegate.swift').write_text(
        'capacitorDidRegisterForRemoteNotifications',
        encoding='utf-8',
    )
    (project / 'ios' / 'App' / 'App' / 'Assets.xcassets' / 'AppIcon.appiconset' / 'Contents.json').write_text(
        '{}',
        encoding='utf-8',
    )
    (project / 'ios' / 'App' / 'App.xcodeproj' / 'project.pbxproj').write_text(
        '\n'.join((
            'PRODUCT_BUNDLE_IDENTIFIER = com.clevercrump.askcrump;',
            f'MARKETING_VERSION = {version};',
            f'CURRENT_PROJECT_VERSION = {build_number};',
            'TARGETED_DEVICE_FAMILY = "1,2";',
            'PrivacyInfo.xcprivacy in Resources',
        )),
        encoding='utf-8',
    )
    (project / 'ios' / 'App' / 'App' / 'PrivacyInfo.xcprivacy').write_text(
        '<plist><dict><key>NSPrivacyTracking</key><false/>'
        '<key>NSPrivacyAccessedAPITypes</key><array/></dict></plist>',
        encoding='utf-8',
    )

    required_keys = (
        'NSCameraUsageDescription',
        'NSPhotoLibraryUsageDescription',
        'NSPhotoLibraryAddUsageDescription',
    )
    info_path = project / 'ios' / 'App' / 'App' / 'Info.plist'

    def write_info(*, omitted=None, empty=None):
        entries = ''.join(
            f'<key>{key}</key><string>{"   " if key == empty else "A clear user-facing purpose."}</string>'
            for key in required_keys
            if key != omitted
        )
        info_path.write_text(f'<plist><dict>{entries}</dict></plist>', encoding='utf-8')

    def verify(extra_env=None):
        env = os.environ.copy()
        for variable in (
            'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS',
            'STORE_VERSION_NAME',
            'STORE_BUILD_NUMBER',
        ):
            env.pop(variable, None)
        env.update(extra_env or {})
        return subprocess.run(
            [node, str(project / 'scripts' / 'verify-native-release.mjs'), 'ios'],
            cwd=project,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    write_info()
    missing_billing_key = verify()
    assert missing_billing_key.returncode == 1
    assert 'REVENUECAT_IOS_PUBLIC_SDK_KEY was missing or empty' in missing_billing_key.stderr

    unsigned_ci = verify({'STORE_ALLOW_MISSING_PUBLIC_BILLING_KEYS': '1'})
    assert unsigned_ci.returncode == 0, unsigned_ci.stderr
    assert 'unsigned structural CI' in unsigned_ci.stderr
    assert 'not release-ready' in unsigned_ci.stderr

    runtime_values['revenueCatAppleApiKey'] = '   '
    write_runtime_config()
    whitespace_billing_key = verify()
    assert whitespace_billing_key.returncode == 1
    assert 'REVENUECAT_IOS_PUBLIC_SDK_KEY was missing or empty' in whitespace_billing_key.stderr

    runtime_values['revenueCatAppleApiKey'] = 'appl_fixture_public_key'
    write_runtime_config()
    valid_result = verify()
    assert valid_result.returncode == 0, valid_result.stderr

    for key in required_keys:
        for invalid in ('omitted', 'empty'):
            write_info(
                omitted=key if invalid == 'omitted' else None,
                empty=key if invalid == 'empty' else None,
            )
            invalid_result = verify()
            assert invalid_result.returncode == 1
            assert f'iOS {key} is missing or empty' in invalid_result.stderr


def test_native_api_defaults_use_the_direct_canonical_host():
    canonical = 'https://www.askcrump.com'
    redirected = "'https://askcrump.com'"

    for relative in (
        'scripts/native-api-origin.mjs',
        'public/mobile-bridge.js',
        'public/runtime-config.js',
        'public/runtime-config-v1.js',
        'public/runtime-body-v1.js',
    ):
        source = read(relative)
        assert canonical in source, f'{relative} must use the canonical API host'
        assert redirected not in source, f'{relative} must not use the redirecting API host'

    for relative in (
        'scripts/build-native.mjs',
        'scripts/prepare-store-release.mjs',
        'scripts/verify-native-release.mjs',
    ):
        source = read(relative)
        assert "from './native-api-origin.mjs'" in source
        assert redirected not in source, f'{relative} must not use the redirecting API host'

    billing = read('docs/BILLING_5_1.md')
    assert 'POST https://www.askcrump.com/api/billing/credits/stripe-webhook' in billing
    assert 'POST https://askcrump.com/api/billing/credits/stripe-webhook' not in billing


def test_native_api_origin_guard_rejects_nonproduction_hosts_and_paths():
    node = os.environ.get('ASKCRUMP_NODE_EXECUTABLE') or shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to execute the native API origin guard.')

    module_url = (ROOT / 'scripts' / 'native-api-origin.mjs').as_uri()
    script = (
        f"import {{ requireProductionNativeApiBase as guard }} from {json.dumps(module_url)};"
        "const values = JSON.parse(process.argv[1]);"
        "for (const value of values.valid) guard(value);"
        "for (const value of values.invalid) {"
        "  let rejected = false;"
        "  try { guard(value); } catch { rejected = true; }"
        "  if (!rejected) throw new Error(`accepted unsafe API base: ${value}`);"
        "}"
    )
    values = {
        'valid': ['', 'https://www.askcrump.com', 'https://www.askcrump.com/'],
        'invalid': [
            'http://www.askcrump.com',
            'https://askcrump.com',
            'https://www.askcrump.com.evil.example',
            'https://www.askcrump.com/api',
            'https://www.askcrump.com/?redirect=evil',
            'https://user:secret@www.askcrump.com',
            'not-a-url',
        ],
    }
    result = subprocess.run(
        [node, '--input-type=module', '--eval', script, json.dumps(values)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_ios_privacy_manifest_is_valid_xml_and_bundled_by_source():
    manifest_path = ROOT / 'resources' / 'PrivacyInfo.xcprivacy'
    root = ET.parse(manifest_path).getroot()
    assert root.tag == 'plist'
    manifest = plistlib.loads(manifest_path.read_bytes())
    source = manifest_path.read_text(encoding='utf-8')
    assert '<key>NSPrivacyTracking</key>' in source
    assert '<key>NSPrivacyCollectedDataTypes</key>' in source
    assert '<key>NSPrivacyAccessedAPITypes</key>' in source
    assert manifest['NSPrivacyTracking'] is False
    assert manifest['NSPrivacyTrackingDomains'] == []
    collected = {
        item['NSPrivacyCollectedDataType']: item
        for item in manifest['NSPrivacyCollectedDataTypes']
    }
    for data_type in (
        'NSPrivacyCollectedDataTypeName',
        'NSPrivacyCollectedDataTypeEmailAddress',
        'NSPrivacyCollectedDataTypeUserID',
        'NSPrivacyCollectedDataTypeOtherUserContent',
        'NSPrivacyCollectedDataTypePhotosorVideos',
        'NSPrivacyCollectedDataTypePurchaseHistory',
        'NSPrivacyCollectedDataTypeDeviceID',
        'NSPrivacyCollectedDataTypeProductInteraction',
    ):
        assert collected[data_type]['NSPrivacyCollectedDataTypeLinked'] is True
        assert collected[data_type]['NSPrivacyCollectedDataTypeTracking'] is False
        assert 'NSPrivacyCollectedDataTypePurposeAppFunctionality' in collected[data_type]['NSPrivacyCollectedDataTypePurposes']
    for data_type in ('NSPrivacyCollectedDataTypePurchaseHistory', 'NSPrivacyCollectedDataTypeProductInteraction'):
        assert 'NSPrivacyCollectedDataTypePurposeAnalytics' in collected[data_type]['NSPrivacyCollectedDataTypePurposes']

    configure = read('scripts/configure-native.mjs')
    assert 'PrivacyInfo.xcprivacy in Resources' in configure


def test_native_privacy_verifier_tracks_runtime_sdks_and_compiled_outputs():
    verifier = read('scripts/verify-native-privacy.mjs')
    data_safety = read('docs/DATA_SAFETY.md')
    package = json.loads(read('package.json'))

    native_packages = sorted(
        name for name in package['dependencies']
        if name.startswith(('@capacitor/', '@revenuecat/', '@aparajita/', '@capacitor-community/'))
    )
    for package_name in native_packages:
        assert f"'{package_name}'" in verifier
        assert f'`{package_name}`' in data_safety
    assert 'NSPrivacyCollectedDataTypePurchaseHistory' in verifier
    assert 'NSPrivacyCollectedDataTypePhotosorVideos' in verifier
    assert 'NSPrivacyCollectedDataTypePurposeAnalytics' in verifier
    assert 'Frameworks/Capacitor.framework/PrivacyInfo.xcprivacy' in verifier
    assert 'Frameworks/Cordova.framework/PrivacyInfo.xcprivacy' in verifier
    assert 'RevenueCat_RevenueCat.bundle/PrivacyInfo.xcprivacy' in verifier
    assert 'SDWebImage_SDWebImage.bundle/PrivacyInfo.xcprivacy' in verifier
    assert 'com.google.android.gms.permission.AD_ID' in verifier
    assert 'android.permission.ACCESS_FINE_LOCATION' in verifier
    assert 'com.android.vending.BILLING' in verifier
    assert 'com.google.android.play.billingclient.version' in verifier
    assert 'billingMetadata.length !== 1' in verifier
    assert 'Number(semver[1]) < 8' in verifier


def test_native_privacy_verifier_executes_compiled_boundaries(tmp_path):
    node = os.environ.get('ASKCRUMP_NODE_EXECUTABLE') or shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to execute the native privacy verifier.')

    verifier = ROOT / 'scripts' / 'verify-native-privacy.mjs'

    android_manifest = tmp_path / 'AndroidManifest.xml'
    android_manifest.write_text(
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        '<uses-permission android:name="android.permission.INTERNET" />'
        '<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />'
        '<uses-permission android:name="com.android.vending.BILLING" />'
        '<application>'
        '<meta-data android:name="com.google.android.play.billingclient.version" '
        'android:value="8.3.0" />'
        '</application>'
        '</manifest>',
        encoding='utf-8',
    )
    android_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert android_result.returncode == 0, android_result.stderr

    supported_manifest = android_manifest.read_text(encoding='utf-8')

    android_manifest.write_text(
        supported_manifest.replace('android:value="8.3.0"', 'android:value="7.1.1"'),
        encoding='utf-8',
    )
    outdated_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert outdated_result.returncode == 1
    assert 'Google Play Billing Library 7.1.1; major version 8 or newer is required' in outdated_result.stderr

    android_manifest.write_text(
        supported_manifest.replace('android:value="8.3.0"', 'android:value="8.3"'),
        encoding='utf-8',
    )
    malformed_version_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert malformed_version_result.returncode == 1
    assert 'value must be a semantic version; found 8.3' in malformed_version_result.stderr

    billing_metadata = (
        '<meta-data android:name="com.google.android.play.billingclient.version" '
        'android:value="8.3.0" />'
    )
    android_manifest.write_text(
        supported_manifest.replace(billing_metadata, billing_metadata + billing_metadata),
        encoding='utf-8',
    )
    duplicate_metadata_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert duplicate_metadata_result.returncode == 1
    assert 'exactly one com.google.android.play.billingclient.version metadata entry; found 2' in duplicate_metadata_result.stderr

    android_manifest.write_text(
        supported_manifest.replace(billing_metadata, ''),
        encoding='utf-8',
    )
    missing_metadata_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_metadata_result.returncode == 1
    assert 'exactly one com.google.android.play.billingclient.version metadata entry; found 0' in missing_metadata_result.stderr

    android_manifest.write_text(
        supported_manifest.replace(
            '<uses-permission android:name="com.android.vending.BILLING" />',
            '',
        ),
        encoding='utf-8',
    )
    missing_permission_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_permission_result.returncode == 1
    assert 'missing com.android.vending.BILLING' in missing_permission_result.stderr

    android_manifest.write_text(
        supported_manifest.replace(
            '</manifest>',
            '<uses-permission android:name="com.google.android.gms.permission.AD_ID" />'
            '</manifest>',
        ),
        encoding='utf-8',
    )
    prohibited_result = subprocess.run(
        [node, str(verifier), 'android-manifest', str(android_manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert prohibited_result.returncode == 1
    assert 'unexpectedly requests com.google.android.gms.permission.AD_ID' in prohibited_result.stderr

    app_bundle = tmp_path / 'App.app'
    app_bundle.mkdir()
    shutil.copy2(ROOT / 'resources' / 'PrivacyInfo.xcprivacy', app_bundle)
    required_manifests = (
        app_bundle / 'Frameworks' / 'Capacitor.framework' / 'PrivacyInfo.xcprivacy',
        app_bundle / 'Frameworks' / 'Cordova.framework' / 'PrivacyInfo.xcprivacy',
        app_bundle / 'RevenueCat_RevenueCat.bundle' / 'PrivacyInfo.xcprivacy',
        app_bundle / 'SDWebImage_SDWebImage.bundle' / 'PrivacyInfo.xcprivacy',
    )
    for manifest in required_manifests:
        manifest.parent.mkdir(parents=True)
        shutil.copy2(ROOT / 'resources' / 'PrivacyInfo.xcprivacy', manifest)
    ios_result = subprocess.run(
        [node, str(verifier), 'ios-bundle', str(app_bundle)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ios_result.returncode == 0, ios_result.stderr

    required_manifests[1].unlink()
    missing_result = subprocess.run(
        [node, str(verifier), 'ios-bundle', str(app_bundle)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_result.returncode == 1
    assert 'missing Frameworks/Cordova.framework/PrivacyInfo.xcprivacy' in missing_result.stderr


def test_moderation_queue_is_server_only_and_account_scoped():
    migration = read('migrations/014_ai_content_reports.sql')
    readiness = read('STORE_READINESS.md')
    audit = read('docs/STORE_READINESS_AUDIT_2026-08-27.md')
    production_evidence = read('docs/AI_REPORT_QUEUE_PRODUCTION_READINESS_2026-09-15.md')
    assert 'references public.users(id) on delete cascade' in migration
    assert 'enable row level security' in migration
    assert 'from public, anon, authenticated' in migration
    assert 'to service_role' in migration
    assert 'Reverify the already-applied `migrations/014_ai_content_reports.sql` boundary' in readiness
    assert 'Apply `migrations/014_ai_content_reports.sql` before testing' not in readiness
    assert 'legitimate signed-device submission/retry remains pending' in audit
    assert 'No row' in production_evidence
    assert 'was inserted.' in production_evidence


def test_store_metadata_source_is_structured_private_and_within_static_limits():
    metadata = json.loads(read('store/listing.en-US.json'))
    apple = metadata['apple']
    google = metadata['google']

    assert metadata['app']['bundleId'] == 'com.clevercrump.askcrump'
    assert len(metadata['app']['name']) <= 30
    assert metadata['app']['supportUrl'] == 'https://www.askcrump.com/legal#contact'
    assert metadata['app']['marketingUrl'] == 'https://www.askcrump.com/'
    assert metadata['app']['privacyUrl'] == 'https://www.askcrump.com/legal#privacy'
    assert metadata['app']['privacyChoicesUrl'] == 'https://www.askcrump.com/delete-account'
    assert metadata['app']['accountDeletionUrl'] == 'https://www.askcrump.com/delete-account'
    assert len(apple['subtitle']) <= 30
    assert len(apple['promotionalText']) <= 170
    assert len(apple['keywords'].encode('utf-8')) <= 100
    assert all(len(item.strip()) > 2 for item in apple['keywords'].split(','))
    assert apple['copyright'] == '2026 Gregory D. Crump Jr.'
    assert len(apple['description']) <= 4000
    assert len(google['shortDescription']) <= 80
    assert len(google['fullDescription']) <= 4000
    assert google['developerEmail'] == 'askcrump@gmail.com'
    assert not google['shortDescription'].endswith('.')
    expected_assets = {
        'appIcon': (512, 512, 6),
        'featureGraphic': (1024, 500, 2),
    }
    for key, (expected_width, expected_height, expected_color_type) in expected_assets.items():
        payload = (ROOT / google[key]).read_bytes()
        assert payload[:8] == b'\x89PNG\r\n\x1a\n'
        assert payload[12:16] == b'IHDR'
        assert int.from_bytes(payload[16:20], 'big') == expected_width
        assert int.from_bytes(payload[20:24], 'big') == expected_height
        assert payload[24] == 8
        assert payload[25] == expected_color_type
    assert len(apple['screenshotPlan']) >= 4
    assert len(google['screenshotPlan']) >= 4
    for description in (apple['description'], google['fullDescription']):
        assert 'Ask, Projects, Create, Video, Library, and You' in description
    expected_frames = ('Ask —', 'Projects —', 'Create —', 'Video —', 'Research in Ask —', 'Library —', 'You —')
    for plan in (apple['screenshotPlan'], google['screenshotPlan']):
        assert plan == metadata['apple']['screenshotPlan']
        for frame in expected_frames:
            assert any(item.startswith(frame) for item in plan), frame
    reviewer_template = json.loads(read('store/reviewer-access.example.json'))
    assert set(reviewer_template) == {'ios', 'android'}
    assert all(
        account['username'] == 'REPLACE_IN_UNTRACKED_FILE'
        and account['password'] == 'REPLACE_IN_UNTRACKED_FILE'
        for account in reviewer_template.values()
    )
    assert set(reviewer_template['ios']['contact']) == {'firstName', 'lastName', 'email', 'phone'}
    assert 'store/reviewer-access.json' in read('.gitignore')
    verifier = read('scripts/verify-store-metadata.mjs')
    assert 'Apple promotional text' in verifier
    assert 'Google short description' in verifier
    assert 'Every Apple keyword must contain more than two characters' in verifier
    assert 'Google Play listing icon' in verifier
    assert 'Google Play feature graphic' in verifier
    assert 'Store listing draft is out of sync' in verifier
    assert 'verified direct-200 canonical URL' in verifier
