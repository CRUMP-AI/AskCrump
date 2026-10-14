from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOTION_PATH = ROOT / "public" / "crump-motion-system.css"


def motion_css() -> str:
    return MOTION_PATH.read_text(encoding="utf-8")


def test_motion_system_has_one_semantic_timing_vocabulary() -> None:
    css = motion_css()

    for token in (
        "--crump-motion-duration-instant",
        "--crump-motion-duration-fast",
        "--crump-motion-duration-standard",
        "--crump-motion-duration-panel",
        "--crump-motion-duration-progress",
        "--crump-motion-ease-standard",
        "--crump-motion-ease-enter",
        "--crump-motion-ease-exit",
        "--crump-motion-ease-linear",
    ):
        assert token in css

    assert "transition: all" not in css
    assert "infinite" not in css
    assert "cubic-bezier(.34, 1.56" not in css
    assert "cubic-bezier(.34,1.56" not in css


def test_motion_system_covers_the_complete_interaction_story() -> None:
    css = motion_css()

    required_selectors = (
        ".cv-destination",
        ".cv-mnav-item",
        ".v1-settings-nav button",
        ".v1-starter-chip",
        ".v1-launch-card",
        ".crump57-book",
        ".v1-command-dock",
        "#filePreview:not(:empty)",
        ".crump50-upload-card",
        ".crump50-upload-progress",
        ".billing51-progress > i",
        ".crump53-progress-track > i",
        ".billing51-modal.is-visible .billing51-sheet",
        ".crump52-attach-overlay.is-visible .crump52-attach-sheet",
        ".crump50-sheet.is-visible",
        ".crump44-panel:not([hidden])",
        ".crump53-overlay:not([hidden]) .crump53-sheet",
        ".v1-settings-panel.is-active",
        "dialog[open] > :first-child",
        ".billing51-skeleton",
        ".crump57-skeleton i",
        ".cvp-skeleton i",
        ".cvl-skeleton i",
        ".typing-dots i",
    )
    for selector in required_selectors:
        assert selector in css, f"Missing motion coverage for {selector}"

    assert "animation-iteration-count: 2 !important" in css
    assert "animation-iteration-count: 6 !important" in css
    assert ".status-online" in css
    assert ".crump53-playback-pulse::after" in css
    assert "animation: none !important" in css
    assert ".message:not(.presence-message)" not in css


def test_appearance_cards_switch_surface_and_text_tokens_atomically() -> None:
    css = motion_css()

    assert "html.crump-theme-switching body.crump-v1-body" in css
    assert "transition: none !important" in css
    assert (
        "body.crump-v1-body .appearance-choices .appearance-choice {\n"
        "  transition-property: border-color, box-shadow, opacity;\n"
        "}" in css
    )


def test_entrances_never_hide_or_move_existing_content() -> None:
    css = motion_css()

    # Motion must not own app geometry, safe-area spacing, or theme colors.
    forbidden_layout_or_theme_declaration = re.compile(
        r"(?m)^\s*(?:position|inset|top|right|bottom|left|display|width|height|"
        r"min-width|max-width|min-height|max-height|padding|margin|color|"
        r"background|background-color)\s*:"
    )
    assert not forbidden_layout_or_theme_declaration.search(css)

    # A late-loaded stylesheet must not flash an already visible surface away.
    assert not re.search(r"opacity\s*:\s*0(?:[;\s}])", css)

    for keyframe in (
        "crump-motion-surface-enter",
        "crump-motion-content-enter",
        "crump-motion-skeleton-breathe",
        "crump-motion-stream-pulse",
    ):
        block_match = re.search(
            rf"@keyframes\s+{re.escape(keyframe)}\s*\{{(.*?)\n\}}",
            css,
            re.DOTALL,
        )
        assert block_match, keyframe
        assert "transform:" not in block_match.group(1)


def test_reduced_motion_contract_reaches_dynamic_and_pseudo_content() -> None:
    css = motion_css()
    reduced_start = css.index("@media (prefers-reduced-motion: reduce)")
    reduced = css[reduced_start:]

    assert "html:focus-within" in reduced
    assert "body.crump-v1-body *" in reduced
    assert "body.crump-v1-body *::before" in reduced
    assert "body.crump-v1-body *::after" in reduced
    assert "scroll-behavior: auto !important" in reduced
    assert "animation-delay: 0ms !important" in reduced
    assert "animation-duration: .01ms !important" in reduced
    assert "animation-iteration-count: 1 !important" in reduced
    assert "transition-delay: 0ms !important" in reduced
    assert "transition-duration: .01ms !important" in reduced
    assert "animation-name: none !important" in reduced


def test_motion_file_is_standalone_until_release_wiring() -> None:
    assert MOTION_PATH.is_file()
    assert MOTION_PATH.stat().st_size > 5_000
