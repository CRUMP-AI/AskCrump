from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_submission_gate_is_fail_closed_and_non_publishing() -> None:
    source = read("scripts/verify-store-submission-packet.mjs")
    package = read("package.json")

    assert "ask-crump-store-submission-evidence/v1" in source
    assert "Store submission gate requires platform, artifact, screenshots, evidence, and reviewer access." in source
    assert "Artifact hash does not match the inspected file." in source
    assert "Screenshot evidence does not match the complete inspected directory." in source
    assert "must be current within fourteen days" in source
    assert "Reviewer access inside the repository must be ignored by Git." in source
    assert "No upload or store submission was performed." in source
    assert "fetch(" not in source
    assert "https://" not in source
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
        "privacyFormsReconciled",
        "reviewerPathVerified",
        "storeConsoleScreenshotsAccepted",
        "signedBundleVerified",
        "playProductsAndRevenueCatVerified",
        "notificationPermissionAndDeliveryVerified",
        "playPreLaunchReportReviewed",
        "playConsoleDeclarationsReconciled",
        "signedArchiveVerified",
        "appStoreProductsAndRevenueCatVerified",
        "pushForegroundBackgroundTerminatedVerified",
        "compiledPrivacyReportReviewed",
        "appStoreConnectDeclarationsReconciled",
    ):
        assert required in source


def test_submission_templates_start_in_a_deliberately_unapproved_state() -> None:
    android = read("store/submission-evidence.android.example.json")
    ios = read("store/submission-evidence.ios.example.json")
    gitignore = read(".gitignore")

    assert '"platform": "android"' in android
    assert '"platform": "ios"' in ios
    assert android.count(": false") == 15
    assert ios.count(": false") == 15
    assert "REPLACE_WITH_SIGNED_AAB_FILENAME" in android
    assert "REPLACE_WITH_SIGNED_IPA_FILENAME" in ios
    assert "store/reviewer-access.json" in gitignore
    assert "store/submission-evidence.json" in gitignore


def test_native_workflows_revalidate_gate_source_changes() -> None:
    for workflow in (
        ".github/workflows/android-store-verify.yml",
        ".github/workflows/ios-store-verify.yml",
    ):
        source = read(workflow)
        assert "scripts/verify-store-submission-packet.mjs" in source
        assert "store/submission-evidence.android.example.json" in source
        assert "store/submission-evidence.ios.example.json" in source
