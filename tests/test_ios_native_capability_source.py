import plistlib
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_ios_push_entitlement_is_reconstructed_and_release_guarded() -> None:
    entitlements_path = ROOT / "resources" / "App.entitlements"
    assert ET.parse(entitlements_path).getroot().tag == "plist"
    entitlements = plistlib.loads(entitlements_path.read_bytes())
    configure = read("scripts/configure-native.mjs")
    verifier = read("scripts/verify-native-release.mjs")

    assert entitlements == {"aps-environment": "development"}
    assert "resources/App.entitlements" in configure
    assert "ios/App/App/App.entitlements" in configure
    assert "CODE_SIGN_ENTITLEMENTS = App/App.entitlements;" in configure
    assert "Every iOS App build configuration must bind App/App.entitlements" in verifier
    assert "The iOS push-entitlements file is missing" in verifier
    assert "Xcode selects the signed environment from the provisioning profile" in verifier
    assert "resources/App.entitlements" in read(".github/workflows/ios-store-verify.yml")


def test_ios_usage_descriptions_orientations_and_push_are_fail_closed() -> None:
    configure = read("scripts/configure-native.mjs")
    verifier = read("scripts/verify-native-release.mjs")
    deployment = read("docs/DEPLOYMENT.md")
    runbook = read("docs/STORE_LAUNCH_RUNBOOK.md")

    for usage_key in (
        "NSPhotoLibraryUsageDescription",
        "NSPhotoLibraryAddUsageDescription",
    ):
        assert usage_key in configure
        assert usage_key in verifier
    for orientation_key in (
        "UISupportedInterfaceOrientations",
        "UISupportedInterfaceOrientations~ipad",
    ):
        assert orientation_key in verifier

    assert "enable Push Notifications for the Apple App ID/provisioning profile" in configure
    assert "Push Notifications + Background Modes" not in configure
    assert "No iOS entitlements file was found" not in verifier
    assert "Enable Push Notifications and Background Modes" not in runbook
    assert "Keep Background Modes off for the" in runbook
    assert "current visible-alert payload" in runbook
    assert "do not\nenable Background Modes" in deployment


def test_ios_configuration_reconstructs_push_capability_idempotently(tmp_path: Path) -> None:
    node = os.environ.get("ASKCRUMP_NODE_EXECUTABLE") or shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute native configuration.")

    for directory in (
        "scripts",
        "resources",
        "ios/App/App",
        "ios/App/App.xcodeproj",
    ):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "scripts/configure-native.mjs", tmp_path / "scripts/configure-native.mjs")
    shutil.copy2(ROOT / "resources/App.entitlements", tmp_path / "resources/App.entitlements")
    shutil.copy2(ROOT / "resources/PrivacyInfo.xcprivacy", tmp_path / "resources/PrivacyInfo.xcprivacy")
    (tmp_path / "package.json").write_text('{"version":"5.9.76"}', encoding="utf-8")
    (tmp_path / "ios/App/App/AppDelegate.swift").write_text(
        "import UIKit\nclass AppDelegate: UIResponder {\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "ios/App/App/Info.plist").write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<plist version=\"1.0\"><dict>\n"
        "<key>UISupportedInterfaceOrientations</key><array/>\n"
        "<key>UISupportedInterfaceOrientations~ipad</key><array/>\n"
        "</dict></plist>\n",
        encoding="utf-8",
    )
    project_path = tmp_path / "ios/App/App.xcodeproj/project.pbxproj"
    project_path.write_text(
        "/* Begin PBXBuildFile section */\n"
        "/* End PBXBuildFile section */\n"
        "/* Begin PBXFileReference section */\n"
        "/* End PBXFileReference section */\n"
        "children = (\n"
        "                AAAAAAAAAAAAAAAAAAAAAAAA /* Info.plist */,\n"
        ");\n"
        "/* Begin PBXResourcesBuildPhase section */\n"
        "files = (\n"
        ");\n"
        "/* End PBXResourcesBuildPhase section */\n"
        "                CURRENT_PROJECT_VERSION = 1;\n"
        "                MARKETING_VERSION = 1.0;\n"
        "                TARGETED_DEVICE_FAMILY = 1;\n"
        "                CURRENT_PROJECT_VERSION = 1;\n"
        "                MARKETING_VERSION = 1.0;\n"
        "                TARGETED_DEVICE_FAMILY = 1;\n",
        encoding="utf-8",
    )

    command = [node, str(tmp_path / "scripts/configure-native.mjs"), "ios"]
    for _ in range(2):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr

    project = project_path.read_text(encoding="utf-8")
    app_delegate = (tmp_path / "ios/App/App/AppDelegate.swift").read_text(encoding="utf-8")
    info = (tmp_path / "ios/App/App/Info.plist").read_text(encoding="utf-8")
    generated_entitlements = plistlib.loads(
        (tmp_path / "ios/App/App/App.entitlements").read_bytes()
    )

    assert project.count("CODE_SIGN_ENTITLEMENTS = App/App.entitlements;") == 2
    assert project.count("/* App.entitlements */ =") == 1
    assert project.count("PrivacyInfo.xcprivacy in Resources") == 2
    assert app_delegate.count("capacitorDidRegisterForRemoteNotifications") == 1
    assert info.count("NSPhotoLibraryUsageDescription") == 1
    assert info.count("NSPhotoLibraryAddUsageDescription") == 1
    assert generated_entitlements == {"aps-environment": "development"}
