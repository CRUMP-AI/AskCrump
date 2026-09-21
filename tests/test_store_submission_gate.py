import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_submission_gate_is_fail_closed_and_non_publishing() -> None:
    source = read("scripts/verify-store-submission-packet.mjs")
    package = read("package.json")

    assert "ask-crump-store-submission-evidence/v3" in source
    assert "evidence v2 is retired; recreate the packet from the current v3 template" in source
    assert "signing certificate, access evidence, and build number" in source
    assert "Artifact hash does not match the inspected file." in source
    assert "Submission evidence source commit does not match the inspected checkout." in source
    assert "CI receipt head SHA does not match the inspected source commit." in source
    assert "Signing certificate evidence does not match the inspected owner-controlled certificate." in source
    assert "Access closeout evidence does not match the inspected file." in source
    assert "The inspected checkout must be clean" in source
    assert "The inspected checkout origin is not the canonical Ask Crump repository." in source
    assert "Store submission gate arguments cannot be repeated." in source
    assert "not a trustless substitute for owner review" in read("docs/STORE_SUBMISSION_PACKET_GATE_2026-09-10.md")
    assert "Screenshot evidence does not match the complete inspected directory." in source
    assert "PNG screenshots must be 24-bit RGB without alpha or transparency." in source
    assert "A PNG screenshot contains an invalid chunk checksum." in source
    assert "A PNG screenshot has no compressed image data." in source
    assert "A PNG screenshot has invalid compressed image data." in source
    assert "Store screenshots must be validated PNG files." in source
    assert "iOS screenshots must use exactly the iphone and ipad device directories." in source
    assert "iphone-6.9" in source
    assert "ipad-13" in source
    assert "Android screenshot directory must contain 4–8 phone screenshots." in source
    assert "must be current within fourteen days" in source
    assert "Reviewer access inside the repository must be ignored by Git." in source
    assert "Submission evidence inside the repository must be ignored by Git." in source
    assert "Access closeout evidence inside the repository must be ignored by Git." in source
    assert "No upload or store submission was performed." in source
    for forbidden in ("fetch(", "https.request", "curl ", "gh api", "fastlane", "altool"):
        assert forbidden not in source
    assert '"store:verify:submission": "node scripts/verify-store-submission-packet.mjs"' in package


def test_submission_gate_requires_the_full_platform_specific_device_contract() -> None:
    source = read("scripts/verify-store-submission-packet.mjs")
    for required in (
        "physicalDeviceCoreJourneyVerified",
        "purchaseAndRestoreVerified",
        "sessionPersistenceVerified",
        "accountDeletionVerified",
        "aiReportingVerified",
        "accessibilityVerified",
        "offlineReconnectVerified",
        "ownerControlledSigningVerified",
        "privacyFormsReconciled",
        "reviewerPathVerified",
        "storeConsoleScreenshotsAccepted",
        "specialistAccessRemovedOrNotUsed",
        "signedBundleVerified",
        "playProductsAndRevenueCatVerified",
        "notificationPermissionAndDeliveryVerified",
        "playPreLaunchReportReviewed",
        "playConsoleDeclarationsReconciled",
        "signedArchiveVerified",
        "appStoreProductsAndRevenueCatVerified",
        "pushForegroundBackgroundTerminatedVerified",
        "compiledPrivacyReportReviewed",
        "ipadLayoutAndCoreJourneyVerified",
        "appStoreConnectDeclarationsReconciled",
    ):
        assert required in source


def test_submission_templates_start_in_a_deliberately_unapproved_state() -> None:
    android = read("store/submission-evidence.android.example.json")
    ios = read("store/submission-evidence.ios.example.json")
    android_data = json.loads(android)
    ios_data = json.loads(ios)
    gitignore = read(".gitignore")

    root_fields = {
        "schema", "platform", "appVersion", "buildNumber", "observedAt", "source",
        "ciReceipts", "operator", "artifact", "console", "accessClosure", "screenshots", "checks",
    }
    assert set(android_data) == root_fields
    assert set(ios_data) == root_fields
    assert {item["workflow"] for item in android_data["ciReceipts"]} == {
        "ci", "android-store-verify", "video-provider-deletion-fence-postgres",
    }
    assert {item["workflow"] for item in ios_data["ciReceipts"]} == {
        "ci", "ios-store-verify", "video-provider-deletion-fence-postgres",
    }
    assert all(value is False for value in android_data["checks"].values())
    assert all(value is False for value in ios_data["checks"].values())
    assert all(item["file"].lower().endswith(".png") for item in android_data["screenshots"])
    assert all(item["file"].lower().endswith(".png") for item in ios_data["screenshots"])

    assert '"platform": "android"' in android
    assert '"platform": "ios"' in ios
    assert android.count(": false") == 17
    assert ios.count(": false") == 18
    assert '"schema": "ask-crump-store-submission-evidence/v3"' in android
    assert '"schema": "ask-crump-store-submission-evidence/v3"' in ios
    assert '"source"' in android and '"ciReceipts"' in android
    assert '"operator"' in android and '"accessClosure"' in android
    assert '"certificateRole": "play-upload"' in android
    assert '"certificateRole": "apple-distribution"' in ios
    assert android_data["buildNumber"] == "REPLACE_WITH_GOOGLE_PLAY_INTEGER_BUILD_NUMBER"
    assert ios_data["buildNumber"] == "REPLACE_WITH_APPLE_BUILD_VERSION"
    assert android_data["operator"]["kind"] == "REPLACE_WITH_OWNER_OR_RELEASE_SPECIALIST"
    assert ios_data["operator"]["kind"] == "REPLACE_WITH_OWNER_OR_RELEASE_SPECIALIST"
    assert "REPLACE_WITH_SIGNED_AAB_FILENAME" in android
    assert "REPLACE_WITH_SIGNED_IPA_FILENAME" in ios
    assert "store/reviewer-access.json" in gitignore
    assert "store/submission-evidence.json" in gitignore
    assert "store/access-closeout-evidence.*" in gitignore


def test_native_workflows_revalidate_gate_source_changes() -> None:
    for workflow in (
        ".github/workflows/android-store-verify.yml",
        ".github/workflows/ios-store-verify.yml",
    ):
        source = read(workflow)
        assert "scripts/verify-store-submission-packet.mjs" in source
        assert "store/submission-evidence.android.example.json" in source
        assert "store/submission-evidence.ios.example.json" in source
