from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def test_sync_requests_are_bounded_through_body_parsing():
    manager = (PUBLIC / "sync-manager.js").read_text(encoding="utf-8")

    request = manager[
        manager.index("async function requestJson") : manager.index("async function pull")
    ]
    assert "SYNC_REQUEST_TIMEOUT_MS = 12_000" in manager
    assert "new AbortController()" in request
    assert "controller.abort()" in request
    assert "await fetch(url, {...options, signal: controller.signal})" in request
    assert "await response.json()" in request
    assert request.index("await response.json()") < request.index("window.clearTimeout(timeoutId)")


def test_changed_sync_manager_is_release_versioned_and_network_first():
    package = (ROOT / "package.json").read_text(encoding="utf-8")
    shell = (PUBLIC / "app.html").read_text(encoding="utf-8")
    runtime = (PUBLIC / "runtime-body-v1.js").read_text(encoding="utf-8")
    worker = (PUBLIC / "sw.js").read_text(encoding="utf-8")

    assert '"version": "5.9.75"' in package
    assert '<script defer src="/sync-manager.js?v=5.9.75"></script>' not in shell
    assert "['/sync-manager.js?v=5.9.75', 'workspacesync']" in runtime
    assert "'/sync-manager.js?v=5.9.75'" in worker
    assert '<script defer src="/presence-manager.js?v=5.9.75"></script>' not in shell
    assert "['/presence-manager.js?v=5.9.75', 'workspacepresence']" in runtime
    assert "'/presence-manager.js?v=5.9.75'" in worker
    assert '<script defer src="/chat-sync.js?v=5.9.75"></script>' not in shell
    assert "['/chat-sync.js?v=5.9.75', 'workspacechatsync']" in runtime
    assert "'/chat-sync.js?v=5.9.75'" in worker
    assert "url.pathname === '/sync-manager.js'" in worker


def test_failed_push_keeps_the_queue_and_returns_a_retryable_result():
    manager = (PUBLIC / "sync-manager.js").read_text(encoding="utf-8")

    flush = manager[manager.index("async function flush") : manager.index("async function push")]
    assert "queued: true" in flush
    assert "retryable: true" in flush
    assert "Your work is still queued." in flush
    assert flush.index("write(key, [])") > flush.index("if (response.ok && data.success)")


def test_startup_draft_does_not_persist_or_schedule_a_blind_push():
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")

    create_chat = app[
        app.index("function createNewChat") : app.index("function openFreshConversationAtStartup")
    ]
    startup_start = app.index("function openFreshConversationAtStartup()")
    startup = app[startup_start : app.index("function loadChat", startup_start)]

    assert "function createNewChat()" in create_chat
    assert "beginFreshConversation();" in create_chat
    assert "createNewChat" not in startup
    assert "saveChats" not in startup
    assert "syncChatsToServer" not in startup
    assert "beginFreshConversation();" in startup


def test_reconnect_sync_has_one_owner():
    sync = (PUBLIC / "chat-sync.js").read_text(encoding="utf-8")
    presence = (PUBLIC / "presence-manager.js").read_text(encoding="utf-8")

    assert "window.addEventListener('online', () => synchronize());" in sync
    reconnect = presence[
        presence.index("function setOnline") : presence.index("async function loadPreferences")
    ]
    assert "announce('Back online. Syncing conversations.');" in reconnect
    assert "syncChatsFromServer" not in reconnect


def test_browser_fixture_uses_the_real_sync_manager_without_credentials_or_network_writes():
    fixture = (ROOT / "tests" / "fixtures" / "project-sync-stall.html").read_text(
        encoding="utf-8"
    )

    assert '<script src="/public/sync-manager.js?v=project-sync-fixture-1"></script>' in fixture
    assert "window.SyncManager.push" in fixture
    assert "return new Promise((_resolve, reject)" in fixture
    assert "options.signal?.addEventListener('abort'" in fixture
    assert "fixture-user" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture
