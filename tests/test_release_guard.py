from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_vercel_build_runs_release_preflight_before_bundle():
    package = read("package.json")
    preflight = read("scripts/production-build-preflight.mjs")
    assert (
        '"build": "node scripts/production-build-preflight.mjs '
        '&& node scripts/build-native.mjs"'
    ) in package
    assert "scripts/check-javascript.mjs" in preflight
    assert "'-m', 'compileall', '-q', 'app.py', 'backend'" in preflight
    assert "process.env.VERCEL" in preflight


def test_subscription_runtime_is_part_of_javascript_contract():
    checker = read("scripts/check-javascript.mjs")
    assert "crump-subscriptions-5.3.2.js" in checker
    assert "ask-crump-new-body-v1-r151" in checker
    assert "crump-polish-5.6.js" in checker


def test_navigation_repair_is_precached_and_network_first():
    service_worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")

    for asset in (
        "/crump-navigation-5.2.5.js",
        "/crump-navigation-5.2.5.css",
        "/crump-navigation-5.9.30.js",
        "/crump-navigation-5.9.30.css",
    ):
        assert service_worker.count(asset) >= 2
        assert f"url.pathname === '{asset}'" in service_worker
        assert f"url.pathname === '{asset}'" in checker


def test_web_csp_allows_private_supabase_video_playback():
    vercel = read("vercel.json")
    assert "media-src 'self' blob: https://*.supabase.co https://*.storage.supabase.co" in vercel
    assert "connect-src 'self' https://askcrump.com https://www.askcrump.com https://*.supabase.co https://*.storage.supabase.co" in vercel

def test_conversation_renderer_delegates_automatic_scroll_to_single_owner():
    ui = read("public/ui-functions.js")
    scroll = read("public/crump-5.2.2.js")

    assert "typeof window.crumpScrollManager?.scrollToBottom === 'function'" in ui
    assert "window.crumpScrollManager.scrollToBottom('auto')" in ui
    assert "if (shouldStick || presence) requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });" not in ui
    assert "state.scroll.suppressLegacyBottomUntil = Date.now() + 3200" in scroll
    assert "if (!force && Date.now() < state.scroll.suppressLegacyBottomUntil) return;" in scroll

def test_new_reply_anchor_is_synchronous_and_survives_sync_rerenders():
    scroll = read("public/crump-5.2.2.js")
    css = read("public/crump-5.2.2.css")

    assert "activeReplyShouldHold" in scroll
    assert "cancelActiveReplyAnchor" in scroll
    assert "shouldPreserveAnchor" in scroll
    assert "state.scroll.activeReplyUntil = state.scroll.suppressLegacyBottomUntil" in scroll
    assert "requestAnimationFrame(() => {\n      requestAnimationFrame(() => {" not in scroll
    assert "overflow-anchor: none !important;" in css
