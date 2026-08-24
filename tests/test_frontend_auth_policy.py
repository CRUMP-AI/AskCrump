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
    assert "'registerPassword', 'newPassword', 'confirmNewPassword'" in controller
    assert '10+ characters with a letter and number' in controller
    assert 'At least 10 characters with a letter and a number' in controller
    assert 'applyPasswordPolicyMarkup();' in controller


def test_registration_has_one_verifiable_password_field_and_tracks_safe_validation_reasons():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'id="registerPassword"' in app
    assert 'id="registerPasswordConfirm"' not in app
    assert 'data-password-target="registerPassword"' in app
    assert 'Free to start. No card required.' in app
    assert 'secure verification link' in app
    assert "trackFunnel('SignupValidationFailed', {reason})" in controller
    assert 'password_length' in controller and 'password_rules' in controller
    assert "form.addEventListener('invalid'" in controller
    assert 'email_format' in controller and 'required_field' in controller


def test_signup_email_failure_has_explicit_recovery_ui():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    assert 'data.accountCreated && data.needsVerification' in controller
    assert "show('verificationNeeded')" in controller
    assert 'Use Resend verification' in controller
