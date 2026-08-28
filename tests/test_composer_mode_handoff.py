from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_quick_actions_preserve_a_draft_and_synchronize_the_real_composer_state():
    app = read("app.js")

    assert "function primeComposer(scaffold)" in app
    assert "const draft = input.value.trim();" in app
    assert "input.value = `${scaffold}${draft}`" in app
    assert "input.dispatchEvent(new Event('input', { bubbles: true }))" in app
    assert "input.focus({ preventScroll: true })" in app
    assert "input.setSelectionRange?.(input.value.length, input.value.length)" in app


def test_reselecting_a_mode_does_not_duplicate_its_visible_scaffold():
    app = read("app.js")

    assert "normalizedDraft === normalizedScaffold" in app
    assert "normalizedDraft.startsWith(`${normalizedScaffold} `)" in app
    assert "else if (!alreadyPrimed)" in app
    assert "primeComposer(COMPOSER_SCAFFOLDS.image)" in app
    assert "primeComposer(COMPOSER_SCAFFOLDS.research)" in app
    assert "primeComposer(COMPOSER_SCAFFOLDS.code)" in app


def test_bare_scaffolds_are_stopped_before_usage_or_chat_mutation():
    app = read("app.js")
    send = app[app.index("async function sendMessage()"):app.index("window.retryMessage")]

    assert "const incompleteScaffold = Object.entries(COMPOSER_SCAFFOLDS)" in send
    assert "Add what you want Crump to research." in send
    assert "Add what you want Crump to create." in send
    assert "Add what you want Crump to help build or debug." in send
    assert send.index("if (incompleteScaffold)") < send.index("await ensureUsageAvailable()")
    assert send.index("if (incompleteScaffold)") < send.index("chat.messages.push(userMessage)")


def test_file_handoff_and_starter_measurement_contracts_remain_unchanged():
    body = read("crump-v1-body.js")

    assert "case 'file':" in body
    assert "forwardClick('attachBtn');" in body
    assert "eventKey: 'first-starter-intent'" in body
    assert "source: command" in body


def test_browser_fixture_is_credential_free_and_uses_the_real_handoff_sources():
    fixture = (ROOT / "tests" / "fixtures" / "composer-mode-handoff.html").read_text(
        encoding="utf-8"
    )

    assert '<script src="/public/app.js"></script>' in fixture
    assert '<script src="/public/crump-v1-body.js"></script>' in fixture
    assert 'data-v1-command="research"' in fixture
    assert 'data-v1-command="image"' in fixture
    assert 'data-v1-command="file"' in fixture
    assert "fetch(" not in fixture
    assert "password" not in fixture.lower()
