from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def hex_rgb(value: str) -> tuple[float, float, float]:
    token = value.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(channel * 2 for channel in token)
    assert len(token) == 6, value
    return tuple(int(token[index : index + 2], 16) / 255 for index in (0, 2, 4))


def luminance(value: str) -> float:
    channels = []
    for channel in hex_rgb(value):
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def custom_property(source: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{3,6}})\s*;", source)
    assert match, f"missing {name}"
    return match.group(1)


def test_appearance_controller_runs_before_paint_and_exposes_a_small_public_contract() -> None:
    shell = read("public/app.html")
    controller = read("public/appearance-theme.js")

    appearance_asset = "/appearance-theme.js?v=5.9.76-appearance-choice-1"
    assert appearance_asset in shell
    assert shell.index(appearance_asset) < shell.index("/crump-v1-body.css")
    assert shell.index(appearance_asset) < shell.index("</head>")
    assert 'name="theme-color" content="#f6f4ee"' in shell

    assert "askcrump.appearance" in controller
    assert "document.documentElement.dataset.theme" in controller
    assert "document.querySelector('meta[name=\"theme-color\"]')" in controller
    assert "crump:appearance-changed" in controller
    assert "window.CrumpAppearance" in controller
    public_api = controller[controller.index("window.CrumpAppearance"):]
    for method in ("get", "set", "syncControls"):
        assert re.search(rf"\b{method}\s*(?::|,)", public_api), method


def test_settings_offer_an_accessible_two_choice_appearance_control() -> None:
    shell = read("public/app.html")

    assert 'data-v1-settings-tab="appearance"' in shell
    assert 'data-v1-settings-panel="appearance"' in shell
    assert 'id="appearanceLight"' in shell
    assert 'id="appearanceDark"' in shell
    assert shell.count('name="appearanceTheme"') == 2
    assert 'value="light"' in shell
    assert 'value="dark"' in shell
    assert re.search(r'id="appearanceLight"[^>]*checked', shell)
    assert 'role="radiogroup"' in shell
    assert "Light" in shell and "Dark" in shell


def test_light_panel_semantics_meet_wcag_aa_for_normal_text() -> None:
    styles = read("public/crump-design-pass.css")
    paper = custom_property(styles, "--atelier-white")
    control = "#f4f0e7"

    for token in (
        "--atelier-panel-text",
        "--atelier-panel-text-2",
        "--atelier-panel-muted",
        "--atelier-panel-label",
        "--atelier-panel-danger",
    ):
        color = custom_property(styles, token)
        assert contrast_ratio(color, paper) >= 4.5, (token, color, paper)

    assert contrast_ratio(custom_property(styles, "--atelier-panel-text"), control) >= 4.5
    assert contrast_ratio(custom_property(styles, "--atelier-panel-muted"), control) >= 4.5


def test_conversation_drawer_uses_explicit_theme_semantics_not_inherited_text_colors() -> None:
    styles = read("public/crump-design-pass.css")

    required_fragments = (
        '.v1-library-header::before',
        '#newChatBtn.v1-new-conversation',
        '#clearChatsBtn.v1-clear-conversations',
        '.v1-library-section-head .section-title',
        '.v1-library-hint',
        '.chat-title',
        '.chat-preview',
        '.sidebar-footer-btn',
        '.v1-library-status',
    )
    for fragment in required_fragments:
        assert fragment in styles, fragment

    drawer_block = styles[
        styles.index("/* Conversations are a contextual drawer") :
        styles.index("/* Workspace chrome and opening canvas")
    ]
    for token in (
        "var(--atelier-panel-text)",
        "var(--atelier-panel-text-2)",
        "var(--atelier-panel-muted)",
        "var(--atelier-panel-label)",
        "var(--atelier-panel-danger)",
    ):
        assert token in drawer_block, token


def test_dark_palette_covers_primary_workspace_and_product_surfaces() -> None:
    styles = read("public/crump-design-pass.css")
    dark = styles[styles.index("/* Dark atelier") :]

    for fragment in (
        'html[data-theme="dark"]',
        '#sidebar.v1-library',
        '.v1-workspace',
        '.input-container',
        '.cvp-root',
        '.cvl-root',
        '.crump53-sheet',
        '.v1-settings-sheet',
        '.crump44-panel',
        '.crump50-sheet',
        '.crump52-attach-sheet',
        '.billing51-sheet',
        '.cv-mobile-nav',
        '.cv-more-sheet',
    ):
        assert fragment in dark, fragment


def test_browser_fixture_exercises_real_theme_assets_and_drawer_markup() -> None:
    fixture = read("tests/fixtures/appearance-theme.html")
    verifier = read("scripts/verify-appearance-theme.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    assert "/public/appearance-theme.js?v=5.9.76-appearance-choice-1" in fixture
    assert "/public/crump-design-pass.css" in fixture
    for asset in (
        "/public/crump-4.4.css",
        "/public/crump-5.0.css",
        "/public/crump-billing-5.1.css",
        "/public/crump-5.2.css",
        "/public/crump-product-5.3.css",
    ):
        assert asset in fixture
    assert 'id="sidebar" class="sidebar v1-library active"' in fixture
    assert 'id="appearanceLight"' in fixture
    assert 'id="appearanceDark"' in fixture
    for probe in ("crump44-panel", "crump50-sheet", "crump52-attach-sheet", "billing51-sheet", "crump53-card", "cv-more-sheet"):
        assert probe in fixture
    assert "askcrump.appearance" in verifier
    assert "contrastRatio" in verifier
    assert "crump:appearance-changed" in verifier
    assert "assertLightSurfaces" in verifier
    assert "assertDarkSurfaces" in verifier
    assert "verify-appearance-theme.cjs" in matrix
