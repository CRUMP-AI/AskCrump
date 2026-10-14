from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-ui-visual-regression.mjs"
FIXTURE = ROOT / "tests" / "fixtures" / "ui-visual-regression.html"
DOC = ROOT / "docs" / "UI_VISUAL_REGRESSION.md"


def test_visual_regression_gate_is_fail_closed_and_complete():
    script = SCRIPT.read_text(encoding="utf-8")

    for state in (
        "home",
        "conversation",
        "files",
        "video",
        "intelligence",
        "settings",
        "billing",
        "create",
        "activity",
    ):
        assert f"'{state}'" in script

    for viewport in (
        "{name: 'phone', width: 390, height: 844, strictTargets: true}",
        "{name: 'tablet', width: 1024, height: 1366, strictTargets: false}",
        "{name: 'desktop', width: 1440, height: 900, strictTargets: false}",
    ):
        assert viewport in script

    assert "const contrastMinimum = 4.5" in script
    assert "const mobileTargetMinimum = 44" in script
    assert "reducedMotion: 'reduce'" in script
    assert "rootOverflow > tolerance" in script
    assert "data-ui-fixed-control" in script
    assert "trayRect.bottom > inputRect.top" in script
    assert "results.length !== expectedScenarioCount" in script
    assert "if (failedScenarios.length)" in script
    assert "process.exitCode = 0" not in script


def test_visual_regression_fixture_uses_final_release_layers_and_real_states():
    fixture = FIXTURE.read_text(encoding="utf-8")

    assert fixture.index("crump-design-pass.css") < fixture.index("crump-activity-center-1.0.css")
    assert fixture.index("crump-activity-center-1.0.css") < fixture.index("crump-ui-guardrails.css")
    assert fixture.index("crump-ui-guardrails.css") < fixture.index("crump-motion-system.css")
    assert fixture.count('data-ui-state="') == 9
    for contract in (
        "message-intelligence-receipt",
        "outcome-feedback",
        "cv-keepsake-real",
        "crump50-attachment-tray",
        'aria-label="Ask Crump Files"',
        'aria-label="Ask Crump Video Studio"',
        'aria-label="Crump Intelligence"',
        "v1-settings-sheet",
        "billing51-sheet",
        "crump52-attach-sheet",
        "crump-activity-panel",
    ):
        assert contract in fixture


def test_visual_regression_evidence_is_ignored_and_documented():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    documentation = DOC.read_text(encoding="utf-8")

    assert "artifacts/" in gitignore
    assert "npm run test:ui-regression" in documentation
    assert "390 × 844" in documentation
    assert "1024 × 1366" in documentation
    assert "1440 × 900" in documentation
    assert "data-ui-contrast-exempt" in documentation
    assert "data-ui-target-exempt" in documentation
