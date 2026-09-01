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
    assert 'Ask questions, create useful work, and pick up where you left off.' in app
    assert 'Free to start—no card required.' in app
    assert 'secure verification link' in app
    assert 'id="registerName"' not in app
    assert 'id="registerTerms" type="checkbox" required' in app
    assert 'I am at least 17 and agree to the' in app
    assert 'href="/legal.html#terms"' in app
    assert 'href="/legal.html#privacy"' in app
    assert 'Full Name' not in app[app.index('id="registerForm"'):app.index('id="forgotPasswordForm"')]
    assert "fullName: byId('registerName')?.value.trim() || ''" in controller
    assert "const TERMS_VERSION = '2026-08-01'" in controller
    assert "termsAccepted: byId('registerTerms')?.checked === true" in controller
    assert 'termsVersion: TERMS_VERSION' in controller
    assert "trackFunnel('SignupValidationFailed', {reason})" in controller
    assert 'password_length' in controller and 'password_rules' in controller and 'terms_required' in controller
    assert "form.addEventListener('invalid'" in controller
    assert 'email_format' in controller and 'required_field' in controller


def test_every_user_entered_password_can_be_checked_before_submission():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    targets = ('loginPassword', 'registerPassword', 'newPassword', 'confirmNewPassword')
    for target in targets:
        assert f'data-password-target="{target}"' in app
        assert f'aria-controls="{target}"' in app
    assert app.count('class="v1-password-toggle"') == len(targets)
    assert app.count('aria-pressed="false">Show</button>') == len(targets)
    assert 'aria-label="Show current password"' in app
    assert app.count('aria-label="Show new password"') == 2
    assert 'aria-label="Show password confirmation"' in app
    assert "document.querySelectorAll('[data-password-target]')" in controller
    assert "button.textContent = showing ? 'Show' : 'Hide'" in controller
    assert "button.setAttribute('aria-pressed', String(!showing))" in controller
    assert "button.dataset.passwordLabel || 'password'" in controller
    assert "input.focus({preventScroll: true})" in controller
    assert "resetPassword?.closest?.('.form-group')?.querySelector('.form-hint')" in controller


def test_mobile_signup_keeps_the_primary_action_above_a_short_phone_fold():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    body = (PUBLIC / 'crump-v1-body.css').read_text(encoding='utf-8')
    registration = app[app.index('id="registerForm"'):app.index('id="forgotPasswordForm"')]

    assert registration.count('class="form-group"') == 2
    assert registration.index('id="registerEmail"') < registration.index('id="registerPassword"')
    assert registration.index('id="registerPassword"') < registration.index('id="registerTerms"')
    assert registration.index('id="registerTerms"') < registration.index('Create free account')
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


def test_cold_signup_entry_keeps_product_value_and_assurance_readable():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    body = (PUBLIC / 'crump-v1-body.css').read_text(encoding='utf-8')
    registration = app[app.index('id="registerForm"'):app.index('id="forgotPasswordForm"')]

    assert 'Ask questions, create useful work, and pick up where you left off.' in registration
    assert 'Free to start—no card required.' in registration
    assurance = body[body.index('.v1-signup-assurance {'):]
    assert 'color: #8f9498;' in assurance[:240]
    assert 'font-size: 11px;' in assurance[:240]
    assert 'id="registrationExploreLink" href="/"' in registration
    assert 'Explore Ask Crump first' in registration
    assert "document: {href: '/ai-document-generator', label: 'See document examples first'}" in controller
    assert "presentation: {href: '/ai-presentation-maker', label: 'See presentation examples first'}" in controller
    assert "resume: {href: '/ai-resume-builder', label: 'See résumé examples first'}" in controller
    assert "video: {href: '/ai-video-generator', label: 'Explore Video Studio first'}" in controller
    assert 'configureRegistrationExploreLink();' in controller
    assert "link.dataset.exploreDestination = kind || 'overview';" in controller
    assert 'function wireExploreRegistrationLink()' in controller
    assert "trackFunnel('RegistrationExplore', {destination});" in controller
    assert 'wireExploreRegistrationLink();' in controller
    assert '.v1-registration-explore a:focus-visible' in body


