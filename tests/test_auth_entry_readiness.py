from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def test_authenticated_entry_does_not_wait_for_secondary_sync():
    controller = (PUBLIC / "auth-controller.js").read_text(encoding="utf-8")

    bootstrap = controller[controller.index("async function bootstrap()") : controller.index("function wireNavigation()")]
    login = controller[controller.index("function wireLogin()") : controller.index("function wireRegistration()")]

    assert "async function pullServerState()" not in controller
    assert "await pullServerState()" not in bootstrap
    assert "await pullServerState()" not in login
    assert bootstrap.index("applyServerSettings(session.data.settings)") < bootstrap.index("routeAuthenticatedUser(activeUser)")
    assert login.index("applyServerSettings(result.data.settings)") < login.index("routeAuthenticatedUser(activeUser)")


def test_server_authoritative_sync_starts_after_the_shell_is_open():
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")

    authenticated = app[app.index("window.initializeAuthenticatedApp") : app.index("window.initializeApp = function()")]
    assert "Sync is server-authoritative. This call is safe before or after initializeApp()." in authenticated
    assert "window.syncChatsFromServer();" in authenticated
    assert "window.startAutoSync();" in authenticated


def test_browser_fixture_reproduces_a_never_settling_sync_without_real_credentials():
    fixture = (ROOT / "tests" / "fixtures" / "auth-entry-sync-stall.html").read_text(encoding="utf-8")

    assert '<script src="/public/auth-controller.js?v=fixture-2"></script>' in fixture
    assert "return new Promise(() => {});" in fixture
    assert "fixture@example.test" in fixture
    assert "fetch(" not in fixture
    assert "askcrump.com" not in fixture


def test_delayed_session_fixture_protects_both_cold_auth_entry_paths():
    fixture = (ROOT / "tests" / "fixtures" / "cold-auth-entry-delay.html").read_text(encoding="utf-8")

    assert '<script src="/public/auth-controller.js?v=fixture-cold-auth-delay-2"></script>' in fixture
    assert "setTimeout(resolve, 3000)" in fixture
    assert "sessionSettled: false" in fixture
    assert "get('authenticated') === '1'" in fixture
    assert "fixtureAppState" in fixture
    assert "startupEvents.push('runtime-ready')" in fixture
    assert "startupEvents.push('app-initialized')" in fixture
    assert "startupEvents.push('authenticated-initialized')" in fixture
    assert "Fixture stopped before account creation." in fixture
    assert "fetch(" not in fixture
    assert "https://" not in fixture
    assert "askcrump.com" not in fixture


def test_bootstrap_exposes_a_truthful_surface_before_the_bounded_session_probe():
    controller = (PUBLIC / "auth-controller.js").read_text(encoding="utf-8")
    bootstrap = controller[controller.index("async function bootstrap()") : controller.index("function wireNavigation()")]

    assert "function showReturningVisitorGate()" in controller
    assert "const bootstrapAuthFlowRevision = authFlowRevision;" in bootstrap
    assert bootstrap.index("showAuth('register')") < bootstrap.index("await window.CrumpAPI?.ready")
    assert bootstrap.index("showReturningVisitorGate()") < bootstrap.index("await window.CrumpAPI?.ready")
    assert bootstrap.index("await window.CrumpAPI?.ready") < bootstrap.index("window.deviceAuth.checkSession()")
    assert "if (authFlowRevision !== bootstrapAuthFlowRevision) return;" in bootstrap
    assert "authFlowRevision += 1;" in controller
