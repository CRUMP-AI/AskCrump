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


def test_registration_explains_password_readiness_before_submission():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    body = (PUBLIC / 'crump-v1-body.css').read_text(encoding='utf-8')

    assert 'id="registerPasswordHint" class="v1-password-requirements"' in app
    assert 'data-password-rule="length"' in app
    assert 'data-password-rule="letter"' in app
    assert 'data-password-rule="number"' in app
    assert 'id="registerPasswordStatus"' in app and 'aria-live="polite"' in app
    assert 'aria-describedby="registerPasswordHint"' in app
    assert 'function passwordRuleState(password)' in controller
    assert 'function updateRegistrationPasswordGuidance' in controller
    assert "status.textContent = 'Password meets all requirements.'" in controller
    assert 'updateRegistrationPasswordGuidance({touched: true})' in controller
    assert "input.setAttribute('aria-invalid', String(!complete))" in controller
    assert '.v1-password-requirements .is-met' in body
    assert '.form-input[aria-invalid="true"]' in body


def test_registration_has_one_verifiable_password_field_and_tracks_safe_validation_reasons():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'id="registerPassword"' in app
    assert 'id="registerPasswordConfirm"' not in app
    assert 'data-password-target="registerPassword"' in app
    assert 'Free to start. No card required.' in app
    assert 'secure verification link' in app
    assert 'id="registerName"' not in app
    assert 'Full Name' not in app[app.index('id="registerForm"'):app.index('id="forgotPasswordForm"')]
    assert "fullName: byId('registerName')?.value.trim() || ''" in controller
    assert "trackFunnel('SignupValidationFailed', {reason})" in controller
    assert 'password_length' in controller and 'password_rules' in controller
    assert "form.addEventListener('invalid'" in controller
    assert 'email_format' in controller and 'required_field' in controller


def test_mobile_signup_keeps_the_primary_action_above_a_short_phone_fold():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    body = (PUBLIC / 'crump-v1-body.css').read_text(encoding='utf-8')
    registration = app[app.index('id="registerForm"'):app.index('id="forgotPasswordForm"')]

    assert registration.count('class="form-group"') == 2
    assert registration.index('id="registerEmail"') < registration.index('id="registerPassword"')
    assert registration.index('id="registerPassword"') < registration.index('Create free account')
    assert '@media (max-width: 560px) and (max-height: 700px)' in body
    assert '#registerForm .btn-primary { min-height: 52px' in body
    assert "trackFunnel('SignupStarted')" in controller
    assert "trackFunnel('SignupCredentialsReady')" in controller
    assert "email?.value.trim()" in controller
    assert "validatePasswordInput(password?.value || '')" in controller
    assert "const trackCredentialsReady = () =>" in controller
    assert "form.addEventListener('input', trackCredentialsReady" in controller
    assert "form.addEventListener('focusin', trackSignupStarted)" not in controller
    assert (
        controller.index("trackCredentialsReady();\n      trackFunnel('SignupSubmitted')")
        < controller.index("const restore = setBusy", controller.index("function wireRegistration"))
    )


def test_registration_autofill_fixture_uses_real_local_runtime_without_production_writes():
    fixture = (
        ROOT / 'tests' / 'fixtures' / 'registration-autofill-submit.html'
    ).read_text(encoding='utf-8')

    assert '/public/auth-resilience.js?v=fixture-registration-autofill' in fixture
    assert '/public/auth-controller.js?v=fixture-registration-autofill-2' in fixture
    assert "document.getElementById('registerEmail').value = 'autofill@example.test'" in fixture
    assert "document.getElementById('registerPassword').value = 'Autofill1234'" in fixture
    assert "Fixture stopped before account creation." in fixture
    assert 'https://' not in fixture
    assert 'askcrump.com' not in fixture


def test_auth_view_transitions_move_focus_to_the_first_actionable_field():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    fixture = (
        ROOT / 'tests' / 'fixtures' / 'auth-navigation-focus.html'
    ).read_text(encoding='utf-8')

    for view, container_id, field_id in (
        ('login', 'loginForm', 'loginEmail'),
        ('register', 'registerForm', 'registerEmail'),
        ('forgot', 'forgotPasswordForm', 'forgotPasswordEmail'),
        ('reset', 'resetPasswordForm', 'newPassword'),
    ):
        assert f"{view}: {{containerId: '{container_id}', fieldId: '{field_id}'}}" in controller
    assert 'function focusAuthView(view)' in controller
    assert "requestAnimationFrame(() => byId(fieldId)?.focus({preventScroll: true}))" in controller
    assert "showAuth('register')" in controller
    assert "showAuth('forgot')" in controller
    assert "showAuth('reset')" in controller
    assert 'role="alert" aria-live="assertive"' in app
    assert '/public/auth-controller.js?v=fixture-auth-focus-3' in fixture
    assert 'id="fixtureEvents"' in fixture
    assert 'window.__fixture = {events: []}' in fixture
    assert 'credential-free-auth-probe' not in fixture
    assert 'https://' not in fixture
    assert 'askcrump.com' not in fixture


