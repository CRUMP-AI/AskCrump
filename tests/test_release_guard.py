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
    assert "ask-crump-new-body-v1-r20" in checker
    assert "crump-polish-5.6.js" in checker


def test_web_csp_allows_private_supabase_video_playback():
    vercel = read("vercel.json")
    assert "media-src 'self' blob: https://*.supabase.co https://*.storage.supabase.co" in vercel
    assert "connect-src 'self' https://askcrump.com https://www.askcrump.com https://*.supabase.co https://*.storage.supabase.co" in vercel
