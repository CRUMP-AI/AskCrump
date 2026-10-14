import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "verify-apple-toolchain.mjs"


def run_verifier(xcode: str, sdk: str) -> subprocess.CompletedProcess[str]:
    node = os.environ.get("ASKCRUMP_NODE_EXECUTABLE") or shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute the Apple toolchain verifier.")
    environment = os.environ.copy()
    environment["ASKCRUMP_XCODE_VERSION_OUTPUT"] = xcode
    environment["ASKCRUMP_IPHONEOS_SDK_VERSION"] = sdk
    return subprocess.run(
        [node, str(VERIFIER)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("xcode", "sdk"),
    (
        ("Xcode 26.0\nBuild version 17A400", "26.0"),
        ("Xcode 26.6\nBuild version 17F113", "26.2"),
        ("Xcode 27.0\nBuild version 18A1", "27.0"),
    ),
)
def test_current_and_newer_apple_toolchains_pass(xcode: str, sdk: str) -> None:
    result = run_verifier(xcode, sdk)

    assert result.returncode == 0, result.stderr
    assert "satisfy the 26+ submission floor" in result.stdout


@pytest.mark.parametrize(
    ("xcode", "sdk", "expected"),
    (
        ("Xcode 16.4\nBuild version 16F6", "18.5", "Xcode 16 is below"),
        ("Xcode 26.0\nBuild version 17A400", "18.5", "iPhoneOS SDK 18 is below"),
        ("unknown", "26.0", "Xcode version output could not be parsed"),
        ("Xcode 26.0\nBuild version 17A400", "unknown", "iPhoneOS SDK version output could not be parsed"),
    ),
)
def test_obsolete_or_unparseable_apple_toolchains_fail_closed(
    xcode: str,
    sdk: str,
    expected: str,
) -> None:
    result = run_verifier(xcode, sdk)

    assert result.returncode == 1
    assert expected in result.stderr
    assert "Select a GitHub runner/toolchain with Xcode 26+" in result.stderr


def test_ios_workflow_runs_on_current_macos_and_verifies_before_compile() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ios-store-verify.yml").read_text(encoding="utf-8")

    assert "runs-on: macos-26" in workflow
    assert "scripts/verify-apple-toolchain.mjs" in workflow
    assert "npm run store:verify:apple-toolchain" in workflow
    assert workflow.index("npm run store:verify:apple-toolchain") < workflow.index("npm run store:prepare:ios")


def test_local_ios_preparation_cannot_bypass_the_toolchain_floor() -> None:
    source = (ROOT / "scripts" / "prepare-store-release.mjs").read_text(encoding="utf-8")
    toolchain = "run(process.execPath, ['scripts/verify-apple-toolchain.mjs']);"
    metadata = "run(process.execPath, ['scripts/verify-store-metadata.mjs']);"

    assert "if (platform === 'ios')" in source
    assert toolchain in source
    assert source.index(toolchain) < source.index(metadata)
