import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_store_prepare_commands_are_platform_specific():
    package = json.loads(read('package.json'))
    scripts = package['scripts']
    assert scripts['store:prepare:android'].endswith('prepare-store-release.mjs android')
    assert scripts['store:prepare:ios'].endswith('prepare-store-release.mjs ios')
    assert scripts['store:verify:metadata'].endswith('verify-store-metadata.mjs')

    prepare = read('scripts/prepare-store-release.mjs')
    assert "['android', 'ios'].includes(platform)" in prepare
    assert "['scripts/configure-native.mjs', platform]" in prepare
    assert "['scripts/verify-native-release.mjs', platform]" in prepare
    assert "['scripts/verify-store-metadata.mjs']" in prepare
    assert "new URL('package-lock.json', root)" in prepare
    assert 'required for reproducible store preparation' in prepare


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
    assert 'npm run store:prepare:ios' in workflow
    assert 'CODE_SIGNING_ALLOWED=NO' in workflow
    assert 'CODE_SIGNING_REQUIRED=NO' in workflow
    assert 'ios/App/App.xcworkspace' in workflow
    assert 'ios/App/App.xcodeproj' in workflow
    assert 'secrets.' not in workflow
    assert 'upload-app' not in workflow
    assert 'upload-testflight' not in workflow
    assert 'app-store-connect' not in workflow.lower()


def test_android_cloud_verification_builds_a_bundle_without_signing_or_upload():
    workflow = read('.github/workflows/android-store-verify.yml')

    assert 'runs-on: ubuntu-latest' in workflow
    assert 'actions/setup-java@v5' in workflow
    assert 'java-version: "21"' in workflow
    assert 'npm run store:prepare:android' in workflow
    assert workflow.index('npm run store:prepare:android') < workflow.index('uses: actions/setup-java@v5')
    assert 'npm run store:signing:check' in workflow
    assert 'store:signing:check:android' not in workflow
    assert './gradlew --no-daemon bundleRelease' in workflow
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


def test_ios_privacy_manifest_is_valid_xml_and_bundled_by_source():
    manifest_path = ROOT / 'resources' / 'PrivacyInfo.xcprivacy'
    root = ET.parse(manifest_path).getroot()
    assert root.tag == 'plist'
    source = manifest_path.read_text(encoding='utf-8')
    assert '<key>NSPrivacyTracking</key>' in source
    assert '<key>NSPrivacyCollectedDataTypes</key>' in source
    assert '<key>NSPrivacyAccessedAPITypes</key>' in source
    product_interaction = source[source.index('NSPrivacyCollectedDataTypeProductInteraction'):]
    assert 'NSPrivacyCollectedDataTypePurposeAnalytics' in product_interaction

    configure = read('scripts/configure-native.mjs')
    assert 'PrivacyInfo.xcprivacy in Resources' in configure


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
    assert len(apple['subtitle']) <= 30
    assert len(apple['promotionalText']) <= 170
    assert len(apple['keywords'].encode('utf-8')) <= 100
    assert len(apple['description']) <= 4000
    assert len(google['shortDescription']) <= 80
    assert len(google['fullDescription']) <= 4000
    assert len(apple['screenshotPlan']) >= 4
    assert len(google['screenshotPlan']) >= 4
    assert 'REPLACE_IN_UNTRACKED_FILE' in read('store/reviewer-access.example.json')
    assert 'store/reviewer-access.json' in read('.gitignore')
    verifier = read('scripts/verify-store-metadata.mjs')
    assert 'Apple promotional text' in verifier
    assert 'Google short description' in verifier
    assert 'Store listing draft is out of sync' in verifier
