from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def test_fresh_start_is_ephemeral_until_the_first_real_message():
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")

    fresh = app[
        app.index("function beginFreshConversation") :
        app.index("function loadChat(chatId)")
    ]
    send = app[
        app.index("async function sendMessage()") :
        app.index("window.retryMessage")
    ]

    assert "freshConversationRequested = true" in fresh
    assert "SafeStorage.removeItem(STORAGE_KEYS.CURRENT_CHAT)" in fresh
    assert "beginFreshConversation();" in fresh
    assert "saveChats" not in fresh
    assert "syncChatsToServer" not in fresh
    assert "ensureCurrentChat()" in send
    assert send.index("await ensureUsageAvailable()") < send.index("ensureCurrentChat()")
    assert send.index("ensureCurrentChat()") < send.index("chat.messages.push(userMessage)")


def test_pristine_legacy_device_rows_are_excluded_from_local_and_sync_state():
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    sync = (PUBLIC / "chat-sync.js").read_text(encoding="utf-8")

    assert "function isPristineChat(chat)" in app
    assert "!isPristineChat(chat)" in app
    assert "const isPristineChat = chat =>" in sync
    assert "if (isPristineChat(local)) continue" in sync
    assert "if (isPristineChat(row)) continue" in sync
    assert "local.filter(chat => !isPristineChat(chat)).map" in sync


def test_studio_sender_materializes_the_ephemeral_draft_before_saving():
    studio = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    send = studio[
        studio.index("async function studioSendMessage()") :
        studio.index("async function retryMessage")
    ]

    assert "currentChat() || window.ensureCurrentChat?.()" in send
    assert send.index("await ensureUsage()") < send.index("window.ensureCurrentChat?.()")
    assert send.index("window.ensureCurrentChat?.()") < send.index("fresh.messages.push(userMessage)")


def test_cross_device_fixture_has_no_credentials_or_production_writes():
    fixture = (
        ROOT / "tests" / "fixtures" / "cross-device-blank-startup.html"
    ).read_text(encoding="utf-8")

    assert "/public/app.js?v=cross-device-blank-startup-3" in fixture
    assert "/public/chat-sync.js?v=cross-device-blank-startup-3" in fixture
    assert "window.initializeAuthenticatedApp({id: 'fixture-user'" in fixture
    assert "window.__fixture.pushes.push(payload)" in fixture
    assert "server-conversation-1" in fixture
    assert "old-device-blank-1" in fixture
    assert "old-device-blank-2" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture
    assert "https://" not in fixture
