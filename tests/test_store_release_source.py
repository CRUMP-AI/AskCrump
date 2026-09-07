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
    assert "new URL('package-lock.json', root)" in prepare
    assert 'required for reproducible store preparation' in prepare

    ci = read('.github/workflows/ci.yml')
    assert 'npm run store:verify:metadata && npm run store:verify:privacy' in ci


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


def test_ios_cloud_verification_cannot_sign_or_upload():
    workflow = read('.github/workflows/ios-store-verify.yml')

    assert 'runs-on: macos-15' in workflow
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
    assert 'actions/setup-java@v5' in workflow
    assert 'java-version: "21"' in workflow
    assert 'npm run store:prepare:android' in workflow
    assert workflow.index('npm run store:prepare:android') < workflow.index('uses: actions/setup-java@v5')
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
    assert 'expectedBuildNumber' in verify
    assert 'REVENUECAT_ANDROID_PUBLIC_SDK_KEY' in verify
    assert 'REVENUECAT_IOS_PUBLIC_SDK_KEY' in verify
    assert 'applicationId "com.clevercrump.askcrump"' in verify
    assert 'PRODUCT_BUNDLE_IDENTIFIER = com.clevercrump.askcrump;' in verify
    assert 'android:allowBackup="false"' in configure
    assert 'android:usesCleartextTraffic="false"' in configure
    assert 'android:allowBackup="false"' in verify
    assert 'android:usesCleartextTraffic="false"' in verify


def test_native_api_defaults_use_the_direct_canonical_host():
    canonical = 'https://www.askcrump.com'
    redirected = "'https://askcrump.com'"

    for relative in (
        'scripts/build-native.mjs',
        'public/mobile-bridge.js',
        'public/runtime-config.js',
        'public/runtime-config-v1.js',
        'public/runtime-body-v1.js',
    ):
        source = read(relative)
        assert canonical in source, f'{relative} must use the canonical API host'
        assert redirected not in source, f'{relative} must not use the redirecting API host'

    billing = read('docs/BILLING_5_1.md')
    assert 'POST https://www.askcrump.com/api/billing/credits/stripe-webhook' in billing
    assert 'POST https://askcrump.com/api/billing/credits/stripe-webhook' not in billing


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
    assert 'NSPrivacyCollectedDataTypePurposeAnalytics' in verifier
    assert 'Capacitor.bundle/PrivacyInfo.xcprivacy' in verifier
    assert 'CapacitorCordova.bundle/PrivacyInfo.xcprivacy' in verifier
    assert 'com.google.android.gms.permission.AD_ID' in verifier
    assert 'android.permission.ACCESS_FINE_LOCATION' in verifier


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

    android_manifest.write_text(
        android_manifest.read_text(encoding='utf-8').replace(
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
    capacitor = app_bundle / 'Frameworks' / 'Capacitor.bundle'
    cordova = app_bundle / 'Frameworks' / 'CapacitorCordova.bundle'
    capacitor.mkdir(parents=True)
    cordova.mkdir(parents=True)
    shutil.copy2(
        ROOT / 'node_modules' / '@capacitor' / 'ios' / 'Capacitor' / 'Capacitor' / 'PrivacyInfo.xcprivacy',
        capacitor,
    )
    shutil.copy2(
        ROOT / 'node_modules' / '@capacitor' / 'ios' / 'CapacitorCordova' / 'CapacitorCordova' / 'PrivacyInfo.xcprivacy',
        cordova,
    )
    ios_result = subprocess.run(
        [node, str(verifier), 'ios-bundle', str(app_bundle)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ios_result.returncode == 0, ios_result.stderr

    (cordova / 'PrivacyInfo.xcprivacy').unlink()
    missing_result = subprocess.run(
        [node, str(verifier), 'ios-bundle', str(app_bundle)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_result.returncode == 1
    assert 'missing CapacitorCordova.bundle/PrivacyInfo.xcprivacy' in missing_result.stderr


def test_moderation_queue_is_server_only_and_account_scoped():
    migration = read('migrations/014_ai_content_reports.sql')
    assert 'references public.users(id) on delete cascade' in migration
    assert 'enable row level security' in migration
    assert 'from public, anon, authenticated' in migration
    assert 'to service_role' in migration


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
    assert len(apple['description']) <= 4000
    assert len(google['shortDescription']) <= 80
    assert len(google['fullDescription']) <= 4000
    assert len(apple['screenshotPlan']) >= 4
    assert len(google['screenshotPlan']) >= 4
    for description in (apple['description'], google['fullDescription']):
        assert 'Ask, Projects, Create, Video, Library, and You' in description
    expected_frames = ('Ask —', 'Projects —', 'Create —', 'Video —', 'Research in Ask —', 'Library —', 'You —')
    for plan in (apple['screenshotPlan'], google['screenshotPlan']):
        assert plan == metadata['apple']['screenshotPlan']
        for frame in expected_frames:
            assert any(item.startswith(frame) for item in plan), frame
    assert 'REPLACE_IN_UNTRACKED_FILE' in read('store/reviewer-access.example.json')
    assert 'store/reviewer-access.json' in read('.gitignore')
    verifier = read('scripts/verify-store-metadata.mjs')
    assert 'Apple promotional text' in verifier
    assert 'Google short description' in verifier
    assert 'Store listing draft is out of sync' in verifier
    assert 'verified direct-200 canonical URL' in verifier
