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
