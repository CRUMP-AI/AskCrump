from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def js_array(source: str, name: str) -> list[str]:
    match = re.search(rf"var {name} = \[([^\]]*)\];", source)
    assert match is not None
    return re.findall(r"'([^']+)'", match.group(1))


def test_shell_exposes_one_truthful_desktop_and_mobile_information_architecture() -> None:
    shell = read("public/crump-vision-shell-1.0.js")
    assert js_array(shell, "ORDER") == ["home", "chats", "projects", "library", "studios", "you"]
    assert js_array(shell, "MOBILE_ORDER") == ["home", "chats", "projects", "library", "studios"]
    assert js_array(shell, "MORE_DESTINATIONS") == []
    assert "button.id = 'cvMobileYou'" in shell
    assert '<span>New</span>' in shell


def test_chats_restores_the_prior_mounted_destination_without_duplicate_measurement() -> None:
    shell = read("public/crump-vision-shell-1.0.js")
    assert "var conversationDrawerReturnId = null;" in shell
    assert "var returnId = currentId !== 'home' ? currentId : null;" in shell
    assert "conversationDrawerReturnId = returnId;" in shell
    assert "navigate(returnId, { silent: true });" in shell
    assert "closeConversationDrawer(true, true);" in shell
    assert "closeConversationDrawer(false, false);" in shell
    assert "if (!silent) {\n      track(id);\n      dispatchShow(id);\n    }" in shell


def test_browser_workspace_is_prepared_but_remains_fail_closed_until_released() -> None:
    app = read("public/app.html")
    browser = read("public/crump-browser-workspace-1.0.js")
    shell = read("public/crump-vision-shell-1.0.js")
    source_lock = read("backend/config.py")
    route = read("backend/routes/browser.py")
    listing = read("store/listing.en-US.json")

    assert 'data-browser-workspace-entry' in app
    assert 'data-v1-command="browser"' in app
    browser_entry = re.search(r'<button\b[^>]*data-browser-workspace-entry[^>]*>', app)
    assert browser_entry is not None
    assert re.search(r'\shidden(?:\s|$)', browser_entry.group(0))
    assert 'aria-hidden="true"' in browser_entry.group(0)
    assert "entry.hidden = state.released !== true;" in browser
    assert "entry.setAttribute('aria-hidden', state.released === true ? 'false' : 'true');" in browser
    assert "if (id === 'browser') return;" in shell
    assert "AUTONOMOUS_CRUMP_BROWSER_PUBLIC_RELEASED = False" in source_lock
    assert '"code": "BROWSER_NOT_RELEASED"' in route
    assert "browser_workspace_environment_released()" in route
    listing_lower = listing.casefold()
    assert "browser workspace" not in listing_lower
    assert "browser control" not in listing_lower


def test_premium_palette_typography_and_mobile_utility_are_release_owned() -> None:
    css = read("public/crump-vision-shell-1.0.css")
    for token in ("#070a0e", "#d5b971", "#b69855", "#f1efe9", "#8a9196"):
        assert token in css
    assert 'font-family: Georgia, "Times New Roman", serif' in css
    assert 'font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' in css
    assert ".cv-mobile-you" in css
    assert "min-width: 44px" in css
    assert "min-height: 44px" in css


def test_web_service_worker_and_native_loader_use_one_ui_revision() -> None:
    app = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    service_worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")
    revision = "5.9.76-premium-browser-workspace-1"

    for asset in (
        "runtime-body-v1.js",
        "crump-vision-shell-1.0.css",
        "crump-vision-shell-1.0.js",
        "crump-vision-studios-1.0.css",
        "crump-vision-studios-1.0.js",
        "crump-browser-workspace-1.0.css",
        "crump-browser-workspace-1.0.js",
    ):
        assert f"/{asset}?v={revision}" in app
        assert f"/{asset}?v={revision}" in service_worker

    for source in (runtime, native, service_worker):
        for asset in (
            "onboarding.js",
            "crump-v1-body.js",
            "crump-polish-5.6.js",
            "crump-navigation-5.9.30.js",
        ):
            assert f"/{asset}?v={revision}" in source
    assert "ask-crump-new-body-v1-r283-premium-browser-workspace-1" in service_worker


def test_tutorial_and_store_copy_match_the_visible_release() -> None:
    tutorial = read("public/onboarding.js")
    listing = json.loads(read("store/listing.en-US.json"))
    desktop = "Home, Chats, Projects, Library, Studios, and You"
    assert "const DESKTOP_DESTINATIONS = Object.freeze(['Home', 'Chats', 'Projects', 'Library', 'Studios', 'You'])" in tutorial
    assert "const MOBILE_DESTINATIONS = Object.freeze(['Home', 'Chats', 'Projects', 'Library', 'Studios'])" in tutorial
    assert "Browse with sources" in tutorial
    assert desktop in listing["apple"]["description"]
    assert desktop in listing["google"]["fullDescription"]


def test_studios_delegates_to_existing_image_and_video_tools() -> None:
    studios = read("public/crump-vision-studios-1.0.js")
    assert "window.CrumpImageStudio && window.CrumpImageStudio.open" in studios
    assert "window.CrumpProduct53 && window.CrumpProduct53.open" in studios
    assert "open('video')" in studios
    assert "Choose aspect ratio, quality, and optional references inside Image Studio" in studios
