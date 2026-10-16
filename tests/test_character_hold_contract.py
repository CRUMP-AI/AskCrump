from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNTIME_CHARACTER_SURFACES = (
    "public/ui-functions.js",
    "public/crump-4.3.js",
    "public/crump-vision-chats-1.0.js",
    "public/crump-vision-projects-1.0.js",
    "public/crump-vision-library-1.0.js",
    "public/crump-vision-demo-1.0.js",
    "public/crump-vision-home-1.0.js",
    "public/crump-vision-shell-1.0.js",
    "public/sw.js",
)

FORBIDDEN_CHARACTER_MARKERS = (
    "/assets/brand/crump-mascot.png",
    "MASCOT_SRC",
    "crump-message-avatar",
    "crump-empty-mascot",
    "cvp-empty-mascot",
    "cvl-empty-mascot",
    ".mascot(",
    "mascot: mascot",
)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_unapproved_character_is_absent_from_runtime_surfaces() -> None:
    for relative in RUNTIME_CHARACTER_SURFACES:
        source = read(relative)
        for marker in FORBIDDEN_CHARACTER_MARKERS:
            assert marker not in source, f"{marker!r} must not ship from {relative}"


def test_assistant_and_thinking_identity_use_the_restrained_status_pip() -> None:
    for relative in (
        "public/ui-functions.js",
        "public/crump-4.3.js",
        "public/crump-vision-chats-1.0.js",
        "public/crump-vision-demo-1.0.js",
    ):
        assert "crump-message-status-pip" in read(relative)


def test_character_hold_is_cache_addressable_and_guarded() -> None:
    worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")

    assert "ask-crump-new-body-v1-r266-response-continuity-cleanup-1" in worker
    assert "/ui-functions.js?v=5.9.76-response-continuity-cleanup-1" in worker
    assert "/crump-4.3.js?v=5.9.76-atelier-workspace-1" in worker
    assert "Zero-runtime-mascot contract failed" in checker
