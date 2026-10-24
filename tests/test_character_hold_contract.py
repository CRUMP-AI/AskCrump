from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNTIME_CHARACTER_SURFACES = (
    "public/app.html",
    "public/runtime-body-v1.js",
    "public/crump-v1-body.js",
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

CHARACTER_ASSET_ONLY_SURFACES = (
    "public/crump-v1-body.css",
)

FORBIDDEN_CHARACTER_MARKERS = (
    "/assets/brand/crump-mascot.png",
    "/assets/brand/crump-mascot-idle.",
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

    for relative in CHARACTER_ASSET_ONLY_SURFACES:
        source = read(relative)
        for marker in (
            "/assets/brand/crump-mascot.png",
            "/assets/brand/crump-mascot-idle.",
        ):
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

    assert "ask-crump-new-body-v1-r273-account-owner-boundary-1" in worker
    assert "/ui-functions.js?v=5.9.76-private-owner-boundary-1" in worker
    assert "/crump-4.3.js?v=5.9.76-atelier-workspace-1" in worker
    assert "Zero-runtime-mascot contract failed" in checker
    for relative in (
        "public/app.html",
        "public/runtime-body-v1.js",
        "public/crump-v1-body.js",
    ):
        assert f"'{relative}'" in checker
    assert "const characterAssetOnlyFiles" in checker
    assert "'public/crump-v1-body.css'" in checker
    assert "'/assets/brand/crump-mascot-idle.'" in checker
