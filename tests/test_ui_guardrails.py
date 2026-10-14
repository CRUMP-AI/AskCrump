from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "public" / "crump-ui-guardrails.css").read_text(encoding="utf-8")


def test_guardrails_use_theme_semantics_for_known_contrast_risks():
    for selector in (
        ".crump53-lock",
        ".crump53-library-copy small",
        ".crump44-premium-copy span",
        ".crump44-memory-header span",
        ".billing51-footer",
    ):
        assert selector in STYLES

    assert "var(--atelier-panel-muted)" in STYLES
    assert "var(--atelier-panel-label)" in STYLES


def test_guardrails_limit_touch_geometry_to_phone_controls():
    assert "@media (max-width: 680px)" in STYLES
    for selector in (
        ".outcome-feedback-btn",
        ".outcome-project-btn",
        ".crump50-artifact-actions button",
        ".crump50-upload-remove",
        ".crump44-close",
        ".crump44-segment",
        ".crump44-premium-button",
        ".crump52-attach-sheet header button",
        ".settings-nested .settings-select",
        ".check-in-categories label",
    ):
        assert selector in STYLES

    assert "min-height: 44px !important" in STYLES
    assert "grid-template-columns: 44px minmax(0, 1fr) 44px !important" in STYLES


def test_guardrails_restore_mobile_navigation_clearance_only_after_shell_mount():
    assert 'html[data-cv-shell="ready"] body.crump-v1-body:not(.crump-v1-keyboard-visible)' in STYLES
    assert "--crump5930-mobile-nav: 68px" in STYLES


def test_guardrails_do_not_take_over_global_layout_or_theme():
    forbidden = (
        "body.crump-v1-body {",
        ".v1-command-dock {",
        ".v1-workspace {",
        "padding-bottom:",
        "position: fixed",
        "env(safe-area-inset",
    )
    for rule in forbidden:
        assert rule not in STYLES
