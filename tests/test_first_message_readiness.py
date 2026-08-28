from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def test_usage_preflight_is_bounded_through_response_parsing():
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")

    preflight = app[
        app.index("async function ensureUsageAvailable")
        : app.index("async function recordFirstSuccessfulResponse")
    ]
    assert "USAGE_PREFLIGHT_TIMEOUT_MS = 10_000" in app
    assert "new AbortController()" in preflight
    assert "controller.abort()" in preflight
    assert "fetch('/api/usage/check', {signal: controller.signal})" in preflight
    assert "await usageResponse.json()" in preflight
    assert preflight.index("await usageResponse.json()") < preflight.index(
        "window.clearTimeout(timeoutId)"
    )


def test_changed_first_message_asset_is_release_versioned():
    package = (ROOT / "package.json").read_text(encoding="utf-8")
    shell = (PUBLIC / "app.html").read_text(encoding="utf-8")
    worker = (PUBLIC / "sw.js").read_text(encoding="utf-8")

    assert '"version": "5.9.51"' in package
    assert '<script defer src="/app.js?v=5.9.51"></script>' in shell
    assert "'/app.js?v=5.9.51'" in worker


def test_pre_message_failure_preserves_the_draft_and_explains_recovery():
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")

    send = app[app.index("async function sendMessage") : app.index("window.retryMessage")]
    assert "Message check took too long. Your draft is still here — try again." in app
    assert "if (userMessage)" in send
    assert "} else {" in send
    assert "showToast(error.message || 'Crump could not start this message. Try again.', 'error')" in send
    assert "userInput?.focus({ preventScroll: true })" in send
    assert send.index("await ensureUsageAvailable()") < send.index("userInput.value = ''")


def test_browser_fixture_uses_real_first_message_code_without_credentials_or_production_writes():
    fixture = (ROOT / "tests" / "fixtures" / "first-message-preflight-stall.html").read_text(
        encoding="utf-8"
    )

    assert '<script src="/public/app.js?v=first-message-fixture-2"></script>' in fixture
    assert "url.pathname === '/api/usage/check'" in fixture
    assert "return new Promise((_resolve, reject)" in fixture
    assert "options.signal?.addEventListener('abort'" in fixture
    assert "Draft a launch plan for a neighborhood bakery." in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture
