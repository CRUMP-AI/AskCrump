from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def test_frontend_password_policy_matches_server_contract_at_runtime():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'function validatePasswordInput(password)' in controller
    assert "Password must be at least 10 characters long." in controller
    assert "Password must contain at least one letter and one number." in controller
    assert "input.setAttribute('minlength', '10')" in controller
    assert "input.setAttribute('maxlength', '256')" in controller
    assert "'registerPassword', 'registerPasswordConfirm', 'newPassword', 'confirmNewPassword'" in controller
    assert '10+ characters with a letter and number' in controller
    assert 'At least 10 characters with a letter and a number' in controller
    assert 'applyPasswordPolicyMarkup();' in controller


def test_signup_email_failure_has_explicit_recovery_ui():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    assert 'data.accountCreated && data.needsVerification' in controller
    assert "show('verificationNeeded')" in controller
    assert 'Use Resend verification' in controller
