from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_shared_auth_transport_bounds_fetch_and_body_parsing():
    transport = read_public("auth-resilience.js")

    assert "DEFAULT_TIMEOUT_MS = 20_000" in transport
    assert "SESSION_TIMEOUT_MS = 10_000" in transport
    assert "LOGIN_TIMEOUT_MS = 30_000" in transport
    assert "new AbortController()" in transport
    assert "signal: controller.signal" in transport
    assert "data = await response.json()" in transport
    assert transport.index("data = await response.json()") < transport.index(
        "window.clearTimeout(timeoutId)"
    )
    assert "timeoutError.code = 'AUTH_REQUEST_TIMEOUT'" in transport


def test_entry_and_recovery_actions_use_the_shared_bounded_transport():
    controller = read_public("auth-controller.js")

    assert "fetch(" not in controller
    assert "window.CrumpAuthTransport.request" in controller
    for route in (
        "/api/auth/register",
        "/api/auth/resend-verification",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/account/accept-terms",
        "/api/account/profile",
    ):
        assert route in controller
    assert "the account may already exist" in controller
    assert "Check your inbox before retrying" in controller


def test_login_session_and_logout_requests_are_bounded_and_login_reconciles():
    device = read_public("device-auth.js")

    assert "fetch(" not in device
    assert device.count("window.CrumpAuthTransport.request") >= 5
    assert "error?.code !== 'AUTH_REQUEST_TIMEOUT'" in device
    assert "A web login can set its HttpOnly cookie" in device
    assert "return {success: true, data: confirmation.data, recovered: true}" in device
    assert "timeoutMs: window.CrumpAuthTransport.SESSION_TIMEOUT_MS" in device
    assert "timeoutMs: window.CrumpAuthTransport.LOGIN_TIMEOUT_MS" in device


def test_auth_transport_is_release_versioned_and_network_first():
    shell = read_public("app.html")
    worker = read_public("sw.js")

    assert '<script defer src="/auth-resilience.js?v=5.9.76"></script>' in shell
    assert shell.index("/auth-resilience.js?v=5.9.76") < shell.index(
        "/device-auth.js?v=5.9.76"
    )
    assert "'/auth-resilience.js?v=5.9.76'" in worker
    assert "url.pathname === '/auth-resilience.js'" in worker
    assert "ask-crump-new-body-v1-r193" in worker


def test_auth_stall_fixtures_are_loopback_only_and_load_real_runtime_assets():
    registration = (
        ROOT / "tests" / "fixtures" / "registration-submit-stall.html"
    ).read_text(encoding="utf-8")
    login = (ROOT / "tests" / "fixtures" / "login-response-stall.html").read_text(
        encoding="utf-8"
    )

    assert '/public/auth-resilience.js?v=fixture-registration-stall-2' in registration
    assert '/public/auth-controller.js?v=fixture-registration-stall-2' in registration
    assert "options.signal?.addEventListener('abort'" in registration
    assert '/public/auth-resilience.js?v=fixture-login-stall' in login
    assert '/public/device-auth.js?v=fixture-login-stall' in login
    assert '/public/auth-controller.js?v=fixture-login-stall' in login
    assert "issued = true" in login
    assert "example.test" in login
    assert 'value="' not in registration
    assert "https://" not in registration
    assert "https://" not in login
    assert "askcrump.com" not in registration
    assert "askcrump.com" not in login


def test_delayed_session_fixture_requires_a_fourth_post_login_confirmation():
    fixture = (
        ROOT / "tests" / "fixtures" / "login-session-propagation.html"
    ).read_text(encoding="utf-8")

    assert '/public/auth-resilience.js?v=fixture-login-propagation' in fixture
    assert '/public/device-auth.js?v=fixture-login-propagation' in fixture
    assert '/public/auth-controller.js?v=fixture-login-propagation' in fixture
    assert 'postLoginChecks >= 4' in fixture
    assert 'fixture@example.test' in fixture
    assert 'https://' not in fixture
    assert 'askcrump.com' not in fixture