def test_registration_offer_matches_enforced_free_limits_and_canonical_product_map():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    config = (ROOT / 'backend' / 'config.py').read_text(encoding='utf-8')
    features = (ROOT / 'backend' / 'feature_service.py').read_text(encoding='utf-8')
    brand = app[app.index('class="v1-auth-brand"'):app.index('class="v1-auth-stage"')]
    assurance = (
        'Free includes 25 messages each day and 2 private Projects. '
        'We’ll email a secure verification link; no card required.'
    )

    assert 'Ask, Projects, Create, Video, Library, and You' in brand
    for destination in ('Ask', 'Projects', 'Create', 'Video', 'Library', 'You'):
        assert f'<span>{destination}</span>' in brand
    assert '<span>Research</span>' not in brand
    assert '<span>Memory</span>' not in brand
    assert 'id="registrationAssurance"' in app
    assert assurance in app
    assert assurance in controller
    assert 'Creating your account does not start billing; checkout remains a separate confirmation.' in controller
    assert "if (assurance) assurance.textContent = plan" in controller
    assert "free_daily_messages=int(os.getenv('FREE_DAILY_MESSAGES', '25'))" in config
    assert 'PROJECT_LIMITS = {"free": 2' in features


def test_registration_preserves_allowlisted_creation_and_paid_plan_promises():
    app = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')

    assert 'id="registrationTitle"' in app
    assert 'id="registrationDescription"' in app
    assert 'id="registrationSubmitBtn"' in app
    assert 'const REGISTRATION_CREATION_HANDOFFS = Object.freeze({' in controller
    assert "title: 'Create your presentation workspace.'" in controller
    assert 'editable PowerPoint draft' in controller
    assert "title: 'Build your résumé workspace.'" in controller
    assert 'without invented credentials' in controller
    assert "title: 'Open your Video Studio.'" in controller
    assert 'see its Crump Credit cost' in controller
    assert 'find completed clips in Projects → Files' in controller
    assert 'keep completed clips in your private Library' not in controller
    assert 'const REGISTRATION_PLAN_HANDOFFS = Object.freeze({' in controller
    assert 'Professional includes Advanced Intelligence at $20/month and remains unpurchased until you review and confirm checkout' in controller
    assert 'Enterprise includes Advanced Intelligence at $50/month and remains unpurchased until you review and confirm checkout' in controller
    assert 'function configureRegistrationHandoff()' in controller
    assert "button.textContent = plan?.button || (creation ? 'Create account & continue' : 'Create free account');" in controller
    assert 'configureRegistrationHandoff();' in controller


def test_explicit_generic_free_signup_clears_stale_specific_intents():
    controller = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    fixture = (ROOT / 'tests' / 'fixtures' / 'cold-auth-entry-delay.html').read_text(encoding='utf-8')

    assert "params.get('signup') === '1' && context.plan === 'free'" in controller
    assert 'localStorage.removeItem(PLAN_INTENT_KEY)' in controller
    assert "if (params.get('signup') === '1')" in controller
    assert 'localStorage.removeItem(CREATION_INTENT_KEY)' in controller
    assert "get('stale') === '1'" in fixture
    assert "plan:'professional'" in fixture
    assert "kind:'resume'" in fixture


def test_cold_signup_explore_fixture_uses_real_runtime_without_production_writes():
    fixture = (
        ROOT / 'tests' / 'fixtures' / 'cold-auth-entry-delay.html'
    ).read_text(encoding='utf-8')

    assert 'id="registrationExploreLink" href="/"' in fixture
    assert 'id="registrationAssurance"' in fixture
    assert 'id="fixtureEvents"' in fixture
    assert "window.__fixture.events.push(payload);" in fixture
    assert "addEventListener('click', event => event.preventDefault())" in fixture
    assert '/public/auth-controller.js?v=fixture-cold-auth-delay-4' in fixture
    assert 'https://' not in fixture
    assert 'askcrump.com' not in fixture


def test_registration_autofill_fixture_uses_real_local_runtime_without_production_writes():
    fixture = (
        ROOT / 'tests' / 'fixtures' / 'registration-autofill-submit.html'
    ).read_text(encoding='utf-8')

    assert '/public/auth-resilience.js?v=fixture-registration-autofill' in fixture
    assert '/public/auth-controller.js?v=fixture-registration-autofill-4' in fixture
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
    assert '/public/auth-controller.js?v=fixture-auth-focus-4' in fixture
    assert 'id="fixtureEvents"' in fixture
    assert 'window.__fixture = {events: []}' in fixture
    assert fixture.count('data-password-target=') == 4
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
    assert 'enter your workspace automatically' in app
    assert 'Already verified? Sign in' in app
    assert 'id="registrationPendingResendBtn"' in app
    assert 'function showRegistrationPending(email, message' in controller
    assert "showRegistrationPending(email, data.message || 'Verification email sent.')" in controller
    assert "if (loginEmail) loginEmail.value = email" in controller
    assert "byId('registrationPending')?.focus()" in controller
    assert 'Email verified. Your workspace is ready.' in controller
    assert 'Sign in here if you completed verification on another device.' in controller
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
