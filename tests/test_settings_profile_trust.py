from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_settings_recovers_server_identity_without_exposing_it_to_logs():
    app = read("public/app.js")

    assert "async function restoreSettingsIdentity()" in app
    assert ".then(() => window.deviceAuth?.checkSession?.())" in app
    assert "const user = result?.authenticated ? result.data?.user : null;" in app
    assert "window.currentUser = { ...(window.currentUser || {}), ...user };" in app
    assert "const userEmail = String(user?.email || '').trim();" in app
    assert "emailField.value = userEmail;" in app
    assert "console.log" not in app[app.index("async function restoreSettingsIdentity()") : app.index("function loadSettingsValues()")]


def test_identity_recovery_starts_before_optional_preference_loading():
    app = read("public/app.js")
    fixture = read("tests/fixtures/settings-profile-trust.html")
    loader = app[app.index("function loadSettingsValues()") : app.index("window.saveSettings = async function()")]

    recovery = "if (!String(settingsEmail.value || '').trim()) void restoreSettingsIdentity();"
    optional_preferences = "window.CrumpPresence?.applyPreferencesToForm?.();"
    assert recovery in loader
    assert optional_preferences in loader
    assert loader.index(recovery) < loader.index(optional_preferences)
    assert "[Settings] Optional presence preferences could not be loaded:" in loader
    assert "Fixture-only optional preference failure" in fixture
    assert "email: '   '" in fixture
    assert "fixtureGuest ? null" in fixture


def test_settings_save_action_tracks_real_edits_and_blocks_duplicate_submissions():
    app = read("public/app.js")
    shell = read("public/app.html")
    css = read("public/crump-v1-body.css")

    assert "const SETTINGS_EDITABLE_IDS = Object.freeze([" in app
    assert "function settingsFormSignature()" in app
    assert "function syncSettingsSaveState()" in app
    assert "modal.addEventListener('input', update);" in app
    assert "modal.addEventListener('change', update);" in app
    assert "saveButton?.dataset.settingsSaving === 'true'" in app
    assert "disabled aria-disabled=\"true\" title=\"No changes to save\"" in shell
    assert 'placeholder="Sign in to view account email"' in shell
    assert 'aria-label="Account email" readonly' in shell
    assert ".settings-primary-btn:disabled" in css


def test_settings_profile_trust_browser_fixture_uses_the_real_runtime():
    fixture = read("tests/fixtures/settings-profile-trust.html")
    verifier = read("scripts/verify-settings-profile-trust.cjs")

    assert '<script src="/public/app.js?v=settings-profile-trust-fixture-1"></script>' in fixture
    assert "demo@example.com" in fixture
    assert "[{width: 1280, height: 760}, {width: 390, height: 844}]" in verifier
    assert "result.initial.saveDisabled" in verifier
    assert "result.reverted.saveDisabled" in verifier
    assert "result.behavior.horizontalOverflow" in verifier
    assert "Sign in to view account email" in verifier
    assert "guestFailed" in verifier


def test_workspace_script_updates_bypass_stale_pwa_and_edge_caches():
    worker = read("public/sw.js")
    vercel = read("vercel.json")

    assert "url.pathname === '/app.js'" in worker
    assert '"source": "/app.js"' in vercel
    app_header = vercel[vercel.index('"source": "/app.js"') :]
    assert '"Cache-Control", "value": "no-cache, no-store, must-revalidate"' in app_header
