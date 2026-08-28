from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_optional_name_setup_never_blocks_the_first_workspace_entry():
    app = read("app.html")
    controller = read("auth-controller.js")

    assert 'id="v1ProfileNudge"' in app
    assert 'aria-label="Optional profile setup"' in app
    assert 'id="v1ProfileNudgeAdd"' in app
    assert 'id="v1ProfileNudgeDismiss"' in app
    assert 'id="onboardingSkipBtn"' in app
    assert "startApp();\n    if (!user.fullName) maybeOfferProfileSetup();" in controller
    assert "startApp();\n        if (!activeUser.fullName) maybeOfferProfileSetup();" in controller
    assert "show('onboardingModal', 'flex');\n      return;" not in controller


def test_optional_profile_setup_is_scoped_dismissible_and_still_saves_to_the_server():
    shell = read("app.html")
    app = read("app.js")
    controller = read("auth-controller.js")

    assert "PROFILE_NUDGE_DISMISSED: 'crump_profile_nudge_dismissed'" in app
    assert "localStorage.setItem(profileNudgeKey(), 'true')" in controller
    assert "window.currentUser?.fullName || activeUser?.fullName" in controller
    assert "if (event.key === 'Escape') dismissProfileSetup();" in controller
    assert "body: JSON.stringify({ fullName: name })" in controller
    assert "localStorage.removeItem(profileNudgeKey())" in controller
    assert "window.addEventListener('crump:profile-updated', maybeOfferProfileSetup)" in controller
    assert 'id="onboardingError"' in shell and 'role="alert"' in shell
    assert "Enter a name or choose Not now." in controller


def test_settings_profile_save_is_truthful_and_refreshes_the_optional_nudge():
    app = read("app.js")

    assert "if (!response.ok || !data.success || !data.user)" in app
    assert "throw new Error(data.error || 'Your name could not be saved. Try again.')" in app
    assert "window.currentUser = data.user" in app
    assert "window.dispatchEvent(new CustomEvent('crump:profile-updated'))" in app
    assert "showToast(error.message || 'Your name could not be saved. Try again.', 'error')" in app


def test_terms_remain_a_required_server_saved_gate_before_workspace_entry():
    controller = read("auth-controller.js")

    terms_gate = controller[controller.index("if (!user.termsAcceptedAt)"):controller.index("if (user.fullName)")]
    assert "show('tosModal', 'flex')" in terms_gate
    assert "return;" in terms_gate
    assert "fetch('/api/account/accept-terms'" in controller
    assert "body: JSON.stringify({ version: TERMS_VERSION })" in controller


def test_name_completion_event_semantics_remain_server_authoritative():
    account = (ROOT / "backend" / "routes" / "account.py").read_text(encoding="utf-8")

    assert "first_completion = not str(auth.user.get('full_name') or '').strip()" in account
    assert "if first_completion:" in account
    assert "event_name='OnboardingCompleted'" in account
