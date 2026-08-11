from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def test_frontend_password_policy_matches_server_contract():
    html = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'Minimum 8 characters' not in html
    assert 'At least 8 characters' not in html
    assert html.count('minlength="10"') >= 4
    assert html.count('maxlength="256"') >= 4
    assert 'At least 10 characters with a letter and a number' in html
    assert "Password must be at least 10 characters long." in controller
    assert "Password must contain at least one letter and one number." in controller


def test_signup_email_failure_has_explicit_recovery_ui():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    assert 'data.accountCreated && data.needsVerification' in controller
    assert "show('verificationNeeded')" in controller
    assert 'Use Resend verification' in controller
