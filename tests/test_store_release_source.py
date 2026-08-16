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

    prepare = read('scripts/prepare-store-release.mjs')
    assert "['android', 'ios'].includes(platform)" in prepare
    assert "['scripts/configure-native.mjs', platform]" in prepare
    assert "['scripts/verify-native-release.mjs', platform]" in prepare


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


def test_ios_privacy_manifest_is_valid_xml_and_bundled_by_source():
    manifest_path = ROOT / 'resources' / 'PrivacyInfo.xcprivacy'
    root = ET.parse(manifest_path).getroot()
    assert root.tag == 'plist'
    source = manifest_path.read_text(encoding='utf-8')
    assert '<key>NSPrivacyTracking</key>' in source
    assert '<key>NSPrivacyCollectedDataTypes</key>' in source
    assert '<key>NSPrivacyAccessedAPITypes</key>' in source

    configure = read('scripts/configure-native.mjs')
    assert 'PrivacyInfo.xcprivacy in Resources' in configure


def test_moderation_queue_is_server_only_and_account_scoped():
    migration = read('migrations/014_ai_content_reports.sql')
    assert 'references public.users(id) on delete cascade' in migration
    assert 'enable row level security' in migration
    assert 'from public, anon, authenticated' in migration
    assert 'to service_role' in migration


def test_listing_field_drafts_fit_store_limits():
    apple_subtitle = 'Create, research, and build'
    apple_promotional_text = (
        'Turn questions into useful work with research, image and video creation, '
        'documents, manuscripts, private files, and a saved creation library.'
    )
    google_short_description = (
        'Create, research, generate media, and manage ambitious projects with Crump.'
    )
    assert len(apple_subtitle) <= 30
    assert len(apple_promotional_text) <= 170
    assert len(google_short_description) <= 80
