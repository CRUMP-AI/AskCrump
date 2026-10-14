from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def source(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_visual_viewport_is_the_canonical_mobile_height_contract() -> None:
    script = source("crump-v1.js")
    styles = source("crump-design-pass.css")

    assert "--v1-visual-viewport-height" in script
    assert "--v1-visual-viewport-top" in script
    assert "--v1-keyboard-inset" in script
    assert "--crump-keyboard-height" in script
    assert "crump-v1-keyboard-visible" in script
    assert "height: var(--v1-visual-viewport-height, 100dvh) !important;" in styles
    assert "inset: var(--v1-visual-viewport-top, 0px) 0 auto !important;" in styles


def test_mobile_keyboard_hides_navigation_and_keeps_composer_in_view() -> None:
    shell = source("crump-vision-shell-1.0.css")
    styles = source("crump-design-pass.css")

    assert ".crump-v1-keyboard-visible .cv-mobile-nav" in shell
    assert ".crump-v1-keyboard-visible .cv-mobile-nav" in styles
    assert ".crump-v1-keyboard-visible .v1-command-dock" in styles
    assert "bottom: 0 !important;" in styles
    assert "display: none !important;" in shell
    assert "coarseMobileFocus" not in source("crump-v1.js")


def test_mobile_product_destinations_fill_space_above_navigation() -> None:
    styles = source("crump-design-pass.css")

    assert "height: calc(var(--v1-visual-viewport-height, 100dvh) - var(--cv-mobile-nav) - env(safe-area-inset-bottom)) !important;" in styles
    assert "body.crump-v1-body .crump53-sheet" in styles
    assert "padding-bottom: 0 !important;" in styles


def test_mobile_navigation_clearance_only_exists_after_the_nav_mounts() -> None:
    styles = source("crump-design-pass.css")

    assert "--cv-mobile-nav: 0px;" in styles
    assert "--crump5930-mobile-nav: 0px;" in styles
    assert 'html[data-cv-shell="ready"] body.crump-v1-body { --cv-mobile-nav: 68px; }' in styles
    assert 'html[data-crump-navigation5930="ready"] body.crump-v1-body {\n    --cv-mobile-nav: 68px;' not in styles
    assert "bottom: calc(var(--cv-mobile-nav) + env(safe-area-inset-bottom)) !important;" not in styles
    assert "height: calc(var(--v1-visual-viewport-height, 100dvh) - var(--cv-mobile-nav) - env(safe-area-inset-bottom)) !important;" in styles
    assert 'html[data-crump-navigation5930="ready"] body.crump-v1-body .crump53-sheet' in styles


def test_small_screen_form_controls_are_legible_and_fill_settings_rows() -> None:
    styles = source("crump-design-pass.css")

    assert "@media (max-width:560px)" in styles
    assert ".settings-row > :is(.settings-field,.settings-select)" in styles
    assert ".settings-inline .settings-select" in styles
    assert "font-size: 16px !important;" in styles
    assert "min-height: 44px;" in styles


def test_precision_editor_preserves_image_geometry_and_mobile_actions() -> None:
    styles = source("crump-precision-image-edit.css")

    assert "object-fit: fill" not in styles
    assert "object-fit: contain" in styles
    assert "position: sticky;" in styles
    assert "bottom: 0;" in styles
    assert ".crump-precision-editor > footer button { flex: 1; min-height: 44px; }" in styles
    assert ".crump-precision-overlay-text input[type=\"text\"]" in styles


def test_conversation_actions_clear_the_mobile_navigation() -> None:
    styles = source("crump-product-5.3.1.css")

    assert "bottom: calc(var(--cv-mobile-nav, 68px) + env(safe-area-inset-bottom, 0px) + 12px);" in styles
    assert "max-height: calc(var(--v1-visual-viewport-height, 100dvh) - var(--cv-mobile-nav, 68px)" in styles
    assert ".crump531-chat-menu-popover button" in styles
    assert "min-height: 44px;" in styles


def test_light_navigation_titles_and_real_scroll_owners_have_semantic_styles() -> None:
    styles = source("crump-design-pass.css")

    assert 'html[data-theme="light"][data-cv-shell="ready"] body.crump-v1-body .cv-mobile-nav' in styles
    assert ".crump53-project-hero h2,.cvp-project-head h2,.cvp-switch-name" in styles
    assert "overflow-wrap: anywhere;" in styles
    assert ".cv-stage-scroll" in styles
    assert ".crump53-sheet-body" in styles
    assert ".cvl-reader-nav" in styles
    assert "scrollbar-color: #b8aa95 transparent !important;" in styles
