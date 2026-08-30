from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_desktop_rail_names_conversations_in_plain_language():
    shell = read("public/app.html")
    product = read("public/crump-product-5.3.js")

    assert '<span class="v1-rail-label">New</span>' in shell
    assert '<span class="v1-rail-label">Chats</span>' in shell
    assert '<span class="v1-rail-label">Projects</span>' in product
    assert 'aria-controls="sidebar" aria-expanded="true"' in shell
    assert 'aria-label="Chats"' in shell
    assert 'aria-label="Close Chats"' in shell
    assert 'aria-label="Open Chats"' in shell
    assert 'Conversation library' not in shell
    assert 'conversation library' not in shell


def test_conversation_library_control_exposes_and_tracks_its_state():
    body = read("public/crump-v1-body.js")
    styles = read("public/crump-v1-body.css")

    assert "function syncLibraryControl()" in body
    assert "control.setAttribute('aria-expanded', expanded ? 'true' : 'false')" in body
    assert "control.classList.toggle(chatsDrawerControl ? 'is-open' : 'is-active', expanded)" in body
    assert "if (chatsDrawerControl)" in body
    assert "const mobileMenu = control.id === 'menuBtn'" in body
    assert "? (expanded ? 'Close' : 'Open')" in body
    assert "control.setAttribute('aria-label', `${action} Chats`)" in body
    assert "sidebar.setAttribute('aria-hidden', expanded ? 'false' : 'true')" in body
    assert "sidebar.removeAttribute('inert')" in body
    assert "sidebar.setAttribute('inert', '')" in body
    assert "sidebar.dataset.v1InertRevision" in body
    assert "new MutationObserver(syncLibraryControl)" in body
    assert 'body.crump-v1-body .v1-rail-label {' in styles
    assert 'body.crump-v1-body .v1-rail-button[aria-expanded="true"]' in styles


def test_chats_is_an_ask_utility_instead_of_a_sixth_active_destination():
    navigation = read("public/crump-navigation-5.9.30.js")
    styles = read("public/crump-navigation-5.9.30.css")

    assert 'data-crump5930-library-toggle aria-label="Hide Chats"' in navigation
    assert "destinations.slice(1).map(buttonMarkup).join('')" in navigation
    assert ".crump5930-chats-toggle.is-open" in styles
    assert "Chats is Ask's conversation drawer, not a sixth product destination." in styles
    assert ".crump5930-chats-toggle.is-active" not in styles


def test_browser_fixture_uses_the_real_rail_assets_without_network_writes():
    fixture = read("tests/fixtures/conversation-library-discovery.html")

    assert '/public/crump-v1-body.css' in fixture
    assert '/public/crump-v1-body.js' in fixture
    assert '/public/assets/brand/crump-shell-lockup-light.png' in fixture
    assert 'data-v1-command="library"' in fixture
    assert '<span class="v1-rail-label">Chats</span>' in fixture
    assert 'aria-label="Chats"' in fixture
    assert 'Conversation library' not in fixture
    assert "fetch(" not in fixture