def test_login_validation_failures_are_visible_and_observable_before_network_submission():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    login = controller[
        controller.index('function wireLogin()'):
        controller.index('function wireRegistration()')
    ]
    assert "form.addEventListener('invalid'" in login
    assert "field?.setAttribute('aria-invalid', 'true')" in login
    assert 'Enter a valid email address.' in login
    assert 'Enter your email.' in login
    assert 'Enter your password.' in login
    assert "trackFunnel('LoginValidationFailed', {reason})" in login
    assert "trackFunnel('LoginSubmitted')" in login
    assert "trackFunnel('LoginCompleted')" in login
    assert "trackFunnel('LoginFailed'" in login


def test_signup_success_has_durable_verification_handoff_and_recovery_ui():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'id="registrationPending"' in app
    assert 'Check your inbox.' in app
    assert 'id="registrationPendingSigninBtn"' in app
    assert 'id="registrationPendingResendBtn"' in app
    assert 'function showRegistrationPending(email, message' in controller
    assert "showRegistrationPending(email, data.message || 'Verification email sent.')" in controller
    assert "if (loginEmail) loginEmail.value = email" in controller
    assert "byId('registrationPending')?.focus()" in controller
    assert "setTimeout(() => { hide('registerForm'); show('loginForm'); }, 1800)" not in controller


def test_signup_email_failure_preserves_created_account_and_explicit_recovery_ui():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'data.accountCreated && data.needsVerification' in controller
    assert "trackFunnel('AccountCreated', {verification_delivery: 'failed'})" in controller
    assert 'Your account exists, but the verification email could not be delivered.' in controller
    assert '{deliveryFailed: true}' in controller
    assert "successId: 'registrationPendingSuccess'" in controller
    assert "errorId: 'registrationPendingError'" in controller


def test_failed_or_reused_verification_link_exposes_an_actionable_recovery_surface():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    fixture = (
        ROOT / 'tests' / 'fixtures' / 'verification-link-recovery.html'
    ).read_text(encoding='utf-8')

    assert 'Email verification needs attention' in app
    assert 'Enter your email above to request a fresh link' in app
    assert 'role="region" aria-labelledby="verificationNeededTitle"' in app
    assert 'invalid, expired, or already used' in controller
    failed_branch = controller[
        controller.index('function showVerificationResult'):
        controller.index('async function bootstrap')
    ]
    assert "show('verificationNeeded')" in failed_branch
    assert "byId('loginEmail')?.focus({preventScroll: true})" in failed_branch
    assert '/public/auth-controller.js?v=fixture-verification-recovery-2' in fixture
    assert 'https://' not in fixture
    assert 'askcrump.com' not in fixture


def test_password_reset_success_has_a_durable_private_signin_handoff():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    fixture = (
        ROOT / 'tests' / 'fixtures' / 'password-reset-handoff.html'
    ).read_text(encoding='utf-8')

    reset_bootstrap = controller[
        controller.index("const resetToken = params.get('token')"):
        controller.index("const verification = params.get('verification')")
    ]
    reset_submit = controller[
        controller.index("byId('resetPasswordFormElement')"):
        controller.index("byId('resendVerificationBtn')")
    ]

    assert "history.replaceState({}, document.title, location.pathname)" in reset_bootstrap
    assert "if (resetForm) delete resetForm.dataset.token" in reset_submit
    assert "setText('loginSuccess', data.message || 'Password updated." in reset_submit
    assert "showAuth('login')" in reset_submit
    assert "login: {containerId: 'loginForm', fieldId: 'loginEmail'}" in controller
    assert "setTimeout(() => { history.replaceState" not in reset_submit
    assert 'id="loginSuccess" class="auth-success" role="status" aria-live="polite"' in app
    assert '/public/auth-resilience.js?v=fixture-password-reset-handoff' in fixture
    assert '/public/auth-controller.js?v=fixture-password-reset-handoff-2' in fixture
    assert 'fixture-token' not in fixture
    assert 'https://' not in fixture
    assert 'askcrump.com' not in fixture
